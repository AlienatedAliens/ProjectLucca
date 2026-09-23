"""
Project Lucca — Production Router Calibration & Wiring Tests
WO-15 Phase 2 (§4.4)
"""

from __future__ import annotations

from pathlib import Path

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import RouteAction
from lucca.memory.db import DatabaseManager
from lucca.router.calibration import fit_guard_from_db, load_labelled_decisions
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_tts import FakeTTS
from tests.helpers.decisions import _insert_decision


def _make_db(tmp_path: Path, name: str = "test.sqlite") -> DatabaseManager:
    db = DatabaseManager(tmp_path / name)
    db.migrate()
    return db


def test_fit_guard_returns_none_on_empty_db(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "empty.sqlite")
    guard = fit_guard_from_db(db)
    assert guard is None


def test_fit_guard_returns_none_below_min_samples(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "sub_min.sqlite")
    for i in range(29):
        _insert_decision(
            db,
            decision_id=f"dec-{i}",
            intent="launch_app",
            transcript="open calculator",
            tool_name="launch_app",
            args={"app": "calculator"},
            tool_ok=1,
            action="RULE",
            probabilities={"RULE": 0.90, "LLM": 0.10, "CLARIFY": 0.0},
        )
    guard = fit_guard_from_db(db, min_samples=30)
    assert guard is None


def test_fit_guard_fits_at_min_samples(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "min.sqlite")
    for i in range(30):
        _insert_decision(
            db,
            decision_id=f"dec-{i}",
            intent="launch_app",
            transcript="open calculator",
            tool_name="launch_app",
            args={"app": "calculator"},
            tool_ok=1,
            action="RULE",
            probabilities={"RULE": 0.90, "LLM": 0.10, "CLARIFY": 0.0},
        )
    guard = fit_guard_from_db(db, min_samples=30)
    assert guard is not None
    assert isinstance(guard.q_hat, float)
    assert 0.0 <= guard.q_hat <= 1.0


def test_label_rule_rule_failure_maps_to_llm(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "rule_fail.sqlite")
    _insert_decision(
        db,
        decision_id="dec-fail-1",
        intent="launch_app",
        transcript="open calculator",
        tool_name="launch_app",
        args={"app": "calculator"},
        tool_ok=0,
        action="RULE",
        probabilities={"RULE": 0.85, "LLM": 0.15, "CLARIFY": 0.0},
    )
    probs, labels = load_labelled_decisions(db)
    assert len(labels) == 1
    assert labels[0] == 1  # RULE failed -> mapped to LLM (1)


def test_fallback_rows_excluded(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "fallback.sqlite")
    for i in range(10):
        _insert_decision(
            db,
            decision_id=f"dec-fb-{i}",
            intent="unknown",
            transcript="maybe whatever",
            action="LLM",
            tool_ok=1,
            fallback_applied=1,
            probabilities={"RULE": 0.0, "LLM": 0.50, "CLARIFY": 0.50},
        )
    probs, labels = load_labelled_decisions(db)
    assert len(labels) == 0


def test_rows_without_probabilities_skipped(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "no_probs.sqlite")
    _insert_decision(
        db,
        decision_id="dec-null-probs",
        intent="chit_chat",
        transcript="hello",
        action="LLM",
        tool_ok=1,
        probabilities=None,
    )
    probs, labels = load_labelled_decisions(db)
    assert len(labels) == 0


def test_orchestrator_router_uncalibrated_on_empty_db(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "orch_empty.sqlite")
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, db=db, execute_tools=False)
    try:
        assert orch.router.conformal_guard is None
        decision = orch.router.route("hello there")
        assert decision.calibrated is False
        assert decision.probabilities is not None
        assert decision.action == RouteAction.LLM
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
        db.close()


def test_orchestrator_router_calibrated_with_seeded_history(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "orch_seeded.sqlite")

    # Seed 40 labelled decisions across classes before constructing Orchestrator
    for i in range(15):
        _insert_decision(
            db,
            decision_id=f"dec-rule-{i}",
            intent="launch_app",
            transcript="open calculator",
            tool_name="launch_app",
            args={"app": "calculator"},
            tool_ok=1,
            action="RULE",
            probabilities={"RULE": 0.95, "LLM": 0.05, "CLARIFY": 0.0},
        )
    for i in range(15):
        _insert_decision(
            db,
            decision_id=f"dec-llm-{i}",
            intent="chit_chat",
            transcript="hello how are you",
            action="LLM",
            tool_ok=1,
            user_interrupted=0,
            probabilities={"RULE": 0.0, "LLM": 0.95, "CLARIFY": 0.05},
        )
    for i in range(10):
        _insert_decision(
            db,
            decision_id=f"dec-clarify-{i}",
            intent="clarify",
            transcript="uh",
            action="CLARIFY",
            tool_ok=1,
            probabilities={"RULE": 0.0, "LLM": 0.20, "CLARIFY": 0.80},
        )

    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, db=db, execute_tools=False)
    try:
        assert orch.router.conformal_guard is not None
        assert orch.router.conformal_guard.q_hat is not None
        decision = orch.router.route("open calculator", has_registered_rule=True)
        assert decision.calibrated is True
        assert decision.action == RouteAction.RULE
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
        db.close()
