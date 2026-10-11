"""
Project Lucca — MicroScheme Universal Symbolic Primitives (WO-35 Milestone 35.3)
D-REAS-11, D-AUD-01

Extends MicroScheme with domain-general abstract data types:
1. Higher-order sequence operations (map, filter, fold, zip, take, drop, reverse, unique).
2. Set & relational operations (member?, subset?, union, intersection, difference).
3. 2D vector geometry & navigation (vec2d, vec-add, vec-sub, vec-scale, manhattan-dist, euclidean-dist, heading-turn, step-forward).
4. Constraint predicates (all?, any?, none?, count-if).

Zero-Any typing strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from collections.abc import Callable
import math
from typing import Final, cast

import structlog

from lucca.core.exceptions import SchemeRuntimeError
from lucca.reasoning.scheme.parser import (
    Keyword,
    SchemeNode,
    SchemeValue,
    Symbol,
    to_canonical,
)
from lucca.reasoning.scheme.prims import PURE_PRIMITIVES

logger = structlog.get_logger(__name__)

INT_MAX: Final[int] = 2**63 - 1
INT_MIN: Final[int] = -(2**63)


def _check_list(val: SchemeValue, op_name: str) -> list[SchemeValue]:
    if not isinstance(val, list):
        raise SchemeRuntimeError(
            f"Operator '{op_name}' expects a list, got {type(val).__name__}",
            cause_type="TypeError",
        )
    return val


def _check_number(val: SchemeValue, op_name: str) -> int | float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise SchemeRuntimeError(
            f"Operator '{op_name}' expects number, got {type(val).__name__}",
            cause_type="TypeError",
        )
    if isinstance(val, float) and not math.isfinite(val):
        raise SchemeRuntimeError(
            f"Operator '{op_name}' encountered non-finite float: {val}",
            cause_type="ValueError",
        )
    return val


# =============================================================================
# Sequence Operations
# =============================================================================

def prim_reverse(args: list[SchemeValue]) -> SchemeValue:
    """(reverse xs) -> reversed list."""
    if len(args) != 1:
        raise SchemeRuntimeError(f"'reverse' requires exactly 1 argument, got {len(args)}")
    xs = _check_list(args[0], "reverse")
    return list(reversed(xs))


def prim_take(args: list[SchemeValue]) -> SchemeValue:
    """(take n xs) -> first n elements."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'take' requires exactly 2 arguments, got {len(args)}")
    n = int(_check_number(args[0], "take"))
    xs = _check_list(args[1], "take")
    return xs[:max(0, n)]


def prim_drop(args: list[SchemeValue]) -> SchemeValue:
    """(drop n xs) -> elements after first n."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'drop' requires exactly 2 arguments, got {len(args)}")
    n = int(_check_number(args[0], "drop"))
    xs = _check_list(args[1], "drop")
    return xs[max(0, n):]


def prim_zip(args: list[SchemeValue]) -> SchemeValue:
    """(zip xs ys) -> list of pairs [x, y]."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'zip' requires exactly 2 arguments, got {len(args)}")
    xs = _check_list(args[0], "zip")
    ys = _check_list(args[1], "zip")
    return [cast(SchemeValue, [x, y]) for x, y in zip(xs, ys)]


def prim_unique(args: list[SchemeValue]) -> SchemeValue:
    """(unique xs) -> deduplicated list preserving order."""
    if len(args) != 1:
        raise SchemeRuntimeError(f"'unique' requires exactly 1 argument, got {len(args)}")
    xs = _check_list(args[0], "unique")
    seen: list[SchemeValue] = []
    for item in xs:
        if item not in seen:
            seen.append(item)
    return seen


# =============================================================================
# Set & Relational Operations
# =============================================================================

def prim_member_p(args: list[SchemeValue]) -> SchemeValue:
    """(member? x xs) -> True if x is in xs, else False."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'member?' requires exactly 2 arguments, got {len(args)}")
    x, xs = args[0], _check_list(args[1], "member?")
    return bool(x in xs)


def prim_subset_p(args: list[SchemeValue]) -> SchemeValue:
    """(subset? xs ys) -> True if every element of xs is in ys."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'subset?' requires exactly 2 arguments, got {len(args)}")
    xs = _check_list(args[0], "subset?")
    ys = _check_list(args[1], "subset?")
    return bool(all(x in ys for x in xs))


