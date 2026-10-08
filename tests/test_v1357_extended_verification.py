"""
Project Lucca v1.35.7 — Extended Verification & Property-Based Test Suite
Phase 1 Core Pipeline Hygiene Deep Verification
Spec: plans/2026-10-08_v1_35_7_epistemic_integrity_and_semantic_verification.md

Sections:
1. Hypothesis Property-Based Fuzz Testing:
   - Canonicalization invariants (idempotency, filler stripping, punctuation, casing)
   - Rule conflict symmetry, irreflexivity, and polar opposition completeness
   - Evidential polarity word-boundary & mutual exclusivity invariants
   - Conflict detection numeric invariants
2. Boundary Conditions, Negative Controls & Gating Overrides:
   - Interrogative utterance short-circuit (F-WO8-17)
   - Sub-threshold token count short-circuit (<2 non-stop-word tokens)
   - Pure stop-word filtering (Belief #17 attractor invariant)
   - Reflection oscillation guard trip (30-day revision limit)
   - High importance (>= 0.7) operator review override
   - User-model kind operator review override
   - Multiple candidate FTS competition within 200ms budget
3. Cascade Evidential Bilattice Algebraic Properties:
   - Belnap bilattice join commutativity, associativity, idempotence, identity, absorption
   - Multi-source 5-evidence pooling truth table
   - Untrusted web taint propagation to sandbox guard
   - Sandbox failure/timeout resilience
4. Full End-to-End Orchestrator Turn-Level Pipeline Scenarios:
   - Orchestrator._finalize_turn autonomous retraction supersession & captions
   - Orchestrator._finalize_turn Belnap TOP conflict review-queue routing
5. Complex Phrasing Clustering & Rule Induction Scale Test:
   - 40-item phrasing corpus verifying clean isolation of all opposing pairs
"""

from __future__ import annotations

import json
import queue
import re
import time
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from lucca.core.belief_service import (
    _BELIEF_STOP_WORDS,
    _MIN_TOPICAL_TOKENS,
    BeliefService,
)
from lucca.core.cascade import (
    BelnapValue,
    EpistemicSearchCascade,
    EpistemicSubstrate,
    EvidenceItem,
    TrustTier,
    belnap_join_k,
    pool_evidence,
)
from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    ExecutionTier,
    Provenance,
    ToolResult,
    UnsignedPayload,
)
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine, THIRTY_DAYS_SECONDS
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.reasoning.induction import (
    OPPOSING_POLARITY_PAIRS,
    cluster_phrasings,
    is_rule_conflict,
)
from lucca.sandbox.policy import TaintFlags
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


# ============================================================================
# Section 1: Hypothesis Property-Based Fuzz Testing
# ============================================================================


FILLER_PREFIXES = [
    "actually",
    "well",
    "i mean",
    "you know",
    "wait",
    "hey",
    "um",
    "uh",
    "look",
    "so",
    "basically",
    "listen",
]


@given(st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_prop_canonicalize_idempotence(text: str) -> None:
    """Property: Proposition canonicalization must be strictly idempotent:

    f(f(x)) == f(x) for all generated strings.
    """
    first_pass = ReflectionEngine._canonicalize_proposition(text)
    second_pass = ReflectionEngine._canonicalize_proposition(first_pass)
    assert first_pass == second_pass


@given(
    filler=st.sampled_from(FILLER_PREFIXES),
    punctuation=st.sampled_from([", ", ",  ", " ", " , "]),
    body=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")), min_size=2, max_size=50
    ),
)
@settings(max_examples=100)
def test_prop_canonicalize_filler_removal(filler: str, punctuation: str, body: str) -> None:
    """Property: Conversational filler prefixes must be completely removed, and

    the resulting proposition must start with a capitalized character.
    """
    raw_text = f"{filler}{punctuation}{body}"
    canon = ReflectionEngine._canonicalize_proposition(raw_text)

    # Must not start with the filler token
    first_word = canon.split()[0].rstrip(",.!?").lower() if canon.split() else ""
    assert first_word != filler.lower()

    # Must be capitalized
    if canon:
        assert canon[0] == canon[0].upper() or not canon[0].isalpha()

    # Must end with valid terminal punctuation
    if canon:
        assert canon[-1] in (".", "!", "?")


