"""
MicroScheme v2 Primitives Table & State Bindings
Spec 05 §2, §4, §5
"""

import fnmatch
import math
import uuid
from collections.abc import Callable

from pydantic import JsonValue

from lucca.core.exceptions import (
    SchemeInterruptSignal,
    SchemeRuntimeError,
    SchemeYieldSignal,
)
from lucca.core.schemas import AssertFact, RuleState, Say, ToolCall, is_valid_predicate
from lucca.reasoning.scheme.parser import Keyword, SchemeValue, Symbol

INT_MAX = 2**63 - 1
INT_MIN = -(2**63)
MAX_STR_LEN = 4096
MAX_LIST_LEN = 256


def _check_number(val: SchemeValue, op_name: str) -> int | float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise SchemeRuntimeError(
            f"Operator '{op_name}' expects number, got {type(val).__name__}", cause_type="TypeError"
        )
    if isinstance(val, float) and not math.isfinite(val):
        raise SchemeRuntimeError(
            f"Operator '{op_name}' encountered non-finite float: {val}", cause_type="ValueError"
        )
    if isinstance(val, int) and (val > INT_MAX or val < INT_MIN):
        raise SchemeRuntimeError(
            f"Integer out of bounds in '{op_name}': {val}", cause_type="OverflowError"
        )
    return val


def _check_str(val: SchemeValue, op_name: str) -> str:
    if not isinstance(val, str):
        raise SchemeRuntimeError(
            f"Operator '{op_name}' expects string, got {type(val).__name__}", cause_type="TypeError"
        )
    if len(val) > MAX_STR_LEN:
        raise SchemeRuntimeError(
            f"String exceeds {MAX_STR_LEN} char limit in '{op_name}'", cause_type="OverflowError"
        )
    return val


# --- Pure Arithmetic & Comparison ---


def prim_add(args: list[SchemeValue]) -> int | float:
    if not args:
        return 0
    total: int | float = 0
    for a in args:
        val = _check_number(a, "+")
        total += val
        if isinstance(total, int) and (total > INT_MAX or total < INT_MIN):
            raise SchemeRuntimeError("Integer overflow in '+'", cause_type="OverflowError")
    return total


def prim_sub(args: list[SchemeValue]) -> int | float:
    if not args:
        raise SchemeRuntimeError("'-' requires at least 1 argument", cause_type="ValueError")
    if len(args) == 1:
        val = _check_number(args[0], "-")
        res = -val
        if isinstance(res, int) and (res > INT_MAX or res < INT_MIN):
            raise SchemeRuntimeError("Integer overflow in '-'", cause_type="OverflowError")
        return res
    total = _check_number(args[0], "-")
    for a in args[1:]:
        val = _check_number(a, "-")
        total -= val
        if isinstance(total, int) and (total > INT_MAX or total < INT_MIN):
            raise SchemeRuntimeError("Integer overflow in '-'", cause_type="OverflowError")
    return total


def prim_mul(args: list[SchemeValue]) -> int | float:
    if not args:
        return 1
    total: int | float = 1
    for a in args:
        # Check that 'a' is strictly number; strings are forbidden per Spec 05 §4
        val = _check_number(a, "*")
        total *= val
        if isinstance(total, int) and (total > INT_MAX or total < INT_MIN):
            raise SchemeRuntimeError("Integer overflow in '*'", cause_type="OverflowError")
    return total


def prim_div(args: list[SchemeValue]) -> int | float:
    if not args:
        raise SchemeRuntimeError("'/' requires at least 1 argument", cause_type="ValueError")
    if len(args) == 1:
        first = _check_number(args[0], "/")
        if first == 0:
            raise SchemeRuntimeError("Division by zero in '/'", cause_type="ZeroDivisionError")
        return 1 / first
    res = _check_number(args[0], "/")
    for a in args[1:]:
        val = _check_number(a, "/")
        if val == 0:
            raise SchemeRuntimeError("Division by zero in '/'", cause_type="ZeroDivisionError")
        res = res / val
    if isinstance(res, float) and not math.isfinite(res):
        raise SchemeRuntimeError("Non-finite result in '/'", cause_type="ValueError")
    return res


def prim_eq(args: list[SchemeValue]) -> bool:
    if len(args) != 2:
        raise SchemeRuntimeError(
            f"'=' requires exactly 2 arguments, got {len(args)}", cause_type="ValueError"
        )
    a, b = args
    # Spec 05 §4: type errors for mismatched comparisons if not equal
    return bool(a == b)


def prim_lt(args: list[SchemeValue]) -> bool:
    if len(args) != 2:
        raise SchemeRuntimeError(
            f"'<' requires exactly 2 arguments, got {len(args)}", cause_type="ValueError"
        )
    a = _check_number(args[0], "<")
    b = _check_number(args[1], "<")
    return bool(a < b)


