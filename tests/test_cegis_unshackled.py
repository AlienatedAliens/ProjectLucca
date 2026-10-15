"""
Unit tests for Unshackled CEGIS Engine and Structured Cell Diff
v1.44.0 General Reasoning Core
"""

import pytest

from lucca.reasoning.cegis_unshackled import (
    CellMismatch,
    GridDiff,
    compute_detailed_grid_diff,
    execute_unshackled_python,
    normalize_to_int_grid,
    render_grid_ansi,
    render_grid_side_by_side,
)


def test_grid_diff_exact_match() -> None:
    g1 = [[1, 2], [3, 4]]
    g2 = [[1, 2], [3, 4]]
    diff = compute_detailed_grid_diff(g1, g2)
    assert diff.is_match is True
    assert diff.shape_match is True
    assert diff.mismatch_count == 0
    assert diff.mismatches == []
    assert diff.bounding_box is None
    assert "Exact match" in diff.summary_message


def test_grid_diff_shape_mismatch() -> None:
    g1 = [[1, 2], [3, 4]]
    g2 = [[1, 2, 3], [4, 5, 6]]
    diff = compute_detailed_grid_diff(g1, g2)
    assert diff.is_match is False
    assert diff.shape_match is False
    assert diff.expected_shape == (2, 2)
    assert diff.actual_shape == (2, 3)
    assert "Shape mismatch" in diff.summary_message


def test_grid_diff_cell_mismatch_and_bbox() -> None:
    expected = [
        [0, 0, 0, 0],
        [0, 2, 2, 0],
        [0, 2, 2, 0],
        [0, 0, 0, 0],
    ]
    actual = [
        [0, 0, 0, 0],
        [0, 2, 0, 0],  # (1, 2) mismatch: expected 2, got 0
        [0, 0, 2, 0],  # (2, 1) mismatch: expected 2, got 0
        [0, 0, 0, 0],
    ]
    diff = compute_detailed_grid_diff(expected, actual)
    assert diff.is_match is False
    assert diff.shape_match is True
    assert diff.mismatch_count == 2
    assert diff.total_cells == 16
    assert diff.bounding_box == (1, 1, 2, 2)
    assert len(diff.mismatches) == 2
    assert diff.mismatches[0] == CellMismatch(row=1, col=2, expected_val=2, actual_val=0)
    assert diff.mismatches[1] == CellMismatch(row=2, col=1, expected_val=2, actual_val=0)

    prompt = diff.format_counterexample_prompt()
    assert "2 of 16 cells differ" in prompt
    assert "(1, 2): expected 2 (red), got 0 (black)" in prompt


def test_execute_unshackled_python_success() -> None:
    code = """
import numpy as np

def transform(grid):
    arr = np.array(grid)
    return (arr * 2).tolist()
"""
    grid_in = [[1, 2], [3, 4]]
    outcome = execute_unshackled_python(code, grid_in)
    assert outcome.success is True
    assert outcome.output_grid == [[2, 4], [6, 8]]
    assert outcome.error_type is None


def test_execute_unshackled_python_infinite_loop_timeout() -> None:
    code = """
def transform(grid):
    while True:
        pass
"""
    outcome = execute_unshackled_python(code, [[0]], timeout_s=0.5)
    assert outcome.success is False
    assert outcome.error_type == "TimeoutError"
    assert "timed out" in (outcome.error_message or "")


def test_execute_unshackled_python_runtime_exception() -> None:
    code = """
def transform(grid):
    return 10 / 0
"""
    outcome = execute_unshackled_python(code, [[0]])
    assert outcome.success is False
    assert outcome.error_type == "ZeroDivisionError"
    assert outcome.traceback_str is not None


def test_render_grid_ansi_and_side_by_side() -> None:
    g1 = [[0, 1], [2, 3]]
    g2 = [[0, 1], [2, 0]]
    ansi_rendered = render_grid_ansi(g1, use_color=True)
    assert isinstance(ansi_rendered, str)
    assert len(ansi_rendered) > 0

    side_by_side = render_grid_side_by_side(g1, g2, input_grid=[[1, 1], [1, 1]], use_color=False)
    assert "--- EXPECTED ---" in side_by_side
    assert "--- PREDICTED ---" in side_by_side
    assert "--- DIFF MASK ---" in side_by_side
