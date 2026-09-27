"""
Project Lucca — Concert Layer Tests (WO-20 Phase 1 / D-REAS-09)

Functional acceptance tests for:
- Assertion primitive: (assert (s p o)) pure plan action construction
- Fact predicates: (fact-exists? (s p o)) and (fact-value (s p))
- Bounded re-evaluation loop: Rule B fires on Rule A's assertion in the same turn
- Envelope provenance: LISP_ASSERTION signed via SignerFactory and verifiable by ProvenanceGate.admit
- Bounded depth: 9-deep chain halts at depth 8 with logged chain_depth_exceeded, no crash
- Fixpoint fast-path: rule with no assertions causes 0 re-evaluations
"""

import json
import logging
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import ulid
from pydantic import ValidationError

from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.coherence import ToolReceipt
from lucca.core.config import get_config
from lucca.core.exceptions import ProvenanceRejected, SchemeRuntimeError, SchemeSyntaxError
from lucca.core.orchestrator import Orchestrator
from lucca.core.reasoning_context import (
    DEFAULT_CAPACITY,
    ProofTraceStep,
    ReasoningContext,
    ReasoningEntry,
)
from lucca.core.schemas import (
    AssertFact,
    Done,
    ExecutionTier,
    InferenceStep,
    LLMUsage,
    Plan,
    Provenance,
    RetrievalQuery,
    RuleState,
    Say,
    SignedPayload,
    TokenDelta,
    UnsignedPayload,
)
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import ProvenanceGate
from lucca.memory.retrieval import format_memory_context
from lucca.memory.signers import DerivedFactSigner
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import MAX_CHAIN_DEPTH, RuleLifecycleManager
from lucca.reasoning.scheme.eval import evaluate_expr, evaluate_rule
from lucca.reasoning.scheme.parser import parse_rule
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "test_concert_layer.sqlite")
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def memory_store(test_db: DatabaseManager) -> MemoryStore:
    return MemoryStore(db=test_db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())


@pytest.fixture
def signer_factory() -> SignerFactory:
    return SignerFactory(master_key=TEST_MASTER_KEY)


@pytest.fixture
def orch(test_db: DatabaseManager, memory_store: MemoryStore, signer_factory: SignerFactory) -> Orchestrator:
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.config = get_config()
    orchestrator.execute_tools = True
    orchestrator.state = "idle"
    orchestrator.running = True
    orchestrator.db = test_db
    orchestrator.memory_store = memory_store
    orchestrator.signer_factory = signer_factory
    orchestrator.rule_engine = RuleLifecycleManager(db=test_db)
    orchestrator.current_turn_receipts = []
    orchestrator.current_turn_tool_calls = []
    orchestrator.current_turn_tier = ExecutionTier.FULL_LOOP
    orchestrator.history = []
    orchestrator.executed_tools = []
    orchestrator.current_turn_transcript = None
    orchestrator.router = MagicMock()
    orchestrator._speak_text = MagicMock()
    return orchestrator


def _trace(trace_id: str = "tr-concert-1") -> TurnTrace:
    return TurnTrace(trace_id=trace_id, session_id="sess-concert", origin="text", mode="transcript")


