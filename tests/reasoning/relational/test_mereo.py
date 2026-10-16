"""
Project Lucca — Relational Kernel Unit Tests: Discrete Mereotopology & Carriers
================================================================================
Verifies:
1. Closed ring enclosing a blob: in_cavity == True, bbox_during == True, part_of == False.
2. U-shape with blob in concavity: in_cavity == False, bbox_during == True.
   (MANDATORY DISAGREEMENT TEST: Proves in_cavity does not fall back to AABB).
3. part_of: subset containment (blob in wall material).
4. Orientation predicates: above, below, left_of, right_of via discrete Y/X projections.
5. Two-Carrier verification: during verified on R (realize_real) and grid projections (realize_grid).
6. 1,000 synthetic random region trials checking cavity extraction invariance.

Zero benchmark strings in test suite per anti-benchmax contract.
"""

from __future__ import annotations

import random
import pytest

from lucca.reasoning.relational.mereo import (
    externally_connected,
    extract_cavities,
    extract_cavity_mask,
    extract_exterior_mask,
    in_cavity,
    is_between,
    part_of,
    partially_overlaps,
)
from lucca.reasoning.relational.realize_grid import (
    above,
    below,
    bbox_during,
    left_of,
    right_of,
    x_projection,
    y_projection,
)
from lucca.reasoning.relational.realize_real import during_real, point_in_interval
from lucca.reasoning.relational.sorts import GridRegion, Interval1D, RealRegion


def test_closed_ring_enclosing_blob() -> None:
    """A closed 5x5 ring enclosing a central 1x1 blob.
    
    Ring:
    # # # # #
    # . . . #
    # . X . #
    # . . . #
    # # # # #
    
    Verifies:
    - in_cavity(blob, ring) is True
    - bbox_during(blob, ring) is True
    - part_of(blob, ring) is False
    - externally_connected(blob, ring) is False
    """
    ring_pts: set[tuple[int, int]] = set()
    for r in range(5):
        for c in range(5):
            if r == 0 or r == 4 or c == 0 or c == 4:
                ring_pts.add((r, c))

    ring = GridRegion(points=frozenset(ring_pts))
    blob = GridRegion(points=frozenset({(2, 2)}))

    assert in_cavity(blob, ring) is True
    assert bbox_during(blob, ring) is True
    assert part_of(blob, ring) is False
    assert externally_connected(blob, ring) is False
    assert partially_overlaps(blob, ring) is False


def test_u_shape_concavity_disagreement() -> None:
    """A 5x5 U-shape open to the top with a central blob in the concavity.
    
    U-Shape:
    # . . . #   <- Open to top!
    # . . . #
    # . X . #
    # . . . #
    # # # # #
    
    MANDATORY DISAGREEMENT TEST:
    - Because the U-shape is open to the border, complement flood-fill reaches into the concavity.
    - Therefore, in_cavity(blob, u_shape) MUST BE FALSE.
    - However, bbox_during(blob, u_shape) is TRUE.
    This proves that in_cavity does NOT rely on AABB bounding-box approximations.
    """
    u_pts: set[tuple[int, int]] = set()
    for r in range(5):
        for c in range(5):
            # Left wall, right wall, or bottom wall (top wall missing)
            if c == 0 or c == 4 or r == 4:
                u_pts.add((r, c))

    u_shape = GridRegion(points=frozenset(u_pts))
    blob = GridRegion(points=frozenset({(2, 2)}))

    # Bbox includes rows 0..4 and cols 0..4, so bbox_during is True:
    assert bbox_during(blob, u_shape) is True

    # But topological cavity is empty because concavity communicates with border:
    assert in_cavity(blob, u_shape) is False

    # Disagreement invariant verified!
    assert in_cavity(blob, u_shape) != bbox_during(blob, u_shape)


def test_part_of_material_wall() -> None:
    """Verifies that a blob placed directly on B's wall is part_of B, but NOT in_cavity."""
    wall_pts = frozenset({(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)})
    b = GridRegion(points=wall_pts)
    sub_blob = GridRegion(points=frozenset({(0, 1), (1, 1)}))

    assert part_of(sub_blob, b) is True
    assert in_cavity(sub_blob, b) is False  # Cannot be in cavity if intersecting material


def test_externally_connected_4_vs_8() -> None:
    """Verifies 4-connected vs 8-connected adjacency."""
    a = GridRegion(points=frozenset({(0, 0)}))
    b_edge = GridRegion(points=frozenset({(0, 1)}))      # 4-adjacent (orthogonal)
    b_corner = GridRegion(points=frozenset({(1, 1)}))    # 8-adjacent (diagonal)
    b_far = GridRegion(points=frozenset({(0, 2)}))       # Disjoint

    # Orthogonal
    assert externally_connected(a, b_edge, four_connected=True) is True
    assert externally_connected(a, b_edge, four_connected=False) is True

    # Diagonal
    assert externally_connected(a, b_corner, four_connected=True) is False
    assert externally_connected(a, b_corner, four_connected=False) is True

    # Far
    assert externally_connected(a, b_far, four_connected=False) is False


