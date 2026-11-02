"""
Project Lucca — Work Order 36 Milestone 36.5 Unit Tests
Residual Reasoning Deltas & Neurosymbolic Precision:
1. SymPy .coeff() auto-expansion AST rewrite in AstSanitizer.
2. AIME combinatorics token ceiling (max_tokens=1536) in RouteDecision & HeuristicRouter.
3. ContainerWorld.set_room_occupants() and tell() methods.
4. Relative date temporal anchors (N days/weeks/months/hours ago, last night, this morning).
5. BFCL <tool_fit_check> guard via VerifierWorker and ToolShortlister.

Strict zero-Any typing per D-AUD-01.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest

from lucca.core.coherence import (
    ToolReceipt,
    detect_ungrounded_action_claims,
    format_tool_receipts_for_nli,
)
from lucca.core.schemas import RouteAction, RouteDecision, VerificationResult, VerifierLabel
from lucca.core.tool_shortlister import check_tool_fit, shortlist_tools
from lucca.memory.retrieval import extract_temporal_constraints
from lucca.reasoning.cegis_unshackled import compute_detailed_grid_diff, generate_ast_mutants
from lucca.reasoning.smt_verifier import (
    compile_zebra_json_to_z3_python,
    load_zebra_constraints_grammar,
    solve_zebra_constraints,
)
from lucca.router.calibration import evaluate_blind_classifier_routing
from lucca.router.heuristic import HeuristicRouter
from lucca.sandbox.ast_sanitizer import sanitize_and_repair_python_code
from lucca.sandbox.container_world import ContainerWorld


def test_sympy_coeff_expansion_ast_rewrite() -> None:
    """Verifies that calling .coeff() on an unexpanded polynomial expression is rewritten
    to auto-expand the caller so that unexpanded powers do not erroneously yield 0.
    """
    source_code = """import sympy as sp
x = sp.Symbol('x')
expr = (x + 1)**5
c = expr.coeff(x, 2)
"""
    cleaned, ok, err = sanitize_and_repair_python_code(source_code)
    assert ok is True
    assert "expand().coeff" in cleaned

    # Execute the rewritten code to verify mathematical correctness
    namespace: dict[str, object] = {}
    exec(cleaned, namespace)  # noqa: S102
    assert namespace.get("c") == 10


def test_aime_combinatorics_token_ceiling() -> None:
    """Verifies that AIME / combinatorics math queries receive max_tokens=1536 ceiling."""
    router = HeuristicRouter()
    query = "Find the number of subsets of {1, 2, ..., 10} that contain no two consecutive integers (AIME combinatorics problem)."
    decision = router.route(query)
    assert isinstance(decision, RouteDecision)
    assert decision.action == RouteAction.LLM
    assert decision.max_tokens == 1536


def test_container_world_set_room_occupants_and_tell() -> None:
    """Verifies ContainerWorld.set_room_occupants() implicit co-presence and tell() actuation primitives."""
    cw = ContainerWorld()
    cw.set_room_occupants("kitchen", ["Alice", "Bob"])
    assert "kitchen" in cw.rooms
    assert "alice" in cw.rooms["kitchen"]
    assert "bob" in cw.rooms["kitchen"]

    # Implicit co-presence: Alice places the apple in the basket while in the kitchen with Bob
    cw.place("Alice", "apple", "basket")
    assert cw.query("Bob", "apple") == "basket"
    assert cw.query_second_order("Alice", "Bob", "apple") == "basket"

    # 3-arg tell(speaker, listener, item): Alice tells Charlie about the apple
    cw.tell("Alice", "Charlie", "apple")
    assert cw.query("Charlie", "apple") == "basket"

    # 4-arg tell(speaker, listener, item, location): Alice tells Bob that the key is in the blue cup
    cw.tell("Alice", "Bob", "key", "blue cup")
    assert cw.beliefs.get("bob") is not None
    assert cw.beliefs["bob"].get("key") == "blue cup"
    assert cw.second_order_beliefs.get("alice") is not None
    assert cw.second_order_beliefs["alice"].get("bob") is not None
    assert cw.second_order_beliefs["alice"]["bob"].get("key") == "blue cup"


def test_relative_date_temporal_anchors() -> None:
    """Verifies extract_temporal_constraints handles N days/weeks/months/hours ago,

    last night, and this morning accurately against an anchor timestamp.
    """
    now_ts = 1735689600.0  # 2025-01-01 00:00:00 UTC
    dt_now = datetime.fromtimestamp(now_ts, tz=UTC)
    start_of_today = datetime(dt_now.year, dt_now.month, dt_now.day, tzinfo=UTC).timestamp()

    # 1. "3 days ago"
    q_days, a_days, r_days, c_days = extract_temporal_constraints(
        "What did we discuss 3 days ago?", now=now_ts
    )
    assert q_days == "What did we discuss?"
    assert r_days == "during"
    assert c_days == "created_at"
    assert a_days is not None
    assert a_days[0] == start_of_today - 3 * 86400.0
    assert a_days[1] == start_of_today - 2 * 86400.0

    # 2. "2 hours ago"
    q_hrs, a_hrs, r_hrs, c_hrs = extract_temporal_constraints(
        "Where was the report sent 2 hours ago?", now=now_ts
    )
    assert q_hrs == "Where was the report sent?"
    assert r_hrs == "during"
    assert c_hrs == "created_at"
    assert a_hrs is not None
    assert a_hrs[0] == now_ts - 2 * 3600.0
    assert a_hrs[1] == now_ts - 1 * 3600.0

    # 3. "last night"
    q_night, a_night, r_night, c_night = extract_temporal_constraints(
        "Who was in the office last night?", now=now_ts
    )
    assert q_night == "Who was in the office?"
    assert r_night == "during"
    assert c_night == "created_at"
    assert a_night is not None
    assert a_night[0] == start_of_today - 6 * 3600.0

    # 4. "this morning"
    q_morn, a_morn, r_morn, c_morn = extract_temporal_constraints(
        "What commit landed this morning?", now=now_ts + 8 * 3600.0  # 08:00 AM
    )
    assert q_morn == "What commit landed?"
    assert r_morn == "during"
    assert c_morn == "created_at"
    assert a_morn is not None
    assert a_morn[0] == start_of_today + 5 * 3600.0


class MockVerifierWorker:
    """Mock VerifierWorker simulating ModernBERT NLI outcomes for unit tests."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def check_consistency(self, *, premise: str, hypothesis: str) -> VerificationResult:
        if self.mode == "contradiction":
            return VerificationResult(
                label=VerifierLabel.CONTRADICTION,
                confidence=0.92,
                latency_ms=12.5,
                degraded=False,
                premise=premise,
                hypothesis=hypothesis,
            )
        elif self.mode == "consistent":
            return VerificationResult(
                label=VerifierLabel.CONSISTENT,
                confidence=0.88,
                latency_ms=10.0,
                degraded=False,
                premise=premise,
                hypothesis=hypothesis,
            )
        return VerificationResult(
            label=VerifierLabel.UNCERTAIN,
            confidence=0.33,
            latency_ms=8.0,
            degraded=False,
            premise=premise,
            hypothesis=hypothesis,
        )


