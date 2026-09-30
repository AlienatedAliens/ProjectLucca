"""
Project Lucca — Latency Trace Schema & Logging
Spec 10 §1, §2
"""

import datetime
import json
import logging
import time
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, JsonValue

from lucca import __version__
from lucca.core.config import get_config

logger = logging.getLogger(__name__)



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
    mode: Literal["audio", "transcript", "vision"] = "audio"
    origin: Literal["ptt", "text"] = "ptt"
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

    # WO-9 A5: convergence-loop telemetry
    rounds_used: int = 0
    cap_hit: bool = False
    enable_thinking: bool | None = None

    # WO-21 Phase 4: Theory-of-Mind & Case-Based Stubs telemetry
    user_model_fired: bool = False
    episode_recall_fired: bool = False

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
        except Exception as exc:  # noqa: BLE001, S110
            logger.debug("cleanup_trace_file_failed: %s", exc)


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
except Exception as exc:  # noqa: BLE001, S110
    logger.debug("init_trace_cleanup_failed: %s", exc)


class StageStat(BaseModel):
    stage: str
    from_to: str
    budget_med: float
    gate_p95: float
    measured_med: float | None = None
    measured_p95: float | None = None
    count: int = 0
    status: str = "NO_DATA"
    notes: str = ""


AUDIO_STAGE_DEFS: list[tuple[str, str, float, float, str]] = [
    (
        "S1 PTT->dispatch",
        "t_key_release -> t_llm_sent",
        15.0,
        30.0,
        "VAD trim + wav encode + HTTP send",
    ),
    (
        "S2 TTFT",
        "t_llm_sent -> t_llm_first_token",
        180.0,
        300.0,
        "Phase 0 measured; estimate 140-180",
    ),
    (
        "S3 first chunk",
        "t_llm_first_token -> t_first_chunk",
        90.0,
        150.0,
        ">= 24 chars at ~60-90 tok/s",
    ),
    ("S4 TTS first", "t_first_chunk -> t_tts_first_done", 150.0, 180.0, "device ladder gate"),
    (
        "S5 to speaker",
        "t_tts_first_done -> t_first_sample",
        40.0,
        80.0,
        "60 ms jitter buffer overlap",
    ),
    (
        "Total E2E",
        "t_key_release -> t_first_sample",
        475.0,
        800.0,
        "canonical gate (median <= 600, p95 <= 800)",
    ),
]

TRANSCRIPT_STAGE_DEFS: list[tuple[str, str, float, float, str]] = [
    (
        "S1b ASR",
        "t_key_release -> t_asr_done",
        250.0,
        400.0,
        "synchronous ASR before LLM dispatch",
    ),
    ("S2 TTFT", "t_llm_sent -> t_llm_first_token", 180.0, 300.0, "Phase 0 measured"),
    (
        "S3 first chunk",
        "t_llm_first_token -> t_first_chunk",
        90.0,
        150.0,
        ">= 24 chars at ~60-90 tok/s",
    ),
    ("S4 TTS first", "t_first_chunk -> t_tts_first_done", 150.0, 180.0, "device ladder gate"),
    (
        "S5 to speaker",
        "t_tts_first_done -> t_first_sample",
        40.0,
        80.0,
        "60 ms jitter buffer overlap",
    ),
    (
        "Total E2E",
        "t_key_release -> t_first_sample",
        700.0,
        1000.0,
        "cascade gate (median <= 800, p95 <= 1000)",
    ),
]


