"""
Negative Regression Tests for D-REAS-08 (Babble/Stitch E-Graph Macro Synthesis).

History: this file previously carried the production-row tripwire
(``test_d_reas_08_production_data_below_induction_floor``), which failed by design
once production crossed the N>=3 induction floor. Provenance check 2026-09-26
(``scratch/check_decisions_provenance.py``) confirmed 21 genuine usage decisions
(6 sessions, 2026-09-21..25, real operator transcripts via the terminal harness),
so the tripwire was retired per its own instructions. The empty-data negative
guard below remains: induction from an empty decisions table must yield nothing.
"""

from pathlib import Path

from lucca.memory.db import DatabaseManager
from lucca.reasoning.induction import RuleInducer
from lucca.reasoning.lifecycle import RuleLifecycleManager

INDUCTION_MIN_FREQUENCY = 3


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
