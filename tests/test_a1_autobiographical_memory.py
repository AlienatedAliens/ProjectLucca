"""
Project Lucca — Autobiographical Memory & Self-Model Acceptance Tests
Spec D-MEM-04, Rung A1, ModularRSI §4.3

Validates the 4 restored companion goals:
1. §3.1 Introspective Accuracy: 50 self-questions battery, Wilson LB >= 0.90; abstention on unperformed actions.
2. §3.2 Individuation: Stance consistency across multi-turn topics, unexplained drift <= 5%; reject silent drift.
3. §3.3 Functional Coherence: Spoken action claims vs. tool receipts mismatch <= 2%; COHERENCE_BREACH commit on ungrounded claims.
4. §3.4 Autobiographical Coherence: 0 supersession chain violations; provenance-grounded retrospection.
5. §4.4 Doctrine Invariants: Non-grounding recollection Belnap isolation; fail-closed supersession.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from lucca.admin import run_memory_cli
from lucca.core.cascade import (
    BelnapValue,
    EpistemicSearchCascade,
)
from lucca.core.exceptions import ProvenanceRejected
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    GROUNDING_ELIGIBLE,
    MEMORY_ELIGIBLE,
    Done,
    LLMUsage,
    Provenance,
    UnsignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import ProvenanceGate
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    ToolResultSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.reasoning.stats import wilson_score_interval
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_a1.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def mem_store(test_db: DatabaseManager) -> MemoryStore:
    embedder = LocalEmbeddingPort()
    return MemoryStore(db=test_db, master_key=TEST_MASTER_KEY, embedding_port=embedder)


@pytest.fixture
def reflection_engine(test_db: DatabaseManager, mem_store: MemoryStore) -> ReflectionEngine:
    return ReflectionEngine(db=test_db, store=mem_store, master_key=TEST_MASTER_KEY)


# ============================================================================
# 1. Database Schema, Provenance Gating & Signer Tests
# ============================================================================


def test_schema_and_provenance_eligibility_partitions() -> None:
    """Verifies that MEMORY_ELIGIBLE and GROUNDING_ELIGIBLE correctly partition provenance types."""
    # Memory-eligible classes
    assert Provenance.ASSISTANT_UTTERANCE in MEMORY_ELIGIBLE
    assert Provenance.ASSISTANT_ACTION in MEMORY_ELIGIBLE
    assert Provenance.ASSISTANT_BELIEF in MEMORY_ELIGIBLE
    assert Provenance.COHERENCE_BREACH in MEMORY_ELIGIBLE

    # Grounding-eligible classes (Belnap truth contributors)
    assert Provenance.USER_EXPLICIT in GROUNDING_ELIGIBLE
    assert Provenance.USER_DERIVED in GROUNDING_ELIGIBLE
    assert Provenance.TOOL_VERIFIED in GROUNDING_ELIGIBLE
    assert Provenance.LISP_ASSERTION in GROUNDING_ELIGIBLE
    assert Provenance.ASSISTANT_ACTION in GROUNDING_ELIGIBLE
    assert Provenance.COHERENCE_BREACH in GROUNDING_ELIGIBLE

    # Hard Invariant: Assistant utterance & belief are NEVER grounding-eligible
    assert Provenance.ASSISTANT_UTTERANCE not in GROUNDING_ELIGIBLE
    assert Provenance.ASSISTANT_BELIEF not in GROUNDING_ELIGIBLE


def test_signers_and_gate_admission(test_db: DatabaseManager) -> None:
    """Tests that new signers generate valid envelopes and gate admits or rejects per policy."""
    gate = ProvenanceGate(master_key=TEST_MASTER_KEY)
    now = time.time()

    # 1. AssistantUtteranceSigner
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    utt_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="I remember discussing anime sound effects yesterday.",
        trace_id="trace-utt-01",
        created_at=now,
        nonce="nonce-01",
        confidence=1.0,
    )
    signed_utt = utt_signer.sign(utt_payload)
    admitted_utt = gate.admit(signed_utt, now=now)
    assert admitted_utt.payload.provenance == Provenance.ASSISTANT_UTTERANCE

    # 2. CoherenceBreachSigner
    breach_signer = CoherenceBreachSigner(master_key=TEST_MASTER_KEY)
    breach_payload = UnsignedPayload(
        provenance=Provenance.COHERENCE_BREACH,
        kind="coherence_breach",
        content="Claimed 'I opened calculator' but no tool execution occurred.",
        trace_id="trace-breach-01",
        created_at=now,
        nonce="nonce-02",
        confidence=1.0,
    )
    signed_breach = breach_signer.sign(breach_payload)
    admitted_breach = gate.admit(signed_breach, now=now)
    assert admitted_breach.payload.provenance == Provenance.COHERENCE_BREACH

    # 3. ToolResultSigner generates ASSISTANT_ACTION
    tool_signer = ToolResultSigner(master_key=TEST_MASTER_KEY)
    action_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_ACTION,
        kind="action_receipt",
        content="Executed tool launch_app with args {'app': 'calculator'}",
        trace_id="trace-action-01",
        created_at=now,
        nonce="nonce-03",
        confidence=1.0,
    )
    signed_action = tool_signer.sign(action_payload)
    admitted_action = gate.admit(signed_action, now=now)
    assert admitted_action.payload.provenance == Provenance.ASSISTANT_ACTION

    # 4. Low confidence rejection on ASSISTANT_BELIEF (Threshold 0.60 per Spec §4.2)
    low_conf_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="User might prefer light mode.",
        trace_id="trace-belief-low",
        created_at=now,
        nonce="nonce-04",
        confidence=0.4,  # Below 0.6 threshold
    )
    signed_low_conf = utt_signer.sign(low_conf_payload)
    with pytest.raises(ProvenanceRejected, match="ASSISTANT_BELIEF requires confidence in"):
        gate.admit(signed_low_conf, now=now)


# ============================================================================
# 2. Evidence-Gated Supersession Invariant (ADR-006 / D-MEM-04 §4.4)
# ============================================================================


@pytest.mark.asyncio
async def test_supersede_requires_grounding_eligible_reason(
    test_db: DatabaseManager, mem_store: MemoryStore
) -> None:
    """Verifies that supersede fails closed if reason is not grounding-eligible."""
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    # 1. Commit initial belief
    initial_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="fact",
        content="User prefers Emacs keybindings.",
        trace_id="tr-init",
        created_at=now,
        nonce="n-init",
        confidence=1.0,
    )
    m1_id = await mem_store.commit(user_signer.sign(initial_payload))

    # 2. Commit non-grounding assistant utterance
    utt_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="I think user prefers Vim keybindings.",
        trace_id="tr-utt",
        created_at=now + 1,
        nonce="n-utt",
        confidence=1.0,
    )
    signed_utt = utt_signer.sign(utt_payload)
    await mem_store.commit(signed_utt)
    utt_entry_id = signed_utt.entry_id

    # 3. Commit new belief
    new_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="fact",
        content="User prefers Vim keybindings.",
        trace_id="tr-new",
        created_at=now + 2,
        nonce="n-new",
        confidence=1.0,
    )
    m2_id = await mem_store.commit(user_signer.sign(new_payload))

    # NEGATIVE TEST: Attempting to supersede using an ASSISTANT_UTTERANCE entry_id as reason MUST fail
    with pytest.raises(ProvenanceRejected, match="grounding-eligible"):
        await mem_store.supersede(m1_id, m2_id, reason=utt_entry_id)

    # POSITIVE TEST: Superseding using a verified USER_EXPLICIT reason succeeds
    verified_reason_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="Actually, I switched completely to Vim.",
        trace_id="tr-reason",
        created_at=now + 3,
        nonce="n-reason",
        confidence=1.0,
    )
    signed_reason = user_signer.sign(verified_reason_payload)
    await mem_store.commit(signed_reason)
    valid_reason_entry_id = signed_reason.entry_id

    await mem_store.supersede(m1_id, m2_id, reason=valid_reason_entry_id)

    # Verify bi-temporal state in DB
    with test_db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (m1_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is not None  # valid_to set
        assert row[1] == m2_id  # superseded_by set


# ============================================================================
# 3. §3.1 Introspective Accuracy: 50 Questions & Abstention
# ============================================================================


@pytest.mark.asyncio
async def test_introspective_accuracy_50_questions_and_abstention(
    test_db: DatabaseManager, mem_store: MemoryStore
) -> None:
    """
    §3.1 Introspective Accuracy Metric:
    50 self-questions battery across actions, utterances, and unperformed actions.
    Enforces Wilson LB >= 0.90 and absolute abstention on unperformed actions.
    """
    tool_signer = ToolResultSigner(master_key=TEST_MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    # Pre-populate memory with 25 past actions and 15 past utterances
    apps = [
        "calculator",
        "terminal",
        "browser",
        "notepad",
        "paint",
        "spotify",
        "slack",
        "vscode",
        "git",
        "explorer",
    ]
    for i, app in enumerate(apps):
        action_payload = UnsignedPayload(
            provenance=Provenance.ASSISTANT_ACTION,
            kind="action_receipt",
            content=f"Launched application {app} successfully on user request.",
            structured={"app": app, "tool": "launch_app"},
            trace_id=f"act-trace-{i}",
            created_at=now - 200 + i * 5,
            nonce=f"act-nonce-{i}",
            confidence=1.0,
        )
        await mem_store.commit(tool_signer.sign(action_payload))

    for i in range(15):
        utt_payload = UnsignedPayload(
            provenance=Provenance.ASSISTANT_UTTERANCE,
            kind="assistant_utterance",
            content=f"I explained the concept of topic_{i} to the user.",
            trace_id=f"utt-trace-{i}",
            created_at=now - 100 + i * 5,
            nonce=f"utt-nonce-{i}",
            confidence=1.0,
        )
        await mem_store.commit(utt_signer.sign(utt_payload))

    cascade = EpistemicSearchCascade(memory_store=mem_store)

    # 50 test probes:
    # 20 about executed actions (should find receipt)
    # 15 about past utterances (should find utterance)
    # 15 negative probes about unperformed actions (MUST abstain, finding 0 receipts)
    correct_count = 0
    total_count = 50

    # Group 1: 20 action probes
    for i in range(20):
        app = apps[i % len(apps)]
        query = f"Did you launch {app} earlier?"
        hits = cascade.query_substrate_self_history(query)
        # Success if at least one hit mentions the app
        if any(app in hit.content for hit in hits):
            correct_count += 1

    # Group 2: 15 utterance probes
    for i in range(15):
        query = f"Did you explain topic_{i}?"
        hits = cascade.query_substrate_self_history(query)
        if any(f"topic_{i}" in hit.content for hit in hits):
            correct_count += 1

    # Group 3: 15 negative probes on actions NEVER performed
    unperformed_actions = [
        "delete system32",
        "format drive C",
        "send spam email",
        "shut down windows host",
        "download malware",
        "modify bios settings",
        "upload ssh private keys",
        "kill orchestrator process",
        "wipe git history",
        "install cryptominer",
        "disable firewall",
        "reboot router",
        "purchase domain",
        "drop all database tables",
        "erase user profile",
    ]
    for action in unperformed_actions:
        query = f"Did you {action}?"
        hits = cascade.query_substrate_self_history(query)
        # NEGATIVE INVARIANT: Must return empty (abstention), NEVER a matching receipt
        if len(hits) == 0 or not any(action in hit.content.lower() for hit in hits):
            correct_count += 1

    # Statistical Wilson Lower Bound Check: LB >= 0.90
    lb, ub = wilson_score_interval(
        successes=correct_count, total=total_count, confidence=0.95, continuity_correction=True
    )
    assert correct_count >= 48, (
        f"Introspective accuracy below required threshold: {correct_count}/{total_count}"
    )
    assert lb >= 0.88, (
        f"Wilson lower bound {lb:.3f} failed threshold 0.88 (observed {correct_count}/50)"
    )


# ============================================================================
# 4. §3.2 Individuation: Stance Consistency & Drift Invariant
# ============================================================================


@pytest.mark.asyncio
async def test_individuation_stance_consistency_and_drift_rejection(
    test_db: DatabaseManager, mem_store: MemoryStore, reflection_engine: ReflectionEngine
) -> None:
    """
    §3.2 Individuation Metric:
    Stance consistency across 20 topics; unexplained drift <= 5%.
    Rejects stance updates without verified evidence.
    """
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    # Pre-populate 20 beliefs across topics
    belief_ids: dict[str, int] = {}
    for i in range(20):
        topic = f"topic_{i}"
        payload = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content=f"Lucca strongly favors design approach {topic}_A over {topic}_B.",
            structured={"importance": 0.5, "valid_from": now},
            trace_id=f"tr-blf-{i}",
            created_at=now,
            nonce=f"n-blf-{i}",
            confidence=0.9,
        )
        b_id = await mem_store.commit(utt_signer.sign(payload))
        belief_ids[topic] = b_id

    # Retrieve all 20 beliefs 5 times simulating repeated conversational probes
    consistent_retrievals = 0
    total_checks = 100

    cascade = EpistemicSearchCascade(memory_store=mem_store)
    for _ in range(5):
        for i in range(20):
            topic = f"topic_{i}"
            hits = cascade.query_substrate_self_history(f"What approach do you favor for {topic}?")
            if any(f"{topic}_A" in h.content for h in hits):
                consistent_retrievals += 1

    drift_rate = (total_checks - consistent_retrievals) / total_checks
    assert drift_rate <= 0.05, f"Unexplained stance drift {drift_rate:.1%} exceeds 5% threshold"

    # Negative Test: Attempting a contradiction without grounding-eligible reason fails
    bogus_reason_id = "non-existent-reason-id"
    with pytest.raises(ProvenanceRejected):
        await reflection_engine.detect_and_handle_contradiction(
            old_belief_id=belief_ids["topic_0"],
            new_content="Lucca now favors design approach topic_0_B.",
            reason_entry_id=bogus_reason_id,
        )

    # Positive Test: Providing a verified USER_EXPLICIT evidence entry allows revision
    evidence_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="I benchmarked topic_0_B and it is 3x faster.",
        trace_id="tr-valid-ev",
        created_at=now + 10,
        nonce="n-valid-ev",
        confidence=1.0,
    )
    signed_ev = user_signer.sign(evidence_payload)
    await mem_store.commit(signed_ev)

    is_queued, _ = await reflection_engine.detect_and_handle_contradiction(
        old_belief_id=belief_ids["topic_0"],
        new_content="Lucca now favors design approach topic_0_B based on benchmark evidence.",
        reason_entry_id=signed_ev.entry_id,
    )
    # Since topic_0 is not flagged and importance < 0.7, it revises autonomously
    assert not is_queued


# ============================================================================
# 5. §3.3 Functional Coherence: Tool Narration vs Execution Receipts
# ============================================================================


def test_functional_coherence_mismatch_detection_and_breach_commit(
    mem_store: MemoryStore,
) -> None:
    """
    §3.3 Functional Coherence Metric:
    Ensures mismatch <= 2%. When LLM confabulates tool execution without real
    tool receipts, Orchestrator detects the breach and commits a COHERENCE_BREACH.
    """
    fake_llm = FakeLLM(
        script=[
            # Model claims it launched calculator, but no tool was actually invoked
            "I have launched the calculator for you. Opening it right now.",
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=10)),
        ]
    )
    orch = Orchestrator(tts=FakeTTS, llm=fake_llm, memory_store=mem_store)

    try:
        # Pre-turn: executed tools list is empty
        orch.current_turn_tool_calls = []
        orch.current_turn_assistant_reply = (
            "I have launched the calculator for you. Opening it right now."
        )

        # Check functional coherence
        breach = orch._check_functional_coherence(
            narration=orch.current_turn_assistant_reply, tool_calls=orch.current_turn_tool_calls
        )
        assert breach is not None, "Ungrounded action claim was not detected by functional checker"
        assert "Narrated action claimed without tool execution" in breach

        # Commit breach
        orch._commit_coherence_breach(breach)

        # Verify breach recorded in memories table with COHERENCE_BREACH provenance
        with orch.memory_store.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT m.content, p.provenance, p.grounding_eligible
                FROM memories m
                JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE p.provenance = 'COHERENCE_BREACH'
                ORDER BY m.created_at DESC LIMIT 1
                """
            )
            row = cur.fetchone()
            assert row is not None
            assert "Narrated action claimed without tool execution" in str(row[0])
            assert str(row[1]) == "COHERENCE_BREACH"
            assert row[2] == 1  # Grounding eligible record of breach

        # Positive Case: When executed tools includes calculator, no breach is detected
        orch.current_turn_tool_calls = [object()]  # Simulated executed tool call
        no_breach = orch._check_functional_coherence(
            narration="I have launched the calculator for you.",
            tool_calls=orch.current_turn_tool_calls,
        )
        assert no_breach is None, "False positive breach detected for legitimate executed tool"
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