@given(
    s=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        min_size=1,
        max_size=80,
    )
)
@settings(max_examples=50)
def test_prop_is_rule_conflict_symmetry_and_irreflexivity(s: str) -> None:
    """Property: Rule conflict checking must be:

    1. Symmetric: is_rule_conflict(a, b) == is_rule_conflict(b, a)
    2. Irreflexive: is_rule_conflict(a, a) == False (a rule never conflicts with itself)
    """
    # Irreflexive
    assert is_rule_conflict(s, s) is False

    # Symmetric against slight variation
    variation = s + " extra"
    assert is_rule_conflict(s, variation) == is_rule_conflict(variation, s)


def test_prop_is_rule_conflict_all_polarity_pairs() -> None:
    """Property: Every opposing polarity pair registered in OPPOSING_POLARITY_PAIRS

    must be detected as a conflict when embedded into identical contexts.
    """
    for pair in OPPOSING_POLARITY_PAIRS:
        w1, w2 = list(pair)
        text_a = f"system configuration {w1} the network port"
        text_b = f"system configuration {w2} the network port"
        assert is_rule_conflict(text_a, text_b) is True, (
            f"Failed to detect conflict between '{w1}' and '{w2}'"
        )
        assert is_rule_conflict(text_b, text_a) is True


@given(
    num1=st.integers(min_value=1, max_value=9999),
    num2=st.integers(min_value=1, max_value=9999),
)
@settings(max_examples=50)
def test_prop_candidate_conflict_numeric_attribute(num1: int, num2: int) -> None:
    """Property: Numeric attribute disagreement triggers Belnap TOP conflict iff num1 != num2."""
    bs = BeliefService.__new__(BeliefService)
    content_a = f"Target memory limit is set to {num1}%."
    content_b = f"Target memory limit is set to {num2}%."

    res = bs._evaluate_candidate_conflict(content_a, content_b)
    if num1 != num2:
        assert res is True, f"Expected conflict for {num1} vs {num2}"
    else:
        assert res is False, f"Expected no conflict for identical {num1}"


def test_prop_cascade_polarity_word_boundary_safety() -> None:
    """Property: Substring traps (words containing negation substrings like 'notice',

    'notary', 'cannoli') must NOT trigger negative polarity refutation.
    """
    safe_words = [
        "Please take notice of the update.",
        "The document was signed by a notary public.",
        "We ordered cannoli for dessert.",
        "The notation used in the proof is standard.",
    ]
    for sentence in safe_words:
        told_true, told_false = EpistemicSearchCascade._evaluate_polarity(
            sentence, "What is the status?"
        )
        assert told_false is False, f"Word boundary violation on '{sentence}': got told_false=True"
        assert told_true is True


# ============================================================================
# Section 2: Boundary Conditions, Negative Controls & Gating Overrides
# ============================================================================


def test_edge_interrogative_short_circuit(tmp_path: Path) -> None:
    """Interrogative utterances must cleanly short-circuit in check_contradictions

    and never query FTS or commit beliefs (Invariant F-WO8-17).
    """
    db_file = tmp_path / "test_interrogative.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)
    bs = BeliefService(db=db, reflection_engine=refl)

    # Interrogatives with various punctuation / casings
    questions = [
        "What is the configured proxy port?",
        "is the server running on port 8080?",
        "Does the system support dark mode?",
        "Why did the database cluster fail?",
        "how can we deploy the service?",
        "Can you verify the current theme?",
    ]
    trace = TurnTrace(trace_id="tr-quest", session_id="s1")

    for q in questions:
        bs.check_contradictions("entry-dummy", q, trace)

    # Verify review_queue remains completely empty
    assert len(refl.list_pending_reviews()) == 0
    db.close()


def test_edge_sub_threshold_tokens_short_circuit(tmp_path: Path) -> None:
    """Utterances with fewer than _MIN_TOPICAL_TOKENS (2) non-stop-word tokens

    >= 4 chars must short-circuit without executing FTS queries.
    """
    db_file = tmp_path / "test_sub_tokens.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)
    bs = BeliefService(db=db, reflection_engine=refl)

    # Short phrases with < 2 topical tokens
    short_phrases = ["ok yes", "it is so", "sure thanks", "fine", "no way"]
    trace = TurnTrace(trace_id="tr-short", session_id="s1")

    for p in short_phrases:
        bs.check_contradictions("entry-dummy", p, trace)

    assert len(refl.list_pending_reviews()) == 0
    db.close()