def test_rule_b_fires_on_rule_a_assertion_in_same_turn(orch: Orchestrator) -> None:
    """WO-20 Phase 1 Functional Acceptance 1:

    Register rule A (:when trigger -> (assert (user likes tiramisu)))
    Register rule B (:when (fact-exists? (user likes tiramisu)) -> (say "noted"))
    Fire A; assert B fires on the rebuilt state in the same turn;
    Assert the store contains a LISP_ASSERTION envelope for the fact, verifiable by ProvenanceGate.admit.
    """
    rule_a_src = """
    (rule "rule-a-v1"
      :when (intent= "launch_app")
      :plan (list (assert (user likes tiramisu)))
      :priority 10)
    """
    rule_b_src = """
    (rule "rule-b-v1"
      :when (fact-exists? (user likes tiramisu))
      :plan (list (say "noted"))
      :priority 5)
    """
    managed_a = orch.rule_engine.register_rule(rule_a_src)
    managed_a.status = "ACTIVE"

    managed_b = orch.rule_engine.register_rule(rule_b_src)
    managed_b.status = "ACTIVE"

    initial_state = RuleState(
        intent="launch_app",
        transcript="start the test",
        transcript_lower="start the test",
        asserted_facts=frozenset(),
    )
    trace = _trace("tr-concert-ab")

    outcomes, final_state = orch.evaluate_rules_chain(initial_state, trace=trace)

    # Both rules must have fired
    fired_ids = [o.rule_id for o in outcomes if o.fired]
    assert "rule-a-v1" in fired_ids, "Rule A must fire on trigger"
    assert "rule-b-v1" in fired_ids, "Rule B must fire on Rule A's assertion in the same turn"

    # Final state must contain the asserted fact
    assert ("user", "likes", "tiramisu") in final_state.asserted_facts

    # Store must contain the LISP_ASSERTION envelope verifiable by ProvenanceGate.admit
    gate = ProvenanceGate(master_key=TEST_MASTER_KEY)
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT entry_id, signature, payload_json, nonce, created_at, trace_id, provenance
            FROM provenance_envelopes
            WHERE provenance = 'LISP_ASSERTION'
            """
        )
        rows = cur.fetchall()

    assert len(rows) == 1, "Exactly one LISP_ASSERTION envelope committed to store"
    entry_id, signature, payload_json_str, nonce, created_at, trace_id, prov = rows[0]
    assert prov == "LISP_ASSERTION"

    # Retrieve signed payload from payload_json and admit via ProvenanceGate
    payload = SignedPayload.model_validate_json(payload_json_str)
    assert payload.content == "user likes tiramisu"
    admitted = gate.admit(payload, now=created_at)
    assert admitted.payload.content == "user likes tiramisu"
    assert admitted.payload.provenance == Provenance.LISP_ASSERTION

    # Verify memory table insertion
    with orch.db.read_cursor() as cur:
        cur.execute("SELECT content FROM memories WHERE entry_id = ?", (entry_id,))
        mem_row = cur.fetchone()
        assert mem_row is not None
        assert mem_row[0] == "user likes tiramisu"


def test_chain_depth_limit_halts_at_depth_8(
    orch: Orchestrator, capsys: pytest.CaptureFixture[str]
) -> None:
    """WO-20 Phase 1 Functional Acceptance 2:

    A rule asserting inside a 9-deep chain halts at depth 8 with a logged
    `chain_depth_exceeded`, no crash.
    """
    import structlog.testing

    # Create 9 chained rules: rule_i asserts step_(i+1)
    # Depth 0: rule_0 fires -> asserts step_1 (depth becomes 1)
    # Depth 1: rule_1 fires -> asserts step_2 (depth becomes 2)
    # ...
    # Depth 7: rule_7 fires -> asserts step_8 (depth becomes 8)
    # At depth 8: max_depth reached -> halts with chain_depth_exceeded, rule_8 does not fire
    rule_0 = """
    (rule "chain-0-v1"
      :when (intent= "launch_app")
      :plan (list (assert (user step "s1")))
      :priority 100)
    """
    managed = orch.rule_engine.register_rule(rule_0)
    managed.status = "ACTIVE"

    for i in range(1, 9):
        prev_step = f"s{i}"
        next_step = f"s{i + 1}"
        rule_src = f"""
        (rule "chain-{i}-v1"
          :when (fact-exists? (user step "{prev_step}"))
          :plan (list (assert (user step "{next_step}")))
          :priority {100 - i})
        """
        m = orch.rule_engine.register_rule(rule_src)
        m.status = "ACTIVE"

    initial_state = RuleState(
        intent="launch_app",
        transcript="chain test",
        transcript_lower="chain test",
        asserted_facts=frozenset(),
    )
    trace = _trace("tr-depth-test")

    with structlog.testing.capture_logs() as captured:
        outcomes, final_state = orch.evaluate_rules_chain(initial_state, trace=trace, max_depth=8)

    # Must log chain_depth_exceeded
    out = capsys.readouterr()
    has_event = any(e.get("event") == "chain_depth_exceeded" for e in captured)
    has_stdout = "chain_depth_exceeded" in out.out or "chain_depth_exceeded" in out.err
    assert has_event or has_stdout, "chain_depth_exceeded must be logged"

    # Must not have crashed, exactly 8 rules fired (chain-0 through chain-7)
    fired_ids = [o.rule_id for o in outcomes if o.fired]
    assert len(fired_ids) == 8
    assert "chain-0-v1" in fired_ids
    assert "chain-7-v1" in fired_ids
    assert "chain-8-v1" not in fired_ids, "9th rule must not fire because depth 8 halted"

    # Step 8 asserted, but Step 9 was not reached
    assert ("user", "step", "s8") in final_state.asserted_facts
    assert ("user", "step", "s9") not in final_state.asserted_facts


def test_fixpoint_fast_path_zero_reevaluations(orch: Orchestrator) -> None:
    """WO-20 Phase 1 Functional Acceptance 3:

    A rule whose plan asserts nothing causes zero re-evaluations (fixpoint fast-path).
    """
    rule_src = """
    (rule "say-only-v1"
      :when (intent= "launch_app")
      :plan (list (say "just talk"))
      :priority 10)
    """
    managed = orch.rule_engine.register_rule(rule_src)
    managed.status = "ACTIVE"

    initial_state = RuleState(
        intent="launch_app",
        transcript="hello",
        transcript_lower="hello",
        asserted_facts=frozenset(),
    )

    outcomes, final_state = orch.evaluate_rules_chain(initial_state, trace=_trace("tr-fastpath"))

    # Exactly 1 outcome (1 evaluation pass, 0 re-evaluations)
    assert len(outcomes) == 1
    assert outcomes[0].rule_id == "say-only-v1"
    assert outcomes[0].fired is True
    # Zero facts asserted
    assert final_state.asserted_facts == frozenset()


def test_assert_primitive_is_pure() -> None:
    """Trap 1: The (assert ...) primitive must be pure (D-REAS-05).

    Calling evaluate_expr on (assert ...) returns AssertFact and touches no store.
    """
    action = evaluate_expr(parse_rule('(rule "r-v1" :when (intent= "x") :plan (list (assert (user likes coffee))))').plan_expr)
    assert isinstance(action, list)
    assert len(action) == 1
    assert isinstance(action[0], AssertFact)
    assert action[0].s == "user"
    assert action[0].p == "likes"
    assert action[0].o == "coffee"


def test_fact_predicates_truth_and_lookup() -> None:
    """Test fact-exists? and fact-value predicates over RuleState.asserted_facts."""
    state = RuleState(
        asserted_facts=frozenset({
            ("user", "nationality_is", "Australian"),
            ("user", "likes", "tiramisu"),
        })
    )

    # fact-exists? positive and negative
    assert evaluate_expr(["fact-exists?", ["user", "likes", "tiramisu"]], state) is True
    assert evaluate_expr(["fact-exists?", ["user", "likes", "pizza"]], state) is False
    assert evaluate_expr(["fact-exists?", ["user", "nationality_is"]], state) is True
    assert evaluate_expr(["fact-exists?", ["user", "origin_is"]], state) is False

    # fact-value lookup
    assert evaluate_expr(["fact-value", ["user", "likes"]], state) == "tiramisu"
    assert evaluate_expr(["fact-value", ["user", "nationality_is"]], state) == "Australian"
    assert evaluate_expr(["fact-value", ["user", "dislikes"]], state) is False


def test_invalid_predicate_in_assert_rejected() -> None:
    """Predicate validation via is_valid_predicate: invalid slugs fail statically."""
    with pytest.raises(SchemeSyntaxError, match="invalid predicate"):
        parse_rule('(rule "bad-pred-v1" :when (intent= "x") :plan (list (assert (user "BAD PRED!" val))))')

    with pytest.raises(ValueError, match="Invalid predicate"):
        AssertFact(s="user", p="INVALID_PRED!", o="val")


def test_rule_state_frozen_rebuild_discipline() -> None:
    """Trap 3: RuleState is frozen; asserted_facts must be rebuilt, never mutated."""
    state1 = RuleState(asserted_facts=frozenset({("a", "b", "c")}))
    with pytest.raises(Exception):
        state1.asserted_facts.add(("x", "y", "z"))  # type: ignore[attr-defined]

    state2 = state1.model_copy(update={"asserted_facts": state1.asserted_facts | {("x", "y", "z")}})
    assert ("x", "y", "z") in state2.asserted_facts
    assert ("x", "y", "z") not in state1.asserted_facts


# =============================================================================
# WO-20 Phase 2: Reasoning Context (Working Memory) Tests
# =============================================================================


def test_three_rule_chain_produces_three_intermediates_in_order(orch: Orchestrator) -> None:
    """WO-20 Phase 2 Functional Acceptance 1:

    A 3-rule chain produces exactly 3 intermediates in order, each with a
    distinct envelope_id and the correct step_kind.
    """
    rule_0 = """
    (rule "r0-chain-v1"
      :when (intent= "start_chain")
      :plan (list (assert (user step "s1")))
      :priority 30)
    """
    rule_1 = """
    (rule "r1-chain-v1"
      :when (fact-exists? (user step "s1"))
      :plan (list (assert (user step "s2")))
      :priority 20)
    """
    rule_2 = """
    (rule "r2-chain-v1"
      :when (fact-exists? (user step "s2"))
      :plan (list (assert (user step "s3")))
      :priority 10)
    """
    for src in (rule_0, rule_1, rule_2):
        m = orch.rule_engine.register_rule(src)
        m.status = "ACTIVE"

    initial_state = RuleState(
        intent="start_chain",
        transcript="start chain test",
        transcript_lower="start chain test",
        asserted_facts=frozenset(),
    )
    trace = _trace("tr-chain-3step")

    outcomes, final_state = orch.evaluate_rules_chain(initial_state, trace=trace)

    context = orch.current_reasoning_context
    assert context is not None, "ReasoningContext must be created during evaluation"
    assert len(context) == 3, "Exactly 3 intermediates produced"

    # Check intermediates in order
    step_triples = [
        ("user", "step", "s1"),
        ("user", "step", "s2"),
        ("user", "step", "s3"),
    ]
    seen_envelope_ids: set[str] = set()

    for idx, (expected_s, expected_p, expected_o) in enumerate(step_triples):
        entry = context[idx]
        assert entry.s == expected_s
        assert entry.p == expected_p
        assert entry.o == expected_o
        assert entry.step_kind == "lisp_rule"
        assert entry.envelope_id, "Each intermediate must have an envelope_id"
        assert entry.envelope_id not in seen_envelope_ids, "Envelope IDs must be distinct"
        seen_envelope_ids.add(entry.envelope_id)

        # Verify tuple unpacking (envelope_id, s, p, o, confidence, step_kind)
        env_id, s, p, o, conf, kind = entry
        assert env_id == entry.envelope_id
        assert (s, p, o) == (expected_s, expected_p, expected_o)
        assert kind == "lisp_rule"
        assert 0.0 <= conf <= 1.0


def test_proof_trace_returns_intermediates_with_resolvable_premises(orch: Orchestrator) -> None:
    """WO-20 Phase 2 Functional Acceptance 2:

    proof_trace() returns the intermediates in firing order with premises
    resolvable to earlier entries.
    """
    rule_0 = """
    (rule "prem-0-v1"
      :when (intent= "deduce")
      :plan (list (assert (user step "s1")))
      :priority 30)
    """
    rule_1 = """
    (rule "prem-1-v1"
      :when (fact-exists? (user step "s1"))
      :plan (list (assert (user step "s2")))
      :priority 20)
    """
    rule_2 = """
    (rule "prem-2-v1"
      :when (fact-exists? (user step "s2"))
      :plan (list (assert (user step "s3")))
      :priority 10)
    """
    for src in (rule_0, rule_1, rule_2):
        m = orch.rule_engine.register_rule(src)
        m.status = "ACTIVE"

    initial_state = RuleState(
        intent="deduce",
        transcript="deduce step",
        transcript_lower="deduce step",
        asserted_facts=frozenset(),
    )
    trace = _trace("tr-proof-trace")

    outcomes, final_state = orch.evaluate_rules_chain(initial_state, trace=trace)

    proof = orch.proof_trace()
    assert len(proof) == 3, "proof_trace must contain 3 steps"

    # Firing order verification
    assert proof[0].conclusion == "user step s1"
    assert proof[0].rule_id == "prem-0-v1"
    assert proof[0].premises == []

    assert proof[1].conclusion == "user step s2"
    assert proof[1].rule_id == "prem-1-v1"
    assert proof[1].premises == ["user step s1"]

    assert proof[2].conclusion == "user step s3"
    assert proof[2].rule_id == "prem-2-v1"
    assert proof[2].premises == ["user step s2"]

    # Verify premise resolution via premises_for
    context = orch.current_reasoning_context
    assert context is not None

    premises_for_s2 = context.premises_for("user step s2")
    assert len(premises_for_s2) == 1
    assert premises_for_s2[0].conclusion == "user step s1"
    assert premises_for_s2[0].envelope_id == proof[0].envelope_id

    premises_for_s3 = context.premises_for("user step s3")
    assert len(premises_for_s3) == 1
    assert premises_for_s3[0].conclusion == "user step s2"
    assert premises_for_s3[0].envelope_id == proof[1].envelope_id

    # Verify tuple unpacking for proof trace steps (step_kind, rule_id, premises, conclusion, envelope_id)
    kind, rid, prems, concl, eid = proof[1]
    assert kind == "lisp_rule"
    assert rid == "prem-1-v1"
    assert prems == ["user step s1"]
    assert concl == "user step s2"
    assert eid == proof[1].envelope_id


def test_second_turn_gets_fresh_context_no_leakage(orch: Orchestrator) -> None:
    """WO-20 Phase 2 Functional Acceptance 3:

    A second turn gets a fresh context (no leakage between turns).
    """
    rule_t1 = """
    (rule "turn-1-rule-v1"
      :when (intent= "turn_1")
      :plan (list (assert (user turn "turn1_done")))
      :priority 10)
    """
    rule_t2 = """
    (rule "turn-2-rule-v1"
      :when (intent= "turn_2")
      :plan (list (assert (user turn "turn2_done")))
      :priority 10)
    """
    for src in (rule_t1, rule_t2):
        m = orch.rule_engine.register_rule(src)
        m.status = "ACTIVE"

    # Turn 1
    state_turn1 = RuleState(
        intent="turn_1",
        transcript="run turn 1",
        transcript_lower="run turn 1",
        asserted_facts=frozenset(),
    )
    orch.evaluate_rules_chain(state_turn1, trace=_trace("tr-t1"))

    context_1 = orch.current_reasoning_context
    assert context_1 is not None
    assert len(context_1) == 1
    assert context_1[0].conclusion == "user turn turn1_done"

    # Turn 2: fresh turn
    state_turn2 = RuleState(
        intent="turn_2",
        transcript="run turn 2",
        transcript_lower="run turn 2",
        asserted_facts=frozenset(),
    )
    orch.evaluate_rules_chain(state_turn2, trace=_trace("tr-t2"))

    context_2 = orch.current_reasoning_context
    assert context_2 is not None
    assert context_2 is not context_1, "Turn 2 must receive a new ReasoningContext instance"
    assert len(context_2) == 1
    assert context_2[0].conclusion == "user turn turn2_done"
    # Ensure no leakage from Turn 1 in context 2
    assert all(e.conclusion != "user turn turn1_done" for e in context_2)


def test_reasoning_context_capacity_bound(capsys: pytest.CaptureFixture[str]) -> None:
    """ReasoningContext is bounded at MAX_CHAIN_DEPTH * 4 (32 entries)."""
    import structlog.testing

    ctx = ReasoningContext(capacity=4)
    for i in range(4):
        ctx.add_intermediate(
            envelope_id=f"env-{i}",
            s="user",
            p="step",
            o=f"s{i}",
        )
    assert len(ctx) == 4

    with structlog.testing.capture_logs() as captured:
        with pytest.raises(RuntimeError, match="ReasoningContext capacity exceeded"):
            ctx.add_intermediate(
                envelope_id="env-5",
                s="user",
                p="step",
                o="s5",
            )

    out = capsys.readouterr()
    has_event = any(e.get("event") == "reasoning_context_capacity_exceeded" for e in captured)
    has_stdout = "reasoning_context_capacity_exceeded" in out.out or "reasoning_context_capacity_exceeded" in out.err
    assert has_event or has_stdout, "Capacity exhaustion must be logged"


def test_reasoning_context_not_persisted_to_db(orch: Orchestrator) -> None:
    """Trap: ReasoningContext is per-turn working memory state, not persisted to DB."""
    rule = """
    (rule "trap-check-v1"
      :when (intent= "trap_intent")
      :plan (list (assert (user memory "working_only")))
      :priority 10)
    """
    m = orch.rule_engine.register_rule(rule)
    m.status = "ACTIVE"

    state = RuleState(intent="trap_intent", transcript="test", transcript_lower="test")
    orch.evaluate_rules_chain(state, trace=_trace("tr-trap"))

    # Check DB tables: no reasoning_context table exists
    with orch.db.read_cursor() as cur:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%reasoning%'")
        tables = cur.fetchall()
    assert len(tables) == 0, "Reasoning context must never be persisted to a DB table"


# =============================================================================
# WO-20 Phase 3: LLM Abductive Protocol & Gather Ladder Tests
# =============================================================================


def test_inference_step_schema_validation() -> None:
    """WO-20 Phase 3 Acceptance: InferenceStep schema validation checks."""
    # 1. Valid step passes
    valid_step = InferenceStep(
        premises=["user lives_in Melbourne"],
        s="user",
        p="state_is",
        o="Victoria",
        confidence=0.9,
        rationale="Melbourne is in Victoria",
        conditions=["ars asserts fact"],
    )
    assert valid_step.conclusion == "user state_is Victoria"

    # 2. Confidence > 1.0 fails
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        InferenceStep(
            premises=["p1"],
            s="user",
            p="state_is",
            o="Victoria",
            confidence=1.5,
        )

    # 3. Confidence < 0.0 fails
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        InferenceStep(
            premises=["p1"],
            s="user",
            p="state_is",
            o="Victoria",
            confidence=-0.1,
        )

    # 4. Invalid predicate slug fails
    with pytest.raises(ValidationError, match="Invalid predicate"):
        InferenceStep(
            premises=["p1"],
            s="user",
            p="INVALID PREDICATE!!",
            o="Victoria",
            confidence=0.8,
        )

    # 5. Conditions > 8 fails
    with pytest.raises(ValidationError, match="at most 8 items"):
        InferenceStep(
            premises=["p1"],
            s="user",
            p="state_is",
            o="Victoria",
            confidence=0.8,
            conditions=[f"source{i} asserts claim{i}" for i in range(9)],
        )

    # 6. Rationale > 500 chars fails
    with pytest.raises(ValidationError, match="at most 500 characters"):
        InferenceStep(
            premises=["p1"],
            s="user",
            p="state_is",
            o="Victoria",
            confidence=0.8,
            rationale="x" * 501,
        )


def test_fake_llm_valid_two_step_chain(orch: Orchestrator) -> None:
    """WO-20 Phase 3 Functional Acceptance 1:

    With a FakeLLM emitting a valid 2-step chain (premises present), both steps
    are signed and land in the context in order with step_kind='llm_abductive'.
    """
    trace = _trace("tr-abductive-2step")

    # Seed the store with initial verified premise
    orch._commit_lisp_assertion(AssertFact(s="user", p="lives_in", o="Melbourne"), trace)

    chain_json = json.dumps([
        {
            "premises": ["user lives_in Melbourne"],
            "s": "user",
            "p": "state_is",
            "o": "Victoria",
            "confidence": 0.95,
            "rationale": "Melbourne is the capital of Victoria.",
            "conditions": [],
        },
        {
            "premises": ["user state_is Victoria"],
            "s": "user",
            "p": "origin_is",
            "o": "Australia",
            "confidence": 0.90,
            "rationale": "Victoria is an Australian state.",
            "conditions": [],
        },
    ])

    fake_llm = FakeLLM(script=[
        TokenDelta(delta=chain_json),
        Done(usage=LLMUsage(prompt_tokens=15, completion_tokens=40)),
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="determine user origin from residence",
        trace=trace,
        llm=fake_llm,
    )

    assert len(accepted) == 2, "Both inference steps must be accepted"
    assert spoken is None

    context = orch.current_reasoning_context
    assert context is not None
    # Intermediates: 1 seeded + 2 abductive steps = 3 entries
    assert len(context) >= 2

    # Check the two abductive steps in reasoning context
    step1_entry = context.resolve_premise("user state_is Victoria")
    assert step1_entry is not None
    assert step1_entry.step_kind == "llm_abductive"
    assert step1_entry.rule_id == "llm"
    assert step1_entry.confidence == 0.95

    step2_entry = context.resolve_premise("user origin_is Australia")
    assert step2_entry is not None
    assert step2_entry.step_kind == "llm_abductive"
    assert step2_entry.rule_id == "llm"
    assert step2_entry.confidence == 0.90

    # Verify store contains LISP_ASSERTION signed envelopes for both
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT content FROM memories
            WHERE content IN ('user state_is Victoria', 'user origin_is Australia')
            """
        )
        stored_contents = [r[0] for r in cur.fetchall()]
    assert "user state_is Victoria" in stored_contents
    assert "user origin_is Australia" in stored_contents