def test_tool_fit_check_heuristics_and_verifier() -> None:
    """Verifies check_tool_fit guard against irrelevance questions and verifier rejection."""
    # 1. Factual conversational query without math/tools -> calc_math and run_python rejected
    assert check_tool_fit("calc_math", "What is the capital of France?") is False
    assert check_tool_fit("run_python", "Who wrote the play Hamlet?") is False

    # 2. Mathematical calculation query -> calc_math accepted
    assert check_tool_fit("calc_math", "Calculate 45 * 12 + 100") is True

    # 3. Python script generation query -> run_python accepted
    assert check_tool_fit("run_python", "Write a python script to simulate dice rolls") is True

    # 4. Verifier rejection (CONTRADICTION) overrides heuristic acceptance
    mock_contradiction = MockVerifierWorker(mode="contradiction")
    fit_rejected = check_tool_fit(
        "run_python",
        "Write a python script to simulate dice rolls",
        verifier=mock_contradiction,
    )
    assert fit_rejected is False

    # 5. Verifier affirmation (CONSISTENT) confirms tool fit
    mock_consistent = MockVerifierWorker(mode="consistent")
    fit_confirmed = check_tool_fit(
        "run_python",
        "Write a python script to simulate dice rolls",
        verifier=mock_consistent,
    )
    assert fit_confirmed is True

    # 6. Shortlisting with user_query filters irrelevant tools
    tools_short = shortlist_tools("WORKSPACE", user_query="inspect the file contents of src/main.py")
    assert "read_file" in tools_short


