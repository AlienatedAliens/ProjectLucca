"""WO-43 Phase 6.2 Verification Wrapper for WO-42 300-Item Blind Benchmark."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    tracked_files = [
        repo_root / "data" / "benchmarks" / "supervision_heldout" / "wo42_blind_300_worksheet.jsonl",
        repo_root / "logs" / "test_reports" / "wo42_statistical_power_and_ci_report.json",
    ]
    saved = {p: p.read_bytes() for p in tracked_files if p.exists()}
    try:
        res = subprocess.run(
            [sys.executable, str(repo_root / "scripts" / "evaluate_wo42_blind_300.py")],
            cwd=str(repo_root),
            check=False,
        )
        return res.returncode
    finally:
        for p, data in saved.items():
            p.write_bytes(data)


if __name__ == "__main__":
    raise SystemExit(main())
