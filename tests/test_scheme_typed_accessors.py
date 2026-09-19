"""
Tests for Proposal F / D-SEC-04: Typed MicroScheme Entity Accessors.
"""

import pytest

from lucca.core.exceptions import SchemeRuntimeError
from lucca.core.schemas import RuleState
from lucca.reasoning.scheme.eval import evaluate_expr
from lucca.reasoning.scheme.parser import parse


def test_entity_int_success() -> None:
    state = RuleState(
        transcript="set timer for 15 minutes",
        transcript_lower="set timer for 15 minutes",
        intent="set_timer",
        entities={"minutes": ["15"], "invalid": ["abc"]},
        apps_running=[],
        hour_local=12,
        weekday=1,
        session_turns=1,
        last_tool=None,
        last_tool_ok=None,
    )
    ast = parse('(entity-int "minutes")')
    res = evaluate_expr(ast, state=state)
    assert res == 15


def test_entity_int_invalid_raises() -> None:
    state = RuleState(
        transcript="set timer for abc minutes",
        transcript_lower="set timer for abc minutes",
        intent="set_timer",
        entities={"invalid": ["abc"]},
        apps_running=[],
        hour_local=12,
        weekday=1,
        session_turns=1,
        last_tool=None,
        last_tool_ok=None,
    )
    ast = parse('(entity-int "invalid")')
    with pytest.raises(SchemeRuntimeError, match="is not an integer"):
        evaluate_expr(ast, state=state)


def test_entity_num_success() -> None:
    state = RuleState(
        transcript="calculate 3.1415",
        transcript_lower="calculate 3.1415",
        intent="calc",
        entities={"val": ["3.1415"]},
        apps_running=[],
        hour_local=12,
        weekday=1,
        session_turns=1,
        last_tool=None,
        last_tool_ok=None,
    )
    ast = parse('(entity-num "val")')
    res = evaluate_expr(ast, state=state)
    assert abs(float(res) - 3.1415) < 1e-6


def test_entity_str_success() -> None:
    state = RuleState(
        transcript="open notepad",
        transcript_lower="open notepad",
        intent="launch_app",
        entities={"app": ["notepad"]},
        apps_running=[],
        hour_local=12,
        weekday=1,
        session_turns=1,
        last_tool=None,
        last_tool_ok=None,
    )
    ast = parse('(entity-str "app")')
    res = evaluate_expr(ast, state=state)
    assert res == "notepad"
