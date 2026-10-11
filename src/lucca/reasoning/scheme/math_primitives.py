"""
Project Lucca — MicroScheme MathCAS Environment (WO-33 Milestone 4)
D-REAS-11, D-AUD-01

Binds pure, gas-metered Computer Algebra System (CAS) operations to MicroScheme AST evaluation.
Provides SymPy-backed algebraic transformations (factor, expand, simplify, solve, diff, integrate)
under bounded gas limits and wall-clock execution timeouts.

Zero domain keywords, zero benchmark problem IDs.
Zero-Any typing strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Final, cast

import structlog
import sympy as sp

from lucca.reasoning.scheme.eval import SchemeEvaluator
from lucca.reasoning.scheme.parser import (
    Keyword,
    SchemeAtom,
    SchemeNode,
    SchemeValue,
    Symbol,
    parse_expr,
    to_canonical,
)
from lucca.reasoning.scheme.prims import PURE_PRIMITIVES
from lucca.reasoning.topology import HoleEnumerationResult, enumerate_hole_bindings

logger = structlog.get_logger(__name__)


def _to_kw_str(val: SchemeValue) -> str:
    """Converts a Scheme atom to a string identifier, stripping leading colons."""
    if isinstance(val, Keyword):
        return val.name.lstrip(":")
    if isinstance(val, Symbol):
        return val.name.lstrip(":")
    if isinstance(val, str):
        return val.lstrip(":")
    return str(val)


def _scheme_to_sympy(node: SchemeValue) -> sp.Basic:
    """Converts a MicroScheme AST expression or value into a SymPy symbolic expression."""
    if isinstance(node, bool):
        return sp.true if node else sp.false
    if isinstance(node, int):
        return sp.Integer(node)
    if isinstance(node, float):
        return sp.Float(node)
    if isinstance(node, Keyword):
        return sp.Symbol(node.name.lstrip(":"))
    if isinstance(node, Symbol):
        name = node.name.strip("'\"")
        if name in ("pi", "pi_val"):
            return sp.pi
        if name in ("E", "e_val"):
            return sp.E
        if name.isdigit() or (name.startswith("-") and name[1:].isdigit()):
            return sp.Integer(int(name))
        return sp.Symbol(name)
    if isinstance(node, str):
        s = node.strip("'\"")
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return sp.Integer(int(s))
        try:
            return sp.sympify(s)
        except Exception as exc:
            logger.debug("sympify_str_error", error=str(exc))
            return sp.Symbol(s)

    if isinstance(node, list):
        if not node:
            return sp.Integer(0)
        head = node[0]
        op = head.name if isinstance(head, Symbol) else str(head)
        args = [_scheme_to_sympy(c) for c in node[1:] if not isinstance(c, Keyword)]

        if op == "+":
            return sp.Add(*args) if args else sp.Integer(0)
        elif op == "-":
            if len(args) == 1:
                return -args[0]
            elif len(args) >= 2:
                return args[0] - sp.Add(*args[1:])
            return sp.Integer(0)
        elif op == "*":
            return sp.Mul(*args) if args else sp.Integer(1)
        elif op == "/":
            if len(args) == 2:
                return args[0] / args[1]
            return sp.Integer(0)
        elif op == "pow":
            if len(args) >= 2:
                return sp.Pow(args[0], args[1])
            return sp.Integer(0)
        elif op == "=":
            if len(args) == 2:
                return sp.Eq(args[0], args[1])
            return sp.Integer(0)
        elif op in ("sin", "cos", "tan", "exp", "log", "sqrt"):
            if args:
                fn = getattr(sp, op, None)
                if fn is not None:
                    return cast(sp.Basic, fn(args[0]))
            return sp.Integer(0)

        # Fallback to general sympified canonical form
        canon = to_canonical(cast(SchemeNode, node))
        try:
            return sp.sympify(canon)
        except Exception as exc:
            logger.debug("sympify_canonical_error", error=str(exc))
            return sp.Symbol("expr")

    return sp.Integer(0)


def _sympy_to_scheme(expr: sp.Basic | int | float | str | bool) -> SchemeValue:
    """Converts a SymPy expression or result to a typed SchemeValue."""
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    if isinstance(expr, float):
        if expr.is_integer():
            return int(expr)
        return expr
    if isinstance(expr, (sp.Integer, sp.core.numbers.Integer)):
        return int(expr)
    if isinstance(expr, (sp.Float, sp.core.numbers.Float)):
        val = float(expr)
        return int(val) if val.is_integer() else val
    if isinstance(expr, (sp.Rational, sp.core.numbers.Rational)):
        if expr.q == 1:
            return int(expr.p)
        return str(expr)
    if isinstance(expr, (sp.Symbol, sp.core.symbol.Symbol)):
        return Symbol(expr.name)
    if isinstance(expr, (list, tuple)):
        return [_sympy_to_scheme(item) for item in expr]
    if isinstance(expr, (set, frozenset)):
        return [_sympy_to_scheme(item) for item in sorted(expr, key=str)]

    # Format symbolic expression into canonical string / representation
    return str(expr)


# =============================================================================
# Pure MathCAS MicroScheme Primitives
# =============================================================================


def prim_simplify(args: list[SchemeValue]) -> SchemeValue:
    """(simplify expr) -> simplified symbolic expression"""
    if not args:
        return 0
    sp_expr = _scheme_to_sympy(args[0])
    try:
        res = sp.simplify(sp_expr)
        return _sympy_to_scheme(res)
    except Exception as exc:
        logger.debug("math_simplify_error", error=str(exc))
        return _sympy_to_scheme(sp_expr)


def prim_factor(args: list[SchemeValue]) -> SchemeValue:
    """(factor expr) -> factored polynomial / algebraic expression"""
    if not args:
        return 0
    sp_expr = _scheme_to_sympy(args[0])
    try:
        res = sp.factor(sp_expr)
        return _sympy_to_scheme(res)
    except Exception as exc:
        logger.debug("math_factor_error", error=str(exc))
        return _sympy_to_scheme(sp_expr)


def prim_expand(args: list[SchemeValue]) -> SchemeValue:
    """(expand expr) -> expanded algebraic expression"""
    if not args:
        return 0
    sp_expr = _scheme_to_sympy(args[0])
    try:
        res = sp.expand(sp_expr)
        return _sympy_to_scheme(res)
    except Exception as exc:
        logger.debug("math_expand_error", error=str(exc))
        return _sympy_to_scheme(sp_expr)


def prim_solve(args: list[SchemeValue]) -> SchemeValue:
    """(solve equation [:var x]) or (solve lhs rhs [:var x]) -> solutions list"""
    if not args:
        return []
    var_sym = sp.Symbol("x")
    sp_eq: sp.Basic
    i = 1
    if len(args) >= 2 and not isinstance(args[1], Keyword) and not (isinstance(args[1], str) and args[1].startswith(":")):
        lhs = _scheme_to_sympy(args[0])
        rhs = _scheme_to_sympy(args[1])
        sp_eq = sp.Eq(lhs, rhs)
        i = 2
    else:
        sp_eq = _scheme_to_sympy(args[0])
        i = 1

    while i < len(args):
        kw = _to_kw_str(args[i])
        if kw == "var" and i + 1 < len(args):
            v_name = _to_kw_str(args[i + 1])
            var_sym = sp.Symbol(v_name)
            i += 2
        else:
            i += 1

    try:
        sols = sp.solve(sp_eq, var_sym)
        return _sympy_to_scheme(sols)
    except Exception as exc:
        logger.debug("math_solve_error", error=str(exc))
        return []


def prim_diff(args: list[SchemeValue]) -> SchemeValue:
    """(diff expr [:var x]) -> derivative of expression"""
    if not args:
        return 0
    sp_expr = _scheme_to_sympy(args[0])
    var_sym = sp.Symbol("x")

    i = 1
    while i < len(args):
        kw = _to_kw_str(args[i])
        if kw == "var" and i + 1 < len(args):
            v_name = _to_kw_str(args[i + 1])
            var_sym = sp.Symbol(v_name)
            i += 2
        else:
            i += 1

    try:
        res = sp.diff(sp_expr, var_sym)
        return _sympy_to_scheme(res)
    except Exception as exc:
        logger.debug("math_diff_error", error=str(exc))
        return 0


def prim_integrate(args: list[SchemeValue]) -> SchemeValue:
    """(integrate expr [:var x]) -> indefinite integral of expression"""
    if not args:
        return 0
    sp_expr = _scheme_to_sympy(args[0])
    var_sym = sp.Symbol("x")

    i = 1
    while i < len(args):
        kw = _to_kw_str(args[i])
        if kw == "var" and i + 1 < len(args):
            v_name = _to_kw_str(args[i + 1])
            var_sym = sp.Symbol(v_name)
            i += 2
        else:
            i += 1

    try:
        res = sp.integrate(sp_expr, var_sym)
        return _sympy_to_scheme(res)
    except Exception as exc:
        logger.debug("math_integrate_error", error=str(exc))
        return 0


def prim_pow(args: list[SchemeValue]) -> SchemeValue:
    """(pow base exp) -> base raised to exp"""
    if len(args) < 2:
        return args[0] if args else 0
    b = _scheme_to_sympy(args[0])
    e = _scheme_to_sympy(args[1])
    try:
        return _sympy_to_scheme(sp.Pow(b, e))
    except Exception as exc:
        logger.debug("math_pow_error", error=str(exc))
        return 0


def prim_subst(args: list[SchemeValue]) -> SchemeValue:
    """(subst expr var val) -> substitute var with val in expr"""
    if len(args) < 3:
        return args[0] if args else 0
    sp_expr = _scheme_to_sympy(args[0])
    v_sym = sp.Symbol(_to_kw_str(args[1]))
    val = _scheme_to_sympy(args[2])
    try:
        res = sp_expr.subs(v_sym, val)
        return _sympy_to_scheme(res)
    except Exception as exc:
        logger.debug("math_subst_error", error=str(exc))
        return _sympy_to_scheme(sp_expr)


def math_add(args: list[SchemeValue]) -> SchemeValue:
    """Symbolic-aware addition."""
    if all(isinstance(a, (int, float)) and not isinstance(a, bool) for a in args):
        nums = [cast(float | int, a) for a in args]
        total = sum(nums)
        if isinstance(total, float) and total.is_integer():
            return int(total)
        return total
    sp_args = [_scheme_to_sympy(a) for a in args]
    return _sympy_to_scheme(sp.Add(*sp_args))


def math_sub(args: list[SchemeValue]) -> SchemeValue:
    """Symbolic-aware subtraction."""
    if not args:
        return 0
    if all(isinstance(a, (int, float)) and not isinstance(a, bool) for a in args):
        nums = [cast(float | int, a) for a in args]
        if len(nums) == 1:
            return -nums[0]
        total = nums[0] - sum(nums[1:])
        if isinstance(total, float) and total.is_integer():
            return int(total)
        return total
    sp_args = [_scheme_to_sympy(a) for a in args]
    if len(sp_args) == 1:
        return _sympy_to_scheme(-sp_args[0])
    return _sympy_to_scheme(sp_args[0] - sp.Add(*sp_args[1:]))


def math_mul(args: list[SchemeValue]) -> SchemeValue:
    """Symbolic-aware multiplication."""
    if all(isinstance(a, (int, float)) and not isinstance(a, bool) for a in args):
        prod: float | int = 1
        for a in args:
            prod *= cast(float | int, a)
        if isinstance(prod, float) and prod.is_integer():
            return int(prod)
        return prod
    sp_args = [_scheme_to_sympy(a) for a in args]
    return _sympy_to_scheme(sp.Mul(*sp_args))


def math_div(args: list[SchemeValue]) -> SchemeValue:
    """Symbolic-aware division."""
    if len(args) == 2 and all(isinstance(a, int) and not isinstance(a, bool) for a in args):
        n0 = cast(int, args[0])
        n1 = cast(int, args[1])
        if n1 != 0:
            return _sympy_to_scheme(sp.Rational(n0, n1))
    sp_args = [_scheme_to_sympy(a) for a in args]
    if len(sp_args) == 2:
        return _sympy_to_scheme(sp_args[0] / sp_args[1])
    return 0


def math_eq(args: list[SchemeValue]) -> SchemeValue:
    """Symbolic-aware equality (= left right)."""
    if len(args) == 2:
        sp_left = _scheme_to_sympy(args[0])
        sp_right = _scheme_to_sympy(args[1])
        return _sympy_to_scheme(sp.Eq(sp_left, sp_right))
    return True


MATH_SCHEME_PRIMITIVES: Final[
    dict[str, Callable[[list[SchemeValue]], SchemeValue]]
] = {
    "+": math_add,
    "-": math_sub,
    "*": math_mul,
    "/": math_div,
    "=": math_eq,
    "simplify": prim_simplify,
    "factor": prim_factor,
    "expand": prim_expand,
    "solve": prim_solve,
    "diff": prim_diff,
    "integrate": prim_integrate,
    "pow": prim_pow,
    "subst": prim_subst,
}


def make_math_scheme_env(
    extra_bindings: dict[str, SchemeValue] | None = None,
) -> dict[str, Callable[[list[SchemeValue]], SchemeValue]]:
    """Constructs a MicroScheme environment initialized with PURE_PRIMITIVES and MATH_SCHEME_PRIMITIVES."""
    env: dict[str, Callable[[list[SchemeValue]], SchemeValue]] = {}
    env.update(PURE_PRIMITIVES)
    env.update(MATH_SCHEME_PRIMITIVES)

    # Standard mathematical free variables default to symbolic representation
    for var_name in ("x", "y", "z", "n", "k", "t", "expr", "ans", "a", "b", "c"):
        v_sym = Symbol(var_name)

        def _make_sym_getter(s: Symbol) -> Callable[[list[SchemeValue]], SchemeValue]:
            return lambda _: s

        env[var_name] = _make_sym_getter(v_sym)

    if extra_bindings:
        for bound_key, bound_val in extra_bindings.items():
            captured_bound = bound_val

            def _make_getter(captured_val: SchemeValue) -> Callable[[list[SchemeValue]], SchemeValue]:
                return lambda _: captured_val

            env[bound_key] = _make_getter(captured_bound)

    return env


def evaluate_math_sketch(
    sketch: SchemeNode | str,
    gas_limit: int = 500,
    timeout_ms: float = 2000.0,
    hole_bindings: dict[str, SchemeValue] | None = None,
) -> SchemeValue:
    """Evaluates a MicroScheme MathCAS sketch under bounded gas and timeout limits."""
    if isinstance(sketch, str):
        lines = [line.strip() for line in sketch.splitlines() if line.strip()]
        first_line = lines[0] if lines else sketch
        node = parse_expr(first_line)
    else:
        node = sketch

    env = make_math_scheme_env(extra_bindings=hole_bindings)
    evaluator = SchemeEvaluator(gas_limit=gas_limit, timeout_ms=timeout_ms)
    return evaluator.eval(node, env)


def enumerate_math_sketch_bindings(
    sketch: SchemeNode | str,
    demos: list[tuple[SchemeValue, SchemeValue]],
    candidate_domains: dict[str, list[SchemeValue]] | None = None,
    max_candidates: int = 100,
) -> HoleEnumerationResult:
    """
    Enumerates candidate hole bindings for a MathCAS sketch against demonstration pairs
    using the domain-general hole enumeration and e-graph pruning engine.
    """
    domains: dict[str, list[SchemeValue]] = candidate_domains or {
        "var": [Symbol("x"), Symbol("y"), Symbol("z"), Symbol("n")],
        "val": [-2, -1, 0, 1, 2, 3, 4, 5],
        "term": [Symbol("x"), Symbol("y"), 0, 1],
    }

    def _eval(node: SchemeNode, inp: SchemeValue, binding: dict[str, SchemeValue]) -> SchemeValue:
        augmented_binding = dict(binding)
        augmented_binding["expr"] = inp
        augmented_binding["x"] = inp
        return evaluate_math_sketch(node, hole_bindings=augmented_binding)

    return enumerate_hole_bindings(
        sketch=sketch,
        eval_fn=_eval,
        demos=demos,
        candidate_domains=domains,
        max_candidates=max_candidates,
        use_egraph_pruning=True,
    )
