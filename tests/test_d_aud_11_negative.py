"""
Negative Regression Test Fixture for D-AUD-11 (Decision Telemetry Data Volume Gate).

Enforces that the ">= 600 labelled decisions" data-volume gate (spec 06 §5, contradiction
register H7) is **not** satisfied by the live production database, so no document or report
may claim the Phase 6 classifier data floor has been reached.

Design note: this test deliberately asserts the *gate*, not a snapshot count. An earlier
version asserted ``count == 0``; that pinned a mutable production artifact and started
failing the moment Lucca recorded her first real decisions (2 rows on 2026-09-21). The
durable invariant is the gate itself — when production genuinely crosses 600 decisions this
test must be retired together with the claim it guards.
"""

import sqlite3
from pathlib import Path

import pytest

PROD_DB_PATH = Path(r"C:\ProjectLucca\data\memory.sqlite")
D_AUD_11_VOLUME_GATE = 600


def _production_decision_count() -> int:
    con = sqlite3.connect(str(PROD_DB_PATH))
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM decisions")
        row = cur.fetchone()
    finally:
        con.close()
    return int(row[0]) if row is not None else 0


def test_d_aud_11_volume_gate_not_yet_met_on_production_db() -> None:
    """The >= 600 decision volume gate must still be unmet on the live production database."""
    if not PROD_DB_PATH.exists():
        pytest.skip(f"Production database does not exist at {PROD_DB_PATH}")

    count = _production_decision_count()
    assert count < D_AUD_11_VOLUME_GATE, (
        f"Production decisions ({count}) now satisfy the >= {D_AUD_11_VOLUME_GATE} volume gate. "
        "Retire this negative fixture and re-audit every document that cites D-AUD-11 as unmet."
    )
