"""
Project Lucca — Emergency Reflex Built-in Fallback Tests
Verifies that critical halt/stop/pause/mute/shutdown commands execute immediately (<150ms)
via built-in reflex handler even when no custom MicroScheme rule is registered.
"""

from unittest.mock import MagicMock

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import ExecutionTier, RouteAction
from lucca.core.trace import TurnTrace
from lucca.senses.ring_buffer import FLAG_ABORT, FLAG_EOS


def test_builtin_emergency_stop_reflex() -> None:
    """Verifies that saying 'Stop.' triggers built-in reflex halt without calling LLM."""
    orch = Orchestrator(execute_tools=False)
    try:
        orch.play_ring.clear_flag(FLAG_ABORT)
        orch.play_ring.clear_flag(FLAG_EOS)

        # Mock LLM client to ensure it is NEVER called
        orch.llm.stream_turn = MagicMock()

        # Route "Stop."
        decision = orch.router.route(transcript="Stop.")
        assert decision.action == RouteAction.RULE
        assert getattr(decision, "tier", None) == ExecutionTier.REFLEX

        # Simulate turn execution for "Stop." with zero custom rules
        trace = TurnTrace(
            trace_id="test-stop-001",
            session_id="test-sess",
            origin="ptt",
            mode="transcript",
        )
        from lucca.core.ipc_schemas import PTTReleasedPayload

        p = PTTReleasedPayload(
            t_ns=1000,
            capture_seq_start=0,
            capture_seq_end=1600,
            duration_ms=100.0,
            vad_speech_ms=100.0,
        )

        # Mock ASR to return "Stop."
        asr_mock = MagicMock()
        asr_res_mock = MagicMock()
        asr_res_mock.text = "Stop."
        asr_mock.transcribe.return_value = asr_res_mock
        orch.asr = asr_mock

        orch._abort_turn = MagicMock(wraps=orch._abort_turn)

        orch._run_turn(trace, p)

        # 1. Assert LLM was NOT invoked
        orch.llm.stream_turn.assert_not_called()

        # 2. Assert abort was triggered immediately on turn/playback and reflex completed with EOS
        orch._abort_turn.assert_called_once()
        assert orch.play_ring.has_flag(FLAG_EOS)

        # 3. Assert conversation history recorded the emergency reflex
        assert len(orch.history) >= 2
        assert orch.history[-1]["role"] == "assistant"
        assert "Emergency Reflex: Stopped." in orch.history[-1]["content"]
    finally:
        orch.stop()


def test_builtin_emergency_stop_reflex_text_turn() -> None:
    """Verifies text turn 'Stop.' triggers built-in reflex halt without calling LLM."""
    orch = Orchestrator(execute_tools=False)
    try:
        orch.llm.stream_turn = MagicMock()
        orch._abort_turn = MagicMock(wraps=orch._abort_turn)

        trace = TurnTrace(
            trace_id="test-stop-text-001",
            session_id="test-sess",
            origin="text",
            mode="transcript",
        )

        orch._run_text_turn(trace, "Stop.")

        orch.llm.stream_turn.assert_not_called()
        orch._abort_turn.assert_called_once()
        assert orch.play_ring.has_flag(FLAG_EOS)
        assert "Emergency Reflex: Stopped." in orch.history[-1]["content"]
    finally:
        orch.stop()


def test_builtin_emergency_shutdown_reflex() -> None:
    """Verifies that saying 'shut down' triggers on_quit_requested without calling LLM."""
    orch = Orchestrator(execute_tools=False)
    try:
        orch.quit_requested = False
        orch.llm.stream_turn = MagicMock()

        trace = TurnTrace(
            trace_id="test-shutdown-001",
            session_id="test-sess",
            origin="ptt",
            mode="transcript",
        )
        from lucca.core.ipc_schemas import PTTReleasedPayload

        p = PTTReleasedPayload(
            t_ns=2000,
            capture_seq_start=0,
            capture_seq_end=1600,
            duration_ms=100.0,
            vad_speech_ms=100.0,
        )

        asr_mock = MagicMock()
        asr_res_mock = MagicMock()
        asr_res_mock.text = "shut down"
        asr_mock.transcribe.return_value = asr_res_mock
        orch.asr = asr_mock

        orch._run_turn(trace, p)

        orch.llm.stream_turn.assert_not_called()
        assert orch.quit_requested is True
        assert "Emergency Reflex: Shutting down." in orch.history[-1]["content"]
    finally:
        orch.stop()
