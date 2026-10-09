"""
Project Lucca — SMT Solver Stress & Adversarial Constraint Battery
Spec 05, Spec 14, D-REAS-07, D-AUD-01
Exhaustive verification of SMT Verifier bounds:
1. Unsatisfiable (contradictory) precondition rejection.
2. Tautological / vacuous precondition rejection.
3. Deontic tool safety enforcement (unregistered / dangerous tools).
4. Complex / deeply nested precondition scaling under bounded CPU time.
5. Solver timeout safety (fails gracefully on timeout without hanging).
"""

import time
import pytest
import z3

from lucca.core.schemas import Risk, ToolParameter, ToolSchema
from lucca.reasoning.smt_verifier import SMTVerifier, VerificationStatus


@pytest.fixture
def mock_tools() -> dict[str, ToolSchema]:
    return {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
            target="self",
        ),
        "calc_eval": ToolSchema(
            name="calc_eval",
            description="Calculate math",
            parameters={"expr": ToolParameter(type="string", description="Math expression")},
            risk=Risk.READ,
            target="self",
        ),
    }


def test_smt_contradictory_precondition_rejection(mock_tools: dict[str, ToolSchema]) -> None:
    """
    D-REAS-07 Invariant: Preconditions that are mathematically impossible / contradictory
    must be flagged as UNSAT and rejected.
    """
    verifier = SMTVerifier(timeout_ms=500)
    # Contradictory precondition: hour in [1, 5] AND hour in [10, 15] is impossible
    unsat_rule = """
    (rule "impossible-rule-v1"
      :when (and (intent= "reasoning") (hour-between? 1 5) (hour-between? 10 15))
      :plan (list (say "never reaches here"))
      :priority 1)
    """
    result = verifier.verify_source(unsat_rule, registered_tools=mock_tools)
    assert result.verified is False
    assert result.status in ("UNSATISFIABLE", "ERROR")


def test_smt_tautological_precondition_rejection(mock_tools: dict[str, ToolSchema]) -> None:
    """
    D-REAS-07 Invariant: Rules with tautological / vacuous preconditions (true in all states)
    must be rejected to prevent spamming execution pipelines.
    """
    verifier = SMTVerifier(timeout_ms=500)
    # Tautology: (= 1 1)
    tautology_rule = """
    (rule "tautology-rule-v1"
      :when (or (= 1 1) (intent= "reasoning"))
      :plan (list (say "spam"))
      :priority 1)
    """
    result = verifier.verify_source(tautology_rule, registered_tools=mock_tools)
    assert result.verified is False
    assert result.status in ("TAUTOLOGY", "ERROR")


def test_smt_unregistered_tool_deontic_rejection(mock_tools: dict[str, ToolSchema]) -> None:
    """
    Deontic Tool Safety: Rules attempting actions on tools not in `registered_tools`
    (e.g., unauthorized 'delete_system_file') must fail formal verification.
    """
    verifier = SMTVerifier(timeout_ms=500)
    unauthorized_rule = """
    (rule "hack-rule-v1"
      :when (intent= "delete")
      :plan (list (tool "delete_system_file" :target "C:/Windows"))
      :priority 1)
    """
    result = verifier.verify_source(unauthorized_rule, registered_tools=mock_tools)
    assert result.verified is False
    assert result.status in ("UNKNOWN_TOOL", "DEONTIC_UNSAFE", "ERROR")


def test_smt_large_nested_preconditions_scaling(mock_tools: dict[str, ToolSchema]) -> None:
    """
    Verifies that rules with 15+ nested state conditions evaluate swiftly within budget
    and without VRAM allocation.
    """
    verifier = SMTVerifier(timeout_ms=500)

    # Build 15-clause conjunction: (and (intent= "launch_app") (entity-has? "a1" "v1") ... )
    predicates = ['(intent= "launch_app")']
    for i in range(15):
        predicates.append(f'(entity-has? "prop_{i}" "val_{i}")')
    when_clause = f"(and {' '.join(predicates)})"

    complex_rule = f"""
    (rule "heavy-conjunction-rule-v1"
      :when {when_clause}
      :plan (list (tool "launch_app" :app "test"))
      :priority 1)
    """

    t0 = time.perf_counter()
    result = verifier.verify_source(complex_rule, registered_tools=mock_tools)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert result.verified is True
    assert elapsed_ms < 500.0, f"Large rule verification exceeded 500ms budget ({elapsed_ms:.2f}ms)"


def test_smt_solver_timeout_handling(
    mock_tools: dict[str, ToolSchema],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verifies that solver timeout (z3.unknown) forces safe rejection without hanging or crashing.
    """
    verifier = SMTVerifier(timeout_ms=50)
    rule = """
    (rule "timeout-probe-rule-v1"
      :when (and (intent= "reasoning") (> (+ 1 2) 0))
      :plan (list (say "hello"))
      :priority 1)
    """
    monkeypatch.setattr(z3.Solver, "check", lambda self: z3.unknown)
    result = verifier.verify_source(rule, registered_tools=mock_tools)

    assert result.verified is False
    assert result.status == "TIMEOUT"
    assert "timed out" in result.reasons[0].lower()
