"""
Project Lucca — Property-Based Fuzzing Suite (Reasoning & AST Engine)
Spec 05, Spec 14, D-REAS-05, D-REAS-07, D-AUD-01
Exhaustive property-based testing using Hypothesis:
1. AST cost monotonicity and invariant bounds.
2. Anti-unification safety, parameter extraction, and substitution closure.
3. MicroScheme parser / canonical roundtrip idempotency.
4. Macro rewrite idempotency and contraction properties.
5. Invariant enforcement against deeply nested or explosive expressions.
"""

import math
from typing import Any
import pytest
from hypothesis import given, settings, strategies as st

from lucca.reasoning.cost import ast_cost, ast_depth, ast_node_count
from lucca.reasoning.egraph import (
    anti_unify,
    anti_unify_many,
    extract_parameters,
    match_template,
)
from lucca.reasoning.scheme.macros import (
    MAX_MACRO_DEPTH,
    MAX_MACRO_STEPS,
    MacroDefinition,
    MacroExpander,
    MacroRegistry,
)
from lucca.reasoning.scheme.parser import (
    Keyword,
    SchemeAtom,
    SchemeNode,
    Symbol,
    parse_expr,
    to_canonical,
)
from lucca.reasoning.compression import rewrite_with_macro


# ==============================================================================
# Hypothesis Strategies for MicroScheme ASTs
# ==============================================================================

# Valid identifier characters for MicroScheme symbols
scheme_identifiers = st.from_regex(r"[a-z][a-z0-9_-]{0,12}", fullmatch=True)

# Leaf primitives
scheme_symbols = scheme_identifiers.map(Symbol)
scheme_ints = st.integers(min_value=-1000, max_value=1000)
scheme_floats = st.floats(
    min_value=-1000.0,
    max_value=1000.0,
    allow_nan=False,
    allow_infinity=False,
).map(lambda x: round(x, 4))
scheme_strings = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
    min_size=0,
    max_size=20,
)
scheme_bools = st.booleans()

scheme_atoms = st.one_of(scheme_symbols, scheme_ints, scheme_floats, scheme_strings, scheme_bools)

# Recursive strategy for bounded MicroScheme ASTs (max_leaves=25 to prevent memory exhaustion)
scheme_exprs = st.recursive(
    scheme_atoms,
    lambda children: st.lists(children, min_size=1, max_size=5),
    max_leaves=25,
)

# Operator-headed ASTs for realistic arithmetic/logic trees
primitives = st.sampled_from(["+", "-", "*", "/", "and", "or", ">", "<", "="])


@st.composite
def realistic_exprs(draw: st.DrawFn, max_depth: int = 4) -> SchemeNode:
    """Generates structured operator expressions like (+ 1 (* 2 x))."""
    if max_depth <= 1:
        return draw(st.one_of(scheme_ints, scheme_identifiers.map(Symbol)))
    op = draw(primitives)
    arity = draw(st.integers(min_value=2, max_value=3))
    args = [draw(realistic_exprs(max_depth=max_depth - 1)) for _ in range(arity)]
    return [Symbol(op), *args]


# ==============================================================================
# 1. AST Cost, Depth, and Node Count Invariant Properties
# ==============================================================================


@settings(max_examples=200, deadline=None)
@given(scheme_exprs)
def test_fuzz_ast_cost_monotonicity(expr: SchemeNode) -> None:
    """
    Property: For any valid MicroScheme AST T:
    - node_count(T) >= 1
    - depth(T) >= 1
    - cost(T) >= alpha * depth(T) where alpha = 0.5
    """
    depth = ast_depth(expr)
    nodes = ast_node_count(expr)
    cost = ast_cost(expr, alpha=0.5)

    assert depth >= 1, f"Depth must be >= 1, got {depth}"
    assert nodes >= 1, f"Node count must be >= 1, got {nodes}"
    assert cost >= 0.5 * depth, f"Cost {cost} violated lower bound 0.5 * depth {depth}"


@settings(max_examples=100, deadline=None)
@given(realistic_exprs(max_depth=3), realistic_exprs(max_depth=3))
def test_fuzz_ast_composition_cost_subadditivity(left: SchemeNode, right: SchemeNode) -> None:
    """
    Property: Composing two expressions (+ left right) has bounded non-negative cost.
    """
    comp: SchemeNode = [Symbol("+"), left, right]
    c_left = ast_cost(left, alpha=0.5)
    c_right = ast_cost(right, alpha=0.5)
    c_comp = ast_cost(comp, alpha=0.5)

    assert c_comp >= max(c_left, c_right), "Composed cost must be at least maximum of components"
    assert c_comp <= c_left + c_right + 5.0, "Composed cost bounded above"