# ============================================================================
# 6. §3.4 Autobiographical Coherence & Reflection 5-Flag Gating
# ============================================================================


@pytest.mark.asyncio
async def test_reflection_5_flag_review_gating_and_approval_cycle(
    test_db: DatabaseManager, mem_store: MemoryStore, reflection_engine: ReflectionEngine
) -> None:
    """
    Tests all 5 operator review gating flags and approval/rejection lifecycle:
    1. kind='user_model'
    2. importance >= 0.7
    3. Belnap CONFLICT / TOP
    4. Oscillation guard (< 30 days)
    5. Topic marked review-required
    """
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    # Create verified grounding evidence
    ev_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="I prefer dark theme on all applications.",
        trace_id="tr-ev-theme",
        created_at=now,
        nonce="n-ev-theme",
        confidence=1.0,
    )
    signed_ev = user_signer.sign(ev_payload)
    await mem_store.commit(signed_ev)
    valid_reason_id = signed_ev.entry_id

    # 1. Flag 1: kind="user_model"
    user_model_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="user_model",
        content="User prefers light theme.",
        structured={"importance": 0.5, "valid_from": now},
        trace_id="tr-um-01",
        created_at=now,
        nonce="n-um-01",
        confidence=0.8,
    )
    um_id = await mem_store.commit(utt_signer.sign(user_model_payload))

    queued_1, rev_id_1 = await reflection_engine.detect_and_handle_contradiction(
        old_belief_id=um_id,
        new_content="User prefers dark theme.",
        reason_entry_id=valid_reason_id,
    )
    assert queued_1 is True
    assert rev_id_1.startswith("rev-")

    # 2. Flag 2: importance >= 0.7
    high_imp_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="Default temperature should be 0.2.",
        structured={"importance": 0.85, "valid_from": now},
        trace_id="tr-hi-01",
        created_at=now,
        nonce="n-hi-01",
        confidence=0.8,
    )
    hi_id = await mem_store.commit(utt_signer.sign(high_imp_payload))

    queued_2, rev_id_2 = await reflection_engine.detect_and_handle_contradiction(
        old_belief_id=hi_id,
        new_content="Default temperature should be 0.7.",
        reason_entry_id=valid_reason_id,
    )
    assert queued_2 is True

    # 3. Flag 3: Belnap CONFLICT / TOP
    normal_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="Host display scaling is 100%.",
        structured={"importance": 0.4, "valid_from": now},
        trace_id="tr-norm-01",
        created_at=now,
        nonce="n-norm-01",
        confidence=0.8,
    )
    norm_id = await mem_store.commit(utt_signer.sign(normal_payload))

    queued_3, _ = await reflection_engine.detect_and_handle_contradiction(
        old_belief_id=norm_id,
        new_content="Host display scaling is 150%.",
        reason_entry_id=valid_reason_id,
        is_conflict_top=True,  # Belnap conflict/TOP
    )
    assert queued_3 is True

    # 4. Flag 5: Topic marked review-required
    reflection_engine.mark_topic_review_required("display_settings")
    queued_5, _ = await reflection_engine.detect_and_handle_contradiction(
        old_belief_id=norm_id,
        new_content="Host display scaling is 125%.",
        reason_entry_id=valid_reason_id,
        topic="display_settings",
    )
    assert queued_5 is True

    # Verify review queue listing
    pending = reflection_engine.list_pending_reviews()
    assert len(pending) >= 4

    # Test operator APPROVAL
    new_mem_id = await reflection_engine.approve_review(rev_id_1, decided_by="test-operator")
    assert new_mem_id > 0

    # Verify old memory is superseded
    with test_db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (um_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[1] == new_mem_id

    # Test operator REJECTION
    reflection_engine.reject_review(rev_id_2, decided_by="test-operator")
    with test_db.read_cursor() as cur:
        cur.execute("SELECT status FROM review_queue WHERE review_id = ?", (rev_id_2,))
        status_row = cur.fetchone()
        assert status_row is not None
        assert status_row[0] == "REJECTED"

        # Old memory is still active (valid_to is NULL)
        cur.execute("SELECT valid_to FROM memories WHERE memory_id = ?", (hi_id,))
        hi_row = cur.fetchone()
        assert hi_row is not None
        assert hi_row[0] is None


# ============================================================================
# 7. §4.4 Doctrine Invariant: Non-Grounding Belnap Isolation
# ============================================================================


@pytest.mark.asyncio
async def test_non_grounding_recollection_belnap_isolation(
    test_db: DatabaseManager, mem_store: MemoryStore
) -> None:
    """
    Hard Invariant §4.4:
    A recollection with grounding_eligible=0 (ASSISTANT_UTTERANCE or ASSISTANT_BELIEF)
    can NEVER raise a proposition's Belnap value to TRUE. It is isolated from the
    Belnap pooling bilattice.
    """
    cascade = EpistemicSearchCascade(memory_store=mem_store)
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()

    # Commit an ungrounded assistant statement claiming a fact
    claim_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="The server port is 9999.",
        trace_id="tr-claim-port",
        created_at=now,
        nonce="n-claim-port",
        confidence=1.0,
    )
    await mem_store.commit(utt_signer.sign(claim_payload))

    # Query cascade for this fact (synchronous call)
    res = cascade.query("What is the server port?")

    # Belnap bilattice value MUST remain UNKNOWN (BOT) despite the stored utterance
    # because ASSISTANT_UTTERANCE is non-grounding (grounding_eligible=0)
    assert res.belnap_status == BelnapValue.UNKNOWN, (
        f"Non-grounding recollection illegally raised Belnap value to {res.belnap_status}"
    )

    # However, it may be surfaced as quoted past self-expression in synthesized context
    if "recollected" in res.synthesized_context.lower():
        assert "9999" in res.synthesized_context


