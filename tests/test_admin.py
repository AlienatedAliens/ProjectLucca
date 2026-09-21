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
    """F-CORE-027: Stubs (metrics, router, replay) exit 3 with message."""
    for stub in ["metrics", "router", "replay"]:
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


def test_admin_rules_cli_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tests lucca-admin rules list, approve, and retire commands."""
    from lucca.core.schemas import Plan, RuleState, ToolCall
    from lucca.memory.db import DatabaseManager
    from lucca.reasoning.lifecycle import RuleLifecycleManager

    db_path = tmp_path / "admin_test.sqlite"
    monkeypatch.setattr("lucca.memory.db.DEFAULT_DB_PATH", db_path)

    # 1. rules list with empty DB
    with pytest.raises(SystemExit) as exc_info:
        main(["rules", "--db", str(db_path), "list"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "No rules currently registered" in captured.out

    # 1b. rules register via CLI
    rule_src = """
    (rule "read-notes-v1"
      :when (and (intent= "read_file") (entity-has? "rel_path" "notes.txt"))
      :plan (list (tool "read_file" :rel_path "notes.txt"))
      :priority 5)
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["rules", "--db", str(db_path), "register", rule_src])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "SUCCESS:" in captured.out
    assert "QUARANTINE" in captured.out

    # 2. Simulate 5 clusters so it reaches PENDING_APPROVAL
    db = DatabaseManager(db_path)
    db.migrate()
    mgr = RuleLifecycleManager(db=db)
    state = RuleState(schema_version=1, intent="read_file", entities={"rel_path": ["notes.txt"]})
    plan = Plan(actions=[ToolCall(tool="read_file", args={"rel_path": "notes.txt"}, call_id="c1")])
    for i in range(5):
        mgr.record_shadow(
            "read-notes-v1",
            matched=True,
            cluster_id=f"c_{i}",
            state_snapshot=state,
            plan_snapshot=plan,
        )
    mgr.promote_if_eligible("read-notes-v1")
    assert mgr.rules["read-notes-v1"].status == "PENDING_APPROVAL"

    # 3. rules list displays the rule in PENDING_APPROVAL
    with pytest.raises(SystemExit) as exc_info:
        main(["rules", "--db", str(db_path), "list"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "read-notes-v1" in captured.out
    assert "PENDING_APPROVAL" in captured.out

    # 4. Human operator approves the rule via CLI
    with pytest.raises(SystemExit) as exc_info:
        main(["rules", "--db", str(db_path), "approve", "read-notes-v1", "--approver", "sec-lead"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "SUCCESS:" in captured.out
    assert "promoted to ACTIVE" in captured.out

    # 5. rules list displays the rule as ACTIVE
    with pytest.raises(SystemExit) as exc_info:
        main(["rules", "--db", str(db_path), "list"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "ACTIVE" in captured.out

    # 6. Human operator retires the rule via CLI
    with pytest.raises(SystemExit) as exc_info:
        main(["rules", "--db", str(db_path), "retire", "read-notes-v1"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "RETIRED:" in captured.out


def test_admin_memory_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tests lucca-admin memory commands (list-review, mark/list/unmark-topic, rollup)."""
    from lucca.memory.db import DatabaseManager

    db_path = tmp_path / "memory_admin_test.sqlite"
    monkeypatch.setattr("lucca.memory.db.DEFAULT_DB_PATH", db_path)

    db = DatabaseManager(db_path)
    db.migrate()

    # 1. review-queue on empty queue
    with pytest.raises(SystemExit) as exc_info:
        main(["memory", "--db", str(db_path), "review-queue"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "No review queue items with status 'PENDING'" in captured.out

    # 2. mark-review
    with pytest.raises(SystemExit) as exc_info:
        main(["memory", "--db", str(db_path), "mark-review", "personal_finances"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "marked as review-required" in captured.out

    # 3. list-topics
    with pytest.raises(SystemExit) as exc_info:
        main(["memory", "--db", str(db_path), "list-topics"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "personal_finances" in captured.out

    # 4. unmark-review
    with pytest.raises(SystemExit) as exc_info:
        main(["memory", "--db", str(db_path), "unmark-review", "personal_finances"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "removed from review-required" in captured.out

    # 5. rollup
    with pytest.raises(SystemExit) as exc_info:
        main(["memory", "--db", str(db_path), "rollup"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Nightly roll-up complete" in captured.out
