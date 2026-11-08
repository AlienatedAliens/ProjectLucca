"""
MicroScheme v2 Evaluator
Spec 05 §4, §5, §6
"""

import time
from collections.abc import Callable

from lucca.core.exceptions import (
    SchemeControlSignal,
    SchemeError,
    SchemeGasExhausted,
    SchemeRuntimeError,
    SchemeTimeout,
)
from lucca.core.schemas import (
    AssertFact,
    Plan,
    RuleOutcome,
    RuleState,
    Say,
    ToolCall,
)
from lucca.reasoning.relational.realize_real import during_real, point_in_interval
from lucca.reasoning.relational.sorts import Interval1D
from lucca.reasoning.scheme import math_primitives, skills, universal_primitives
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
DEFAULT_TIMEOUT_MS = 25.0


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

        if self.start_time <= 0.0:
            self.start_time = time.perf_counter()

        elapsed_ms = (time.perf_counter() - self.start_time) * 1000.0
        if elapsed_ms > self.timeout_ms:
            raise SchemeTimeout(f"Execution exceeded timeout limit of {self.timeout_ms}ms")

        # Atoms
        if isinstance(node, (bool, int, float, str, Keyword)):
            return node
        elif isinstance(node, Symbol):
            if node.name in env:
                var_fn = env[node.name]
                return var_fn([]) if callable(var_fn) else var_fn
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
            if isinstance(head, Symbol):
                op = head.name
            elif isinstance(head, str):
                op = head
            else:
                raise SchemeRuntimeError(
                    f"First element of call must be an operator symbol, got {type(head).__name__}",
                    rule_id=self.rule_id,
                    form=to_canonical(node),
                    cause_type="TypeError",
                )

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
            if op in ("assert", "fact-exists?", "fact-value"):
                for arg in node[1:]:
                    if isinstance(arg, list):
                        triple_items: list[SchemeValue] = []
                        for item in arg:
                            if isinstance(item, Symbol):
                                triple_items.append(item.name)
                            elif isinstance(item, Keyword):
                                triple_items.append(item.name.lstrip(":"))
                            elif isinstance(item, (str, int, float, bool)):
                                triple_items.append(item)
                            else:
                                triple_items.append(self.eval(item, env))
                        args.append(triple_items)
                    elif isinstance(arg, Symbol):
                        args.append(arg.name)
                    elif isinstance(arg, Keyword):
                        args.append(arg.name.lstrip(":"))
                    else:
                        args.append(self.eval(arg, env))
            else:
                for arg in node[1:]:
                    # If argument is a Keyword, preserve it directly without evaluating as symbol
                    if isinstance(arg, Keyword):
                        args.append(arg)
                    else:
                        args.append(self.eval(arg, env))

            try:
                return fn(args)
            except (SchemeError, SchemeControlSignal):
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


def _prim_point_in_interval(args: list[SchemeValue]) -> SchemeValue:
    """(point-in-interval? x [start end]) or (point-in-interval? x start end)."""



    if len(args) == 2 and isinstance(args[1], list) and len(args[1]) >= 2:
        pt = float(args[0])  # type: ignore[arg-type]
        iv = Interval1D(start=float(args[1][0]), end=float(args[1][1]), kind="continuous")  # type: ignore[arg-type]
        return point_in_interval(pt, iv)
    if len(args) >= 3:
        pt = float(args[0])  # type: ignore[arg-type]
        iv = Interval1D(start=float(args[1]), end=float(args[2]), kind="continuous")  # type: ignore[arg-type]
        return point_in_interval(pt, iv)
    raise SchemeRuntimeError("'point-in-interval?' expects (x [start end]) or (x start end)")


def _prim_during_real(args: list[SchemeValue]) -> SchemeValue:
    """(during-real? [a0 a1] [b0 b1])."""



    if len(args) == 2 and isinstance(args[0], list) and isinstance(args[1],
        list) and len(args[0]) >= 2 and len(args[1]) >= 2:
        iv_a = Interval1D(start=float(args[0][0]), end=float(args[0][1]), kind="continuous")  # type: ignore[arg-type]
        iv_b = Interval1D(start=float(args[1][0]), end=float(args[1][1]), kind="continuous")  # type: ignore[arg-type]
        return during_real(iv_a, iv_b)
    raise SchemeRuntimeError("'during-real?' expects ([a0 a1] [b0 b1])")


