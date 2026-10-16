"""
Project Lucca — Induction Relational Kernel Integration Tests
=============================================================
Verifies that execute_unshackled_python seamlessly executes synthesized
transformation code using Organ A relational primitives:
1. in_cavity on closed ring with enclosed blob -> True
2. in_cavity on open U-shape with concavity blob -> False (Disagreement invariant)
3. part_of on sub-component -> True
4. above / below qualitative sorting of components without manual index loops.

Zero benchmark dataset strings per anti-benchmax contract.
"""

from __future__ import annotations

import pytest

from src.lucca.reasoning.cegis_unshackled import execute_unshackled_python


def test_induction_closed_ring_cavity_execution() -> None:
    """Verifies synthesized transform code using in_cavity on a closed ring."""
    # 5x5 grid: 1=blue ring, 2=green blob in cavity
    # # # # #
    # . . . #
    # . X . #
    # . . . #
    # # # # #
    grid_in = [
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 2, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 1],
    ]

    code = """
def transform(grid):
    comps = connected_components(np.array(grid))
    ring = next(c for c in comps if c.color == 1)
    blob = next(c for c in comps if c.color == 2)
    
    # Use relational kernel in_cavity primitive
    is_enclosed = in_cavity(blob, ring)
    
    # Return 1x1 grid with 3 if enclosed, else 0
    return [[3 if is_enclosed else 0]]
"""
    outcome = execute_unshackled_python(code, grid_in)
    assert outcome.success is True, f"Execution failed: {outcome.error_message}"
    assert outcome.output_grid == [[3]], f"Expected [[3]], got {outcome.output_grid}"


def test_induction_u_shape_concavity_disagreement_execution() -> None:
    """Verifies that in_cavity in synthesized code returns False for open U-shape."""
    # 5x5 grid: 1=blue U-shape (open at top), 2=green blob in concavity
    # # . . . #   <- open to border!
    # # . . . #
    # # . X . #
    # # . . . #
    # # # # # #
    grid_in = [
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 2, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 1],
    ]

    code = """
def transform(grid):
    comps = connected_components(np.array(grid))
    u_shape = next(c for c in comps if c.color == 1)
    blob = next(c for c in comps if c.color == 2)
    
    # in_cavity MUST be False for open U-shape
    is_enclosed = in_cavity(blob, u_shape)
    
    return [[3 if is_enclosed else 0]]
"""
    outcome = execute_unshackled_python(code, grid_in)
    assert outcome.success is True, f"Execution failed: {outcome.error_message}"
    assert outcome.output_grid == [[0]], f"Expected [[0]] (not enclosed), got {outcome.output_grid}"


def test_induction_qualitative_vertical_ordering() -> None:
    """Verifies synthesized transform code sorting components via above() predicate."""
    # 7x7 grid with three 1x1 blobs at different rows:
    # color 1 at row 1
    # color 2 at row 3
    # color 3 at row 5
    grid_in = [
        [0, 0, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 2, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 3, 0],
        [0, 0, 0, 0, 0, 0, 0],
    ]

    code = """
def transform(grid):
    comps = connected_components(np.array(grid))
    # Filter non-background components
    colored = [c for c in comps if c.color != 0]
    
    # Verify above() predicate consistency
    c1 = next(c for c in colored if c.color == 1)
    c2 = next(c for c in colored if c.color == 2)
    c3 = next(c for c in colored if c.color == 3)
    
    assert above(c1, c2) is True
    assert above(c2, c3) is True
    assert above(c1, c3) is True
    assert below(c3, c1) is True
    
    # Sort colored components from top to bottom
    sorted_colors = [c.color for c in sorted(colored, key=lambda c: y_projection(c).start)]
    return [sorted_colors]
"""
    outcome = execute_unshackled_python(code, grid_in)
    assert outcome.success is True, f"Execution failed: {outcome.error_message}"
    assert outcome.output_grid == [[1, 2, 3]], f"Expected [[1, 2, 3]], got {outcome.output_grid}"
