"""
MicroScheme v2 Evaluator
Spec 05 §4, §5, §6
"""

import time
from collections.abc import Callable

from lucca.core.exceptions import (
    SchemeError,
    SchemeGasExhausted,
    SchemeRuntimeError,
    SchemeTimeout,
)
from lucca.core.schemas import Plan, RuleOutcome, RuleState, Say, ToolCall
from lucca.reasoning.scheme.parser import (
    Keyword,
    RuleDefinition,
    SchemeNode,
    SchemeValue,
    Symbol,
    to_canonical,
)
from lucca.reasoning.scheme.prims import PURE_PRIMITIVES, make_state_primitives

DEFAULT_GAS_LIMIT = 1000
DEFAULT_TIMEOUT_MS = 20.0


class SchemeEvaluator:
    def __init__(
        self,
        gas_limit: int = DEFAULT_GAS_LIMIT,
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
        rule_id: str | None = None,
    ) -> None:
        self.gas_limit = gas_limit
        self.timeout_ms = timeout_ms
        self.gas_used = 0
        self.rule_id = rule_id
        self.start_time = 0.0

    def eval(
        self, node: SchemeNode, env: dict[str, Callable[[list[SchemeValue]], SchemeValue]]
    ) -> SchemeValue:
        self.gas_used += 1
        if self.gas_used > self.gas_limit:
            raise SchemeGasExhausted(f"Gas limit of {self.gas_limit} exceeded")

        elapsed_ms = (time.perf_counter() - self.start_time) * 1000.0
        if elapsed_ms > self.timeout_ms:
            raise SchemeTimeout(f"Execution exceeded timeout limit of {self.timeout_ms}ms")

        # Atoms
        if isinstance(node, (bool, int, float, str, Keyword)):
            return node
        elif isinstance(node, Symbol):
            raise SchemeRuntimeError(
                f"Unbound symbol '{node.name}'",
                rule_id=self.rule_id,
                form=node.name,
                cause_type="NameError",
            )
        elif isinstance(node, list):
            if not node:
                return []

            head = node[0]
            if not isinstance(head, Symbol):
                raise SchemeRuntimeError(
                    f"First element of call must be an operator symbol, got {type(head).__name__}",
                    rule_id=self.rule_id,
                    form=to_canonical(node),
                    cause_type="TypeError",
                )

            op = head.name

            # Special forms: and, or, if
            if op == "and":
                for arg in node[1:]:
                    val = self.eval(arg, env)
                    if val is False:
                        return False
                return True

            elif op == "or":
                for arg in node[1:]:
                    val = self.eval(arg, env)
                    if val is not False:
                        return val
                return False

            elif op == "if":
                cond = self.eval(node[1], env)
                if cond is not False:
                    return self.eval(node[2], env)
                elif len(node) > 3:
                    return self.eval(node[3], env)
                return False

            # Strict evaluation for normal primitives
            if op not in env:
                raise SchemeRuntimeError(
                    f"Undefined or disallowed primitive '{op}'",
                    rule_id=self.rule_id,
                    form=to_canonical(node),
                    cause_type="KeyError",
                )

            fn = env[op]
            args: list[SchemeValue] = []
            for arg in node[1:]:
                # If argument is a Keyword, preserve it directly without evaluating as symbol
                if isinstance(arg, Keyword):
                    args.append(arg)
                else:
                    args.append(self.eval(arg, env))

            try:
                return fn(args)
            except SchemeError:
                raise
            except Exception as e:
                raise SchemeRuntimeError(
                    f"Error in primitive '{op}': {e}",
                    rule_id=self.rule_id,
                    form=to_canonical(node),
                    cause_type=type(e).__name__,
                ) from e

        raise SchemeRuntimeError(
            f"Unsupported AST node type: {type(node).__name__}",
            rule_id=self.rule_id,
            form=to_canonical(node),
            cause_type="TypeError",
        )


def build_env(
    state: RuleState | None = None,
) -> dict[str, Callable[[list[SchemeValue]], SchemeValue]]:
    env: dict[str, Callable[[list[SchemeValue]], SchemeValue]] = dict(PURE_PRIMITIVES)
    if state is not None:
        state_env = make_state_primitives(state)
        # Verify no shadowing
        for k in state_env:
            if k in PURE_PRIMITIVES:
                raise SchemeRuntimeError(
                    f"Attempted to shadow pure primitive '{k}'", cause_type="RuntimeError"
                )
        env.update(state_env)
    return env


def evaluate_expr(
    expr: SchemeNode,
    state: RuleState | None = None,
    gas_limit: int = DEFAULT_GAS_LIMIT,
    timeout_ms: float = DEFAULT_TIMEOUT_MS,
    rule_id: str | None = None,
) -> SchemeValue:
    """Evaluates an arbitrary Scheme expression with gas and timeout limits."""
    evaluator = SchemeEvaluator(gas_limit=gas_limit, timeout_ms=timeout_ms, rule_id=rule_id)
    evaluator.start_time = time.perf_counter()
    env = build_env(state)
    return evaluator.eval(expr, env)


def evaluate_rule(
    rule: RuleDefinition,
    state: RuleState,
    gas_limit: int = DEFAULT_GAS_LIMIT,
    timeout_ms: float = DEFAULT_TIMEOUT_MS,
) -> RuleOutcome:
    """Evaluates a RuleDefinition against a given RuleState per Spec 05 §4 & §6."""
    evaluator = SchemeEvaluator(gas_limit=gas_limit, timeout_ms=timeout_ms, rule_id=rule.rule_id)
    t0 = time.perf_counter()
    evaluator.start_time = t0
    env = build_env(state)

    try:
        when_result = evaluator.eval(rule.when_expr, env)
        fired = when_result is not False

        plan: Plan | None = None
        if fired:
            raw_plan = evaluator.eval(rule.plan_expr, env)
            if not isinstance(raw_plan, list):
                raise SchemeRuntimeError(
                    f"Expected :plan to evaluate to list of actions, got {type(raw_plan).__name__}",
                    rule_id=rule.rule_id,
                    form=to_canonical(rule.plan_expr),
                    cause_type="TypeError",
                )
            actions: list[ToolCall | Say] = []
            for item in raw_plan:
                if isinstance(item, (ToolCall, Say)):
                    actions.append(item)
                else:
                    raise SchemeRuntimeError(
                        f"Invalid action in plan: {item}",
                        rule_id=rule.rule_id,
                        form=str(item),
                        cause_type="TypeError",
                    )
            plan = Plan(actions=actions)

        elapsed_us = int((time.perf_counter() - t0) * 1_000_000)
        return RuleOutcome(
            rule_id=rule.rule_id,
            fired=fired,
            plan=plan,
            gas_used=evaluator.gas_used,
            elapsed_us=elapsed_us,
            error=None,
        )

    except SchemeError as e:
        elapsed_us = int((time.perf_counter() - t0) * 1_000_000)
        return RuleOutcome(
            rule_id=rule.rule_id,
            fired=False,
            plan=None,
            gas_used=evaluator.gas_used,
            elapsed_us=elapsed_us,
            error=str(e),
        )
