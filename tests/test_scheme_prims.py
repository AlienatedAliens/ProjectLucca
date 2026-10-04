"""
Direct unit tests for MicroScheme v2 Primitives Table & State Bindings.
lucca.reasoning.scheme.prims
Spec 05 §2, §4, §5
"""

import math
import pytest

from lucca.core.exceptions import (
    SchemeInterruptSignal,
    SchemeRuntimeError,
    SchemeYieldSignal,
)
from lucca.core.schemas import AssertFact, RuleState, Say, ToolCall
from lucca.reasoning.scheme.parser import Keyword
from lucca.reasoning.scheme.prims import (
    INT_MAX,
    INT_MIN,
    MAX_LIST_LEN,
    MAX_STR_LEN,
    PURE_PRIMITIVES,
    _check_number,
    _check_str,
    make_state_primitives,
    prim_add,
    prim_assert,
    prim_div,
    prim_eq,
    prim_gt,
    prim_gte,
    prim_interrupt_core,
    prim_len,
    prim_list,
    prim_lt,
    prim_lte,
    prim_max,
    prim_min,
    prim_mul,
    prim_not,
    prim_say,
    prim_str_contains,
    prim_str_lower,
    prim_sub,
    prim_tool,
    prim_yield_to_core,
)


def test_pure_primitives_table_completeness() -> None:
    """PURE_PRIMITIVES contains all expected primitive operators."""
    expected_ops = {
        "+", "-", "*", "/", "=", "<", ">", "<=", ">=", "not",
        "len", "str-contains?", "str-lower", "min", "max",
        "list", "say", "tool", "assert", "yield-to-core", "interrupt-core",
        # Spatial & Geometric DSL (WO-29)
        "point", "vec", "rect", "circle", "polygon", "distance",
        "translate", "rotate", "scale", "bounding-box", "contains?",
        "intersects?", "intersect", "area", "perimeter",
    }
    assert set(PURE_PRIMITIVES.keys()) == expected_ops


def test_check_number_type_and_bounds() -> None:
    """_check_number enforces numeric types, finite floats, and integer bounds."""
    assert _check_number(42, "test") == 42
    assert _check_number(-3.14, "test") == -3.14
    assert _check_number(INT_MAX, "test") == INT_MAX
    assert _check_number(INT_MIN, "test") == INT_MIN

    # Booleans are rejected (not treated as 0/1)
    with pytest.raises(SchemeRuntimeError) as exc:
        _check_number(True, "test")
    assert exc.value.cause_type == "TypeError"

    # Strings/lists rejected
    with pytest.raises(SchemeRuntimeError) as exc:
        _check_number("123", "test")
    assert exc.value.cause_type == "TypeError"

    # Non-finite floats rejected
    with pytest.raises(SchemeRuntimeError) as exc:
        _check_number(float("inf"), "test")
    assert exc.value.cause_type == "ValueError"

    with pytest.raises(SchemeRuntimeError) as exc:
        _check_number(float("nan"), "test")
    assert exc.value.cause_type == "ValueError"

    # Out of bounds integers rejected
    with pytest.raises(SchemeRuntimeError) as exc:
        _check_number(INT_MAX + 1, "test")
    assert exc.value.cause_type == "OverflowError"

    with pytest.raises(SchemeRuntimeError) as exc:
        _check_number(INT_MIN - 1, "test")
    assert exc.value.cause_type == "OverflowError"


def test_check_str_type_and_bounds() -> None:
    """_check_str enforces string type and MAX_STR_LEN limit (4,096)."""
    assert _check_str("hello", "test") == "hello"
    exact_str = "a" * MAX_STR_LEN
    assert _check_str(exact_str, "test") == exact_str

    with pytest.raises(SchemeRuntimeError) as exc:
        _check_str(123, "test")  # type: ignore[arg-type]
    assert exc.value.cause_type == "TypeError"

    # Over MAX_STR_LEN
    with pytest.raises(SchemeRuntimeError) as exc:
        _check_str(exact_str + "b", "test")
    assert exc.value.cause_type == "OverflowError"


def test_primitive_arithmetic() -> None:
    """Arithmetic primitives: +, -, *, /."""
    # Addition
    assert prim_add([]) == 0
    assert prim_add([1, 2, 3]) == 6
    assert prim_add([1.5, 2.5]) == 4.0
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_add([INT_MAX, 1])
    assert exc.value.cause_type == "OverflowError"

    # Subtraction
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_sub([])
    assert exc.value.cause_type == "ValueError"
    assert prim_sub([5]) == -5
    assert prim_sub([10, 3, 2]) == 5
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_sub([INT_MIN, 1])
    assert exc.value.cause_type == "OverflowError"

    # Multiplication
    assert prim_mul([]) == 1
    assert prim_mul([2, 3, 4]) == 24
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_mul([INT_MAX, 2])
    assert exc.value.cause_type == "OverflowError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_mul(["a", 2])
    assert exc.value.cause_type == "TypeError"

    # Division
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_div([])
    assert exc.value.cause_type == "ValueError"
    assert prim_div([2]) == 0.5
    assert prim_div([12, 3, 2]) == 2.0
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_div([10, 0])
    assert exc.value.cause_type == "ZeroDivisionError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_div([0])
    assert exc.value.cause_type == "ZeroDivisionError"


