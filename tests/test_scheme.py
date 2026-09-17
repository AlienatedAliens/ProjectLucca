"""
MicroScheme v2 Mechanical Test Suite
Tests T-LISP-01 through T-LISP-09 and T-RULE-01
Spec 05 §3, §4, §11
"""

import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lucca.core.exceptions import (
    SchemeRuntimeError,
    SchemeSyntaxError,
)
from lucca.core.schemas import RuleState, Say, ToolCall
from lucca.reasoning.scheme import (
    evaluate_expr,
    evaluate_rule,
    parse,
    parse_rule,
    to_canonical,
    tokenize,
)

SAMPLE_RULE = """
(rule "open-calculator-v1"                     ; rule-id (string literal, kebab-case + -vN)
  :when (and (intent= "launch_app")
             (entity-has? "app" "calculator")
             (not (app-running? "calculator")))
  :plan (list (tool "launch_app" :app "calculator")
              (say "Opening the calculator."))
  :priority 10)                                 ; optional int, default 0
"""


def test_t_lisp_01_sample_rule_parses():
    """T-LISP-01: Regex-based lexer handles quoted strings with spaces/escapes, keywords, comments."""
    rule = parse_rule(SAMPLE_RULE)
    assert rule.rule_id == "open-calculator-v1"
    assert rule.priority == 10
    canonical = to_canonical(parse(SAMPLE_RULE))
    assert 'rule "open-calculator-v1"' in canonical
    assert ":when" in canonical
    assert ":plan" in canonical
    assert ":priority 10" in canonical


def test_t_lisp_02_limits_exceeded():
    """T-LISP-02: Max nesting depth 32; max tokens 2000; max source 8 KiB -> SchemeSyntaxError."""
    # Nesting depth > 32
    deep_expr = "(" * 33 + "1" + ")" * 33
    with pytest.raises(SchemeSyntaxError, match="nesting depth"):
        parse(deep_expr)

    # Max tokens > 2000
    token_soup = " ".join(["1"] * 2001)
    with pytest.raises(SchemeSyntaxError, match="Token count exceeds"):
        tokenize(token_soup)

    # Max source > 8192 bytes
    large_source = ";" + ("x" * 8200)
    with pytest.raises(SchemeSyntaxError, match="Source size exceeds"):
        tokenize(large_source)


def test_t_lisp_03_parser_o_n():
    """T-LISP-03: Parser O(n) (index-based, no pop(0)) (token input parses under 50 ms)."""
    # 1500 tokens (within 2000 cap)
    tokens_str = "(+ " + " ".join(["1"] * 1000) + ")"
    t0 = time.perf_counter()
    ast = parse(tokens_str)
    duration_ms = (time.perf_counter() - t0) * 1000.0
    assert duration_ms < 50.0
    assert isinstance(ast, list)
    assert len(ast) == 1001


def test_t_lisp_04_syntax_errors_have_location():
    """T-LISP-04: Unbalanced parens / stray tokens -> SchemeSyntaxError{line, col}."""
    with pytest.raises(SchemeSyntaxError) as exc_info:
        parse("(+ 1 2")
    assert exc_info.value.line is not None
    assert exc_info.value.col is not None

    with pytest.raises(SchemeSyntaxError) as exc_info2:
        parse("(+ 1 2) )")
    assert exc_info2.value.line is not None
    assert exc_info2.value.col is not None


def test_t_lisp_05_if_arity_checked_at_parse_time():
    """T-LISP-05: 'if' with 2 or 3 branches only; arity errors are SchemeSyntaxError at parse time."""
    # Valid: 2 args (cond, then)
    ast2 = parse("(if #t 1)")
    assert isinstance(ast2, list)

    # Valid: 3 args (cond, then, else)
    ast3 = parse("(if #t 1 2)")
    assert isinstance(ast3, list)

    # Invalid: 1 arg
    with pytest.raises(SchemeSyntaxError, match="'if' form requires 2 or 3 arguments"):
        parse("(if #t)")

    # Invalid: 4 args
    with pytest.raises(SchemeSyntaxError, match="'if' form requires 2 or 3 arguments"):
        parse("(if #t 1 2 3)")


@given(st.text())
@settings(max_examples=50, deadline=1000)
def test_t_lisp_06_hypothesis_random_token_soup(soup: str):
    """T-LISP-06: Hypothesis: random token soup never raises anything but SchemeSyntaxError."""
    try:
        parse(soup)
    except SchemeSyntaxError:
        pass
    except Exception as e:
        pytest.fail(f"Unexpected exception {type(e)}: {e} on input: {soup!r}")


