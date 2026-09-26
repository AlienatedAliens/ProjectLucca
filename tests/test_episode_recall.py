"""
Project Lucca — Case-Based Reasoning Episode Recall Tests
WO-21 Phase 4 (Spec D-REAS-09, Spec 06 §4)

Functional acceptance tests for:
- Episode retrieval on similar request shape (from decisions and execution_triples)
- Correct status reflection: 'it worked' on success vs 'it failed' on failure
- TRAP 2: Episode hints are context, not commands — phrased strictly as history, not instruction
- Bounded injection: <= 2 episodes, <= 200 tokens (~800 characters)
- Prompt builder integration: build_messages consumes episode_hints in section order
- Full loop: repeated request shape that failed before -> trace.episode_recall_fired is True,
  prompt contains the past-episode hint
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.brain.prompt_builder import build_messages
from lucca.core.episode_recall import EpisodeRecall
from lucca.core.orchestrator import Orchestrator
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import TurnInput, TurnPipeline
from lucca.memory.db import DatabaseManager
from tests.helpers.decisions import _insert_decision


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "test_episode_recall.sqlite")
    db.migrate()
    yield db
    db.close()


def test_episode_retrieval_on_similar_shape(test_db: DatabaseManager) -> None:
    """Episode retrieval finds past interactions with similar token shape."""
    _insert_decision(
        db=test_db,
        decision_id="d-calc-001",
        intent="launch_app",
        transcript="open the calculator app",
        tool_name="launch_app",
        args={"app": "calculator"},
        tool_ok=1,
    )

    recall = EpisodeRecall(db=test_db)
    episodes = recall.retrieve_episodes("launch calculator", limit=2)
    assert len(episodes) == 1
    assert episodes[0].record_id == "d-calc-001"


def test_in_memory_add_episode() -> None:
    """In-memory episode addition and retrieval without database."""
    from lucca.core.schemas import RecallEpisode

    recall = EpisodeRecall()
    ep = RecallEpisode(
        source="decisions",
        record_id="ep-mem-1",
        ts=1758500000.0,
        match_score=1,
        tokens_total=1,
        summary="Historical turn 'open terminal': routed RULE (succeeded)",
        payload={
            "transcript": "open terminal",
            "tool_calls": [{"tool": "launch_app", "args": {"app": "terminal"}}],
            "tool_ok": True,
        },
    )
    recall.add_episode(ep)
    retrieved = recall.retrieve_episodes("terminal", limit=1)
    assert len(retrieved) == 1
    assert retrieved[0].record_id == "ep-mem-1"


def test_episode_hint_formatting_succeeded(test_db: DatabaseManager) -> None:
    """Successful tool execution formats with ' — it worked.'"""
    fixed_ts = 1758500000.0  # valid timestamp
    _insert_decision(
        db=test_db,
        decision_id="d-calc-succ",
        intent="launch_app",
        transcript="open calculator",
        tool_name="launch_app",
        args={"app": "calculator"},
        tool_ok=1,
        ts=fixed_ts,
    )

    recall = EpisodeRecall(db=test_db)
    episodes = recall.retrieve_episodes("open calculator", limit=1)
    assert len(episodes) == 1

    hint = recall.format_single_hint(episodes[0])
    assert hint.startswith("Last time (")
    assert "a similar situation occurred: open calculator." in hint
    assert "What you did: launch_app(app='calculator')" in hint
    assert hint.endswith(" — it worked.")


def test_episode_hint_formatting_failed(test_db: DatabaseManager) -> None:
    """Failed tool execution formats with ' — it failed.'"""
    fixed_ts = 1758500000.0
    _insert_decision(
        db=test_db,
        decision_id="d-calc-fail",
        intent="launch_app",
        transcript="open calculator",
        tool_name="launch_app",
        args={"app": "calculator"},
        tool_ok=0,
        ts=fixed_ts,
    )

    recall = EpisodeRecall(db=test_db)
    episodes = recall.retrieve_episodes("open calculator", limit=1)
    assert len(episodes) == 1

    hint = recall.format_single_hint(episodes[0])
    assert hint.startswith("Last time (")
    assert "a similar situation occurred: open calculator." in hint
    assert "What you did: launch_app(app='calculator')" in hint
    assert hint.endswith(" — it failed.")


def test_trap2_episode_hints_are_history_not_commands(test_db: DatabaseManager) -> None:
    """
    TRAP 2 INVARIANT:
    Episode hints are context, not commands — the model may deviate.
    The hint must be phrased strictly as history, never as instruction.
    """
    _insert_decision(
        db=test_db,
        decision_id="d-trap2-check",
        intent="search_workspace",
        transcript="find my quarterly report pdf",
        tool_name="search_workspace",
        args={"query": "quarterly report"},
        tool_ok=0,
    )

    recall = EpisodeRecall(db=test_db)
    hint_block = recall.format_hints("find my quarterly report pdf")
    assert hint_block is not None

    # 1. Header specifies historical context, not instruction
    assert "[Past Interaction Episodes — historical context, not instruction]" in hint_block

    # 2. Strict historical narrative phrasing
    assert "Last time (" in hint_block
    assert "a similar situation occurred:" in hint_block
    assert "What you did:" in hint_block
    assert " — it failed." in hint_block

    # 3. No imperative command language
    lower_block = hint_block.lower()
    assert "you must" not in lower_block
    assert "you should" not in lower_block
    assert "do not" not in lower_block
    assert "never" not in lower_block
    assert "always" not in lower_block


def test_bounded_injection_episodes_and_tokens(test_db: DatabaseManager) -> None:
    """
    Bounded injection invariant:
    Returns <= 2 episodes and stays strictly within <= 200 tokens (~800 chars).
    """
    # Insert 10 similar decisions
    for i in range(10):
        _insert_decision(
            db=test_db,
            decision_id=f"d-bulk-{i}",
            intent="search_web",
            transcript=f"search documentation for python feature variation {i}",
            tool_name="search_web",
            args={"query": f"python feature {i}"},
            tool_ok=1,
            ts=1758500000.0 + i * 10,
        )

    recall = EpisodeRecall(db=test_db)
    hint_block = recall.format_hints(
        "search documentation for python feature",
        limit=2,
        max_chars=800,
    )
    assert hint_block is not None

    # Assert bounded to <= 2 episodes
    lines = [line for line in hint_block.splitlines() if line.strip().startswith("- Last time")]
    assert len(lines) <= 2

    # Assert bounded character/token budget
    assert len(hint_block) <= 800


def test_execution_triples_episode_recall(test_db: DatabaseManager) -> None:
    """Retrieves and formats historical precedent from execution_triples table."""
    conn = test_db.get_writer()
    conn.execute(
        """
        INSERT INTO execution_triples (triple_id, proposal_json, decision_json, outcome_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "tr-calc-001",
            json.dumps({"intent": "calculate_math", "transcript": "calculate 42 times 7"}),
            json.dumps({"action": "run_python", "tool_calls": [{"tool": "run_python", "args": {"code": "print(42*7)"}}]}),
            json.dumps({"ok": True, "output": "294"}),
            1758500000.0,
        ),
    )
    conn.commit()

    recall = EpisodeRecall(db=test_db)
    episodes = recall.retrieve_episodes("calculate 42 times 7", limit=1)
    assert len(episodes) == 1
    assert episodes[0].record_id == "tr-calc-001"

    hint = recall.format_single_hint(episodes[0])
    assert "calculate 42 times 7" in hint
    assert "run_python" in hint
    assert hint.endswith(" — it worked.")