def prim_gt(args: list[SchemeValue]) -> bool:
    if len(args) != 2:
        raise SchemeRuntimeError(
            f"'>' requires exactly 2 arguments, got {len(args)}", cause_type="ValueError"
        )
    a = _check_number(args[0], ">")
    b = _check_number(args[1], ">")
    return bool(a > b)


def prim_lte(args: list[SchemeValue]) -> bool:
    if len(args) != 2:
        raise SchemeRuntimeError(
            f"'<=' requires exactly 2 arguments, got {len(args)}", cause_type="ValueError"
        )
    a = _check_number(args[0], "<=")
    b = _check_number(args[1], "<=")
    return bool(a <= b)


def prim_gte(args: list[SchemeValue]) -> bool:
    if len(args) != 2:
        raise SchemeRuntimeError(
            f"'>=' requires exactly 2 arguments, got {len(args)}", cause_type="ValueError"
        )
    a = _check_number(args[0], ">=")
    b = _check_number(args[1], ">=")
    return bool(a >= b)


def prim_not(args: list[SchemeValue]) -> bool:
    if len(args) != 1:
        raise SchemeRuntimeError(
            f"'not' requires exactly 1 argument, got {len(args)}", cause_type="ValueError"
        )
    # In Scheme, only #f (False) is false. Everything else is truthy.
    return args[0] is False


# --- String & List Helpers ---


def prim_len(args: list[SchemeValue]) -> int:
    if len(args) != 1:
        raise SchemeRuntimeError(
            f"'len' requires exactly 1 argument, got {len(args)}", cause_type="ValueError"
        )
    val = args[0]
    if isinstance(val, (str, list)):
        length = len(val)
        if length > MAX_LIST_LEN:
            raise SchemeRuntimeError(
                f"'len' exceeds maximum element count {MAX_LIST_LEN}", cause_type="OverflowError"
            )
        return length
    raise SchemeRuntimeError(
        f"'len' expects string or list, got {type(val).__name__}", cause_type="TypeError"
    )


def prim_str_contains(args: list[SchemeValue]) -> bool:
    if len(args) != 2:
        raise SchemeRuntimeError(
            f"'str-contains?' requires 2 arguments, got {len(args)}", cause_type="ValueError"
        )
    haystack = _check_str(args[0], "str-contains?")
    needle = _check_str(args[1], "str-contains?")
    return needle in haystack


def prim_str_lower(args: list[SchemeValue]) -> str:
    if len(args) != 1:
        raise SchemeRuntimeError(
            f"'str-lower' requires 1 argument, got {len(args)}", cause_type="ValueError"
        )
    s = _check_str(args[0], "str-lower")
    return s.lower()


def prim_min(args: list[SchemeValue]) -> int | float:
    if not args:
        raise SchemeRuntimeError("'min' requires at least 1 argument", cause_type="ValueError")
    nums = [_check_number(a, "min") for a in args]
    return min(nums)


def prim_max(args: list[SchemeValue]) -> int | float:
    if not args:
        raise SchemeRuntimeError("'max' requires at least 1 argument", cause_type="ValueError")
    nums = [_check_number(a, "max") for a in args]
    return max(nums)


# --- State Predicates ---


