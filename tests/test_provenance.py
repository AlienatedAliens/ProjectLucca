"""
Project Lucca — Provenance Signers & Gate Mechanical Tests
Spec 03 §6 (T-PROV-01 through T-PROV-05)
"""

import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lucca.core.exceptions import ProvenanceRejected
from lucca.core.schemas import (
    LLMNarration,
    Provenance,
    UnsignedPayload,
)
from lucca.memory.gate import ProvenanceGate
from lucca.memory.signers import (
    DerivedFactSigner,
    LispAssertionSigner,
    ToolResultSigner,
    UserSpeechSigner,
    canonicalize_unsigned_payload,
)

TEST_MASTER_KEY = b"01234567890123456789012345678901"  # 32 bytes


@pytest.fixture
def gate():
    return ProvenanceGate(master_key=TEST_MASTER_KEY)


@pytest.fixture
def user_signer():
    return UserSpeechSigner(master_key=TEST_MASTER_KEY)


@pytest.fixture
def fact_signer():
    return DerivedFactSigner(master_key=TEST_MASTER_KEY)


@pytest.fixture
def tool_signer():
    return ToolResultSigner(master_key=TEST_MASTER_KEY)


@pytest.fixture
def lisp_signer():
    return LispAssertionSigner(master_key=TEST_MASTER_KEY)


def test_t_prov_01_canonicalisation_key_order_independent():
    """T-PROV-01: Canonicalisation is key-order independent; field changes alter entry_id."""
    now = time.time()
    payload1 = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="hello world",
        structured={"b": 2, "a": 1},
        trace_id="trace-1",
        session_id="sess-1",
        created_at=now,
        nonce="nonce12345678901",
        confidence=1.0,
    )
    payload2 = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="hello world",
        structured={"a": 1, "b": 2},  # Reordered dict keys
        trace_id="trace-1",
        session_id="sess-1",
        created_at=now,
        nonce="nonce12345678901",
        confidence=1.0,
    )
    assert canonicalize_unsigned_payload(payload1) == canonicalize_unsigned_payload(payload2)

    # Any field change produces a different canonical serialization
    payload3 = payload1.model_copy(update={"content": "hello world!"})
    assert canonicalize_unsigned_payload(payload1) != canonicalize_unsigned_payload(payload3)


def test_t_prov_02_signer_authorization_matrix(user_signer, fact_signer, tool_signer, lisp_signer):
    """T-PROV-02: Every provenance x every signer: only allowed pairs sign; others raise."""
    now = time.time()

    def make_payload(p: Provenance) -> UnsignedPayload:
        return UnsignedPayload(
            provenance=p,
            kind="transcript" if "USER" in p.value else "tool_fact",
            content="test content",
            source_entry_ids=["src1"] if p == Provenance.USER_DERIVED else [],
            created_at=now,
            nonce=f"nonce_{p.value}",
        )

    # UserSpeechSigner: USER_EXPLICIT, USER_EXPLICIT_LOWCONF
    assert user_signer.sign(make_payload(Provenance.USER_EXPLICIT)).signature
    assert user_signer.sign(make_payload(Provenance.USER_EXPLICIT_LOWCONF)).signature
    with pytest.raises(ProvenanceRejected):
        user_signer.sign(make_payload(Provenance.TOOL_VERIFIED))
    with pytest.raises(ProvenanceRejected):
        user_signer.sign(make_payload(Provenance.USER_DERIVED))

    # DerivedFactSigner: USER_DERIVED only
    assert fact_signer.sign(make_payload(Provenance.USER_DERIVED)).signature
    with pytest.raises(ProvenanceRejected):
        fact_signer.sign(make_payload(Provenance.USER_EXPLICIT))

    # ToolResultSigner: TOOL_VERIFIED, TOOL_CONTENT_UNTRUSTED
    assert tool_signer.sign(make_payload(Provenance.TOOL_VERIFIED)).signature
    assert tool_signer.sign(make_payload(Provenance.TOOL_CONTENT_UNTRUSTED)).signature
    with pytest.raises(ProvenanceRejected):
        tool_signer.sign(make_payload(Provenance.LISP_ASSERTION))

    # LispAssertionSigner: LISP_ASSERTION only
    assert lisp_signer.sign(make_payload(Provenance.LISP_ASSERTION)).signature
    with pytest.raises(ProvenanceRejected):
        lisp_signer.sign(make_payload(Provenance.USER_EXPLICIT))


