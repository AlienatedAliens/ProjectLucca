"""
Unit tests for lucca-admin CLI.
Spec 11 §7, F-CORE-026, F-CORE-027, F-DRIFT-003
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lucca.admin import main


def test_admin_unknown_command_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    """F-CORE-026: Unknown commands must exit 2 with usage on stderr."""
    with pytest.raises(SystemExit) as exc_info:
        main(["definitely-not-a-command"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "usage: lucca-admin" in captured.err


def test_admin_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    """Verifies help command exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "usage: lucca-admin" in captured.out


def test_admin_stubs_exit_3(capsys: pytest.CaptureFixture[str]) -> None:
    """F-CORE-027: Stubs (metrics, memory, rules, router, replay) exit 3 with message."""
    for stub in ["metrics", "memory", "rules", "router", "replay"]:
        with pytest.raises(SystemExit) as exc_info:
            main([stub])
        assert exc_info.value.code == 3
        captured = capsys.readouterr()
        assert "not implemented (tracked as F-CORE-027)" in captured.out


def test_admin_latency_no_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """F-DRIFT-003: Empty logs directory handled gracefully without crash."""
    monkeypatch.setenv("LUCCA_HOME", str(tmp_path))
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)

    with pytest.raises(SystemExit) as exc_info:
        main(["latency", "--last", "10"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "No matching trace records found" in captured.out


def test_admin_latency_report_from_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    F-DRIFT-003 & F-CORE-027: Real trace records parsed into median/p95 latency report.
    """
    monkeypatch.setenv("LUCCA_HOME", str(tmp_path))
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    traces_file = logs_dir / "traces.jsonl"

    synthetic_trace = {
        "trace_id": "test-trace-01",
        "session_id": "sess-01",
        "mode": "audio",
        "origin": "ptt",
        "total_e2e_ms": 475.0,
        "ttft_ms": 180.0,
        "tts_first_ms": 150.0,
        "stages_ms": {
            "t_key_release": 0.0,
            "t_llm_sent": 15.0,
            "t_llm_first_token": 195.0,
            "t_first_chunk": 285.0,
            "t_tts_first_sent": 285.0,
            "t_tts_first_done": 435.0,
            "t_first_sample": 475.0,
        },
    }
    traces_file.write_text(json.dumps(synthetic_trace) + "\n", encoding="utf-8")

    out_file = tmp_path / "report.json"
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "latency",
                "--last",
                "10",
                "--mode",
                "audio",
                "--format",
                "json",
                "--output",
                str(out_file),
            ]
        )
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)

    stages_by_name = {s["stage"]: s for s in data}
    assert stages_by_name["S1 PTT->dispatch"]["measured_med"] == 15.0
    assert stages_by_name["S2 TTFT"]["measured_med"] == 180.0
    assert stages_by_name["S3 first chunk"]["measured_med"] == 90.0
    assert stages_by_name["S4 TTS first"]["measured_med"] == 150.0
    assert stages_by_name["S5 to speaker"]["measured_med"] == 40.0
    assert stages_by_name["Total E2E"]["measured_med"] == 475.0
    assert stages_by_name["Total E2E"]["status"] == "PASS"

    # Verify JSON output file
    assert out_file.exists()
    assert json.loads(out_file.read_text(encoding="utf-8")) == data

    # Test Markdown format
    md_file = tmp_path / "report.md"
    with pytest.raises(SystemExit) as exc_info2:
        main(
            [
                "latency",
                "--last",
                "10",
                "--mode",
                "audio",
                "--format",
                "markdown",
                "--output",
                str(md_file),
            ]
        )
    assert exc_info2.value.code == 0
    md_content = md_file.read_text(encoding="utf-8")
    assert "Lucca Latency Report" in md_content
    assert "S1 PTT->dispatch" in md_content


def test_admin_models_verify(capsys: pytest.CaptureFixture[str]) -> None:
    """Verifies models verify subcommand delegates to check_models_manifest."""
    with patch("lucca.admin.check_models_manifest", return_value=(True, "Weights verified")):
        with pytest.raises(SystemExit) as exc_info:
            main(["models", "verify"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "[PASS] Weights verified" in captured.out