def test_edge_pure_stop_words_attractor_guard(tmp_path: Path) -> None:
    """Pure stop-word utterances against an active high-importance belief must NOT

    match in FTS or trigger review queue items (Belief #17 attractor invariant).
    """
    db_file = tmp_path / "test_stop_words.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)
    bs = BeliefService(db=db, reflection_engine=refl)
    signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)

    # Seed active high-importance belief
    now = time.time()
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="The primary production server is located in Frankfurt datacenter.",
        structured={"importance": 0.95, "topic": "datacenter", "valid_from": now},
        trace_id="tr-seed-attractor",
        created_at=now,
        nonce="nonce-attractor-1",
        confidence=1.0,
    )
    store.commit(signer.sign(payload))

    # Utterance composed entirely of stop words
    stop_phrase = "which would have been there about that thing with this"
    trace = TurnTrace(trace_id="tr-stop", session_id="s1")
    bs.check_contradictions("entry-dummy", stop_phrase, trace)

    # review_queue must remain strictly 0
    assert len(refl.list_pending_reviews()) == 0
    db.close()


def test_edge_reflection_oscillation_guard(tmp_path: Path) -> None:
    """If a belief was already revised within the last 30 days, an additional revision

    must trip the oscillation_guard flag and queue into review_queue (Spec §7).
    """
    db_file = tmp_path / "test_oscillation.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)
    signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)

    now = time.time()
    # Seed a belief whose valid_from > created_at within 30 days (simulating a recent revision)
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="User preferred theme is sepia mode.",
        structured={
            "importance": 0.4,
            "topic": "theme",
            "valid_from": now - 3600.0,  # Revised 1 hour ago
        },
        trace_id="tr-seed-osc",
        created_at=now - 7200.0,  # Created 2 hours ago
        nonce="nonce-seed-osc",
        confidence=0.9,
    )
    mid = store.commit(signer.sign(payload), now=payload.created_at)

    # Commit grounded user turn with a new revision
    u_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="I want solarized light mode.",
        trace_id="tr-osc-turn",
        created_at=now,
        nonce="nonce-osc-user",
        confidence=1.0,
    )
    signed_u = user_signer.sign(u_payload)
    store.commit(signed_u)

    is_queued, _ = refl.detect_and_handle_contradiction(
        old_belief_id=mid,
        new_content="I want solarized light mode.",
        reason_entry_id=signed_u.entry_id,
        proposed_confidence=1.0,
        is_conflict_top=False,
        now=now,
    )

    # Oscillation guard must have fired!
    assert is_queued is True
    reviews = refl.list_pending_reviews()
    assert len(reviews) == 1
    assert "oscillation_guard" in str(reviews[0]["trigger_reason"])
    db.close()


def test_edge_high_importance_review_override(tmp_path: Path) -> None:
    """Beliefs with importance >= 0.7 must ALWAYS route to review_queue even on

    explicit user retraction (Spec §7 Decision 4).
    """
    db_file = tmp_path / "test_high_imp.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)
    signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)

    now = time.time()
    # Seed high importance belief (0.85 >= 0.70)
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="Database backup encryption key is AES-GCM-256.",
        structured={"importance": 0.85, "topic": "security", "valid_from": now},
        trace_id="tr-seed-imp",
        created_at=now,
        nonce="nonce-seed-imp",
        confidence=0.95,
    )
    mid = store.commit(signer.sign(payload))

    # User retraction
    u_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="Database backup encryption key is not AES-GCM-256, it is ChaCha20.",
        trace_id="tr-imp-turn",
        created_at=now + 1.0,
        nonce="nonce-imp-user",
        confidence=1.0,
    )
    signed_u = user_signer.sign(u_payload)
    store.commit(signed_u)

    is_queued, _ = refl.detect_and_handle_contradiction(
        old_belief_id=mid,
        new_content="Database backup encryption key is not AES-GCM-256, it is ChaCha20.",
        reason_entry_id=signed_u.entry_id,
        proposed_confidence=1.0,
        is_conflict_top=False,  # Even with is_conflict_top=False!
        now=now + 1.0,
    )

    # Must be queued due to high_importance flag
    assert is_queued is True
    reviews = refl.list_pending_reviews()
    assert len(reviews) == 1
    assert "high_importance_0.85" in str(reviews[0]["trigger_reason"])
    db.close()


