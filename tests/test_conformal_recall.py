"""
Project Lucca — C1 Conformal Routing Abstention & Episode Recall Tests
WO-14 Phase 2.4
"""

import json
import time
from pathlib import Path

import numpy as np

from lucca.core.cascade import EpistemicSearchCascade, EpistemicSubstrate
from lucca.core.schemas import ExecutionTier, RecallEpisode, RouteAction
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore
from lucca.reasoning.recall import recall_past_episodes
from lucca.router.conformal import ConformalGuard
from lucca.router.heuristic import HeuristicRouter


def test_low_confidence_route_abstains() -> None:
    """Router with low-confidence classification falls back to FULL_LOOP."""
    router = HeuristicRouter(confidence_threshold=0.60)

    # 1. Low confidence on an intent that would otherwise be a candidate rule
    decision_low = router.route(
        transcript="maybe launch calculator or something",
        intent_conf=0.45,
        has_registered_rule=True,
    )
    assert decision_low.tier == ExecutionTier.FULL_LOOP
    assert decision_low.action == RouteAction.LLM
    assert decision_low.fallback_applied is True

    # 2. High confidence on same intent routes directly to RULE
    decision_high = router.route(
        transcript="launch calculator",
        intent_conf=0.95,
        has_registered_rule=True,
    )
    assert decision_high.tier == ExecutionTier.ACT_THEN_NARRATE
    assert decision_high.action == RouteAction.RULE
    assert decision_high.fallback_applied is False

    # 3. Test with fitted ConformalGuard
    cal_probs = np.array(
        [
            [0.90, 0.10, 0.00],
            [0.85, 0.15, 0.00],
            [0.10, 0.85, 0.05],
            [0.05, 0.90, 0.05],
            [0.05, 0.15, 0.80],
            [0.10, 0.10, 0.80],
            [0.92, 0.08, 0.00],
            [0.08, 0.92, 0.00],
            [0.05, 0.05, 0.90],
            [0.88, 0.12, 0.00],
        ],
        dtype=np.float64,
    )
    cal_labels = np.array([0, 0, 1, 1, 2, 2, 0, 1, 2, 0], dtype=np.int64)

    guard = ConformalGuard(alpha=0.10)
    guard.fit(cal_probs, cal_labels)

    conf_router = HeuristicRouter(conformal_guard=guard)
    # Ambiguous input (spread probabilities) forces fallback to LLM
    decision_ambiguous = conf_router.route(
        transcript="open calculator maybe",
        intent_conf=0.50,
        has_registered_rule=True,
    )
    assert decision_ambiguous.tier == ExecutionTier.FULL_LOOP
    assert decision_ambiguous.action == RouteAction.LLM
    assert decision_ambiguous.fallback_applied is True
    assert decision_ambiguous.calibrated is True


def test_episode_recall_no_llm_call(tmp_path: Path) -> None:
    """Episode retrieval returns past decisions without any LLM inference."""
    db_path = tmp_path / "lucca_recall_test1.db"
    db = DatabaseManager(db_path=db_path)
    db.migrate()
    # Deterministic lookup against empty or populated store without LLMClient
    episodes = recall_past_episodes(db, query_text="calculator")
    assert isinstance(episodes, list)
    assert len(episodes) == 0


def test_recall_returns_relevant_episodes(tmp_path: Path) -> None:
    """Given a similar input, recall returns matching past episodes."""
    db_path = tmp_path / "lucca_recall_test2.db"
    db = DatabaseManager(db_path=db_path)
    db.migrate()

    now = time.time()
    # 1. Seed decisions table with past episodes
    writer = db.get_writer()
    features_1 = {
        "transcript": "open calculator",
        "intent": "launch_app",
        "entities": {"app": ["calculator"]},
    }
    tool_calls_1 = [{"tool": "launch_app", "args": {"app": "calculator"}}]
    writer.execute(
        """
        INSERT INTO decisions(
            decision_id, trace_id, session_id, ts, features_json, action,
            probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
            router_version, executed_path, tool_calls_json, tool_ok
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "dec-001",
            "tr-001",
            "sess-001",
            now - 50.0,
            json.dumps(features_1),
            "RULE",
            json.dumps({"RULE": 1.0}),
            json.dumps(["RULE"]),
            0,
            150,
            "heuristic-1.0",
            "ACT_THEN_NARRATE",
            json.dumps(tool_calls_1),
            1,
        ),
    )

    features_2 = {
        "transcript": "read project notes.txt",
        "intent": "file_read",
        "entities": {"file": ["notes.txt"]},
    }
    tool_calls_2 = [{"tool": "read_file", "args": {"path": "notes.txt"}}]
    writer.execute(
        """
        INSERT INTO decisions(
            decision_id, trace_id, session_id, ts, features_json, action,
            probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
            router_version, executed_path, tool_calls_json, tool_ok
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "dec-002",
            "tr-002",
            "sess-001",
            now - 30.0,
            json.dumps(features_2),
            "RULE",
            json.dumps({"RULE": 1.0}),
            json.dumps(["RULE"]),
            0,
            120,
            "heuristic-1.0",
            "ACT_THEN_NARRATE",
            json.dumps(tool_calls_2),
            1,
        ),
    )

    # 2. Query recall for calculator
    calc_episodes = recall_past_episodes(db, query_text="what did we do with calculator?", limit=5)
    assert len(calc_episodes) == 1
    assert isinstance(calc_episodes[0], RecallEpisode)
    assert calc_episodes[0].record_id == "dec-001"
    assert calc_episodes[0].payload["transcript"] == "open calculator"
    assert calc_episodes[0].payload["action"] == "RULE"
    assert calc_episodes[0].payload["tool_ok"] is True

    # 3. Query recall for notes.txt
    notes_episodes = recall_past_episodes(
        db, query_text="have we opened notes.txt before?", limit=5
    )
    assert len(notes_episodes) == 1
    assert isinstance(notes_episodes[0], RecallEpisode)
    assert notes_episodes[0].record_id == "dec-002"
    assert notes_episodes[0].payload["intent"] == "file_read"

    # 4. Verify epistemic cascade integration
    mem_store = MemoryStore(db=db, master_key=b"0" * 32)
    cascade = EpistemicSearchCascade(memory_store=mem_store)
    evidence = cascade.query_substrate_self_history("calculator")
    assert len(evidence) >= 1
    assert any("calculator" in ev.content.lower() for ev in evidence)
    assert any(ev.substrate == EpistemicSubstrate.SELF_HISTORY for ev in evidence)