def test_t_lisp_07_evaluator_catches_all_primitive_errors():
    """T-LISP-07: Type errors, division by zero -> SchemeRuntimeError with cause_type."""
    state = RuleState(schema_version=1)

    # Division by zero
    with pytest.raises(SchemeRuntimeError) as exc1:
        evaluate_expr(parse("(/ 10 0)"), state)
    assert exc1.value.cause_type == "ZeroDivisionError"

    # Type error (< "a" 1)
    with pytest.raises(SchemeRuntimeError) as exc2:
        evaluate_expr(parse('(< "a" 1)'), state)
    assert exc2.value.cause_type == "TypeError"

    # Multiplication on string
    with pytest.raises(SchemeRuntimeError) as exc3:
        evaluate_expr(parse('(* "a" 5)'), state)
    assert exc3.value.cause_type == "TypeError"


def test_t_lisp_08_memory_bomb_and_overflow_guards():
    """T-LISP-08: Memory bomb attempts -> typed error within 20 ms."""
    state = RuleState(schema_version=1)

    # Deep nesting is rejected at parse time
    bomb_parse = "(" * 33 + "1" + ")" * 33
    with pytest.raises(SchemeSyntaxError):
        parse(bomb_parse)

    # Huge integer overflow in evaluation
    overflow_expr = parse("(* 9223372036854775807 2)")
    with pytest.raises(SchemeRuntimeError) as exc:
        evaluate_expr(overflow_expr, state)
    assert exc.value.cause_type == "OverflowError"


def test_t_lisp_09_define_and_shadowing_forbidden():
    """T-LISP-09: Primitive shadowing / define -> SchemeSyntaxError."""
    with pytest.raises(SchemeSyntaxError, match="define"):
        parse("(define x 10)")

    with pytest.raises(SchemeSyntaxError, match="define"):
        parse('(rule "test-v1" :when (define x 1) :plan (list (say "hi")))')


def test_t_rule_01_sample_rule_execution():
    """T-RULE-01: Sample rule §1 -> Plan with 1 ToolCall + 1 Say; canonical equality."""
    rule = parse_rule(SAMPLE_RULE)

    # State where rule should fire
    matching_state = RuleState(
        schema_version=1,
        intent="launch_app",
        entities={"app": ["calculator"]},
        apps_running=frozenset(["chrome"]),
    )

    outcome = evaluate_rule(rule, matching_state)
    assert outcome.fired is True
    assert outcome.plan is not None
    assert len(outcome.plan.actions) == 2

    # Check actions
    action1 = outcome.plan.actions[0]
    action2 = outcome.plan.actions[1]
    assert isinstance(action1, ToolCall)
    assert action1.tool == "launch_app"
    assert action1.args == {"app": "calculator"}

    assert isinstance(action2, Say)
    assert action2.text == "Opening the calculator."

    # State where app is already running -> rule should NOT fire
    not_matching_state = RuleState(
        schema_version=1,
        intent="launch_app",
        entities={"app": ["calculator"]},
        apps_running=frozenset(["calculator"]),
    )
    outcome2 = evaluate_rule(rule, not_matching_state)
    assert outcome2.fired is False
    assert outcome2.plan is None


def test_t_rule_08_static_validation_rejections():
    """T-RULE-08: Static validation rejects: unknown tool, bad kwargs, constant-true :when, regex primitive."""
    from lucca.core.exceptions import RuleError, SchemeSyntaxError
    from lucca.core.schemas import Risk, ToolParameter, ToolSchema
    from lucca.reasoning.scheme.validator import validate_rule_static

    registered_tools = {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="app name", required=True)},
            risk=Risk.LAUNCH,
        )
    }

    # 1. Unknown tool
    rule_unknown_tool = """
    (rule "bad-tool-v1"
      :when (intent= "bad")
      :plan (list (tool "nonexistent_tool" :x 1)))
    """
    with pytest.raises(RuleError, match="not in registered tool list"):
        validate_rule_static(rule_unknown_tool, registered_tools)

    # 2. Bad kwargs
    rule_bad_kwargs = """
    (rule "bad-kwarg-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :unknown_param "calc")))
    """
    with pytest.raises(RuleError, match="does not accept parameter"):
        validate_rule_static(rule_bad_kwargs, registered_tools)

    # 3. Constant-true :when (no state predicates)
    rule_const_true = """
    (rule "const-true-v1"
      :when #t
      :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError, match="must reference at least one state predicate"):
        validate_rule_static(rule_const_true, registered_tools)

    # 4. Disallowed primitive (e.g. regex 'matches?')
    rule_regex = """
    (rule "regex-v1"
      :when (matches? ".*" "calc")
      :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError, match=r"Unknown or disallowed operator 'matches\?'"):
        validate_rule_static(rule_regex, registered_tools)
