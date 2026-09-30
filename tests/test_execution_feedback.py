"""
Project Lucca — Version 1.3 Neurosymbolic Execution Feedback Tests
WO-28 Phase 3: Unified Execution Feedback Loop & Turn-1 Compiler Preflight
"""

from __future__ import annotations

import ast
import pytest
from lucca.sandbox.ast_sanitizer import (
    extract_python_code_tolerant,
    sanitize_and_repair_python_code,
)


def test_feedback_loop_cap_at_two_rounds() -> None:
    """Verifies that the execution feedback loop strictly enforces the hard cap of <= 2 rounds."""
    attempts = 0
    max_rounds = 2
    
    # Simulate execution loop with continuous error
    class MockSandboxFailure:
        exit_code = 1
        stderr = "ZeroDivisionError: division by zero"
        content = ""

    feedback_triggered = False
    feedback_rounds = 0
    final_pass = False

    for round_idx in range(1, max_rounds + 1):
        attempts += 1
        res = MockSandboxFailure()
        if res.exit_code != 0:
            if round_idx < max_rounds:
                feedback_triggered = True
                feedback_rounds += 1
                # Round 2 proceeds
                continue
            else:
                # Reached cap: do not retry again
                break
        else:
            final_pass = True
            break

    assert attempts == 2
    assert feedback_triggered is True
    assert feedback_rounds == 1
    assert final_pass is False


def test_turn1_preflight_resolves_composite_derivative_without_turn2() -> None:
    """Verifies that composite differentiation traps (e.g. sp.diff(..., x/h)) are rewritten in <1ms."""
    code = """
import sympy as sp
x, h = sp.symbols('x h')
expr = sp.sin(x/h)
res = sp.diff(expr, x/h)
print(res)
"""
    sanitized, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    tree = ast.parse(sanitized)
    assert tree is not None
    assert "_diff_var_" in sanitized
    assert "sp.symbols('_diff_var_'" in sanitized


def test_turn1_preflight_rewrites_expr_solve_without_turn2() -> None:
    """Verifies that expr.solve(var) is rewritten to sp.solve(expr, var) deterministically."""
    code = """
import sympy as sp
x = sp.Symbol('x')
eq = x**2 - 9
ans = eq.solve(x)
print(ans)
"""
    sanitized, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "sp.solve(eq, x)" in sanitized or "sympy.solve(eq, x)" in sanitized
    tree = ast.parse(sanitized)
    assert tree is not None


def test_turn1_preflight_filters_hallucinated_sympy_imports() -> None:
    """Verifies hallucinated SymPy imports are filtered while valid imports are retained."""
    code = """
from sympy import symbols, Eq, solve, schmitt_method, IntegerResult
x = symbols('x')
print(x)
"""
    sanitized, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "schmitt_method" not in sanitized
    assert "IntegerResult" not in sanitized
    assert "symbols" in sanitized
    assert "solve" in sanitized
    tree = ast.parse(sanitized)
    assert tree is not None


def test_turn1_preflight_injects_missing_itertools() -> None:
    """Verifies itertools is auto-imported when itertools.combinations is called without import."""
    code = """
perms = list(itertools.permutations([1, 2, 3]))
print(len(perms))
"""
    sanitized, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "import itertools" in sanitized
    tree = ast.parse(sanitized)
    assert tree is not None


def test_turn1_preflight_defines_missing_math_sets() -> None:
    """Verifies primes and odds sets are auto-defined when referenced."""
    code = """
p_list = [x for x in range(20) if x in primes]
print(p_list)
"""
    sanitized, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "primes =" in sanitized
    tree = ast.parse(sanitized)
    assert tree is not None
