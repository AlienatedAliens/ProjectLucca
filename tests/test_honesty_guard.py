"""
Project Lucca — Unified Honesty & Register Nudge Tests (WO-11.2, G1+G6, D-HON-01)

Validates that when a tool result in the round loop has ok=False (or is rejected
by BDI), the orchestrator injects an explicit Honesty Directive into tool_messages
for subsequent rounds. The directive:
1. Names the failed tool specifically.
2. Instructs the model to state the failure plainly and never guess/fabricate numbers.
3. Gates celebration/success register (G6) on unverified or failed results.
"""

from collections import deque
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.coherence import detect_celebration_register_markers
from lucca.core.config import DEFAULT_CELEBRATION_MARKERS, get_config, load_heuristics
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    ExecutionTier,
    LLMUsage,
    TokenDelta,
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


# ============================================================================
# Register gate unit tests (harness-side celebration marker detection)
# ============================================================================


def test_celebration_markers_in_config() -> None:
    """Register gate markers exist in config defaults and load_heuristics."""
    markers = load_heuristics("celebration_markers")
    assert "crushed it" in markers
    assert "we did it" in markers
    assert "nailed" in markers
    assert "perfect!" in markers
    assert set(markers) == set(DEFAULT_CELEBRATION_MARKERS)


@pytest.mark.parametrize(
    "narration,expected",
    [
        ("We did it! The answer is 3236823534.", ["we did it"]),
        ("Crushed it! Here is your result.", ["crushed it"]),
        ("Nailed it! Done.", ["nailed it", "nailed"]),
        ("That was perfect!", ["perfect!"]),
        ("I encountered an error running run_python, so I cannot provide the number.", []),
        ("The calculation failed.", []),
        ("My computation tool failed, so I cannot give you that number.", []),
    ],
)
def test_detect_celebration_register_markers(narration: str, expected: list[str]) -> None:
    detected = detect_celebration_register_markers(narration)
    for exp in expected:
        assert exp in detected
    if not expected:
        assert detected == []


# ============================================================================
# Orchestrator test fixture
# ============================================================================


@pytest.fixture
def orch(tmp_path: Path) -> Orchestrator:
    db = DatabaseManager(tmp_path / "test_honesty_guard.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    orch_inst = Orchestrator.__new__(Orchestrator)
    orch_inst.config = get_config()
    orch_inst.execute_tools = True
    orch_inst.state = "idle"
    orch_inst.running = True
    orch_inst.db = db
    orch_inst.memory_store = store
    orch_inst.current_turn_receipts = []
    orch_inst.current_turn_tool_calls = []
    orch_inst.current_turn_tier = ExecutionTier.FULL_LOOP
    orch_inst.current_turn_tool_spoken = []
    orch_inst.current_turn_tool_ok = True
    orch_inst.pending_spoken_updates = deque()
    orch_inst.history = []
    orch_inst.executed_tools = []
    orch_inst.current_turn_transcript = None
    orch_inst.current_turn_assistant_reply = None
    orch_inst.active_trace = None
    orch_inst.rule_engine = MagicMock(rules={})
    orch_inst.output_supervisor = MagicMock()
    orch_inst.output_supervisor.turn_has_stalled = False
    orch_inst.output_supervisor.feed_chunk.return_value = ([], False)
    orch_inst.output_supervisor.flush.return_value = ([], False)
    orch_inst.sandbox = MagicMock()
    orch_inst.sandbox.check_confirmation_needed.return_value = False
    orch_inst.sandbox.execute_tool.return_value = ToolResult(
        call_id="x", ok=True, exit_code=0, content="ok", elapsed_ms=0.0
    )
    orch_inst.affect_tracker = MagicMock()
    orch_inst.play_ring = MagicMock()
    orch_inst._tts_queue = MagicMock()
    orch_inst.tts = MagicMock()
    orch_inst.asr = MagicMock()
    orch_inst.bdi_validator = MagicMock()
    orch_inst.bdi_validator.validate_tool_call.return_value = MagicMock(is_valid=True)
    orch_inst._publish_bus = MagicMock()
    orch_inst._publish_caption = MagicMock()
    orch_inst._speak_text = MagicMock()
    orch_inst._set_state = MagicMock()
    orch_inst._finalize_turn = MagicMock()
    return orch_inst


def _trace(trace_id: str) -> TurnTrace:
    return TurnTrace(trace_id=trace_id, session_id="sess-hon", origin="text", mode="transcript")


def _tool_round(tool: str, args: dict[str, object], call_id: str) -> list[object]:
    call = ToolCall(tool=tool, args=args, call_id=call_id)
    return [
        ToolCallEnd(call=call),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
    ]


def _text_round(text: str) -> list[object]:
    return [
        TokenDelta(delta=text),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=3)),
    ]