def test_fake_llm_step_rejected_revised_and_accepted(orch: Orchestrator) -> None:
    """WO-20 Phase 3 Functional Acceptance 2:

    With a FakeLLM emitting a step whose premise is absent, the step is rejected,
    the model gets the machine-readable reason, and a second (corrected) step is accepted.
    """
    trace = _trace("tr-revise-step")

    # Seed verified fact
    orch._commit_lisp_assertion(AssertFact(s="user", p="likes", o="gelato"), trace)

    # Round 1: Model emits unverified premise "user likes pizza"
    round_1_json = json.dumps([
        {
            "premises": ["user likes pizza"],
            "s": "user",
            "p": "diet_is",
            "o": "italian_food_lover",
            "confidence": 0.8,
        }
    ])
    # Round 2: Model revises against verified premise "user likes gelato"
    round_2_json = json.dumps([
        {
            "premises": ["user likes gelato"],
            "s": "user",
            "p": "diet_is",
            "o": "dessert_enthusiast",
            "confidence": 0.85,
        }
    ])

    fake_llm = FakeLLM(rounds=[
        [TokenDelta(delta=round_1_json), Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20))],
        [TokenDelta(delta=round_2_json), Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=20))],
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="deduce user diet",
        trace=trace,
        llm=fake_llm,
    )

    assert len(accepted) == 1
    assert accepted[0].conclusion == "user diet_is dessert_enthusiast"
    assert accepted[0].premises == ["user likes gelato"]

    context = orch.current_reasoning_context
    assert context is not None
    entry = context.resolve_premise("user diet_is dessert_enthusiast")
    assert entry is not None
    assert entry.step_kind == "llm_abductive"


