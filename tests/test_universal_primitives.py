"""
Unit tests for MicroScheme Universal Symbolic Primitives (WO-35 Milestone 35.3)
"""

from __future__ import annotations

import pytest

from lucca.reasoning.scheme.eval import evaluate_expr
from lucca.reasoning.scheme.parser import parse_expr
from lucca.reasoning.scheme.universal_primitives import (
    register_universal_primitives,
)


@pytest.fixture(autouse=True)
def init_prims() -> None:
    register_universal_primitives()


def eval_scheme(expr_str: str) -> object:
    node = parse_expr(expr_str)
    return evaluate_expr(node)


def test_sequence_operations() -> None:
    assert eval_scheme("(reverse (list 1 2 3))") == [3, 2, 1]
    assert eval_scheme("(take 2 (list 1 2 3 4))") == [1, 2]
    assert eval_scheme("(drop 2 (list 1 2 3 4))") == [3, 4]
    assert eval_scheme("(zip (list 1 2) (list 3 4))") == [[1, 3], [2, 4]]
    assert eval_scheme("(unique (list 1 2 2 3 1))") == [1, 2, 3]


def test_set_operations() -> None:
    assert eval_scheme("(member? 2 (list 1 2 3))") is True
    assert eval_scheme("(member? 5 (list 1 2 3))") is False
    assert eval_scheme("(subset? (list 1 2) (list 1 2 3))") is True
    assert eval_scheme("(subset? (list 1 4) (list 1 2 3))") is False
    assert eval_scheme("(union (list 1 2) (list 2 3))") == [1, 2, 3]
    assert eval_scheme("(intersection (list 1 2 3) (list 2 3 4))") == [2, 3]
    assert eval_scheme("(difference (list 1 2 3) (list 2 3 4))") == [1]


def test_vector_geometry_and_navigation() -> None:
    assert eval_scheme("(vec2d 3 4)") == [3, 4]
    assert eval_scheme("(vec-add (vec2d 1 2) (vec2d 3 4))") == [4, 6]
    assert eval_scheme("(vec-sub (vec2d 5 7) (vec2d 2 3))") == [3, 4]
    assert eval_scheme("(vec-scale (vec2d 2 3) 4)") == [8, 12]
    assert eval_scheme("(manhattan-dist (vec2d 0 0) (vec2d 3 4))") == 7
    assert eval_scheme("(euclidean-dist (vec2d 0 0) (vec2d 3 4))") == 5.0

    # Navigation turns: 0=N, 1=E, 2=S, 3=W
    assert eval_scheme('(heading-turn 0 "right")') == 1  # N -> E
    assert eval_scheme('(heading-turn 1 "right")') == 2  # E -> S
    assert eval_scheme('(heading-turn 0 "left")') == 3   # N -> W
    assert eval_scheme('(heading-turn 0 "around")') == 2 # N -> S

    # Step forward: from [0, 0] heading N (0), move 5 steps -> [0, 5]
    assert eval_scheme("(step-forward (vec2d 0 0) 0 5)") == [0.0, 5.0]
    # From [0, 5] heading E (1), move 3 steps -> [3, 5]
    assert eval_scheme("(step-forward (vec2d 0 5) 1 3)") == [3.0, 5.0]