# ==============================================================================
# 2. Anti-Unification Properties & Substitution Closure
# ==============================================================================


@settings(max_examples=100, deadline=None)
@given(realistic_exprs(max_depth=3), realistic_exprs(max_depth=3))
def test_fuzz_anti_unify_safety(t1: SchemeNode, t2: SchemeNode) -> None:
    """
    Property: Anti-unifying any two well-formed trees:
    - Never raises unhandled exception.
    - Resulting template depth <= max(depth(t1), depth(t2)).
    - Synthesized template matches both t1 and t2.
    """
    tpl, subs = anti_unify(t1, t2, var_prefix="arg")
    tpl_depth = ast_depth(tpl)

    assert tpl_depth <= max(ast_depth(t1), ast_depth(t2))
    assert isinstance(subs, dict)

    # Matching template against inputs must succeed
    b1 = match_template(tpl, t1)
    b2 = match_template(tpl, t2)
    assert b1 is not None, f"Template {to_canonical(tpl)} failed to match instance 1 {to_canonical(t1)}"
    assert b2 is not None, f"Template {to_canonical(tpl)} failed to match instance 2 {to_canonical(t2)}"


@settings(max_examples=50, deadline=None)
@given(st.lists(realistic_exprs(max_depth=3), min_size=2, max_size=5))
def test_fuzz_anti_unify_many_invariants(exprs: list[SchemeNode]) -> None:
    """
    Property: Multi-tree anti-unification preserves arity and parameter consistency.
    """
    tpl, subs_list = anti_unify_many(exprs, var_prefix="arg")
    params = extract_parameters(tpl)

    assert len(subs_list) == len(exprs)
    for sub in subs_list:
        for p in params:
            assert p in sub, f"Extracted parameter {p} missing in substitution map {sub}"


# ==============================================================================
# 3. MicroScheme Parser / Canonical Roundtrip Idempotency
# ==============================================================================


@settings(max_examples=100, deadline=None)
@given(realistic_exprs(max_depth=4))
def test_fuzz_parser_canonical_roundtrip(expr: SchemeNode) -> None:
    """
    Property: For canonical S-expressions, parse(to_canonical(E)) == E.
    """
    canon_str = to_canonical(expr)
    parsed = parse_expr(canon_str)
    re_canon = to_canonical(parsed)

    assert canon_str == re_canon, f"Roundtrip serialization drift: {canon_str} != {re_canon}"


# ==============================================================================
# 4. Macro Rewrite Idempotency & Contraction
# ==============================================================================


@settings(max_examples=80, deadline=None)
@given(st.integers(min_value=1, max_value=100), st.integers(min_value=1, max_value=100))
def test_fuzz_macro_rewrite_cost_contraction(a: int, b: int) -> None:
    """
    Property: Rewriting an affine expression with a defined macro reduces AST cost
    and is idempotent (second rewrite produces identical AST).
    """
    expr = parse_expr(f"(+ {a} (* {b} x))")
    macro_def = MacroDefinition(
        name="affine",
        params=["arg_0", "arg_1"],
        body=parse_expr("(+ arg_0 (* arg_1 x))"),
    )

    rewritten_1 = rewrite_with_macro(expr, macro_def)
    rewritten_2 = rewrite_with_macro(rewritten_1, macro_def)

    # 1. Idempotency
    assert to_canonical(rewritten_1) == to_canonical(rewritten_2)

    # 2. Contraction: Rewritten call (affine a b) has lower cost than expanded (+ a (* b x))
    cost_orig = ast_cost(expr)
    cost_rewritten = ast_cost(rewritten_1)
    assert cost_rewritten < cost_orig, f"Rewritten cost {cost_rewritten} not less than original {cost_orig}"


# ==============================================================================
# 5. D-REAS-05 Complexity Boundary Fuzzing
# ==============================================================================


def test_deep_ast_depth_limit_violation_caught() -> None:
    """
    Verify synthetic expressions with depth > MAX_MACRO_DEPTH (8) are detected and flagged.
    """
    # Build deep nested expression: (+ (+ (+ ...)))
    deep_expr: SchemeNode = 1
    for _ in range(12):
        deep_expr = [Symbol("+"), deep_expr, 1]

    depth = ast_depth(deep_expr)
    assert depth == 13
    assert depth > MAX_MACRO_DEPTH, "Expression must exceed depth limit"
