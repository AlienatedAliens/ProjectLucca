"""
Unit tests verifying WO-43 Phase 2 Sub-Step 2.6 Behavioral Organ Activation:
1. WorkingMemory task_journal lifecycle + PipelineTracer live_pipeline_state.json +
   DeductionAndPlanningRunner Walton critical-question corroboration in TurnPipeline.run().
2. ConsolidationEngine + ASTHoleMCTSEngine hole repair + Orchestrator.maybe_run_nightly_rollup()
   invocation while enforcing D-REAS-06 (0 auto-promotions to ACTIVE).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.deduction_runner import DeductionAndPlanningRunner
from lucca.core.orchestrator import Orchestrator
from lucca.core.pipeline_tracer import LIVE_STATE_FILE, PipelineTracer
from lucca.core.schemas import ExecutionTier, RouteAction, RouteDecision, RuleState
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import TurnInput, TurnPipeline
from lucca.memory.db import DatabaseManager
from lucca.memory.working import WorkingMemory
from lucca.reasoning.consolidation import ConsolidationConfig, ConsolidationEngine
from lucca.reasoning.lifecycle import RuleLifecycleManager


def test_turn_pipeline_activates_working_memory_pipeline_tracer_and_deduction_runner(
    tmp_path: Path,
) -> None:
    """
    Proves that a live turn through TurnPipeline.run():
    1. Opens and closes a WorkingMemory task entry in SQLite `task_journal`.
    2. Updates `logs/telemetry/live_pipeline_state.json` via PipelineTracer.
    3. Invokes DeductionAndPlanningRunner.evaluate_step_corroboration on deep-thinking turns
       and attaches Walton critical-question metadata to epistemic_context.
    """
    db_path = tmp_path / "test_phase2_organs.db"
    db = DatabaseManager(db_path)
    db.migrate()

    orch = Orchestrator.__new__(Orchestrator)
    orch.db = db
    orch.memory_store = None
    orch.working_memory = WorkingMemory(db=db)
    orch.sandbox = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.play_ring = MagicMock()
    orch.history = []
    orch.prev_decision_record = None
    orch.prev_turn_ts = None
    orch.session_id = "sess-phase2"
    orch.cascade = MagicMock()
    orch.cascade.classify_intent.return_value = (False, [], "none")
    orch.user_model = None
    orch.episode_recall = None
    orch.active_goals = None
    orch.last_turn_timestamp = None
    orch._build_rule_state = MagicMock(
        return_value=RuleState(
            schema_version=1,
            transcript="Think step by step: according to Dr. Smith, the bridge is safe.",
            transcript_lower="think step by step: according to dr. smith, the bridge is safe.",
            intent="general_query",
            intent_conf=0.9,
            entities={},
            hour_local=12,
            weekday=2,
            apps_running=frozenset(),
            session_turns=1,
        )
    )
    orch.rule_engine = MagicMock()
    orch.rule_engine.evaluate.return_value = []
    orch.router = MagicMock()
    orch.router.route.return_value = RouteDecision(
        action=RouteAction.LLM,
        tier=ExecutionTier.FULL_LOOP,
        intent="general_query",
        intent_conf=0.9,
        prediction_set=[RouteAction.LLM],
        elapsed_us=10,
        reason="test_deliberation",
    )
    orch.router.last_decision_record = None
    orch._search_memories = MagicMock(return_value=[])
    orch.current_turn_receipts = []
    orch.deduction_runner = DeductionAndPlanningRunner(orch)

    captured_epistemic_ctx: list[str | None] = []

    def _fake_stream_llm_speech(**kwargs: object) -> None:
        captured_epistemic_ctx.append(
            kwargs.get("epistemic_context")  # type: ignore[arg-type]
        )
        orch.current_turn_assistant_reply = "Let us evaluate the expert authority claim carefully."

    orch._stream_llm_speech = MagicMock(side_effect=_fake_stream_llm_speech)

    pipeline = TurnPipeline(orch)
    orch.turn_pipeline = pipeline

    trace = TurnTrace(
        trace_id="trace-wo43-phase2-001",
        session_id="sess-phase2",
        origin="text",
    )
    inp = TurnInput(
        user_text="Think step by step: according to Dr. Smith, the bridge is safe.",
        trace=trace,
        origin="text",
        mode="transcript",
    )
    pipeline.run(inp)

    # 1. Verify WorkingMemory recorded and closed task in task_journal
    with db.read_cursor() as cur:
        cur.execute(
            "SELECT task_id, opened_at, closed_at, outcome FROM task_journal WHERE task_id = ?",
            ("trace-wo43-phase2-001",),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "trace-wo43-phase2-001"
    assert row[1] is not None and float(row[1]) > 0
    assert row[2] is not None and float(row[2]) >= float(row[1])
    assert row[3] == "completed"

    # 2. Verify PipelineTracer updated live_pipeline_state.json for this trace
    tracer = PipelineTracer.get_instance()
    assert tracer.active_trace_id == "trace-wo43-phase2-001"
    assert LIVE_STATE_FILE.exists()
    live_payload = json.loads(LIVE_STATE_FILE.read_text(encoding="utf-8"))
    assert live_payload["trace_id"] == "trace-wo43-phase2-001"

    # 3. Verify DeductionAndPlanningRunner attached Walton critical-question corroboration metadata
    assert len(captured_epistemic_ctx) == 1
    assert captured_epistemic_ctx[0] is not None
    assert "[Walton Critical-Question Corroboration:" in captured_epistemic_ctx[0]
    db.close()


def test_nightly_rollup_triggers_consolidation_and_mcts_hole_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Proves that:
    1. ConsolidationEngine repairs a partial MicroScheme sketch containing a hole (?hole)
       via ASTHoleMCTSEngine (mcts.py + abduction.py + topology.py).
    2. Orchestrator.maybe_run_nightly_rollup() invokes ConsolidationEngine.run_consolidation_cycle()
       and strictly enforces 0 auto-promotions to ACTIVE (D-REAS-06).
    """
    import lucca.evaluation.in_d_grader as in_d_mod

    monkeypatch.setattr(in_d_mod, "REPORT_DIR", tmp_path / "personhood")

    lifecycle = RuleLifecycleManager()
    engine = ConsolidationEngine(
        config=ConsolidationConfig(min_instances_for_macro=2, auto_update_in_d_scorecard=True),
        lifecycle_manager=lifecycle,
    )

    # Direct hole repair check via ASTHoleMCTSEngine
    repair_res = engine.repair_sketch_with_mcts("(+ ?hole 2)", goal=5, candidate_literals=[3])
    assert repair_res.success is True
    assert repair_res.canonical_code == "(+ 3 2)"

    # Buffer traces including a partial hole trace and recurring rule predicates
    engine.record_traces(
        [
            "(= (+ ?hole 2) 3)",
            '(and (intent= "launch_app") (entity-has? "app" "calc") (not (app-running? "calc")))',
            '(and (intent= "launch_app") (entity-has? "app" "notepad") (not (app-running? "notepad")))',
        ]
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch.reflection_engine = MagicMock()
    orch.reflection_engine.get_last_rollup_at.return_value = 0.0
    orch.reflection_engine.nightly_rollup.return_value = 4
    orch.config = MagicMock()
    orch.config.memory.rollup_hour_local = 3
    orch.consolidation_engine = engine

    # Choose a timestamp at 03:30 local time so is_rollup_due returns True
    import datetime

    dt = datetime.datetime(2026, 11, 8, 3, 30, 0).astimezone()
    compressed = orch.maybe_run_nightly_rollup(now=dt.timestamp())
    assert compressed == 4
    assert engine._cycle_counter == 1
    in_d = engine.get_in_d_report()
    assert in_d.learned_skills_quarantined >= 1
    assert in_d.learned_skills_active == 0
    assert in_d.guard_active_zero_passed is True
