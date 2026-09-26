"""
Direct unit tests for MicroScheme v2 Evaluator.
lucca.reasoning.scheme.eval
Spec 05 §4, §5, §6
"""

import time
import pytest

from lucca.core.exceptions import (
    SchemeError,
    SchemeGasExhausted,
    SchemeRuntimeError,
    SchemeTimeout,
)
from lucca.core.schemas import Plan, RuleOutcome, RuleState, Say, ToolCall
from lucca.reasoning.scheme.eval import (
    DEFAULT_GAS_LIMIT,
    DEFAULT_TIMEOUT_MS,
    SchemeEvaluator,
    build_env,
    evaluate_expr,
    evaluate_plan,
    evaluate_rule,
)
from lucca.reasoning.scheme.parser import (
    Keyword,
    RuleDefinition,
    Symbol,
    parse,
    parse_rule,
)


def test_scheme_evaluator_gas_metering() -> None:
    """Gas metering increments on each eval and raises SchemeGasExhausted deterministically."""
    evaluator = SchemeEvaluator(gas_limit=4)
    evaluator.start_time = time.perf_counter()
    env = build_env()

    # Evaluating a simple atom uses 1 gas
    val = evaluator.eval(42, env)
    assert val == 42
    assert evaluator.gas_used == 1

    # Evaluating (+ 1 2) uses 3 gas: outer list (+), plus 2 argument elements (1, 2)
    # Total gas used will reach 4 (limit reached)
    val2 = evaluator.eval(parse("(+ 1 2)"), env)
    assert val2 == 3
    assert evaluator.gas_used == 4

    # Next eval call exceeds limit 4 -> raises SchemeGasExhausted
    with pytest.raises(SchemeGasExhausted, match="Gas limit of 4 exceeded"):
        evaluator.eval(1, env)


def test_scheme_evaluator_gas_exhaustion_at_default_limit() -> None:
    """Default gas limit (1,000) aborts infinite or deeply unrolled evaluation deterministically.

    The wall-clock timeout is disabled (raised far above any plausible runtime) so this
    test isolates gas exhaustion deterministically — otherwise a loaded machine can hit
    the 25 ms timeout before 1,000 gas is consumed and raise SchemeTimeout instead.
    """
    evaluator = SchemeEvaluator(gas_limit=DEFAULT_GAS_LIMIT, timeout_ms=600_000.0)
    evaluator.start_time = time.perf_counter()
    env = build_env()

    # Create an expression that requires more than 1000 eval steps
    # 400 iterations * 3 eval calls per level = 1200 > 1000
    nested: list[object] = [Symbol("+"), 1, 1]
    for _ in range(400):
        nested = [Symbol("+"), 1, 1, nested]

    with pytest.raises(SchemeGasExhausted, match=f"Gas limit of {DEFAULT_GAS_LIMIT} exceeded"):
        evaluator.eval(nested, env)


def test_scheme_evaluator_timeout_handling() -> None:
    """Evaluation aborts with SchemeTimeout when duration exceeds timeout_ms."""
    # With a timeout_ms of 0.0 (or negative), even the first operation fails immediately
    evaluator = SchemeEvaluator(timeout_ms=0.0001)
    evaluator.start_time = time.perf_counter() - 1.0  # Simulate 1 second already elapsed
    env = build_env()

    with pytest.raises(SchemeTimeout, match="Execution exceeded timeout limit"):
        evaluator.eval(parse("(+ 1 2)"), env)


def test_evaluator_purity() -> None:
    """Evaluation does not mutate the input AST or the environment dictionary."""
    ast = parse("(+ 1 2 3)")
    original_ast = parse("(+ 1 2 3)")
    env = build_env()
    original_env_keys = set(env.keys())

    res = evaluate_expr(ast)
    assert res == 6
    assert ast == original_ast
    assert set(env.keys()) == original_env_keys


def test_evaluator_atoms_and_unbound_symbols() -> None:
    """Atoms evaluate to themselves; unbound symbols raise SchemeRuntimeError(NameError)."""
    assert evaluate_expr(True) is True
    assert evaluate_expr(False) is False
    assert evaluate_expr(42) == 42
    assert evaluate_expr(3.14) == 3.14
    assert evaluate_expr("hello") == "hello"
    assert evaluate_expr(Keyword(":kw")) == Keyword(":kw")

    # Unbound symbol
    with pytest.raises(SchemeRuntimeError) as exc:
        evaluate_expr(Symbol("unbound_var"))
    assert exc.value.cause_type == "NameError"
    assert "Unbound symbol 'unbound_var'" in str(exc.value)


