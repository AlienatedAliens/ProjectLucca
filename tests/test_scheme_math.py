"""
Unit tests for WO-33 Milestone 4: Multi-Domain Harmonization (MathCAS & Code ASTs).
Tests SymPy-backed MicroScheme math primitives, algebraic sketches, typed hole enumeration,
and GBNF grammar files.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from lucca.reasoning.scheme.math_primitives import (
    MATH_SCHEME_PRIMITIVES,
    enumerate_math_sketch_bindings,
    evaluate_math_sketch,
)
from lucca.reasoning.scheme.parser import parse_expr


def test_math_primitives_evaluation():
    # Simplify
    res_simp = evaluate_math_sketch("(simplify (+ (* 2 x) (* 3 x)))")
    assert str(res_simp) in ("5*x", "5 * x")

    # Factor
    res_factor = evaluate_math_sketch("(factor (+ (pow x 2) (* 5 x) 6))")
    assert "x + 2" in str(res_factor) and "x + 3" in str(res_factor)

    # Expand
    res_expand = evaluate_math_sketch("(expand (* (+ x 1) (+ x 2)))")
    assert "x**2" in str(res_expand) and "3*x" in str(res_expand)

    # Solve
    res_solve = evaluate_math_sketch("(solve (= (* 2 x) 10) :var x)")
    assert res_solve == [5]

    # Diff
    res_diff = evaluate_math_sketch("(diff (pow x 3) :var x)")
    assert str(res_diff) in ("3*x**2", "3 * x ** 2")

    # Integrate
    res_int = evaluate_math_sketch("(integrate (* 2 x) :var x)")
    assert str(res_int) in ("x**2", "x ** 2")


def test_math_sketch_gbnf_grammar_file():
    grammar_path = Path("config/grammars/math_sketch.gbnf")
    assert grammar_path.exists()
    content = grammar_path.read_text(encoding="utf-8")
    assert "root ::= ws expr-list ws" in content
    assert "sketch ::=" in content
    assert "?hole-var" in content
    assert "?hole-val" in content
    assert "simplify" in content
    assert "factor" in content


def test_code_sketch_gbnf_grammar_file():
    grammar_path = Path("config/grammars/code_sketch.gbnf")
    assert grammar_path.exists()
    content = grammar_path.read_text(encoding="utf-8")
    assert "root ::=" in content
    assert "def-func ::=" in content
    assert "?hole-bound" in content
    assert "?hole-val" in content


def test_math_sketch_hole_enumeration():
    # Sketch with parameter hole: (+ (* ?hole-val x) 1)
    demos = [(2, 5), (3, 7), (10, 21)]
    res = enumerate_math_sketch_bindings(
        sketch="(+ (* ?hole-val x) 1)",
        demos=demos,
        max_candidates=50,
    )

    assert res.best_binding is not None
    assert res.best_binding.get("?hole-val") == 2
    assert res.coverage_rate == 1.0
    assert res.latency_ms < 100.0