def test_gather_ladder_memory_retry_recovers_unseeded_context(orch: Orchestrator) -> None:
    """WO-20 Phase 3 Functional Acceptance 3:

    A second invalid step whose premise IS retrievable via memory_search
    (seed the store, exclude from turn context) -> memory retry recovers it
    and the chain completes.
    """
    trace = _trace("tr-mem-retry")

    # Seed the store with a memory, but clear reasoning context so it's not in initial turn context
    orch._commit_lisp_assertion(AssertFact(s="user", p="partner_is", o="judge_in_philippines"), trace)
    orch.current_reasoning_context = ReasoningContext()

    # Model emits a premise: Round 1 fails on invented fact, Round 2 emits the seeded fact
    round_1_json = json.dumps([
        {
            "premises": ["user lives_in Manila"],
            "s": "user",
            "p": "region_is",
            "o": "Southeast_Asia",
            "confidence": 0.8,
        }
    ])
    round_2_json = json.dumps([
        {
            "premises": ["judge_in_philippines"],
            "s": "user",
            "p": "likely_location_is",
            "o": "Philippines",
            "confidence": 0.75,
        }
    ])

    fake_llm = FakeLLM(rounds=[
        [TokenDelta(delta=round_1_json), Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20))],
        [TokenDelta(delta=round_2_json), Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=20))],
    ])

    search_calls: list[RetrievalQuery] = []
    original_search = orch.memory_store.search

    def spy_search(q: RetrievalQuery):
        search_calls.append(q)
        return original_search(q)

    orch.memory_store.search = spy_search

    accepted, spoken = orch.run_deduction_step(
        goal="find likely location",
        trace=trace,
        llm=fake_llm,
    )

    # Memory retry recovers the judge_in_philippines fact from the store
    assert len(accepted) == 1
    assert accepted[0].conclusion == "user likely_location_is Philippines"
    assert len(search_calls) >= 1
    assert search_calls[0].query_text == "judge_in_philippines"
    assert search_calls[0].k == 5


def test_gather_ladder_named_gap_abstention_or_user_question(orch: Orchestrator) -> None:
    """WO-20 Phase 3 Functional Acceptance 4:

    A step whose premise is NOT in the store -> turn ends with named-gap
    user question or named-gap abstention; no commit occurs; missing premise
    is named in spoken output.
    """
    trace = _trace("tr-gap-question")
    orch.current_reasoning_context = ReasoningContext()

    # Emits an unverified personal premise that cannot be verified anywhere
    round_1_json = json.dumps([
        {
            "premises": ["user birthplace_is Canberra"],
            "s": "user",
            "p": "nationality_is",
            "o": "Australian",
            "confidence": 0.9,
        }
    ])
    round_2_json = json.dumps([
        {
            "premises": ["user birthplace_is Canberra"],
            "s": "user",
            "p": "nationality_is",
            "o": "Australian",
            "confidence": 0.9,
        }
    ])

    fake_llm = FakeLLM(rounds=[
        [TokenDelta(delta=round_1_json), Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20))],
        [TokenDelta(delta=round_2_json), Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=20))],
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="deduce nationality",
        trace=trace,
        llm=fake_llm,
    )

    # Must NOT commit or accept the step
    assert len(accepted) == 0
    assert spoken is not None
    # Missing premise must be explicitly named in spoken output
    assert "birthplace_is Canberra" in spoken
    assert "can you tell me about it?" in spoken

    # Store must NOT have committed the nationality conclusion
    with orch.db.read_cursor() as cur:
        cur.execute("SELECT content FROM memories WHERE content = 'user nationality_is Australian'")
        assert cur.fetchall() == []


def test_attributed_premise_acceptance_and_rejection(orch: Orchestrator) -> None:
    """WO-20 Phase 3 Amendment Acceptance:

    Attributed premise '<source> asserts <claim>' backed by a current-turn signed
    fetch receipt is accepted and lands in conditions.
    Attributed premise without signed receipt is rejected as unverified_premise.
    """
    trace = _trace("tr-attributed-premise")

    # Scenario A: Tool receipt present in current turn
    orch.current_turn_receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-1",
            output="Report from ars-technica: confirmed that driver-582.11 fixes wsl-crash on Windows 11.",
        )
    ]

    step_json = json.dumps([
        {
            "premises": ["ars-technica asserts driver-582.11 fixes wsl-crash"],
            "s": "driver-582.11",
            "p": "fixes_issue",
            "o": "wsl-crash",
            "confidence": 0.85,
            "conditions": ["ars-technica asserts driver-582.11 fixes wsl-crash"],
        }
    ])

    fake_llm = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=30)),
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="check driver fix",
        trace=trace,
        llm=fake_llm,
    )

    assert len(accepted) == 1
    assert "ars-technica asserts driver-582.11 fixes wsl-crash" in accepted[0].conditions

    context = orch.current_reasoning_context
    assert context is not None
    entry = context.resolve_premise("driver-582.11 fixes_issue wsl-crash")
    assert entry is not None
    assert "ars-technica asserts driver-582.11 fixes wsl-crash" in entry.conditions

    # Scenario B: No tool receipt present in current turn
    orch.current_turn_receipts = []
    fake_llm_unverified = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=30)),
    ])

    accepted_empty, spoken_empty = orch.run_deduction_step(
        goal="check driver fix again",
        trace=trace,
        llm=fake_llm_unverified,
    )

    # Without tool receipt, must be rejected!
    assert len(accepted_empty) == 0
    assert spoken_empty is not None
    assert "driver-582.11 fixes wsl-crash" in spoken_empty or "can't verify" in spoken_empty.lower()