def make_state_primitives(
    state: RuleState,
) -> dict[str, Callable[[list[SchemeValue]], SchemeValue]]:
    """Builds a fresh child environment of state predicates for a single RuleState."""

    def prim_intent_eq(args: list[SchemeValue]) -> bool:
        if len(args) != 1:
            raise SchemeRuntimeError("'intent=' requires 1 argument", cause_type="ValueError")
        expected = _check_str(args[0], "intent=")
        return state.intent == expected

    def prim_entity_has(args: list[SchemeValue]) -> bool:
        if len(args) != 2:
            raise SchemeRuntimeError("'entity-has?' requires 2 arguments", cause_type="ValueError")
        cat = _check_str(args[0], "entity-has?")
        val = _check_str(args[1], "entity-has?")
        return val in state.entities.get(cat, [])

    def prim_entity(args: list[SchemeValue]) -> str:
        if len(args) != 1:
            raise SchemeRuntimeError("'entity' requires 1 argument", cause_type="ValueError")
        cat = _check_str(args[0], "entity")
        ents = state.entities.get(cat, [])
        return ents[0] if ents else ""

    def prim_entity_int(args: list[SchemeValue]) -> int:
        if len(args) != 1:
            raise SchemeRuntimeError("'entity-int' requires 1 argument", cause_type="ValueError")
        cat = _check_str(args[0], "entity-int")
        ents = state.entities.get(cat, [])
        if not ents:
            raise SchemeRuntimeError(
                f"'entity-int' entity '{cat}' not found", cause_type="KeyError"
            )
        try:
            return int(ents[0])
        except ValueError as err:
            raise SchemeRuntimeError(
                f"'entity-int' entity '{cat}' value '{ents[0]}' is not an integer",
                cause_type="ValueError",
            ) from err

    def prim_entity_num(args: list[SchemeValue]) -> float:
        if len(args) != 1:
            raise SchemeRuntimeError("'entity-num' requires 1 argument", cause_type="ValueError")
        cat = _check_str(args[0], "entity-num")
        ents = state.entities.get(cat, [])
        if not ents:
            raise SchemeRuntimeError(
                f"'entity-num' entity '{cat}' not found", cause_type="KeyError"
            )
        try:
            return float(ents[0])
        except ValueError as err:
            raise SchemeRuntimeError(
                f"'entity-num' entity '{cat}' value '{ents[0]}' is not a number",
                cause_type="ValueError",
            ) from err

    def prim_entity_str(args: list[SchemeValue]) -> str:
        if len(args) != 1:
            raise SchemeRuntimeError("'entity-str' requires 1 argument", cause_type="ValueError")
        cat = _check_str(args[0], "entity-str")
        ents = state.entities.get(cat, [])
        return str(ents[0]) if ents else ""

    def prim_transcript_has(args: list[SchemeValue]) -> bool:
        if len(args) != 1:
            raise SchemeRuntimeError(
                "'transcript-has?' requires 1 argument", cause_type="ValueError"
            )
        sub = _check_str(args[0], "transcript-has?")
        return sub.lower() in state.transcript_lower

    def prim_transcript_matches_glob(args: list[SchemeValue]) -> bool:
        if len(args) != 1:
            raise SchemeRuntimeError(
                "'transcript-matches-glob?' requires 1 argument", cause_type="ValueError"
            )
        pattern = _check_str(args[0], "transcript-matches-glob?")
        return fnmatch.fnmatch(state.transcript_lower, pattern)

    def prim_app_running(args: list[SchemeValue]) -> bool:
        if len(args) != 1:
            raise SchemeRuntimeError("'app-running?' requires 1 argument", cause_type="ValueError")
        app_name = _check_str(args[0], "app-running?")
        return app_name in state.apps_running

    def prim_hour_between(args: list[SchemeValue]) -> bool:
        if len(args) != 2:
            raise SchemeRuntimeError(
                "'hour-between?' requires 2 arguments", cause_type="ValueError"
            )
        h1 = int(_check_number(args[0], "hour-between?"))
        h2 = int(_check_number(args[1], "hour-between?"))
        return h1 <= state.hour_local <= h2

    def prim_weekday(args: list[SchemeValue]) -> bool:
        if len(args) != 1:
            raise SchemeRuntimeError("'weekday?' requires 1 argument", cause_type="ValueError")
        day = int(_check_number(args[0], "weekday?"))
        return state.weekday == day

    def prim_last_tool_ok(args: list[SchemeValue]) -> bool:
        if len(args) != 0:
            raise SchemeRuntimeError("'last-tool-ok?' takes no arguments", cause_type="ValueError")
        return bool(state.last_tool_ok)

    def prim_last_tool_eq(args: list[SchemeValue]) -> bool:
        if len(args) != 1:
            raise SchemeRuntimeError("'last-tool=' requires 1 argument", cause_type="ValueError")
        tname = _check_str(args[0], "last-tool=")
        return state.last_tool == tname

    def prim_session_turns_gte(args: list[SchemeValue]) -> bool:
        if len(args) != 1:
            raise SchemeRuntimeError(
                "'session-turns>=' requires 1 argument", cause_type="ValueError"
            )
        n = int(_check_number(args[0], "session-turns>="))
        return state.session_turns >= n

    def prim_interrupted(args: list[SchemeValue]) -> bool:
        if len(args) != 0:
            raise SchemeRuntimeError("'interrupted?' takes no arguments", cause_type="ValueError")
        return bool(state.interrupted)

    def prim_fact_exists(args: list[SchemeValue]) -> bool:
        """(fact-exists? (s p o)) or (fact-exists? (s p)) or 2/3 args.

        Tests presence in state.asserted_facts.
        """
        if len(args) == 1 and isinstance(args[0], list):
            items = args[0]
            if len(items) == 3:
                s, p, o = str(items[0]).strip(), str(items[1]).strip().lower(), str(items[2]).strip()
                return (s, p, o) in state.asserted_facts
            elif len(items) == 2:
                s, p = str(items[0]).strip(), str(items[1]).strip().lower()
                return any(fs == s and fp == p for fs, fp, _ in state.asserted_facts)
            else:
                raise SchemeRuntimeError(
                    f"'fact-exists?' expects 2 or 3 pattern elements, got {len(items)}",
                    cause_type="ValueError",
                )
        elif len(args) == 3:
            s, p, o = str(args[0]).strip(), str(args[1]).strip().lower(), str(args[2]).strip()
            return (s, p, o) in state.asserted_facts
        elif len(args) == 2:
            s, p = str(args[0]).strip(), str(args[1]).strip().lower()
            return any(fs == s and fp == p for fs, fp, _ in state.asserted_facts)
        else:
            raise SchemeRuntimeError(
                f"'fact-exists?' requires pattern (s p o) or (s p), got {len(args)} args",
                cause_type="ValueError",
            )

    def prim_fact_value(args: list[SchemeValue]) -> SchemeValue:
        """(fact-value (s p)) or (fact-value s p).

        Returns object 'o' from matching asserted_fact, or False if not found.
        """
        if len(args) == 1 and isinstance(args[0], list):
            items = args[0]
            if len(items) >= 2:
                s, p = str(items[0]).strip(), str(items[1]).strip().lower()
            else:
                raise SchemeRuntimeError(
                    f"'fact-value' requires at least subject and predicate, got {len(items)}",
                    cause_type="ValueError",
                )
        elif len(args) >= 2:
            s, p = str(args[0]).strip(), str(args[1]).strip().lower()
        else:
            raise SchemeRuntimeError(
                f"'fact-value' requires (s p) or 2 arguments, got {len(args)}",
                cause_type="ValueError",
            )

        for fs, fp, fo in state.asserted_facts:
            if fs == s and fp == p:
                return fo
        return False

    return {
        "intent=": prim_intent_eq,
        "entity-has?": prim_entity_has,
        "entity": prim_entity,
        "entity-int": prim_entity_int,
        "entity-num": prim_entity_num,
        "entity-str": prim_entity_str,
        "transcript-has?": prim_transcript_has,
        "transcript-matches-glob?": prim_transcript_matches_glob,
        "app-running?": prim_app_running,
        "hour-between?": prim_hour_between,
        "weekday?": prim_weekday,
        "last-tool-ok?": prim_last_tool_ok,
        "last-tool=": prim_last_tool_eq,
        "session-turns>=": prim_session_turns_gte,
        "interrupted?": prim_interrupted,
        "fact-exists?": prim_fact_exists,
        "fact-value": prim_fact_value,
    }


