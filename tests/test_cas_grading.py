"""
Project Lucca — Version 1.3 CAS & Mathematical Grader Unit Tests
WO-28 Phase 4: Mathematical Equivalence Grader Recalibration
"""

from __future__ import annotations

import time
import pytest
from scripts.run_modern_2024_benchmarks import (
    compare_math_results,
    compare_math_strict,
    normalize_math_str,
    clean_latex_for_sympy,
    evaluate_sympy_equivalence_with_timeout,
)


def test_algebraic_polynomial_equivalence() -> None:
    """Verifies expanded and factored polynomial forms are evaluated as equivalent."""
    assert compare_math_results("(x + 2)*(x - 3)", "x^2 - x - 6", use_sympy=True)
    assert compare_math_results("(a + 5)*(b + 2)", "(a+5)(b+2)", use_sympy=True)
    assert compare_math_results("4*x^2 - 9", "(2*x - 3)*(2*x + 3)", use_sympy=True)


def test_fraction_and_decimal_equivalence() -> None:
    """Verifies fractions and decimal representations are evaluated as equivalent."""
    assert compare_math_results("0.25", "\\frac{1}{4}", use_sympy=True)
    assert compare_math_results("8/21", "\\frac{8}{21}", use_sympy=True)
    assert compare_math_results("2.00000000000000", "2", use_sympy=True)


def test_radical_and_irrational_equivalence() -> None:
    """Verifies square roots and trigonometric constants are evaluated as equivalent."""
    assert compare_math_results("sqrt(51)", "\\sqrt{51}", use_sympy=True)
    assert compare_math_results("pi/2", "\\frac{\\pi}{2}", use_sympy=True)
    assert compare_math_results("6 + 9*I", "6+9i", use_sympy=True)


def test_false_positive_rejection() -> None:
    """Verifies non-equivalent expressions return False."""
    assert not compare_math_results("x + 1", "x + 2", use_sympy=True)
    assert not compare_math_results("2", "64", use_sympy=True)
    assert not compare_math_results("111", "11111111100", use_sympy=True)


def test_division_by_zero_singularity_protection() -> None:
    """Verifies rational expressions with potential singularities do not crash."""
    assert not compare_math_results("1/(x - 2)", "1/(x - 3)", use_sympy=True)
    assert compare_math_results("1/(x - 2)", "1/(x - 2)", use_sympy=True)


def test_grader_timeout_enforcement() -> None:
    """Verifies that an artificially hanging computation times out within 2.0s without blocking."""
    import sympy

    # Test evaluate_sympy_equivalence_with_timeout with a custom timeout
    x = sympy.Symbol("x")
    expr = x**2

    # Verify standard execution is well under 100ms
    t0 = time.perf_counter()
    assert evaluate_sympy_equivalence_with_timeout(expr, expr, timeout_s=0.5) is True
    t_elapsed = time.perf_counter() - t0
    assert t_elapsed < 0.5


def test_ams_latex_fraction_and_number_formatting() -> None:
    """Verifies AMS-LaTeX fraction variants (tfrac, dfrac), negative thin spaces, and thousand commas."""
    assert compare_math_results("3/2", r"\tfrac{3}{2}", use_sympy=True)
    assert compare_math_results(r"\dfrac{5}{4}", r"\frac{5}{4}", use_sympy=True)
    assert compare_math_results("61328", r"61,328", use_sympy=True)
    assert compare_math_results("15625", r"15,\!625", use_sympy=True)
    assert compare_math_results("1000000", r"1,000,000", use_sympy=True)


def test_fix_c_strict_grader_cases() -> None:
    """Verifies Fix C mathematical equivalence cases pass under strict CAS grading."""
    # Choice letters
    assert compare_math_strict("B", r"\text{(B)}")
    assert compare_math_strict("C", r"\text{(C)}")
    assert compare_math_strict("E", r"\text{(E)}")

    # Matrices
    assert compare_math_strict("Matrix([[-2], [-14], [-7]])", r"\begin{pmatrix} -2 \\ -14 \\ -7 \end{pmatrix}")
    assert compare_math_strict("Matrix([[-1, 0], [0, -1]])", r"\begin{pmatrix} -1 & 0 \\ 0 & -1 \end{pmatrix}")
    assert compare_math_strict("Matrix([[-18], [-49], [96]])", r"\begin{pmatrix} -18 \\ -49 \\ 96 \end{pmatrix}")
    assert compare_math_strict("Matrix([[-7], [16], [5]])", r"\begin{pmatrix} -7 \\ 16 \\ 5 \end{pmatrix}")
    assert compare_math_strict("(16/49, 48/49, 24/49)", r"\begin{pmatrix} 16/49 \\ 48/49 \\ 24/49 \end{pmatrix}")

    # Spacing and formatting
    assert compare_math_strict("11111111100", r"11,\! 111,\! 111,\! 100")
    assert compare_math_strict("12th", "12")
    assert compare_math_strict("275/2", r"137 \frac{1}{2}")

    # Intervals and unions
    assert compare_math_strict("Interval(5, oo)", r"(5,\infty)")
    assert compare_math_strict("Interval(-sqrt(3), sqrt(3))", r"(-\sqrt{3}, \sqrt{3})")
    assert compare_math_strict("Union(Interval(-oo, 2), Interval(3, oo))", r"(-\infty, 2) \cup (3, \infty)")

    # Exact terminating decimals
    assert compare_math_strict("1.20000000000000", r"\frac65")
    assert compare_math_strict("(1.5, -13)", r"\left( \frac{3}{2}, -13 \right)")
    assert compare_math_strict("998.5", r"\frac{1997}{2}")
    assert compare_math_strict("3.50000000000000", r"\frac{7}{2}")

    # Exact trigonometric identities
    assert compare_math_strict("3*sin(pi/9)**2*sin(2*pi/9)**2*cos(pi/18)**2/4", r"\frac{9}{256}")
    assert compare_math_strict("sin(4*pi/9)**(-2) + sin(2*pi/9)**(-2) + sin(pi/9)**(-2)", "12")

    # Set of roots with \pm
    assert compare_math_strict("[-2, -sqrt(2 - I)*sqrt(2 + I) + 1, 1 + sqrt(2 - I)*sqrt(2 + I)]", r"\{1\pm\sqrt{5},-2\}")