# ============================================================================
# Gate 1: Tool-failure round -> nudge injected exactly once
# ============================================================================


def test_tool_failure_round_nudge_injected_exactly_once(orch: Orchestrator) -> None:
    """When a tool fails in round 1, exactly one Honesty Directive is injected into round 2."""
    orch.sandbox.execute_tool.return_value = ToolResult(
        call_id="c1",
        ok=False,
        exit_code=1,
        stderr="ZeroDivisionError: division by zero",
        elapsed_ms=1.5,
    )
    orch.llm = FakeLLM(
        rounds=[
            _tool_round("run_python", {"code": "1/0"}, "c1"),
            _text_round("The computation failed with an error, so I cannot provide the result."),
        ]
    )
    trace = _trace("tr-fail-1")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="compute 1/0",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
    )

    assert orch.llm.call_count == 2
    r2_kwargs = orch.llm.all_kwargs[1]
    tool_msgs = r2_kwargs.get("tool_messages") or []

    # Count honesty directives in round 2's tool_messages
    directives = [m for m in tool_msgs if "Honesty Directive" in str(m.content)]
    assert len(directives) == 1, f"Expected exactly 1 Honesty Directive, found {len(directives)}"

    directive_text = str(directives[0].content)
    # Names the failed tool specifically
    assert "run_python" in directive_text
    # Contains anti-fabrication mandate
    assert "Never guess, estimate, or fabricate" in directive_text
    # Contains G6 register gate
    assert "Do not use celebration, confidence, or success register" in directive_text


# ============================================================================
# Gate 2: No-failure round -> no nudge
# ============================================================================


def test_no_failure_round_no_nudge(orch: Orchestrator) -> None:
    """When a tool succeeds in round 1, round 2 contains no Honesty Directive."""
    orch.sandbox.execute_tool.return_value = ToolResult(
        call_id="c1",
        ok=True,
        exit_code=0,
        content="3232500612894",
        elapsed_ms=2.0,
    )
    orch.llm = FakeLLM(
        rounds=[
            _tool_round("run_python", {"code": "348291 * 9281034"}, "c1"),
            _text_round("The product is 3,232,500,612,894."),
        ]
    )
    trace = _trace("tr-succ-1")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="multiply numbers",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
    )

    assert orch.llm.call_count == 2
    r2_kwargs = orch.llm.all_kwargs[1]
    tool_msgs = r2_kwargs.get("tool_messages") or []
    directives = [m for m in tool_msgs if "Honesty Directive" in str(m.content)]
    assert len(directives) == 0, "No honesty directive should be present when tools succeed"


# ============================================================================
# Gate 3: Failure in round 2 of 3 -> nudge only in subsequent rounds
# ============================================================================


