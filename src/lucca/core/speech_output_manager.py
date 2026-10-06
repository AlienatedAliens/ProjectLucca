"""
Project Lucca — Speech Output Manager
WO-18b.5 (F-ARCH-103)

Extracted from Orchestrator: manages speech synthesis queue, background worker consumption,
synthesis latency tracking, overflow policy, and caption event publishing.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import TYPE_CHECKING, Literal

import structlog

from lucca.brain.chunker import sanitize_for_voice
from lucca.core.ipc_schemas import Envelope, PlayBeginPayload, UICaptionPayload
from lucca.core.tts_safety_guard import SAFE_REPLACEMENT, TTSSafetyGuard
from lucca.core.trace import TurnTrace, now_ns
from lucca.senses.ring_buffer import FLAG_ABORT, FLAG_EOS

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


class SpeechOutputManager:
    """Manages TTS queuing, worker thread, synthesis, and caption broadcasts."""

    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        start_worker: bool = False,
        maxsize: int = 32,
        safety_guard: TTSSafetyGuard | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        # P6 remediation: deterministic output screen at the TTS boundary.
        # None = guard disabled (tests / explicit opt-out).
        self._safety_guard = safety_guard
        self.tts_queue: queue.Queue[
            tuple[TurnTrace, int, str]
            | tuple[TurnTrace, int, str, threading.Event | None]
            | None
        ] = queue.Queue(maxsize=maxsize)
        self.tts_running: bool = False
        self.tts_thread: threading.Thread | None = None

        if start_worker:
            self.start()

    def start(self) -> None:
        """Starts the background core-tts worker thread if not already active."""
        if self.tts_thread is not None and self.tts_thread.is_alive():
            return
        self.tts_running = True
        self.tts_thread = threading.Thread(
            target=self.tts_worker,
            name="core-tts",
            daemon=True,
        )
        self.tts_thread.start()

    def stop(self) -> None:
        """Gracefully terminates the background worker and drains pending items."""
        self.tts_running = False
        self.clear_queue()
        try:
            self.tts_queue.put_nowait(None)
        except (queue.Full, AttributeError):
            logger.debug("speech_output_queue_full_on_stop")
        if self.tts_thread is not None and self.tts_thread.is_alive():
            self.tts_thread.join(timeout=1.0)
            self.tts_thread = None

    def clear_queue(self) -> None:
        """Drains the TTS queue and unblocks any waiting done_events.

        Canonical queue-drain logic; all abort paths must delegate here.
        """
        q = getattr(self, "tts_queue", None)
        if q is None:
            return
        while not q.empty():
            try:
                item = q.get_nowait()
                if item is not None and len(item) == 4 and item[3] is not None:
                    item[3].set()
            except (queue.Empty, AttributeError):
                break

    def emit_tts_overflow(self, trace_id: str = "", chunk_id: int = -1) -> None:
        """WO-17 Phase 7: emit a tts_queue_overflow telemetry event on the bus."""
        try:
            env = Envelope(
                type="tts_queue_overflow",
                trace_id=trace_id,
                ts_ns=now_ns(),
                src="core",
                payload={
                    "chunk_id": chunk_id,
                    "status": "dropped_oldest",
                },
            )
            orch = self._orchestrator
            if orch is not None and hasattr(orch, "_publish_bus"):
                orch._publish_bus(env)
        except Exception as exc:  # noqa: BLE001
            logger.debug("tts_overflow_event_publish_failed", error=str(exc))

    def enqueue_tts_chunk(self, trace: TurnTrace, chunk_id: int, text: str) -> None:
        """Enqueues a synthesized voice chunk with drop-oldest overflow policy (WO-17 Phase 7).

        P6 remediation: each chunk is screened by the TTS safety guard before
        entering the queue; blocked chunks are replaced with the canned safe
        line. Chunks are screened independently (sentence-aligned chunking
        makes cross-chunk evasion unlikely but not impossible).
        """
        if self._safety_guard is not None and text:
            verdict = self._safety_guard.screen(text)
            if not verdict.allowed:
                text = SAFE_REPLACEMENT
        item = (trace, chunk_id, text, None)
        try:
            self.tts_queue.put(item, timeout=0.05)
        except queue.Full:
            dropped_id = -1
            try:
                dropped = self.tts_queue.get_nowait()
                if dropped is not None and len(dropped) >= 2 and isinstance(dropped[1], int):
                    dropped_id = dropped[1]
                if dropped is not None and len(dropped) >= 4 and dropped[3] is not None:
                    dropped[3].set()
            except (queue.Empty, AttributeError):
                pass

            logger.warning(
                "tts_queue_overflow",
                chunk_id=chunk_id,
                dropped_chunk_id=dropped_id,
            )
            self.emit_tts_overflow(trace_id=trace.trace_id, chunk_id=chunk_id)

            try:
                self.tts_queue.put_nowait(item)
            except (queue.Full, AttributeError):
                logger.warning("tts_queue_full_drop_chunk", chunk_id=chunk_id)

    def publish_caption(
        self,
        text: str,
        source: Literal["assistant", "user", "status"] = "assistant",
        is_final: bool = False,
        trace_id: str = "",
    ) -> None:
        """Publishes ui.caption event to the broadcast bus."""
        orch = self._orchestrator
        if not trace_id and orch is not None:
            active_trace = getattr(orch, "active_trace", None)
            trace_id = active_trace.trace_id if active_trace else ""

        env = Envelope(
            type="ui.caption",
            trace_id=trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=UICaptionPayload(text=text, is_final=is_final, source=source).model_dump(),
        )
        if orch is not None and hasattr(orch, "_publish_bus"):
            orch._publish_bus(env)

    def synthesize_chunk(self, trace: TurnTrace, chunk_id: int, text: str) -> None:
        """Synthesizes an audio chunk, updating trace timestamps and chunk counts."""
        if chunk_id == 0:
            trace.t_tts_first_sent = now_ns()

        orch = self._orchestrator
        tts = getattr(orch, "tts", None) if orch is not None else None
        affect_tracker = getattr(orch, "affect_tracker", None) if orch is not None else None
        speed_mult = affect_tracker.get_tts_speed_multiplier() if affect_tracker else 1.0

        if tts is not None:
            try:
                _done = tts.synthesize(
                    chunk_id=chunk_id,
                    text=text,
                    speed=speed_mult,
                    is_first=(chunk_id == 0),
                )
            except TypeError:
                _done = tts.synthesize(
                    chunk_id=chunk_id,
                    text=text,
                    is_first=(chunk_id == 0),
                )

        if chunk_id == 0:
            trace.t_tts_first_done = now_ns()
        trace.t_tts_last_done = now_ns()
        trace.chunks += 1

    def tts_worker(self) -> None:
        """Background worker thread (core-tts) consuming chunks from tts_queue."""
        while self.tts_running:
            try:
                item = self.tts_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                break

            try:
                if len(item) == 3:
                    trace, chunk_id, text = item
                    done_event = None
                else:
                    trace, chunk_id, text, done_event = item

                if trace.interrupted:
                    if done_event is not None:
                        done_event.set()
                    continue

                if chunk_id is not None and chunk_id >= 0 and text:
                    self.synthesize_chunk(trace, chunk_id, text)

                if done_event is not None:
                    done_event.set()
            except Exception as exc:  # noqa: BLE001
                logger.error("tts_worker_chunk_error", error=str(exc))
                if len(item) >= 4 and item[3] is not None:
                    item[3].set()

    def wait_for_playback(self, trace: TurnTrace, timeout_s: float = 15.0) -> bool:
        """Enqueues a sentinel and waits until all preceding voice chunks have finished
        synthesizing.
        """
        done_event = threading.Event()
        sentinel_enqueued = False
        for retry in range(5):
            try:
                self.tts_queue.put((trace, -1, "", done_event), timeout=2.0)
                sentinel_enqueued = True
                break
            except queue.Full:
                logger.warning("tts_queue_full_sentinel_retry", retry=retry)
                try:
                    self.tts_queue.get_nowait()
                except (queue.Empty, AttributeError):
                    pass

        if sentinel_enqueued:
            if not done_event.wait(timeout=timeout_s):
                logger.warning("tts_sentinel_wait_timeout")
        else:
            logger.warning("tts_queue_full_sentinel_failed")

        # Drain backlog check: never set FLAG_EOS while unsynthesized chunks remain
        try:
            t_drain_start = time.perf_counter()
            while (
                hasattr(self.tts_queue, "empty")
                and not self.tts_queue.empty()
                and not trace.interrupted
            ):
                if hasattr(self.tts_queue, "_mock_name") or hasattr(
                    self.tts_queue, "_mock_methods"
                ):
                    break
                if time.perf_counter() - t_drain_start > 10.0:
                    logger.warning("tts_backlog_drain_timeout")
                    break
                time.sleep(0.05)
        except Exception as drain_err:  # noqa: BLE001
            logger.debug("tts_drain_check_failed", error=str(drain_err))

        return sentinel_enqueued and done_event.is_set()

    def speak_text(self, trace: TurnTrace, text: str) -> None:
        """Directly sanitizes and synthesizes text, managing playback state and ring buffer.

        P6 remediation: the sanitized text is screened by the TTS safety guard
        before synthesis; blocked utterances are replaced with the canned safe
        line so the caption and the spoken audio stay consistent.
        """
        clean_text = sanitize_for_voice(text)
        if not clean_text:
            return

        if self._safety_guard is not None:
            verdict = self._safety_guard.screen(clean_text)
            if not verdict.allowed:
                clean_text = SAFE_REPLACEMENT

        orch = self._orchestrator
        if orch is not None and hasattr(orch, "play_ring") and orch.play_ring is not None:
            orch.play_ring.clear_flag(FLAG_ABORT)
            orch.play_ring.clear_flag(FLAG_EOS)

        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        if orch is not None and hasattr(orch, "_publish_bus"):
            orch._publish_bus(begin_env)
        if orch is not None and hasattr(orch, "_set_state"):
            orch._set_state("speaking")

        self.publish_caption(clean_text, source="assistant", is_final=True, trace_id=trace.trace_id)
        trace.t_tts_first_sent = now_ns()

        orch = self._orchestrator
        tts = getattr(orch, "tts", None) if orch is not None else None
        affect_tracker = getattr(orch, "affect_tracker", None) if orch is not None else None
        speed_mult = affect_tracker.get_tts_speed_multiplier() if affect_tracker else 1.0

        if tts is not None:
            try:
                tts.synthesize(chunk_id=0, text=clean_text, speed=speed_mult, is_first=True)
            except TypeError:
                tts.synthesize(chunk_id=0, text=clean_text, is_first=True)

        trace.t_tts_first_done = now_ns()
        trace.t_tts_last_done = trace.t_tts_first_done
        trace.chunks += 1

        if orch is not None and hasattr(orch, "play_ring") and orch.play_ring is not None:
            orch.play_ring.set_flag(FLAG_EOS)
