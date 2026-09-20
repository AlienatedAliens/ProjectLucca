"""
Negative Regression Test Fixture for D-AUD-11 (Decision Telemetry Data Volume Gate).
Enforces that a data volume claim of >= 600 records fails on empty production database.
"""

import sqlite3
from pathlib import Path
import pytest


def test_d_aud_11_volume_gate_fails_on_empty_db():
    """Verifies that the claimed >= 600 records volume gate does not pass on empty database."""
    prod_db_path = Path(r"C:\ProjectLucca\data\memory.sqlite")
    if not prod_db_path.exists():
        pytest.skip("Production database does not exist at C:\\ProjectLucca\\data\\memory.sqlite")

    con = sqlite3.connect(str(prod_db_path))
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM decisions")
    count = cur.fetchone()[0]
    con.close()

    # The claim was: ">= 600 records data volume gate counts first label per decision"
    # Live production count is 0, so the 600 record threshold fails
    assert count < 600, f"Expected production decisions to fail >= 600 threshold, got {count}"
    assert count == 0, f"Expected 0 production decisions, got {count}"
