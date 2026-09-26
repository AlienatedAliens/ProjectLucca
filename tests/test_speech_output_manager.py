"""
Tests for SpeechOutputManager (WO-18b.5 / F-ARCH-103).
"""

from __future__ import annotations

import queue
import threading
from unittest.mock import MagicMock

from lucca.core.orchestrator import Orchestrator
from lucca.core.speech_output_manager import SpeechOutputManager
from lucca.core.trace import TurnTrace
from lucca.senses.ring_buffer import FLAG_ABORT, FLAG_EOS


def test_new_constructed_orchestrator_survives_property_access() -> None:
    """Condition 3: Orchestrator.__new__(Orchestrator) instances must access
    speech_output, _tts_queue, _tts_running, and _tts_thread without AttributeError,
    matching the ClockPort precedent from WO-18d.
    """
    orch = Orchestrator.__new__(Orchestrator)

    # 1. Getter access without __init__
    assert orch.speech_output is not None
    assert isinstance(orch.speech_output, SpeechOutputManager)
    assert isinstance(orch._tts_queue, queue.Queue)
    assert orch._tts_queue.maxsize == 32
    assert orch._tts_running is False
    assert orch._tts_thread is None

    # 2. Setter access
    new_q: queue.Queue[
        tuple[TurnTrace, int, str]
        | tuple[TurnTrace, int, str, threading.Event | None]
        | None
    ] = queue.Queue(maxsize=16)
    orch._tts_queue = new_q
    assert orch._tts_queue is new_q
    assert orch.speech_output.tts_queue is new_q

    orch._tts_running = True
    assert orch._tts_running is True
    assert orch.speech_output.tts_running is True

    mock_thread = MagicMock()
    orch._tts_thread = mock_thread
    assert orch._tts_thread is mock_thread
    assert orch.speech_output.tts_thread is mock_thread


def test_speech_output_manager_clear_queue_unblocks_waiters() -> None:
    """Condition 2: clear_queue() must drain the queue and set done_event
    for any enqueued items waiting with threading.Event.
    """
    manager = SpeechOutputManager()
    trace = TurnTrace(trace_id="test-clear")
    ev1 = threading.Event()
    ev2 = threading.Event()

    manager.tts_queue.put((trace, 0, "hello", ev1))
    manager.tts_queue.put((trace, -1, "", ev2))
    assert not manager.tts_queue.empty()
    assert not ev1.is_set()
    assert not ev2.is_set()

    manager.clear_queue()

    assert manager.tts_queue.empty()
    assert ev1.is_set()
    assert ev2.is_set()


def test_speech_output_manager_drop_oldest_overflow() -> None:
    """WO-17 Phase 7: drop-oldest eviction policy and overflow event publication."""
    mock_orch = MagicMock()
    manager = SpeechOutputManager(orchestrator=mock_orch, maxsize=3)
    trace = TurnTrace(trace_id="test-overflow")

    manager.enqueue_tts_chunk(trace, 0, "chunk 0")
    manager.enqueue_tts_chunk(trace, 1, "chunk 1")
    manager.enqueue_tts_chunk(trace, 2, "chunk 2")
    assert manager.tts_queue.qsize() == 3

    # Enqueue 4th item on full queue (maxsize=3)
    manager.enqueue_tts_chunk(trace, 3, "chunk 3")
    assert manager.tts_queue.qsize() == 3

    items = []
    while not manager.tts_queue.empty():
        items.append(manager.tts_queue.get_nowait())

    # Chunk 0 should have been dropped; chunks 1, 2, 3 remain
    chunk_ids = [item[1] for item in items if item is not None]
    assert chunk_ids == [1, 2, 3]

    # Verify tts_queue_overflow event was published
    assert mock_orch._publish_bus.called
    emitted_envs = [
        call.args[0] for call in mock_orch._publish_bus.call_args_list
        if getattr(call.args[0], "type", None) == "tts_queue_overflow"
    ]
    assert len(emitted_envs) >= 1
    assert emitted_envs[0].payload["chunk_id"] == 3
    assert emitted_envs[0].payload["status"] == "dropped_oldest"


def test_speech_output_manager_publish_caption() -> None:
    """Captions published to orchestrator bus with correct envelope payload."""
    mock_orch = MagicMock()
    mock_orch.active_trace = TurnTrace(trace_id="trace-cap")
    manager = SpeechOutputManager(orchestrator=mock_orch)

    manager.publish_caption("Hello world", source="assistant", is_final=True)

    assert mock_orch._publish_bus.called
    env = mock_orch._publish_bus.call_args[0][0]
    assert env.type == "ui.caption"
    assert env.trace_id == "trace-cap"
    assert env.payload["text"] == "Hello world"
    assert env.payload["source"] == "assistant"
    assert env.payload["is_final"] is True


def test_speech_output_manager_speak_text_lifecycle() -> None:
    """Condition 1: speak_text operates through self._orchestrator without duplicating state."""
    mock_orch = MagicMock()
    mock_orch.play_ring = MagicMock()
    mock_orch.tts = MagicMock()
    mock_orch.affect_tracker.get_tts_speed_multiplier.return_value = 1.0

    manager = SpeechOutputManager(orchestrator=mock_orch)
    trace = TurnTrace(trace_id="trace-speak")

    manager.speak_text(trace, "Hello voice test!")

    # 1. Ring buffer flags cleared and EOS set
    mock_orch.play_ring.clear_flag.assert_any_call(FLAG_ABORT)
    mock_orch.play_ring.clear_flag.assert_any_call(FLAG_EOS)
    mock_orch.play_ring.set_flag.assert_called_with(FLAG_EOS)

    # 2. State machine updated via orchestrator
    mock_orch._set_state.assert_called_with("speaking")

    # 3. TTS synthesize called
    mock_orch.tts.synthesize.assert_called_once()
    call_kwargs = mock_orch.tts.synthesize.call_args.kwargs
    assert call_kwargs.get("chunk_id") == 0
    assert "Hello voice test!" in call_kwargs.get("text", "")

    # 4. Bus messages published (play.begin and ui.caption)
    published_types = [
        call.args[0].type for call in mock_orch._publish_bus.call_args_list
    ]
    assert "play.begin" in published_types
    assert "ui.caption" in published_types


def test_speech_output_manager_worker_and_stop() -> None:
    """Worker consumes synthesized chunks and stop joins thread cleanly."""
    mock_orch = MagicMock()
    mock_orch.tts = MagicMock()
    mock_orch.affect_tracker.get_tts_speed_multiplier.return_value = 1.0

    manager = SpeechOutputManager(orchestrator=mock_orch, start_worker=True)
    assert manager.tts_running is True
    assert manager.tts_thread is not None and manager.tts_thread.is_alive()

    trace = TurnTrace(trace_id="trace-worker")
    done_ev = threading.Event()
    manager.tts_queue.put((trace, 0, "worker chunk", done_ev))

    assert done_ev.wait(timeout=2.0)
    mock_orch.tts.synthesize.assert_called_once()

    manager.stop()
    assert manager.tts_running is False
    assert manager.tts_thread is None
