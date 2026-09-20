"""
Tests for Rule Induction & Safe Procedural Compilation (Proposal E, D-REAS-06)
"""

import json
import time
from pathlib import Path

import pytest

from lucca.core.schemas import Risk, RuleState, ToolParameter, ToolSchema
from lucca.memory.db import DatabaseManager
from lucca.reasoning.egraph import (
    EGraph,
    anti_unify,
    synthesize_macro_from_patterns,
)
from lucca.reasoning.induction import InductionCluster, RuleInducer
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.parser import Symbol, parse_rule, to_canonical
from lucca.reasoning.smt_verifier import SMTVerifier


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
        "write_file": ToolSchema(
            name="write_file",
            description="Write file",
            parameters={
                "path": ToolParameter(type="string", description="File path"),
                "content": ToolParameter(type="string", description="Content", required=False),
            },
            risk=Risk.WRITE,
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


def test_egraph_congruence_closure():
    """Verify E-Graph term insertion, union-find merging, and congruence closure."""
    egraph = EGraph()
    # Add expressions: (+ 1 2) and (+ 1 2)
    expr1 = [Symbol("+"), 1, 2]
    expr2 = [Symbol("+"), 1, 2]
    id1 = egraph.add(expr1)
    id2 = egraph.add(expr2)
    assert id1 == id2

    # Add (+ a b) and (+ c b)
    expr3 = [Symbol("+"), Symbol("a"), Symbol("b")]
    expr4 = [Symbol("+"), Symbol("c"), Symbol("b")]
    id3 = egraph.add(expr3)
    id4 = egraph.add(expr4)
    assert id3 != id4

    # Merge a and c
    id_a = egraph.add(Symbol("a"))
    id_c = egraph.add(Symbol("c"))
    egraph.merge(id_a, id_c)
    egraph.rebuild()

    # After congruence closure, (+ a b) and (+ c b) should be in the same e-class
    assert egraph.find(id3) == egraph.find(id4)


def test_first_order_anti_unification():
    """Verify syntactic anti-unification extracts common structure and parameter holes."""
    expr_a = parse_rule("""
    (rule "test-a-v1"
      :when (and (intent= "launch_app") (entity-has? "app" "calc"))
      :plan (list (tool "launch_app" :app "calc"))
      :priority 5)
    """)
    expr_b = parse_rule("""
    (rule "test-b-v1"
      :when (and (intent= "launch_app") (entity-has? "app" "notepad"))
      :plan (list (tool "launch_app" :app "notepad"))
      :priority 5)
    """)

    gen_template, substitutions = anti_unify(expr_a.when_expr, expr_b.when_expr, var_prefix="app")
    assert isinstance(gen_template, list)
    canon = to_canonical(gen_template)
    assert 'intent= "launch_app"' in canon
    assert 'entity-has? "app"' in canon
    # The variable should be abstracted
    assert len(substitutions) == 1
    var_name = list(substitutions.keys())[0]
    assert substitutions[var_name] == ("calc", "notepad")


def test_anti_unify_many_and_macro_synthesis():
    """Verify Babble/Stitch macro synthesis generates defmacro with positive compression score."""
    p1 = parse_rule("""
    (rule "r1-v1"
      :when (and (intent= "launch_app") (entity-has? "app" "calc") (not (app-running? "calc")))
      :plan (list (say "hi"))
      :priority 1)
    """).when_expr

    p2 = parse_rule("""
    (rule "r2-v1"
      :when (and (intent= "launch_app") (entity-has? "app" "notepad") (not (app-running? "notepad")))
      :plan (list (say "hi"))
      :priority 1)
    """).when_expr

    p3 = parse_rule("""
    (rule "r3-v1"
      :when (and (intent= "launch_app") (entity-has? "app" "edge") (not (app-running? "edge")))
      :plan (list (say "hi"))
      :priority 1)
    """).when_expr

    macro_res = synthesize_macro_from_patterns(
        macro_name="when-launch-app",
        patterns=[p1, p2, p3],
        min_instances=2,
    )
    assert macro_res is not None
    macro_def, macro_sexpr = macro_res
    assert macro_def.name == "when-launch-app"
    assert len(macro_def.params) == 1
    assert "defmacro when-launch-app" in macro_sexpr
    assert 'intent= "launch_app"' in macro_sexpr


def test_smt_verifier_valid_rule(rule_engine):
    """Verify valid, contingent, safe rule passes Z3 SMT formal verification."""
    source = """
    (rule "valid-rule-v1"
      :when (and (intent= "launch_app")
                 (hour-between? 9 17)
                 (entity-has? "app" "calculator")
                 (not (app-running? "calculator")))
      :plan (list (tool "launch_app" :app "calculator"))
      :priority 5)
    """
    verifier = SMTVerifier(timeout_ms=500)
    res = verifier.verify_source(source, registered_tools=rule_engine.registered_tools)

    assert res.verified is True
    assert res.status == "VERIFIED"
    assert res.model_sample is not None
    assert res.model_sample.get("intent") == "launch_app"


def test_smt_verifier_rejects_unsat_precondition(rule_engine):
    """Verify SMT verifier rejects rules with logically contradictory / dead-code preconditions."""
    source = """
    (rule "contradictory-rule-v1"
      :when (and (intent= "launch_app")
                 (intent= "file_read"))
      :plan (list (tool "launch_app" :app "calculator"))
      :priority 5)
    """
    verifier = SMTVerifier(timeout_ms=500)
    res = verifier.verify_source(source, registered_tools=rule_engine.registered_tools)

    assert res.verified is False
    assert res.status == "UNSATISFIABLE"
    assert any("UNSATISFIABLE" in r for r in res.reasons)


def test_smt_verifier_rejects_tautology_precondition(rule_engine):
    """Verify SMT verifier rejects tautological preconditions that fire unconditionally."""
    source = """
    (rule "tautology-rule-v1"
      :when (or (intent= "launch_app")
                (not (intent= "launch_app")))
      :plan (list (tool "launch_app" :app "calculator"))
      :priority 5)
    """
    verifier = SMTVerifier(timeout_ms=500)
    res = verifier.verify_source(source, registered_tools=rule_engine.registered_tools)

    assert res.verified is False
    assert res.status == "TAUTOLOGY"
    assert any("TAUTOLOGY" in r for r in res.reasons)


def test_smt_verifier_rejects_path_traversal(rule_engine):
    """Verify SMT verifier rejects rules targeting directory traversal '..'."""
    source = """
    (rule "traversal-rule-v1"
      :when (and (intent= "file_read") (entity-has? "file" "test"))
      :plan (list (tool "read_file" :path "../../../secret.txt"))
      :priority 5)
    """
    verifier = SMTVerifier(timeout_ms=500)
    res = verifier.verify_source(source, registered_tools=rule_engine.registered_tools)

    assert res.verified is False
    assert res.status == "DEONTIC_UNSAFE"
    assert any("prohibited sequence" in r for r in res.reasons)


def test_smt_verifier_rejects_system_directory(rule_engine):
    """Verify SMT verifier rejects rules targeting OS system directories."""
    source = """
    (rule "system-dir-rule-v1"
      :when (and (intent= "file_read") (entity-has? "file" "sam"))
      :plan (list (tool "read_file" :path "C:/Windows/System32/config/SAM"))
      :priority 5)
    """
    verifier = SMTVerifier(timeout_ms=500)
    res = verifier.verify_source(source, registered_tools=rule_engine.registered_tools)

    assert res.verified is False
    assert res.status == "DEONTIC_UNSAFE"
    assert any("prohibited sequence" in r for r in res.reasons)


def test_smt_verifier_rejects_prohibited_executable_extension(rule_engine):
    """Verify SMT verifier rejects mutation tools writing dangerous executable extensions."""
    source = """
    (rule "malicious-write-rule-v1"
      :when (and (intent= "file_write") (entity-has? "file" "payload"))
      :plan (list (tool "write_file" :path "payload.exe" :content "danger"))
      :priority 5)
    """
    verifier = SMTVerifier(timeout_ms=500)
    res = verifier.verify_source(source, registered_tools=rule_engine.registered_tools)

    assert res.verified is False
    assert res.status == "DEONTIC_UNSAFE"
    assert any("prohibited executable extension" in r for r in res.reasons)


def test_smt_verifier_rejects_unknown_tool(rule_engine):
    """Verify SMT verifier rejects rules referencing unregistered tools."""
    source = """
    (rule "rogue-tool-rule-v1"
      :when (intent= "hack")
      :plan (list (tool "format_c_drive" :force #t))
      :priority 5)
    """
    verifier = SMTVerifier(timeout_ms=500)
    res = verifier.verify_source(source, registered_tools=rule_engine.registered_tools)

    assert res.verified is False
    assert res.status == "UNKNOWN_TOOL"


def test_inducer_rejects_unsafe_candidate_at_smt_gate(test_db, rule_engine):
    """
    Verify that when mined patterns attempt unsafe targets (e.g. traversal path),
    the SMT verifier gate blocks them from entering QUARANTINE.
    """
    for i in range(4):
        insert_decision(
            test_db,
            decision_id=f"dec-unsafe-{i}",
            intent="file_read",
            tool_name="read_file",
            args={"path": "../etc/passwd"},
            tool_ok=1,
        )

    inducer = RuleInducer(test_db, rule_engine, min_frequency=3)
    # The cluster is mined
    clusters = inducer.mine_patterns()
    assert len(clusters) == 1

    # But candidate induction and quarantine must reject it
    candidates = inducer.induce_and_quarantine()
    assert len(candidates) == 0
    assert len(rule_engine.rules) == 0


def test_inducer_macro_synthesis_across_clusters(test_db, rule_engine):
    """Verify RuleInducer.induce_macros() discovers recurring patterns and abstracts them."""
    # Insert 3 calculator launches
    for i in range(3):
        insert_decision(
            test_db,
            decision_id=f"dec-calc-{i}",
            intent="launch_app",
            tool_name="launch_app",
            args={"app": "calculator"},
            tool_ok=1,
        )

    # Insert 3 notepad launches
    for i in range(3):
        insert_decision(
            test_db,
            decision_id=f"dec-note-{i}",
            intent="launch_app",
            tool_name="launch_app",
            args={"app": "notepad"},
            tool_ok=1,
        )

    inducer = RuleInducer(test_db, rule_engine, min_frequency=3)
    macros = inducer.induce_macros(min_cluster_instances=2)

    assert len(macros) >= 1
    macro = macros[0]
    assert macro.name == "when-launch-app-app"
    assert "defmacro when-launch-app-app" in macro.s_expression
    assert len(macro.supporting_clusters) == 2

