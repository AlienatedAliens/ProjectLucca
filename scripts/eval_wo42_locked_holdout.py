"""WO-43 Phase 6.2 Verification Wrapper for WO-42 Locked 150-Item Holdout."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    report_path = repo_root / "logs" / "test_reports" / "wo42_locked_holdout_150_post_router_fix_report.json"
    orig_bytes = report_path.read_bytes() if report_path.exists() else None
    try:
        res = subprocess.run(
            [sys.executable, str(repo_root / "scripts" / "evaluate_wo42_locked_holdout_150.py"), "--post-router-fix"],
            cwd=str(repo_root),
            check=False,
        )
        return res.returncode
    finally:
        if orig_bytes is not None:
            report_path.write_bytes(orig_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
