import datetime
import json
from pathlib import Path

import pytest

from lucca.core.trace import TurnTrace, log_turn_trace, now_ns


def test_clock_resolution_below_1ms() -> None:
    """
    F-CORE-008: Verify now_ns() uses high-resolution timer (QPC on Windows).
    Asserts minimal non-zero delta over 1,000 back-to-back samples is < 1,000,000 ns (1 ms).
    """
    samples = [now_ns() for _ in range(1000)]
    deltas = [samples[i] - samples[i - 1] for i in range(1, len(samples))]
    pos_deltas = [d for d in deltas if d > 0]

    assert len(pos_deltas) > 0, "All consecutive clock samples were identical"
    min_delta = min(pos_deltas)
    assert min_delta < 1_000_000, f"Clock resolution {min_delta} ns exceeds 1 ms threshold"


def test_log_turn_trace_emits_relative_stages_ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    F-CORE-008: Verify log_turn_trace emits stages_ms relative to t_key_release.
    """
    monkeypatch.setenv("LUCCA_HOME", str(tmp_path))

    t_release = 10_000_000_000
    trace = TurnTrace(
        trace_id="test-trace-01",
        mode="audio",
        t_key_release=t_release,
        t_llm_sent=t_release + 15_000_000,  # +15 ms
        t_llm_first_token=t_release + 160_000_000,  # +160 ms
        t_first_chunk=t_release + 220_000_000,  # +220 ms
        t_first_sample=t_release + 380_000_000,  # +380 ms
    )

    log_turn_trace(trace)

    trace_file = tmp_path / "logs" / "traces.jsonl"
    assert trace_file.exists()

    lines = trace_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert "stages_ms" in entry
    stages = entry["stages_ms"]

    assert stages["t_key_release"] == 0.0
    assert stages["t_llm_sent"] == 15.0
    assert stages["t_llm_first_token"] == 160.0
    assert stages["t_first_chunk"] == 220.0
    assert stages["t_first_sample"] == 380.0


def test_trace_rotation_and_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    F-CORE-056: Verify TurnTrace schema metadata fields, daily rotation, and retention cleanup.
    """
    monkeypatch.setenv("LUCCA_HOME", str(tmp_path))
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    old_file = logs_dir / "traces-20200101.jsonl"
    old_file.write_text('{"trace_id": "old"}\n', encoding="utf-8")

    trace = TurnTrace(trace_id="new-trace-01", session_id="sess-123", error="sample error")
    log_turn_trace(trace)

    # Old dated log should be pruned
    assert not old_file.exists()

    # Daily dated trace should be created
    today_str = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    new_dated_file = logs_dir / f"traces-{today_str}.jsonl"
    assert new_dated_file.exists()

    # Canonical traces.jsonl should also be written
    canonical_file = logs_dir / "traces.jsonl"
    assert canonical_file.exists()

    data = json.loads(new_dated_file.read_text(encoding="utf-8").strip().splitlines()[0])
    assert data["session_id"] == "sess-123"
    from lucca import __version__
    assert data["version"] == __version__