# --- Plan Construction Primitives ---


def prim_list(args: list[SchemeValue]) -> list[SchemeValue]:
    if len(args) > MAX_LIST_LEN:
        raise SchemeRuntimeError(
            f"'list' exceeds max element count {MAX_LIST_LEN}", cause_type="OverflowError"
        )
    return list(args)


def prim_say(args: list[SchemeValue]) -> Say:
    if len(args) != 1:
        raise SchemeRuntimeError(
            f"'say' requires 1 string argument, got {len(args)}", cause_type="ValueError"
        )
    text = _check_str(args[0], "say")
    return Say(text=text)


def prim_tool(args: list[SchemeValue]) -> ToolCall:
    if not args or not isinstance(args[0], str):
        raise SchemeRuntimeError(
            "'tool' requires tool name as first argument", cause_type="ValueError"
        )
    tool_name = args[0]
    kwargs: dict[str, JsonValue] = {}
    i = 1
    while i < len(args):
        key = args[i]
        if isinstance(key, Keyword):
            clean_key = key.name.lstrip(":")
        elif isinstance(key, str) and key.startswith(":"):
            clean_key = key[1:]
        else:
            raise SchemeRuntimeError(
                f"Expected keyword in tool call, got {key}", cause_type="TypeError"
            )

        if i + 1 >= len(args):
            raise SchemeRuntimeError(
                f"Missing value for keyword {key} in tool call", cause_type="ValueError"
            )

        val = args[i + 1]
        if isinstance(val, (str, int, float, bool)) or val is None:
            kwargs[clean_key] = val
        elif isinstance(val, list):
            kwargs[clean_key] = [
                item if isinstance(item, (str, int, float, bool)) or item is None else str(item)
                for item in val
            ]
        elif isinstance(val, Keyword):
            kwargs[clean_key] = val.name
        else:
            raise SchemeRuntimeError(
                f"Unsupported argument value type in tool call: {type(val).__name__}",
                cause_type="TypeError",
            )
        i += 2

    return ToolCall(tool=tool_name, args=kwargs, call_id=f"rule-call-{uuid.uuid4().hex[:8]}")


def prim_yield_to_core(args: list[SchemeValue]) -> SchemeValue:
    """
    (yield-to-core reason [context-dict-or-pairs])
    Raises SchemeYieldSignal to transfer S1 control to System 2 with optional context.
    """
    if not args:
        raise SchemeRuntimeError(
            "'yield-to-core' requires at least a reason string", cause_type="ValueError"
        )
    reason = _check_str(args[0], "yield-to-core")
    context: dict[str, object] = {}
    if len(args) > 1:
        i = 1
        while i < len(args):
            k = args[i]
            k_name = k.name.lstrip(":") if isinstance(k, Keyword) else str(k).lstrip(":")
            if i + 1 < len(args):
                context[k_name] = args[i + 1]
                i += 2
            else:
                context[k_name] = True
                i += 1
    raise SchemeYieldSignal(reason=reason, context=context)


