"""
Tests for robust multi-tier grid extraction in ConceptARC and ARC-AGI runners.
"""

from scripts.run_concept_arc import extract_grid_from_text, extract_perceptual_invariants


def test_extract_grid_direct_json():
    text = "[[0, 1], [1, 0]]"
    assert extract_grid_from_text(text) == [[0, 1], [1, 0]]


def test_extract_grid_markdown_json_block():
    text = "Here is the result:\n```json\n[[2, 3, 4], [5, 6, 7]]\n```"
    assert extract_grid_from_text(text) == [[2, 3, 4], [5, 6, 7]]


def test_extract_grid_with_variable_assignment():
    text = "```python\noutput_grid = [[1, 2], [3, 4]]\n```"
    assert extract_grid_from_text(text) == [[1, 2], [3, 4]]


def test_extract_grid_with_numpy_array():
    text = "```\nnp.array([[8, 9], [0, 1]])\n```"
    assert extract_grid_from_text(text) == [[8, 9], [0, 1]]


def test_extract_grid_from_markdown_table():
    text = """
    | 1 | 2 | 3 |
    | 4 | 5 | 6 |
    """
    assert extract_grid_from_text(text) == [[1, 2, 3], [4, 5, 6]]


def test_extract_grid_from_whitespace_separated_digits():
    text = """
    The solved grid is:
    0 1 2
    3 4 5
    6 7 8
    """
    assert extract_grid_from_text(text) == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]


def test_extract_grid_from_callable_transform_code():
    code = """
    ```python
    def transform(grid):
        return [[c * 2 for c in row] for row in grid]
    ```
    """
    inp = [[1, 2], [3, 4]]
    assert extract_grid_from_text(code, grid_in=inp) == [[2, 4], [6, 8]]


def test_extract_perceptual_invariants():
    train_pairs = [
        {"input": [[1, 2], [3, 4]], "output": [[1, 2], [3, 4]]},
        {"input": [[5, 6], [7, 8]], "output": [[5, 6], [7, 8]]},
    ]
    invs = extract_perceptual_invariants(train_pairs, test_input=[[0, 1], [2, 3]])
    assert "Strict 1:1 shape preservation" in invs
    assert "Zero novel colors introduced" in invs
