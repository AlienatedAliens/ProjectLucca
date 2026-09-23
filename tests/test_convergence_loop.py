"""
Project Lucca — Convergence Tool Loop Tests (WO-9 A5 / F5)

The tool loop terminates when the model stops calling tools (convergence),
not at a fixed quota. Tools stay available every round; the hard cap (8) is a
runaway guard only — on the cap round tools are withdrawn and the model must
summarise honestly. A repeat guard blocks identical (tool, args) re-calls.
"""

from collections import deque
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    ExecutionTier,
    LLMUsage,
    ToolCall,
    ToolCallEnd,
    ToolResult,
)
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def orch(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test_convergence.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    orch = Orchestrator.__new__(Orchestrator)
    orch.config = get_config()
    orch.execute_tools = True
    orch.state = "idle"
    orch.running = True
    orch.db = db
    orch.memory_store = store
    orch.current_turn_receipts = []
    orch.current_turn_tool_calls = []
    orch.current_turn_tier = ExecutionTier.FULL_LOOP
    orch.current_turn_tool_spoken = []
    orch.current_turn_tool_ok = True
    orch.pending_spoken_updates = deque()
    orch.history = []
    orch.executed_tools = []
    orch.current_turn_transcript = None
    orch.current_turn_assistant_reply = None
    orch.active_trace = None
    orch.rule_engine = MagicMock(rules={})
    orch.output_supervisor = MagicMock()
    orch.output_supervisor.turn_has_stalled = False
    orch.output_supervisor.feed_chunk.return_value = ([], False)
    orch.output_supervisor.flush.return_value = ([], False)
    orch.sandbox = MagicMock()
    orch.sandbox.check_confirmation_needed.return_value = False
    orch.sandbox.execute_tool.return_value = ToolResult(
        call_id="x", ok=True, exit_code=0, content="ok", elapsed_ms=0.0
    )
    orch.affect_tracker = MagicMock()
    orch.play_ring = MagicMock()
    orch._tts_queue = MagicMock()
    orch.tts = MagicMock()
    orch.asr = MagicMock()
    orch.bdi_validator = MagicMock()
    orch.bdi_validator.validate_tool_call.return_value = MagicMock(is_valid=True)
    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._set_state = MagicMock()
    orch._finalize_turn = MagicMock()
    return orch


def _trace(trace_id: str) -> TurnTrace:
    return TurnTrace(trace_id=trace_id, session_id="sess-conv", origin="text", mode="transcript")


def _search_round(query: str, call_id: str) -> list:

    call = ToolCall(tool="memory_search", args={"query": query}, call_id=call_id)
    return [
        ToolCallEnd(call=call),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
    ]


def _text_round(text: str) -> list:
    from lucca.core.schemas import TokenDelta

    return [
        TokenDelta(delta=text),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=3)),
    ]


def test_convergence_four_tool_rounds(orch) -> None:
    """Tools stay available past the old fixed quota; loop converges when the
    model stops calling tools (round 5 plain text)."""
    orch.llm = FakeLLM(
        rounds=[
            _search_round("q1", "c1"),
            _search_round("q2", "c2"),
            _search_round("q3", "c3"),
            _search_round("q4", "c4"),
            _text_round("Here is what I found."),
        ]
    )
    trace = _trace("tr-conv-1")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="research Sean",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
    )

    assert len(orch.executed_tools) == 4, "tools must not be stripped at round 3"
    assert orch.llm.call_count == 5
    assert trace.rounds_used == 5
    assert trace.cap_hit is False


def test_cap_hit_forces_honest_synthesis(orch) -> None:
    """Seven tool rounds + cap round: tools withdrawn, cap flagged in trace."""
    rounds = [_search_round(f"q{i}", f"c{i}") for i in range(7)]
    rounds.append(_text_round("Summarising what I found and what I could not verify."))
    orch.llm = FakeLLM(rounds=rounds)
    trace = _trace("tr-conv-cap")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="deep research",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
    )

    assert orch.llm.call_count == 8
    assert trace.rounds_used == 8
    assert trace.cap_hit is True
    assert len(orch.executed_tools) == 7


def test_repeated_call_guard_injects_directive(orch) -> None:
    """An identical (tool, args) call twice injects the Repeat Guard directive."""
    orch.llm = FakeLLM(
        rounds=[
            _search_round("same query", "c1"),
            _search_round("same query", "c2"),
            _text_round("Using the result I already have."),
        ]
    )
    trace = _trace("tr-conv-repeat")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="search again",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
    )

    assert len(orch.executed_tools) == 2
    # The round-3 stream call must carry the Repeat Guard directive
    round3_kwargs = orch.llm.all_kwargs[2]
    tool_msgs = round3_kwargs.get("tool_messages") or []
    assert any("Repeat Guard" in str(m.content) for m in tool_msgs)
