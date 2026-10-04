"""
Unit tests for WO-29 Module 2: Equality Saturation Rewrite Rules.
Tests term-rewriting equality saturation over MicroScheme ASTs,
canonical simplification, constant folding, and spatial rewrites.
"""

import pytest

from lucca.reasoning.egraph import (
    EGraph,
    RewriteRule,
    SPATIAL_REWRITE_RULES,
    STANDARD_REWRITE_RULES,
    equality_saturate,
    extract_best,
)
from lucca.reasoning.scheme.parser import Symbol, parse_expr, to_canonical


def test_rewrite_rule_creation():
    rule = RewriteRule.from_sexpr("(+ ?x 0)", "?x", name="add-zero")
    assert isinstance(rule.lhs, list)
    assert rule.lhs[0] == Symbol("+")
    assert rule.rhs == Symbol("?x")
    assert rule.name == "add-zero"


def test_algebraic_equality_saturation_simplification():
    eg = EGraph()
    # Expression: (* 1 (+ x 0))
    cid = eg.add(parse_expr("(* 1 (+ x 0))"))

    iters = eg.saturate(rules=STANDARD_REWRITE_RULES)
    assert iters >= 1

    # Best representation should be simply 'x'
    best = eg.extract(cid)
    assert best == Symbol("x")


def test_constant_folding():
    eg = EGraph()
    # Expression: (+ 10 (* 2 5))
    cid = eg.add(parse_expr("(+ 10 (* 2 5))"))

    eg.saturate(rules=STANDARD_REWRITE_RULES)
    best = eg.extract(cid)
    # (+ 10 10) -> 20
    assert best == 20


def test_spatial_equality_saturation():
    eg = EGraph()
    # Expression: (translate (translate s 10 20) 5 5)
    # Rules: (translate (translate ?s ?dx1 ?dy1) ?dx2 ?dy2) -> (translate ?s (+ ?dx1 ?dx2) (+ ?dy1 ?dy2))
    # Combined with constant folding (+ 10 5) -> 15, (+ 20 5) -> 25
    cid = eg.add(parse_expr("(translate (translate s 10 20) 5 5)"))

    eg.saturate(rules=SPATIAL_REWRITE_RULES + STANDARD_REWRITE_RULES)
    best = eg.extract(cid)
    assert best == [Symbol("translate"), Symbol("s"), 15, 25]


def test_spatial_identity_elimination():
    eg = EGraph()
    # (scale (translate s 0 0) 1) -> s
    cid = eg.add(parse_expr("(scale (translate s 0 0) 1)"))

    eg.saturate(rules=SPATIAL_REWRITE_RULES + STANDARD_REWRITE_RULES)
    best = eg.extract(cid)
    assert best == Symbol("s")


def test_idempotence_and_self_cancellation():
    eg = EGraph()
    cid1 = eg.add(parse_expr("(- x x)"))
    eg.saturate(rules=STANDARD_REWRITE_RULES)
    assert eg.extract(cid1) == 0

    eg2 = EGraph()
    cid2 = eg2.add(parse_expr("(and y y)"))
    eg2.saturate(rules=STANDARD_REWRITE_RULES)
    assert eg2.extract(cid2) == Symbol("y")