def test_orientation_predicates() -> None:
    """Verifies above, below, left_of, right_of on discrete grids."""
    top_region = GridRegion(points=frozenset({(0, 5), (1, 5)}))
    bottom_region = GridRegion(points=frozenset({(3, 5), (4, 5)}))
    left_region = GridRegion(points=frozenset({(5, 0), (5, 1)}))
    right_region = GridRegion(points=frozenset({(5, 4), (5, 5)}))

    assert above(top_region, bottom_region) is True
    assert below(bottom_region, top_region) is True
    assert above(bottom_region, top_region) is False

    assert left_of(left_region, right_region) is True
    assert right_of(right_region, left_region) is True
    assert left_of(right_region, left_region) is False


def test_two_carrier_during_real_and_grid() -> None:
    """Verifies the Two-Carrier Rule: 'during' evaluated across both R and Grid projections."""
    # Carrier 1: Real line R
    real_outer = RealRegion(interval=Interval1D(start=0.0, end=10.0, kind="continuous"))
    real_inner = RealRegion(interval=Interval1D(start=2.5, end=7.5, kind="continuous"))
    real_outside = RealRegion(interval=Interval1D(start=12.0, end=15.0, kind="continuous"))

    assert during_real(real_inner, real_outer) is True
    assert during_real(real_outside, real_outer) is False
    assert point_in_interval(5.0, real_outer) is True
    assert point_in_interval(15.0, real_outer) is False

    # Carrier 2: Grid discrete projections
    grid_outer = GridRegion(points=frozenset({(0, 0), (10, 10)}))
    grid_inner = GridRegion(points=frozenset({(3, 3), (7, 7)}))
    assert bbox_during(grid_inner, grid_outer) is True


def test_synthetic_1000_random_holed_masks() -> None:
    """Stress tests extract_cavities across 1,000 procedurally generated random holed rings."""
    rng = random.Random(1337)

    for i in range(1000):
        # Generate a random bounding frame size: 7x7 to 15x15
        h = rng.randint(7, 15)
        w = rng.randint(7, 15)
        
        # Build an outer closed boundary at row 1..h-2, col 1..w-2
        ring_pts: set[tuple[int, int]] = set()
        for r in range(1, h - 1):
            ring_pts.add((r, 1))
            ring_pts.add((r, w - 2))
        for c in range(1, w - 1):
            ring_pts.add((1, c))
            ring_pts.add((h - 2, c))

        ring = GridRegion(points=frozenset(ring_pts))
        cavities = extract_cavities(ring)

        # The interior of the ring (rows 2..h-3, cols 2..w-3) MUST all be cavities
        expected_interior = frozenset(
            (r, c) for r in range(2, h - 2) for c in range(2, w - 2)
        )
        assert expected_interior == cavities, f"Trial {i} failed: cavity extraction mismatch"

        # Any interior point must pass in_cavity
        sample_r = rng.randint(2, h - 3)
        sample_c = rng.randint(2, w - 3)
        test_blob = GridRegion(points=frozenset({(sample_r, sample_c)}))
        assert in_cavity(test_blob, ring, cached_b_cavities=cavities) is True

        # Puncturing the ring at a border cell turns it into an open C/U shape!
        puncture_r = 1
        puncture_c = rng.randint(2, w - 3)
        punctured_pts = ring_pts - {(puncture_r, puncture_c)}
        punctured_shape = GridRegion(points=frozenset(punctured_pts))

        # Because of the puncture, exterior flood-fill enters the interior!
        punctured_cavities = extract_cavities(punctured_shape)
        assert len(punctured_cavities) == 0, f"Trial {i} failed: punctured ring must have 0 cavities"
        assert in_cavity(test_blob, punctured_shape, cached_b_cavities=punctured_cavities) is False


def test_cavity_mask_and_betweenness() -> None:
    """Verifies extract_cavity_mask, extract_exterior_mask, and is_between."""
    import numpy as np

    # 5x5 closed ring
    ring_pts = {
        (1, 1), (1, 2), (1, 3),
        (2, 1),         (2, 3),
        (3, 1), (3, 2), (3, 3),
    }
    ring = GridRegion(points=frozenset(ring_pts))

    cav_mask = extract_cavity_mask(ring, shape=(5, 5))
    assert cav_mask.shape == (5, 5)
    assert cav_mask[2, 2] == True
    assert cav_mask.sum() == 1

    ext_mask = extract_exterior_mask(ring, shape=(5, 5))
    assert ext_mask.shape == (5, 5)
    assert ext_mask[0, 0] == True
    assert ext_mask[2, 2] == False
    assert ext_mask[1, 1] == False
    assert ext_mask.sum() == (25 - 8 - 1)  # 25 total - 8 wall - 1 cavity = 16 exterior

    # is_between
    p = (2, 4)
    a = (2, 1)
    b = (2, 8)
    assert is_between(p, a, b) is True

    p_outside = (2, 9)
    assert is_between(p_outside, a, b) is False

    # 2D diagonal bounding span
    corner1 = (0, 0)
    corner2 = (4, 4)
    assert is_between((2, 2), corner1, corner2) is True
    assert is_between((5, 2), corner1, corner2) is False

