"""
Project Lucca — Unit Tests for Milestone 36.3: Two-Cadence Inner Life & Homeostatic Drives.
Acceptance Gate: G-WO36-INNER-LIFE.
Tests CoherenceDrive, CompetenceDrive, IdlePulse, DreamRetrospective, and Waking Continuity.
"""

from __future__ import annotations

import time
from pathlib import Path
import pytest

from lucca.core.affect import AffectSignal, AffectTracker
from lucca.core.orchestrator import Orchestrator
from lucca.core.turn_pipeline import TurnPipeline
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import (
    CoherenceDrive,
    CompetenceDrive,
    DreamRetrospective,
    IdlePulse,
    log_learning_event,
)


def test_coherence_drive_evaluates_belnap_conflicts(tmp_path: Path) -> None:
    """CoherenceDrive prioritizes Belnap Top conflicts over regular revisions."""
    db_path = tmp_path / "test_coherence.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()

    drive = CoherenceDrive(db)

    # Initially empty review_queue
    assert drive.evaluate_deficit() == 0.0
    assert drive.scan_pending_conflicts() == []

    # Insert a regular pending review item and a Belnap Top conflict item
    with db.get_writer() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            INSERT INTO review_queue (
                review_id, belief_id, proposed_content, proposed_confidence,
                reason_entry_id, trigger_reason, created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            ("rev-001", 1, "Regular revision", 0.9, "reason-01", "high_importance_0.8", time.time() - 10),
        )
        conn.execute(
            """
            INSERT INTO review_queue (
                review_id, belief_id, proposed_content, proposed_confidence,
                reason_entry_id, trigger_reason, created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            ("rev-002", 2, "Belnap Top revision", 0.9, "reason-02", "belnap_conflict_top; kind_user_model", time.time() - 5),
        )

    deficit = drive.evaluate_deficit()
    # 1 Belnap conflict (0.4) + 1 regular (0.1) = 0.5
    assert 0.45 <= deficit <= 0.55

    conflicts = drive.scan_pending_conflicts(limit=5)
    assert len(conflicts) == 2
    # The Belnap conflict item must be ordered first
    assert conflicts[0]["review_id"] == "rev-002"
    assert "conflict" in str(conflicts[0]["trigger_reason"])


def test_competence_drive_and_dream_retrospective(tmp_path: Path) -> None:
    """CompetenceDrive scans CEGIS repairs; DreamRetrospective mines skills into QUARANTINE (D-REAS-06)."""
    db_path = tmp_path / "test_competence.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()

    # Insert a successful CEGIS repair decision
    with db.get_writer() as conn:
        conn.execute(
            """
            INSERT INTO decisions (
                decision_id, trace_id, session_id, ts, features_json, action,
                probabilities_json, prediction_set_json, elapsed_us, router_version,
                executed_path, tool_calls_json, tool_ok
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dec-cegis-001",
                "tr-01",
                "sess-01",
                time.time() - 50,
                '{"cegis_turns": 2, "transcript": "solve cryptarithm"}',
                "cegis_repair_macro",
                "{}",
                "[]",
                1200,
                "v1",
                "REFLEX",
                "[]",
                1,
            ),
        )

    comp_drive = CompetenceDrive(db)
    repairs = comp_drive.scan_candidate_repairs(limit=5)
    assert len(repairs) >= 1
    assert repairs[0]["decision_id"] == "dec-cegis-001"

    # Run DreamRetrospective
    retro = DreamRetrospective(db)
    result = retro.retrospective()

    assert result.replays_analyzed >= 1
    assert result.skills_mined >= 1
    assert len(result.quarantined_rules) >= 1
    assert "rule-quarantine-dec-cegi" in result.quarantined_rules[0]

    # Verify D-REAS-06 invariant: RULE_QUARANTINED and SKILL_MINED are recorded in learning_events
    with db.read_cursor() as cur:
        cur.execute("SELECT event_type, details_json FROM learning_events ORDER BY created_at ASC")
        rows = cur.fetchall()
        types = [r[0] for r in rows]
        assert "RULE_QUARANTINED" in types
        assert "SKILL_MINED" in types
        for _, details_raw in rows:
            assert "QUARANTINE" in details_raw


def test_idle_pulse_execution_and_learning_ledger(tmp_path: Path) -> None:
    """IdlePulse executes sub-50ms heartbeat, distills pending conflicts, and logs IDLE_PULSE_DISTILL to ledger."""
    db_path = tmp_path / "test_idle_pulse.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()

    # Insert a pending conflict in review_queue to exercise real distillation in IdlePulse
    with db.get_writer() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            INSERT INTO review_queue (
                review_id, belief_id, proposed_content, proposed_confidence,
                reason_entry_id, trigger_reason, created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            ("rev-distill-01", 1, "Actually, I prefer dark mode in all editors", 0.95, "reason-01", "belnap_conflict_top", time.time() - 5),
        )

    pulse_engine = IdlePulse(db)
    res = pulse_engine.pulse()

    assert res.latency_ms >= 0.0
    assert res.distilled_events_count == 1
    assert res.coherence_deficit > 0.0
    assert res.competence_deficit >= 0.0
    assert any("distilled_rev-distill-01" in a for a in res.actions_taken)

    # Verify learning_events ledger entry includes distilled proposition
    with db.read_cursor() as cur:
        cur.execute("SELECT event_type, topic, details_json FROM learning_events")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "IDLE_PULSE_DISTILL"
        assert row[1] == "homeostatic_heartbeat"
        assert "coherence_deficit" in row[2]
        assert "The user prefers dark mode in all editors." in row[2]


def test_waking_continuity_note_and_long_gap(tmp_path: Path) -> None:
    """Session gap >= 30 min triggers AffectSignal.LONG_GAP and injects waking continuity note."""
    db_path = tmp_path / "test_continuity.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()

    orch = Orchestrator(db=db)
    pipeline = orch.turn_pipeline

    # Simulate a past turn timestamp 45 minutes ago and run orchestrator idle pulse
    orch.last_turn_timestamp = time.time() - (45 * 60)
    pulse_res = orch.maybe_run_idle_pulse(now=time.time() - 60)
    assert pulse_res is not None

    epistemic_ctx = pipeline.build_epistemic_context(user_text="Good morning, Lucca.")

    assert epistemic_ctx is not None
    assert "[Waking Continuity Note: 45 minutes elapsed since last turn." in epistemic_ctx
    assert "Resuming collaborative workspace" in epistemic_ctx
    assert "IDLE_PULSE_DISTILL" in epistemic_ctx

    # Last turn timestamp must have been refreshed to now
    assert time.time() - orch.last_turn_timestamp < 5.0