def prim_interrupt_core(args: list[SchemeValue]) -> SchemeValue:
    """
    (interrupt-core [reason])
    Raises SchemeInterruptSignal to abort execution immediately.
    """
    reason = "Emergency interrupt triggered"
    if args:
        reason = _check_str(args[0], "interrupt-core")
    raise SchemeInterruptSignal(reason=reason)


def prim_assert(args: list[SchemeValue]) -> AssertFact:
    """(assert (s p o)) or (assert s p o) -> AssertFact.

    Pure plan action construction per D-REAS-05 / D-REAS-09 (Trap 1).
    No side effects or store writes occur in the primitive.
    """
    if len(args) == 1 and isinstance(args[0], list):
        items = args[0]
        if len(items) != 3:
            raise SchemeRuntimeError(
                f"'assert' requires a triple (s p o), got list of length {len(items)}",
                cause_type="ValueError",
            )
        s, p, o = str(items[0]), str(items[1]), str(items[2])
    elif len(args) == 3:
        s, p, o = str(args[0]), str(args[1]), str(args[2])
    else:
        raise SchemeRuntimeError(
            f"'assert' requires a triple (s p o) or 3 arguments, got {len(args)}",
            cause_type="ValueError",
        )

    clean_p = p.strip().lower()
    if not is_valid_predicate(clean_p):
        raise SchemeRuntimeError(
            f"Invalid predicate '{p}' in assert action", cause_type="ValueError"
        )
    return AssertFact(s=s.strip(), p=clean_p, o=o.strip())


# --- Spatial & Geometric DSL Primitives (WO-29 Module 1) ---


def _to_point_2d(val: SchemeValue, op_name: str) -> tuple[float, float]:
    if isinstance(val, list):
        items = val
        if len(items) >= 3 and (
            items[0] == "point"
            or (isinstance(items[0], Symbol) and items[0].name == "point")
            or items[0] == "vec"
            or (isinstance(items[0], Symbol) and items[0].name == "vec")
        ):
            items = items[1:]
        if len(items) >= 2:
            return float(_check_number(items[0], op_name)), float(_check_number(items[1], op_name))
    raise SchemeRuntimeError(
        f"Operator '{op_name}' expects 2D point [x, y] or (point x y), got {val}",
        cause_type="TypeError",
    )


def prim_point(args: list[SchemeValue]) -> list[SchemeValue]:
    if len(args) == 2:
        x = _check_number(args[0], "point")
        y = _check_number(args[1], "point")
        return ["point", x, y]
    elif len(args) == 3:
        x = _check_number(args[0], "point")
        y = _check_number(args[1], "point")
        z = _check_number(args[2], "point")
        return ["point", x, y, z]
    raise SchemeRuntimeError(
        f"'point' requires 2 or 3 coordinates, got {len(args)}", cause_type="ValueError"
    )


def prim_vec(args: list[SchemeValue]) -> list[SchemeValue]:
    if len(args) == 2:
        dx = _check_number(args[0], "vec")
        dy = _check_number(args[1], "vec")
        return ["vec", dx, dy]
    elif len(args) == 3:
        dx = _check_number(args[0], "vec")
        dy = _check_number(args[1], "vec")
        dz = _check_number(args[2], "vec")
        return ["vec", dx, dy, dz]
    raise SchemeRuntimeError(
        f"'vec' requires 2 or 3 components, got {len(args)}", cause_type="ValueError"
    )


def prim_rect(args: list[SchemeValue]) -> list[SchemeValue]:
    if len(args) != 4:
        raise SchemeRuntimeError(
            f"'rect' requires 4 arguments (x y w h), got {len(args)}", cause_type="ValueError"
        )
    x = _check_number(args[0], "rect")
    y = _check_number(args[1], "rect")
    w = _check_number(args[2], "rect")
    h = _check_number(args[3], "rect")
    if w < 0 or h < 0:
        raise SchemeRuntimeError(
            f"'rect' width and height must be non-negative, got w={w}, h={h}", cause_type="ValueError"
        )
    return ["rect", x, y, w, h]


def prim_circle(args: list[SchemeValue]) -> list[SchemeValue]:
    if len(args) == 2:
        cx, cy = _to_point_2d(args[0], "circle")
        r = _check_number(args[1], "circle")
    elif len(args) == 3:
        cx = _check_number(args[0], "circle")
        cy = _check_number(args[1], "circle")
        r = _check_number(args[2], "circle")
    else:
        raise SchemeRuntimeError(
            f"'circle' requires (center r) or (cx cy r), got {len(args)} args",
            cause_type="ValueError",
        )
    if r < 0:
        raise SchemeRuntimeError(
            f"'circle' radius must be non-negative, got r={r}", cause_type="ValueError"
        )
    return ["circle", cx, cy, r]