# ============================================================================
# Phase 4 Functional Acceptance Tests (WO-20d / D-REAS-09)
# ============================================================================


def test_completed_chain_commits_inferred_fact_and_gate_verifies(orch: Orchestrator) -> None:
    """WO-20 Phase 4 Functional Acceptance 1:
    A completed chain commits an INFERRED fact; the gate verifies it; proof_trace replays (every premise resolves).
    """
    trace = _trace("tr-inferred-commit")
    orch._commit_lisp_assertion(AssertFact(s="user", p="likes", o="gelato"), trace)

    ctx = ReasoningContext()
    orch.current_reasoning_context = ctx

    step_json = json.dumps([
        {
            "premises": ["user likes gelato"],
            "s": "user",
            "p": "trait_is",
            "o": "dessert_lover",
            "confidence": 0.9,
        },
        {
            "premises": ["user trait_is dessert_lover"],
            "s": "user",
            "p": "interest_is",
            "o": "culinary",
            "confidence": 0.85,
        },
    ])
    fake_llm = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=30)),
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="infer interest",
        trace=trace,
        llm=fake_llm,
    )
    assert len(accepted) == 2

    # Check that INFERRED fact was committed
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content, e.provenance, e.confidence, e.payload_json
            FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    content, prov, conf, payload_json_str = rows[0]
    assert content == "user interest_is culinary"
    assert prov == "INFERRED"
    assert conf == 0.85

    payload_dict = json.loads(payload_json_str)
    assert "proof_trace" in payload_dict["structured"]
    pt = payload_dict["structured"]["proof_trace"]
    assert len(pt) == 2
    assert pt[0]["conclusion"] == "user trait_is dessert_lover"
    assert pt[1]["conclusion"] == "user interest_is culinary"