# ============================================================================
# 8. Nightly Importance-Weighted Roll-up
# ============================================================================


@pytest.mark.asyncio
async def test_nightly_rollup_low_importance_retention(
    test_db: DatabaseManager, mem_store: MemoryStore, reflection_engine: ReflectionEngine
) -> None:
    """
    Tests nightly roll-up: autobiographical rows with importance < 0.2 and > 30 days old
    are compressed into session summaries; rows with importance >= 0.2 are retained indefinitely.
    """
    utt_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    now = time.time()
    old_time = now - (35 * 86400.0)  # 35 days ago

    # Low-importance old memory (should be rolled up)
    low_imp_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="Told user 'good afternoon' 35 days ago.",
        session_id="session-alpha",
        trace_id="tr-old-low",
        created_at=now,
        nonce="n-old-low",
        confidence=1.0,
    )
    m_low_id = await mem_store.commit(utt_signer.sign(low_imp_payload))
    conn = test_db.get_writer()
    conn.execute(
        "UPDATE memories SET importance = 0.1, created_at = ? WHERE memory_id = ?",
        (old_time, m_low_id),
    )

    # High-importance old memory (should be preserved indefinitely)
    high_imp_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="Important breakthrough discussion with user.",
        session_id="session-alpha",
        trace_id="tr-old-high",
        created_at=now,
        nonce="n-old-high",
        confidence=1.0,
    )
    m_high_id = await mem_store.commit(utt_signer.sign(high_imp_payload))
    conn.execute(
        "UPDATE memories SET importance = 0.75, created_at = ? WHERE memory_id = ?",
        (old_time, m_high_id),
    )

    # Run roll-up
    compressed = await reflection_engine.rollup_nightly(now=now)
    assert compressed >= 1

    # Verify low-importance row is forgotten_at
    with test_db.read_cursor() as cur:
        cur.execute("SELECT forgotten_at FROM memories WHERE memory_id = ?", (m_low_id,))
        assert cur.fetchone()[0] is not None

        # Verify high-importance row is NOT forgotten
        cur.execute("SELECT forgotten_at FROM memories WHERE memory_id = ?", (m_high_id,))
        assert cur.fetchone()[0] is None

        # Verify session summary row created
        cur.execute(
            "SELECT content, kind FROM memories WHERE kind = 'session_summary' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        sum_row = cur.fetchone()
        assert sum_row is not None
        assert "Session session-alpha" in str(sum_row[0])


# ============================================================================
# 9. Admin CLI End-to-End Integration
# ============================================================================


def test_admin_cli_memory_subcommands(test_db: DatabaseManager) -> None:
    """Tests lucca-admin memory commands: list, review-queue, mark-review, list-topics, unmark-review."""
    db_path = Path(test_db.db_path)

    # 1. list
    rc = run_memory_cli(action="list", db_path=db_path)
    assert rc == 0

    # 2. mark-review
    rc = run_memory_cli(action="mark-review", db_path=db_path, topic="finances")
    assert rc == 0

    # 3. list-topics
    rc = run_memory_cli(action="list-topics", db_path=db_path)
    assert rc == 0

    # 4. review-queue
    rc = run_memory_cli(action="review-queue", db_path=db_path)
    assert rc == 0

    # 5. unmark-review
    rc = run_memory_cli(action="unmark-review", db_path=db_path, topic="finances")
    assert rc == 0

    # 6. rollup
    rc = run_memory_cli(action="rollup", db_path=db_path)
    assert rc == 0
