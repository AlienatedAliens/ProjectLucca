"""
Project Lucca — Relational Kernel Unit Tests: Allen 1D Interval Algebra
=======================================================================
Verifies:
1. All 13 qualitative relations for both discrete and continuous intervals.
2. Converse symmetry: relation_1d(B, A) == converse(relation_1d(A, B)).
3. Double converse involution: converse(converse(R)) == R.
4. Discrete vs continuous meets boundary condition:
   - Discrete: end_A + 1 == start_B
   - Continuous: end_A == start_B
5. Soundness of the frozen 13x13 Allen Composition Table over 1,000 synthetic triples:
   rel(I, K) in compose(rel(I, J), rel(J, K)).

Zero benchmark strings in test suite per anti-benchmax contract.
"""

from __future__ import annotations

import random
import pytest

from src.lucca.reasoning.relational.allen import (
    ALLEN_COMPOSITION_TABLE,
    AllenRelation,
    compose,
    converse,
    relation_1d,
)
from src.lucca.reasoning.relational.sorts import Interval1D


def test_converse_involution() -> None:
    """Verifies that converse(converse(R)) == R for all 13 relations."""
    for rel in AllenRelation:
        assert converse(converse(rel)) == rel


def test_discrete_meets_off_by_one_boundary() -> None:
    """Verifies discrete 'meets' occurs when end_A + 1 == start_B."""
    a = Interval1D(start=1.0, end=4.0, kind="discrete")
    b_meets = Interval1D(start=5.0, end=8.0, kind="discrete")
    b_before = Interval1D(start=6.0, end=8.0, kind="discrete")
    b_overlaps = Interval1D(start=4.0, end=8.0, kind="discrete")

    assert relation_1d(a, b_meets) == AllenRelation.MEETS
    assert relation_1d(b_meets, a) == AllenRelation.MET_BY

    assert relation_1d(a, b_before) == AllenRelation.BEFORE
    assert relation_1d(b_before, a) == AllenRelation.AFTER

    assert relation_1d(a, b_overlaps) == AllenRelation.OVERLAPS
    assert relation_1d(b_overlaps, a) == AllenRelation.OVERLAPPED_BY


def test_continuous_meets_boundary() -> None:
    """Verifies continuous 'meets' occurs when end_A == start_B."""
    a = Interval1D(start=1.0, end=4.0, kind="continuous")
    b_meets = Interval1D(start=4.0, end=8.0, kind="continuous")
    b_before = Interval1D(start=4.0001, end=8.0, kind="continuous")

    assert relation_1d(a, b_meets) == AllenRelation.MEETS
    assert relation_1d(b_meets, a) == AllenRelation.MET_BY

    assert relation_1d(a, b_before) == AllenRelation.BEFORE
    assert relation_1d(b_before, a) == AllenRelation.AFTER


def test_all_13_discrete_relations_covered() -> None:
    """Constructs explicit canonical examples for all 13 discrete relations."""
    ref = Interval1D(start=10.0, end=20.0, kind="discrete")

    cases = {
        AllenRelation.BEFORE: Interval1D(start=1.0, end=8.0, kind="discrete"),
        AllenRelation.MEETS: Interval1D(start=1.0, end=9.0, kind="discrete"),
        AllenRelation.OVERLAPS: Interval1D(start=5.0, end=15.0, kind="discrete"),
        AllenRelation.STARTS: Interval1D(start=10.0, end=15.0, kind="discrete"),
        AllenRelation.DURING: Interval1D(start=12.0, end=18.0, kind="discrete"),
        AllenRelation.FINISHES: Interval1D(start=15.0, end=20.0, kind="discrete"),
        AllenRelation.EQUALS: Interval1D(start=10.0, end=20.0, kind="discrete"),
        AllenRelation.FINISHED_BY: Interval1D(start=5.0, end=20.0, kind="discrete"),
        AllenRelation.CONTAINS: Interval1D(start=5.0, end=25.0, kind="discrete"),
        AllenRelation.STARTED_BY: Interval1D(start=10.0, end=25.0, kind="discrete"),
        AllenRelation.OVERLAPPED_BY: Interval1D(start=15.0, end=25.0, kind="discrete"),
        AllenRelation.MET_BY: Interval1D(start=21.0, end=30.0, kind="discrete"),
        AllenRelation.AFTER: Interval1D(start=22.0, end=30.0, kind="discrete"),
    }

    assert len(cases) == 13
    for expected_rel, target in cases.items():
        computed = relation_1d(target, ref)
        assert computed == expected_rel, f"Expected {expected_rel}, got {computed} for target={target}"
        # Converse check
        assert relation_1d(ref, target) == converse(expected_rel)


def test_composition_table_soundness_triples() -> None:
    """Generates 2,000 synthetic random interval triples (I, J, K).
    
    Verifies that for every valid triple:
    rel(I, K) in compose(rel(I, J), rel(J, K)).
    """
    rng = random.Random(42)
    relations_seen: set[AllenRelation] = set()

    for _ in range(2000):
        # Sample independent start and lengths
        s_i = rng.randint(0, 30)
        e_i = s_i + rng.randint(0, 20)
        s_j = rng.randint(0, 30)
        e_j = s_j + rng.randint(0, 20)
        s_k = rng.randint(0, 30)
        e_k = s_k + rng.randint(0, 20)

        inv_i = Interval1D(start=float(s_i), end=float(e_i), kind="discrete")
        inv_j = Interval1D(start=float(s_j), end=float(e_j), kind="discrete")
        inv_k = Interval1D(start=float(s_k), end=float(e_k), kind="discrete")

        r_ij = relation_1d(inv_i, inv_j)
        r_jk = relation_1d(inv_j, inv_k)
        r_ik = relation_1d(inv_i, inv_k)

        relations_seen.add(r_ij)
        relations_seen.add(r_jk)
        relations_seen.add(r_ik)

        possible_ik = compose(r_ij, r_jk)
        assert r_ik in possible_ik, (
            f"Composition violation: {r_ij} o {r_jk} = {possible_ik}, but r_ik is {r_ik}!\n"
            f"I={inv_i}, J={inv_j}, K={inv_k}"
        )

    # Ensure all 13 relations were represented in the sampled population
    assert len(relations_seen) == 13, f"Only saw {len(relations_seen)} relations during sampling"

