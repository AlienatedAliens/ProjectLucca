"""
Project Lucca — Promise-Without-Action Guard Tests (WO-9 A4 / F4)

Future-tense action promises ("I'll go ahead and commit that right now") can
never be grounded by receipts. detect_promised_action_claims flags them; the
turn loop injects an honesty directive forcing the model to either call the
tool or state plainly that it has not done it.
"""

from collections import deque
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.coherence import detect_promised_action_claims
from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    ExecutionTier,
    LLMUsage,
    MemoryHit,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM

TEST_MASTER_KEY = b"01234567890123456789012345678901"


# ============================================================================
# Detector unit tests (live-log cases verbatim)
# ============================================================================


@pytest.mark.parametrize(
    "narration",
    [
        "Got it! Since you've confirmed that, I'll go ahead and commit your name "
        "to my memory right now so I'll always know who I'm working with!",
        "I actually haven't executed the tool yet, but I am doing it right now. "
        "One second while I get that into my memory for good!",
        "Let me get that fixed for you right this second!",
        "I'll save that for you.",
        "I will search the web for that.",
    ],
)
def test_promises_detected(narration: str) -> None:
    assert detect_promised_action_claims(narration), f"missed promise: {narration}"


@pytest.mark.parametrize(
    "narration",
    [
        "I saved your note to the workspace.",  # past tense -> receipt path
        "I would commit it if you asked me to.",  # conditional, not a promise
        "Let me explain how my memory works.",  # no action verb
        "I checked my memory records, but have no verified record of your name.",  # abstention
        "I have not committed anything.",  # negation guard
        "",
    ],
)
def test_non_promises_not_flagged(narration: str) -> None:
    assert detect_promised_action_claims(narration) == []


# ============================================================================
# Loop-level test: promise without tool call triggers a re-prompt round
# ============================================================================


@pytest.fixture
def orch(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test_promise_guard.sqlite")
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


def test_promise_without_tool_call_triggers_reprompt(orch) -> None:
    """Round 1 promises an action with no tool call -> directive injected -> round 2 calls the tool."""
    search_call = ToolCall(
        tool="memory_search", args={"query": "Sean"}, call_id="call-p1"
    )
    orch.llm = FakeLLM(
        rounds=[
            [
                TokenDelta(delta="I'll go ahead and commit that right now! "),
                Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=3)),
            ],
            [
                ToolCallEnd(call=search_call),
                Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
            ],
        ]
    )
    orch._stream_llm_speech(
        trace=MagicMock(trace_id="tr-p1", interrupted=False),
        user_msg="commit my name",
        decision_id=None,
        memories=[],
    )
    # The re-prompt made the model actually call the tool in round 2
    assert orch.executed_tools
    assert orch.executed_tools[0][0] == "memory_search"
    assert orch.llm.call_count == 2


def test_promise_with_no_followup_breaks_loop(orch) -> None:
    """Without a follow-up round the loop terminates after the re-prompt attempt."""
    orch.llm = FakeLLM(
        rounds=[
            [
                TokenDelta(delta="I'll go ahead and save that right now! "),
                Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=3)),
            ],
        ]
    )
    orch._stream_llm_speech(
        trace=MagicMock(trace_id="tr-p2", interrupted=False),
        user_msg="save that",
        decision_id=None,
        memories=[],
    )
    # No tool was ever executed; the loop ran the re-prompt round which
    # produced nothing further (FakeLLM exhausted) and terminated.
    assert not orch.executed_tools
    assert orch.llm.call_count == 2


def test_no_promise_no_extra_round(orch) -> None:
    """A plain reply with no promise framing terminates after one round."""
    orch.llm = FakeLLM(
        rounds=[
            [
                TokenDelta(delta="Here is what I found about Sean. "),
                Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=3)),
            ],
        ]
    )
    orch._stream_llm_speech(
        trace=MagicMock(trace_id="tr-p3", interrupted=False),
        user_msg="who is Sean",
        decision_id=None,
        memories=[
            MemoryHit(
                memory_id=1,
                entry_id="e1",
                content="Sean",
                provenance="USER_EXPLICIT",
                score=1.0,
            )
        ],
    )
    assert not orch.executed_tools
    assert orch.llm.call_count == 1