def _extract_stage_delta(rec: dict[str, JsonValue], stage_name: str) -> float | None:
    stages_ms_val = rec.get("stages_ms")
    stages_ms: dict[str, JsonValue] = stages_ms_val if isinstance(stages_ms_val, dict) else {}

    def get_ms(point: str) -> float | None:
        if point in stages_ms:
            v = stages_ms[point]
            if isinstance(v, (int, float)):
                return float(v)
        raw_ns = rec.get(point)
        origin_ns = rec.get("t_key_release", 0)
        if (
            isinstance(raw_ns, (int, float))
            and raw_ns > 0
            and isinstance(origin_ns, (int, float))
            and origin_ns > 0
        ):
            return (raw_ns - origin_ns) / 1_000_000.0
        return None

    if stage_name == "S1 PTT->dispatch":
        llm_sent = get_ms("t_llm_sent")
        return llm_sent if llm_sent is not None and llm_sent >= 0 else None

    if stage_name == "S1b ASR":
        asr_done = get_ms("t_asr_done")
        return asr_done if asr_done is not None and asr_done >= 0 else None

    if stage_name == "S2 TTFT":
        ttft = rec.get("ttft_ms")
        if isinstance(ttft, (int, float)) and ttft > 0:
            return float(ttft)
        t_first = get_ms("t_llm_first_token")
        t_sent = get_ms("t_llm_sent")
        if t_first is not None and t_sent is not None and t_first >= t_sent:
            return t_first - t_sent
        return None

    if stage_name == "S3 first chunk":
        t_chunk = get_ms("t_first_chunk")
        t_first = get_ms("t_llm_first_token")
        if t_chunk is not None and t_first is not None and t_chunk >= t_first:
            return t_chunk - t_first
        return None

    if stage_name == "S4 TTS first":
        t_done = get_ms("t_tts_first_done")
        t_chunk = get_ms("t_first_chunk")
        t_sent = get_ms("t_tts_first_sent")
        if t_done is not None:
            if t_chunk is not None and t_done >= t_chunk:
                return t_done - t_chunk
            if t_sent is not None and t_done >= t_sent:
                return t_done - t_sent
        tts_first = rec.get("tts_first_ms")
        if isinstance(tts_first, (int, float)) and tts_first > 0:
            return float(tts_first)
        return None

    if stage_name == "S5 to speaker":
        t_sample = get_ms("t_first_sample")
        t_done = get_ms("t_tts_first_done")
        if t_sample is not None and t_done is not None and t_sample >= t_done:
            return t_sample - t_done
        return None

    if stage_name == "Total E2E":
        total_e2e = rec.get("total_e2e_ms")
        if isinstance(total_e2e, (int, float)) and total_e2e > 0:
            return float(total_e2e)
        t_sample = get_ms("t_first_sample")
        return t_sample if t_sample is not None and t_sample >= 0 else None

    return None


def compute_latency_statistics(
    traces: list[dict[str, JsonValue]],
    mode: Literal["audio", "transcript", "vision"] = "audio",
) -> list[StageStat]:
    """Computes median and p95 latency per Spec 10 stage."""
    stage_defs = AUDIO_STAGE_DEFS if mode == "audio" else TRANSCRIPT_STAGE_DEFS
    results: list[StageStat] = []

    for name, from_to, b_med, g_p95, notes in stage_defs:
        vals: list[float] = []
        for r in traces:
            d = _extract_stage_delta(r, name)
            if d is not None and d >= 0:
                vals.append(d)

        if not vals:
            results.append(
                StageStat(
                    stage=name,
                    from_to=from_to,
                    budget_med=b_med,
                    gate_p95=g_p95,
                    notes=notes,
                    status="NO_DATA",
                )
            )
            continue

        med = round(float(np.median(vals)), 2)
        p95 = round(float(np.percentile(vals, 95)), 2)

        if name == "Total E2E":
            gate_med = 600.0 if mode == "audio" else 800.0
            gate_max_p95 = 800.0 if mode == "audio" else 1000.0
            if med <= gate_med and p95 <= gate_max_p95:
                status = "PASS"
            elif med > gate_med * 1.25:
                status = "REGRESSION"
            else:
                status = "FAIL"
        elif med <= b_med and p95 <= g_p95:
            status = "PASS"
        elif med > b_med * 1.25:
            status = "REGRESSION"
        else:
            status = "FAIL"

        results.append(
            StageStat(
                stage=name,
                from_to=from_to,
                budget_med=b_med,
                gate_p95=g_p95,
                measured_med=med,
                measured_p95=p95,
                count=len(vals),
                status=status,
                notes=notes,
            )
        )
    return results


def format_latency_markdown(
    stats: list[StageStat],
    mode: str = "audio",
    sample_count: int = 0,
) -> str:
    """Renders Spec 10 §2 latency report as Markdown."""
    header = (
        "| Stage | From -> To | Budget (med / p95) | Measured Median | "
        "Measured p95 | Count | Status | Notes |"
    )
    lines = [
        f"# Lucca Latency Report — {mode.capitalize()} Mode",
        f"**Sample Count:** {sample_count} turns",
        "",
        header,
        "|---|---|---|---|---|---|---|---|",
    ]

    for s in stats:
        med_str = f"{s.measured_med:.1f} ms" if s.measured_med is not None else "-"
        p95_str = f"{s.measured_p95:.1f} ms" if s.measured_p95 is not None else "-"
        lines.append(
            f"| {s.stage} | {s.from_to} | {s.budget_med:.0f} / {s.gate_p95:.0f} ms | "
            f"{med_str} | {p95_str} | {s.count} | {s.status} | {s.notes} |"
        )
    return "\n".join(lines)