def test_primitive_comparisons() -> None:
    """Comparison primitives: =, <, >, <=, >=."""
    # Equality (=)
    assert prim_eq([1, 1]) is True
    assert prim_eq([1, 2]) is False
    assert prim_eq(["a", "a"]) is True
    assert prim_eq(["a", "b"]) is False
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_eq([1])
    assert exc.value.cause_type == "ValueError"

    # Ordered comparisons (<, >, <=, >=)
    assert prim_lt([1, 2]) is True
    assert prim_lt([2, 1]) is False
    assert prim_gt([3, 2]) is True
    assert prim_gt([2, 3]) is False
    assert prim_lte([2, 2]) is True
    assert prim_lte([3, 2]) is False
    assert prim_gte([2, 2]) is True
    assert prim_gte([1, 2]) is False

    with pytest.raises(SchemeRuntimeError) as exc:
        prim_lt([1])
    assert exc.value.cause_type == "ValueError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_lt(["a", 1])
    assert exc.value.cause_type == "TypeError"


def test_primitive_not_scheme_truthiness() -> None:
    """prim_not implements Scheme truthiness (only #f/False is falsy)."""
    assert prim_not([False]) is True
    assert prim_not([True]) is False
    assert prim_not([0]) is False  # 0 is truthy in Scheme
    assert prim_not([""]) is False  # empty string is truthy in Scheme
    assert prim_not([[]]) is False  # empty list is truthy in Scheme

    with pytest.raises(SchemeRuntimeError) as exc:
        prim_not([])
    assert exc.value.cause_type == "ValueError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_not([True, False])
    assert exc.value.cause_type == "ValueError"


def test_primitive_string_and_list() -> None:
    """String and list helpers: len, str-contains?, str-lower, min, max, list."""
    # len
    assert prim_len(["hello"]) == 5
    assert prim_len([[1, 2, 3]]) == 3
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_len([42])
    assert exc.value.cause_type == "TypeError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_len([[0] * (MAX_LIST_LEN + 1)])
    assert exc.value.cause_type == "OverflowError"

    # str-contains?
    assert prim_str_contains(["hello world", "world"]) is True
    assert prim_str_contains(["hello world", "xyz"]) is False
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_str_contains(["hello"])
    assert exc.value.cause_type == "ValueError"

    # str-lower
    assert prim_str_lower(["Hello World!"]) == "hello world!"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_str_lower([])
    assert exc.value.cause_type == "ValueError"

    # min / max
    assert prim_min([3, 1, 4, 1, 5]) == 1
    assert prim_max([3, 1, 4, 1, 5]) == 5
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_min([])
    assert exc.value.cause_type == "ValueError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_max([])
    assert exc.value.cause_type == "ValueError"

    # list
    assert prim_list([1, "a", True]) == [1, "a", True]
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_list([0] * (MAX_LIST_LEN + 1))
    assert exc.value.cause_type == "OverflowError"


def test_primitive_action_constructors() -> None:
    """Plan action construction: say, tool, yield-to-core, interrupt-core, assert."""
    # say
    say_action = prim_say(["hello"])
    assert isinstance(say_action, Say)
    assert say_action.text == "hello"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_say([])
    assert exc.value.cause_type == "ValueError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_say([123])
    assert exc.value.cause_type == "TypeError"

    # tool
    tool_action = prim_tool(["launch_app", Keyword(":app"), "calc", Keyword(":force"), True])
    assert isinstance(tool_action, ToolCall)
    assert tool_action.tool == "launch_app"
    assert tool_action.args == {"app": "calc", "force": True}
    assert tool_action.call_id.startswith("rule-call-")

    # tool with list arg
    tool_list_arg = prim_tool(["run_cmd", Keyword(":args"), ["a", "b"]])
    assert tool_list_arg.args == {"args": ["a", "b"]}

    # tool errors
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_tool([])
    assert exc.value.cause_type == "ValueError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_tool([123])
    assert exc.value.cause_type == "ValueError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_tool(["tool_name", "not_a_keyword", "val"])
    assert exc.value.cause_type == "TypeError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_tool(["tool_name", Keyword(":app")])
    assert exc.value.cause_type == "ValueError"

    # yield-to-core raises SchemeYieldSignal
    with pytest.raises(SchemeYieldSignal) as yield_exc:
        prim_yield_to_core(["Need human clarification", Keyword(":topic"), "calendar"])
    assert yield_exc.value.reason == "Need human clarification"
    assert yield_exc.value.context == {"topic": "calendar"}

    with pytest.raises(SchemeRuntimeError) as exc:
        prim_yield_to_core([])
    assert exc.value.cause_type == "ValueError"

    # interrupt-core raises SchemeInterruptSignal
    with pytest.raises(SchemeInterruptSignal) as intr_exc:
        prim_interrupt_core([])
    assert intr_exc.value.reason == "Emergency interrupt triggered"

    with pytest.raises(SchemeInterruptSignal) as intr_exc2:
        prim_interrupt_core(["Immediate abort requested"])
    assert intr_exc2.value.reason == "Immediate abort requested"

    # assert
    assert_fact = prim_assert(["alice", "likes", "bob"])
    assert isinstance(assert_fact, AssertFact)
    assert assert_fact.s == "alice"
    assert assert_fact.p == "likes"
    assert assert_fact.o == "bob"

    assert_triple = prim_assert([["alice", "likes", "bob"]])
    assert assert_triple == assert_fact

    with pytest.raises(SchemeRuntimeError) as exc:
        prim_assert(["alice", "unauthorized_claim", "bob"])
    assert exc.value.cause_type == "ValueError"
    with pytest.raises(SchemeRuntimeError) as exc:
        prim_assert(["alice", "likes"])
    assert exc.value.cause_type == "ValueError"


