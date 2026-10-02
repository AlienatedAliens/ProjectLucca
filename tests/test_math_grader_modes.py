"""Unit tests for Step 3: Math Grader with Strict and Lenient Modes.
Spec: Step 3 Measurement Fixes
"""

from __future__ import annotations

import pytest

from scripts.regrade_math_checkpoint import (
    compare_math_lenient,
    compare_math_results,
    compare_math_strict,
)


def test_strict_rejects_decimal_for_fraction():
    assert not compare_math_strict("0.5", "\\frac{1}{2}")
    assert not compare_math_strict("0.875", "\\frac{7}{8}")
    assert not compare_math_strict("0.2", "\\frac{1}{5}")
    assert not compare_math_strict("1.33333333333333", "\\frac{4}{3}")


def test_strict_rejects_decimal_for_irrational():
    assert not compare_math_strict("15.5241746962600", "\\sqrt{241}")
    assert not compare_math_strict("3.141592653589793", "\\pi")
    assert not compare_math_strict("3.87298334620742", "\\sqrt{15}")


def test_strict_accepts_exact_symbolic_and_string_equivalence():
    assert compare_math_strict("1/2", "\\frac{1}{2}")
    assert compare_math_strict("2/4", "\\frac{1}{2}")
    assert compare_math_strict("2*sqrt(3) - 2", "-2 + 2*\\sqrt{3}")
    assert compare_math_strict("x^2 - 1", "(x - 1)*(x + 1)")
    assert compare_math_strict("277.000000000000", "277")
    assert compare_math_strict("0.38", ".38")
    assert compare_math_strict("4130", "4130_5")


def test_lenient_accepts_multiple_choice_letters():
    assert compare_math_lenient("E", "\\text{(E)}")
    assert compare_math_lenient("E", "(E)")
    assert compare_math_lenient("B", "\\mathbf{B}")
    assert compare_math_lenient("\\text{(A)}", "A")
    assert not compare_math_lenient("A", "\\text{(B)}")


def test_lenient_accepts_stripped_percent():
    assert compare_math_lenient("33", "33\\%")
    assert compare_math_lenient("33%", "33\\%")
    assert compare_math_lenient("33", "33%")
    assert not compare_math_lenient("33", "34%")


def test_lenient_accepts_unit_labels():
    assert compare_math_lenient("10", "10\\;\\text{edges}")
    assert compare_math_lenient("10", "10\\text{ cm}")
    assert compare_math_lenient("25", "25\\text{ sq units}")
    assert compare_math_lenient("90", "90^\\circ")


def test_lenient_accepts_set_and_list_order():
    assert compare_math_lenient("-1/12, 1/2", "\\frac{1}{2}, -\\frac{1}{12}")
    assert compare_math_lenient("(-3/4, 3/4)", "\\frac{3}{4}, -\\frac{3}{4}")
    assert compare_math_lenient("[-3, 1]", "1, -3")


def test_lenient_accepts_matrix_rendering():
    assert compare_math_lenient("[[1], [7]]", "\\begin{pmatrix} 1 \\\\ 7 \\end{pmatrix}")
    assert compare_math_lenient("Matrix([[-6], [9]])", "\\begin{pmatrix} -6 \\\\ 9 \\end{pmatrix}")
    assert compare_math_lenient("Matrix([[1/5, 4/5], [0, 1]])", "\\begin{pmatrix} 1/5 & 4/5 \\\\ 0 & 1 \\end{pmatrix}")


def test_lenient_accepts_interval_rendering():
    assert compare_math_lenient("Interval(-oo, -3)", "(-\\infty, -3)")
    assert compare_math_lenient("Interval(0, 5)", "(0, 5)")


def test_unified_entry_point():
    assert compare_math_results("E", "\\text{(E)}", mode="lenient")
    assert not compare_math_results("E", "\\text{(E)}", mode="strict")
    assert compare_math_results("0.5", "\\frac{1}{2}", mode="lenient")
    assert not compare_math_results("0.5", "\\frac{1}{2}", mode="strict")