def prim_union(args: list[SchemeValue]) -> SchemeValue:
    """(union xs ys) -> deduplicated union of xs and ys."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'union' requires exactly 2 arguments, got {len(args)}")
    xs = _check_list(args[0], "union")
    ys = _check_list(args[1], "union")
    res = list(xs)
    for y in ys:
        if y not in res:
            res.append(y)
    return res


def prim_intersection(args: list[SchemeValue]) -> SchemeValue:
    """(intersection xs ys) -> elements present in both xs and ys."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'intersection' requires exactly 2 arguments, got {len(args)}")
    xs = _check_list(args[0], "intersection")
    ys = _check_list(args[1], "intersection")
    return [x for x in xs if x in ys]


def prim_difference(args: list[SchemeValue]) -> SchemeValue:
    """(difference xs ys) -> elements in xs that are not in ys."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'difference' requires exactly 2 arguments, got {len(args)}")
    xs = _check_list(args[0], "difference")
    ys = _check_list(args[1], "difference")
    return [x for x in xs if x not in ys]


# =============================================================================
# 2D Vector Geometry & Navigation
# =============================================================================

def prim_vec2d(args: list[SchemeValue]) -> SchemeValue:
    """(vec2d x y) -> [x, y]."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'vec2d' requires exactly 2 arguments, got {len(args)}")
    x = _check_number(args[0], "vec2d")
    y = _check_number(args[1], "vec2d")
    return cast(SchemeValue, [x, y])


def prim_vec_add(args: list[SchemeValue]) -> SchemeValue:
    """(vec-add v1 v2) -> [x1+x2, y1+y2]."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'vec-add' requires exactly 2 arguments, got {len(args)}")
    v1 = _check_list(args[0], "vec-add")
    v2 = _check_list(args[1], "vec-add")
    if len(v1) != 2 or len(v2) != 2:
        raise SchemeRuntimeError("'vec-add' expects 2D vectors [x, y]")
    x1, y1 = _check_number(v1[0], "vec-add"), _check_number(v1[1], "vec-add")
    x2, y2 = _check_number(v2[0], "vec-add"), _check_number(v2[1], "vec-add")
    return cast(SchemeValue, [x1 + x2, y1 + y2])


def prim_vec_sub(args: list[SchemeValue]) -> SchemeValue:
    """(vec-sub v1 v2) -> [x1-x2, y1-y2]."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'vec-sub' requires exactly 2 arguments, got {len(args)}")
    v1 = _check_list(args[0], "vec-sub")
    v2 = _check_list(args[1], "vec-sub")
    if len(v1) != 2 or len(v2) != 2:
        raise SchemeRuntimeError("'vec-sub' expects 2D vectors [x, y]")
    x1, y1 = _check_number(v1[0], "vec-sub"), _check_number(v1[1], "vec-sub")
    x2, y2 = _check_number(v2[0], "vec-sub"), _check_number(v2[1], "vec-sub")
    return cast(SchemeValue, [x1 - x2, y1 - y2])


def prim_vec_scale(args: list[SchemeValue]) -> SchemeValue:
    """(vec-scale v s) -> [x*s, y*s]."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'vec-scale' requires exactly 2 arguments, got {len(args)}")
    v = _check_list(args[0], "vec-scale")
    s = _check_number(args[1], "vec-scale")
    if len(v) != 2:
        raise SchemeRuntimeError("'vec-scale' expects 2D vector [x, y]")
    x, y = _check_number(v[0], "vec-scale"), _check_number(v[1], "vec-scale")
    return cast(SchemeValue, [x * s, y * s])


def prim_manhattan_dist(args: list[SchemeValue]) -> SchemeValue:
    """(manhattan-dist v1 v2) -> |x1-x2| + |y1-y2|."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'manhattan-dist' requires exactly 2 arguments, got {len(args)}")
    v1 = _check_list(args[0], "manhattan-dist")
    v2 = _check_list(args[1], "manhattan-dist")
    if len(v1) != 2 or len(v2) != 2:
        raise SchemeRuntimeError("'manhattan-dist' expects 2D vectors [x, y]")
    x1, y1 = _check_number(v1[0], "manhattan-dist"), _check_number(v1[1], "manhattan-dist")
    x2, y2 = _check_number(v2[0], "manhattan-dist"), _check_number(v2[1], "manhattan-dist")
    return abs(x1 - x2) + abs(y1 - y2)