def test_make_state_primitives_bindings() -> None:
    """make_state_primitives provides correct behavior against a RuleState fixture."""
    state = RuleState(
        schema_version=1,
        intent="launch_app",
        intent_conf=0.95,
        entities={"app": ["calculator"], "count": ["42"], "ratio": ["3.14"], "bad_int": ["xyz"]},
        transcript="Please launch the Calculator application.",
        transcript_lower="please launch the calculator application.",
        apps_running=frozenset(["chrome", "notepad"]),
        hour_local=14,
        weekday=2,
        last_tool="read_file",
        last_tool_ok=True,
        session_turns=5,
        mode="audio",
        interrupted=False,
        asserted_facts=[("alice", "likes", "bob"), ("carol", "lives_in", "paris")],
    )

    prims = make_state_primitives(state)

    # intent=
    assert prims["intent="](["launch_app"]) is True
    assert prims["intent="](["other_intent"]) is False

    # entity-has?
    assert prims["entity-has?"](["app", "calculator"]) is True
    assert prims["entity-has?"](["app", "terminal"]) is False
    assert prims["entity-has?"](["missing_cat", "x"]) is False

    # entity
    assert prims["entity"](["app"]) == "calculator"
    assert prims["entity"](["missing_cat"]) == ""

    # entity-int
    assert prims["entity-int"](["count"]) == 42
    # Missing key raises KeyError
    with pytest.raises(SchemeRuntimeError) as exc:
        prims["entity-int"](["missing_key"])
    assert exc.value.cause_type == "KeyError"
    # Non-integer raises ValueError
    with pytest.raises(SchemeRuntimeError) as exc:
        prims["entity-int"](["bad_int"])
    assert exc.value.cause_type == "ValueError"

    # entity-num
    assert prims["entity-num"](["ratio"]) == 3.14
    assert prims["entity-num"](["count"]) == 42.0
    # Missing key raises KeyError
    with pytest.raises(SchemeRuntimeError) as exc:
        prims["entity-num"](["missing_key"])
    assert exc.value.cause_type == "KeyError"
    # Non-float raises ValueError
    with pytest.raises(SchemeRuntimeError) as exc:
        prims["entity-num"](["bad_int"])
    assert exc.value.cause_type == "ValueError"

    # entity-str
    assert prims["entity-str"](["app"]) == "calculator"
    assert prims["entity-str"](["missing_cat"]) == ""

    # transcript-has?
    assert prims["transcript-has?"](["calculator"]) is True
    assert prims["transcript-has?"](["terminal"]) is False

    # transcript-matches-glob?
    assert prims["transcript-matches-glob?"](["*calculator*"]) is True
    assert prims["transcript-matches-glob?"](["*terminal*"]) is False

    # app-running?
    assert prims["app-running?"](["chrome"]) is True
    assert prims["app-running?"](["calculator"]) is False

    # hour-between?
    assert prims["hour-between?"]([10, 16]) is True
    assert prims["hour-between?"]([15, 20]) is False

    # weekday?
    assert prims["weekday?"]([2]) is True
    assert prims["weekday?"]([3]) is False

    # last-tool-ok?
    assert prims["last-tool-ok?"]([]) is True

    # last-tool=
    assert prims["last-tool="](["read_file"]) is True
    assert prims["last-tool="](["launch_app"]) is False

    # session-turns>=
    assert prims["session-turns>="]([5]) is True
    assert prims["session-turns>="]([6]) is False

    # interrupted?
    assert prims["interrupted?"]([]) is False

    # fact-exists?
    assert prims["fact-exists?"](["alice", "likes", "bob"]) is True
    assert prims["fact-exists?"](["alice", "likes"]) is True
    assert prims["fact-exists?"](["alice", "dislikes"]) is False
    assert prims["fact-exists?"]([["alice", "likes", "bob"]]) is True
    assert prims["fact-exists?"]([["alice", "likes"]]) is True

    # fact-value
    assert prims["fact-value"](["alice", "likes"]) == "bob"
    assert prims["fact-value"](["carol", "lives_in"]) == "paris"
    assert prims["fact-value"](["alice", "dislikes"]) is False
    assert prims["fact-value"]([["alice", "likes"]]) == "bob"
