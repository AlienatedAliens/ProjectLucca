"""
Negative Regression Test Fixture for D-REAS-08 (Production-Row Check & Naming Test).
Enforces that Babble/Stitch E-Graph Macro Synthesis does not claim live verification
when executed against empty production decision telemetry.
"""

import sqlite3
from pathlib import Path
import pytest
from lucca.reasoning.induction import RuleInducer
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.memory.db import DatabaseManager


def test_d_reas_08_production_data_is_zero():
    """Verifies that production SQLite database currently has zero recorded decisions."""
    prod_db_path = Path(r"C:\ProjectLucca\data\memory.sqlite")
    if not prod_db_path.exists():
        pytest.skip("Production database file does not exist at C:\\ProjectLucca\\data\\memory.sqlite")

    con = sqlite3.connect(str(prod_db_path))
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM decisions")
    count = cur.fetchone()[0]
    con.close()

    assert count == 0, f"Expected 0 production decisions, found {count}"


def test_d_reas_08_macro_synthesis_refuses_empty_production_data(tmp_path: Path):
    """Enforces that an empty decisions table yields zero clusters and cannot claim verification."""
    db_file = tmp_path / "empty_test.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    lifecycle = RuleLifecycleManager(registered_tools={}, db=db)
    inducer = RuleInducer(db, lifecycle, min_frequency=3)

    clusters = inducer.mine_patterns()
    assert len(clusters) == 0, "Empty decisions table must yield zero clusters"

    candidate_rules = inducer.induce_and_quarantine()
    induced_macros = inducer.induce_macros()
    assert len(candidate_rules) == 0
    assert len(induced_macros) == 0
    db.close()
