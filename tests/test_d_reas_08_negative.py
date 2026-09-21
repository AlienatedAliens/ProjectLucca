"""
Negative Regression Test Fixture for D-REAS-08 (Production-Row Check & Naming Test).

Enforces that Babble/Stitch E-Graph Macro Synthesis cannot claim *live* verification while
production decision telemetry is below the induction floor. Rule induction requires
``min_frequency = 3`` recurrences per cluster (D-REAS-06); below that floor no cluster can
form, so no macro or rule can have been induced from real usage.

Design note: an earlier version asserted ``count == 0`` against the live production DB — a
snapshot that broke as soon as Lucca recorded her first decisions. The durable invariant is
the induction floor. When production genuinely crosses it, retire this fixture together with
the "no live induction evidence" caveat it guards in the docs.
"""

import sqlite3
from pathlib import Path

import pytest

from lucca.memory.db import DatabaseManager
from lucca.reasoning.induction import RuleInducer
from lucca.reasoning.lifecycle import RuleLifecycleManager

PROD_DB_PATH = Path(r"C:\ProjectLucca\data\memory.sqlite")
INDUCTION_MIN_FREQUENCY = 3


def _production_decision_count() -> int:
    con = sqlite3.connect(str(PROD_DB_PATH))
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM decisions")
        row = cur.fetchone()
    finally:
        con.close()
    return int(row[0]) if row is not None else 0


def test_d_reas_08_production_data_below_induction_floor() -> None:
    """Production decision telemetry must still be below the N>=3 induction floor."""
    if not PROD_DB_PATH.exists():
        pytest.skip(f"Production database file does not exist at {PROD_DB_PATH}")

    count = _production_decision_count()
    assert count < INDUCTION_MIN_FREQUENCY, (
        f"Production has {count} decisions (>= induction floor {INDUCTION_MIN_FREQUENCY}). "
        "Live induction is now possible: retire this fixture and re-audit D-REAS-08 claims."
    )


def test_d_reas_08_macro_synthesis_refuses_empty_production_data(tmp_path: Path) -> None:
    """Enforces that an empty decisions table yields zero clusters and cannot claim verification."""
    db_file = tmp_path / "empty_test.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    lifecycle = RuleLifecycleManager(registered_tools={}, db=db)
    inducer = RuleInducer(db, lifecycle, min_frequency=INDUCTION_MIN_FREQUENCY)

    clusters = inducer.mine_patterns()
    assert len(clusters) == 0, "Empty decisions table must yield zero clusters"

    candidate_rules = inducer.induce_and_quarantine()
    induced_macros = inducer.induce_macros()
    assert len(candidate_rules) == 0
    assert len(induced_macros) == 0
    db.close()
