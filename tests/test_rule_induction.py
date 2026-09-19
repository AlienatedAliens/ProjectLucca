"""
Tests for Rule Induction & Safe Procedural Compilation (Proposal E, D-REAS-06)
"""

import json
import time
from pathlib import Path

import pytest

from lucca.core.schemas import Risk, RuleState, ToolParameter, ToolSchema
from lucca.memory.db import DatabaseManager
from lucca.reasoning.induction import InductionCluster, RuleInducer
from lucca.reasoning.lifecycle import RuleLifecycleManager


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_induction.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def rule_engine(test_db):
    tools = {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
        ),
        "read_file": ToolSchema(
            name="read_file",
            description="Read file",
            parameters={"path": ToolParameter(type="string", description="File path")},
            risk=Risk.READ,
        ),
    }
    return RuleLifecycleManager(registered_tools=tools, db=test_db)


def insert_decision(
    db: DatabaseManager,
    decision_id: str,
    intent: str,
    tool_name: str,
    args: dict[str, object],
    tool_ok: int = 1,
) -> None:
    features = {
        "intent": intent,
        "entities": {"app": [str(args.get("app", ""))] if "app" in args else []},
    }
    tool_calls = [{"tool": tool_name, "args": args, "call_id": f"call-{decision_id}"}]
    with db.get_writer() as cur:
        cur.execute(
            """
            INSERT INTO decisions(
                decision_id, trace_id, session_id, ts, features_json, action,
                probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                user_interrupted, interrupted_after_ms, counterfactual_rule_fired
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                f"trace-{decision_id}",
                "session-1",
                time.time(),
                json.dumps(features),
                "LLM",
                "{}",
                "[]",
                0,
                5000,
                "heuristic-1.0",
                "LLM",
                json.dumps(tool_calls),
                tool_ok,
                150.0,
                0,
                0.0,
                0,
            ),
        )


def test_mine_patterns_from_sqlite(test_db, rule_engine):
    """Verify recurring tool executions reaching min_frequency are mined into clusters."""
    # 4 successful calculator launches
    for i in range(4):
        insert_decision(
            test_db,
            decision_id=f"dec-calc-{i}",
            intent="launch_app",
            tool_name="launch_app",
            args={"app": "calculator"},
            tool_ok=1,
        )

    # 2 notepad launches (below threshold of 3)
    for i in range(2):
        insert_decision(
            test_db,
            decision_id=f"dec-note-{i}",
            intent="launch_app",
            tool_name="launch_app",
            args={"app": "notepad"},
            tool_ok=1,
        )

    inducer = RuleInducer(test_db, rule_engine, min_frequency=3)
    clusters = inducer.mine_patterns()

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.intent == "launch_app"
    assert cluster.tool == "launch_app"
    assert cluster.arg_val == "calculator"
    assert cluster.occurrences == 4


def test_synthesize_canonical_microscheme_rule(test_db, rule_engine):
    """Verify synthesized candidate rule has canonical syntax and passes static validation."""
    cluster = InductionCluster(
        intent="launch_app",
        tool="launch_app",
        arg_key="app",
        arg_val="calculator",
        occurrences=5,
    )
    inducer = RuleInducer(test_db, rule_engine, min_frequency=3)
    candidate = inducer.synthesize_rule(cluster, version=1)

    assert candidate is not None
    assert candidate.rule_id == "induced-launch-app-calculator-v1"
    assert candidate.intended_intent == "launch_app"
    assert 'rule "induced-launch-app-calculator-v1"' in candidate.s_expression
    assert 'tool "launch_app" :app "calculator"' in candidate.s_expression


def test_induce_and_quarantine_invariant(test_db, rule_engine):
    """D-REAS-06: Induced rules are placed strictly into QUARANTINE mode."""
    for i in range(4):
        insert_decision(
            test_db,
            decision_id=f"dec-calc-{i}",
            intent="launch_app",
            tool_name="launch_app",
            args={"app": "calculator"},
            tool_ok=1,
        )

    inducer = RuleInducer(test_db, rule_engine, min_frequency=3)
    candidates = inducer.induce_and_quarantine()

    assert len(candidates) == 1
    cand = candidates[0]

    # Verify rule is registered in engine
    assert cand.rule_id in rule_engine.rules
    managed = rule_engine.rules[cand.rule_id]

    # Hard invariant D-REAS-06: must be QUARANTINE, never ACTIVE
    assert managed.status == "QUARANTINE"

    # Evaluate in shadow mode: state matching calculator should fire
    match_state = RuleState(
        schema_version=1,
        transcript="open calculator",
        transcript_lower="open calculator",
        intent="launch_app",
        intent_conf=0.95,
        entities={"app": ["calculator"]},
        hour_local=14,
        weekday=2,
        apps_running=frozenset(),
        session_turns=1,
    )
    outcomes = rule_engine.evaluate(match_state, mode="shadow")
    fired = [o for o in outcomes if o.fired]
    assert len(fired) >= 1
    assert fired[0].rule_id == cand.rule_id


def test_no_duplicate_induction(test_db, rule_engine):
    """Running induction repeatedly does not re-register existing candidate rules."""
    for i in range(4):
        insert_decision(
            test_db,
            decision_id=f"dec-calc-{i}",
            intent="launch_app",
            tool_name="launch_app",
            args={"app": "calculator"},
            tool_ok=1,
        )

    inducer = RuleInducer(test_db, rule_engine, min_frequency=3)
    first_run = inducer.induce_and_quarantine()
    assert len(first_run) == 1

    # Second induction pass
    second_run = inducer.induce_and_quarantine()
    assert len(second_run) == 0