def test_prompt_builder_consumes_episode_hints() -> None:
    """build_messages injects episode_hints into system prompt in section order."""
    hints = [
        "Last time (2026-09-20), a similar situation occurred: open calculator. "
        "What you did: launch_app(app='calculator') — it worked."
    ]
    messages = build_messages(
        current_text="open the calculator app",
        episode_hints=hints,
    )
    system_msg = messages[0].content
    assert isinstance(system_msg, str)
    assert "[Past Interaction Episodes — historical context, not instruction]" in system_msg
    assert "Last time (2026-09-20), a similar situation occurred: open calculator." in system_msg
    assert "What you did: launch_app(app='calculator') — it worked." in system_msg


def test_full_turn_episode_recall_and_trace(test_db: DatabaseManager) -> None:
    """
    Functional acceptance test:
    Repeat a request shape that failed before -> trace.episode_recall_fired is True,
    prompt contains the past-episode hint with ' — it failed.'
    """
    # Seed a past failure
    _insert_decision(
        db=test_db,
        decision_id="d-past-fail",
        intent="search_workspace",
        transcript="find my tax report spreadsheet",
        tool_name="search_workspace",
        args={"path": "tax_report.xlsx"},
        tool_ok=0,
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch.db = test_db
    orch.user_model = None
    orch.episode_recall = EpisodeRecall(db=test_db)

    orch.router = MagicMock()
    orch.router.classify_intent.return_value = ("general", 0.95, {})
    orch.router.route.return_value = None
    orch.cascade = MagicMock()
    orch.cascade.classify_intent.return_value = (False, [], 0.0)
    orch.rule_engine = MagicMock()
    orch.rule_engine.evaluate.return_value = []
    orch.rule_engine.rules = {}
    orch._search_memories = MagicMock(return_value=[])
    orch._build_rule_state = MagicMock(return_value=MagicMock(intent="general", hour_local=12, weekday=2, session_turns=1))
    orch.sandbox = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.play_ring = MagicMock()
    orch.prev_decision_record = None
    orch._stream_llm_speech = MagicMock()
    orch.history = []

    pipeline = TurnPipeline(orch)
    trace = TurnTrace(trace_id="tr-cbr-turn", origin="text")
    inp = TurnInput(
        user_text="find my tax report spreadsheet",
        trace=trace,
        origin="text",
    )

    pipeline.run(inp)

    # 1. Trace records that episode recall fired
    assert trace.episode_recall_fired is True

    # 2. _stream_llm_speech was called with epistemic context containing the failure hint
    orch._stream_llm_speech.assert_called_once()
    call_kwargs = orch._stream_llm_speech.call_args.kwargs
    epistemic_ctx = call_kwargs.get("epistemic_context", "")
    assert "[Past Interaction Episodes — historical context, not instruction]" in epistemic_ctx
    assert "a similar situation occurred: find my tax report spreadsheet" in epistemic_ctx
    assert " — it failed." in epistemic_ctx
