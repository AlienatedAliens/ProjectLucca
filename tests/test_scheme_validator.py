"""
Direct unit tests for MicroScheme v2 Static Rule Validator.
lucca.reasoning.scheme.validator
Spec 05 §7, T-RULE-08
"""

import pytest

from lucca.core.exceptions import RuleError, SchemeSyntaxError
from lucca.core.schemas import Risk, RuleState, ToolParameter, ToolSchema
from lucca.reasoning.scheme.parser import RuleDefinition
from lucca.reasoning.scheme.validator import (
    _collect_plan_tool_actions,
    _generate_test_states,
    _validate_plan_tools,
    validate_rule_static,
)


@pytest.fixture
def registered_tools() -> dict[str, ToolSchema]:
    return {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={
                "app": ToolParameter(type="string", description="Application name", required=True),
                "force": ToolParameter(type="boolean", description="Force launch", required=False),
            },
            risk=Risk.LAUNCH,
            target="self",
        ),
        "read_file": ToolSchema(
            name="read_file",
            description="Read file contents",
            parameters={
                "path": ToolParameter(type="string", description="File path", required=True),
            },
            risk=Risk.READ,
            target="self",
        ),
    }


def test_generate_test_states_deterministic() -> None:
    """_generate_test_states produces deterministic pseudo-random fixtures."""
    states1 = _generate_test_states(20)
    states2 = _generate_test_states(20)
    assert len(states1) == 20
    assert len(states2) == 20

    for s1, s2 in zip(states1, states2, strict=True):
        assert isinstance(s1, RuleState)
        assert s1.intent == s2.intent
        assert s1.hour_local == s2.hour_local
        assert s1.apps_running == s2.apps_running
        assert s1.entities == s2.entities


def test_validate_rule_static_valid(registered_tools: dict[str, ToolSchema]) -> None:
    """Valid rule passes full static validation."""
    source = """
    (rule "open-calc-v1"
      :when (and (intent= "launch_app")
                 (entity-has? "app" "calculator")
                 (not (app-running? "calculator")))
      :plan (list (tool "launch_app" :app "calculator")
                  (say "Opening calculator"))
      :priority 5)
    """
    rule = validate_rule_static(source, registered_tools=registered_tools)
    assert isinstance(rule, RuleDefinition)
    assert rule.rule_id == "open-calc-v1"
    assert rule.priority == 5


def test_validate_rule_static_constant_true_rejection(registered_tools: dict[str, ToolSchema]) -> None:
    """Constant-true :when condition (no state predicates) is rejected."""
    # Boolean constant
    src_bool = """
    (rule "const-true-v1"
      :when #t
      :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError, match="must reference at least one state predicate"):
        validate_rule_static(src_bool, registered_tools=registered_tools)

    # Arithmetic without state predicates
    src_arith = """
    (rule "const-math-v1"
      :when (= (+ 1 1) 2)
      :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError, match="must reference at least one state predicate"):
        validate_rule_static(src_arith, registered_tools=registered_tools)


def test_validate_rule_static_unmodeled_predicate_fail_closed(
    registered_tools: dict[str, ToolSchema],
) -> None:
    """Unmodeled predicate or disallowed operator in :when fails closed with SchemeSyntaxError."""
    src = """
    (rule "unmodeled-pred-v1"
      :when (unregistered-pred "test")
      :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError, match="Unknown or disallowed operator 'unregistered-pred'"):
        validate_rule_static(src, registered_tools=registered_tools)


def test_validate_rule_static_existing_rule_id_conflict(
    registered_tools: dict[str, ToolSchema],
) -> None:
    """Attempting to validate a rule whose ID already exists raises RuleError."""
    src = """
    (rule "existing-rule-v1"
      :when (intent= "launch_app")
      :plan (list (say "hi")))
    """
    with pytest.raises(RuleError, match="Rule ID 'existing-rule-v1' already exists"):
        validate_rule_static(src, registered_tools=registered_tools, existing_rule_ids={"existing-rule-v1"})


def test_validate_rule_static_registered_tool_checks(
    registered_tools: dict[str, ToolSchema],
) -> None:
    """validate_rule_static enforces tool registration, valid params, and required params."""
    # 1. Unknown tool
    src_unknown = """
    (rule "unknown-tool-v1"
      :when (intent= "launch_app")
      :plan (list (tool "nonexistent_tool" :x 1)))
    """
    with pytest.raises(RuleError, match="is not in registered tool list"):
        validate_rule_static(src_unknown, registered_tools=registered_tools)

    # 2. Missing required parameter
    src_missing_param = """
    (rule "missing-param-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :force #t)))
    """
    with pytest.raises(RuleError, match="missing required parameter 'app'"):
        validate_rule_static(src_missing_param, registered_tools=registered_tools)

    # 3. Unrecognized parameter
    src_bad_param = """
    (rule "bad-param-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :app "calc" :unrecognized_param 123)))
    """
    with pytest.raises(RuleError, match="does not accept parameter 'unrecognized_param'"):
        validate_rule_static(src_bad_param, registered_tools=registered_tools)


def test_collect_plan_tool_actions_and_branches() -> None:
    """_collect_plan_tool_actions traverses list and if branches to gather all tool actions."""
    from lucca.reasoning.scheme.parser import Keyword, Symbol

    plan = [
        Symbol("if"),
        Symbol("cond"),
        [Symbol("list"), [Symbol("tool"), "launch_app", Keyword(":app"), "calc"]],
        [Symbol("tool"), "read_file", Keyword(":path"), "a.txt"],
    ]
    actions = _collect_plan_tool_actions(plan)
    assert len(actions) == 2
    assert actions[0][1] == "launch_app"
    assert actions[1][1] == "read_file"


def test_validate_rule_static_signals_permitted(
    registered_tools: dict[str, ToolSchema],
) -> None:
    """yield-to-core and interrupt-core signals do not cause static validation failure."""
    src_yield = """
    (rule "yield-rule-v1"
      :when (intent= "launch_app")
      :plan (list (yield-to-core "Clarification needed" :topic "app")))
    """
    rule_yield = validate_rule_static(src_yield, registered_tools=registered_tools)
    assert rule_yield.rule_id == "yield-rule-v1"

    src_interrupt = """
    (rule "interrupt-rule-v1"
      :when (intent= "launch_app")
      :plan (list (interrupt-core "Safety halt")))
    """
    rule_intr = validate_rule_static(src_interrupt, registered_tools=registered_tools)
    assert rule_intr.rule_id == "interrupt-rule-v1"


def test_validate_rule_static_fixture_runtime_error_fails(
    registered_tools: dict[str, ToolSchema],
) -> None:
    """If a rule raises SchemeRuntimeError during 20 fixture evaluations, static validation raises RuleError."""
    # (entity-int "nonexistent_key") raises KeyError during fixture evaluation
    src_err = """
    (rule "runtime-err-v1"
      :when (and (intent= "launch_app") (= (entity-int "nonexistent_key") 10))
      :plan (list (say "hi")))
    """
    with pytest.raises(RuleError, match="Static validation failed on fixture"):
        validate_rule_static(src_err, registered_tools=registered_tools)