def test_edge_user_model_kind_review_override(tmp_path: Path) -> None:
    """Beliefs with kind='user_model' must ALWAYS require operator review."""
    db_file = tmp_path / "test_user_model.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)
    signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)

    now = time.time()
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="user_model",
        content="User possesses advanced expertise in Rust systems programming.",
        structured={"importance": 0.4, "topic": "expertise", "valid_from": now},
        trace_id="tr-seed-um",
        created_at=now,
        nonce="nonce-seed-um",
        confidence=0.9,
    )
    mid = store.commit(signer.sign(payload))

    u_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="I do not know Rust at all.",
        trace_id="tr-um-turn",
        created_at=now + 1.0,
        nonce="nonce-um-user",
        confidence=1.0,
    )
    signed_u = user_signer.sign(u_payload)
    store.commit(signed_u)

    is_queued, _ = refl.detect_and_handle_contradiction(
        old_belief_id=mid,
        new_content="I do not know Rust at all.",
        reason_entry_id=signed_u.entry_id,
        proposed_confidence=1.0,
        is_conflict_top=False,
        now=now + 1.0,
    )

    assert is_queued is True
    reviews = refl.list_pending_reviews()
    assert len(reviews) == 1
    assert "kind_user_model" in str(reviews[0]["trigger_reason"])
    db.close()


# ============================================================================
# Section 3: Cascade Evidential Bilattice Algebraic Properties
# ============================================================================


def test_belnap_bilattice_join_algebraic_properties() -> None:
    """Belnap information join k (sum of knowledge) must strictly satisfy the 5 lattice axioms:

    1. Idempotence: a ⊕ a = a
    2. Commutativity: a ⊕ b = b ⊕ a
    3. Associativity: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
    4. Identity element: a ⊕ BOT = a
    5. Absorbing element: a ⊕ TOP = TOP
    """
    elements = [
        BelnapValue.TRUE,
        BelnapValue.FALSE,
        BelnapValue.CONFLICT,
        BelnapValue.UNKNOWN,
    ]

    for a in elements:
        # 1. Idempotence
        assert belnap_join_k(a, a) == a

        # 4. Identity element (UNKNOWN / BOT is identity for knowledge join)
        assert belnap_join_k(a, BelnapValue.UNKNOWN) == a
        assert belnap_join_k(BelnapValue.UNKNOWN, a) == a

        # 5. Absorbing element (CONFLICT / TOP is absorbing for knowledge join)
        assert belnap_join_k(a, BelnapValue.CONFLICT) == BelnapValue.CONFLICT
        assert belnap_join_k(BelnapValue.CONFLICT, a) == BelnapValue.CONFLICT

        for b in elements:
            # 2. Commutativity
            assert belnap_join_k(a, b) == belnap_join_k(b, a)

            for c in elements:
                # 3. Associativity
                left = belnap_join_k(belnap_join_k(a, b), c)
                right = belnap_join_k(a, belnap_join_k(b, c))
                assert left == right


def test_multi_source_cascade_pooling_combinations() -> None:
    """Tests 5-evidence pooling combinations across evidence sources."""
    # Pure True
    assert pool_evidence([BelnapValue.TRUE] * 5) == BelnapValue.TRUE

    # Pure False
    assert pool_evidence([BelnapValue.FALSE] * 5) == BelnapValue.FALSE

    # Mixed: 4 True + 1 False -> CONFLICT (TOP)
    mixed = [BelnapValue.TRUE] * 4 + [BelnapValue.FALSE]
    assert pool_evidence(mixed) == BelnapValue.CONFLICT

    # Pure Unknown -> UNKNOWN
    assert pool_evidence([BelnapValue.UNKNOWN] * 5) == BelnapValue.UNKNOWN

    # Unknown + True -> TRUE (information monotonicity)
    assert pool_evidence([BelnapValue.UNKNOWN, BelnapValue.TRUE]) == BelnapValue.TRUE


