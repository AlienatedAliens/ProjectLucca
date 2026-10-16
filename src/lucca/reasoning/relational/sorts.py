"""
Project Lucca — Relational Sorts & Mathematical Primitives
===========================================================
Formal typed sorts for qualitative spatial and temporal reasoning.
Zero-Any typing strictly enforced per D-AUD-01.

Tagged union carriers:
- GridRegion: Discrete frozenset of (row, col) coordinates.
- RealRegion: Continuous interval on the real line R.
(ASTRegion deferred until Week 1 synthetic tests are green).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Interval1D:
    """1D interval with explicit discretization semantics.
    
    Invariants:
    - start <= end
    - If kind == "discrete": start and end are integers representing closed [start, end].
      Punctual start == end is explicitly allowed (single pixel or single line).
    - If kind == "continuous": real interval on R.
    """
    start: int | float
    end: int | float
    kind: Literal["discrete", "continuous"] = "discrete"

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"Interval invariant violated: start ({self.start}) > end ({self.end})")
        if self.kind == "discrete":
            if isinstance(self.start, float) and not self.start.is_integer():
                raise ValueError(f"Discrete interval requires integer bounds: [{self.start}, {self.end}]")
            if isinstance(self.end, float) and not self.end.is_integer():
                raise ValueError(f"Discrete interval requires integer bounds: [{self.start}, {self.end}]")
            object.__setattr__(self, "start", int(self.start))
            object.__setattr__(self, "end", int(self.end))

    @property
    def length(self) -> float:
        if self.kind == "discrete":
            return float((int(self.end) - int(self.start)) + 1)
        return float(self.end - self.start)


@dataclass(frozen=True)
class GridRegion:
    """Discrete 2D region defined as a hashable set of (row, col) grid coordinates."""
    points: frozenset[tuple[int, int]]

    @property
    def is_empty(self) -> bool:
        return len(self.points) == 0

    @property
    def bounding_box(self) -> tuple[int, int, int, int]:
        """Returns (min_r, min_c, max_r, max_c). Raises ValueError if empty."""
        if not self.points:
            raise ValueError("Empty GridRegion has no bounding box")
        min_r = min(r for r, _ in self.points)
        max_r = max(r for r, _ in self.points)
        min_c = min(c for _, c in self.points)
        max_c = max(c for _, c in self.points)
        return (min_r, min_c, max_r, max_c)


@dataclass(frozen=True)
class RealRegion:
    """Continuous 1D region on the real line R."""
    interval: Interval1D

    def __post_init__(self) -> None:
        if self.interval.kind != "continuous":
            raise ValueError("RealRegion must wrap a continuous Interval1D")


Region = GridRegion | RealRegion


@dataclass(frozen=True)
class Object:
    """A named entity with domain attributes and a principal geometric or continuous region."""
    id: str
    attributes: dict[str, str | int | float]
    region: Region


@dataclass
class Network:
    """Qualitative constraint network containing objects and relational assertions."""
    objects: dict[str, Object]
