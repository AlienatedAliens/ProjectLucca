import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lucca.core.config import get_config


@pytest.fixture(autouse=True)
def _isolated_lucca_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    home = tmp_path / "lucca_home"
    home.mkdir(parents=True, exist_ok=True)
    for sub in ("models", "data", "workspace", "inbox", "logs", "cache", "tmp"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()
    yield home
    get_config.cache_clear()


@pytest.fixture(autouse=True)
def _check_tier_prerequisites(request: pytest.FixtureRequest) -> None:
    hw_marker = request.node.get_closest_marker("hw")
    net_marker = request.node.get_closest_marker("net")

    if hw_marker is not None:
        try:
            req = urllib.request.Request("http://127.0.0.1:8080/health")
            with urllib.request.urlopen(req, timeout=2.0) as resp:  # noqa: S310
                if resp.status != 200:
                    pytest.fail(
                        f"Live hardware test failed fast: llama-server returned HTTP {resp.status} on /health"
                    )
        except Exception as e:
            pytest.fail(
                f"Live hardware test failed fast: llama-server unreachable at http://127.0.0.1:8080/health ({e})"
            )

    if net_marker is not None:
        try:
            wsl_bin = shutil.which("wsl") or "wsl"
            res = subprocess.run(  # noqa: S603
                [wsl_bin, "-d", "Ubuntu", "--", "docker", "info"],
                capture_output=True,
                timeout=5.0,
                check=False,
            )
            if res.returncode != 0:
                pytest.fail(
                    f"Network test failed fast: 'wsl -d Ubuntu -- docker info' returned code {res.returncode}"
                )
        except Exception as e:
            pytest.fail(f"Network test failed fast: Docker in WSL2 unreachable ({e})")


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config._session_start_time = time.time()  # type: ignore[attr-defined]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    tier = os.environ.get("LUCCA_TEST_TIER")
    if not tier:
        return

    passed = 0
    failed = 0
    xfailed = 0
    skipped = 0
    duration_s = 0.0

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        passed = len(reporter.stats.get("passed", []))
        failed = len(reporter.stats.get("failed", []))
        xfailed = len(reporter.stats.get("xfailed", []))
        skipped = len(reporter.stats.get("skipped", []))

    start_time = getattr(session.config, "_session_start_time", 0.0)
    if start_time > 0:
        duration_s = time.time() - start_time

    markers_expr = session.config.option.markexpr or ""
    repo_root = Path(__file__).resolve().parent.parent
    reports_dir = repo_root / "logs" / "test_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    utc_ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_file = reports_dir / f"pytest_{tier}_{utc_ts}.json"

    report_data = {
        "tier": tier,
        "command": " ".join(sys.argv),
        "markers_expr": markers_expr,
        "passed": passed,
        "failed": failed,
        "xfailed": xfailed,
        "skipped": skipped,
        "duration_s": round(duration_s, 2),
        "exitstatus": int(exitstatus),
        "created_at_utc": utc_ts,
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)


@pytest.fixture
def sample_state():
    from lucca.core.schemas import RuleState

    return RuleState(
        schema_version=1,
        transcript="open calculator",
        transcript_lower="open calculator",
        intent="launch_app",
        intent_conf=0.95,
        entities={"app": ["calculator"]},
        apps_running=frozenset(),
    )
