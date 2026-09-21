"""
Unit and integration tests for Phase 2 (S1) typed Proposal/Decision/Outcome contract.
Spec §5, Handover #4 §2.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from lucca.core.schemas import (
    Decision,
    ExecutionTriple,
    Outcome,
    Plan,
    Proposal,
    RuleState,
    Say,
    ToolCall,
)
from lucca.memory.db import DatabaseManager
from lucca.reasoning.lifecycle import RuleLifecycleManager


def test_triple_round_trips_through_sqlite(tmp_path: Path) -> None:
    """(a) Triple round-trips through SQLite WAL and matches all fields."""
    db = DatabaseManager(tmp_path / "test_s1.sqlite")
    db.migrate()

    proposal = Proposal(
        rule_id="read-notes-v1",
        plan=[ToolCall(tool="read_file", args={"rel_path": "notes.txt"}, call_id="c1")],
        confidence=0.95,
        gas_estimate=12,
        evidence_refs=["trace-001", "trace-002"],
    )
    decision = Decision(
        proposal_id=proposal.proposal_id,
        verdict="accepted",
        reason_code="CONFIDENCE_HIGH",
    )
    outcome = Outcome(
        decision_id=decision.decision_id,
        signal="tool_exit_zero",
        detail="file read successfully",
    )
    triple = ExecutionTriple(
        proposal=proposal,
        decision=decision,
        outcome=outcome,
    )

    db.record_execution_triple(triple)

    retrieved = db.get_execution_triple(triple.triple_id)
    assert retrieved is not None
    assert retrieved.triple_id == triple.triple_id
    assert retrieved.proposal.rule_id == "read-notes-v1"
    assert retrieved.proposal.confidence == 0.95
    assert retrieved.proposal.gas_estimate == 12
    assert retrieved.proposal.evidence_refs == ["trace-001", "trace-002"]
    assert len(retrieved.proposal.plan) == 1
    assert isinstance(retrieved.proposal.plan[0], ToolCall)
    assert retrieved.proposal.plan[0].tool == "read_file"
    assert retrieved.decision.verdict == "accepted"
    assert retrieved.decision.reason_code == "CONFIDENCE_HIGH"
    assert retrieved.outcome.signal == "tool_exit_zero"
    assert retrieved.outcome.detail == "file read successfully"

    # List verification
    triples = db.list_execution_triples(limit=10)
    assert len(triples) == 1
    assert triples[0].triple_id == triple.triple_id


def test_schema_rejects_outcome_signal_outside_enum() -> None:
    """(b) Schema rejects an Outcome.signal value outside enum (e.g. LLM self-judgment)."""
    # Negative test: LLM self-judgment cannot be an Outcome.signal
    with pytest.raises(ValidationError) as exc_info:
        Outcome(
            decision_id="dec-123",
            signal="llm_self_judged",  # type: ignore[arg-type]
            detail="Self-evaluated success",
        )
    assert "signal" in str(exc_info.value)

    # Negative test: arbitrary string
    with pytest.raises(ValidationError) as exc_info:
        Outcome(
            decision_id="dec-123",
            signal="arbitrary_invented_signal",  # type: ignore[arg-type]
            detail="invalid",
        )
    assert "signal" in str(exc_info.value)

    # Valid signals must all be accepted
    valid_signals = [
        "tool_exit_zero",
        "pydantic_valid",
        "operator_confirm",
        "operator_correct",
        "abstained",
    ]
    for sig in valid_signals:
        out = Outcome(decision_id="dec-valid", signal=sig)  # type: ignore[arg-type]
        assert out.signal == sig


def test_schema_rejects_decision_verdict_outside_enum() -> None:
    """Decision schema rejects verdicts outside {accepted, overridden, escalated}."""
    with pytest.raises(ValidationError) as exc_info:
        Decision(
            proposal_id="prop-123",
            verdict="approved_by_llm",  # type: ignore[arg-type]
            reason_code="INVALID",
        )
    assert "verdict" in str(exc_info.value)


def test_shadow_evaluation_produces_triple_with_signal_abstained(tmp_path: Path) -> None:
    """(c) Shadow evaluation produces a triple with signal='abstained'."""
    db = DatabaseManager(tmp_path / "test_shadow.sqlite")
    db.migrate()

    mgr = RuleLifecycleManager(db=db)
    rule_src = """
    (rule "shadow-test-v1"
      :when (intent= "search_web")
      :plan (list (tool "search_web" :query "test"))
      :priority 5)
    """
    mgr.register_rule(rule_src)
    assert mgr.rules["shadow-test-v1"].status == "QUARANTINE"

    state = RuleState(
        transcript="search web for test",
        transcript_lower="search web for test",
        intent="search_web",
        intent_conf=0.98,
    )

    outcomes = mgr.evaluate(state, mode="shadow")
    assert len(outcomes) == 1
    assert outcomes[0].fired is True

    # Verify triple emission
    assert len(mgr.latest_triples) >= 1
    shadow_triple = mgr.latest_triples[-1]
    assert shadow_triple.proposal.rule_id == "shadow-test-v1"
    assert shadow_triple.decision.verdict == "escalated"
    assert shadow_triple.decision.reason_code == "SHADOW_EVAL"
    assert shadow_triple.outcome.signal == "abstained"
    assert shadow_triple.outcome.detail == "shadow evaluation, not executed"

    # Verify persisted in SQLite
    persisted = db.get_execution_triple(shadow_triple.triple_id)
    assert persisted is not None
    assert persisted.outcome.signal == "abstained"
    assert persisted.decision.verdict == "escalated"


def test_evidence_refs_preserved(tmp_path: Path) -> None:
    """(d) evidence_refs are preserved through shadow recording and database persistence."""
    db = DatabaseManager(tmp_path / "test_evidence.sqlite")
    db.migrate()

    mgr = RuleLifecycleManager(db=db)
    rule_src = """
    (rule "evidence-rule-v1"
      :when (intent= "read_file")
      :plan (list (tool "read_file" :rel_path "test.txt"))
      :priority 5)
    """
    mgr.register_rule(rule_src)

    state = RuleState(intent="read_file", transcript="read file test.txt")
    plan = Plan(actions=[ToolCall(tool="read_file", args={"rel_path": "test.txt"}, call_id="c1")])
    expected_refs = ["turn-trace-alpha-001", "turn-trace-alpha-002", "inducing-episode-042"]

    triple = mgr.record_shadow(
        "evidence-rule-v1",
        matched=True,
        cluster_id="cluster-ev-1",
        state_snapshot=state,
        plan_snapshot=plan,
        evidence_refs=expected_refs,
    )

    assert triple is not None
    assert triple.proposal.evidence_refs == expected_refs

    # Retrieve from DB and assert exact evidence_refs preservation
    retrieved = db.get_execution_triple(triple.triple_id)
    assert retrieved is not None
    assert retrieved.proposal.evidence_refs == expected_refs
    assert retrieved.proposal.evidence_refs == [
        "turn-trace-alpha-001",
        "turn-trace-alpha-002",
        "inducing-episode-042",
    ]


def test_active_execution_triple_emission(tmp_path: Path) -> None:
    """Real executions of ACTIVE rules emit tool_exit_zero or pydantic_valid triples."""
    db = DatabaseManager(tmp_path / "test_active.sqlite")
    db.migrate()

    mgr = RuleLifecycleManager(db=db)
    plan = Plan(actions=[ToolCall(tool="read_file", args={"rel_path": "notes.txt"}, call_id="c1")])

    t_ok = mgr.emit_execution_triple(
        rule_id="active-rule-v1",
        plan=plan,
        signal="tool_exit_zero",
        detail="exit code 0",
    )
    assert t_ok.decision.verdict == "accepted"
    assert t_ok.outcome.signal == "tool_exit_zero"

    t_valid = mgr.emit_execution_triple(
        rule_id="active-rule-v2",
        plan=plan,
        signal="pydantic_valid",
        detail="schema valid, subtool non-zero",
    )
    assert t_valid.outcome.signal == "pydantic_valid"

    # Verify both in DB
    all_triples = db.list_execution_triples(limit=10)
    assert len(all_triples) == 2
    signals = {t.outcome.signal for t in all_triples}
    assert signals == {"tool_exit_zero", "pydantic_valid"}


def test_proposal_plan_coercion() -> None:
    """Proposal.plan coerces from Plan object or list of actions."""
    tool_act = ToolCall(tool="list_dir", args={"rel_path": "."}, call_id="c1")
    say_act = Say(text="Done")
    plan_obj = Plan(actions=[tool_act, say_act], rationale="listing")

    # From Plan object
    p1 = Proposal(rule_id="r1", plan=plan_obj)
    assert len(p1.plan) == 2
    assert p1.plan[0] == tool_act
    assert p1.plan[1] == say_act

    # From list of actions
    p2 = Proposal(rule_id="r2", plan=[tool_act])
    assert len(p2.plan) == 1
    assert p2.plan[0] == tool_act
