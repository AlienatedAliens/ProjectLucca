"""
Project Lucca — Realization Carrier: Continuous Real Line R
===========================================================
Interval relations and containment over continuous real variables.
Zero-Any typing strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from .allen import AllenRelation, relation_1d
from .sorts import Interval1D, RealRegion


def during_real(a: RealRegion | Interval1D, b: RealRegion | Interval1D) -> bool:
    """True iff continuous interval A is strictly during continuous interval B."""
    inv_a = a.interval if isinstance(a, RealRegion) else a
    inv_b = b.interval if isinstance(b, RealRegion) else b

    if inv_a.kind != "continuous" or inv_b.kind != "continuous":
        raise ValueError("during_real requires continuous Interval1D instances")

    return relation_1d(inv_a, inv_b) == AllenRelation.DURING


def point_in_interval(point: float, interval: RealRegion | Interval1D, inclusive: bool = True) -> bool:
    """True iff real point x lies within interval [start, end]."""
    inv = interval.interval if isinstance(interval, RealRegion) else interval
    if inclusive:
        return inv.start <= point <= inv.end
    return inv.start < point < inv.end
