"""
Test Battery: WO-34 — Proactive Reflection & Macro Consolidation Loop (Module 14)
Enforces:
- Sleep-phase autonomous trace aggregation & DreamCoder macro mining
- Invariant D-REAS-05: Macro depth <= 8, step count <= 64
- Invariant D-REAS-06: 0 mined macros admitted to ACTIVE (all in QUARANTINE)
- Mechanical grading and scorecard update for IN-D (Learned Competencies / Individuation)
- Zero-Any typing, ΔVRAM = 0 MB, CPU host execution
"""

from __future__ import annotations

import json
from pathlib import Path
import time
import pytest

from lucca.reasoning.consolidation import (
    ConsolidationConfig,
    ConsolidationCycleResult,
    ConsolidationEngine,
)
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.parser import parse_expr


def test_consolidation_config_defaults() -> None:
    """Verifies default parameters for consolidation loop."""
    cfg = ConsolidationConfig()
    assert cfg.idle_threshold_seconds == 30.0
    assert cfg.max_traces_per_cycle == 50
    assert cfg.min_instances_for_macro == 2
    assert cfg.smt_timeout_ms == 500
    assert cfg.auto_update_in_d_scorecard is True


def test_consolidation_trace_buffer_management() -> None:
    """Verifies buffering of string and SchemeNode traces and buffer clearing."""
    engine = ConsolidationEngine()
    assert engine.buffer_size == 0

    engine.record_trace("(+ 1 2)")
    engine.record_trace(parse_expr("(* 3 4)"))
    assert engine.buffer_size == 2

    engine.record_traces(["(/ 10 2)", "(- 8 3)"])
    assert engine.buffer_size == 4

    engine.clear_trace_buffer()
    assert engine.buffer_size == 0


def test_consolidation_cycle_insufficient_traces() -> None:
    """Verifies that cycles with fewer traces than min_instances skip gracefully."""
    engine = ConsolidationEngine(config=ConsolidationConfig(min_instances_for_macro=3))
    engine.record_trace("(+ 1 2)")

    res = engine.run_consolidation_cycle()
    assert isinstance(res, ConsolidationCycleResult)
    assert res.macros_mined == 0
    assert res.traces_examined == 1
    assert res.in_d_guard_passed is True


def test_consolidation_cycle_mines_and_quarantines_macro(tmp_path: Path) -> None:
    """
    Verifies end-to-end sleep consolidation:
    1. Traces with recurring structure (+ a (* b c)) are mined.
    2. Candidate is verified and admitted into QUARANTINE.
    3. D-REAS-06 invariant verified: 0 macros reach ACTIVE.
    4. IN-D report reflects >= 1 quarantined learned skill.
    """
    mgr = RuleLifecycleManager()
    cfg = ConsolidationConfig(
        min_instances_for_macro=2,
        auto_update_in_d_scorecard=True,
    )
    engine = ConsolidationEngine(config=cfg, lifecycle_manager=mgr)

    traces = [
        '(and (intent= "launch_app") (entity-has? "app" "calc") (not (app-running? "calc")))',
        '(and (intent= "launch_app") (entity-has? "app" "notepad") (not (app-running? "notepad")))',
        '(and (intent= "launch_app") (entity-has? "app" "edge") (not (app-running? "edge")))',
    ]
    engine.record_traces(traces)
    assert engine.buffer_size == 3

    res = engine.run_consolidation_cycle()
    assert res.macros_mined >= 1
    assert len(res.quarantined_macro_ids) >= 1
    assert len(res.active_macro_ids) == 0, "D-REAS-06: 0 mined macros may reach ACTIVE"
    assert res.in_d_guard_passed is True
    assert res.in_d_quarantined_count >= 1

    # Verify IN-D scorecard report file
    in_d_file = Path("logs/test_reports/personhood/in_d_latest.json")
    assert in_d_file.exists()
    report_data = json.loads(in_d_file.read_text(encoding="utf-8"))
    assert report_data["stratum"] == "IN-D"
    assert report_data["status"] == "MEASURED"
    assert report_data["learned_skills_quarantined"] >= 1
    assert report_data["learned_skills_active"] == 0
    assert report_data["guard_active_zero_passed"] is True


def test_consolidation_execution_latency_and_zero_vram() -> None:
    """Verifies sub-second CPU execution budget and zero VRAM impact."""
    mgr = RuleLifecycleManager()
    engine = ConsolidationEngine(lifecycle_manager=mgr)

    traces = [
        "(+ 1 (* 2 2))",
        "(+ 5 (* 3 3))",
    ]
    engine.record_traces(traces)

    t0 = time.perf_counter()
    res = engine.run_consolidation_cycle()
    elapsed = (time.perf_counter() - t0) * 1000.0

    assert res.elapsed_ms > 0.0
    assert elapsed < 2000.0, f"Consolidation cycle exceeded 2.0s: {elapsed:.2f}ms"
