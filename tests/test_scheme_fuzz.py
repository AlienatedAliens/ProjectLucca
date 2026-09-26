"""
Hypothesis fuzzing suite for MicroScheme v2.
Tests parser and evaluator robustness against arbitrary generated inputs.
Asserts that parser/eval never crash with unhandled exceptions (only typed SchemeError / SchemeControlSignal).
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lucca.core.exceptions import SchemeControlSignal, SchemeError
from lucca.core.schemas import RuleState
from lucca.reasoning.scheme.eval import evaluate_expr
from lucca.reasoning.scheme.parser import (
    ALLOWED_OPS,
    Keyword,
    SchemeNode,
    Symbol,
    parse,
    to_canonical,
)


# Strategy for generating Scheme atoms
@st.composite
def scheme_symbols(draw: st.DrawFn) -> Symbol:
    name = draw(
        st.one_of(
            st.sampled_from(sorted(ALLOWED_OPS)),
            st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_?=<>!-]{0,15}", fullmatch=True),
        )
    )
    return Symbol(name)


@st.composite
def scheme_keywords(draw: st.DrawFn) -> Keyword:
    name = draw(st.from_regex(r":[a-zA-Z][a-zA-Z0-9_-]{0,15}", fullmatch=True))
    return Keyword(name)


def scheme_atoms() -> st.SearchStrategy[SchemeNode]:
    return st.one_of(
        st.integers(min_value=-2**64, max_value=2**64),
        st.floats(allow_nan=True, allow_infinity=True),
        st.booleans(),
        st.text(max_size=50),
        scheme_symbols(),
        scheme_keywords(),
    )


# Recursive strategy for generating arbitrary S-expression ASTs
def scheme_sexprs() -> st.SearchStrategy[SchemeNode]:
    return st.recursive(
        scheme_atoms(),
        lambda children: st.lists(children, max_size=5),
        max_leaves=25,
    )


@given(st.text(max_size=300))
@settings(max_examples=100, deadline=1500)
def test_fuzz_parser_random_text(source: str) -> None:
    """Random text strings parsed by MicroScheme must either parse cleanly or raise SchemeError."""
    try:
        parse(source)
    except SchemeError:
        pass
    except Exception as e:
        pytest.fail(f"Unhandled exception {type(e).__name__}: {e} during parse of: {source!r}")


@given(scheme_sexprs())
@settings(max_examples=100, deadline=1500)
def test_fuzz_evaluator_random_ast(node: SchemeNode) -> None:
    """Random S-expression ASTs evaluated by MicroScheme must never crash with unhandled exceptions."""
    state = RuleState(
        schema_version=1,
        intent="launch_app",
        entities={"app": ["calculator"]},
        apps_running=frozenset(["calc"]),
        hour_local=12,
        weekday=3,
        asserted_facts=[("alice", "likes", "bob")],
    )
    try:
        evaluate_expr(node, state=state, gas_limit=100, timeout_ms=10.0)
    except (SchemeError, SchemeControlSignal):
        pass
    except Exception as e:
        pytest.fail(f"Unhandled exception {type(e).__name__}: {e} during evaluation of: {node!r}")


@given(scheme_sexprs())
@settings(max_examples=50, deadline=1500)
def test_fuzz_to_canonical_safety(node: SchemeNode) -> None:
    """to_canonical on valid SchemeNode never raises unhandled exceptions."""
    try:
        canonical = to_canonical(node)
        assert isinstance(canonical, str)
    except SchemeError:
        pass
    except Exception as e:
        pytest.fail(f"Unhandled exception {type(e).__name__}: {e} in to_canonical for: {node!r}")


@given(st.lists(scheme_atoms(), min_size=1, max_size=10))
@settings(max_examples=50, deadline=1500)
def test_fuzz_eval_gas_termination(args: list[SchemeNode]) -> None:
    """Evaluation under gas limit 10 always terminates deterministically without hang or crash."""
    call_node: SchemeNode = [Symbol("+")] + args
    try:
        evaluate_expr(call_node, gas_limit=10, timeout_ms=5.0)
    except (SchemeError, SchemeControlSignal):
        pass
    except Exception as e:
        pytest.fail(f"Unhandled exception {type(e).__name__}: {e} for gas termination: {call_node!r}")
