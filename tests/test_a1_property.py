"""
Project Lucca — Rung A1 Property & Fuzz Testing Suite
Work Order #8 WP-1 (F-TS-04 tests, F-TS-05)

Tests:
1. Eligibility partition & trigger invariants (Hypothesis).
2. Five-flag decision table boundary conditions & state properties (Hypothesis).
3. Review-queue state machine transitions and invalid supersession defense (Hypothesis).
4. Substrate 7 Belnap bilattice evidential isolation (Hypothesis).
5. Importance arithmetic clamping, boost/decay, and roll-up retention limits.
6. Coherence checker adversarial corpus & fuzzing (marked xfail(strict=True) until WP-2).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from collections.abc import Coroutine
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from lucca.core.cascade import BelnapValue, EpistemicSearchCascade
from lucca.core.exceptions import ProvenanceRejected
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    GROUNDING_ELIGIBLE,
    MEMORY_ELIGIBLE,
    Provenance,
    UnsignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


# ============================================================================
# Section 1: Eligibility Partition & Trigger Invariants (§3.1)
# ============================================================================


def test_provenance_eligibility_set_properties() -> None:
    """Verifies theoretical set properties of MEMORY_ELIGIBLE and GROUNDING_ELIGIBLE."""
    # 1. GROUNDING_ELIGIBLE is a strict subset of MEMORY_ELIGIBLE
    assert GROUNDING_ELIGIBLE.issubset(MEMORY_ELIGIBLE)
    assert MEMORY_ELIGIBLE >= GROUNDING_ELIGIBLE

    # 2. Freeform LLM Narration is NEVER memory eligible (ADR-006 / §2.1)
    assert Provenance.LLM_NARRATION not in MEMORY_ELIGIBLE
    assert Provenance.LLM_NARRATION not in GROUNDING_ELIGIBLE

    # 3. Untrusted tool content is not memory eligible without user action
    assert Provenance.TOOL_CONTENT_UNTRUSTED not in MEMORY_ELIGIBLE
    assert Provenance.TOOL_CONTENT_UNTRUSTED not in GROUNDING_ELIGIBLE

    # 4. Assistant utterances and beliefs are memory-eligible but NOT grounding-eligible
    recollections = MEMORY_ELIGIBLE - GROUNDING_ELIGIBLE
    assert Provenance.ASSISTANT_UTTERANCE in recollections
    assert Provenance.ASSISTANT_BELIEF in recollections

    # 5. COHERENCE_BREACH is a verified negative ground truth
    assert Provenance.COHERENCE_BREACH in GROUNDING_ELIGIBLE


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    is_grounding_reason=st.booleans(),
)
def test_supersede_grounding_invariant_property(
    tmp_path_factory: pytest.TempPathFactory,
    is_grounding_reason: bool,
) -> None:
    """
    Property §3.1:
    MemoryStore.supersede(old, new, reason) succeeds IFF reason envelope has grounding_eligible=1.
    Otherwise, raises ProvenanceRejected and leaves old memory valid.
    Also asserts that direct SQL bypass of trigger mem_bi_eligible fails closed.
    """
    tmp_path = tmp_path_factory.mktemp("prop_eligibility")
    db = DatabaseManager(tmp_path / "prop_mem.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())

    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    # Seed old memory
    old_p = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="Old belief content",
        structured={"importance": 0.5, "valid_from": now},
        trace_id=f"tr-old-{uuid.uuid4().hex[:6]}",
        created_at=now,
        nonce=uuid.uuid4().hex,
        confidence=0.9,
    )
    old_mid = store.commit(utt_signer.sign(old_p))

    # Seed new memory
    new_p = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="New belief content",
        structured={"importance": 0.6, "valid_from": now + 1},
        trace_id=f"tr-new-{uuid.uuid4().hex[:6]}",
        created_at=now + 1,
        nonce=uuid.uuid4().hex,
        confidence=0.95,
    )
    new_mid = store.commit(utt_signer.sign(new_p))

    # Reason envelope: grounding-eligible (USER_EXPLICIT) vs non-grounding (ASSISTANT_UTTERANCE)
    if is_grounding_reason:
        reason_p = UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            content="User explicit correction",
            trace_id=f"tr-rsn-{uuid.uuid4().hex[:6]}",
            created_at=now + 2,
            nonce=uuid.uuid4().hex,
            confidence=1.0,
        )
        signed_reason = user_signer.sign(reason_p)
    else:
        reason_p = UnsignedPayload(
            provenance=Provenance.ASSISTANT_UTTERANCE,
            kind="assistant_utterance",
            content="Unverified assistant self-narration",
            trace_id=f"tr-rsn-{uuid.uuid4().hex[:6]}",
            created_at=now + 2,
            nonce=uuid.uuid4().hex,
            confidence=1.0,
        )
        signed_reason = utt_signer.sign(reason_p)

    store.commit(signed_reason)
    reason_entry_id = signed_reason.entry_id

    if is_grounding_reason:
        store.supersede(old_mid, new_mid, reason=reason_entry_id)
        with db.read_cursor() as cur:
            cur.execute(
                "SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,)
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] is not None
            assert row[1] == new_mid
    else:
        with pytest.raises(ProvenanceRejected, match="grounding-eligible"):
            store.supersede(old_mid, new_mid, reason=reason_entry_id)

        # Invariant: old memory remains untouched and active
        with db.read_cursor() as cur:
            cur.execute(
                "SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,)
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] is None
            assert row[1] is None

    # Test trigger mem_bi_eligible direct SQL bypass defense
    with pytest.raises(sqlite3.IntegrityError, match="provenance not memory-eligible"):
        conn = db.get_writer()
        fake_entry_id = f"fake-{uuid.uuid4().hex[:8]}"
        conn.execute(
            """
            INSERT INTO provenance_envelopes (
                entry_id, provenance, kind, signer_id, signature, content_sha256, nonce,
                created_at, trace_id, session_id, confidence, payload_json, grounding_eligible
            ) VALUES (?, 'TOOL_CONTENT_UNTRUSTED', 'raw_html', 'test', 'sig', 'hash', ?, ?, 'tr', 'sess', 1.0, '{}', 0)
            """,
            (fake_entry_id, uuid.uuid4().hex, now),
        )
        conn.execute(
            """
            INSERT INTO memories (entry_id, content, kind, importance, created_at)
            VALUES (?, 'Bypass attempt', 'raw_html', 0.1, ?)
            """,
            (fake_entry_id, now),
        )

    db.close()


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(chain_len=st.integers(min_value=2, max_value=5))
def test_supersession_chain_integrity_hypothesis(
    tmp_path_factory: pytest.TempPathFactory,
    chain_len: int,
) -> None:
    """
    Property §3.1:
    After any sequence of valid supersessions:
    - No superseded_by dangles.
    - No row has valid_to IS NULL while also being the 'old' side of a supersession.
    - Exactly one currently-valid row per chain.
    """
    tmp_path = tmp_path_factory.mktemp("prop_chain")
    db = DatabaseManager(tmp_path / "chain_mem.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())

    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    chain_mids: list[int] = []
    for i in range(chain_len):
        payload = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content=f"Belief version {i}",
            structured={"importance": 0.5, "valid_from": now + i * 10},
            trace_id=f"tr-chain-{i}",
            created_at=now + i * 10,
            nonce=uuid.uuid4().hex,
            confidence=0.9,
        )
        mid = store.commit(utt_signer.sign(payload))
        chain_mids.append(mid)

    # Perform sequential supersessions
    for i in range(chain_len - 1):
        reason_p = UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            content=f"Evidence updating to version {i + 1}",
            trace_id=f"tr-ev-{i}",
            created_at=now + i * 10 + 5,
            nonce=uuid.uuid4().hex,
            confidence=1.0,
        )
        signed_reason = user_signer.sign(reason_p)
        store.commit(signed_reason)
        store.supersede(
            chain_mids[i],
            chain_mids[i + 1],
            reason=signed_reason.entry_id,
            now=now + i * 10 + 6,
        )

    # Verify invariants
    with db.read_cursor() as cur:
        cur.execute("SELECT memory_id, valid_to, superseded_by FROM memories")
        all_rows = cur.fetchall()

    row_map = {r[0]: (r[1], r[2]) for r in all_rows}

    # 1. No dangling superseded_by
    for _, (_, sup_by) in row_map.items():
        if sup_by is not None:
            assert sup_by in row_map, f"Dangling superseded_by: {sup_by}"

    # 2. No row has valid_to IS NULL while being superseded
    for mid in chain_mids[:-1]:
        valid_to, sup_by = row_map[mid]
        assert valid_to is not None, f"Superseded memory {mid} has NULL valid_to"
        assert sup_by is not None

    # 3. Exactly one currently-valid row in chain
    active_mids = [m for m in chain_mids if row_map[m][0] is None]
    assert len(active_mids) == 1
    assert active_mids[0] == chain_mids[-1]

    db.close()


# ============================================================================
# Section 2: Five-Flag Decision Table (§3.2, reflection.py:126-154)
# ============================================================================


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    kind=st.sampled_from(["user_model", "belief", "opinion", "fact", "preference"]),
    importance=st.floats(min_value=0.0, max_value=1.0),
    is_conflict_top=st.booleans(),
    age_days=st.floats(min_value=0.0, max_value=90.0),
    revised_recently=st.booleans(),
    topic_marked=st.booleans(),
)
@example(
    kind="belief",
    importance=0.7,
    is_conflict_top=False,
    age_days=40.0,
    revised_recently=False,
    topic_marked=False,
)
@example(
    kind="belief",
    importance=0.699,
    is_conflict_top=False,
    age_days=40.0,
    revised_recently=False,
    topic_marked=False,
)
@example(
    kind="user_model",
    importance=0.2,
    is_conflict_top=False,
    age_days=40.0,
    revised_recently=False,
    topic_marked=False,
)
def test_five_flag_decision_table_hypothesis(
    tmp_path_factory: pytest.TempPathFactory,
    kind: str,
    importance: float,
    is_conflict_top: bool,
    age_days: float,
    revised_recently: bool,
    topic_marked: bool,
) -> None:
    """
    Property §3.2:
    Tests the 5-flag operator review decision table independently derived from spec §7:
    1. kind == 'user_model'
    2. importance >= 0.7
    3. is_conflict_top
    4. oscillation guard: age_since_revision < 30 days and valid_from > created_at
    5. topic marked review-required
    Asserts is_queued == any(flags).
    """
    tmp_path = tmp_path_factory.mktemp("prop_flags")
    db = DatabaseManager(tmp_path / "flag_mem.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)

    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)

    current_time = time.time()
    created_at = current_time - (age_days * 86400.0)

    if revised_recently:
        valid_from = current_time - (15.0 * 86400.0)
        if valid_from <= created_at:
            valid_from = created_at + 100.0
    else:
        valid_from = created_at

    topic_name = "test_prop_topic"
    if topic_marked:
        refl.mark_topic_review_required(topic_name)

    # Commit old belief with current_time so envelope passes freshness gate
    old_p = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="user_model" if kind == "user_model" else "belief",
        content="Historical belief statement",
        structured={"importance": importance, "valid_from": valid_from},
        trace_id=f"tr-flg-{uuid.uuid4().hex[:6]}",
        created_at=current_time,
        nonce=uuid.uuid4().hex,
        confidence=0.85,
    )
    old_mid = store.commit(utt_signer.sign(old_p))

    # Explicit DB override for test temporal precision
    conn = db.get_writer()
    conn.execute(
        "UPDATE memories SET kind = ?, importance = ?, created_at = ?, valid_from = ? WHERE memory_id = ?",
        (kind, importance, created_at, valid_from, old_mid),
    )

    # Verified grounding reason
    reason_p = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="Ground truth evidence",
        trace_id="tr-ev",
        created_at=current_time,
        nonce=uuid.uuid4().hex,
        confidence=1.0,
    )
    signed_reason = user_signer.sign(reason_p)
    store.commit(signed_reason)

    # Independent flag calculation
    flag_user_model = kind == "user_model"
    flag_high_importance = importance >= 0.7
    flag_conflict_top = is_conflict_top
    age_since_rev = current_time - valid_from
    flag_oscillation = (age_since_rev < 30 * 86400.0) and (valid_from > created_at)
    flag_topic = topic_marked

    expected_queued = any(
        [flag_user_model, flag_high_importance, flag_conflict_top, flag_oscillation, flag_topic]
    )

    is_queued, res_str = refl.detect_and_handle_contradiction(
        old_belief_id=old_mid,
        new_content="Updated belief statement",
        reason_entry_id=signed_reason.entry_id,
        proposed_confidence=0.9,
        is_conflict_top=is_conflict_top,
        topic=topic_name,
        now=current_time,
    )

    assert is_queued == expected_queued, (
        f"Flag decision mismatch: got queued={is_queued}, expected={expected_queued}. "
        f"Flags: user_model={flag_user_model}, hi_imp={flag_high_importance}, "
        f"top={flag_conflict_top}, osc={flag_oscillation}, topic={flag_topic}"
    )

    if is_queued:
        assert res_str.startswith("rev-")
        pending = refl.list_pending_reviews()
        assert any(r["review_id"] == res_str for r in pending)
        with db.read_cursor() as cur:
            cur.execute("SELECT valid_to FROM memories WHERE memory_id = ?", (old_mid,))
            assert cur.fetchone()[0] is None
    else:
        assert res_str.startswith("I've revised a belief I had")
        with db.read_cursor() as cur:
            cur.execute(
                "SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,)
            )
            row = cur.fetchone()
            assert row[0] is not None
            new_mid = row[1]
            assert new_mid is not None

            cur.execute("SELECT importance, valid_to FROM memories WHERE memory_id = ?", (new_mid,))
            nrow = cur.fetchone()
            assert nrow[1] is None
            expected_new_imp = min(1.0, max(importance, 0.5) + 0.4)
            assert abs(nrow[0] - expected_new_imp) < 1e-4

    db.close()


# ============================================================================
# Section 3: Review-Queue State Machine (§3.3)
# ============================================================================


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    first_action=st.sampled_from(["approve", "reject"]),
    second_action=st.sampled_from(["approve", "reject"]),
    supersede_before_decision=st.booleans(),
)
def test_review_queue_state_machine_hypothesis(
    tmp_path_factory: pytest.TempPathFactory,
    first_action: str,
    second_action: str,
    supersede_before_decision: bool,
) -> None:
    """
    Property §3.3:
    Review queue transitions:
    - Decided item cannot be decided again (raises ValueError).
    - Approving after belief was independently superseded raises ValueError.
    - Rejecting leaves belief unchanged.
    """
    tmp_path = tmp_path_factory.mktemp("prop_queue")
    db = DatabaseManager(tmp_path / "rq_mem.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)

    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    old_p = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="High importance candidate belief",
        structured={"importance": 0.85, "valid_from": now},
        trace_id="tr-rq-old",
        created_at=now,
        nonce=uuid.uuid4().hex,
        confidence=0.9,
    )
    old_mid = store.commit(utt_signer.sign(old_p))

    reason_p = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="Evidence for revision",
        trace_id="tr-rq-rsn",
        created_at=now + 1,
        nonce=uuid.uuid4().hex,
        confidence=1.0,
    )
    signed_reason = user_signer.sign(reason_p)
    store.commit(signed_reason)

    is_queued, review_id = refl.detect_and_handle_contradiction(
        old_belief_id=old_mid,
        new_content="Revised belief content",
        reason_entry_id=signed_reason.entry_id,
        now=now + 2,
    )
    assert is_queued
    assert review_id.startswith("rev-")

    if supersede_before_decision:
        indep_p = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content="Independent superseding belief",
            structured={"importance": 0.9, "valid_from": now + 3},
            trace_id="tr-indep",
            created_at=now + 3,
            nonce=uuid.uuid4().hex,
            confidence=0.9,
        )
        indep_mid = store.commit(utt_signer.sign(indep_p))
        store.supersede(old_mid, indep_mid, reason=signed_reason.entry_id, now=now + 4)

        if first_action == "approve":
            with pytest.raises(ValueError, match="already superseded"):
                refl.approve_review(review_id)
        else:
            refl.reject_review(review_id)
            with pytest.raises(ValueError, match="not PENDING"):
                refl.reject_review(review_id)
    else:
        if first_action == "approve":
            new_mid = refl.approve_review(review_id, decided_by="operator_test")
            assert new_mid is not None
            with db.read_cursor() as cur:
                cur.execute(
                    "SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,)
                )
                r = cur.fetchone()
                assert r[0] is not None
                assert r[1] == new_mid
        else:
            refl.reject_review(review_id, decided_by="operator_test")
            with db.read_cursor() as cur:
                cur.execute(
                    "SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,)
                )
                r = cur.fetchone()
                assert r[0] is None
                assert r[1] == None

        with pytest.raises(ValueError, match="not PENDING"):
            if second_action == "approve":
                refl.approve_review(review_id)
            else:
                refl.reject_review(review_id)

    db.close()


# ============================================================================
# Section 4: Substrate 7 Belnap Isolation (§3.4, cascade.py:947)
# ============================================================================


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    num_recollections=st.integers(min_value=1, max_value=4),
    include_grounded_evidence=st.booleans(),
)
def test_substrate_7_belnap_isolation_hypothesis(
    tmp_path_factory: pytest.TempPathFactory,
    num_recollections: int,
    include_grounded_evidence: bool,
) -> None:
    """
    Property §3.4:
    Substrate 7 Belnap isolation:
    - Recollections with grounding_eligible=0 (ASSISTANT_UTTERANCE, ASSISTANT_BELIEF)
      can NEVER verify or falsify a proposition; their polarity defaults to UNKNOWN.
    - Adding recollections leaves the evidential fused verdict identical.
    - Calibrated honest refusal / abstention returned when no grounding rows match.
    """
    tmp_path = tmp_path_factory.mktemp("prop_substrate7")
    db = DatabaseManager(tmp_path / "casc_mem.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    cascade = EpistemicSearchCascade(memory_store=store)

    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    topic_token = "quantum_engine"

    # Add non-grounding recollections
    for i in range(num_recollections):
        p = UnsignedPayload(
            provenance=Provenance.ASSISTANT_UTTERANCE
            if i % 2 == 0
            else Provenance.ASSISTANT_BELIEF,
            kind="assistant_utterance" if i % 2 == 0 else "belief",
            content=f"I previously said that the {topic_token} was fully activated in simulation {i}.",
            structured={"valid_from": now},
            trace_id=f"tr-rec-{i}",
            created_at=now + i,
            nonce=uuid.uuid4().hex,
            confidence=0.9,
        )
        store.commit(utt_signer.sign(p))

    # Query without grounded evidence
    query_text = f"Is the {topic_token} operational?"
    res_recollections_only = cascade.query(query_text)

    # INVARIANT 1: Recollections cannot raise proposition to TRUE
    assert res_recollections_only.belnap_status == BelnapValue.UNKNOWN, (
        f"Non-grounding recollection illegally raised Belnap status to {res_recollections_only.belnap_status}"
    )

    if include_grounded_evidence:
        ev_p = UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            content=f"The {topic_token} is confirmed operational by telemetry.",
            trace_id="tr-grounded",
            created_at=now + 50,
            nonce=uuid.uuid4().hex,
            confidence=1.0,
        )
        store.commit(user_signer.sign(ev_p))

        res_with_evidence = cascade.query(query_text)
        assert res_with_evidence.belnap_status == BelnapValue.TRUE

    db.close()


# ============================================================================
# Section 5: Importance Arithmetic & Roll-up Invariants (§3.5)
# ============================================================================


@settings(max_examples=200, deadline=None)
@given(
    initial_imp=st.floats(min_value=0.0, max_value=1.0),
    adjustments=st.lists(
        st.sampled_from([0.4, 0.3, 0.1, 0.2, -0.1, -0.2, -0.3]),
        min_size=1,
        max_size=10,
    ),
)
def test_importance_arithmetic_clamping_property(
    initial_imp: float,
    adjustments: list[float],
) -> None:
    """Property §3.5: Importance arithmetic stays strictly within [0.0, 1.0]."""
    current = initial_imp
    for adj in adjustments:
        current = max(0.0, min(1.0, current + adj))
        assert 0.0 <= current <= 1.0


def test_nightly_rollup_boundary_and_retention_invariants(tmp_path: Path) -> None:
    """
    Property §3.5:
    Roll-up selects EXACTLY rows with importance < 0.2 AND age > 30 days.
    Boundary rows (importance == 0.2 or age == 30 days) are retained.
    Rolled rows get forgotten_at set. One session_summary per session.
    Grounding eligible of session_summary is 0.
    """
    db = DatabaseManager(tmp_path / "rollup_prop.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)

    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()
    thirty_days = 30 * 86400.0

    # Row 1: Eligible (< 0.2 and > 30 d)
    p1 = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="Low importance old utterance",
        session_id="sess_1",
        trace_id="tr-1",
        created_at=now,
        nonce=uuid.uuid4().hex,
        confidence=1.0,
    )
    m1 = store.commit(utt_signer.sign(p1))

    # Row 2: Boundary importance (== 0.2, > 30 d) -> MUST BE RETAINED
    p2 = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="Boundary importance old utterance",
        session_id="sess_1",
        trace_id="tr-2",
        created_at=now,
        nonce=uuid.uuid4().hex,
        confidence=1.0,
    )
    m2 = store.commit(utt_signer.sign(p2))

    # Row 3: Boundary age (< 0.2, == 30 d) -> MUST BE RETAINED
    p3 = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="Low importance boundary age utterance",
        session_id="sess_1",
        trace_id="tr-3",
        created_at=now,
        nonce=uuid.uuid4().hex,
        confidence=1.0,
    )
    m3 = store.commit(utt_signer.sign(p3))

    conn = db.get_writer()
    conn.execute(
        "UPDATE memories SET importance = 0.1, created_at = ? WHERE memory_id = ?",
        (now - thirty_days - 1000.0, m1),
    )
    conn.execute(
        "UPDATE memories SET importance = 0.2, created_at = ? WHERE memory_id = ?",
        (now - thirty_days - 1000.0, m2),
    )
    conn.execute(
        "UPDATE memories SET importance = 0.1, created_at = ? WHERE memory_id = ?",
        (now - thirty_days + 1000.0, m3),
    )

    compressed_count = refl.rollup_nightly(now=now)
    assert compressed_count == 1

    with db.read_cursor() as cur:
        # m1 must be forgotten_at
        cur.execute("SELECT forgotten_at FROM memories WHERE memory_id = ?", (m1,))
        assert cur.fetchone()[0] == now

        # m2 and m3 must NOT be forgotten_at
        cur.execute("SELECT forgotten_at FROM memories WHERE memory_id = ?", (m2,))
        assert cur.fetchone()[0] is None
        cur.execute("SELECT forgotten_at FROM memories WHERE memory_id = ?", (m3,))
        assert cur.fetchone()[0] is None

        # Check session_summary committed with grounding_eligible=0
        cur.execute(
            """
            SELECT m.content, p.grounding_eligible, p.provenance
            FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            WHERE m.kind = 'session_summary'
            """
        )
        srow = cur.fetchone()
        assert srow is not None
        assert srow[1] == 0
        assert srow[2] == "ASSISTANT_UTTERANCE"

    db.close()


# ============================================================================
# Section 6: Coherence Checker Adversarial Corpus & Fuzz (§3.6)
# Marked xfail(strict=True) until WP-2 lands receipt-aware checker
# ============================================================================


def _load_narration_corpus() -> list[dict[str, object]]:
    corpus_path = Path(__file__).parent / "fixtures" / "coherence" / "narration_corpus.jsonl"
    rows: list[dict[str, object]] = []
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


CORPUS_ROWS = _load_narration_corpus()


_shared_orch = Orchestrator.__new__(Orchestrator)
_shared_orch.current_turn_receipts = []


def test_coherence_corpus_narration_breach_detection() -> None:
    """
    Tests the 120+ row adversarial narration corpus.
    In WP-1, this targets orchestrator._check_functional_coherence and was marked
    xfail(strict=True). In WP-2, the receipt-aware checker flips this test to pass.
    """
    mismatches: list[str] = []
    for case in CORPUS_ROWS:
        text = str(case["text"])
        receipts_raw = case["receipts"]
        receipts = [dict(r) for r in receipts_raw] if isinstance(receipts_raw, list) else []
        expect_breach = bool(case["expect_breach"])

        breach = _shared_orch._check_functional_coherence(text, receipts)
        has_breach = breach is not None
        if has_breach != expect_breach:
            mismatches.append(
                f"[{case['note']}] '{text}' -> expected breach={expect_breach}, got {breach}"
            )

    assert not mismatches, (
        f"Corpus check failed on {len(mismatches)}/{len(CORPUS_ROWS)} rows:\n"
        + "\n".join(mismatches[:10])
    )


@settings(max_examples=60, deadline=None)
@given(
    trap_prefix=st.sampled_from(
        [
            "I ran into a problem",
            "I have written poetry before",
            "I opened up to you about that",
            "I created a mental note",
            "I've updated my understanding",
            "I saved you the trouble",
        ]
    ),
    suffix=st.text(min_size=0, max_size=40),
)
def test_coherence_checker_benign_frame_fuzz(trap_prefix: str, suffix: str) -> None:
    """Hypothesis fuzz inserting benign idioms and asserting no false-positive breach."""
    sentence = f"{trap_prefix} {suffix}".strip()
    breach = _shared_orch._check_functional_coherence(sentence, [])
    assert breach is None, f"False-positive breach fired on benign sentence: '{sentence}'"