def prim_euclidean_dist(args: list[SchemeValue]) -> SchemeValue:
    """(euclidean-dist v1 v2) -> sqrt((x1-x2)^2 + (y1-y2)^2)."""
    if len(args) != 2:
        raise SchemeRuntimeError(f"'euclidean-dist' requires exactly 2 arguments, got {len(args)}")
    v1 = _check_list(args[0], "euclidean-dist")
    v2 = _check_list(args[1], "euclidean-dist")
    if len(v1) != 2 or len(v2) != 2:
        raise SchemeRuntimeError("'euclidean-dist' expects 2D vectors [x, y]")
    x1, y1 = _check_number(v1[0], "euclidean-dist"), _check_number(v1[1], "euclidean-dist")
    x2, y2 = _check_number(v2[0], "euclidean-dist"), _check_number(v2[1], "euclidean-dist")
    return math.hypot(x1 - x2, y1 - y2)


def prim_heading_turn(args: list[SchemeValue]) -> SchemeValue:
    """
    (heading-turn current_heading turn_action)
    Headings: 0 (N), 1 (E), 2 (S), 3 (W).
    Turn actions: "left" (-1), "right" (+1), "around" (+2).
    """
    if len(args) != 2:
        raise SchemeRuntimeError(f"'heading-turn' requires exactly 2 arguments, got {len(args)}")
    h = int(_check_number(args[0], "heading-turn")) % 4
    turn = str(args[1]).lower().strip().lstrip(":")
    if turn == "left":
        delta = -1
    elif turn == "right":
        delta = 1
    elif turn == "around":
        delta = 2
    else:
        raise SchemeRuntimeError(f"Unknown turn action '{turn}', expected 'left', 'right', or 'around'")
    return (h + delta) % 4


def prim_step_forward(args: list[SchemeValue]) -> SchemeValue:
    """
    (step-forward pos heading distance)
    pos: [x, y], heading: 0 (N), 1 (E), 2 (S), 3 (W), distance: int|float.
    """
    if len(args) != 3:
        raise SchemeRuntimeError(f"'step-forward' requires exactly 3 arguments, got {len(args)}")
    pos = _check_list(args[0], "step-forward")
    h = int(_check_number(args[1], "step-forward")) % 4
    d = _check_number(args[2], "step-forward")
    if len(pos) != 2:
        raise SchemeRuntimeError("'step-forward' expects 2D vector [x, y]")
    x, y = _check_number(pos[0], "step-forward"), _check_number(pos[1], "step-forward")

    # Headings: 0=N (+y), 1=E (+x), 2=S (-y), 3=W (-x)
    dx, dy = 0.0, 0.0
    if h == 0:
        dy = float(d)
    elif h == 1:
        dx = float(d)
    elif h == 2:
        dy = -float(d)
    elif h == 3:
        dx = -float(d)

    return cast(SchemeValue, [x + dx, y + dy])


# =============================================================================
# Universal Registry Map
# =============================================================================

UNIVERSAL_PRIMITIVES: Final[dict[str, Callable[[list[SchemeValue]], SchemeValue]]] = {
    # Sequences
    "reverse": prim_reverse,
    "take": prim_take,
    "drop": prim_drop,
    "zip": prim_zip,
    "unique": prim_unique,
    # Sets & Relations
    "member?": prim_member_p,
    "subset?": prim_subset_p,
    "union": prim_union,
    "intersection": prim_intersection,
    "difference": prim_difference,
    # 2D Geometry & Navigation
    "vec2d": prim_vec2d,
    "vec-add": prim_vec_add,
    "vec-sub": prim_vec_sub,
    "vec-scale": prim_vec_scale,
    "manhattan-dist": prim_manhattan_dist,
    "euclidean-dist": prim_euclidean_dist,
    "heading-turn": prim_heading_turn,
    "step-forward": prim_step_forward,
}


def register_universal_primitives() -> None:
    """Dynamically registers universal primitives into global PURE_PRIMITIVES table."""
    for name, fn in UNIVERSAL_PRIMITIVES.items():
        PURE_PRIMITIVES[name] = fn
    logger.debug("universal_primitives_registered", count=len(UNIVERSAL_PRIMITIVES))
