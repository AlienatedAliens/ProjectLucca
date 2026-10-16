"""
Project Lucca — Discrete Mereotopology on Grids
================================================
Implements discrete region relations without continuous approximations:
- part_of (subset)
- externally_connected (adjacency)
- partially_overlaps (proper intersection)
- in_cavity (topological enclosure via border-complement flood-fill)

Seamlessly accepts GridRegion, Component (with .mask), or 2D numpy masks.
Zero-Any typing strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Final

from .realize_grid import OFFSETS_4, to_grid_region
from .sorts import GridRegion

# 8-connected offsets (includes diagonals)
OFFSETS_8: Final[tuple[tuple[int, int], ...]] = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1)
)


def part_of(a: object, b: object) -> bool:
    """True iff A is non-empty and every cell of A is a cell of B (A subset B)."""
    gr_a = to_grid_region(a)
    gr_b = to_grid_region(b)
    if gr_a.is_empty or gr_b.is_empty:
        return False
    return gr_a.points.issubset(gr_b.points)


def partially_overlaps(a: object, b: object) -> bool:
    """True iff A and B share cells, but neither is a subset of the other."""
    gr_a = to_grid_region(a)
    gr_b = to_grid_region(b)
    if gr_a.is_empty or gr_b.is_empty:
        return False
    intersection = gr_a.points.intersection(gr_b.points)
    if not intersection:
        return False
    return not gr_a.points.issubset(gr_b.points) and not gr_b.points.issubset(gr_a.points)


def externally_connected(a: object, b: object, four_connected: bool = True) -> bool:
    """True iff A and B are completely disjoint but share at least one adjacent boundary."""
    gr_a = to_grid_region(a)
    gr_b = to_grid_region(b)
    if gr_a.is_empty or gr_b.is_empty:
        return False
    if not gr_a.points.isdisjoint(gr_b.points):
        return False  # Must have empty intersection to be externally connected

    offsets = OFFSETS_4 if four_connected else OFFSETS_8
    b_pts = gr_b.points

    for r, c in gr_a.points:
        for dr, dc in offsets:
            if (r + dr, c + dc) in b_pts:
                return True
    return False


def extract_cavities(
    b: object,
    frame_bounds: tuple[int, int, int, int] | None = None
) -> frozenset[tuple[int, int]]:
    """Extracts all cavity/hole coordinates of region B via 4-connected border flood-fill.
    
    Algorithm:
    1. Establish an evaluation bounding frame with at least 1 cell of exterior padding.
    2. Construct the complement set of B within this frame.
    3. Flood-fill the complement starting from all perimeter cells of the frame.
    4. Any cell in the complement that was NOT reached by the border flood-fill is an
       enclosed hole/cavity of B.
    """
    gr_b = to_grid_region(b)
    if gr_b.is_empty:
        return frozenset()

    if frame_bounds is None:
        min_r, min_c, max_r, max_c = gr_b.bounding_box
        # Pad by 2 so that an exterior corridor completely surrounds B
        min_r -= 2
        min_c -= 2
        max_r += 2
        max_c += 2
    else:
        min_r, min_c, max_r, max_c = frame_bounds

    b_pts = gr_b.points
    visited_exterior: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    # Seed all perimeter cells of the frame
    for r in range(min_r, max_r + 1):
        for c in (min_c, max_c):
            pt = (r, c)
            if pt not in b_pts and pt not in visited_exterior:
                visited_exterior.add(pt)
                queue.append(pt)

    for c in range(min_c, max_c + 1):
        for r in (min_r, max_r):
            pt = (r, c)
            if pt not in b_pts and pt not in visited_exterior:
                visited_exterior.add(pt)
                queue.append(pt)

    # 4-connected flood-fill through complement
    while queue:
        curr_r, curr_c = queue.popleft()
        for dr, dc in OFFSETS_4:
            nr, nc = curr_r + dr, curr_c + dc
            if min_r <= nr <= max_r and min_c <= nc <= max_c:
                neighbor = (nr, nc)
                if neighbor not in b_pts and neighbor not in visited_exterior:
                    visited_exterior.add(neighbor)
                    queue.append(neighbor)

    # All cells in the frame that are NOT in B and NOT reachable from border are holes
    cavities: set[tuple[int, int]] = set()
    for r in range(min_r, max_r + 1):
        for c in range(min_c, max_c + 1):
            pt = (r, c)
            if pt not in b_pts and pt not in visited_exterior:
                cavities.add(pt)

    return frozenset(cavities)


def in_cavity(
    a: object,
    b: object,
    cached_b_cavities: frozenset[tuple[int, int]] | None = None
) -> bool:
    """True iff A is non-empty, disjoint from B, and completely enclosed within B's cavities.
    
    Key correctness invariant:
    - If B is a closed ring enclosing A: in_cavity is TRUE.
    - If B is a U-shape open to the border with A inside the concavity:
      the concavity connects to the border, so in_cavity is FALSE.
      (Whereas bounding-box 'during' would falsely report True).
    - If A is part of the wall of B: A intersects B, so in_cavity is FALSE.
    """
    gr_a = to_grid_region(a)
    gr_b = to_grid_region(b)

    if gr_a.is_empty or gr_b.is_empty:
        return False

    # A cannot intersect the foreground/material of B
    if not gr_a.points.isdisjoint(gr_b.points):
        return False

    cavities = cached_b_cavities if cached_b_cavities is not None else extract_cavities(gr_b)
    if not cavities:
        return False

    return gr_a.points.issubset(cavities)


def extract_cavity_mask(
    b: object,
    shape: tuple[int, int] | None = None,
) -> Any:
    """Returns a 2D boolean numpy mask of region B's cavities/holes.
    If shape is not specified, uses (max_r + 1, max_c + 1) from B's coordinates.
    """
    import numpy as np

    cavs = extract_cavities(b)
    gr_b = to_grid_region(b)

    if shape is None:
        if gr_b.is_empty and not cavs:
            return np.zeros((0, 0), dtype=bool)
        all_pts = cavs | gr_b.points
        max_r = max(r for r, c in all_pts)
        max_c = max(c for r, c in all_pts)
        shape = (max_r + 1, max_c + 1)

    mask = np.zeros(shape, dtype=bool)
    for r, c in cavs:
        if 0 <= r < shape[0] and 0 <= c < shape[1]:
            mask[r, c] = True
    return mask


def extract_exterior_mask(
    b: object,
    shape: tuple[int, int],
) -> Any:
    """Returns a 2D boolean numpy mask of cells that are OUTSIDE B and not in B's cavities."""
    import numpy as np

    gr_b = to_grid_region(b)
    cav_mask = extract_cavity_mask(gr_b, shape=shape)
    b_mask = np.zeros(shape, dtype=bool)
    for r, c in gr_b.points:
        if 0 <= r < shape[0] and 0 <= c < shape[1]:
            b_mask[r, c] = True
    return ~b_mask & ~cav_mask


def is_between(
    p: object,
    a: object,
    b: object,
) -> bool:
    """True iff point or region P lies strictly within the bounding span formed by anchors A and B.

    Supports:
    - Coordinate pairs: p=(r, c), a=(ra, ca), b=(rb, cb)
    - Components or GridRegions: extracts centroids or points
    """
    def _to_coord(obj: object) -> tuple[float, float]:
        if isinstance(obj, (tuple, list)) and len(obj) == 2:
            return float(obj[0]), float(obj[1])
        gr = to_grid_region(obj)
        if gr.is_empty:
            return 0.0, 0.0
        r_sum = sum(r for r, c in gr.points)
        c_sum = sum(c for r, c in gr.points)
        n = len(gr.points)
        return r_sum / n, c_sum / n

    pr, pc = _to_coord(p)
    ar, ac = _to_coord(a)
    br, bc = _to_coord(b)

    r_min, r_max = min(ar, br), max(ar, br)
    c_min, c_max = min(ac, bc), max(ac, bc)

    in_span = (r_min <= pr <= r_max) and (c_min <= pc <= c_max)
    not_anchor = (pr, pc) != (ar, ac) and (pr, pc) != (br, bc)
    return in_span and not_anchor

