"""WO-43 Sub-Step 2.3: Unit tests for TracebackDivergenceGuard wiring in SpeechStreamPipeline."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    LLMUsage,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
    ToolResult,
)
from lucca.core.speech_stream_pipeline import SpeechStreamPipeline
from lucca.core.trace import TurnTrace

LLMStreamEvent = Done | TokenDelta | ToolCallEnd


class _ScriptedLLM:
    """Deterministic scripted LLM stream for testing sub-turn tool loops."""

    def __init__(self, rounds: list[list[LLMStreamEvent]]) -> None:
        self._rounds = list(rounds)
        self.call_count = 0
        self.all_kwargs: list[dict[str, object]] = []

    def stream_turn(self, **kwargs: object) -> Iterator[LLMStreamEvent]:
        idx = self.call_count
        self.call_count += 1
        self.all_kwargs.append(kwargs)
        events = self._rounds[idx] if idx < len(self._rounds) else []
        yield from events


def _tool_round(tool: str, args: dict[str, object], call_id: str) -> list[LLMStreamEvent]:
    call = ToolCall(tool=tool, args=args, call_id=call_id)
    return [
        ToolCallEnd(call=call),
        Done(usage=LLMUsage(prompt_tokens=6, completion_tokens=2)),
    ]


def _text_round(text: str) -> list[LLMStreamEvent]:
    return [
        TokenDelta(delta=text),
        Done(usage=LLMUsage(prompt_tokens=6, completion_tokens=4)),
    ]


@pytest.fixture
def orch() -> Orchestrator:
    o = Orchestrator.__new__(Orchestrator)
    o._cancel_token = threading.Event()
    o.execute_tools = True
    o.history = []
    o.affect_tracker = MagicMock()
    o.affect_tracker.get_prompt_suffix_tag.return_value = "[STANCE: NEUTRAL]"
    o.output_supervisor = MagicMock()
    o.output_supervisor.feed_chunk.side_effect = lambda c, _t, **_kw: ([(c, "PASS")], False)
    o.output_supervisor.flush.return_value = ([], False)
    o.output_supervisor.turn_has_stalled = False
    o.play_ring = MagicMock()
    o.sandbox = MagicMock(taint_flags=0)
    o.bdi_validator = MagicMock()
    o.bdi_validator.validate_tool_call.return_value = MagicMock(
        is_valid=True, reason="OK", elapsed_us=5
    )
    o.turn_pipeline = MagicMock()
    o.turn_pipeline.sanity_guard.validate.return_value = MagicMock(is_valid=True, directive="")
    o._publish_bus = MagicMock()
    o._publish_caption = MagicMock()
    o._speak_text = MagicMock()
    o._set_state = MagicMock()
    o._enqueue_tts_chunk = MagicMock()
    o._finalize_turn = MagicMock()
    o._select_verbal_cue = MagicMock(return_value="Checking.")
    o._log_impasse_to_backlog = MagicMock()
    o._check_functional_coherence = MagicMock(return_value=None)
    o.speech_output = MagicMock()
    o.speech_stream = SpeechStreamPipeline(o)
    return o


def _make_trace(trace_id: str) -> TurnTrace:
    return TurnTrace(trace_id=trace_id, session_id="sess-div", origin="text", mode="transcript")


def test_repeated_failing_tool_call_triggers_divergence_and_aborts_retries(
    orch: Orchestrator,
) -> None:
    """Repeating the same failing tool call twice triggers TracebackDivergenceGuard,
    withdraws tools on Round 3, and prevents Round 3/4 tool execution retries."""
    executed_calls: list[tuple[str, dict[str, object]]] = []

    def _fake_handle_tool(
        _trace: TurnTrace, tool_name: str, tool_args: dict[str, object], **_kw: object
    ) -> ToolResult:
        executed_calls.append((tool_name, tool_args))
        return ToolResult(
            call_id=f"c-{len(executed_calls)}",
            ok=False,
            stderr="ZeroDivisionError: division by zero",
            elapsed_ms=2.0,
        )

    orch._handle_tool_call = _fake_handle_tool  # type: ignore[method-assign]

    # Model attempts 4 identical failing tool calls in a row
    orch.llm = _ScriptedLLM(
        rounds=[
            _tool_round("run_python", {"code": "1 / 0"}, "c1"),
            _tool_round("run_python", {"code": "1 / 0"}, "c2"),
            _tool_round("run_python", {"code": "1 / 0"}, "c3"),
            _tool_round("run_python", {"code": "1 / 0"}, "c4"),
        ]
    )

    trace = _make_trace("tr-div-fail")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="compute 1/0",
        decision_id=None,
        memories=[],
        tools=[{"type": "function", "function": {"name": "run_python"}}],
        max_rounds=4,
    )

    # Tool was only executed twice (Round 1 and Round 2); Round 3/4 retries were halted!
    assert len(executed_calls) == 2
    # Round 3 had tools withdrawn (tools=[]) and received Divergence Guard directive
    assert orch.llm.call_count == 3
    r3_kwargs = orch.llm.all_kwargs[2]
    assert r3_kwargs["tools"] == []
    r3_msgs = r3_kwargs.get("tool_messages") or []
    assert any("Divergence Guard (state_cycle)" in str(m.content) for m in r3_msgs)


def test_alternating_oscillation_triggers_state_cycle(orch: Orchestrator) -> None:
    """Alternating between two tool calls (A -> B -> A) triggers TracebackDivergenceGuard."""
    executed_calls: list[tuple[str, dict[str, object]]] = []

    def _fake_handle_tool(
        _trace: TurnTrace, tool_name: str, tool_args: dict[str, object], **_kw: object
    ) -> ToolResult:
        executed_calls.append((tool_name, tool_args))
        return ToolResult(
            call_id=f"c-{len(executed_calls)}",
            ok=True,
            content="file contents",
            elapsed_ms=1.0,
        )

    orch._handle_tool_call = _fake_handle_tool  # type: ignore[method-assign]

    orch.llm = _ScriptedLLM(
        rounds=[
            _tool_round("file_read", {"path": "a.txt"}, "c1"),
            _tool_round("file_read", {"path": "b.txt"}, "c2"),
            _tool_round("file_read", {"path": "a.txt"}, "c3"),
            _text_round("Done reading files a.txt and b.txt."),
        ]
    )

    trace = _make_trace("tr-div-osc")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="compare a.txt and b.txt",
        decision_id=None,
        memories=[],
        tools=[{"type": "function", "function": {"name": "file_read"}}],
        max_rounds=6,
    )

    assert len(executed_calls) == 3
    r4_kwargs = orch.llm.all_kwargs[3]
    assert r4_kwargs["tools"] == []
    r4_msgs = r4_kwargs.get("tool_messages") or []
    assert any("Divergence Guard (state_cycle)" in str(m.content) for m in r4_msgs)


def test_progressive_distinct_multi_tool_calls_do_not_trigger_false_divergence(
    orch: Orchestrator,
) -> None:
    """Distinct progressive multi-tool calls (search_web -> fetch_url -> note_write)
    converge normally without triggering TracebackDivergenceGuard."""
    executed_calls: list[tuple[str, dict[str, object]]] = []

    def _fake_handle_tool(
        _trace: TurnTrace, tool_name: str, tool_args: dict[str, object], **_kw: object
    ) -> ToolResult:
        executed_calls.append((tool_name, tool_args))
        return ToolResult(
            call_id=f"c-{len(executed_calls)}",
            ok=True,
            content=f"ok from {tool_name}",
            elapsed_ms=1.0,
        )

    orch._handle_tool_call = _fake_handle_tool  # type: ignore[method-assign]

    orch.llm = _ScriptedLLM(
        rounds=[
            _tool_round("search_web", {"query": "Lucca neurosymbolic architecture"}, "c1"),
            _tool_round("fetch_url", {"url": "https://example.org/lucca"}, "c2"),
            _tool_round("note_write", {"title": "Summary", "body": "Verified architecture"}, "c3"),
            _text_round("I searched, fetched the page, and saved the summary note."),
        ]
    )

    trace = _make_trace("tr-div-prog")
    orch._stream_llm_speech(
        trace=trace,
        user_msg="search, fetch, and write a note",
        decision_id=None,
        memories=[],
        tools=[{"type": "function"}],
        max_rounds=6,
    )

    assert len(executed_calls) == 3
    assert orch.llm.call_count == 4
    # None of the rounds had Divergence Guard injected, and tools remained available on Round 4
    r4_kwargs = orch.llm.all_kwargs[3]
    assert r4_kwargs["tools"] == [{"type": "function"}]
    r4_msgs = r4_kwargs.get("tool_messages") or []
    assert not any("Divergence Guard" in str(m.content) for m in r4_msgs)
