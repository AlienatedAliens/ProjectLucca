"""
Project Lucca — Confirmation Manager
Spec §3, §7, WO-9 A1, WO-18b (F-ARCH-103)

Extracted from Orchestrator: manages action confirmation lifecycle,
prompt audio playback aborts, and confirmation state (audio/click/timeout/voice).
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Literal

import structlog

from lucca.senses.ring_buffer import FLAG_ABORT
from lucca.core.ipc_schemas import Envelope, PlayAbortPayload, UIConfirmPayload
from lucca.sandbox.policy import parse_confirmation_response
from lucca.core.trace import TurnTrace, now_ns
from pydantic import JsonValue

if TYPE_CHECKING:
    from lucca.core.ipc_schemas import PTTReleasedPayload
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


class ConfirmationManager:
    """Manages action confirmation dialogs and lifecycle (F-ARCH-103, WO-18b)."""

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self._orchestrator = orchestrator
        self.confirm_event: threading.Event = threading.Event()
        self.confirm_result: bool = False
        self.pending_confirmation_active: bool = False
        self.confirm_audio: PTTReleasedPayload | None = None
        self.confirm_via: str | None = None
        self.confirm_lock: threading.Lock = threading.Lock()

    def confirm_action(
        self,
        accepted: bool,
        via: Literal["voice", "click", "timeout", "abort"] = "click",
    ) -> None:
        """Manually or programmatically confirm/reject the pending action."""
        logger.info("confirmation_action_received", accepted=accepted, via=via)
        with self.confirm_lock:
            self.confirm_audio = None
            self.confirm_via = via
        self.confirm_result = accepted
        self.confirm_event.set()

    def abort_confirmation_prompt_playback(self) -> None:
        """Stops confirmation-prompt audio without cancelling the pending confirmation.

        Unlike _abort_turn, this never touches pending_confirmation_active,
        the LLM stream, the turn thread, or trace.interrupted — the waiting
        confirm worker must stay alive to receive the spoken answer.
        """
        orch = self._orchestrator
        if orch is not None and hasattr(orch, "_tts_queue"):
            while not orch._tts_queue.empty():
                try:
                    item = orch._tts_queue.get_nowait()
                    if item is not None and len(item) == 4 and item[3] is not None:
                        item[3].set()
                except queue.Empty:
                    break

        if orch is not None and hasattr(orch, "play_ring") and orch.play_ring is not None:
            orch.play_ring.set_flag(FLAG_ABORT)

        trace_id = ""
        if orch is not None and getattr(orch, "active_trace", None) is not None:
            trace_id = orch.active_trace.trace_id

        abort_env = Envelope(
            type="play.abort",
            trace_id=trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayAbortPayload(trace_id=trace_id).model_dump(),
        )
        if orch is not None and hasattr(orch, "_publish_bus"):
            orch._publish_bus(abort_env)
        logger.info("confirmation_prompt_playback_aborted")

    _abort_confirmation_prompt_playback = abort_confirmation_prompt_playback

    def request_confirmation(
        self,
        trace: TurnTrace,
        name: str,
        args: dict[str, JsonValue],
        timeout_s: float = 15.0,
    ) -> bool:
        orch = self._orchestrator
        action_desc = (
            orch._describe_tool_action(name, args)
            if orch is not None and hasattr(orch, "_describe_tool_action")
            else f"execute {name}"
        )
        prompt_text = f"Do you want me to {action_desc}? Say yes or no."

        self.confirm_result = False
        self.confirm_event.clear()
        self.pending_confirmation_active = True
        with self.confirm_lock:
            self.confirm_audio = None
            self.confirm_via = None

        if orch is not None and hasattr(orch, "_set_state"):
            orch._set_state("confirm_wait", detail=action_desc)

        confirm_env = Envelope(
            type="ui.confirm",
            trace_id=trace.trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=UIConfirmPayload(
                prompt_text=prompt_text,
                action_summary=action_desc,
                timeout_s=timeout_s,
            ).model_dump(),
        )
        if orch is not None and hasattr(orch, "_publish_bus"):
            orch._publish_bus(confirm_env)

        # Speak prompt
        if orch is not None and hasattr(orch, "_speak_text"):
            orch._speak_text(trace, prompt_text)
        # Restore confirm_wait state in case TTS set it to speaking
        if self.pending_confirmation_active:
            if orch is not None and hasattr(orch, "_set_state"):
                orch._set_state("confirm_wait", detail=action_desc)

        # Wait for user confirmation
        got_signal = self.confirm_event.wait(timeout=timeout_s)
        self.pending_confirmation_active = False

        if not got_signal:
            logger.info("confirmation_timeout", tool=name)
            return False

        with self.confirm_lock:
            confirm_audio = self.confirm_audio
            self.confirm_audio = None
            confirm_via = self.confirm_via

        if confirm_via == "voice" and confirm_audio is not None and orch is not None:
            # F-CORE-015: transcribe on this turn worker thread, outside the
            # ingest path. The slice is read late, so stale-window detection
            # (F-SENS-003) applies: an overwritten window yields an empty
            # transcript, which parses as "unknown" and cancels the action.
            pcm_samples = (
                orch.cap_ring.read_slice(
                    confirm_audio.capture_seq_start, confirm_audio.capture_seq_end
                )
                if hasattr(orch, "cap_ring") and orch.cap_ring is not None
                else b""
            )
            transcript_text = ""
            if hasattr(orch, "asr") and orch.asr and len(pcm_samples) > 0:
                asr_res = orch.asr.transcribe(pcm_samples)
                transcript_text = asr_res.text
            decision = parse_confirmation_response(transcript_text)
            # A click or barge-in may have superseded the voice answer while
            # ASR was running; the explicit user act always wins.
            with self.confirm_lock:
                superseded = self.confirm_via in ("click", "abort")
                final_result = self.confirm_result if superseded else decision == "confirm"
            if superseded:
                logger.info("voice_confirmation_superseded", via=self.confirm_via)
            else:
                logger.info("voice_confirmation_parsed", decision=decision)
            return final_result

        return self.confirm_result

    _request_confirmation = request_confirmation
