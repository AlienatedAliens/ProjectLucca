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
from lucca.core.schemas import RuleState, Say, ToolCall
from lucca.reasoning.scheme.parser import Keyword, SchemeValue

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
    "yield-to-core": prim_yield_to_core,
    "interrupt-core": prim_interrupt_core,
}