def test_t_prov_03_tamper_detection(user_signer, gate):
    """T-PROV-03: Tamper any field after signing -> gate rejects."""
    now = time.time()
    unsigned = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="Open calculator please",
        created_at=now,
        nonce="nonce_tamper_test1",
    )
    signed = user_signer.sign(unsigned)

    # Legitimate signature is admitted
    admitted = gate.admit(signed, now=now)
    assert admitted.payload.entry_id == signed.entry_id

    # 1. Tamper content -> caught by entry_id
    tampered_content = signed.model_copy(
        update={"content": "Open malicious_app please", "nonce": "nonce_tamper_2"}
    )
    with pytest.raises(ProvenanceRejected, match="Tampered entry_id"):
        gate.admit(tampered_content, now=now)

    # 2. Tamper content_sha256 directly (keep nonce so entry_id matches)
    tampered_hash = signed.model_copy(update={"content_sha256": "0" * 64})
    with pytest.raises(ProvenanceRejected, match="Tampered content_sha256"):
        gate.admit(tampered_hash, now=now)

    # 3. Tamper signature
    tampered_sig = signed.model_copy(update={"signature": "bad_sig" + signed.signature[7:]})
    with pytest.raises(ProvenanceRejected, match="Invalid cryptographic signature"):
        gate.admit(tampered_sig, now=now)

    # 4. Tamper session_id
    tampered_sess = signed.model_copy(
        update={"session_id": "other_sess", "nonce": "nonce_tamper_4"}
    )
    with pytest.raises(ProvenanceRejected):
        gate.admit(tampered_sess, now=now)


def test_t_prov_04_replay_rejection(user_signer, gate):
    """T-PROV-04: Replay same payload twice -> second rejected."""
    now = time.time()
    unsigned = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="Testing replay defense",
        created_at=now,
        nonce="nonce_replay_unique",
    )
    signed = user_signer.sign(unsigned)

    # First admission succeeds
    gate.admit(signed, now=now)

    # Replaying identical payload fails
    with pytest.raises(ProvenanceRejected, match="Replay detected"):
        gate.admit(signed, now=now)


def test_t_prov_05_freshness_window(user_signer, gate):
    """T-PROV-05: created_at 301 s old -> rejected; 299 s -> accepted."""
    now = 1000000.0

    # 299s old -> accepted
    payload_valid = user_signer.sign(
        UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            content="Fresh payload",
            created_at=now - 299.0,
            nonce="nonce_fresh_299",
        )
    )
    admitted = gate.admit(payload_valid, now=now)
    assert admitted.payload.nonce == "nonce_fresh_299"

    # 301s old -> rejected
    payload_stale = user_signer.sign(
        UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            content="Stale payload",
            created_at=now - 301.0,
            nonce="nonce_stale_301",
        )
    )
    with pytest.raises(ProvenanceRejected, match="expired"):
        gate.admit(payload_stale, now=now)


def test_llm_narration_unconditionally_rejected(gate):
    """LLM_NARRATION is forbidden from entering memory."""
    narration = LLMNarration(text="I remembered your name", created_at=time.time())
    with pytest.raises(ProvenanceRejected, match="LLM_NARRATION is forbidden"):
        gate.admit(narration)


@given(
    content=st.text(min_size=1, max_size=100),
    trace_id=st.text(min_size=1, max_size=20),
    nonce=st.text(min_size=1, max_size=20),
    confidence=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=100, deadline=1000)
def test_p_05_canonical_json_invariants(content: str, trace_id: str, nonce: str, confidence: float):
    """P-05: Key-order independence; field changes alter canonical bytes / entry_id."""
    # Test dictionary key ordering invariance
    d1 = {"a": content, "b": trace_id, "c": {"x": 1, "y": 2}}
    d2 = {"b": trace_id, "c": {"y": 2, "x": 1}, "a": content}
    from lucca.memory.signers import canonicalize_payload_dict

    assert canonicalize_payload_dict(d1) == canonicalize_payload_dict(d2)

    # Test payload entry_id changes when content is modified
    p1 = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content=content,
        trace_id=trace_id,
        nonce=nonce,
        created_at=1000.0,
        confidence=confidence,
    )
    p2 = p1.model_copy(update={"content": content + "_mod"})
    assert canonicalize_unsigned_payload(p1) != canonicalize_unsigned_payload(p2)
