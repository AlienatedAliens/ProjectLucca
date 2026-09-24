"""
Regression test for commit 0ef309d tool_whitelist.toml truncation.
Block B Item 1 — Restores and protects the audited 5-app suite.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WHITELIST_PATH = REPO_ROOT / "config" / "tool_whitelist.toml"


def test_tool_whitelist_regression_0ef309d() -> None:
    """
    Regression test for commit 0ef309d truncation.
    Asserts >=5 apps, each with non-empty exe, and that
    calc, notepad, terminal, task_manager (and browser) keys exist.
    """
    assert WHITELIST_PATH.exists(), f"Missing configuration file at: {WHITELIST_PATH}"

    with open(WHITELIST_PATH, "rb") as f:
        data = tomllib.load(f)

    assert "apps" in data and isinstance(data["apps"], dict), "Malformed TOML: missing 'apps' table"
    apps = data["apps"]

    # Invariant: at least 5 apps
    assert len(apps) >= 5, (
        f"Expected >= 5 whitelisted applications, found {len(apps)}: {list(apps.keys())}"
    )

    # Invariant: mandatory keys
    required_keys = ["calc", "notepad", "terminal", "task_manager"]
    for key in required_keys:
        assert key in apps, f"Required application key '{key}' missing from tool_whitelist.toml"

    # Invariant: non-empty exe for all entries
    for key, entry in apps.items():
        assert isinstance(entry, dict), f"App entry for '{key}' must be a table/dict"
        exe = entry.get("exe")
        assert exe and isinstance(exe, str) and exe.strip(), (
            f"App '{key}' must have a non-empty 'exe' string, found: {exe!r}"
        )


def test_whitelist_parse_error_fails_closed(tmp_path: Path) -> None:
    """F-SBX-013: A corrupted tool_whitelist.toml must fail closed, refusing launches."""
    from lucca.sandbox.launcher import AppLauncher

    corrupted_toml = tmp_path / "corrupted_whitelist.toml"
    corrupted_toml.write_text("this is [not valid toml :::", encoding="utf-8")

    launcher = AppLauncher(config_path=corrupted_toml, execute=False)
    assert launcher.whitelist_error is not None
    assert len(launcher.apps) == 0

    ok, msg = launcher.launch("calculator")
    assert not ok
    assert "unparseable" in msg
