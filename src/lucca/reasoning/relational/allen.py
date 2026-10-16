"""
Project Lucca — Allen 1D Interval Algebra
=========================================
Formal 13 qualitative relations, discrete vs continuous meets semantics,
converse operators, and the canonical frozen 13x13 composition table.
Strict zero-Any typing per D-AUD-01.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from .sorts import Interval1D


class AllenRelation(str, Enum):
    """The 13 mutually exclusive qualitative interval relations."""
    BEFORE = "before"                 # p / b
    AFTER = "after"                   # pi / a
    MEETS = "meets"                   # m
    MET_BY = "met_by"                 # mi
    OVERLAPS = "overlaps"             # o
    OVERLAPPED_BY = "overlapped_by"   # oi
    STARTS = "starts"                 # s
    STARTED_BY = "started_by"         # si
    DURING = "during"                 # d
    CONTAINS = "contains"             # di
    FINISHES = "finishes"             # f
    FINISHED_BY = "finished_by"       # fi
    EQUALS = "equals"                 # eq


CONVERSE_MAP: Final[dict[AllenRelation, AllenRelation]] = {
    AllenRelation.EQUALS: AllenRelation.EQUALS,
    AllenRelation.BEFORE: AllenRelation.AFTER,
    AllenRelation.AFTER: AllenRelation.BEFORE,
    AllenRelation.MEETS: AllenRelation.MET_BY,
    AllenRelation.MET_BY: AllenRelation.MEETS,
    AllenRelation.OVERLAPS: AllenRelation.OVERLAPPED_BY,
    AllenRelation.OVERLAPPED_BY: AllenRelation.OVERLAPS,
    AllenRelation.STARTS: AllenRelation.STARTED_BY,
    AllenRelation.STARTED_BY: AllenRelation.STARTS,
    AllenRelation.DURING: AllenRelation.CONTAINS,
    AllenRelation.CONTAINS: AllenRelation.DURING,
    AllenRelation.FINISHES: AllenRelation.FINISHED_BY,
    AllenRelation.FINISHED_BY: AllenRelation.FINISHES,
}


def converse(rel: AllenRelation) -> AllenRelation:
    """Returns the converse relation conv(R) such that R(A, B) <=> conv(R)(B, A)."""
    return CONVERSE_MAP[rel]


def relation_1d(a: Interval1D, b: Interval1D) -> AllenRelation:
    """Computes the exact qualitative Allen relation between two intervals.
    
    Discretization rules:
    - Discrete (grid coordinates, line numbers): closed [start, end].
      'meets' means end_A + 1 == start_B (adjacent without gap).
    - Continuous (real line R):
      'meets' means end_A == start_B.
    """
    s_a, e_a = a.start, a.end
    s_b, e_b = b.start, b.end

    if a.kind == "discrete":
        # Integer boundary conditions
        if s_a == s_b and e_a == e_b:
            return AllenRelation.EQUALS
        if e_a + 1 < s_b:
            return AllenRelation.BEFORE
        if e_b + 1 < s_a:
            return AllenRelation.AFTER
        if e_a + 1 == s_b:
            return AllenRelation.MEETS
        if e_b + 1 == s_a:
            return AllenRelation.MET_BY
        if s_a == s_b:
            return AllenRelation.STARTS if e_a < e_b else AllenRelation.STARTED_BY
        if e_a == e_b:
            return AllenRelation.FINISHES if s_a > s_b else AllenRelation.FINISHED_BY
        if s_b < s_a and e_a < e_b:
            return AllenRelation.DURING
        if s_a < s_b and e_b < e_a:
            return AllenRelation.CONTAINS
        if s_a < s_b and s_b <= e_a and e_a < e_b:
            return AllenRelation.OVERLAPS
        if s_b < s_a and s_a <= e_b and e_b < e_a:
            return AllenRelation.OVERLAPPED_BY
        raise RuntimeError(f"Unclassified discrete interval pair: {a}, {b}")

    else:
        # Continuous boundary conditions on R
        if s_a == s_b and e_a == e_b:
            return AllenRelation.EQUALS
        if e_a < s_b:
            return AllenRelation.BEFORE
        if e_b < s_a:
            return AllenRelation.AFTER
        if e_a == s_b:
            return AllenRelation.MEETS
        if e_b == s_a:
            return AllenRelation.MET_BY
        if s_a == s_b:
            return AllenRelation.STARTS if e_a < e_b else AllenRelation.STARTED_BY
        if e_a == e_b:
            return AllenRelation.FINISHES if s_a > s_b else AllenRelation.FINISHED_BY
        if s_b < s_a and e_a < e_b:
            return AllenRelation.DURING
        if s_a < s_b and e_b < e_a:
            return AllenRelation.CONTAINS
        if s_a < s_b and s_b < e_a and e_a < e_b:
            return AllenRelation.OVERLAPS
        if s_b < s_a and s_a < e_b and e_b < e_a:
            return AllenRelation.OVERLAPPED_BY
        raise RuntimeError(f"Unclassified continuous interval pair: {a}, {b}")


# Aliases for table brevity
_B = AllenRelation.BEFORE
_A = AllenRelation.AFTER
_M = AllenRelation.MEETS
_MI = AllenRelation.MET_BY
_O = AllenRelation.OVERLAPS
_OI = AllenRelation.OVERLAPPED_BY
_S = AllenRelation.STARTS
_SI = AllenRelation.STARTED_BY
_D = AllenRelation.DURING
_C = AllenRelation.CONTAINS
_F = AllenRelation.FINISHES
_FI = AllenRelation.FINISHED_BY
_EQ = AllenRelation.EQUALS
_ALL = frozenset(AllenRelation)

# Canonical Allen 1983 13x13 Composition Table
# Map (R1, R2) -> frozenset of possible R3
ALLEN_COMPOSITION_TABLE: Final[dict[tuple[AllenRelation, AllenRelation], frozenset[AllenRelation]]] = {
    (AllenRelation.AFTER, AllenRelation.AFTER): frozenset([AllenRelation.AFTER]),
    (AllenRelation.AFTER, AllenRelation.BEFORE): frozenset([AllenRelation.AFTER, AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.DURING, AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES, AllenRelation.MEETS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.OVERLAPS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.AFTER, AllenRelation.CONTAINS): frozenset([AllenRelation.AFTER]),
    (AllenRelation.AFTER, AllenRelation.DURING): frozenset([AllenRelation.AFTER, AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.AFTER, AllenRelation.EQUALS): frozenset([AllenRelation.AFTER]),
    (AllenRelation.AFTER, AllenRelation.FINISHED_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.AFTER, AllenRelation.FINISHES): frozenset([AllenRelation.AFTER]),
    (AllenRelation.AFTER, AllenRelation.MEETS): frozenset([AllenRelation.AFTER, AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.AFTER, AllenRelation.MET_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.AFTER, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.AFTER, AllenRelation.OVERLAPS): frozenset([AllenRelation.AFTER, AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.AFTER, AllenRelation.STARTED_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.AFTER, AllenRelation.STARTS): frozenset([AllenRelation.AFTER, AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.BEFORE, AllenRelation.AFTER): frozenset([AllenRelation.AFTER, AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.DURING, AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES, AllenRelation.MEETS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.OVERLAPS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.BEFORE, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.BEFORE, AllenRelation.CONTAINS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.BEFORE, AllenRelation.DURING): frozenset([AllenRelation.BEFORE, AllenRelation.DURING, AllenRelation.MEETS, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.BEFORE, AllenRelation.EQUALS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.BEFORE, AllenRelation.FINISHED_BY): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.BEFORE, AllenRelation.FINISHES): frozenset([AllenRelation.BEFORE, AllenRelation.DURING, AllenRelation.MEETS, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.BEFORE, AllenRelation.MEETS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.BEFORE, AllenRelation.MET_BY): frozenset([AllenRelation.BEFORE, AllenRelation.DURING, AllenRelation.MEETS, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.BEFORE, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.BEFORE, AllenRelation.DURING, AllenRelation.MEETS, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.BEFORE, AllenRelation.OVERLAPS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.BEFORE, AllenRelation.STARTED_BY): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.BEFORE, AllenRelation.STARTS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.CONTAINS, AllenRelation.AFTER): frozenset([AllenRelation.AFTER, AllenRelation.CONTAINS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.CONTAINS, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.CONTAINS, AllenRelation.CONTAINS): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.CONTAINS, AllenRelation.DURING): frozenset([AllenRelation.CONTAINS, AllenRelation.DURING, AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY, AllenRelation.OVERLAPS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.CONTAINS, AllenRelation.EQUALS): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.CONTAINS, AllenRelation.FINISHED_BY): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.CONTAINS, AllenRelation.FINISHES): frozenset([AllenRelation.CONTAINS, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.CONTAINS, AllenRelation.MEETS): frozenset([AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.OVERLAPS]),
    (AllenRelation.CONTAINS, AllenRelation.MET_BY): frozenset([AllenRelation.CONTAINS, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.CONTAINS, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.CONTAINS, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.CONTAINS, AllenRelation.OVERLAPS): frozenset([AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.OVERLAPS]),
    (AllenRelation.CONTAINS, AllenRelation.STARTED_BY): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.CONTAINS, AllenRelation.STARTS): frozenset([AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.OVERLAPS]),
    (AllenRelation.DURING, AllenRelation.AFTER): frozenset([AllenRelation.AFTER]),
    (AllenRelation.DURING, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.DURING, AllenRelation.CONTAINS): frozenset([AllenRelation.AFTER, AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.DURING, AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES, AllenRelation.MEETS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.OVERLAPS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.DURING, AllenRelation.DURING): frozenset([AllenRelation.DURING]),
    (AllenRelation.DURING, AllenRelation.EQUALS): frozenset([AllenRelation.DURING]),
    (AllenRelation.DURING, AllenRelation.FINISHED_BY): frozenset([AllenRelation.BEFORE, AllenRelation.DURING, AllenRelation.MEETS, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.DURING, AllenRelation.FINISHES): frozenset([AllenRelation.DURING]),
    (AllenRelation.DURING, AllenRelation.MEETS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.DURING, AllenRelation.MET_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.DURING, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.AFTER, AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.DURING, AllenRelation.OVERLAPS): frozenset([AllenRelation.BEFORE, AllenRelation.DURING, AllenRelation.MEETS, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.DURING, AllenRelation.STARTED_BY): frozenset([AllenRelation.AFTER, AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.DURING, AllenRelation.STARTS): frozenset([AllenRelation.DURING]),
    (AllenRelation.EQUALS, AllenRelation.AFTER): frozenset([AllenRelation.AFTER]),
    (AllenRelation.EQUALS, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.EQUALS, AllenRelation.CONTAINS): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.EQUALS, AllenRelation.DURING): frozenset([AllenRelation.DURING]),
    (AllenRelation.EQUALS, AllenRelation.EQUALS): frozenset([AllenRelation.EQUALS]),
    (AllenRelation.EQUALS, AllenRelation.FINISHED_BY): frozenset([AllenRelation.FINISHED_BY]),
    (AllenRelation.EQUALS, AllenRelation.FINISHES): frozenset([AllenRelation.FINISHES]),
    (AllenRelation.EQUALS, AllenRelation.MEETS): frozenset([AllenRelation.MEETS]),
    (AllenRelation.EQUALS, AllenRelation.MET_BY): frozenset([AllenRelation.MET_BY]),
    (AllenRelation.EQUALS, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.EQUALS, AllenRelation.OVERLAPS): frozenset([AllenRelation.OVERLAPS]),
    (AllenRelation.EQUALS, AllenRelation.STARTED_BY): frozenset([AllenRelation.STARTED_BY]),
    (AllenRelation.EQUALS, AllenRelation.STARTS): frozenset([AllenRelation.STARTS]),
    (AllenRelation.FINISHED_BY, AllenRelation.AFTER): frozenset([AllenRelation.AFTER, AllenRelation.CONTAINS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.FINISHED_BY, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.FINISHED_BY, AllenRelation.CONTAINS): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.FINISHED_BY, AllenRelation.DURING): frozenset([AllenRelation.DURING, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.FINISHED_BY, AllenRelation.EQUALS): frozenset([AllenRelation.FINISHED_BY]),
    (AllenRelation.FINISHED_BY, AllenRelation.FINISHED_BY): frozenset([AllenRelation.FINISHED_BY]),
    (AllenRelation.FINISHED_BY, AllenRelation.FINISHES): frozenset([AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES]),
    (AllenRelation.FINISHED_BY, AllenRelation.MEETS): frozenset([AllenRelation.MEETS]),
    (AllenRelation.FINISHED_BY, AllenRelation.MET_BY): frozenset([AllenRelation.CONTAINS, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.FINISHED_BY, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.CONTAINS, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.FINISHED_BY, AllenRelation.OVERLAPS): frozenset([AllenRelation.OVERLAPS]),
    (AllenRelation.FINISHED_BY, AllenRelation.STARTED_BY): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.FINISHED_BY, AllenRelation.STARTS): frozenset([AllenRelation.OVERLAPS]),
    (AllenRelation.FINISHES, AllenRelation.AFTER): frozenset([AllenRelation.AFTER]),
    (AllenRelation.FINISHES, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.FINISHES, AllenRelation.CONTAINS): frozenset([AllenRelation.AFTER, AllenRelation.CONTAINS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.FINISHES, AllenRelation.DURING): frozenset([AllenRelation.DURING]),
    (AllenRelation.FINISHES, AllenRelation.EQUALS): frozenset([AllenRelation.FINISHES]),
    (AllenRelation.FINISHES, AllenRelation.FINISHED_BY): frozenset([AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES]),
    (AllenRelation.FINISHES, AllenRelation.FINISHES): frozenset([AllenRelation.FINISHES]),
    (AllenRelation.FINISHES, AllenRelation.MEETS): frozenset([AllenRelation.MEETS]),
    (AllenRelation.FINISHES, AllenRelation.MET_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.AFTER, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.FINISHES, AllenRelation.OVERLAPS): frozenset([AllenRelation.DURING, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.FINISHES, AllenRelation.STARTED_BY): frozenset([AllenRelation.AFTER, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.FINISHES, AllenRelation.STARTS): frozenset([AllenRelation.DURING]),
    (AllenRelation.MEETS, AllenRelation.AFTER): frozenset([AllenRelation.AFTER, AllenRelation.CONTAINS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.MEETS, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.MEETS, AllenRelation.CONTAINS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.MEETS, AllenRelation.DURING): frozenset([AllenRelation.DURING, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.MEETS, AllenRelation.EQUALS): frozenset([AllenRelation.MEETS]),
    (AllenRelation.MEETS, AllenRelation.FINISHED_BY): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.MEETS, AllenRelation.FINISHES): frozenset([AllenRelation.DURING, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.MEETS, AllenRelation.MEETS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.MEETS, AllenRelation.MET_BY): frozenset([AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES]),
    (AllenRelation.MEETS, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.DURING, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.MEETS, AllenRelation.OVERLAPS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.MEETS, AllenRelation.STARTED_BY): frozenset([AllenRelation.MEETS]),
    (AllenRelation.MEETS, AllenRelation.STARTS): frozenset([AllenRelation.MEETS]),
    (AllenRelation.MET_BY, AllenRelation.AFTER): frozenset([AllenRelation.AFTER]),
    (AllenRelation.MET_BY, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.MET_BY, AllenRelation.CONTAINS): frozenset([AllenRelation.AFTER]),
    (AllenRelation.MET_BY, AllenRelation.DURING): frozenset([AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.MET_BY, AllenRelation.EQUALS): frozenset([AllenRelation.MET_BY]),
    (AllenRelation.MET_BY, AllenRelation.FINISHED_BY): frozenset([AllenRelation.MET_BY]),
    (AllenRelation.MET_BY, AllenRelation.FINISHES): frozenset([AllenRelation.MET_BY]),
    (AllenRelation.MET_BY, AllenRelation.MEETS): frozenset([AllenRelation.EQUALS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.MET_BY, AllenRelation.MET_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.MET_BY, AllenRelation.OVERLAPS): frozenset([AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.MET_BY, AllenRelation.STARTED_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.MET_BY, AllenRelation.STARTS): frozenset([AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.AFTER): frozenset([AllenRelation.AFTER]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.CONTAINS): frozenset([AllenRelation.AFTER, AllenRelation.CONTAINS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.DURING): frozenset([AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.EQUALS): frozenset([AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.FINISHED_BY): frozenset([AllenRelation.CONTAINS, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.FINISHES): frozenset([AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.MEETS): frozenset([AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.OVERLAPS]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.MET_BY): frozenset([AllenRelation.AFTER]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.AFTER, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.OVERLAPS): frozenset([AllenRelation.CONTAINS, AllenRelation.DURING, AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY, AllenRelation.OVERLAPS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY): frozenset([AllenRelation.AFTER, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.OVERLAPPED_BY, AllenRelation.STARTS): frozenset([AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.OVERLAPS, AllenRelation.AFTER): frozenset([AllenRelation.AFTER, AllenRelation.CONTAINS, AllenRelation.MET_BY, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.OVERLAPS, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.OVERLAPS, AllenRelation.CONTAINS): frozenset([AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.OVERLAPS, AllenRelation.DURING): frozenset([AllenRelation.DURING, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.OVERLAPS, AllenRelation.EQUALS): frozenset([AllenRelation.OVERLAPS]),
    (AllenRelation.OVERLAPS, AllenRelation.FINISHED_BY): frozenset([AllenRelation.BEFORE, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.OVERLAPS, AllenRelation.FINISHES): frozenset([AllenRelation.DURING, AllenRelation.OVERLAPS, AllenRelation.STARTS]),
    (AllenRelation.OVERLAPS, AllenRelation.MEETS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.OVERLAPS, AllenRelation.MET_BY): frozenset([AllenRelation.CONTAINS, AllenRelation.OVERLAPPED_BY, AllenRelation.STARTED_BY]),
    (AllenRelation.OVERLAPS, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.CONTAINS, AllenRelation.DURING, AllenRelation.EQUALS, AllenRelation.FINISHED_BY, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY, AllenRelation.OVERLAPS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.OVERLAPS, AllenRelation.OVERLAPS): frozenset([AllenRelation.BEFORE, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.OVERLAPS, AllenRelation.STARTED_BY): frozenset([AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.OVERLAPS]),
    (AllenRelation.OVERLAPS, AllenRelation.STARTS): frozenset([AllenRelation.OVERLAPS]),
    (AllenRelation.STARTED_BY, AllenRelation.AFTER): frozenset([AllenRelation.AFTER]),
    (AllenRelation.STARTED_BY, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.STARTED_BY, AllenRelation.CONTAINS): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.STARTED_BY, AllenRelation.DURING): frozenset([AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.STARTED_BY, AllenRelation.EQUALS): frozenset([AllenRelation.STARTED_BY]),
    (AllenRelation.STARTED_BY, AllenRelation.FINISHED_BY): frozenset([AllenRelation.CONTAINS]),
    (AllenRelation.STARTED_BY, AllenRelation.FINISHES): frozenset([AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.STARTED_BY, AllenRelation.MEETS): frozenset([AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.OVERLAPS]),
    (AllenRelation.STARTED_BY, AllenRelation.MET_BY): frozenset([AllenRelation.MET_BY]),
    (AllenRelation.STARTED_BY, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.STARTED_BY, AllenRelation.OVERLAPS): frozenset([AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.OVERLAPS]),
    (AllenRelation.STARTED_BY, AllenRelation.STARTED_BY): frozenset([AllenRelation.STARTED_BY]),
    (AllenRelation.STARTED_BY, AllenRelation.STARTS): frozenset([AllenRelation.EQUALS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.STARTS, AllenRelation.AFTER): frozenset([AllenRelation.AFTER]),
    (AllenRelation.STARTS, AllenRelation.BEFORE): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.STARTS, AllenRelation.CONTAINS): frozenset([AllenRelation.BEFORE, AllenRelation.CONTAINS, AllenRelation.FINISHED_BY, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.STARTS, AllenRelation.DURING): frozenset([AllenRelation.DURING]),
    (AllenRelation.STARTS, AllenRelation.EQUALS): frozenset([AllenRelation.STARTS]),
    (AllenRelation.STARTS, AllenRelation.FINISHED_BY): frozenset([AllenRelation.BEFORE, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.STARTS, AllenRelation.FINISHES): frozenset([AllenRelation.DURING]),
    (AllenRelation.STARTS, AllenRelation.MEETS): frozenset([AllenRelation.BEFORE]),
    (AllenRelation.STARTS, AllenRelation.MET_BY): frozenset([AllenRelation.MET_BY]),
    (AllenRelation.STARTS, AllenRelation.OVERLAPPED_BY): frozenset([AllenRelation.DURING, AllenRelation.FINISHES, AllenRelation.OVERLAPPED_BY]),
    (AllenRelation.STARTS, AllenRelation.OVERLAPS): frozenset([AllenRelation.BEFORE, AllenRelation.MEETS, AllenRelation.OVERLAPS]),
    (AllenRelation.STARTS, AllenRelation.STARTED_BY): frozenset([AllenRelation.EQUALS, AllenRelation.STARTED_BY, AllenRelation.STARTS]),
    (AllenRelation.STARTS, AllenRelation.STARTS): frozenset([AllenRelation.STARTS]),
}


def compose(r1: AllenRelation, r2: AllenRelation) -> frozenset[AllenRelation]:
    """Computes relational composition r1 o r2 from the canonical frozen table."""
    return ALLEN_COMPOSITION_TABLE[(r1, r2)]