def test_evaluator_special_forms() -> None:
    """Special forms: and, or, if."""
    # and: short-circuits on False
    assert evaluate_expr(parse("(and)")) is True
    assert evaluate_expr(parse("(and #t 42 \"yes\")")) is True
    assert evaluate_expr(parse("(and #t #f (/ 1 0))")) is False  # division by zero avoided!

    # or: short-circuits on truthy
    assert evaluate_expr(parse("(or)")) is False
    assert evaluate_expr(parse("(or #f #f)")) is False
    assert evaluate_expr(parse('(or #f "found" (/ 1 0))')) == "found"  # division by zero avoided!

    # if: (if cond then [else])
    assert evaluate_expr(parse("(if #t 1 2)")) == 1
    assert evaluate_expr(parse("(if #f 1 2)")) == 2
    assert evaluate_expr(parse("(if #f 1)")) is False
    # Only evaluates the chosen branch
    assert evaluate_expr(parse("(if #t 42 (/ 1 0))")) == 42
    assert evaluate_expr(parse("(if #f (/ 1 0) 99)")) == 99


def test_evaluator_primitive_dispatch_and_errors() -> None:
    """Disallowed operator or invalid head type raises SchemeRuntimeError."""
    # Invalid head type
    with pytest.raises(SchemeRuntimeError) as exc1:
        evaluate_expr([42, 1, 2])
    assert exc1.value.cause_type == "TypeError"

    # Undefined primitive
    with pytest.raises(SchemeRuntimeError) as exc2:
        evaluate_expr([Symbol("unknown_primitive"), 1, 2])
    assert exc2.value.cause_type == "KeyError"


def test_build_env_pure_and_state() -> None:
    """build_env constructs pure environment or composite environment with state predicates."""
    pure_env = build_env()
    assert "+" in pure_env
    assert "say" in pure_env
    assert "intent=" not in pure_env

    state = RuleState(schema_version=1, intent="launch_app")
    state_env = build_env(state)
    assert "+" in state_env
    assert "intent=" in state_env

    # Verification that shadowing pure primitive raises SchemeRuntimeError
    def malicious_state_primitives(s: RuleState) -> dict[str, object]:
        return {"+": lambda args: 0}

    import unittest.mock
    with unittest.mock.patch("lucca.reasoning.scheme.eval.make_state_primitives", malicious_state_primitives):
        with pytest.raises(SchemeRuntimeError, match="Attempted to shadow pure primitive"):
            build_env(state)


def test_evaluate_rule_lifecycle() -> None:
    """evaluate_rule properly returns RuleOutcome for match, non-match, and errors."""
    rule_src = """
    (rule "calc-test-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :app "calculator")
                  (say "Opening calculator")))
    """
    rule = parse_rule(rule_src)

    # 1. Matching state -> fired=True, errored=False, plan populated
    match_state = RuleState(schema_version=1, intent="launch_app")
    outcome = evaluate_rule(rule, match_state)
    assert isinstance(outcome, RuleOutcome)
    assert outcome.fired is True
    assert outcome.errored is False
    assert outcome.plan is not None
    assert len(outcome.plan.actions) == 2
    assert outcome.error is None
    assert outcome.gas_used > 0
    assert outcome.elapsed_us >= 0

    # 2. Non-matching state -> fired=False, errored=False, plan is None
    no_match_state = RuleState(schema_version=1, intent="browse")
    outcome_nomatch = evaluate_rule(rule, no_match_state)
    assert outcome_nomatch.fired is False
    assert outcome_nomatch.errored is False
    assert outcome_nomatch.plan is None

    # 3. When-phase error -> fired=False, errored=True
    bad_when_rule = RuleDefinition(
        rule_id="bad-when-v1",
        when_expr=parse("(/ 10 0)"),
        plan_expr=parse('(list (say "hi"))'),
        priority=0,
        source_canonical="",
        source_hash="",
    )
    outcome_bad_when = evaluate_rule(bad_when_rule, match_state)
    assert outcome_bad_when.fired is False
    assert outcome_bad_when.errored is True
    assert outcome_bad_when.plan is None
    assert "Division by zero" in str(outcome_bad_when.error)

    # 4. Plan-phase error -> fired=True, errored=True
    bad_plan_rule = RuleDefinition(
        rule_id="bad-plan-v1",
        when_expr=parse('(intent= "launch_app")'),
        plan_expr=parse('(list (tool "launch_app" :app (/ 10 0)))'),
        priority=0,
        source_canonical="",
        source_hash="",
    )
    outcome_bad_plan = evaluate_rule(bad_plan_rule, match_state)
    assert outcome_bad_plan.fired is True
    assert outcome_bad_plan.errored is True
    assert outcome_bad_plan.plan is None
    assert "Division by zero" in str(outcome_bad_plan.error)


def test_evaluate_plan_direct() -> None:
    """evaluate_plan directly evaluates plan_expr without evaluating when_expr."""
    rule = parse_rule("""
    (rule "plan-direct-v1"
      :when (intent= "never_matches")
      :plan (list (say "direct action")))
    """)
    state = RuleState(schema_version=1, intent="other")
    outcome = evaluate_plan(rule, state)
    assert outcome.fired is True
    assert outcome.errored is False
    assert outcome.plan is not None
    assert len(outcome.plan.actions) == 1
    assert isinstance(outcome.plan.actions[0], Say)
    assert outcome.plan.actions[0].text == "direct action"