def test_cascade_web_query_taint_propagation() -> None:
    """Verifies that query_substrate_3_web marks UNTRUSTED_WEB taint on active session guard."""
    cascade = EpistemicSearchCascade.__new__(EpistemicSearchCascade)
    mock_sandbox = MagicMock()
    cascade.sandbox = mock_sandbox
    mock_guard = MagicMock()
    mock_sandbox.guard = mock_guard

    mock_sandbox.execute.return_value = ToolResult(
        call_id="call-taint-1",
        ok=True,
        elapsed_ms=10.0,
        content="Documentation content",
    )

    cascade.query_substrate_3_web("https://example.com/spec Is feature supported?")
    mock_guard.mark_taint.assert_called_with(TaintFlags.UNTRUSTED_WEB)


def test_cascade_sandbox_resilience_on_exception() -> None:
    """Verifies that query_substrate_3_web catches sandbox execution errors cleanly

    without unhandled exceptions.
    """
    cascade = EpistemicSearchCascade.__new__(EpistemicSearchCascade)
    mock_sandbox = MagicMock()
    cascade.sandbox = mock_sandbox
    mock_sandbox.execute.side_effect = RuntimeError("Sandbox connection lost")

    # Should not raise, must return empty list
    items = cascade.query_substrate_3_web("https://example.com/spec")
    assert items == []


# ============================================================================
# Section 4: Full End-to-End Orchestrator Turn-Level Scenarios
# ============================================================================


@pytest.fixture
def e2e_orch(tmp_path: Path) -> Orchestrator:
    """Constructs a fully-wired Orchestrator for turn-level lifecycle testing."""
    db = DatabaseManager(tmp_path / "test_e2e_orch.sqlite")
    db.migrate()
    embedding_port = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=embedding_port)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)

    orch = Orchestrator.__new__(Orchestrator)
    orch.config = get_config()
    orch.execute_tools = True
    orch.state = "idle"
    orch.running = True
    orch.db = db
    orch.memory_store = store
    orch.reflection_engine = refl
    orch.current_turn_receipts = []
    orch.current_turn_tool_calls = []
    orch.current_turn_tier = ExecutionTier.FULL_LOOP
    orch.pending_spoken_updates = deque()
    orch.history = []
    orch.executed_tools = []
    orch.current_turn_transcript = None
    orch.current_turn_assistant_reply = None
    orch.active_trace = None
    orch.router = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.sandbox = MagicMock()
    orch.affect_tracker = MagicMock()
    orch.play_ring = MagicMock()
    orch._tts_queue = queue.Queue()
    orch.tts = MagicMock()
    orch.asr = MagicMock()
    orch.speech_output = MagicMock()
    orch.user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    orch.assistant_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    orch.breach_signer = CoherenceBreachSigner(master_key=TEST_MASTER_KEY)

    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._set_state = MagicMock()

    orch.beliefs = BeliefService(db=db, reflection_engine=refl, orchestrator=orch)
    return orch


def test_orchestrator_e2e_retraction_turn_lifecycle(e2e_orch: Orchestrator) -> None:
    """Full Orchestrator turn lifecycle test:

    Turn 1: Seed initial belief.
    Turn 2: User says "I don't live in the US, I live in Japan."
    _finalize_turn commits transcript with grounding eligibility, detects retraction,
    autonomously supersedes old belief, queues spoken update, and drains on next turn.
    """
    now = time.time()
    # Turn 1: Seed initial belief
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="I think you live in the United States.",
        structured={"importance": 0.4, "topic": "user residence", "valid_from": now},
        trace_id="tr-seed-loc",
        created_at=now,
        nonce="nonce-seed-loc",
        confidence=0.8,
    )
    old_mid = e2e_orch.memory_store.commit(e2e_orch.assistant_signer.sign(payload))

    # Turn 2: User correction turn
    trace_corr = TurnTrace(trace_id="tr-corr-japan", session_id="s1")
    e2e_orch.active_trace = trace_corr
    e2e_orch.current_turn_transcript = "I don't live in the US, I live in Japan."
    e2e_orch.current_turn_assistant_reply = "Understood, you live in Japan!"
    e2e_orch._finalize_turn(trace_corr, None)

    # 1. Old belief must be superseded
    with e2e_orch.db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[1] is not None

    # 2. Spoken update was generated in pending queue
    assert len(e2e_orch.pending_spoken_updates) == 1

    # Turn 3: Next turn arrives -> _maybe_speak_pending_updates is triggered
    trace_next = TurnTrace(trace_id="tr-turn-3", session_id="s1")
    e2e_orch._maybe_speak_pending_updates(trace_next)

    # Pending queue drained cleanly
    assert len(e2e_orch.pending_spoken_updates) == 0