def build_env(
    state: RuleState | None = None,
) -> dict[str, Callable[[list[SchemeValue]], SchemeValue]]:


    env: dict[str, Callable[[list[SchemeValue]], SchemeValue]] = dict(PURE_PRIMITIVES)
    for k, fn in universal_primitives.UNIVERSAL_PRIMITIVES.items():
        env.setdefault(k, fn)
    for k, fn in math_primitives.MATH_SCHEME_PRIMITIVES.items():
        if k not in PURE_PRIMITIVES:
            env[k] = fn
    env.setdefault("point-in-interval?", _prim_point_in_interval)
    env.setdefault("during-real?", _prim_during_real)
    env.setdefault("active-skill-limit", lambda _: skills.ACTIVE_SKILL_LIMIT)
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
    except SchemeError as e:
        elapsed_us = int((time.perf_counter() - t0) * 1_000_000)
        return RuleOutcome(
            rule_id=rule.rule_id,
            fired=False,
            errored=True,
            plan=None,
            gas_used=evaluator.gas_used,
            elapsed_us=elapsed_us,
            error=str(e),
        )

    plan: Plan | None = None
    if fired:
        try:
            raw_plan = evaluator.eval(rule.plan_expr, env)
            if isinstance(raw_plan, (ToolCall, Say, AssertFact)):
                raw_plan = [raw_plan]
            elif not isinstance(raw_plan, list):
                raise SchemeRuntimeError(
                    f"Expected :plan to evaluate to list of actions, got {type(raw_plan).__name__}",
                    rule_id=rule.rule_id,
                    form=to_canonical(rule.plan_expr),
                    cause_type="TypeError",
                )
            actions: list[ToolCall | Say | AssertFact] = []
            for item in raw_plan:
                if isinstance(item, (ToolCall, Say, AssertFact)):
                    actions.append(item)
                else:
                    raise SchemeRuntimeError(
                        f"Invalid action in plan: {item}",
                        rule_id=rule.rule_id,
                        form=str(item),
                        cause_type="TypeError",
                    )
            plan = Plan(actions=actions)
        except SchemeError as e:
            elapsed_us = int((time.perf_counter() - t0) * 1_000_000)
            return RuleOutcome(
                rule_id=rule.rule_id,
                fired=True,
                errored=True,
                plan=None,
                gas_used=evaluator.gas_used,
                elapsed_us=elapsed_us,
                error=str(e),
            )

    elapsed_us = int((time.perf_counter() - t0) * 1_000_000)
    return RuleOutcome(
        rule_id=rule.rule_id,
        fired=fired,
        errored=False,
        plan=plan,
        gas_used=evaluator.gas_used,
        elapsed_us=elapsed_us,
        error=None,
    )


def evaluate_plan(
    rule: RuleDefinition,
    state: RuleState,
    gas_limit: int = DEFAULT_GAS_LIMIT,
    timeout_ms: float = DEFAULT_TIMEOUT_MS,
) -> RuleOutcome:
    """Evaluates rule.plan_expr directly without when_expr gating (for invoke_skill dispatch)."""
    evaluator = SchemeEvaluator(gas_limit=gas_limit, timeout_ms=timeout_ms, rule_id=rule.rule_id)
    t0 = time.perf_counter()
    evaluator.start_time = t0
    env = build_env(state)

    try:
        raw_plan = evaluator.eval(rule.plan_expr, env)
        if isinstance(raw_plan, (ToolCall, Say, AssertFact)):
            raw_plan = [raw_plan]
        elif not isinstance(raw_plan, list):
            raise SchemeRuntimeError(
                f"Expected :plan to evaluate to list of actions, got {type(raw_plan).__name__}",
                rule_id=rule.rule_id,
                form=to_canonical(rule.plan_expr),
                cause_type="TypeError",
            )
        actions: list[ToolCall | Say | AssertFact] = []
        for item in raw_plan:
            if isinstance(item, (ToolCall, Say, AssertFact)):
                actions.append(item)
            else:
                raise SchemeRuntimeError(
                    f"Invalid action in plan: {item}",
                    rule_id=rule.rule_id,
                    form=str(item),
                    cause_type="TypeError",
                )
        plan = Plan(actions=actions)
    except SchemeError as e:
        elapsed_us = int((time.perf_counter() - t0) * 1_000_000)
        return RuleOutcome(
            rule_id=rule.rule_id,
            fired=True,
            errored=True,
            plan=None,
            gas_used=evaluator.gas_used,
            elapsed_us=elapsed_us,
            error=str(e),
        )

    elapsed_us = int((time.perf_counter() - t0) * 1_000_000)
    return RuleOutcome(
        rule_id=rule.rule_id,
        fired=True,
        errored=False,
        plan=plan,
        gas_used=evaluator.gas_used,
        elapsed_us=elapsed_us,
        error=None,
    )
