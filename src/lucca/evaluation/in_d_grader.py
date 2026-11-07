"""Backwards-compatibility re-export shim for lucca.eval.in_d_grader (WO-43 Phase 4.1)."""

from __future__ import annotations

from lucca.eval.in_d_grader import (
    INDGraderReport,
    INDSkillEntry,
    REPORT_DIR,
    grade_in_d,
    save_in_d_report,
)

__all__ = [
    "INDGraderReport",
    "INDSkillEntry",
    "REPORT_DIR",
    "grade_in_d",
    "save_in_d_report",
]