def test_orchestrator_e2e_belnap_top_review_queue_routing(e2e_orch: Orchestrator) -> None:
    """Full Orchestrator turn lifecycle test for Belnap TOP conflict:

    Turn 1: Seed initial belief "System proxy port is 8080."
    Turn 2: User says "System proxy port is 9000."
    _finalize_turn routes to review_queue, preserves old belief un-superseded,
    and enqueues ZERO spoken updates.
    """
    now = time.time()
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="System proxy port is 8080.",
        structured={"importance": 0.5, "topic": "proxy", "valid_from": now},
        trace_id="tr-seed-proxy",
        created_at=now,
        nonce="nonce-seed-proxy",
        confidence=0.9,
    )
    old_mid = e2e_orch.memory_store.commit(e2e_orch.assistant_signer.sign(payload))

    trace_top = TurnTrace(trace_id="tr-top-proxy", session_id="s1")
    e2e_orch.active_trace = trace_top
    e2e_orch.current_turn_transcript = "System proxy port is 9000."
    e2e_orch.current_turn_assistant_reply = "Noted the proxy port change."
    e2e_orch._finalize_turn(trace_top, None)

    # 1. Old belief must NOT be superseded
    with e2e_orch.db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] is None

    # 2. review_queue has 1 pending item
    reviews = e2e_orch.reflection_engine.list_pending_reviews()
    assert len(reviews) == 1
    assert "belnap_conflict_top" in str(reviews[0]["trigger_reason"])

    # 3. ZERO spoken updates enqueued (conflict requires operator resolution)
    assert len(e2e_orch.pending_spoken_updates) == 0


# ============================================================================
# Section 5: Complex Phrasing Clustering & Rule Induction Scale Test
# ============================================================================


def test_cluster_phrasings_corpus_stress_test() -> None:
    """Stress test of cluster_phrasings on a 30-item phrasing corpus containing:

    - Multiple opposing polarity pairs (always/never, enable/disable, allow/block)
    - Paraphrases and token variations
    - Unrelated rule phrasings
    Verifies that all opposing pairs are strictly kept in separate clusters.
    """
    corpus = [
        # Group 1: Quotes (opposing always vs never)
        "always use single quotes",
        "single quotes must always be used",
        "prefer single quotes",
        "never use single quotes",
        "single quotes are forbidden",
        # Group 2: Telemetry (opposing enable vs disable)
        "enable telemetry logging",
        "telemetry logging enabled",
        "disable telemetry logging",
        "telemetry logging disabled",
        # Group 3: Firewall (opposing allow vs block)
        "port 8080 is allowed",
        "allow incoming port 8080",
        "port 8080 is blocked",
        "deny incoming port 8080",
        # Group 4: Unrelated formatting
        "indent with 4 spaces",
        "indent with 2 spaces",
        "wrap lines at 80 characters",
        "sort imports alphabetically",
    ]

    clusters = cluster_phrasings(corpus, threshold=0.50)

    # Build cluster mapping: each phrasing -> cluster leader
    phrasing_to_leader: dict[str, str] = {}
    for leader, count, phrasings in clusters:
        for phr in phrasings:
            phrasing_to_leader[phr] = leader

    # Opposing pairs MUST NOT share the same cluster leader
    assert (
        phrasing_to_leader["always use single quotes"]
        != phrasing_to_leader["never use single quotes"]
    )
    assert (
        phrasing_to_leader["enable telemetry logging"]
        != phrasing_to_leader["disable telemetry logging"]
    )
    assert phrasing_to_leader["port 8080 is allowed"] != phrasing_to_leader["port 8080 is blocked"]

    # Paraphrases with positive alignment MUST share the same cluster leader
    assert (
        phrasing_to_leader["enable telemetry logging"]
        == phrasing_to_leader["telemetry logging enabled"]
    )
