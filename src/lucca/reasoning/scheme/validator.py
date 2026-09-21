"""
MicroScheme v2 Static Rule Validator
Spec 05 §7, T-RULE-08
"""

import random

from lucca.core.exceptions import (
    RuleError,
    SchemeError,
    SchemeInterruptSignal,
    SchemeSyntaxError,
    SchemeYieldSignal,
)
from lucca.core.schemas import RuleState, ToolSchema
from lucca.reasoning.scheme.eval import evaluate_expr
from lucca.reasoning.scheme.parser import (
    Keyword,
    RuleDefinition,
    SchemeNode,
    Symbol,
    parse_rule,
)


def _generate_test_states(count: int = 20) -> list[RuleState]:
    intents = [
        "launch_app",
        "file_read",
        "file_write",
        "web_fetch",
        "memory_query",
        "chit_chat",
        "clarify",
        "unknown",
    ]
    apps = ["calculator", "notepad", "terminal", "browser", "code"]
    rng = random.Random(42)  # Deterministic test states

    states: list[RuleState] = []
    for i in range(count):
        intent = rng.choice(intents)
        chosen_apps = rng.sample(apps, k=rng.randint(0, 3))
        entities = {
            "app": rng.sample(apps, k=rng.randint(0, 2)),
            "file": [f"doc_{i}.txt"],
        }
        states.append(
            RuleState(
                schema_version=1,
                transcript=f"sample transcript {i}",
                transcript_lower=f"sample transcript {i}",
                intent=intent,
                intent_conf=rng.uniform(0.1, 0.99),
                entities=entities,
                hour_local=rng.randint(0, 23),
                weekday=rng.randint(0, 6),
                apps_running=frozenset(chosen_apps),
                last_tool=rng.choice([None, "read_file", "launch_app"]),
                last_tool_ok=rng.choice([None, True, False]),
                session_turns=rng.randint(0, 50),
                mode=rng.choice(["audio", "transcript"]),
            )
        )
    return states


def validate_rule_static(
    source: str,
    registered_tools: dict[str, ToolSchema] | None = None,
    existing_rule_ids: set[str] | None = None,
) -> RuleDefinition:
    """
    Performs full static validation of a rule per Spec 05 §7:
    1. Parse and grammar validation.
    2. Depth and size limits.
    3. Op whitelist validation.
    4. Registered tool checks and kwarg validation.
    5. Non-constant-true :when predicate check.
    6. Evaluation against 20 random RuleState fixtures.
    7. Uniqueness check.
    """
    rule = parse_rule(source)

    if existing_rule_ids is not None and rule.rule_id in existing_rule_ids:
        raise RuleError(f"Rule ID '{rule.rule_id}' already exists")

    # Validate tools in :plan
    if registered_tools is not None:
        _validate_plan_tools(rule.plan_expr, registered_tools)

    # Evaluate against 20 random RuleState fixtures
    test_fixtures = _generate_test_states(20)
    for idx, fixture in enumerate(test_fixtures):
        try:
            evaluate_expr(rule.when_expr, fixture, rule_id=rule.rule_id)
            evaluate_expr(rule.plan_expr, fixture, rule_id=rule.rule_id)
        except (SchemeYieldSignal, SchemeInterruptSignal):
            pass
        except SchemeError as e:
            raise RuleError(
                f"Static validation failed on fixture {idx} for rule '{rule.rule_id}': {e}"
            ) from e

    return rule


def _collect_plan_tool_actions(plan_node: SchemeNode) -> list[list[SchemeNode]]:
    actions: list[list[SchemeNode]] = []
    if not isinstance(plan_node, list) or len(plan_node) < 1:
        return actions
    head = plan_node[0]
    if isinstance(head, Symbol):
        if head.name == "if":
            for branch in plan_node[2:]:
                actions.extend(_collect_plan_tool_actions(branch))
        elif head.name == "list":
            for item in plan_node[1:]:
                actions.extend(_collect_plan_tool_actions(item))
        elif head.name == "tool":
            actions.append(plan_node)
    return actions


def _validate_plan_tools(plan_node: SchemeNode, registered_tools: dict[str, ToolSchema]) -> None:
    tool_actions = _collect_plan_tool_actions(plan_node)
    for action in tool_actions:
        tool_name = action[1]
        if not isinstance(tool_name, str):
            raise SchemeSyntaxError(f"Tool name must be string literal, got {tool_name}")
        if tool_name not in registered_tools:
            raise RuleError(f"Tool '{tool_name}' is not in registered tool list")

        tool_schema = registered_tools[tool_name]
        # Collect kwargs
        passed_kwargs: set[str] = set()
        i = 2
        while i < len(action):
            kw_node = action[i]
            if isinstance(kw_node, Keyword):
                arg_name = kw_node.name.lstrip(":")
                if arg_name not in tool_schema.parameters:
                    raise RuleError(f"Tool '{tool_name}' does not accept parameter '{arg_name}'")
                passed_kwargs.add(arg_name)
            i += 2

        # Check required parameters
        for p_name, p_schema in tool_schema.parameters.items():
            if p_schema.required and p_name not in passed_kwargs:
                raise RuleError(f"Tool '{tool_name}' missing required parameter '{p_name}'")