def prim_polygon(args: list[SchemeValue]) -> list[SchemeValue]:
    pts: list[tuple[float, float]] = []
    if len(args) == 1 and isinstance(args[0], list):
        raw_pts = args[0]
    else:
        raw_pts = args
    for p in raw_pts:
        pts.append(_to_point_2d(p, "polygon"))
    if len(pts) < 3:
        raise SchemeRuntimeError(
            f"'polygon' requires at least 3 vertices, got {len(pts)}", cause_type="ValueError"
        )
    return ["polygon", *[["point", p[0], p[1]] for p in pts]]


def prim_distance(args: list[SchemeValue]) -> float:
    if len(args) == 2:
        p1 = _to_point_2d(args[0], "distance")
        p2 = _to_point_2d(args[1], "distance")
        return math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    elif len(args) == 4:
        x1 = float(_check_number(args[0], "distance"))
        y1 = float(_check_number(args[1], "distance"))
        x2 = float(_check_number(args[2], "distance"))
        y2 = float(_check_number(args[3], "distance"))
        return math.hypot(x2 - x1, y2 - y1)
    raise SchemeRuntimeError(
        f"'distance' requires 2 points or 4 coordinates (x1 y1 x2 y2), got {len(args)} args",
        cause_type="ValueError",
    )


def prim_translate(args: list[SchemeValue]) -> SchemeValue:
    if len(args) != 3:
        raise SchemeRuntimeError(
            f"'translate' requires 3 arguments (shape dx dy), got {len(args)}",
            cause_type="ValueError",
        )
    shape = args[0]
    dx = float(_check_number(args[1], "translate"))
    dy = float(_check_number(args[2], "translate"))

    if not isinstance(shape, list) or not shape:
        raise SchemeRuntimeError(f"'translate' expects a shape list, got {shape}", cause_type="TypeError")

    tag = shape[0].name if isinstance(shape[0], Symbol) else str(shape[0])

    if tag == "point":
        return ["point", float(shape[1]) + dx, float(shape[2]) + dy]
    elif tag == "rect":
        return ["rect", float(shape[1]) + dx, float(shape[2]) + dy, shape[3], shape[4]]
    elif tag == "circle":
        return ["circle", float(shape[1]) + dx, float(shape[2]) + dy, shape[3]]
    elif tag == "polygon":
        new_pts = [
            ["point", float(p[1]) + dx, float(p[2]) + dy]
            for p in shape[1:]
            if isinstance(p, list) and len(p) >= 3
        ]
        return ["polygon", *new_pts]
    elif tag == "vec":
        return ["vec", shape[1], shape[2]]
    else:
        raise SchemeRuntimeError(f"Unsupported shape type in 'translate': {tag}", cause_type="ValueError")


def prim_rotate(args: list[SchemeValue]) -> SchemeValue:
    if len(args) < 2 or len(args) > 4:
        raise SchemeRuntimeError(
            f"'rotate' requires (shape theta [ox oy]), got {len(args)} args", cause_type="ValueError"
        )
    shape = args[0]
    theta = float(_check_number(args[1], "rotate"))
    ox, oy = 0.0, 0.0
    if len(args) == 3:
        ox, oy = _to_point_2d(args[2], "rotate")
    elif len(args) == 4:
        ox = float(_check_number(args[2], "rotate"))
        oy = float(_check_number(args[3], "rotate"))

    if not isinstance(shape, list) or not shape:
        raise SchemeRuntimeError(f"'rotate' expects a shape list, got {shape}", cause_type="TypeError")

    tag = shape[0].name if isinstance(shape[0], Symbol) else str(shape[0])
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    def rot_xy(x: float, y: float) -> tuple[float, float]:
        rx = ox + (x - ox) * cos_t - (y - oy) * sin_t
        ry = oy + (x - ox) * sin_t + (y - oy) * cos_t
        return rx, ry

    if tag == "point":
        rx, ry = rot_xy(float(shape[1]), float(shape[2]))
        return ["point", rx, ry]
    elif tag == "circle":
        rx, ry = rot_xy(float(shape[1]), float(shape[2]))
        return ["circle", rx, ry, shape[3]]
    elif tag == "rect":
        x, y, w, h = float(shape[1]), float(shape[2]), float(shape[3]), float(shape[4])
        pts = [
            rot_xy(x, y),
            rot_xy(x + w, y),
            rot_xy(x + w, y + h),
            rot_xy(x, y + h),
        ]
        return ["polygon", *[["point", px, py] for px, py in pts]]
    elif tag == "polygon":
        new_pts = []
        for p in shape[1:]:
            if isinstance(p, list) and len(p) >= 3:
                rx, ry = rot_xy(float(p[1]), float(p[2]))
                new_pts.append(["point", rx, ry])
        return ["polygon", *new_pts]
    else:
        raise SchemeRuntimeError(f"Unsupported shape type in 'rotate': {tag}", cause_type="ValueError")


