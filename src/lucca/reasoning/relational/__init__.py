"""
Project Lucca — Relational & Mereotopological Kernel
====================================================
Public interface for Organ A:
- Typed Sorts: Interval1D, GridRegion, RealRegion, Region, Object, Network
- Allen 1D Algebra: AllenRelation, relation_1d, converse, compose, ALLEN_COMPOSITION_TABLE
- Discrete Mereotopology: part_of, externally_connected, partially_overlaps, in_cavity, extract_cavities
- Grid Realization: y_projection, x_projection, above, below, left_of, right_of, bbox_during, extract_connected_components
- Real Realization: during_real, point_in_interval

Zero-Any typing strictly enforced per D-AUD-01.
Zero benchmark dataset strings in package.
"""

from .allen import (
    ALLEN_COMPOSITION_TABLE,
    AllenRelation,
    compose,
    converse,
    relation_1d,
)
from .mereo import (
    externally_connected,
    extract_cavities,
    extract_cavity_mask,
    extract_exterior_mask,
    in_cavity,
    is_between,
    part_of,
    partially_overlaps,
)
from .realize_grid import (
    above,
    below,
    bbox_during,
    extract_connected_components,
    left_of,
    right_of,
    x_projection,
    y_projection,
)
from .realize_real import during_real, point_in_interval
from .sorts import GridRegion, Interval1D, Network, Object, RealRegion, Region

__all__ = [
    "ALLEN_COMPOSITION_TABLE",
    "AllenRelation",
    "GridRegion",
    "Interval1D",
    "Network",
    "Object",
    "RealRegion",
    "Region",
    "above",
    "below",
    "bbox_during",
    "compose",
    "converse",
    "during_real",
    "externally_connected",
    "extract_cavities",
    "extract_cavity_mask",
    "extract_connected_components",
    "extract_exterior_mask",
    "in_cavity",
    "is_between",
    "left_of",
    "part_of",
    "partially_overlaps",
    "point_in_interval",
    "relation_1d",
    "right_of",
    "x_projection",
    "y_projection",
]
