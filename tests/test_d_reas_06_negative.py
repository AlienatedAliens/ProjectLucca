"""
Negative Regression Test Fixture for D-REAS-06 (Safe Rule Induction Production-Row Check).
Enforces that rule induction cannot synthesize or promote rules from zero production data.
"""

from pathlib import Path

from lucca.memory.db import DatabaseManager
from lucca.reasoning.induction import RuleInducer
from lucca.reasoning.lifecycle import RuleLifecycleManager


def test_d_reas_06_empty_telemetry_prevents_rule_generation(tmp_path: Path):
    """Verifies that rule inducer refuses to generate rules when telemetry volume is insufficient."""
    db_file = tmp_path / "zero_telemetry.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    lifecycle = RuleLifecycleManager(registered_tools={}, db=db)
    inducer = RuleInducer(db, lifecycle, min_frequency=3)

    clusters = inducer.mine_patterns()
    assert len(clusters) == 0

    rules = inducer.induce_and_quarantine()
    macros = inducer.induce_macros()
    assert len(rules) == 0
    assert len(macros) == 0
    db.close()