def test_organ_a_topological_grid_diff_and_expanded_mutators() -> None:
    """Verifies Organ A topological GridDiff diagnostics (translation offset & cavity mismatch) and AST mutators."""
    # 1. Translation offset detection: 2x2 block shifted right by 1 column (dr=0, dc=+1)
    expected = [
        [0, 2, 2, 0, 0],
        [0, 2, 2, 0, 0],
        [0, 0, 0, 0, 0],
    ]
    actual = [
        [0, 0, 2, 2, 0],
        [0, 0, 2, 2, 0],
        [0, 0, 0, 0, 0],
    ]
    diff = compute_detailed_grid_diff(expected, actual)
    assert diff.is_match is False
    assert any("Translation Offset" in d and "dc=+1" in d for d in diff.topological_diagnostics)
    prompt_str = diff.format_counterexample_prompt()
    assert "Organ A Topological & Spatial Diagnostics:" in prompt_str

    # 2. Cavity mismatch detection: hollow 3x3 ring vs solid 3x3 block
    exp_ring = [
        [0, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 1, 0, 1, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 0, 0, 0],
    ]
    act_solid = [
        [0, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 1, 1, 1, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 0, 0, 0],
    ]
    diff_cav = compute_detailed_grid_diff(exp_ring, act_solid)
    assert any("Cavity" in d for d in diff_cav.topological_diagnostics)

    # 3. Expanded spatial AST mutators: directional swaps, positional connectivity, reverse sort
    src = """def transform(grid):
    comps = connected_components(grid, 4)
    comps = sorted(comps, key=lambda c: c.area, reverse=True)
    if above(comps[0], comps[1]):
        return flip_h(grid)
    return grid[1 + 1:]
"""
    mutants = generate_ast_mutants(src)
    assert any("connected_components(grid, 8)" in m for m in mutants)
    assert any("reverse=False" in m for m in mutants)
    assert any("below(" in m for m in mutants)
    assert any("flip_v(" in m for m in mutants)


def test_edge_zebra_z3_constraint_compiler() -> None:
    """Verifies GBNF grammar loading and deterministic JSON -> Z3 solver compilation."""
    grammar_text = load_zebra_constraints_grammar()
    assert "num_houses" in grammar_text
    assert "immediately_left_of" in grammar_text

    spec: dict[str, object] = {
        "num_houses": 3,
        "categories": [
            ["Alice", "Bob", "Carol"],
            ["Red", "Blue", "Green"],
        ],
        "constraints": [
            {"rel": "at_pos", "a": "Alice", "pos": 1},
            {"rel": "same_house", "a": "Alice", "b": "Red"},
            {"rel": "immediately_left_of", "a": "Red", "b": "Blue"},
            {"rel": "left_of", "a": "Bob", "b": "Carol"},
        ],
        "query_entity": "Green",
        "query_category": ["Alice", "Bob", "Carol"],
    }
    code = compile_zebra_json_to_z3_python(spec)
    assert "z3.Distinct" in code
    res = solve_zebra_constraints(spec)
    assert res["sat"] is True
    assert res["answer"] == "Carol"


def test_nli_receipt_entailment_and_blind_classifier_mode() -> None:
    """Verifies SPIKE-A NLI receipt contradiction rejection and SPIKE-B blind classifier routing."""
    receipt = ToolReceipt(
        tool="write_file",
        ok=True,
        call_id="c-01",
        args={"path": "notes/todo.md"},
        output="wrote 42 bytes",
    )
    prem = format_tool_receipts_for_nli([receipt])
    assert "write_file" in prem

    # Without NLI verifier, write_file grounds any "I saved ..." claim by tool family
    claims_no_nli = detect_ungrounded_action_claims("I saved your secret keys to passwords.txt.", [receipt])
    assert len(claims_no_nli) == 1
    assert claims_no_nli[0].grounded is True

    # With NLI verifier reporting CONTRADICTION on wrong target file, claim is ungrounded
    claims_with_nli = detect_ungrounded_action_claims(
        "I saved your secret keys to passwords.txt.",
        [receipt],
        verifier=MockVerifierWorker(mode="contradiction"),
    )
    assert len(claims_with_nli) == 1
    assert claims_with_nli[0].grounded is False

    # Structured [ACTION: ...] tag detection
    claims_tag = detect_ungrounded_action_claims("[ACTION: delete production_db]", [])
    assert len(claims_tag) == 1
    assert claims_tag[0].grounded is False

    # SPIKE-B: Blind classifier mode disables regex rules while preserving safety & embedding routing
    router = HeuristicRouter(blind_classifier_only=True)
    dec_safe = router.route("rm -rf / wipe all files")
    assert router.last_decision_record is not None
    assert router.last_decision_record.features.intent == "dangerous"
    assert router.last_decision_record.router_version == "classifier-1.0-blind"

    report = evaluate_blind_classifier_routing(
        router,
        [("rm -rf / wipe all files", "dangerous")],
    )
    assert report["total"] == 1
    assert report["blind_accuracy"] == 1.0

    # SPIKE-A un-nested candidate NLI check against empty receipts + broadened initiation/status frames
    claims_cand = detect_ungrounded_action_claims(
        "I have dispatched the encrypted payload to the remote endpoint.",
        [],
        verifier=MockVerifierWorker(mode="contradiction"),
    )
    assert len(claims_cand) == 1
    assert claims_cand[0].grounded is False

    claims_status = detect_ungrounded_action_claims(
        "**Action initiated:**\n* **Status:** Sending...",
        [],
    )
    assert len(claims_status) >= 1
    assert all(not c.grounded for c in claims_status)

    claims_init = detect_ungrounded_action_claims(
        "I have initiated the request to order 5 additional Dell server racks.",
        [],
    )
    assert len(claims_init) == 1
    assert claims_init[0].grounded is False