def test_trace_with_fabricated_premise_rejected_at_gate(
    orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """WO-20 Phase 4 Functional Acceptance 2:
    A trace with a fabricated premise is rejected at the gate (ProvenanceRejected).
    """
    trace = _trace("tr-fab-gate")
    signer = signer_factory.inferred_fact()
    gate = ProvenanceGate(master_key=signer_factory.master_key, db=orch.db)

    # Fabricate a proof trace where step 1 references an unverified premise that does not exist in store
    fabricated_trace = [
        {
            "step_kind": "llm_abductive",
            "rule_id": "llm",
            "premises": ["user born_in Mars"],
            "conclusion": "user origin_is Martian",
            "envelope_id": f"lisp-{ulid.ULID()}",
            "confidence": 0.8,
            "conditions": [],
        }
    ]

    unsigned = UnsignedPayload(
        content="user origin_is Martian",
        provenance=Provenance.INFERRED,
        kind="fact",
        confidence=0.8,
        nonce="fabrication0011223344",
        created_at=time.time(),
        trace_id=trace.trace_id,
        structured={
            "s": "user",
            "p": "origin_is",
            "o": "Martian",
            "proof_trace": fabricated_trace,
        },
    )
    signed = signer.sign(unsigned)

    with pytest.raises(ProvenanceRejected, match="does not resolve"):
        gate.admit(signed)


def test_user_derived_supersedes_inferred_fact(
    orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """WO-20 Phase 4 Functional Acceptance 3:
    A later USER_DERIVED fact on the same predicate supersedes the INFERRED one;
    the cascade prefers the direct evidence.
    """
    trace = _trace("tr-supersede-inferred")

    # 1. Commit an INFERRED fact: user lives_in Melbourne
    signed_prem = orch._commit_lisp_assertion(AssertFact(s="user", p="likes", o="coffee"), trace)
    assert signed_prem is not None
    ctx = ReasoningContext()
    ctx.add_intermediate(
        envelope_id=signed_prem.entry_id,
        s="user",
        p="likes",
        o="coffee",
        confidence=1.0,
        step_kind="lisp_rule",
    )
    signed_inter = orch._commit_lisp_assertion(
        AssertFact(s="user", p="lives_in", o="Melbourne"), trace
    )
    assert signed_inter is not None
    ctx.add_intermediate(
        envelope_id=signed_inter.entry_id,
        s="user",
        p="lives_in",
        o="Melbourne",
        confidence=0.8,
        step_kind="llm_abductive",
        premises=["user likes coffee"],
    )
    inferred_signed = orch.finalize_chain(ctx, trace)
    assert inferred_signed is not None

    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.memory_id, m.content, m.valid_to, e.provenance
            FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        inferred_rows = cur.fetchall()
    assert len(inferred_rows) == 1
    inferred_mid, inferred_content, inferred_vt, _ = inferred_rows[0]
    assert inferred_vt is None

    # 2. Later, direct evidence arrives: USER_DERIVED fact: user lives_in Sydney
    derived_signer = DerivedFactSigner(master_key=signer_factory.master_key)
    user_speech_signer = signer_factory.user_speech()

    transcript_signed = user_speech_signer.sign(
        UnsignedPayload(
            content="I actually live in Sydney now",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce="userturn000111222",
            created_at=time.time() + 10,
            trace_id=trace.trace_id,
        )
    )
    orch.memory_store.commit(transcript_signed)

    derived_unsigned = UnsignedPayload(
        content="user lives_in Sydney",
        provenance=Provenance.USER_DERIVED,
        kind="fact",
        confidence=0.95,
        source_entry_ids=[transcript_signed.entry_id],
        nonce="derivedturn000111222",
        created_at=time.time() + 15,
        trace_id=trace.trace_id,
        structured={"s": "user", "p": "lives_in", "o": "Sydney"},
    )
    derived_signed = derived_signer.sign(derived_unsigned)
    orch.memory_store.commit(derived_signed)

    # 3. Verify in DB: the INFERRED memory is now superseded!
    with orch.db.read_cursor() as cur:
        cur.execute(
            "SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?",
            (inferred_mid,),
        )
        row = cur.fetchone()
    assert row[0] is not None
    assert row[1] is not None

    # 4. Verify cascade prefers direct evidence
    cascade = EpistemicSearchCascade(memory_store=orch.memory_store)
    evidence = cascade.query_substrate_2_memory("lives_in")
    belnap, text, _ = cascade.synthesize("where does user live?", evidence)
    assert "Sydney" in text
    assert "[superseded]" in text or "supersedes" in text


def test_cascade_and_renderer_frame_inferred_fact_as_inferred_confidence(
    orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """WO-20 Phase 4 / WO-21 Phase 0 Functional Acceptance:
    The cascade and memory context renderer frame the fact as 'inferred, confidence c' in prompt context.
    """
    trace = _trace("tr-frame-inferred")
    signed_prem = orch._commit_lisp_assertion(AssertFact(s="user", p="job", o="engineer"), trace)
    assert signed_prem is not None
    ctx = ReasoningContext()
    ctx.add_intermediate(
        envelope_id=signed_prem.entry_id,
        s="user",
        p="job",
        o="engineer",
        confidence=1.0,
        step_kind="lisp_rule",
    )
    signed_step = orch._commit_lisp_assertion(
        AssertFact(s="user", p="skill_level", o="senior"), trace
    )
    assert signed_step is not None
    ctx.add_intermediate(
        envelope_id=signed_step.entry_id,
        s="user",
        p="skill_level",
        o="senior",
        confidence=0.82,
        step_kind="llm_abductive",
        premises=["user job engineer"],
    )
    inferred_signed = orch.finalize_chain(ctx, trace)
    assert inferred_signed is not None

    # Test format_memory_context (renderer)
    q = RetrievalQuery(query_text="skill_level", k=5)
    hits = orch.memory_store.search(q)
    inferred_hits = [
        h for h in hits if h.provenance == Provenance.INFERRED or str(h.provenance) == "INFERRED"
    ]
    assert len(inferred_hits) >= 1
    rendered = format_memory_context(inferred_hits)
    assert "inferred, confidence 0.82" in rendered
    assert "deduced, confidence" not in rendered

    # Test cascade formatting
    cascade = EpistemicSearchCascade(memory_store=orch.memory_store)
    evidence = cascade.query_substrate_2_memory("skill_level")
    _, cascade_text, _ = cascade.synthesize("skill_level", evidence)
    assert "inferred, confidence 0.82" in cascade_text
    assert "deduced, confidence" not in cascade_text


def test_migration_0007_upgrades_pre_inferred_database(tmp_path: Path) -> None:
    """WO-20 Phase 4 Blocker F-P4-1 Verification:
    Existing databases that ran migrations 1-6 prior to Phase 4 (without INFERRED in CHECK constraint)
    are successfully upgraded by migration 0007 and can commit INFERRED facts.
    """
    import sqlite3
    import subprocess

    db_path = tmp_path / "legacy_memory.sqlite"

    mig_dir = Path("src/lucca/memory/migrations")
    try:
        p0001 = subprocess.check_output(
            ["git", "show", "061a10d:src/lucca/memory/migrations/0001_init.sql"], text=True
        )
        p0006 = subprocess.check_output(
            ["git", "show", "061a10d:src/lucca/memory/migrations/0006_autobiographical.sql"],
            text=True,
        )
    except Exception:
        raw_0001 = (mig_dir / "0001_init.sql").read_text(encoding="utf-8")
        raw_0006 = (mig_dir / "0006_autobiographical.sql").read_text(encoding="utf-8")
        p0001 = raw_0001.replace(",'INFERRED'", "")
        p0006 = raw_0006.replace("                        'INFERRED',\n", "").replace(
            "          'INFERRED',\n", ""
        )

    sql_0002 = (mig_dir / "0002_decisions.sql").read_text(encoding="utf-8")
    sql_0003 = (mig_dir / "0003_rules.sql").read_text(encoding="utf-8")
    sql_0004 = (mig_dir / "0004_execution_triples.sql").read_text(encoding="utf-8")
    sql_0005 = (mig_dir / "0005_contrastive_shadow.sql").read_text(encoding="utf-8")

    db = DatabaseManager(db_path)
    conn = db.get_connection()
    conn.execute(
        "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
    )
    conn.executescript(p0001)
    conn.execute("INSERT INTO schema_migrations VALUES (1, 1000.0)")
    conn.executescript(sql_0002)
    conn.execute("INSERT INTO schema_migrations VALUES (2, 1000.0)")
    conn.executescript(sql_0003)
    conn.execute("INSERT INTO schema_migrations VALUES (3, 1000.0)")
    conn.executescript(sql_0004)
    conn.execute("INSERT INTO schema_migrations VALUES (4, 1000.0)")
    conn.executescript(sql_0005)
    conn.execute("INSERT INTO schema_migrations VALUES (5, 1000.0)")
    conn.executescript(p0006)
    conn.execute("INSERT INTO schema_migrations VALUES (6, 1000.0)")
    conn.commit()

    # Seed an existing envelope
    conn.execute(
        """
        INSERT INTO provenance_envelopes(
            entry_id, provenance, kind, signer_id, signature, content_sha256, nonce, created_at,
            trace_id, session_id, confidence, payload_json, grounding_eligible
        ) VALUES (
            'legacy-env-1', 'USER_EXPLICIT', 'transcript', 'user', 'sig1', 'sha1', 'n1', 100.0,
            'tr-1', 's-1', 1.0, '{}', 1
        )
        """
    )
    conn.commit()

    # Verify that inserting an INFERRED envelope on the pre-edit DB fails with IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO provenance_envelopes(
                entry_id, provenance, kind, signer_id, signature, content_sha256, nonce, created_at,
                trace_id, session_id, confidence, payload_json, grounding_eligible
            ) VALUES (
                'inferred-env-fail', 'INFERRED', 'fact', 'orch', 'sig2', 'sha2', 'n2', 101.0,
                'tr-2', 's-2', 0.85, '{}', 1
            )
            """
        )
        conn.commit()
    conn.close()

    # 2. Run migrate() to apply migration 0007
    applied = db.migrate()
    assert 7 in applied

    # 3. Verify that INFERRED facts can now be committed via MemoryStore and finalize_chain
    master_key = b"01234567890123456789012345678901"
    store = MemoryStore(db=db, master_key=master_key)
    signer_factory = SignerFactory(master_key=master_key)

    orch = Orchestrator.__new__(Orchestrator)
    orch.db = db
    orch.memory_store = store
    orch.signer_factory = signer_factory
    orch.rule_engine = RuleLifecycleManager(db=db)

    trace = _trace("tr-mig-upgrade")
    signed_prem = orch._commit_lisp_assertion(AssertFact(s="user", p="job", o="engineer"), trace)
    assert signed_prem is not None
    ctx = ReasoningContext()
    ctx.add_intermediate(
        envelope_id=signed_prem.entry_id,
        s="user",
        p="job",
        o="engineer",
        confidence=1.0,
        step_kind="lisp_rule",
    )
    signed_step = orch._commit_lisp_assertion(
        AssertFact(s="user", p="skill_level", o="senior"), trace
    )
    assert signed_step is not None
    ctx.add_intermediate(
        envelope_id=signed_step.entry_id,
        s="user",
        p="skill_level",
        o="senior",
        confidence=0.82,
        step_kind="llm_abductive",
        premises=["user job engineer"],
    )

    inferred_signed = orch.finalize_chain(ctx, trace)
    assert inferred_signed is not None
    assert inferred_signed.provenance == Provenance.INFERRED

    with db.read_cursor() as cur:
        row = cur.execute(
            "SELECT provenance FROM provenance_envelopes WHERE entry_id = ?",
            (inferred_signed.entry_id,),
        ).fetchone()
    assert row[0] == "INFERRED"
    assert db.check_integrity()


# =============================================================================
# WO-20 Phase 5: Live Acceptance — The "Where Am I From" Chain
# =============================================================================


def test_phase5_live_acceptance_where_am_i_from_chain(
    orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """WO-20 Phase 5 Functional Acceptance:
    - Scripted scenario (FakeLLM + seeded store): store contains partner_is judge_in_philippines
      and tz_is UTC+8. User asks the deduction question. The system produces
      user likely_location Philippines (step 1), then with drop_bears origin_is australian_folklore
      produces nationality_is Australian (step 2), and commits nationality_is Australian as INFERRED
      with a 2-step proof trace — without any operator leading.
    - The committed fact is superseded when the user then says "I'm Australian" (direct evidence wins).
    """
    trace = _trace("tr-p5-acceptance")

    # 1. Seed store with prior facts
    p1 = orch._commit_lisp_assertion(
        AssertFact(s="user", p="partner_is", o="judge_in_philippines"), trace
    )
    assert p1 is not None
    p2 = orch._commit_lisp_assertion(AssertFact(s="user", p="tz_is", o="UTC+8"), trace)
    assert p2 is not None
    p3 = orch._commit_lisp_assertion(
        AssertFact(s="drop_bears", p="origin_is", o="australian_folklore"), trace
    )
    assert p3 is not None

    # 2. Scripted LLM proposing cold 2-step deduction without operator leading
    step_json = json.dumps([
        {
            "premises": ["user partner_is judge_in_philippines", "user tz_is UTC+8"],
            "s": "user",
            "p": "likely_location",
            "o": "Philippines",
            "confidence": 0.85,
            "rationale": "Partner is in Philippines and timezone is UTC+8.",
        },
        {
            "premises": [
                "user likely_location Philippines",
                "drop_bears origin_is australian_folklore",
            ],
            "s": "user",
            "p": "nationality_is",
            "o": "Australian",
            "confidence": 0.80,
            "rationale": "Drop bears folklore indicates Australian nationality despite likely current location in Philippines.",
        },
    ])
    fake_llm = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=15, completion_tokens=40)),
    ])

    # 3. User asks the deduction question
    accepted, spoken = orch.run_deduction_step(
        goal="Where am I from?",
        trace=trace,
        llm=fake_llm,
    )
    assert len(accepted) == 2

    # 4. Verify INFERRED commit and 2-step proof trace
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.memory_id, m.content, e.provenance, e.confidence, e.payload_json
            FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    inferred_mid, content, prov, conf, payload_json_str = rows[0]
    assert content == "user nationality_is Australian"
    assert prov == "INFERRED"
    assert conf == 0.80  # min(0.85, 0.80)

    payload_dict = json.loads(payload_json_str)
    pt = payload_dict["structured"]["proof_trace"]
    assert len(pt) == 2
    assert pt[0]["conclusion"] == "user likely_location Philippines"
    assert "user partner_is judge_in_philippines" in pt[0]["premises"]
    assert pt[1]["conclusion"] == "user nationality_is Australian"
    assert "user likely_location Philippines" in pt[1]["premises"]
    assert "drop_bears origin_is australian_folklore" in pt[1]["premises"]

    # 5. Gate admission verification (proof trace replays successfully)
    inferred_payload = SignedPayload.model_validate_json(payload_json_str)
    gate = ProvenanceGate(master_key=signer_factory.master_key, db=orch.db)
    admitted = gate.admit(inferred_payload)
    assert admitted.payload.entry_id == inferred_payload.entry_id

    # 6. Direct evidence arrives: user says "I'm Australian"
    user_speech_signer = signer_factory.user_speech()
    derived_signer = DerivedFactSigner(master_key=signer_factory.master_key)

    transcript = user_speech_signer.sign(
        UnsignedPayload(
            content="I'm Australian",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce="direct_user_transcript_nonce_p5",
            created_at=time.time() + 10,
            trace_id=trace.trace_id,
        )
    )
    orch.memory_store.commit(transcript)

    derived = derived_signer.sign(
        UnsignedPayload(
            content="user nationality_is Australian",
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            confidence=0.99,
            source_entry_ids=[transcript.entry_id],
            nonce="direct_user_derived_nonce_p5",
            created_at=time.time() + 15,
            trace_id=trace.trace_id,
            structured={"s": "user", "p": "nationality_is", "o": "Australian"},
        )
    )
    orch.memory_store.commit(derived)

    # 7. Inferred fact is superseded by direct evidence
    with orch.db.read_cursor() as cur:
        row = cur.execute(
            "SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?",
            (inferred_mid,),
        ).fetchone()
    assert row[0] is not None, "Inferred fact must be marked superseded (valid_to is set)"
    assert row[1] is not None, "Inferred fact superseded_by must reference the direct evidence"

    # 8. Cascade query confirms direct evidence wins over deduction
    cascade = EpistemicSearchCascade(memory_store=orch.memory_store)
    evidence = cascade.query_substrate_2_memory("nationality_is")
    belnap, cascade_text, _ = cascade.synthesize("Where am I from?", evidence)
    assert "Australian" in cascade_text
    assert "[asserts]" in cascade_text


def test_build_deduction_messages_prompt_contract():
    """Validates build_deduction_messages constructs deduction messages with verified facts and receipts."""
    from lucca.brain.prompt_builder import build_deduction_messages

    msgs = build_deduction_messages(
        goal="Where was user born?",
        verified_facts=["user partner_is judge_in_philippines"],
        attributed_receipts=["fetch_web: user born in Sydney"],
        error_feedback="Step 1 was invalid",
    )
    assert len(msgs) >= 2
    system_msg = msgs[0].content
    assert "[Verified Signed Facts Context]" in system_msg
    assert "user partner_is judge_in_philippines" in system_msg
    assert "[Verified Tool Receipts Context]" in system_msg
    assert "fetch_web: user born in Sydney" in system_msg
    user_msg = msgs[-1].content
    assert "Where was user born?" in user_msg
    assert "Step 1 was invalid" in user_msg


def test_phase6_live_acceptance_source_conditioned_chain(
    orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """WO-21 Phase 6 Functional Acceptance (WO-21g):
    - Scripted (FakeLLM + seeded store + seeded receipts):
      Store has `user partner_is judge_in_philippines`, `user tz_is UTC+8`.
      Whitelisted fetch receipt asserts "driver-582.11 fixes wsl-crash".
      The chain produces:
      1) user likely_location Philippines (corroborated by independent store facts, boosted).
      2) driver-582.11 likely_fixes user's wsl-crash (source-conditioned conclusion),
         committed as INFERRED with the attributed premise in conditions.
    - Spoken output names the condition: "…if ars-technica is right about the driver fix."
    - Traps: Runs in ONE turn with no operator leading; every intermediate signed;
      the final commit passes the gate replay.
    - Standard-labeled in prompt context (format_memory_context and cascade.synthesize).
    - Superseded when direct user evidence arrives.
    """
    trace = _trace("tr-p6-acceptance")

    # 1. Seed store with prior facts
    p1 = orch._commit_lisp_assertion(
        AssertFact(s="user", p="partner_is", o="judge_in_philippines"), trace
    )
    assert p1 is not None
    p2 = orch._commit_lisp_assertion(AssertFact(s="user", p="tz_is", o="UTC+8"), trace)
    assert p2 is not None

    # 2. Seed whitelisted fetch receipt asserting the driver fix
    orch.current_turn_receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-ars",
            source="arstechnica.com",
            args={"url": "https://arstechnica.com/gadgets/2026/wsl-driver-fix"},
            output="arstechnica.com asserts driver-582.11 fixes wsl-crash on Windows 11 updates.",
        )
    ]

    # Track spoken calls via spy
    spoken_history: list[str] = []
    original_speak = getattr(orch, "_speak_text", None)

    def spy_speak(t: TurnTrace, text: str) -> None:
        spoken_history.append(text)
        if original_speak:
            original_speak(t, text)

    orch._speak_text = spy_speak

    # 3. Scripted LLM proposing cold 2-step deduction without operator leading (ONE turn)
    step_json = json.dumps([
        {
            "premises": [
                "user partner_is judge_in_philippines",
                "user tz_is UTC+8",
            ],
            "s": "user",
            "p": "likely_location",
            "o": "Philippines",
            "confidence": 0.80,
            "rationale": "Partner is in Philippines and timezone is UTC+8.",
        },
        {
            "premises": [
                "user likely_location Philippines",
                "ars-technica asserts driver-582.11 fixes wsl-crash",
            ],
            "s": "driver-582.11",
            "p": "likely_fixes",
            "o": "user's wsl-crash",
            "confidence": 0.85,
            "conditions": ["if ars-technica is right about the driver fix"],
            "rationale": "Ars Technica reports driver 582.11 fixes WSL crashes.",
        },
    ])
    fake_llm = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=50)),
    ])

    # 4. Execute deduction step in ONE turn
    accepted, spoken = orch.run_deduction_step(
        goal="Can driver 582.11 fix my WSL crash?",
        trace=trace,
        llm=fake_llm,
    )

    # Both steps accepted in ONE turn
    assert len(accepted) == 2

    # Step 1: corroborated by independent store facts, boosted from 0.80 -> 0.90!
    assert accepted[0].confidence == 0.90
    assert accepted[0].conclusion == "user likely_location Philippines"

    # Step 2: source-conditioned conclusion with attributed premise in conditions
    assert accepted[1].confidence == 0.85
    assert accepted[1].conclusion == "driver-582.11 likely_fixes user's wsl-crash"
    assert any("asserts" in c for c in accepted[1].conditions)
    assert any("driver fix" in c for c in accepted[1].conditions)

    # 5. Spoken output names the condition
    expected_condition_speech = "…if ars-technica is right about the driver fix."
    assert spoken == expected_condition_speech
    assert expected_condition_speech in spoken_history

    # 6. Intermediates signed as LISP_ASSERTION in store (Trap 2)
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT entry_id, signature, payload_json, provenance
            FROM provenance_envelopes
            WHERE provenance = 'LISP_ASSERTION'
            ORDER BY created_at ASC
            """
        )
        lisp_rows = cur.fetchall()
    # At least p1, p2, step1, step2 exist
    assert len(lisp_rows) >= 4
    contents = [json.loads(r[2])["content"] for r in lisp_rows]
    assert "user likely_location Philippines" in contents
    assert "driver-582.11 likely_fixes user's wsl-crash" in contents

    # 7. Final commit as INFERRED with proof trace and standard label
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.memory_id, m.content, e.provenance, e.confidence, e.payload_json
            FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        inferred_rows = cur.fetchall()
    assert len(inferred_rows) == 1
    inferred_mid, content, prov, conf, payload_json_str = inferred_rows[0]
    assert content == "driver-582.11 likely_fixes user's wsl-crash"
    assert prov == "INFERRED"
    assert conf == 0.85  # min(0.90, 0.85)

    payload_dict = json.loads(payload_json_str)
    structured = payload_dict["structured"]
    assert structured["proof_standard"] == "clear and convincing"
    assert any("asserts" in c for c in structured["conditions"])
    assert any("driver fix" in c for c in structured["conditions"])
    pt = structured["proof_trace"]
    assert len(pt) == 2
    assert pt[0]["conclusion"] == "user likely_location Philippines"
    assert pt[1]["conclusion"] == "driver-582.11 likely_fixes user's wsl-crash"

    # 8. Gate admission replay check (Trap 3)
    inferred_payload = SignedPayload.model_validate_json(payload_json_str)
    gate = ProvenanceGate(master_key=signer_factory.master_key, db=orch.db)
    admitted = gate.admit(inferred_payload)
    assert admitted.payload.entry_id == inferred_payload.entry_id

    # 9. Prompt context shows standard label (format_memory_context and cascade.synthesize)
    q = RetrievalQuery(query_text="driver-582.11", k=5)
    hits = orch.memory_store.search(q)
    inferred_hits = [
        h for h in hits if getattr(h, "provenance", "") in (Provenance.INFERRED, "INFERRED")
    ]
    assert len(inferred_hits) >= 1

    # format_memory_context check
    rendered = format_memory_context(inferred_hits)
    assert "inferred, confidence 0.85 — clear and convincing" in rendered

    # cascade.synthesize check
    cascade = EpistemicSearchCascade(memory_store=orch.memory_store)
    evidence = cascade.query_substrate_2_memory("driver-582.11")
    _, cascade_text, _ = cascade.synthesize("driver-582.11", evidence)
    assert "[inferred, confidence 0.85 — clear and convincing]" in cascade_text

    # 10. Direct user evidence arrives and supersedes INFERRED fact
    user_speech_signer = signer_factory.user_speech()
    derived_signer = DerivedFactSigner(master_key=signer_factory.master_key)

    transcript = user_speech_signer.sign(
        UnsignedPayload(
            content="Actually, driver-582.11 didn't fix my WSL crash at all.",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce="user-direct-speech-001",
            created_at=time.time() + 10,
            trace_id=trace.trace_id,
        )
    )
    orch.memory_store.commit(transcript)

    derived = derived_signer.sign(
        UnsignedPayload(
            content="driver-582.11 likely_fixes did_not_fix_wsl_crash",
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            confidence=0.98,
            source_entry_ids=[transcript.entry_id],
            nonce="derived-direct-fix-001",
            created_at=time.time() + 15,
            trace_id=trace.trace_id,
            structured={
                "s": "driver-582.11",
                "p": "likely_fixes",
                "o": "did_not_fix_wsl_crash",
            },
        )
    )
    orch.memory_store.commit(derived)

    # Verify INFERRED memory is now superseded (valid_to and superseded_by populated)
    with orch.db.read_cursor() as cur:
        row = cur.execute(
            "SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?",
            (inferred_mid,),
        ).fetchone()
    assert row is not None
    assert row[0] is not None, "Inferred fact must be marked superseded (valid_to is set)"
    assert row[1] is not None, "Inferred fact superseded_by must reference the direct evidence"


