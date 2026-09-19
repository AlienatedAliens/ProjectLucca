"""
Tests for MicroScheme Bounded Macro System (Proposal D, D-REAS-05)
"""

import pytest

from lucca.core.exceptions import SchemeSyntaxError
from lucca.reasoning.scheme.macros import (
    MAX_MACRO_DEPTH,
)
from lucca.reasoning.scheme.parser import parse_rule, to_canonical


def test_basic_macro_definition_and_expansion():
    """Verify compile-time macro expansion in rule :when condition."""
    source = """
    (defmacro when-app-launch (app)
      (and (intent= "launch_app")
           (entity-has? "app" app)
           (not (app-running? app))))

    (rule "calc-launcher-v1"
      :when (when-app-launch "calculator")
      :plan (list (tool "launch_app" :app "calculator")
                  (say "Launching calculator"))
      :priority 10)
    """
    rule = parse_rule(source)
    assert rule.rule_id == "calc-launcher-v1"
    assert rule.priority == 10

    canonical = to_canonical(rule.when_expr)
    # The macro invocation must be completely expanded in canonical form
    assert "when-app-launch" not in canonical
    assert 'intent= "launch_app"' in canonical
    assert 'entity-has? "app" "calculator"' in canonical
    assert 'not (app-running? "calculator")' in canonical


def test_macro_plan_expansion():
    """Verify macro expansion inside rule :plan list."""
    source = """
    (defmacro launch-and-confirm (app msg)
      (list (tool "launch_app" :app app)
            (say msg)))

    (rule "quick-notepad-v1"
      :when (and (intent= "launch_app") (entity-has? "app" "notepad"))
      :plan (launch-and-confirm "notepad" "Opening notepad for you.")
      :priority 5)
    """
    rule = parse_rule(source)
    assert rule.rule_id == "quick-notepad-v1"
    canonical_plan = to_canonical(rule.plan_expr)
    assert "launch-and-confirm" not in canonical_plan
    assert 'tool "launch_app" :app "notepad"' in canonical_plan
    assert 'say "Opening notepad for you."' in canonical_plan


def test_nested_macro_expansion():
    """Verify nested macros expand sequentially within bounded depth."""
    source = """
    (defmacro check-intent (it)
      (intent= it))

    (defmacro check-app-and-intent (it app)
      (and (check-intent it) (entity-has? "app" app)))

    (rule "browser-v1"
      :when (check-app-and-intent "launch_app" "edge")
      :plan (list (say "Launching browser"))
      :priority 1)
    """
    rule = parse_rule(source)
    canonical = to_canonical(rule.when_expr)
    assert "check-intent" not in canonical
    assert "check-app-and-intent" not in canonical
    assert 'intent= "launch_app"' in canonical
    assert 'entity-has? "app" "edge"' in canonical


def test_macro_depth_limit_exceeded():
    """Proposal D / D-REAS-05: Exceeding MAX_MACRO_DEPTH (8) raises SchemeSyntaxError."""
    source = """
    (defmacro loop-a (x) (loop-b x))
    (defmacro loop-b (x) (loop-a x))

    (rule "infinite-macro-v1"
      :when (and (intent= "launch_app") (loop-a "test"))
      :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError) as exc_info:
        parse_rule(source)
    assert f"depth limit exceeded ({MAX_MACRO_DEPTH})" in str(exc_info.value)


def test_macro_cannot_shadow_primitives():
    """Macros cannot shadow allowed operators or primitive names."""
    source = """
    (defmacro and (x y) (or x y))
    (rule "shadow-v1" :when (intent= "test") :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError) as exc_info:
        parse_rule(source)
    assert "primitive" in str(exc_info.value).lower()


def test_macro_arity_mismatch():
    """Macro called with incorrect number of arguments raises SchemeSyntaxError."""
    source = """
    (defmacro check-two (a b) (and (intent= a) (entity-has? "app" b)))
    (rule "arity-v1" :when (check-two "only_one") :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError) as exc_info:
        parse_rule(source)
    assert "expects 2 arguments, got 1" in str(exc_info.value)


def test_disallowed_operator_after_macro_expansion():
    """Operator validation post-expansion catches disallowed operators."""
    source = """
    (defmacro evil-macro (x)
      (system-exec-arbitrary x))

    (rule "evil-v1"
      :when (and (intent= "test") (evil-macro "bad"))
      :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError) as exc_info:
        parse_rule(source)
    assert "Disallowed operator 'system-exec-arbitrary' after macro expansion" in str(
        exc_info.value
    )
