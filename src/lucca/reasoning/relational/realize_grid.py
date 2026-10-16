"""
Project Lucca — Realization Carrier: Discrete 2D Grids
======================================================
Projects 2D discrete grid regions onto discrete 1D intervals,
determines spatial orientations (above, below, left_of, right_of) via Allen algebra,
and provides connected component extraction and bounding-box comparison.

Zero-Any typing strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from collections import deque
from typing import Final

import numpy as np

from .allen import AllenRelation, relation_1d
from .sorts import GridRegion, Interval1D

OFFSETS_4: Final[tuple[tuple[int, int], ...]] = (
    (-1, 0), (1, 0), (0, -1), (0, 1)
)

OFFSETS_8: Final[tuple[tuple[int, int], ...]] = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1)
)


def to_grid_region(obj: object) -> GridRegion:
    """Coerces GridRegion, Component (with .mask), 2D numpy mask, or coordinate collections into GridRegion."""
    if isinstance(obj, GridRegion):
        return obj
    if hasattr(obj, "mask"):
        mask = getattr(obj, "mask")
        if isinstance(mask, np.ndarray):
            coords = np.argwhere(mask)
            return GridRegion(points=frozenset((int(r), int(c)) for r, c in coords))
    if isinstance(obj, np.ndarray):
        coords = np.argwhere(obj)
        return GridRegion(points=frozenset((int(r), int(c)) for r, c in coords))
    if isinstance(obj, (set, frozenset)):
        return GridRegion(points=frozenset(obj))
    if isinstance(obj, (list, tuple)):
        return GridRegion(points=frozenset(obj))
    raise TypeError(f"Cannot convert object of type {type(obj).__name__} to GridRegion")


def y_projection(region: object) -> Interval1D:
    """Projects discrete 2D region onto Y-axis (row indices)."""
    gr = to_grid_region(region)
    if gr.is_empty:
        raise ValueError("Cannot project empty GridRegion")
    min_r, _, max_r, _ = gr.bounding_box
    return Interval1D(start=min_r, end=max_r, kind="discrete")


def x_projection(region: object) -> Interval1D:
    """Projects discrete 2D region onto X-axis (column indices)."""
    gr = to_grid_region(region)
    if gr.is_empty:
        raise ValueError("Cannot project empty GridRegion")
    _, min_c, _, max_c = gr.bounding_box
    return Interval1D(start=min_c, end=max_c, kind="discrete")


def above(a: object, b: object) -> bool:
    """True iff region A is qualitatively above region B in row coordinates.
    
    In standard grid coordinates, row 0 is top. A is above B iff
    y(A) is BEFORE or MEETS y(B).
    """
    rel = relation_1d(y_projection(a), y_projection(b))
    return rel in (AllenRelation.BEFORE, AllenRelation.MEETS)


def below(a: object, b: object) -> bool:
    """True iff region A is qualitatively below region B in row coordinates."""
    rel = relation_1d(y_projection(a), y_projection(b))
    return rel in (AllenRelation.AFTER, AllenRelation.MET_BY)


def left_of(a: object, b: object) -> bool:
    """True iff region A is qualitatively left of region B in col coordinates."""
    rel = relation_1d(x_projection(a), x_projection(b))
    return rel in (AllenRelation.BEFORE, AllenRelation.MEETS)


def right_of(a: object, b: object) -> bool:
    """True iff region A is qualitatively right of region B in col coordinates."""
    rel = relation_1d(x_projection(a), x_projection(b))
    return rel in (AllenRelation.AFTER, AllenRelation.MET_BY)


def bbox_during(a: object, b: object) -> bool:
    """True iff A's bounding box is strictly during B's bounding box in both dimensions.
    
    NOTE: This is an AABB filter, NOT topological enclosure.
    A blob in the concavity of a U-shape will have bbox_during == True,
    while in_cavity == False.
    """
    gr_a = to_grid_region(a)
    gr_b = to_grid_region(b)
    if gr_a.is_empty or gr_b.is_empty:
        return False
    y_during = relation_1d(y_projection(gr_a), y_projection(gr_b)) == AllenRelation.DURING
    x_during = relation_1d(x_projection(gr_a), x_projection(gr_b)) == AllenRelation.DURING
    return y_during and x_during


def extract_connected_components(
    points: frozenset[tuple[int, int]] | set[tuple[int, int]],
    four_connected: bool = True
) -> list[GridRegion]:
    """Extracts discrete connected components from coordinate set."""
    unvisited = set(points)
    components: list[GridRegion] = []
    offsets = OFFSETS_4 if four_connected else OFFSETS_8

    while unvisited:
        seed = next(iter(unvisited))
        unvisited.remove(seed)
        comp_pts: set[tuple[int, int]] = {seed}
        queue: deque[tuple[int, int]] = deque([seed])

        while queue:
            curr_r, curr_c = queue.popleft()
            for dr, dc in offsets:
                neighbor = (curr_r + dr, curr_c + dc)
                if neighbor in unvisited:
                    unvisited.remove(neighbor)
                    comp_pts.add(neighbor)
                    queue.append(neighbor)

        components.append(GridRegion(points=frozenset(comp_pts)))

    return components
