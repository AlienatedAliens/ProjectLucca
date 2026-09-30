"""
Project Lucca — Visual Pipeline Debugger & Live Flow Tracer
Spec 01 §1, Spec 10 §1-§3, ADR-005

Records granular stage-by-stage transitions across the hydraulic cascade:
Tank 1: Input Ingestion & Demulsifier
Tank 2: Conformal Intent Valve & Safety Shunt
Tank 3: MicroScheme Symbolic Centrifuge
Tank 4: Epistemic Clarifier & Context Infusion
Tank 5: Neural Deliberation Boiler
Tank 6: Sandbox Execution Turbine
Tank 6b: Recirculation Loop (Self-Debug)
Tank 7: Mind-Mouth Purifier & Equivalence Grader
Tank 8: Acoustic Turbine & Visual UI
Tank 9: Autobiographical WAL Basin

Outputs:
- logs/telemetry/live_pipeline_state.json  (Real-time live status for visual debugger)
- logs/telemetry/flow_traces.jsonl        (Append-only replayable forensic records)
- logs/telemetry/latest_trace.json        (Quick inspection of last completed flow)
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from pathlib import Path

from pydantic import JsonValue

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
TELEMETRY_DIR = REPO_ROOT / "logs" / "telemetry"
TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)

LIVE_STATE_FILE = TELEMETRY_DIR / "live_pipeline_state.json"
FLOW_TRACES_FILE = TELEMETRY_DIR / "flow_traces.jsonl"
LATEST_TRACE_FILE = TELEMETRY_DIR / "latest_trace.json"


class PipelineTracer:
    """Singleton/thread-safe flow tracer for real-time visual debugging and replay."""

    _instance: PipelineTracer | None = None

    def __init__(self) -> None:
        self.active_trace_id: str = ""
        self.task_info: dict[str, JsonValue] = {}
        self.tanks: list[dict[str, JsonValue]] = []
        self.current_tank_id: str = ""
        self.stage_start_t: float = 0.0
        self.total_start_t: float = 0.0
        self.current_stage_meta: dict[str, JsonValue] = {}
        self.config_metadata: dict[str, JsonValue] = {
            "model": "active-brain-model",
            "context_size": 16384,
            "hardware": "NVIDIA GeForce RTX 5080 Laptop GPU (16 GB) + Intel Core Ultra 9 275HX",
        }
        self.stats = {"completed": 0, "passed": 0, "failed": 0, "current_accuracy": 0.0}

    @classmethod
    def get_instance(cls) -> PipelineTracer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_environment_config(self, config_meta: dict[str, JsonValue]) -> None:
        """Register active model, git commit, seed, and context configuration."""
        self.config_metadata = config_meta

    def update_stats(self, completed: int, passed: int, failed: int) -> None:
        acc = (passed / completed * 100.0) if completed > 0 else 0.0
        self.stats = {
            "completed": completed,
            "passed": passed,
            "failed": failed,
            "current_accuracy": round(acc, 2),
        }

    def start_flow(self, trace_id: str, task_info: dict[str, JsonValue]) -> None:
        """Start a new prompt/problem flow-through."""
        self.active_trace_id = trace_id
        self.task_info = task_info
        self.tanks = []
        self.current_tank_id = "tank_1_ingestion"
        self.total_start_t = time.perf_counter()
        self.stage_start_t = self.total_start_t
        self.current_stage_meta = {}

        self._write_live_state(
            active=True,
            current_stage="tank_1_ingestion",
            stage_name="Input Ingestion & Demulsifier",
            details="Ingesting prompt string...",
        )

    def transition_stage(
        self,
        tank_id: str,
        tank_name: str,
        subsystem: str,
        received_payload: JsonValue,
        details: str = "",
    ) -> None:
        """Move from one tank to the next."""
        self.current_tank_id = tank_id
        self.stage_start_t = time.perf_counter()
        self.current_stage_meta = {
            "tank_id": tank_id,
            "tank_name": tank_name,
            "subsystem": subsystem,
            "received": str(received_payload)[:2000],
            "details": details,
        }

        self._write_live_state(
            active=True,
            current_stage=tank_id,
            stage_name=tank_name,
            details=details or f"Processing in {tank_name}...",
        )

    def record_stage_result(
        self,
        tank_id: str,
        tank_name: str,
        subsystem: str,
        status: str,
        action: str,
        output_payload: JsonValue,
        stderr: str = "",
        custom_duration_ms: float | None = None,
        unmeasured: bool = False,
    ) -> None:
        """Record the outcome of a tank's computation."""
        now = time.perf_counter()
        if unmeasured:
            dur_ms = None
        elif custom_duration_ms is not None:
            dur_ms = custom_duration_ms
        else:
            dur_ms = round((now - self.stage_start_t) * 1000.0, 2)

        stage_record = {
            "tank_id": tank_id,
            "tank_name": tank_name,
            "subsystem": subsystem,
            "status": status,
            "duration_ms": dur_ms,
            "unmeasured": unmeasured,
            "received": self.current_stage_meta.get("received", ""),
            "action": action,
            "output": str(output_payload)[:3000],
            "stderr": stderr.strip() if stderr else "",
        }
        self.tanks.append(stage_record)

    def finish_flow(
        self,
        predicted_ans: str,
        expected_ans: str,
        passed: bool,
        total_latency_s: float | None = None,
        strict_pass: bool | None = None,
        lenient_pass: bool | None = None,
        failure_class: str = "",
        reconstructed: bool = False,
        tags: list[str] | None = None,
    ) -> dict[str, JsonValue]:
        """Finalize the current flow trace and persist to disk."""
        now = time.perf_counter()
        total_dur = (
            total_latency_s
            if total_latency_s is not None
            else round(now - self.total_start_t, 3)
        )

        verdict: dict[str, JsonValue] = {
            "strict_pass": strict_pass if strict_pass is not None else passed,
            "lenient_pass": lenient_pass if lenient_pass is not None else passed,
            "failure_class": failure_class,
        }

        trace_data: dict[str, JsonValue] = {
            "trace_id": self.active_trace_id,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "reconstructed": reconstructed,
            "config": self.config_metadata,
            "task_info": self.task_info,
            "predicted_ans": predicted_ans,
            "expected_ans": expected_ans,
            "passed": passed,
            "verdict": verdict,
            "total_latency_s": total_dur,
            "tags": tags or [],
            "tanks": self.tanks,
        }

        # Update running stats
        self.stats["completed"] += 1
        if passed:
            self.stats["passed"] += 1
        else:
            self.stats["failed"] += 1
        acc = (self.stats["passed"] / self.stats["completed"]) * 100.0
        self.stats["current_accuracy"] = round(acc, 2)

        # Write to latest_trace.json
        try:
            LATEST_TRACE_FILE.write_text(json.dumps(trace_data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed writing latest_trace.json: %s", exc)

        # Append to flow_traces.jsonl
        try:
            with open(FLOW_TRACES_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_data) + "\n")
        except Exception as exc:
            logger.debug("Failed appending to flow_traces.jsonl: %s", exc)

        # Update live state to idle/waiting
        self._write_live_state(
            active=False,
            current_stage="tank_9_wal_basin",
            stage_name="Autobiographical WAL Basin",
            details=f"Flow complete ({'PASS' if passed else 'FAIL'}). Result committed to WAL.",
        )

        return trace_data

    def _write_live_state(
        self,
        active: bool,
        current_stage: str,
        stage_name: str,
        details: str,
    ) -> None:
        """Write atomic live state file polled by visual debugger."""
        state = {
            "active": active,
            "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "trace_id": self.active_trace_id,
            "current_task": self.task_info,
            "current_stage": current_stage,
            "stage_name": stage_name,
            "details": details,
            "stats": self.stats,
        }
        try:
            temp_file = LIVE_STATE_FILE.with_suffix(".tmp")
            temp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
            temp_file.replace(LIVE_STATE_FILE)
        except Exception as exc:
            logger.debug("Failed writing live_pipeline_state: %s", exc)


tracer = PipelineTracer.get_instance()