def prim_scale(args: list[SchemeValue]) -> SchemeValue:
    if len(args) < 2 or len(args) > 4:
        raise SchemeRuntimeError(
            f"'scale' requires (shape factor [ox oy]), got {len(args)} args", cause_type="ValueError"
        )
    shape = args[0]
    factor = float(_check_number(args[1], "scale"))
    ox, oy = 0.0, 0.0
    if len(args) == 3:
        ox, oy = _to_point_2d(args[2], "scale")
    elif len(args) == 4:
        ox = float(_check_number(args[2], "scale"))
        oy = float(_check_number(args[3], "scale"))

    if not isinstance(shape, list) or not shape:
        raise SchemeRuntimeError(f"'scale' expects a shape list, got {shape}", cause_type="TypeError")

    tag = shape[0].name if isinstance(shape[0], Symbol) else str(shape[0])

    def scale_xy(x: float, y: float) -> tuple[float, float]:
        return ox + (x - ox) * factor, oy + (y - oy) * factor

    if tag == "point":
        sx, sy = scale_xy(float(shape[1]), float(shape[2]))
        return ["point", sx, sy]
    elif tag == "rect":
        x, y, w, h = float(shape[1]), float(shape[2]), float(shape[3]), float(shape[4])
        sx, sy = scale_xy(x, y)
        return ["rect", sx, sy, w * factor, h * factor]
    elif tag == "circle":
        cx, cy, r = float(shape[1]), float(shape[2]), float(shape[3])
        scx, scy = scale_xy(cx, cy)
        return ["circle", scx, scy, abs(r * factor)]
    elif tag == "polygon":
        new_pts = []
        for p in shape[1:]:
            if isinstance(p, list) and len(p) >= 3:
                sx, sy = scale_xy(float(p[1]), float(p[2]))
                new_pts.append(["point", sx, sy])
        return ["polygon", *new_pts]
    else:
        raise SchemeRuntimeError(f"Unsupported shape type in 'scale': {tag}", cause_type="ValueError")


def prim_bounding_box(args: list[SchemeValue]) -> list[SchemeValue]:
    if len(args) != 1:
        raise SchemeRuntimeError(f"'bounding-box' requires 1 argument, got {len(args)}", cause_type="ValueError")
    shape = args[0]
    if not isinstance(shape, list) or not shape:
        raise SchemeRuntimeError(f"'bounding-box' expects shape list, got {shape}", cause_type="TypeError")

    tag = shape[0].name if isinstance(shape[0], Symbol) else str(shape[0])

    if tag == "point":
        return ["rect", shape[1], shape[2], 0, 0]
    elif tag == "rect":
        return ["rect", shape[1], shape[2], shape[3], shape[4]]
    elif tag == "circle":
        cx, cy, r = float(shape[1]), float(shape[2]), float(shape[3])
        return ["rect", cx - r, cy - r, 2 * r, 2 * r]
    elif tag == "polygon":
        xs = [float(p[1]) for p in shape[1:] if isinstance(p, list) and len(p) >= 3]
        ys = [float(p[2]) for p in shape[1:] if isinstance(p, list) and len(p) >= 3]
        if not xs or not ys:
            raise SchemeRuntimeError("Empty polygon in 'bounding-box'", cause_type="ValueError")
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return ["rect", min_x, min_y, max_x - min_x, max_y - min_y]
    else:
        raise SchemeRuntimeError(f"Unsupported shape in 'bounding-box': {tag}", cause_type="ValueError")


