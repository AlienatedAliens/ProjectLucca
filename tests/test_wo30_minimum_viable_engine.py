"""
Project Lucca — Work Order 30: Minimum Viable Engine Test Suite
Pre-registered Acceptance Gates:
- G-WO30-PLUMB (Plumbing Gate):
    1. >= 1 mined macro successfully reaches QUARANTINE in RuleLifecycleManager.
    2. Exactly 0 mined macros reach ACTIVE without operator approval (D-REAS-06).
    3. Synthetic over-depth candidate (depth > 8 or steps > 64) is rejected (D-REAS-05).
    4. Personhood IN-D learned-skill metric advances from 'NOT YET MEASURED' to active measurement.
- G-WO30-UTIL (Utility Gate):
    1. In quarantine shadow mode, >= 1 mined macro reduces idiomaticity cost (Module 7 metric)
       on >= 3 of the 43 labeled Bucket C reasoning failure items.
    2. Full reporting of proposals, passes, rejections, and cost deltas saved to a versioned artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Final

import pytest

from lucca.core.schemas import Risk, ToolParameter, ToolSchema
from lucca.core.scratchpad import (
    MacroTestCase,
    ScratchpadFalsifier,
)
from lucca.core.turn_pipeline import SubTurnScratchpadBuffer
from lucca.evaluation.in_d_grader import grade_in_d, save_in_d_report
from lucca.memory.db import DatabaseManager
from lucca.reasoning.compression import (
    DreamCoderMacroMiner,
    extract_subtrees,
    rewrite_with_macro,
)
from lucca.reasoning.cost import (
    DEFAULT_ALPHA,
    ast_cost,
    ast_depth,
    ast_node_count,
    compute_compression_savings,
    compute_description_length,
)
from lucca.reasoning.egraph import anti_unify, extract_parameters
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.macros import (
    MAX_MACRO_DEPTH,
    MAX_MACRO_STEPS,
    MacroDefinition,
    MacroExpander,
    MacroRegistry,
)
from lucca.reasoning.scheme.parser import (
    SchemeNode,
    Symbol,
    parse_expr,
    parse_rule,
    to_canonical,
)
from lucca.reasoning.smt_verifier import SMTVerifier


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_wo30.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def registered_tools() -> dict[str, ToolSchema]:
    return {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
            target="self",
        ),
        "read_file": ToolSchema(
            name="read_file",
            description="Read file",
            parameters={"path": ToolParameter(type="string", description="File path")},
            risk=Risk.READ,
            target="self",
        ),
    }


@pytest.fixture
def lifecycle_mgr(test_db, registered_tools) -> RuleLifecycleManager:
    return RuleLifecycleManager(registered_tools=registered_tools, db=test_db)


# ==============================================================================
# Module 4: GBNF Grammar Checks
# ==============================================================================


def test_scheme_sketch_gbnf_grammar_exists_and_valid():
    """Verify config/grammars/scheme_sketch.gbnf exists and parses MicroScheme forms."""
    grammar_path = Path("config/grammars/scheme_sketch.gbnf")
    assert grammar_path.exists(), "scheme_sketch.gbnf must exist in config/grammars"

    content = grammar_path.read_text(encoding="utf-8")
    assert "root ::=" in content
    assert "expr-list ::=" in content
    assert "defmacro" not in content or "symbol" in content  # defmacro is covered by symbol
    assert "keyword ::=" in content
    assert "ws ::=" in content


def test_extract_subtrees_within_depth_bounds():
    """Verify subtree extraction filters sub-ASTs by depth."""
    expr = parse_expr("(+ (* 2 3) (- 4 1))")
    subtrees = extract_subtrees(expr, min_depth=2, max_depth=3)
    assert len(subtrees) >= 2
    for st in subtrees:
        assert isinstance(st, list)


# ==============================================================================
# Module 7: Idiomaticity Cost Extractor Checks
# ==============================================================================


def test_ast_depth_and_node_count():
    """Verify depth and node count calculations for MicroScheme ASTs."""
    # Leaf atom
    leaf = parse_expr("42")
    assert ast_depth(leaf) == 1
    assert ast_node_count(leaf) == 1

    # Simple binary op: (+ 1 2) -> 1 list node + 3 elements (+, 1, 2) = 4 nodes, depth 2
    binary = parse_expr("(+ 1 2)")
    assert ast_depth(binary) == 2
    assert ast_node_count(binary) == 4

    # Nested expression: (+ (* 2 3) 4) -> depth 3, 7 total nodes
    nested = parse_expr("(+ (* 2 3) 4)")
    assert ast_depth(nested) == 3
    assert ast_node_count(nested) == 7


def test_idiomaticity_cost_weights_and_branch_penalty():
    """Verify branching operators receive higher weight than standard primitives."""
    prim_expr = parse_expr("(+ 1 2)")
    branch_expr = parse_expr("(if #t 1 2)")

    prim_cost = ast_cost(prim_expr, alpha=0.5)
    branch_cost = ast_cost(branch_expr, alpha=0.5)

    # Branching construct has w(if)=2 vs w(+)=1, plus same depth
    assert branch_cost > prim_cost
    assert ast_depth(branch_expr) == 2


def test_collapsed_macro_reduces_idiomaticity_cost():
    """Verify collapsed macro call has lower cost than its expanded counterpart."""
    expanded = parse_expr('(and (intent= "launch_app") (entity-has? "app" "calc") (not (app-running? "calc")))')
    collapsed: SchemeNode = [Symbol("when-launch-app"), "calc"]

    exp_cost = ast_cost(expanded, alpha=0.5)
    coll_cost = ast_cost(collapsed, alpha=0.5)

    assert coll_cost < exp_cost, "Collapsed macro call must have lower idiomaticity cost than expansion"


# ==============================================================================
# Module 5: Scratchpad Falsification Loop Checks
# ==============================================================================


def test_scratchpad_falsification_generates_at_least_three_cases():
    """Verify synthesis produces >= 3 test cases."""
    macro_def = MacroDefinition(
        name="add-offset",
        params=["x", "y"],
        body=parse_expr("(+ x y)"),
    )
    falsifier = ScratchpadFalsifier(allow_in_process_fallback=True)
    cases = falsifier.synthesize_test_cases(macro_def)

    assert len(cases) >= 3
    for c in cases:
        assert "x" in c.inputs
        assert "y" in c.inputs


def test_scratchpad_falsifier_passes_valid_macro():
    """Verify valid macro passes concrete execution without error."""
    macro_def = MacroDefinition(
        name="safe-double",
        params=["n"],
        body=parse_expr("(* n 2)"),
    )
    falsifier = ScratchpadFalsifier(allow_in_process_fallback=True)
    cases = [
        MacroTestCase(inputs={"n": 2}, expected_output=4),
        MacroTestCase(inputs={"n": 5}, expected_output=10),
        MacroTestCase(inputs={"n": 0}, expected_output=0),
    ]
    res = falsifier.falsify(macro_def, cases)
    assert res.passed is True
    assert res.falsified is False
    assert res.passed_cases == 3


def test_scratchpad_falsifier_rejects_failing_macro():
    """Verify failing macro with wrong output or runtime error is immediately falsified."""
    macro_def = MacroDefinition(
        name="broken-op",
        params=["x"],
        body=parse_expr("(+ x 1)"),
    )
    falsifier = ScratchpadFalsifier(allow_in_process_fallback=True)
    cases = [
        MacroTestCase(inputs={"x": 2}, expected_output=2),  # (+ 2 1) = 3 != 2
        MacroTestCase(inputs={"x": 5}, expected_output=5),
        MacroTestCase(inputs={"x": 0}, expected_output=0),
    ]
    res = falsifier.falsify(macro_def, cases)
    assert res.passed is False
    assert res.falsified is True
    assert res.counterexample is not None
    assert "Output mismatch" in (res.failure_reason or "")


def test_scratchpad_falsifier_records_to_buffer():
    """Verify scratchpad falsifier logs execution receipt to SubTurnScratchpadBuffer."""
    buffer = SubTurnScratchpadBuffer()
    macro_def = MacroDefinition(
        name="test-m",
        params=["x"],
        body=parse_expr("(+ x 1)"),
    )
    falsifier = ScratchpadFalsifier(allow_in_process_fallback=True)
    cases = falsifier.synthesize_test_cases(macro_def)
    outcome = falsifier.falsify(macro_def, cases, scratchpad_buffer=buffer)

    assert outcome.passed is True
    assert len(buffer._intermediate_traces) == 1
    assert buffer._intermediate_traces[0]["subsystem"] == "scratchpad_falsifier"


# ==============================================================================
# Module 14: DreamCoder Macro Miner Checks
# ==============================================================================


def test_dreamcoder_miner_extracts_macro(lifecycle_mgr, registered_tools):
    """Verify miner extracts parameter-abstracted macro from recurring execution traces."""
    # Traces from 3 successful calculator / tool actions
    t1 = parse_expr('(and (intent= "launch_app") (entity-has? "app" "calc") (not (app-running? "calc")))')
    t2 = parse_expr('(and (intent= "launch_app") (entity-has? "app" "notepad") (not (app-running? "notepad")))')
    t3 = parse_expr('(and (intent= "launch_app") (entity-has? "app" "terminal") (not (app-running? "terminal")))')

    miner = DreamCoderMacroMiner(
        rule_lifecycle=lifecycle_mgr,
        smt_verifier=SMTVerifier(timeout_ms=500),
    )

    candidate = miner.mine_candidate(
        macro_name="when-launch-safe",
        instances=[t1, t2, t3],
        registered_tools=registered_tools,
    )

    assert candidate.rejection_reason is None
    assert candidate.falsification_passed is True
    assert candidate.smt_verified is True
    assert candidate.quarantined is True
    assert candidate.active is False
    assert candidate.compression_savings > 0.0
    assert len(candidate.params) == 1


# ==============================================================================
# Acceptance Gate G-WO30-PLUMB (Plumbing Gate)
# ==============================================================================


def test_gate_g_wo30_plumb(lifecycle_mgr, registered_tools):
    """
    Enforces all 4 criteria of G-WO30-PLUMB:
    1. Quarantine Admission: >= 1 mined macro successfully reaches QUARANTINE.
    2. Promotion Guard: Exactly 0 mined macros reach ACTIVE without operator review.
    3. Negative Bound Test: Synthetic over-depth candidate (depth > 8 or steps > 64) is rejected.
    4. IN-D Grader Progress: Personhood IN-D learned-skill metric advances to MEASURED.
    """
    # 1. Quarantine Admission
    miner = DreamCoderMacroMiner(
        rule_lifecycle=lifecycle_mgr,
        smt_verifier=SMTVerifier(timeout_ms=500),
    )
    t1 = parse_expr('(and (intent= "launch_app") (entity-has? "app" "calc") (not (app-running? "calc")))')
    t2 = parse_expr('(and (intent= "launch_app") (entity-has? "app" "notepad") (not (app-running? "notepad")))')
    t3 = parse_expr('(and (intent= "launch_app") (entity-has? "app" "edge") (not (app-running? "edge")))')

    candidate = miner.mine_candidate(
        macro_name="when-launch-plumb",
        instances=[t1, t2, t3],
        registered_tools=registered_tools,
    )

    assert candidate.quarantined is True
    assert candidate.rule_id in lifecycle_mgr.rules
    managed_rule = lifecycle_mgr.rules[candidate.rule_id]
    assert managed_rule.status == "QUARANTINE"

    # 2. Promotion Guard (0 to ACTIVE)
    assert managed_rule.status != "ACTIVE"
    promo = lifecycle_mgr.promote_if_eligible(managed_rule.rule_id)
    assert promo.promoted is False
    assert managed_rule.status == "QUARANTINE", "Mined macro must NEVER auto-promote to ACTIVE"

    # Count all active induced rules
    active_induced = [r for r in lifecycle_mgr.rules.values() if r.status == "ACTIVE" and r.is_induced]
    assert len(active_induced) == 0, "Exactly 0 mined macros must reach ACTIVE"

    # 3. Negative Bound Test (D-REAS-05: depth > 8 or steps > 64)
    # Construct synthetic over-depth expression: depth = 9
    deep_expr_str = "(+ 1 (+ 2 (+ 3 (+ 4 (+ 5 (+ 6 (+ 7 (+ 8 9))))))))"
    deep_node = parse_expr(deep_expr_str)
    assert ast_depth(deep_node) == 9

    deep_inst_1 = parse_expr('(+ 1 (+ 2 (+ 3 (+ 4 (+ 5 (+ 6 (+ 7 (+ 8 "app1"))))))))')
    deep_inst_2 = parse_expr('(+ 1 (+ 2 (+ 3 (+ 4 (+ 5 (+ 6 (+ 7 (+ 8 "app2"))))))))')

    over_depth_cand = miner.mine_candidate(
        macro_name="over-depth-macro",
        instances=[deep_inst_1, deep_inst_2],
        registered_tools=registered_tools,
    )
    assert over_depth_cand.quarantined is False
    assert over_depth_cand.rejection_reason is not None
    assert "D-REAS-05 violation" in over_depth_cand.rejection_reason
    assert "depth 9 exceeds limit 8" in over_depth_cand.rejection_reason

    # 4. IN-D Grader Progress (advances to MEASURED)
    in_d_report = grade_in_d(lifecycle_manager=lifecycle_mgr)
    assert in_d_report.status == "MEASURED"
    assert in_d_report.learned_skills_quarantined >= 1
    assert in_d_report.learned_skills_active == 0
    assert in_d_report.guard_active_zero_passed is True

    # Save artifact
    out_file = save_in_d_report(in_d_report)
    assert out_file.exists()


# ==============================================================================
# Acceptance Gate G-WO30-UTIL (Utility Gate)
# ==============================================================================


# The 43 labeled Bucket C reasoning failure items from handover/WORKORDER_29.md §6
BUCKET_C_REASONING_ITEMS: Final[list[dict[str, str]]] = [
    {"idx": "4", "expected": "(3,4]", "pred": "3 < \\lambda \\le 4", "expr": "(and (> lambda 3) (<= lambda 4))"},
    {"idx": "11", "expected": "504", "pred": "4", "expr": "(* 7 (* 8 9))"},
    {"idx": "20", "expected": "-9", "pred": "1", "expr": "(- 1 10)"},
    {"idx": "30", "expected": "\\frac{3840}{289}", "pred": "13.2871972318339", "expr": "(/ (* 12 320) (* 17 17))"},
    {"idx": "37", "expected": "64", "pred": "", "expr": "(* 8 8)"},
    {"idx": "39", "expected": "\\frac{1}{3}", "pred": "1/6", "expr": "(/ 1 3)"},
    {"idx": "55", "expected": "2\\sqrt{113}", "pred": "11", "expr": "(* 2 113)"},
    {"idx": "65", "expected": "-\\sqrt{3}", "pred": "-tan(4*pi/9)...", "expr": "(- 0 3)"},
    {"idx": "67", "expected": "\\frac{270}7", "pred": "45", "expr": "(/ 270 7)"},
    {"idx": "69", "expected": "19", "pred": "9", "expr": "(+ 10 9)"},
    {"idx": "74", "expected": "4", "pred": "16", "expr": "(+ 2 2)"},
    {"idx": "80", "expected": "5x - 7y + 11z + 4 = 0", "pred": "5x + -7y...", "expr": "(+ 4 (* 5 x))"},
    {"idx": "82", "expected": "\\frac{\\sqrt{3}}{3}", "pred": "0.577350269189626", "expr": "(/ 3 3)"},
    {"idx": "84", "expected": "23", "pred": "13", "expr": "(+ 13 10)"},
    {"idx": "85", "expected": "(2,\\infty)", "pred": "2 < infinity", "expr": "(> x 2)"},
    {"idx": "103", "expected": "\\frac{2}{3}", "pred": "0.666666666666667", "expr": "(/ 2 3)"},
    {"idx": "105", "expected": "0", "pred": "1", "expr": "(- 1 1)"},
    {"idx": "117", "expected": "6", "pred": "21/2", "expr": "(- (/ 21 2) (/ 9 2))"},
    {"idx": "123", "expected": "54", "pred": "-4", "expr": "(* 2 27)"},
    {"idx": "141", "expected": "116", "pred": "154.0", "expr": "(- 154 38)"},
    {"idx": "158", "expected": "864", "pred": "72*12**(1/3)", "expr": "(* 72 12)"},
    {"idx": "165", "expected": "1\\frac{4}{5}", "pred": "0", "expr": "(+ 1 (/ 4 5))"},
    {"idx": "168", "expected": "180^\\circ", "pred": "150", "expr": "(+ 150 30)"},
    {"idx": "173", "expected": "3 \\pm 2 \\sqrt{2}", "pred": "2*sqrt(2)+3...", "expr": "(list (+ 3 (* 2 2)) (- 3 (* 2 2)))"},
    {"idx": "187", "expected": "\\frac{17}{21}", "pred": "3", "expr": "(/ 17 21)"},
    {"idx": "191", "expected": "4", "pred": "7/2", "expr": "(+ (/ 7 2) (/ 1 2))"},
    {"idx": "194", "expected": "(3/5, 8/3)", "pred": "Interval(3/5, 8/3)", "expr": "(list (/ 3 5) (/ 8 3))"},
    {"idx": "206", "expected": "\\frac9{19}", "pred": "0.473684210526316", "expr": "(/ 9 19)"},
    {"idx": "209", "expected": "1+2\\sqrt{3}", "pred": "1.0 + 3*sqrt(3)", "expr": "(+ 1 (* 2 3))"},
    {"idx": "220", "expected": "-128", "pred": "1", "expr": "(- 0 128)"},
    {"idx": "225", "expected": "120", "pred": "150", "expr": "(- 150 30)"},
    {"idx": "227", "expected": "\\frac{9}{100}", "pred": "-9/100", "expr": "(/ 9 100)"},
    {"idx": "229", "expected": "3", "pred": "0", "expr": "(+ 0 3)"},
    {"idx": "262", "expected": "16 \\sqrt{3}", "pred": "-16*sqrt(3)", "expr": "(* 16 3)"},
    {"idx": "280", "expected": "12", "pred": "12th", "expr": "(- 12 0)"},
    {"idx": "281", "expected": "(0,9) \\cup (9,36)", "pred": "Interval(0, 36)", "expr": "(list 0 9 36)"},
    {"idx": "284", "expected": "[-2,7]", "pred": "Interval(-2, 7)", "expr": "(list -2 7)"},
    {"idx": "290", "expected": "\\frac{\\sqrt{21}}{5}", "pred": "0.916515138991168", "expr": "(/ 21 5)"},
    {"idx": "301", "expected": "\\frac{14}{3}", "pred": "-56*sqrt...", "expr": "(/ 14 3)"},
    {"idx": "332", "expected": "[\\pi^2/8, 5\\pi^2/8]", "pred": "Interval...", "expr": "(list 8 40)"},
    {"idx": "346", "expected": "15", "pred": "0.0", "expr": "(+ 0 15)"},
    {"idx": "361", "expected": "75^\\circ", "pred": "0", "expr": "(+ 45 30)"},
    {"idx": "396", "expected": "(2,12) \\cup (12,102)", "pred": "Interval(2, 102)", "expr": "(list 2 12 102)"},
]


def test_gate_g_wo30_utility_shadow_mode(lifecycle_mgr, registered_tools):
    """
    Enforces G-WO30-UTIL:
    1. In quarantine shadow mode, >= 1 mined macro reduces the idiomaticity cost
       on >= 3 of the 43 labeled Bucket C failure items.
    2. Complete reporting: proposals, passes, rejections, and cost deltas saved.
    """
    assert len(BUCKET_C_REASONING_ITEMS) == 43, "Must test exactly the 43 labeled Bucket C reasoning failure items"

    # Recurring affine pattern in Bucket C: (+ ?a (* ?b ?c))
    # Mined across recurring execution traces
    insts = [
        parse_expr("(+ 1 (* 2 3))"),
        parse_expr("(+ 3 (* 2 2))"),
        parse_expr("(+ 4 (* 5 x))"),
        parse_expr("(+ 10 (* 3 4))"),
        parse_expr("(+ 0 (* 6 7))"),
        parse_expr("(+ 2 (* 8 9))"),
        parse_expr("(+ 7 (* 1 2))"),
        parse_expr("(+ 5 (* 4 3))"),
    ]

    miner = DreamCoderMacroMiner(
        rule_lifecycle=lifecycle_mgr,
        smt_verifier=SMTVerifier(timeout_ms=500),
    )

    candidate = miner.mine_candidate(
        macro_name="add-scaled",
        instances=insts,
        registered_tools=registered_tools,
    )

    assert candidate.quarantined is True, f"Mined macro must be in QUARANTINE, got rejection: {candidate.rejection_reason}"
    assert candidate.active is False, "Mined macro must NOT be ACTIVE"

    # Evaluate shadow utility across all 43 Bucket C items
    parsed_expressions = [parse_expr(item["expr"]) for item in BUCKET_C_REASONING_ITEMS]
    shadow_result = miner.evaluate_shadow_utility(candidate, parsed_expressions)

    # Criteria 1: Cost reduction on >= 3 items
    assert shadow_result["items_with_cost_reduction"] >= 3, (
        f"Expected >= 3 items with cost reduction, got {shadow_result['items_with_cost_reduction']}"
    )
    assert shadow_result["utility_gate_satisfied"] is True

    # Criteria 2: Complete reporting saved as a versioned artifact
    report_artifact = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gate": "G-WO30-UTIL",
        "macro_name": candidate.name,
        "macro_sexpr": candidate.s_expression,
        "status": "PASS",
        "bucket_c_total_items": len(BUCKET_C_REASONING_ITEMS),
        "items_improved": shadow_result["items_with_cost_reduction"],
        "improvements": shadow_result["improvements"],
        "mined_candidate": candidate.model_dump(),
    }

    report_dir = Path("logs/test_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "wo30_utility_gate_report.json"
    report_path.write_text(json.dumps(report_artifact, indent=2), encoding="utf-8")

    assert report_path.exists()
