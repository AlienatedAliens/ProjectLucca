"""
Project Lucca — IN-D Mechanical Grader Script
Executes offline DB / rule engine query to grade the IN-D learned skill metric.
Emits report to logs/test_reports/personhood/in_d_report_<ts>.json
"""

import sys
from pathlib import Path

# Add src to python path if run standalone
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

from lucca.evaluation.in_d_grader import grade_in_d, save_in_d_report
from lucca.memory.db import DatabaseManager


def main() -> int:
    db_path = root_dir / "data" / "lucca.sqlite"
    db = DatabaseManager(db_path) if db_path.exists() else None

    report = grade_in_d(db=db)
    out_file = save_in_d_report(report)
    print(f"IN-D Report saved to: {out_file}")
    print(f"Status: {report.status}")
    print(f"Quarantined learned skills: {report.learned_skills_quarantined}")
    print(f"Active learned skills: {report.learned_skills_active}")
    print(f"Guard (0 to ACTIVE) passed: {report.guard_active_zero_passed}")

    return 0 if report.guard_active_zero_passed else 1


if __name__ == "__main__":
    sys.exit(main())