def prim_contains(args: list[SchemeValue]) -> bool:
    if len(args) == 2:
        shape = args[0]
        px, py = _to_point_2d(args[1], "contains?")
    elif len(args) == 3:
        shape = args[0]
        px = float(_check_number(args[1], "contains?"))
        py = float(_check_number(args[2], "contains?"))
    else:
        raise SchemeRuntimeError(
            f"'contains?' requires (shape pt) or (shape px py), got {len(args)} args",
            cause_type="ValueError",
        )

    if not isinstance(shape, list) or not shape:
        raise SchemeRuntimeError(f"'contains?' expects shape list, got {shape}", cause_type="TypeError")

    tag = shape[0].name if isinstance(shape[0], Symbol) else str(shape[0])

    if tag == "rect":
        rx, ry, rw, rh = float(shape[1]), float(shape[2]), float(shape[3]), float(shape[4])
        return rx <= px <= rx + rw and ry <= py <= ry + rh
    elif tag == "circle":
        cx, cy, r = float(shape[1]), float(shape[2]), float(shape[3])
        return (px - cx) ** 2 + (py - cy) ** 2 <= (r**2) + 1e-9
    elif tag == "polygon":
        # Ray casting point-in-polygon algorithm
        vertices = [
            (float(p[1]), float(p[2]))
            for p in shape[1:]
            if isinstance(p, list) and len(p) >= 3
        ]
        n = len(vertices)
        if n < 3:
            return False
        inside = False
        p1x, p1y = vertices[0]
        for i in range(1, n + 1):
            p2x, p2y = vertices[i % n]
            if py > min(p1y, p2y):
                if py <= max(p1y, p2y):
                    if px <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (py - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or px <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside
    elif tag == "point":
        return abs(float(shape[1]) - px) < 1e-9 and abs(float(shape[2]) - py) < 1e-9
    else:
        raise SchemeRuntimeError(f"Unsupported shape in 'contains?': {tag}", cause_type="ValueError")


def prim_intersects(args: list[SchemeValue]) -> bool:
    if len(args) != 2:
        raise SchemeRuntimeError(f"'intersects?' requires 2 shapes, got {len(args)}", cause_type="ValueError")
    bb1 = prim_bounding_box([args[0]])
    bb2 = prim_bounding_box([args[1]])
    x1, y1, w1, h1 = float(bb1[1]), float(bb1[2]), float(bb1[3]), float(bb1[4])
    x2, y2, w2, h2 = float(bb2[1]), float(bb2[2]), float(bb2[3]), float(bb2[4])
    # AABB overlap check
    return not (x1 + w1 < x2 or x2 + w2 < x1 or y1 + h1 < y2 or y2 + h2 < y1)


def prim_area(args: list[SchemeValue]) -> float:
    if len(args) != 1:
        raise SchemeRuntimeError(f"'area' requires 1 shape, got {len(args)}", cause_type="ValueError")
    shape = args[0]
    if not isinstance(shape, list) or not shape:
        raise SchemeRuntimeError(f"'area' expects shape list, got {shape}", cause_type="TypeError")

    tag = shape[0].name if isinstance(shape[0], Symbol) else str(shape[0])

    if tag == "rect":
        return float(shape[3]) * float(shape[4])
    elif tag == "circle":
        return math.pi * (float(shape[3]) ** 2)
    elif tag == "polygon":
        vertices = [
            (float(p[1]), float(p[2]))
            for p in shape[1:]
            if isinstance(p, list) and len(p) >= 3
        ]
        n = len(vertices)
        if n < 3:
            return 0.0
        # Shoelace formula
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += vertices[i][0] * vertices[j][1]
            area -= vertices[j][0] * vertices[i][1]
        return 0.5 * abs(area)
    elif tag in ("point", "vec"):
        return 0.0
    else:
        raise SchemeRuntimeError(f"Unsupported shape in 'area': {tag}", cause_type="ValueError")


def prim_perimeter(args: list[SchemeValue]) -> float:
    if len(args) != 1:
        raise SchemeRuntimeError(f"'perimeter' requires 1 shape, got {len(args)}", cause_type="ValueError")
    shape = args[0]
    if not isinstance(shape, list) or not shape:
        raise SchemeRuntimeError(f"'perimeter' expects shape list, got {shape}", cause_type="TypeError")

    tag = shape[0].name if isinstance(shape[0], Symbol) else str(shape[0])

    if tag == "rect":
        return 2.0 * (float(shape[3]) + float(shape[4]))
    elif tag == "circle":
        return 2.0 * math.pi * float(shape[3])
    elif tag == "polygon":
        vertices = [
            (float(p[1]), float(p[2]))
            for p in shape[1:]
            if isinstance(p, list) and len(p) >= 3
        ]
        n = len(vertices)
        if n < 2:
            return 0.0
        perim = 0.0
        for i in range(n):
            j = (i + 1) % n
            perim += math.hypot(vertices[j][0] - vertices[i][0], vertices[j][1] - vertices[i][1])
        return perim
    elif tag in ("point", "vec"):
        return 0.0
    else:
        raise SchemeRuntimeError(f"Unsupported shape in 'perimeter': {tag}", cause_type="ValueError")


# Frozen static primitives table
PURE_PRIMITIVES: dict[str, Callable[[list[SchemeValue]], SchemeValue]] = {
    "+": prim_add,
    "-": prim_sub,
    "*": prim_mul,
    "/": prim_div,
    "=": prim_eq,
    "<": prim_lt,
    ">": prim_gt,
    "<=": prim_lte,
    ">=": prim_gte,
    "not": prim_not,
    "len": prim_len,
    "str-contains?": prim_str_contains,
    "str-lower": prim_str_lower,
    "min": prim_min,
    "max": prim_max,
    "list": prim_list,
    "say": prim_say,
    "tool": prim_tool,
    "assert": prim_assert,
    "yield-to-core": prim_yield_to_core,
    "interrupt-core": prim_interrupt_core,
    # Spatial & Geometric DSL (WO-29 Module 1)
    "point": prim_point,
    "vec": prim_vec,
    "rect": prim_rect,
    "circle": prim_circle,
    "polygon": prim_polygon,
    "distance": prim_distance,
    "translate": prim_translate,
    "rotate": prim_rotate,
    "scale": prim_scale,
    "bounding-box": prim_bounding_box,
    "contains?": prim_contains,
    "intersects?": prim_intersects,
    "intersect": prim_intersects,
    "area": prim_area,
    "perimeter": prim_perimeter,
}
