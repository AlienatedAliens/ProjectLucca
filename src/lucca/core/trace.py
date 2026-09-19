"""
Project Lucca — Latency Trace Schema & Logging
Spec 10 §1, §2
"""

import datetime
import json
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from lucca import __version__
from lucca.core.config import get_config


def now_ns() -> int:
    """High-resolution monotonic timestamp in nanoseconds.

    Backed by QueryPerformanceCounter on Windows; process-independent since Windows 8.
    Resolves F-CORE-008 clock quantization (~15.6 ms on CPython <= 3.12 GetTickCount64).
    """
    return time.perf_counter_ns()


class TurnTrace(BaseModel):
    trace_id: str
    session_id: str = ""
    version: str = __version__
    error: str = ""
    mode: Literal["audio", "transcript"] = "audio"
    route: str = "llm"
    tts_device: str = "CPU"
    asr_device: str = "cpu"

    # Monotonic timestamps (ns)
    t_key_press: int = 0
    t_key_release: int = 0  # Origin
    t_vad_done: int = 0
    t_asr_sent: int = 0
    t_asr_done: int = 0
    t_route_done: int = 0
    t_llm_sent: int = 0
    t_llm_first_token: int = 0
    t_first_chunk: int = 0
    t_tts_first_sent: int = 0
    t_tts_first_done: int = 0
    t_first_sample: int = 0  # Latency end
    t_llm_done: int = 0
    t_tts_last_done: int = 0
    t_playback_done: int = 0
    t_postturn_done: int = 0

    tokens_out: int = 0
    chunks: int = 0
    underruns: int = 0
    interrupted: bool = False

    @property
    def total_e2e_ms(self) -> float:
        if self.t_key_release > 0 and self.t_first_sample > self.t_key_release:
            return (self.t_first_sample - self.t_key_release) / 1_000_000.0
        return 0.0

    @property
    def ttft_ms(self) -> float:
        if self.t_llm_sent > 0 and self.t_llm_first_token > self.t_llm_sent:
            return (self.t_llm_first_token - self.t_llm_sent) / 1_000_000.0
        return 0.0

    @property
    def tts_first_ms(self) -> float:
        if self.t_tts_first_sent > 0 and self.t_tts_first_done > self.t_tts_first_sent:
            return (self.t_tts_first_done - self.t_tts_first_sent) / 1_000_000.0
        return 0.0


def cleanup_old_traces(logs_dir: Path, retention_days: int) -> None:
    """Purges dated traces older than retention_days (Spec 11 §8, F-CORE-056)."""
    cutoff_seconds = retention_days * 86400.0
    now_utc = datetime.datetime.now(datetime.UTC)
    for p in logs_dir.glob("traces-*.jsonl"):
        try:
            stem = p.stem
            parts = stem.split("-")
            if len(parts) == 2 and len(parts[1]) == 8 and parts[1].isdigit():
                file_date = datetime.datetime.strptime(parts[1], "%Y%m%d").replace(
                    tzinfo=datetime.UTC
                )
                age_s = (now_utc - file_date).total_seconds()
                if age_s > cutoff_seconds:
                    p.unlink(missing_ok=True)
                    continue
            if (time.time() - p.stat().st_mtime) > cutoff_seconds:
                p.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001, S110
            pass


def log_turn_trace(trace: TurnTrace) -> None:
    config = get_config()
    logs_dir = config.resolve_path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    cleanup_old_traces(logs_dir, config.log.retention_days)

    today_str = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    dated_trace_file = logs_dir / f"traces-{today_str}.jsonl"
    canonical_trace_file = logs_dir / "traces.jsonl"

    data = trace.model_dump()
    data["total_e2e_ms"] = trace.total_e2e_ms
    data["ttft_ms"] = trace.ttft_ms
    data["tts_first_ms"] = trace.tts_first_ms

    t_fields = [
        "t_key_press",
        "t_key_release",
        "t_vad_done",
        "t_asr_sent",
        "t_asr_done",
        "t_route_done",
        "t_llm_sent",
        "t_llm_first_token",
        "t_first_chunk",
        "t_tts_first_sent",
        "t_tts_first_done",
        "t_first_sample",
        "t_llm_done",
        "t_tts_last_done",
        "t_playback_done",
        "t_postturn_done",
    ]
    origin = trace.t_key_release
    if origin > 0:
        data["stages_ms"] = {
            name: round((getattr(trace, name) - origin) / 1_000_000.0, 3)
            for name in t_fields
            if getattr(trace, name) > 0
        }
    else:
        data["stages_ms"] = {}

    line = json.dumps(data) + "\n"
    with open(dated_trace_file, "a", encoding="utf-8") as f:
        f.write(line)
    with open(canonical_trace_file, "a", encoding="utf-8") as f:
        f.write(line)


try:
    _init_logs = get_config().resolve_path("logs")
    if _init_logs.exists():
        cleanup_old_traces(_init_logs, get_config().log.retention_days)
except Exception:  # noqa: BLE001, S110
    pass
