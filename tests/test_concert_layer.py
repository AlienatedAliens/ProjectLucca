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

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.config import get_config
from lucca.core.exceptions import SchemeRuntimeError, SchemeSyntaxError
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    AssertFact,
    ExecutionTier,
    Plan,
    Provenance,
    RuleState,
    Say,
    SignedPayload,
)
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import ProvenanceGate
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import MAX_CHAIN_DEPTH, RuleLifecycleManager
from lucca.reasoning.scheme.eval import evaluate_expr, evaluate_rule
from lucca.reasoning.scheme.parser import parse_rule
from lucca.senses.embed import LocalEmbeddingPort

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