def test_failure_in_round_2_of_3_nudge_only_in_subsequent_rounds(orch: Orchestrator) -> None:
    """Round 1 succeeds -> round 2 has no nudge.

    Round 2 fails -> round 3 has the nudge.
    """
    def execute_side_effect(call_id: str, tool_name: str, args: dict[str, object], **kwargs: object) -> ToolResult:
        if tool_name == "search_web":
            return ToolResult(call_id=call_id, ok=True, content="found data", elapsed_ms=1.0)
        return ToolResult(call_id=call_id, ok=False, stderr="execution timeout", elapsed_ms=5000.0)

    orch.sandbox.execute_tool.side_effect = execute_side_effect
    orch.llm = FakeLLM(
        rounds=[
            _tool_round("search_web", {"query": "test"}, "c1"),
            _tool_round("run_python", {"code": "heavy_calc()"}, "c2"),
            _text_round("I searched first, but the python computation timed out."),
        ]
    )
    trace = _trace("tr-seq-1")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="search then compute",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
    )

    assert orch.llm.call_count == 3

    # Round 1 stream: tool_messages is None
    assert orch.llm.all_kwargs[0].get("tool_messages") is None

    # Round 2 stream: tool_messages has round 1's tool, NO Honesty Directive
    r2_tool_msgs = orch.llm.all_kwargs[1].get("tool_messages") or []
    r2_directives = [m for m in r2_tool_msgs if "Honesty Directive" in str(m.content)]
    assert len(r2_directives) == 0, "Round 2 must NOT have a Honesty Directive (Round 1 succeeded)"

    # Round 3 stream: tool_messages has the Honesty Directive from round 2's failure
    r3_tool_msgs = orch.llm.all_kwargs[2].get("tool_messages") or []
    r3_directives = [m for m in r3_tool_msgs if "Honesty Directive" in str(m.content)]
    assert len(r3_directives) == 1, "Round 3 must have exactly 1 Honesty Directive from Round 2"
    assert "run_python" in str(r3_directives[0].content)


# ============================================================================
# Gate 4: Nudge fires on any ok=False, including after Repeat Guard exhaustion
# ============================================================================


def test_nudge_fires_after_repeat_guard_exhaustion(orch: Orchestrator) -> None:
    """When a model calls the same failing tool twice, Repeat Guard fires AND

    the Honesty Directive fires.
    """
    orch.sandbox.execute_tool.return_value = ToolResult(
        call_id="cf", ok=False, stderr="Command failed", elapsed_ms=1.0
    )
    orch.llm = FakeLLM(
        rounds=[
            _tool_round("run_python", {"code": "bad()"}, "c1"),
            _tool_round("run_python", {"code": "bad()"}, "c2"),
            _text_round("My tool failed repeatedly. I cannot compute this."),
        ]
    )
    trace = _trace("tr-repeat-fail")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="run bad",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
    )

    assert orch.llm.call_count == 3
    r3_tool_msgs = orch.llm.all_kwargs[2].get("tool_messages") or []

    # Both Repeat Guard AND Honesty Directive must be present
    has_repeat_guard = any("Repeat Guard" in str(m.content) for m in r3_tool_msgs)
    has_honesty_directive = any("Honesty Directive" in str(m.content) for m in r3_tool_msgs)

    assert has_repeat_guard, "Round 3 must carry Repeat Guard directive"
    assert has_honesty_directive, "Round 3 must carry Honesty Directive"


# ============================================================================
# Gate 5: Speculative BDI rejection also triggers the Honesty Directive
# ============================================================================


def test_speculative_bdi_rejection_triggers_honesty_directive(orch: Orchestrator) -> None:
    """When BDI validator rejects a tool call, the tool is marked failed and

    an Honesty Directive naming the rejected tool is injected for round 2.
    """
    orch.bdi_validator.validate_tool_call.return_value = MagicMock(
        is_valid=False, reason="Path traversal outside workspace forbidden", elapsed_us=15
    )
    orch.llm = FakeLLM(
        rounds=[
            _tool_round("read_file", {"path": "../../etc/shadow"}, "c1"),
            _text_round("That action was prohibited by security constraints."),
        ]
    )
    trace = _trace("tr-bdi-fail")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="read shadow",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
    )

    assert orch.llm.call_count == 2
    r2_tool_msgs = orch.llm.all_kwargs[1].get("tool_messages") or []
    directives = [m for m in r2_tool_msgs if "Honesty Directive" in str(m.content)]
    assert len(directives) == 1
    assert "read_file" in str(directives[0].content)
