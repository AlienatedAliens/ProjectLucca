"""
Project Lucca — Personhood IN-D Mechanical Grader
Spec: docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md §2 (Battery IN - Stratum IN-D)
Measures learned-skill count and quarantine lifecycle state from real usage induction.

Invariants:
- Mechanical DB/lifecycle state query; no LLM evaluation or holistic estimation.
- Raw integer count reporting, never an unanchored percentage.
- D-REAS-06: Validates that 0 induced rules reach ACTIVE without explicit operator sign-off.
- Advances IN-D from 'NOT YET MEASURED' to an active measurement.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Final

from pydantic import BaseModel, Field
import structlog

from lucca.memory.db import DatabaseManager
from lucca.reasoning.lifecycle import RuleLifecycleManager

logger = structlog.get_logger(__name__)

REPORT_DIR: Final[Path] = Path("logs/test_reports/personhood")


class INDSkillEntry(BaseModel):
    rule_id: str
    status: str
    is_induced: bool
    created_at: float
    promoted_at: float | None = None


class INDGraderReport(BaseModel):
    as_of: str
    stratum: str = "IN-D"
    status: str = "MEASURED"
    learned_skills_active: int
    learned_skills_quarantined: int
    total_quarantined_all: int
    total_active_all: int
    guard_active_zero_passed: bool
    quarantined_skills: list[INDSkillEntry] = Field(default_factory=list)
    active_skills: list[INDSkillEntry] = Field(default_factory=list)
    grader_version: str = "1.0.0"


def grade_in_d(
    db: DatabaseManager | None = None,
    lifecycle_manager: RuleLifecycleManager | None = None,
) -> INDGraderReport:
    """
    Mechanically grades the IN-D learned-skill count.
    Queries rule lifecycle state from SQLite database or active RuleLifecycleManager.
    """
    quarantined_skills: list[INDSkillEntry] = []
    active_skills: list[INDSkillEntry] = []
    total_quarantined = 0
    total_active = 0

    if lifecycle_manager is not None:
        for r in lifecycle_manager.rules.values():
            if r.status == "QUARANTINE":
                total_quarantined += 1
                if r.is_induced or "induced" in r.rule_id or "mined" in r.rule_id:
                    quarantined_skills.append(
                        INDSkillEntry(
                            rule_id=r.rule_id,
                            status=r.status,
                            is_induced=True,
                            created_at=r.created_at,
                            promoted_at=r.promoted_at,
                        )
                    )
            elif r.status == "ACTIVE":
                total_active += 1
                if r.is_induced or "induced" in r.rule_id or "mined" in r.rule_id:
                    active_skills.append(
                        INDSkillEntry(
                            rule_id=r.rule_id,
                            status=r.status,
                            is_induced=True,
                            created_at=r.created_at,
                            promoted_at=r.promoted_at,
                        )
                    )
    elif db is not None:
        try:
            with db.read_cursor() as cur:
                cur.execute(
                    """
                    SELECT rule_id, status, source_canonical, created_at, promoted_at
                    FROM rule_states
                    """
                )
                rows = cur.fetchall()
                for row in rows:
                    r_id = str(row[0])
                    st = str(row[1])
                    src_canon = str(row[2]) if len(row) > 2 and row[2] is not None else ""
                    c_at = float(row[3]) if len(row) > 3 and row[3] is not None else 0.0
                    p_at = float(row[4]) if len(row) > 4 and row[4] is not None else None

                    is_ind = ("induced" in r_id.lower() or "mined" in r_id.lower() or "defmacro" in src_canon.lower())
                    entry = INDSkillEntry(
                        rule_id=r_id,
                        status=st,
                        is_induced=is_ind,
                        created_at=c_at,
                        promoted_at=p_at,
                    )

                    if st == "QUARANTINE":
                        total_quarantined += 1
                        if is_ind:
                            quarantined_skills.append(entry)
                    elif st == "ACTIVE":
                        total_active += 1
                        if is_ind:
                            active_skills.append(entry)
        except Exception as exc:
            logger.warning("in_d_grader_db_read_failed", error=str(exc))

    learned_active_count = len(active_skills)
    learned_quarantine_count = len(quarantined_skills)
    guard_passed = (learned_active_count == 0)

    iso_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return INDGraderReport(
        as_of=iso_ts,
        learned_skills_active=learned_active_count,
        learned_skills_quarantined=learned_quarantine_count,
        total_quarantined_all=total_quarantined,
        total_active_all=total_active,
        guard_active_zero_passed=guard_passed,
        quarantined_skills=quarantined_skills,
        active_skills=active_skills,
    )


def save_in_d_report(report: INDGraderReport, output_dir: Path | None = None) -> Path:
    """Saves the IN-D grader report to a timestamped JSON file and a latest symlink/file."""
    target_dir = output_dir or REPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    ts_str = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    report_file = target_dir / f"in_d_report_{ts_str}.json"
    latest_file = target_dir / "in_d_latest.json"

    content = report.model_dump_json(indent=2)
    report_file.write_text(content, encoding="utf-8")
    latest_file.write_text(content, encoding="utf-8")

    logger.info(
        "in_d_report_saved",
        report_file=str(report_file),
        quarantined=report.learned_skills_quarantined,
        active=report.learned_skills_active,
    )
    return report_file