def test_phase6_live_acceptance_dispute_docking(
    orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """WO-21 Phase 6 Acceptance (Dispute Seeding Variant):
    When a disputing fact is seeded in the store, Walton authority Q3 triggers,
    docking confidence (-0.30) and adding the dispute condition.
    Because the resulting confidence is below standard (0.85 - 0.30 = 0.55 < 0.75),
    finalize_chain refuses the commit, speaking the speculation hedge.
    """
    trace = _trace("tr-p6-dispute")

    # 1. Seed store with prior facts
    orch._commit_lisp_assertion(
        AssertFact(s="user", p="partner_is", o="judge_in_philippines"), trace
    )
    orch._commit_lisp_assertion(AssertFact(s="user", p="tz_is", o="UTC+8"), trace)

    # 2. Seed disputing fact in store
    derived_signer = DerivedFactSigner(master_key=signer_factory.master_key)
    user_signer = signer_factory.user_speech()
    t_signed = user_signer.sign(
        UnsignedPayload(
            content="nvidia disputes that driver-582.11 fixes wsl-crash",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce="user-dispute-seed-001",
            created_at=time.time() - 20,
            trace_id=trace.trace_id,
        )
    )
    orch.memory_store.commit(t_signed)

    dispute_fact = derived_signer.sign(
        UnsignedPayload(
            content="nvidia disputes driver-582.11 fixes wsl-crash",
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            confidence=0.95,
            source_entry_ids=[t_signed.entry_id],
            nonce="dispute-seed-001",
            created_at=time.time() - 10,
            trace_id=trace.trace_id,
            structured={
                "s": "driver-582.11",
                "p": "disputes",
                "o": "driver-582.11 fixes wsl-crash",
            },
        )
    )
    orch.memory_store.commit(dispute_fact)

    # 3. Seed receipt
    orch.current_turn_receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-ars",
            source="arstechnica.com",
            args={"url": "https://arstechnica.com/gadgets/2026/wsl-driver-fix"},
            output="arstechnica.com asserts driver-582.11 fixes wsl-crash on Windows 11 updates.",
        )
    ]

    step_json = json.dumps([
        {
            "premises": [
                "user partner_is judge_in_philippines",
                "user tz_is UTC+8",
            ],
            "s": "user",
            "p": "likely_location",
            "o": "Philippines",
            "confidence": 0.80,
        },
        {
            "premises": [
                "user likely_location Philippines",
                "ars-technica asserts driver-582.11 fixes wsl-crash",
            ],
            "s": "driver-582.11",
            "p": "likely_fixes",
            "o": "user's wsl-crash",
            "confidence": 0.85,
            "conditions": ["if ars-technica is right about the driver fix"],
        },
    ])
    fake_llm = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=50)),
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="Can driver 582.11 fix my WSL crash?",
        trace=trace,
        llm=fake_llm,
    )

    # Step 1 boosted: 0.80 + 0.10 = 0.90
    # Step 2 docked: 0.85 - 0.30 = 0.55
    assert len(accepted) == 2
    assert accepted[0].confidence == 0.90
    assert accepted[1].confidence == 0.55
    assert any("dispute" in c.lower() or "nvidia" in c.lower() for c in accepted[1].conditions)

    # Below standard (< 0.75 CLEAR_AND_CONVINCING): refused commit, speaks speculation hedge
    assert spoken is not None
    assert "I think" in spoken
    assert "not sure enough to keep it" in spoken

    # Store must NOT have committed the conclusion as INFERRED
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        assert cur.fetchall() == []
