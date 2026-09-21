"""
Project Lucca — Central Orchestrator & State Machine
Spec 01 §3, §4, §6, Spec 10, ADR-008
"""

import asyncio
import base64
import io
import json
import os
import queue
import re
import sys
import threading
import time
import wave
from collections import deque
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001, S110
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001, S110
        pass

import structlog
import ulid
import zmq
from pydantic import JsonValue

from lucca.brain.chunker import StreamingChunker, sanitize_for_voice
from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import (
    build_narration_messages,
    get_all_tool_definitions,
    set_persona,
)
from lucca.core.affect import AffectSignal, AffectTracker
from lucca.core.bdi_validator import SpeculativeBDIValidator
from lucca.core.capabilities import dispatch_invoke_skill
from lucca.core.cascade import EpistemicSearchCascade, EpistemicSubstrate
from lucca.core.coherence import ToolReceipt, detect_ungrounded_action_claims
from lucca.core.config import get_config
from lucca.core.exceptions import SchemeInterruptSignal, SchemeYieldSignal
from lucca.core.ipc_schemas import (
    Envelope,
    PlayAbortPayload,
    PlayBeginPayload,
    PTTReleasedPayload,
    UICaptionPayload,
    UIConfigUpdatePayload,
    UIConfirmPayload,
    UIConfirmResultPayload,
    UIStatePayload,
    UIUserTextPayload,
    decode_envelope,
    encode_envelope,
)
from lucca.core.schemas import (
    ChatMessage,
    DecisionRecord,
    ExecutionTier,
    MemoryHit,
    Provenance,
    RetrievalQuery,
    RouteAction,
    RuleOutcome,
    RuleState,
    Say,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
    ToolResult,
    TTSChunk,
    UnsignedPayload,
)
from lucca.core.trace import TurnTrace, log_turn_trace, now_ns
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine, is_rollup_due
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
    create_assistant_utterance_signer,
    create_user_speech_signer,
)
from lucca.ports import MemoryStorePort, STTPort, TTSPort
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.eval import evaluate_plan, evaluate_rule
from lucca.router.heuristic import HeuristicRouter
from lucca.router.labeler import derive_label, persist_decision_label
from lucca.sandbox.output_supervisor import OutputSupervisorSession
from lucca.sandbox.policy import parse_confirmation_response
from lucca.sandbox.service import SandboxService
from lucca.senses.asr import ASRWorker
from lucca.senses.ring_buffer import (
    FLAG_ABORT,
    FLAG_EOS,
    get_capture_ring,
    get_playback_ring,
)
from lucca.senses.tts import TTSWorker

logger = structlog.get_logger(__name__)

TurnState = Literal[
    "idle", "listening", "thinking", "speaking", "confirm_wait", "postturn", "degraded", "offline"
]


def normalize_spelled_words(transcript: str) -> tuple[str, list[str]]:
    """
    Detects single-letter spelling sequences (hyphenated 'F-A-W-K-N-E-R', period-separated
    'F. A. W. K. N. E. R.', or space-separated single letters 'F A W K N E R') from ASR output,
    assembles them into title-cased words, and returns (normalized_transcript, detected_words).
    """
    detected_words: list[str] = []

    # 1. Period-separated letters (e.g. F. A. W. K. N. E. R. or F.A.W.K.N.E.R.)
    def replace_period(m: re.Match[str]) -> str:
        raw = str(m.group(0))
        letters = re.findall(r"[a-zA-Z]", raw)
        if len(letters) >= 3:
            w = str("".join(letters).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(r"\b[a-zA-Z]\.(?:\s*[a-zA-Z]\.){2,}", replace_period, transcript)

    # 2. Hyphen-separated letters (e.g. F-A-W-K-N-E-R or F - A - W - K - N - E - R)
    def replace_hyphen(m: re.Match[str]) -> str:
        raw = str(m.group(0))
        letters = re.findall(r"[a-zA-Z]", raw)
        if len(letters) >= 3:
            w = str("".join(letters).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(r"\b[a-zA-Z](?:\s*-\s*[a-zA-Z]){2,}\b", replace_hyphen, text)

    # 3. Space-separated single letters (e.g. F A W K N E R or W K N E R)
    def replace_spaces(m: re.Match[str]) -> str:
        raw = str(m.group(1))
        tokens = raw.split()
        if len(tokens) >= 3 and all(len(t) == 1 and t.isalpha() for t in tokens):
            w = str("".join(tokens).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(
        r"(?:^|(?<=\s))([a-zA-Z](?:\s+[a-zA-Z]){2,})(?=\s|[.,!?]|$)",
        replace_spaces,
        text,
    )

    return text, list(dict.fromkeys(detected_words))


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculates Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            dels = curr[j] + 1
            subs = prev[j] + (0 if c1 == c2 else 1)
            curr.append(min(ins, dels, subs))
        prev = curr
    return prev[-1]


STANCE_MARKERS: tuple[str, ...] = (
    "i think",
    "i believe",
    "in my view",
    "i prefer",
    "my opinion",
)


def _extract_stance_topic(text: str) -> str:
    """Extracts candidate topic string from a first-person stance utterance (Spec §7, WP-2)."""
    lower = text.lower()
    for marker in STANCE_MARKERS:
        if marker in lower:
            idx = lower.find(marker)
            sub = text[idx + len(marker) :].strip(" ,:.-")
            if sub:
                clause = re.split(r"[.!?;\n]+", sub)[0].strip()
                if clause:
                    return clause[:40].strip()
    return text[:40].strip()


class Orchestrator:
    quit_requested: bool = False

    def __init__(
        self,
        llm: LLMClient | None = None,
        tts: TTSPort | type[TTSPort] | None = None,
        asr: STTPort | type[STTPort] | None = None,
        sandbox: SandboxService | None = None,
        execute_tools: bool = True,
        router: HeuristicRouter | None = None,
        db: DatabaseManager | None = None,
        rule_engine: RuleLifecycleManager | None = None,
        memory_store: MemoryStorePort | None = None,
        master_key: bytes | None = None,
        user_signer: UserSpeechSigner | None = None,
        cascade: EpistemicSearchCascade | None = None,
        affect_tracker: AffectTracker | None = None,
        reflection_engine: ReflectionEngine | None = None,
    ) -> None:
        self.config = get_config()
        self.execute_tools = execute_tools
        self.state: TurnState = "idle"
        self.running = False

        # ZeroMQ sockets
        self.ctx = zmq.Context()
        self.ctl_sock = self.ctx.socket(zmq.ROUTER)
        self.bus_sock = self.ctx.socket(zmq.PUB)
        self.ingest_sock = self.ctx.socket(zmq.PULL)
        self.ingest_sock.setsockopt(zmq.RCVHWM, 1000)

        # Audio rings
        self.cap_ring = get_capture_ring(create=True)
        self.play_ring = get_playback_ring(create=True)
        self.play_ring.clear_flag(FLAG_ABORT)
        self.play_ring.clear_flag(FLAG_EOS)

        # Brain & Voice
        self.llm = llm or LLMClient()
        if tts is not None:
            if isinstance(tts, type):
                self.tts = tts(self.play_ring)
            else:
                self.tts = tts
        else:
            self.tts = TTSWorker(self.play_ring)
        self.chunker = StreamingChunker()

        # TTS synthesis queue & worker thread (F-CORE-017)
        self._tts_queue: queue.Queue[
            tuple[TurnTrace, int, str] | tuple[TurnTrace, int, str, threading.Event | None] | None
        ] = queue.Queue(maxsize=8)
        self._tts_running = True
        self._tts_thread = threading.Thread(
            target=self._tts_worker,
            name="core-tts",
            daemon=True,
        )
        self._tts_thread.start()

        # ASR
        if asr is not None:
            if isinstance(asr, type):
                self.asr = asr()
            else:
                self.asr = asr
        else:
            self.asr = ASRWorker()

        # Sandbox Service
        self.sandbox = sandbox or SandboxService(execute_apps=self.execute_tools)

        # Output Supervisor Layer (Dimension 7B)
        self.output_supervisor: OutputSupervisorSession[TTSChunk] = OutputSupervisorSession()

        # Rule Engine (Spec 05 §6 & §8)
        if rule_engine is not None:
            self.rule_engine = rule_engine
        else:
            default_skills = self.config.resolve_path("config/skills")
            self.rule_engine = RuleLifecycleManager(
                skills_dir=default_skills if default_skills.exists() else None
            )

        # Router & Decision Telemetry
        self.db = db
        if router is not None:
            self.router = router
        else:
            log_path = self.config.home_dir / "logs" / "decisions.jsonl"
            self.router = HeuristicRouter(db=self.db, log_path=log_path)

        self.prev_decision_record: DecisionRecord | None = None
        self.prev_turn_ts: float | None = None
        self.current_turn_tool_calls: list[ToolCall] = []
        self.current_turn_tool_spoken: list[str] = []
        self.current_turn_tool_ok: bool = True
        self.current_turn_shadow_outcomes: list[RuleOutcome] = []
        self.current_turn_receipts: list[ToolReceipt] = []
        self.pending_spoken_updates: deque[str] = deque()
        self.current_turn_tier: ExecutionTier = ExecutionTier.FULL_LOOP

        # Confirmation State (F-CORE-015: voice answers are handed off as a
        # PTTReleasedPayload and transcribed by the waiting turn worker, never
        # on the ingest thread)
        self._confirm_event = threading.Event()
        self._confirm_result: bool = False
        self._pending_confirmation_active: bool = False
        self._confirm_audio: PTTReleasedPayload | None = None
        self._confirm_via: str | None = None
        self._confirm_lock = threading.Lock()

        # Turn context
        self.active_trace: TurnTrace | None = None
        self.active_turn_thread: threading.Thread | None = None
        self.history: list[dict[str, str]] = []
        self.executed_tools: list[tuple[str, dict[str, JsonValue]]] = []
        self._turn_lock = threading.Lock()
        self._last_pong: dict[str, float] = {}
        self._last_ptt_press_ns: int = 0
        self._last_unspoken_tool_msg: str | None = None
        self.quit_requested: bool = False

        # Memory Store & Provenance Signer
        self.memory_store = memory_store
        key = master_key
        if key is None and memory_store is not None:
            store_key = getattr(memory_store, "master_key", None)
            if isinstance(store_key, (bytes, bytearray)) and len(store_key) >= 32:
                key = bytes(store_key)

        if user_signer is not None:
            self.user_signer: UserSpeechSigner | None = user_signer
        elif key is not None and len(key) >= 32:
            self.user_signer = create_user_speech_signer(master_key=key)
        else:
            self.user_signer = None

        self.session_id: str = str(ulid.ULID())
        self.current_turn_transcript: str | None = None

        # Epistemic Search Cascade (Milestone 3)
        self.cascade = cascade or EpistemicSearchCascade(
            sandbox=self.sandbox,
            memory_store=self.memory_store,
        )

        ws_root = (
            getattr(self.sandbox.workspace_mgr, "workspace_root", None)
            if hasattr(self.sandbox, "workspace_mgr")
            else None
        )
        if ws_root is None:
            ws_root = self.config.resolve_path("workspace")
        self.bdi_validator = SpeculativeBDIValidator(workspace_root=ws_root)

        # Affect State Machine & 3D PAD ODE (Milestone 5)
        self.affect_tracker = affect_tracker or AffectTracker()
        self.active_detected_words: list[str] = []
        self.assistant_signer: AssistantUtteranceSigner | None = None
        self.breach_signer: CoherenceBreachSigner | None = None

        # Autobiographical Reflection Engine (Spec §7, D-MEM-04, WP-2)
        if reflection_engine is not None:
            self.reflection_engine: ReflectionEngine | None = reflection_engine
        elif self.memory_store is not None and hasattr(self.memory_store, "db"):
            effective_key = (
                key if (key is not None and len(key) >= 32) else b"01234567890123456789012345678901"
            )
            self.reflection_engine = ReflectionEngine(
                db=self.memory_store.db,
                store=self.memory_store,
                master_key=effective_key,
            )
        elif self.db is not None and self.memory_store is not None:
            effective_key = (
                key if (key is not None and len(key) >= 32) else b"01234567890123456789012345678901"
            )
            self.reflection_engine = ReflectionEngine(
                db=self.db,
                store=self.memory_store,
                master_key=effective_key,
            )
        else:
            self.reflection_engine = None

    def _neutralize_context_attractors(self, target_word: str) -> list[str]:
        """
        In-place history token neutralization: Replaces corrupt phonetic/orthographic
        variants in recent turn history with target_word, destroying self-attention
        repetition basins without causing amnesia or deleting pronoun antecedents.
        Returns list of replaced corrupt variants.
        """
        replaced_variants: set[str] = set()
        target_lower = target_word.lower()
        recent_turns = self.history[-10:] if len(self.history) > 10 else self.history
        for msg in recent_turns:
            content = msg.get("content", "")
            if not content or not isinstance(content, str):
                continue
            tokens = re.findall(r"\b[a-zA-Z]{3,}\b", content)
            modified = False
            for token in tokens:
                tok_lower = token.lower()
                if tok_lower == target_lower:
                    continue
                max_dist = 2 if len(target_word) >= 6 else 1
                dist = _levenshtein_distance(target_lower, tok_lower)
                if dist <= max_dist:
                    replaced_variants.add(token)
                    replacement = target_word if token[0].isupper() else target_word.lower()
                    content = re.sub(rf"\b{re.escape(token)}\b", replacement, content)
                    modified = True
            if modified:
                msg["content"] = content
        return sorted(replaced_variants)

    @property
    def last_decision(self) -> DecisionRecord | None:
        return self.router.last_decision_record

    def start(self) -> None:
        self.running = True

        # Bind sockets
        self.ctl_sock.bind(f"tcp://127.0.0.1:{self.config.ipc.ctl_port}")
        self.bus_sock.bind(f"tcp://127.0.0.1:{self.config.ipc.bus_port}")
        self.ingest_sock.bind(f"tcp://127.0.0.1:{self.config.ipc.ingest_port}")

        # Start ingest listener thread
        ingest_thread = threading.Thread(target=self._ingest_loop, name="core-ingest", daemon=True)
        ingest_thread.start()

        # Start heartbeat thread
        hb_thread = threading.Thread(target=self._heartbeat_loop, name="core-hb", daemon=True)
        hb_thread.start()

        self._set_state("idle")

    def _set_state(self, new_state: TurnState, detail: str = "") -> None:
        self.state = new_state
        ui_state: Literal[
            "idle", "listening", "thinking", "speaking", "confirm", "offline", "degraded"
        ]
        if new_state == "confirm_wait":
            ui_state = "confirm"
        elif new_state == "postturn":
            ui_state = "idle"
        else:
            ui_state = new_state

        env = Envelope(
            type="ui.state",
            trace_id=self.active_trace.trace_id if self.active_trace else "",
            ts_ns=now_ns(),
            src="core",
            payload=UIStatePayload(state=ui_state, detail=detail).model_dump(),
        )
        self._publish_bus(env)

    def _publish_bus(self, env: Envelope) -> None:
        try:
            self.bus_sock.send(encode_envelope(env), zmq.NOBLOCK)
        except zmq.ZMQError as exc:
            logger.debug("publish_bus_zmq_error", error=str(exc))

    def publish_offline(self) -> None:
        """Broadcasts ui.state offline, play.abort, and sys.shutdown on the bus."""
        self._set_state("offline")
        trace_id = self.active_trace.trace_id if self.active_trace else ""
        abort_env = Envelope(
            type="play.abort",
            trace_id=trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayAbortPayload(trace_id=trace_id).model_dump(),
        )
        self._publish_bus(abort_env)
        shutdown_env = Envelope(
            type="sys.shutdown",
            trace_id="",
            ts_ns=now_ns(),
            src="core",
            payload={},
        )
        self._publish_bus(shutdown_env)

    def _publish_caption(
        self,
        text: str,
        source: Literal["assistant", "user", "status"] = "assistant",
        is_final: bool = False,
    ) -> None:
        trace_id = self.active_trace.trace_id if self.active_trace else ""
        env = Envelope(
            type="ui.caption",
            trace_id=trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=UICaptionPayload(text=text, is_final=is_final, source=source).model_dump(),
        )
        self._publish_bus(env)

    def _ingest_loop(self) -> None:
        while self.running:
            try:
                raw = self.ingest_sock.recv()
                env = decode_envelope(raw)
                self._handle_ingest_message(env)
            except zmq.ZMQError as exc:
                if not self.running:
                    break
                logger.debug("ingest_loop_zmq_error", error=str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.warning("ingest_loop_unexpected_error", error=str(exc))

    def _handle_ingest_message(self, env: Envelope) -> None:
        with self._turn_lock:
            if env.type == "ptt.pressed":
                self._last_ptt_press_ns = env.ts_ns
                self._on_ptt_pressed(env.ts_ns)
            elif env.type == "ptt.released":
                p = PTTReleasedPayload.model_validate(env.payload)
                self._on_ptt_released(env.ts_ns, p)
            elif env.type == "ui.user_text":
                p_text = UIUserTextPayload.model_validate(env.payload)
                self._on_user_text(env.ts_ns, p_text.text)
            elif env.type == "ui.config_update":
                p_cfg = UIConfigUpdatePayload.model_validate(env.payload)
                if p_cfg.voice:
                    self.tts.set_voice(p_cfg.voice)
                if p_cfg.speed is not None:
                    self.tts.set_speed(p_cfg.speed)
                if p_cfg.dsp_pitch_semitones is not None or p_cfg.dsp_enabled is not None:
                    pitch = (
                        p_cfg.dsp_pitch_semitones if p_cfg.dsp_pitch_semitones is not None else 0.0
                    )
                    en = p_cfg.dsp_enabled if p_cfg.dsp_enabled is not None else True
                    self.tts.set_dsp_config(pitch_semitones=pitch, enabled=en)
                if (
                    p_cfg.persona_archetype is not None
                    or p_cfg.formality is not None
                    or p_cfg.custom_system_prompt is not None
                    or p_cfg.voice is not None
                    or p_cfg.speed is not None
                    or p_cfg.ptt_key is not None
                ):
                    set_persona(
                        archetype=p_cfg.persona_archetype,
                        formality=p_cfg.formality,
                        custom_prompt=p_cfg.custom_system_prompt,
                        voice=p_cfg.voice,
                        speed=p_cfg.speed,
                        ptt_key=p_cfg.ptt_key,
                        dsp_pitch_semitones=p_cfg.dsp_pitch_semitones,
                        dsp_enabled=p_cfg.dsp_enabled,
                    )
                # Re-publish onto bus_sock so AudioProcess receives ptt_key and audio settings
                self._publish_bus(env)
                logger.info(
                    "ui_config_updated",
                    voice=p_cfg.voice,
                    speed=p_cfg.speed,
                    ptt_key=p_cfg.ptt_key,
                    archetype=p_cfg.persona_archetype,
                    formality=p_cfg.formality,
                    dsp_pitch=p_cfg.dsp_pitch_semitones,
                )
            elif env.type == "audio.first_sample_played":
                if self.active_trace:
                    self.active_trace.t_first_sample = env.ts_ns
            elif env.type == "audio.playback_done":
                if self.active_trace and self.active_trace.trace_id == env.trace_id:
                    self.active_trace.t_playback_done = env.ts_ns
            elif env.type in ("ui.talk_press", "ui.talk_release"):
                self._publish_bus(env)
            elif env.type == "ui.confirm_result":
                p_conf = UIConfirmResultPayload.model_validate(env.payload)
                self.confirm_action(p_conf.accepted, via=p_conf.via)
            elif env.type == "sys.pong":
                self._last_pong[env.src] = time.monotonic()
            elif env.type == "ui.quit":
                self.on_quit_requested()

    def on_quit_requested(self) -> None:
        """Signals that UI requested application shutdown."""
        self.quit_requested = True

    def register_peer(self, peer: str) -> None:
        """Registers an expected child process for heartbeat monitoring."""
        self._last_pong[peer] = time.monotonic()

    def dead_peers(self, misses: int = 3) -> set[str]:
        """Returns set of peers that missed heartbeats (last pong > 2.0s * misses)."""
        now = time.monotonic()
        threshold = 2.0 * misses
        return {peer for peer, last_t in self._last_pong.items() if now - last_t > threshold}

    def confirm_action(
        self,
        accepted: bool,
        via: Literal["voice", "click", "timeout"] = "click",
    ) -> None:
        """Manually or programmatically confirm/reject the pending action."""
        logger.info("confirmation_action_received", accepted=accepted, via=via)
        with self._confirm_lock:
            self._confirm_audio = None
            self._confirm_via = via
        self._confirm_result = accepted
        self._confirm_event.set()

    def _on_ptt_pressed(self, ts_ns: int) -> None:
        if self.state in ("speaking", "thinking", "confirm_wait"):
            # Instant barge-in: abort LLM and playback
            self._abort_turn()

        print("\n[PTT] 🎙️ Listening... (Hold Alt-Gr or Right-Ctrl to speak)", flush=True)
        self._publish_caption("Listening... 🎙️", source="status", is_final=False)
        self._set_state("listening")

    def _abort_turn(self) -> None:
        self.affect_tracker.record_signal(
            AffectSignal.DOUBLE_INTERRUPT, custom_cause="user barge-in interruption"
        )
        if self._pending_confirmation_active:
            self._pending_confirmation_active = False
            self._confirm_result = False
            with self._confirm_lock:
                self._confirm_audio = None
                self._confirm_via = "abort"
            self._confirm_event.set()
            logger.info("confirmation_cancelled_by_barge_in")

        target_trace_id = self.active_trace.trace_id if self.active_trace else None
        self.llm.abort(trace_id=target_trace_id)
        self.chunker.reset()

        # F-CORE-017: drain TTS synthesis queue before setting FLAG_ABORT
        while not self._tts_queue.empty():
            try:
                item = self._tts_queue.get_nowait()
                if item is not None and len(item) == 4 and item[3] is not None:
                    item[3].set()
            except queue.Empty:
                break

        self.play_ring.set_flag(FLAG_ABORT)

        # Notify audio to abort output immediately
        trace_id = self.active_trace.trace_id if self.active_trace else ""
        abort_env = Envelope(
            type="play.abort",
            trace_id=trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayAbortPayload(trace_id=trace_id).model_dump(),
        )
        self._publish_bus(abort_env)

        if self.active_trace:
            self.active_trace.interrupted = True

        # Bounded join on running turn thread (bounded to 5ms to preserve <=50ms barge-in budget)
        if self.active_turn_thread and self.active_turn_thread is not threading.current_thread():
            self.active_turn_thread.join(timeout=0.005)
            if self.active_turn_thread.is_alive():
                logger.debug("turn_thread_join_timeout", thread=self.active_turn_thread.name)
            self.active_turn_thread = None

    def _on_ptt_released(self, ts_ns: int, p: PTTReleasedPayload) -> None:
        if self._pending_confirmation_active:
            # F-CORE-015: never run ASR on the ingest thread. Stash the release
            # payload and wake the waiting turn worker, which transcribes the
            # captured slice outside the ingest path (see _request_confirmation).
            with self._confirm_lock:
                self._confirm_audio = p
                self._confirm_via = "voice"
            self._confirm_event.set()
            return

        # Empty capture guard
        if p.capture_seq_end <= p.capture_seq_start:
            print("[PTT] Empty audio sequence captured; resetting to idle.\n", flush=True)
            self._publish_caption(
                "I didn't hear anything. (Hold Alt-Gr or Right-Ctrl while speaking)",
                source="status",
                is_final=True,
            )
            self._set_state("idle")
            return

        if self.active_turn_thread and self.active_turn_thread.is_alive():
            self._abort_turn()

        trace_id = str(ulid.ULID())
        press_ns = (
            self._last_ptt_press_ns
            if self._last_ptt_press_ns > 0
            else max(1, ts_ns - int(p.duration_ms * 1_000_000))
        )
        vad_done_ns = getattr(p, "vad_done_ns", 0) or ts_ns
        trace = TurnTrace(
            trace_id=trace_id,
            session_id=self.session_id,
            origin="ptt",
            mode=self.config.llm.mode,
            t_key_press=press_ns,
            t_key_release=ts_ns,
            t_vad_done=vad_done_ns,
        )
        self.active_trace = trace
        print(f"[PTT] ⚙️ Processing speech ({p.duration_ms:.0f}ms captured)...", flush=True)
        self._publish_caption("Thinking... ⚙️", source="status", is_final=False)
        self._set_state("thinking")

        # Launch turn worker thread
        t = threading.Thread(target=self._run_turn, args=(trace, p), daemon=True)
        self.active_turn_thread = t
        t.start()

    def _on_user_text(self, ts_ns: int, user_text: str) -> None:
        if self.active_turn_thread and self.active_turn_thread.is_alive():
            self._abort_turn()
        elif self.state in ("speaking", "thinking", "confirm_wait"):
            self._abort_turn()

        trace_id = str(ulid.ULID())
        trace = TurnTrace(
            trace_id=trace_id,
            session_id=self.session_id,
            origin="text",
            mode="transcript",
            t_key_press=ts_ns,
            t_key_release=ts_ns,
            t_vad_done=ts_ns,
        )

        self.active_trace = trace

        print(f'\n[User] "{user_text}"', flush=True)
        self._publish_caption(user_text, source="user", is_final=True)
        self._publish_caption("Thinking... ⚙️", source="status", is_final=False)
        self._set_state("thinking")

        t = threading.Thread(target=self._run_text_turn, args=(trace, user_text), daemon=True)
        self.active_turn_thread = t
        t.start()

    def _build_rule_state(
        self, transcript: str, mode: Literal["audio", "transcript"] = "transcript"
    ) -> RuleState:
        local_now = time.localtime()
        intent, auto_conf, entities = self.router.classify_intent(transcript)
        return RuleState(
            schema_version=1,
            transcript=transcript,
            transcript_lower=transcript.strip().lower(),
            intent=intent,
            intent_conf=auto_conf,
            entities=entities,
            hour_local=local_now.tm_hour,
            weekday=local_now.tm_wday,
            apps_running=frozenset(),
            last_tool=self.executed_tools[-1][0] if self.executed_tools else None,
            last_tool_ok=self.current_turn_tool_ok if self.executed_tools else None,
            session_turns=len(self.history) // 2,
            mode=mode,
        )

    def _search_memories(self, text: str) -> list[MemoryHit]:
        if not self.memory_store or not text.strip():
            return []
        try:
            q = RetrievalQuery(query_text=text.strip(), k=8)
            res = self.memory_store.search(q)
            if asyncio.iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        return pool.submit(asyncio.run, res).result()
                return asyncio.run(res)
            if isinstance(res, list):
                return res
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning("memory_search_failed", error=str(e))
            return []

    def _commit_transcript(self, text: str, trace: TurnTrace) -> str | None:
        if not self.memory_store or not text.strip():
            return None
        try:
            if self.user_signer is None:
                key = getattr(self.memory_store, "master_key", None)
                if isinstance(key, (bytes, bytearray)) and len(key) >= 32:
                    self.user_signer = create_user_speech_signer(master_key=bytes(key))
                else:
                    dev_key = b"01234567890123456789012345678901"
                    self.user_signer = create_user_speech_signer(master_key=dev_key)

            unsigned = UnsignedPayload(
                content=text.strip(),
                provenance=Provenance.USER_EXPLICIT,
                kind="fact",
                nonce=os.urandom(16).hex(),
                created_at=time.time(),
                trace_id=trace.trace_id,
            )
            signed = self.user_signer.sign(unsigned)
            res = self.memory_store.commit(signed)
            if asyncio.iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(asyncio.run, res).result()
                else:
                    asyncio.run(res)
            return signed.entry_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("transcript_commit_failed", error=str(exc))
            return None

    def _commit_assistant_utterance(self, text: str, trace: TurnTrace) -> None:
        """Commits assistant's spoken utterance to memory (D-MEM-04, ASSISTANT_UTTERANCE)."""
        if not self.memory_store or not text.strip():
            return
        try:
            if not hasattr(self, "assistant_signer") or self.assistant_signer is None:
                key = getattr(self.memory_store, "master_key", None)
                if isinstance(key, (bytes, bytearray)) and len(key) >= 32:
                    self.assistant_signer = create_assistant_utterance_signer(master_key=bytes(key))
                else:
                    dev_key = b"01234567890123456789012345678901"
                    self.assistant_signer = create_assistant_utterance_signer(master_key=dev_key)

            unsigned = UnsignedPayload(
                content=text.strip(),
                provenance=Provenance.ASSISTANT_UTTERANCE,
                kind="assistant_utterance",
                nonce=os.urandom(16).hex(),
                created_at=time.time(),
                trace_id=trace.trace_id,
            )
            signed = self.assistant_signer.sign(unsigned)
            res = self.memory_store.commit(signed)
            if asyncio.iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(asyncio.run, res).result()
                else:
                    asyncio.run(res)
        except Exception as exc:  # noqa: BLE001
            logger.warning("assistant_utterance_commit_failed", error=str(exc))

    def _check_functional_coherence(
        self,
        narration: str,
        receipts: Sequence[ToolReceipt | dict[str, JsonValue] | object] | None = None,
    ) -> str | None:
        """
        Checks for discrepancy between spoken action claim and actual tool execution
        (Spec §3.3, WP-2). Returns breach description if discrepancy detected, else None.
        """
        if receipts is None:
            receipts = getattr(self, "current_turn_receipts", [])
        norm_receipts: list[ToolReceipt] = []
        for r in receipts:
            if isinstance(r, ToolReceipt):
                norm_receipts.append(r)
            elif isinstance(r, dict):
                norm_receipts.append(
                    ToolReceipt(
                        tool=str(r.get("tool") or r.get("tool_name") or ""),
                        ok=bool(r.get("ok", True)),
                        call_id=str(r.get("call_id", "")),
                        args=r.get("args") if isinstance(r.get("args"), dict) else {},
                        output=str(r.get("output")) if r.get("output") is not None else None,
                        error=str(r.get("error")) if r.get("error") is not None else None,
                    )
                )
            elif hasattr(r, "tool"):
                norm_receipts.append(
                    ToolReceipt(
                        tool=str(getattr(r, "tool", "")),
                        ok=bool(getattr(r, "ok", True)),
                        call_id=str(getattr(r, "call_id", "")),
                    )
                )
        claims = detect_ungrounded_action_claims(narration, norm_receipts)
        un_grounded = [c for c in claims if not c.grounded]
        if un_grounded:
            return un_grounded[0].breach_description or "Ungrounded action claim detected"
        return None

    def _commit_coherence_breach(self, claim: str, trace: TurnTrace | None = None) -> None:
        """Commits functional coherence breach to memory (D-MEM-04, COHERENCE_BREACH)."""
        if not self.memory_store or not claim.strip():
            return
        try:
            if not hasattr(self, "breach_signer") or self.breach_signer is None:
                key = getattr(self.memory_store, "master_key", None)
                dev_key = (
                    bytes(key)
                    if isinstance(key, (bytes, bytearray)) and len(key) >= 32
                    else b"01234567890123456789012345678901"
                )
                self.breach_signer = CoherenceBreachSigner(master_key=dev_key)

            trace_id = trace.trace_id if trace is not None else f"breach-{ulid.ULID()}"
            unsigned = UnsignedPayload(
                content=claim.strip(),
                provenance=Provenance.COHERENCE_BREACH,
                kind="coherence_breach",
                nonce=os.urandom(16).hex(),
                created_at=time.time(),
                trace_id=trace_id,
            )
            signed = self.breach_signer.sign(unsigned)
            res = self.memory_store.commit(signed)
            if asyncio.iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(asyncio.run, res).result()
                else:
                    asyncio.run(res)
        except Exception as exc:  # noqa: BLE001
            logger.warning("coherence_breach_commit_failed", error=str(exc))

    def _finalize_turn(self, trace: TurnTrace, decision_id: str | None) -> None:
        if self.active_trace is trace and not trace.interrupted:
            self._set_state("postturn")
        committed_user_id: str | None = None
        user_transcript_text: str | None = None
        if self.current_turn_transcript:
            user_transcript_text = self.current_turn_transcript
            committed_user_id = self._commit_transcript(self.current_turn_transcript, trace)
            self.current_turn_transcript = None

        if hasattr(self, "current_turn_assistant_reply") and self.current_turn_assistant_reply:
            reply_text = self.current_turn_assistant_reply
            self._commit_assistant_utterance(reply_text, trace)

            # Functional coherence check (Spec §3.3 / D-MEM-04 / WP-2)
            breach_msg = self._check_functional_coherence(reply_text, self.current_turn_receipts)
            if breach_msg:
                self._commit_coherence_breach(breach_msg, trace)

            # Stance / belief formation at runtime (Spec §7, WP-2)
            if (
                self.current_turn_tier == ExecutionTier.FULL_LOOP
                and not self.current_turn_tool_calls
            ):
                self._maybe_form_belief(reply_text, trace)

            self.current_turn_assistant_reply = None

        # Contradiction detection on USER_EXPLICIT commit (Spec §7, WP-2)
        if committed_user_id and user_transcript_text:
            self._check_contradictions(committed_user_id, user_transcript_text, trace)

        if decision_id:
            try:
                ttft_ms = (
                    (trace.t_llm_first_token - trace.t_llm_sent) / 1_000_000.0
                    if trace.t_llm_first_token and trace.t_llm_sent
                    else None
                )
                turn_tool_ok = self.current_turn_tool_ok if self.current_turn_tool_calls else None
                self.router.record_post_turn(
                    decision_id=decision_id,
                    tool_calls=self.current_turn_tool_calls,
                    tool_ok=turn_tool_ok,
                    llm_first_token_ms=ttft_ms,
                    user_interrupted=trace.interrupted,
                )
                if self.db is not None and self.router.last_decision_record:
                    cur_rec = self.router.last_decision_record
                    init_label, init_reason = derive_label(
                        cur_rec,
                        user_interrupted=trace.interrupted,
                        tool_ok=turn_tool_ok,
                    )
                    persist_decision_label(self.db, cur_rec.decision_id, init_label, init_reason)

                self.prev_decision_record = self.router.last_decision_record
                self.prev_turn_ts = time.time()
            except Exception as e:  # noqa: BLE001
                logger.debug("post_turn_telemetry_error", error=str(e))

        # Log contrastive shadow pairs per Spec 1.1.2 §6.2 (ModularRSI §3.3)
        if hasattr(self, "current_turn_shadow_outcomes") and self.current_turn_shadow_outcomes:
            turn_tool_ok = self.current_turn_tool_ok if self.current_turn_tool_calls else None
            # S1 semantics: "tool_exit_zero" requires an actual tool execution. A turn
            # where the core ran no tools is "abstained" (S1 Outcome enum), not a success.
            core_sig = (
                "operator_correct"
                if trace.interrupted
                else (
                    "abstained"
                    if not self.current_turn_tool_calls
                    else ("tool_exit_zero" if turn_tool_ok is True else "tool_exit_nonzero")
                )
            )
            core_p = (
                "RULE"
                if (
                    self.router.last_decision_record
                    and self.router.last_decision_record.decision.action == RouteAction.RULE
                )
                else "LLM"
            )
            for so in self.current_turn_shadow_outcomes:
                if so.fired or so.plan is not None or so.errored:
                    rule_sig = (
                        "error"
                        if so.errored
                        else ("tool_exit_zero" if so.plan and so.plan.actions else "abstained")
                    )
                    try:
                        self.rule_engine.log_contrastive_shadow_pair(
                            rule_id=so.rule_id,
                            trace_id=trace.trace_id,
                            rule_plan=so.plan,
                            core_tool_calls=self.current_turn_tool_calls,
                            core_path=core_p,
                            rule_outcome_signal=rule_sig,
                            core_outcome_signal=core_sig,
                        )
                    except Exception as shadow_err:  # noqa: BLE001
                        logger.debug("contrastive_shadow_log_failed", error=str(shadow_err))
            self.current_turn_shadow_outcomes = []

        trace.t_postturn_done = now_ns()
        log_turn_trace(trace)
        if self.active_trace is trace and not trace.interrupted:
            self._set_state("idle")

    def _record_tool_receipt(
        self,
        name: str,
        call_id: str,
        args: dict[str, JsonValue],
        ok: bool,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        self.current_turn_receipts.append(
            ToolReceipt(
                tool=name,
                tool_name=name,
                ok=ok,
                call_id=call_id,
                args=dict(args),
                output=output,
                error=error,
                timestamp=time.time(),
            )
        )

    def _maybe_form_belief(self, reply_text: str, trace: TurnTrace) -> None:
        """Extracts first-person stance claims and commits an ASSISTANT_BELIEF (Spec §7, WP-2)."""
        if not self.memory_store or not reply_text.strip():
            return
        if not getattr(self.config.memory, "form_beliefs", True):
            return

        lower_reply = reply_text.lower()
        if not any(m in lower_reply for m in STANCE_MARKERS):
            return

        topic = _extract_stance_topic(reply_text)
        now = time.time()
        try:
            if not hasattr(self, "assistant_signer") or self.assistant_signer is None:
                key = getattr(self.memory_store, "master_key", None)
                dev_key = (
                    bytes(key)
                    if isinstance(key, (bytes, bytearray)) and len(key) >= 32
                    else b"01234567890123456789012345678901"
                )
                self.assistant_signer = create_assistant_utterance_signer(master_key=dev_key)

            unsigned = UnsignedPayload(
                content=reply_text.strip(),
                provenance=Provenance.ASSISTANT_BELIEF,
                kind="belief",
                nonce=os.urandom(16).hex(),
                created_at=now,
                trace_id=trace.trace_id,
                confidence=0.7,
                structured={"importance": 0.3, "topic": topic, "valid_from": now},
            )
            signed = self.assistant_signer.sign(unsigned)
            res = self.memory_store.commit(signed)
            if asyncio.iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(asyncio.run, res).result()
                else:
                    asyncio.run(res)
            logger.info("assistant_belief_formed", topic=topic, trace_id=trace.trace_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("assistant_belief_commit_failed", error=str(exc))

    def _check_contradictions(self, new_entry_id: str, new_content: str, trace: TurnTrace) -> None:
        """
        Evaluates contradiction detection against active beliefs (Spec §7, D-MEM-04, WP-2).
        FTS matches candidate beliefs on topic tokens, capped at 5 beliefs with a 200 ms budget.
        """
        if self.reflection_engine is None or self.db is None:
            return

        tokens = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", new_content.lower())]
        if not tokens:
            return

        candidate_beliefs: list[tuple[int, str, str]] = []
        try:
            with self.db.read_cursor() as cur:
                fts_query = " OR ".join(f'"{t}"' for t in tokens[:10])
                try:
                    cur.execute(
                        """
                        SELECT m.memory_id, m.content, m.kind
                        FROM memories m
                        JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                        WHERE m.valid_to IS NULL
                          AND p.provenance = 'ASSISTANT_BELIEF'
                          AND m.memory_id IN (
                              SELECT rowid FROM fts_memories WHERE fts_memories MATCH ?
                          )
                        LIMIT 5
                        """,
                        (fts_query,),
                    )
                    candidate_beliefs = [(int(r[0]), str(r[1]), str(r[2])) for r in cur.fetchall()]
                except Exception:  # noqa: BLE001
                    cur.execute(
                        """
                        SELECT m.memory_id, m.content, m.kind
                        FROM memories m
                        JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                        WHERE m.valid_to IS NULL AND p.provenance = 'ASSISTANT_BELIEF'
                        LIMIT 50
                        """
                    )
                    for r in cur.fetchall():
                        c_low = str(r[1]).lower()
                        if any(t in c_low for t in tokens):
                            candidate_beliefs.append((int(r[0]), str(r[1]), str(r[2])))
                            if len(candidate_beliefs) >= 5:
                                break
        except Exception as exc:  # noqa: BLE001
            logger.debug("contradiction_search_error", error=str(exc))
            return

        if not candidate_beliefs:
            return

        t_start = time.perf_counter()
        for belief_id, _old_content, _ in candidate_beliefs:
            if (time.perf_counter() - t_start) > 0.200:
                logger.warning("reflection_contradiction_budget_exceeded", trace_id=trace.trace_id)
                break

            try:
                coro = self.reflection_engine.detect_and_handle_contradiction(
                    old_belief_id=belief_id,
                    new_content=new_content,
                    reason_entry_id=new_entry_id,
                    proposed_confidence=1.0,
                    is_conflict_top=False,
                    topic=None,
                    now=time.time(),
                )
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        is_queued, res_str = pool.submit(asyncio.run, coro).result()
                else:
                    is_queued, res_str = asyncio.run(coro)

                if is_queued:
                    logger.info(
                        "belief_revision_flagged_for_review",
                        review_id=res_str,
                        belief_id=belief_id,
                    )
                else:
                    self.pending_spoken_updates.append(res_str)
                    logger.info(
                        "belief_revision_enqueued_spoken_update",
                        spoken_update=res_str,
                        belief_id=belief_id,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("contradiction_handling_failed", error=str(exc), belief_id=belief_id)

    def _maybe_speak_pending_updates(self, trace: TurnTrace) -> None:
        """Speaks queued unflagged belief revision sentences once before turn reply."""
        while self.pending_spoken_updates:
            spoken_update = self.pending_spoken_updates.popleft()
            if spoken_update.strip():
                print(f"[Lucca Revision] 💡 {spoken_update}", flush=True)
                self._speak_text(trace, spoken_update)
                self._publish_caption(spoken_update, source="assistant", is_final=True)
                self.history.append({"role": "assistant", "content": spoken_update})

    def maybe_run_nightly_rollup(self, now: float | None = None) -> int:
        """Executes nightly roll-up if due and records persistent timestamp."""
        if not self.reflection_engine:
            return 0
        current_time = now if now is not None else time.time()
        last_rollup = self.reflection_engine.get_last_rollup_at()
        rollup_hour = getattr(self.config.memory, "rollup_hour_local", 3)
        if is_rollup_due(last_rollup, current_time, rollup_hour):
            try:
                coro = self.reflection_engine.nightly_rollup(now=current_time)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        compressed = pool.submit(asyncio.run, coro).result()
                else:
                    compressed = asyncio.run(coro)
                self.reflection_engine.record_last_rollup_at(current_time)
                logger.info("nightly_rollup_completed", compressed=compressed, ts=current_time)
                return int(compressed)
            except Exception as exc:  # noqa: BLE001
                logger.warning("nightly_rollup_failed", error=str(exc))
        return 0

    def _select_verbal_cue(self, tool_name: str) -> str:
        """Selects a natural verbal thinking cue per Proposal I / Owner Section 6 requirement."""
        t = tool_name.lower()
        if "read" in t or "cat" in t or "inspect" in t:
            return "Checking that file for you..."
        elif "write" in t or "save" in t:
            return "Writing that down now..."
        elif "launch" in t or "open" in t:
            return "Opening that up..."
        elif "calc" in t:
            return "Running that calculation..."
        elif "query" in t:
            return "Checking my systems..."
        elif "fetch" in t or "web" in t:
            return "Looking that up online..."
        elif "skill" in t:
            return "Executing that procedure..."
        return "On it, working on that now..."

    def _stream_llm_speech(
        self,
        trace: TurnTrace,
        user_msg: str,
        decision_id: str | None,
        messages: list[ChatMessage] | None = None,
        current_audio_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        tools: list[object] | None = None,
        max_rounds: int = 3,
        epistemic_context: str | None = None,
    ) -> None:
        """
        Executes streaming LLM response generation with multi-step tool re-prompting
        and verbal thinking cues (Proposals I, J & D-BRAIN-03).
        """
        self._maybe_speak_pending_updates(trace)

        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        self._publish_bus(begin_env)

        chunk_index = 0
        chunker = StreamingChunker()
        first_token_seen = False
        full_response_text: list[str] = []
        tool_messages: list[ChatMessage] = []
        tool_receipts: list[dict[str, JsonValue]] = []

        if tools is None:
            if self.execute_tools:
                active_rules = [r for r in self.rule_engine.rules.values() if r.status == "ACTIVE"]
                tools = get_all_tool_definitions(active_rules)
            else:
                tools = []

        # Seed session-scoped allowed URLs from conversation history & epistemic context
        history_urls: list[str] = []
        for h_msg in self.history:
            content_val = h_msg.get("content", "")
            if content_val:
                history_urls.extend(re.findall(r"https?://[^\s<>\"'()]+", content_val))
        if epistemic_context:
            history_urls.extend(re.findall(r"https?://[^\s<>\"'()]+", epistemic_context))
        # If user query references local dev or ports, seed localhost into allowed URLs
        local_cues = ("localhost", "127.0.0.1", "ollama", "port", "api server")
        if user_msg and any(w in user_msg.lower() for w in local_cues):
            history_urls.extend(["http://localhost", "http://127.0.0.1"])
        if history_urls and hasattr(self.output_supervisor, "register_allowed_urls"):
            self.output_supervisor.register_allowed_urls(history_urls)

        def _trigger_supervisor_abort(
            reason_msg: str, offending_chunk: str, breach_type: str | None = None
        ) -> None:
            nonlocal chunk_index
            logger.warning(
                "output_supervisor_tier1_abort",
                reason=reason_msg,
                chunk=offending_chunk,
                breach_type=breach_type,
                trace_id=trace.trace_id,
            )
            trace.interrupted = True
            self.play_ring.set_flag(FLAG_ABORT)
            # Drain queued TTS chunks
            while not self._tts_queue.empty():
                try:
                    self._tts_queue.get_nowait()
                except queue.Empty:
                    break
            is_citation_breach = (
                breach_type == "ungrounded_citation"
                or "ungrounded" in reason_msg.lower()
                or "citation" in reason_msg.lower()
            )
            if is_citation_breach:
                refusal = (
                    "I apologize, but I do not have a verified source for "
                    "that citation and won't guess."
                )
            else:
                refusal = "I cannot fulfill that request as it violates core safety invariants."
            self._publish_caption(refusal, source="assistant", is_final=True)
            self._speak_text(trace, refusal)
            self.history.append({"role": "user", "content": user_msg})
            self.history.append({"role": "assistant", "content": refusal})

        current_stance = self.affect_tracker.get_prompt_suffix_tag()

        try:
            for round_num in range(1, max_rounds + 1):
                if trace.interrupted:
                    break

                round_tool_called = False
                print(f"[Lucca R{round_num}] " if round_num > 1 else "[Lucca] ", end="", flush=True)
                if round_num == 1:
                    trace.t_llm_sent = now_ns()

                # Forced Final Synthesis: on final round, strip tools so LLM synthesizes response
                round_tools = tools if round_num < max_rounds else []

                for event in self.llm.stream_turn(
                    current_audio_b64=current_audio_b64 if round_num == 1 else None,
                    current_text=current_text or user_msg,
                    history=self.history,
                    memories=memories,
                    tools=round_tools,
                    messages=messages,
                    tool_messages=tool_messages if tool_messages else None,
                    trace_id=trace.trace_id,
                    epistemic_context=epistemic_context,
                    stance_tag=current_stance,
                ):
                    if trace.interrupted:
                        break

                    if isinstance(event, TokenDelta) and event.delta:
                        if not first_token_seen:
                            first_token_seen = True
                            trace.t_llm_first_token = now_ns()

                        trace.tokens_out += 1
                        full_response_text.append(event.delta)
                        print(event.delta, end="", flush=True)

                        accumulated = "".join(full_response_text)
                        self._publish_caption(accumulated, source="assistant", is_final=False)

                        for chunk in chunker.feed(event.delta):
                            if trace.interrupted:
                                break

                            eval_text = (
                                chunk.raw_text if getattr(chunk, "raw_text", None) else chunk.text
                            )
                            emitted_chunks, should_abort = self.output_supervisor.feed_chunk(
                                chunk, eval_text, verified_receipts=tool_receipts
                            )
                            if should_abort:
                                _trigger_supervisor_abort(
                                    "Tier 1 Capitulation/Provenance breach", eval_text
                                )
                                break

                            for em_chunk, _em_gate in emitted_chunks:
                                clean_chunk_text = sanitize_for_voice(em_chunk.text)
                                if not clean_chunk_text:
                                    continue
                                if chunk_index == 0:
                                    trace.t_first_chunk = now_ns()
                                    self._set_state("speaking")

                                try:
                                    self._tts_queue.put(
                                        (trace, em_chunk.chunk_id, clean_chunk_text, None),
                                        timeout=2.0,
                                    )
                                except queue.Full:
                                    logger.warning(
                                        "tts_queue_full_drop_chunk",
                                        chunk_id=em_chunk.chunk_id,
                                    )
                                chunk_index += 1

                    elif isinstance(event, ToolCallEnd):
                        round_tool_called = True
                        call_id = event.call.call_id
                        tool_name = event.call.tool
                        tool_args = dict(event.call.args)

                        # Speculative BDI Validation (Milestone 4)
                        bdi_res = self.bdi_validator.validate_tool_call(
                            tool_name,
                            tool_args,
                            taint_flags=getattr(self.sandbox, "taint_flags", 0),
                        )
                        if not bdi_res.is_valid:
                            logger.warning(
                                "speculative_bdi_call_rejected",
                                tool=tool_name,
                                reason=bdi_res.reason,
                                elapsed_us=bdi_res.elapsed_us,
                            )
                            content_str = (
                                f"Speculative Invariant Violation: {bdi_res.reason}. "
                                "Action prohibited."
                            )
                            tool_messages.append(
                                ChatMessage(
                                    role="assistant",
                                    content=f"Call tool {tool_name}",
                                    tool_call_id=call_id,
                                )
                            )
                            tool_messages.append(
                                ChatMessage(
                                    role="tool",
                                    content=content_str,
                                    tool_call_id=call_id,
                                    name=tool_name,
                                )
                            )
                            continue

                        # Emit verbal thinking cue before tool execution (Proposal I)
                        cue = self._select_verbal_cue(tool_name)
                        print(f'\n[Lucca Cue] 💬 "{cue}"', flush=True)
                        self._speak_text(trace, cue)

                        # Execute tool
                        tool_res = self._handle_tool_call(trace, tool_name, tool_args, speak=False)

                        if tool_res is not None:
                            if tool_res.ok:
                                tool_target = str(
                                    tool_args.get("path")
                                    or tool_args.get("filename")
                                    or tool_args.get("target")
                                    or tool_args.get("command")
                                    or tool_args.get("app_name")
                                    or tool_args.get("url")
                                    or ""
                                )
                                tool_receipts.append({"action": tool_name, "target": tool_target})

                                # Register allowed URLs from search, fetch, or browse results
                                if tool_name == "search_web" and getattr(
                                    tool_res, "structured", None
                                ):
                                    search_urls: list[str] = []
                                    for s_item in tool_res.structured.get("results", []):
                                        if s_item.get("url"):
                                            search_urls.append(s_item["url"])
                                    if tool_res.content:
                                        search_urls.extend(
                                            re.findall(r"https?://[^\s<>\"'()]+", tool_res.content)
                                        )
                                    if hasattr(self.output_supervisor, "register_allowed_urls"):
                                        self.output_supervisor.register_allowed_urls(search_urls)
                                elif tool_name in ("fetch_url", "browse_page"):
                                    target_u = tool_args.get("url")
                                    to_register: list[str] = []
                                    if target_u:
                                        to_register.append(target_u)
                                    if getattr(tool_res, "structured", None):
                                        if tool_res.structured.get("url"):
                                            to_register.append(tool_res.structured["url"])
                                        if tool_res.structured.get("embedded_links"):
                                            to_register.extend(
                                                tool_res.structured["embedded_links"]
                                            )
                                    if to_register and hasattr(
                                        self.output_supervisor, "register_allowed_urls"
                                    ):
                                        self.output_supervisor.register_allowed_urls(to_register)

                            if tool_res.content:
                                content_str = str(tool_res.content)
                            elif tool_res.structured:
                                content_str = json.dumps(tool_res.structured)
                            elif tool_res.stderr and not tool_res.ok:
                                content_str = f"Error: {tool_res.stderr}"
                            else:
                                content_str = "Success"
                        else:
                            content_str = "Action completed."

                        tool_messages.append(
                            ChatMessage(
                                role="assistant",
                                content=f"Call tool {tool_name}",
                                tool_call_id=call_id,
                            )
                        )
                        tool_messages.append(
                            ChatMessage(
                                role="tool",
                                content=content_str,
                                tool_call_id=call_id,
                                name=tool_name,
                            )
                        )

                if not round_tool_called:
                    # Anti-stalling check:
                    # If the model evaded research by outputting a rhetorical question
                    if (
                        round_num < max_rounds
                        and tools
                        and getattr(self.output_supervisor, "turn_has_stalled", False)
                    ):
                        logger.info(
                            "stalling_research_question_intercepted_forcing_tool_execution",
                            round_num=round_num,
                        )
                        tool_messages.append(
                            ChatMessage(
                                role="user",
                                content=(
                                    "[Autonomous Research Directive: Do not ask rhetorical "
                                    "permission questions or request clarification. "
                                    "Execute search_web or fetch_url immediately "
                                    "to retrieve and present the verified facts.]"
                                ),
                            )
                        )
                        self.output_supervisor.turn_has_stalled = False
                        continue
                    break

            # Flush remaining chunker text
            if not trace.interrupted:
                for chunk in chunker.flush():
                    if trace.interrupted:
                        break
                    eval_text = chunk.raw_text if getattr(chunk, "raw_text", None) else chunk.text
                    emitted_chunks, should_abort = self.output_supervisor.feed_chunk(
                        chunk, eval_text, verified_receipts=tool_receipts
                    )
                    if should_abort:
                        _trigger_supervisor_abort(
                            "Tier 1 Capitulation/Provenance breach on flush", eval_text
                        )
                        break

                    for em_chunk, _em_gate in emitted_chunks:
                        clean_chunk_text = sanitize_for_voice(em_chunk.text)
                        if not clean_chunk_text:
                            continue
                        if chunk_index == 0:
                            trace.t_first_chunk = now_ns()
                            self._set_state("speaking")
                        try:
                            self._tts_queue.put(
                                (trace, em_chunk.chunk_id, clean_chunk_text, None), timeout=2.0
                            )
                        except queue.Full:
                            logger.warning("tts_queue_full_drop_chunk", chunk_id=em_chunk.chunk_id)
                        chunk_index += 1

                # Final flush of output supervisor lookahead buffer
                if not trace.interrupted:
                    emitted_final, should_abort = self.output_supervisor.flush()
                    if should_abort:
                        _trigger_supervisor_abort("Tier 1 Capitulation unrefuted end-of-stream", "")
                    else:
                        for em_chunk, _em_gate in emitted_final:
                            clean_final_text = sanitize_for_voice(em_chunk.text)
                            if not clean_final_text:
                                continue
                            if chunk_index == 0:
                                trace.t_first_chunk = now_ns()
                                self._set_state("speaking")
                            try:
                                self._tts_queue.put(
                                    (trace, em_chunk.chunk_id, clean_final_text, None), timeout=2.0
                                )
                            except queue.Full:
                                logger.warning(
                                    "tts_queue_full_drop_chunk", chunk_id=em_chunk.chunk_id
                                )
                            chunk_index += 1

                if chunk_index > 0 and not trace.interrupted:
                    done_event = threading.Event()
                    try:
                        self._tts_queue.put((trace, -1, "", done_event), timeout=1.0)
                        done_event.wait(timeout=3.0)
                    except queue.Full:
                        logger.warning("tts_queue_full_sentinel_failed")

                if not trace.interrupted:
                    self.play_ring.set_flag(FLAG_EOS)

            trace.t_llm_done = now_ns()
            print("\n", flush=True)

            # If no streaming response was generated but a tool was executed without narration,
            # speak the tool result as fallback so the turn produces audio feedback and history
            if not full_response_text and self._last_unspoken_tool_msg and not trace.interrupted:
                self._speak_text(trace, self._last_unspoken_tool_msg)
                self.current_turn_tool_spoken.append(self._last_unspoken_tool_msg)
                self._publish_caption(
                    self._last_unspoken_tool_msg, source="assistant", is_final=True
                )
                self.play_ring.set_flag(FLAG_EOS)

            # Record turn in history
            if not trace.interrupted:
                reply_parts: list[str] = []
                if full_response_text:
                    reply_parts.append("".join(full_response_text))
                if self.current_turn_tool_spoken:
                    reply_parts.extend(self.current_turn_tool_spoken)
                if reply_parts:
                    reply_str = " ".join(reply_parts)
                    self.history.append({"role": "user", "content": user_msg})
                    self.history.append({"role": "assistant", "content": reply_str})
                    self.current_turn_assistant_reply = reply_str
                    if full_response_text:
                        self._publish_caption(reply_str, source="assistant", is_final=True)

        except Exception as exc:  # noqa: BLE001
            trace.error = str(exc)
            if not trace.interrupted:
                logger.error("turn_execution_error", trace_id=trace.trace_id, error=str(exc))
                print(f"\n[Error] {exc}", flush=True)
                self._publish_caption(
                    "Sorry, I had trouble processing that request.",
                    source="status",
                    is_final=True,
                )
            trace.interrupted = True
        finally:
            self._finalize_turn(trace, decision_id)

    def _run_turn(self, trace: TurnTrace, p: PTTReleasedPayload) -> None:
        self.sandbox.reset_turn()
        self.output_supervisor.reset_turn()
        self.play_ring.clear_flag(FLAG_ABORT)
        self.play_ring.clear_flag(FLAG_EOS)
        self.current_turn_tool_calls = []
        self.current_turn_receipts = []
        self.current_turn_tier = ExecutionTier.FULL_LOOP
        self.current_turn_tool_spoken = []
        self.current_turn_tool_ok = True
        self._last_unspoken_tool_msg = None
        decision_id: str | None = None

        # Read audio slice from capture ring
        pcm_samples = self.cap_ring.read_slice(p.capture_seq_start, p.capture_seq_end)

        # Empty PCM guard
        if len(pcm_samples) == 0:
            print("[PTT] 0 audio samples in capture ring; resetting to idle.\n", flush=True)
            self._publish_caption(
                "I didn't hear anything. (Hold Alt-Gr or Right-Ctrl while speaking)",
                source="status",
                is_final=True,
            )
            self._set_state("idle")
            return

        if trace.interrupted:
            return

        # Transcribe audio with ASR
        transcribed_text = ""
        eff_transcribed_text = ""
        spelling_hint: str | None = None
        if self.asr and len(pcm_samples) > 0:
            trace.t_asr_sent = now_ns()
            asr_res = self.asr.transcribe(pcm_samples)
            trace.t_asr_done = now_ns()
            transcribed_text = asr_res.text.strip()
            self.current_turn_transcript = transcribed_text

            # Detect spelled-word corrections (e.g. F-A-W-K-N-E-R -> Fawkner)
            normalized_text, detected_words = normalize_spelled_words(transcribed_text)
            self.active_detected_words = detected_words
            eff_transcribed_text = normalized_text
            if detected_words:
                all_corrupt: list[str] = []
                for w in detected_words:
                    c_vars = self._neutralize_context_attractors(w)
                    all_corrupt.extend(c_vars)
                w_str = ", ".join(f"'{w}'" for w in detected_words)
                if all_corrupt:
                    c_str = ", ".join(f"'{c}'" for c in sorted(set(all_corrupt)))
                    spelling_hint = (
                        f"[User Explicit Spelling Correction: The target entity is {w_str}. "
                        f"Disregard phonetically confused prior references to {c_str}. "
                        f"You must search for and reference {w_str} exactly.]"
                    )
                else:
                    spelling_hint = (
                        f"[User Explicit Spelling Correction: The target entity is spelled "
                        f"{w_str}. You must search for and reference {w_str} exactly.]"
                    )

        if trace.interrupted:
            return

        # Silence check: discard if low speech and no transcribed words
        if (p.vad_speech_ms < 100.0 or len(pcm_samples) < 1600) and not transcribed_text:
            self.current_turn_transcript = None
            print("[PTT] No speech detected.\n", flush=True)
            self._publish_caption(
                "I didn't hear anything. (Hold Alt-Gr or Right-Ctrl while speaking)",
                source="status",
                is_final=True,
            )
            self._set_state("idle")
            return

        if transcribed_text:
            print(f'\n[User] 🎙️ "{transcribed_text}"', flush=True)
            self._publish_caption(transcribed_text, source="user", is_final=True)
            self._publish_caption("Thinking... ⚙️", source="status", is_final=False)

        # Update label for previous turn if present
        eval_text = eff_transcribed_text or transcribed_text
        if self.prev_decision_record and self.db is not None:
            try:
                next_intent, next_conf, _ = self.router.classify_intent(eval_text)
                time_to_next = (time.time() - self.prev_turn_ts) if self.prev_turn_ts else None
                label, reason = derive_label(
                    self.prev_decision_record,
                    next_transcript=eval_text,
                    next_intent=next_intent,
                    next_intent_conf=next_conf,
                    time_to_next_turn_s=time_to_next,
                )
                persist_decision_label(
                    self.db, self.prev_decision_record.decision_id, label, reason
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("prev_decision_label_error", error=str(e))

        # Build RuleState and evaluate rules
        mode: Literal["audio", "transcript"] = (
            "transcript" if self.config.llm.mode == "transcript" else "audio"
        )
        rule_state = self._build_rule_state(eval_text, mode=mode)
        yielded_context: dict[str, object] | None = None
        shadow_outcomes: list[RuleOutcome] = []
        active_outcomes: list[RuleOutcome] = []
        try:
            shadow_outcomes = self.rule_engine.evaluate(rule_state, mode="shadow")
            active_outcomes = self.rule_engine.evaluate(rule_state, mode="active")
            self.current_turn_shadow_outcomes = shadow_outcomes
        except SchemeYieldSignal as e:
            logger.info("scheme_rule_yielded_to_core", reason=e.reason, context=e.context)
            yielded_context = {"reason": e.reason, "context": e.context}
        except SchemeInterruptSignal as e:
            logger.warning("scheme_rule_interrupted_core", reason=e.reason)
            self._abort_turn()
            self._speak_text(trace, f"Interrupted: {e.reason}")
            self._finalize_turn(trace, None)
            return

        any_quarantine_fired = any(o.fired for o in shadow_outcomes)
        any_active_fired = any(o.fired for o in active_outcomes)
        has_registered_rule = any(r.status == "ACTIVE" for r in self.rule_engine.rules.values())

        # Route decision
        route_decision = None
        try:
            vad_ms = int(p.vad_speech_ms)
            route_decision = self.router.route(
                transcript=transcribed_text,
                any_active_rule_fired=any_active_fired,
                any_quarantine_rule_fired=any_quarantine_fired,
                vad_speech_ms=vad_ms,
                trace_id=trace.trace_id,
                session_id=trace.trace_id,
                hour_local=rule_state.hour_local,
                weekday=rule_state.weekday,
                session_turns=rule_state.session_turns,
                mode=mode,
                has_registered_rule=has_registered_rule,
            )
            decision_id = (
                self.router.last_decision_record.decision_id
                if self.router.last_decision_record
                else None
            )
        except Exception as e:  # noqa: BLE001
            logger.error("router_execution_error", error=str(e))
        trace.t_route_done = now_ns()

        if route_decision and route_decision.action == RouteAction.RULE:
            winning_outcome: RuleOutcome | None = None
            for outcome in active_outcomes:
                if outcome.fired and not outcome.errored and outcome.plan is not None:
                    winning_outcome = outcome
                    break

            tier = getattr(route_decision, "tier", ExecutionTier.ACT_THEN_NARRATE)
            self.current_turn_tier = tier
            if tier == ExecutionTier.REFLEX:
                try:
                    if winning_outcome and winning_outcome.plan:
                        tool_executions: list[str] = []
                        for action in winning_outcome.plan.actions:
                            if isinstance(action, Say):
                                self._speak_text(trace, action.text)
                                self._publish_caption(
                                    action.text, source="assistant", is_final=True
                                )
                            elif isinstance(action, ToolCall):
                                tool_res = self._handle_tool_call(
                                    trace, action.tool, dict(action.args), speak=True
                                )
                                status = (
                                    "ok"
                                    if (tool_res is None or getattr(tool_res, "ok", True))
                                    else "failed"
                                )
                                args_str = ", ".join(f"{k}={v!r}" for k, v in action.args.items())
                                tool_executions.append(
                                    f"[Executed {action.tool}({args_str}) -> {status}]"
                                )

                        self.rule_engine.emit_execution_triple(
                            rule_id=winning_outcome.rule_id,
                            plan=winning_outcome.plan,
                            signal="tool_exit_zero",
                            detail="REFLEX execution",
                        )

                        user_msg = transcribed_text or "[Voice audio]"
                        spoken_msg = " ".join(
                            a.text for a in winning_outcome.plan.actions if isinstance(a, Say)
                        )
                        exec_details = " ".join(tool_executions)
                        assistant_msg = (
                            f"{spoken_msg} {exec_details}".strip()
                            if spoken_msg
                            else (exec_details or f"[Rule executed: {winning_outcome.rule_id}]")
                        )
                        self.history.append({"role": "user", "content": user_msg})
                        self.history.append({"role": "assistant", "content": assistant_msg})
                        self.play_ring.set_flag(FLAG_EOS)
                    else:
                        # Built-in Emergency Reflex Fallback (<150ms halt)
                        self._abort_turn()
                        lower_t = (transcribed_text or "").lower()
                        if any(w in lower_t for w in ("shut down", "turn off", "exit", "quit")):
                            ack_msg = "Shutting down."
                            self.on_quit_requested()
                        elif "pause" in lower_t:
                            ack_msg = "Paused."
                        elif "mute" in lower_t:
                            ack_msg = "Muted."
                        else:
                            ack_msg = "Stopped."

                        self._speak_text(trace, ack_msg)
                        self._publish_caption(ack_msg, source="assistant", is_final=True)
                        user_msg = transcribed_text or "[Voice audio]"
                        self.history.append({"role": "user", "content": user_msg})
                        self.history.append(
                            {"role": "assistant", "content": f"[Emergency Reflex: {ack_msg}]"}
                        )
                        self.play_ring.set_flag(FLAG_EOS)
                finally:
                    self._finalize_turn(trace, decision_id)
                return
            elif winning_outcome and winning_outcome.plan:
                # ACT_THEN_NARRATE (Proposal B / D-ARCH-05)
                try:
                    last_tool_res: ToolResult | None = None
                    last_tool_name: str = ""
                    last_tool_args: dict[str, JsonValue] = {}
                    for action in winning_outcome.plan.actions:
                        if isinstance(action, ToolCall):
                            tool_res = self._handle_tool_call(
                                trace, action.tool, dict(action.args), speak=False
                            )
                            last_tool_res = tool_res
                            last_tool_name = action.tool
                            last_tool_args = dict(action.args)

                    signal: Literal["tool_exit_zero", "pydantic_valid"] = (
                        "tool_exit_zero"
                        if (last_tool_res is None or getattr(last_tool_res, "ok", True))
                        else "pydantic_valid"
                    )
                    self.rule_engine.emit_execution_triple(
                        rule_id=winning_outcome.rule_id,
                        plan=winning_outcome.plan,
                        signal=signal,
                        detail="ACT_THEN_NARRATE execution",
                    )

                    mem_hits = self._search_memories(transcribed_text) if transcribed_text else []
                    narration_msgs = build_narration_messages(
                        tool_name=last_tool_name or winning_outcome.rule_id,
                        tool_args=last_tool_args,
                        tool_result=last_tool_res,
                        user_text=transcribed_text,
                        memories=mem_hits,
                        stance_tag=self.affect_tracker.get_prompt_suffix_tag(),
                    )
                    self._stream_llm_speech(
                        trace=trace,
                        user_msg=transcribed_text or "[Voice audio]",
                        decision_id=decision_id,
                        messages=narration_msgs,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error("act_then_narrate_error", error=str(e))
                    self._finalize_turn(trace, decision_id)
                return

        # Encode to WAV bytes
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.config.audio.capture_rate)
            wf.writeframes(pcm_samples.tobytes())
        wav_b64 = base64.b64encode(wav_buf.getvalue()).decode("utf-8")

        llm_audio = wav_b64 if self.config.llm.mode == "audio" else None
        is_trans_mode = self.config.llm.mode == "transcript"
        llm_text = transcribed_text if (is_trans_mode or not llm_audio) else None
        mem_hits = self._search_memories(transcribed_text) if transcribed_text else []
        epistemic_ctx: str | None = None
        if transcribed_text:
            is_epistemic, target_subs, topic = self.cascade.classify_intent(transcribed_text)
            if is_epistemic:
                is_file_or_web = any(
                    s in target_subs for s in (EpistemicSubstrate.WORKSPACE, EpistemicSubstrate.WEB)
                )
                if is_file_or_web:
                    cue = self.cascade.select_floor_cue(transcribed_text, target_subs[0])
                    self._speak_text(trace, cue)
                    self._publish_caption(cue, source="assistant", is_final=False)
                cascade_res = self.cascade.query(
                    transcribed_text, substrates=target_subs, emit_floor_cue=False
                )
                epistemic_ctx = cascade_res.synthesized_context or None

        if yielded_context:
            yield_str = f"[Cognitive Bus Yield: {yielded_context['reason']}]"
            epistemic_ctx = f"{epistemic_ctx}\n{yield_str}" if epistemic_ctx else yield_str

        if spelling_hint:
            epistemic_ctx = f"{epistemic_ctx}\n{spelling_hint}" if epistemic_ctx else spelling_hint

        # Intent-based tool gating for voice turn
        turn_tools: list[object] | None = None
        intent = rule_state.intent if hasattr(rule_state, "intent") else "unknown"
        TOOLLESS_INTENTS = {"dangerous"}

        is_follow_up = False
        text_for_gate = (
            eff_transcribed_text if "eff_transcribed_text" in locals() else transcribed_text
        ) or transcribed_text
        if text_for_gate:
            u_low = text_for_gate.lower()
            follow_up_patterns = (
                "tell me more",
                "more about",
                "what else",
                "who is",
                "what about",
                "are you sure",
                "what are your sources",
                "cite your sources",
                "where did you get that",
                "all of this is wrong",
                "elaborate",
                "yes",
                "yeah",
                "yep",
                "sure",
                "okay",
                "ok",
                "do it",
                "please do",
                "go ahead",
                "where is",
                "where was",
                "where are",
                "who was",
                "facts about",
                "how about",
                "spelled",
                "spelling",
                "search",
            )
            is_follow_up = any(p in u_low for p in follow_up_patterns)
            if not is_follow_up and self.history:
                last_asst = next(
                    (
                        m.get("content", "")
                        for m in reversed(self.history)
                        if m.get("role") == "assistant"
                    ),
                    "",
                )
                search_cues = ("search", "found", "look", "judge", "suburb", "results", "?")
                if any(w in last_asst.lower() for w in search_cues):
                    is_follow_up = True

        if intent in TOOLLESS_INTENTS or (intent == "chit_chat" and not is_follow_up):
            turn_tools = []
            logger.info(
                "tool_gating_suppressed",
                intent=intent,
                reason="conversational or dangerous intent — tools withheld",
            )

        self._stream_llm_speech(
            trace=trace,
            user_msg=transcribed_text or "[Voice audio]",
            decision_id=decision_id,
            current_audio_b64=llm_audio,
            current_text=llm_text,
            memories=mem_hits,
            epistemic_context=epistemic_ctx,
            tools=turn_tools,
        )

    def _run_text_turn(self, trace: TurnTrace, user_text: str) -> None:
        self.sandbox.reset_turn()
        self.output_supervisor.reset_turn()
        self.play_ring.clear_flag(FLAG_ABORT)
        self.play_ring.clear_flag(FLAG_EOS)
        self.current_turn_tool_calls = []
        self.current_turn_receipts = []
        self.current_turn_tier = ExecutionTier.FULL_LOOP
        self.current_turn_tool_spoken = []
        self.current_turn_tool_ok = True
        self._last_unspoken_tool_msg = None
        self.current_turn_transcript = user_text
        decision_id: str | None = None

        # Step 1: Detect spelled-word corrections (e.g. F-A-W-K-N-E-R -> Fawkner)
        normalized_text, detected_words = normalize_spelled_words(user_text)
        self.active_detected_words = detected_words
        eff_user_text = normalized_text
        spelling_hint: str | None = None
        if detected_words:
            all_corrupt: list[str] = []
            for w in detected_words:
                c_vars = self._neutralize_context_attractors(w)
                all_corrupt.extend(c_vars)
            w_str = ", ".join(f"'{w}'" for w in detected_words)
            if all_corrupt:
                c_str = ", ".join(f"'{c}'" for c in sorted(set(all_corrupt)))
                spelling_hint = (
                    f"[User Explicit Spelling Correction: The target entity is {w_str}. "
                    f"Disregard phonetically confused prior references to {c_str}. "
                    f"You must search for and reference {w_str} exactly.]"
                )
            else:
                spelling_hint = (
                    f"[User Explicit Spelling Correction: The target entity is spelled {w_str}. "
                    f"You must search for and reference {w_str} exactly.]"
                )

        eval_user_text = eff_user_text or user_text
        # Update label for previous turn if present
        if self.prev_decision_record and self.db is not None:
            try:
                next_intent, next_conf, _ = self.router.classify_intent(eval_user_text)
                time_to_next = (time.time() - self.prev_turn_ts) if self.prev_turn_ts else None
                label, reason = derive_label(
                    self.prev_decision_record,
                    next_transcript=eval_user_text,
                    next_intent=next_intent,
                    next_intent_conf=next_conf,
                    time_to_next_turn_s=time_to_next,
                )
                persist_decision_label(
                    self.db, self.prev_decision_record.decision_id, label, reason
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("prev_decision_label_error", error=str(e))

        # Build RuleState and evaluate rules
        rule_state = self._build_rule_state(eval_user_text, mode="transcript")
        yielded_context: dict[str, object] | None = None
        shadow_outcomes: list[RuleOutcome] = []
        active_outcomes: list[RuleOutcome] = []
        try:
            shadow_outcomes = self.rule_engine.evaluate(rule_state, mode="shadow")
            active_outcomes = self.rule_engine.evaluate(rule_state, mode="active")
            self.current_turn_shadow_outcomes = shadow_outcomes
        except SchemeYieldSignal as e:
            logger.info("scheme_rule_yielded_to_core", reason=e.reason, context=e.context)
            yielded_context = {"reason": e.reason, "context": e.context}
        except SchemeInterruptSignal as e:
            logger.warning("scheme_rule_interrupted_core", reason=e.reason)
            self._abort_turn()
            self._speak_text(trace, f"Interrupted: {e.reason}")
            self._finalize_turn(trace, None)
            return

        any_quarantine_fired = any(o.fired for o in shadow_outcomes)
        any_active_fired = any(o.fired for o in active_outcomes)
        has_registered_rule = any(r.status == "ACTIVE" for r in self.rule_engine.rules.values())

        # Route decision
        route_decision = None
        try:
            route_decision = self.router.route(
                transcript=user_text,
                any_active_rule_fired=any_active_fired,
                any_quarantine_rule_fired=any_quarantine_fired,
                vad_speech_ms=1000,
                trace_id=trace.trace_id,
                session_id=trace.trace_id,
                hour_local=rule_state.hour_local,
                weekday=rule_state.weekday,
                session_turns=rule_state.session_turns,
                mode="transcript",
                has_registered_rule=has_registered_rule,
            )
            decision_id = (
                self.router.last_decision_record.decision_id
                if self.router.last_decision_record
                else None
            )
        except Exception as e:  # noqa: BLE001
            logger.error("router_execution_error", error=str(e))
        trace.t_route_done = now_ns()

        if route_decision and route_decision.action == RouteAction.RULE:
            winning_outcome: RuleOutcome | None = None
            for outcome in active_outcomes:
                if outcome.fired and not outcome.errored and outcome.plan is not None:
                    winning_outcome = outcome
                    break

            tier = getattr(route_decision, "tier", ExecutionTier.ACT_THEN_NARRATE)
            self.current_turn_tier = tier
            if tier == ExecutionTier.REFLEX:
                try:
                    if winning_outcome and winning_outcome.plan:
                        tool_executions: list[str] = []
                        for action in winning_outcome.plan.actions:
                            if isinstance(action, Say):
                                self._speak_text(trace, action.text)
                                self._publish_caption(
                                    action.text, source="assistant", is_final=True
                                )
                            elif isinstance(action, ToolCall):
                                tool_res = self._handle_tool_call(
                                    trace, action.tool, dict(action.args), speak=True
                                )
                                status = (
                                    "ok"
                                    if (tool_res is None or getattr(tool_res, "ok", True))
                                    else "failed"
                                )
                                args_str = ", ".join(f"{k}={v!r}" for k, v in action.args.items())
                                tool_executions.append(
                                    f"[Executed {action.tool}({args_str}) -> {status}]"
                                )

                        user_msg = user_text
                        spoken_msg = " ".join(
                            a.text for a in winning_outcome.plan.actions if isinstance(a, Say)
                        )
                        exec_details = " ".join(tool_executions)
                        assistant_msg = (
                            f"{spoken_msg} {exec_details}".strip()
                            if spoken_msg
                            else (exec_details or f"[Rule executed: {winning_outcome.rule_id}]")
                        )
                        self.history.append({"role": "user", "content": user_msg})
                        self.history.append({"role": "assistant", "content": assistant_msg})
                        self.play_ring.set_flag(FLAG_EOS)
                    else:
                        # Built-in Emergency Reflex Fallback (<150ms halt)
                        self._abort_turn()
                        lower_t = user_text.lower()
                        if any(w in lower_t for w in ("shut down", "turn off", "exit", "quit")):
                            ack_msg = "Shutting down."
                            self.on_quit_requested()
                        elif "pause" in lower_t:
                            ack_msg = "Paused."
                        elif "mute" in lower_t:
                            ack_msg = "Muted."
                        else:
                            ack_msg = "Stopped."

                        self._speak_text(trace, ack_msg)
                        self._publish_caption(ack_msg, source="assistant", is_final=True)
                        self.history.append({"role": "user", "content": user_text})
                        self.history.append(
                            {"role": "assistant", "content": f"[Emergency Reflex: {ack_msg}]"}
                        )
                        self.play_ring.set_flag(FLAG_EOS)
                finally:
                    self._finalize_turn(trace, decision_id)
                return
            elif winning_outcome and winning_outcome.plan:
                # ACT_THEN_NARRATE (Proposal B / D-ARCH-05)
                try:
                    last_tool_res: ToolResult | None = None
                    last_tool_name: str = ""
                    last_tool_args: dict[str, JsonValue] = {}
                    for action in winning_outcome.plan.actions:
                        if isinstance(action, ToolCall):
                            tool_res = self._handle_tool_call(
                                trace, action.tool, dict(action.args), speak=False
                            )
                            last_tool_res = tool_res
                            last_tool_name = action.tool
                            last_tool_args = dict(action.args)

                    mem_hits = self._search_memories(user_text) if user_text else []
                    narration_msgs = build_narration_messages(
                        tool_name=last_tool_name or winning_outcome.rule_id,
                        tool_args=last_tool_args,
                        tool_result=last_tool_res,
                        user_text=user_text,
                        memories=mem_hits,
                        stance_tag=self.affect_tracker.get_prompt_suffix_tag(),
                    )
                    self._stream_llm_speech(
                        trace=trace,
                        user_msg=user_text,
                        decision_id=decision_id,
                        messages=narration_msgs,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error("act_then_narrate_error", error=str(e))
                    self._finalize_turn(trace, decision_id)
                return

        mem_hits = self._search_memories(user_text) if user_text else []
        epistemic_ctx: str | None = None
        if user_text:
            is_epistemic, target_subs, topic = self.cascade.classify_intent(user_text)
            if is_epistemic:
                cascade_res = self.cascade.query(
                    user_text, substrates=target_subs, emit_floor_cue=False
                )
                epistemic_ctx = cascade_res.synthesized_context or None

        if yielded_context:
            yield_str = f"[Cognitive Bus Yield: {yielded_context['reason']}]"
            epistemic_ctx = f"{epistemic_ctx}\n{yield_str}" if epistemic_ctx else yield_str

        if spelling_hint:
            epistemic_ctx = f"{epistemic_ctx}\n{spelling_hint}" if epistemic_ctx else spelling_hint

        # Intent-based tool gating — suppress tools ONLY for dangerous or pure chit-chat
        turn_tools: list[object] | None = None  # None = let _stream_llm_speech decide
        intent = rule_state.intent if hasattr(rule_state, "intent") else "unknown"
        TOOLLESS_INTENTS = {"dangerous"}

        # Do not suppress tools if the user is asking follow-up factual questions
        is_follow_up = False
        text_for_gate = eval_user_text or user_text
        if text_for_gate:
            u_low = text_for_gate.lower()
            follow_up_patterns = (
                "tell me more",
                "more about",
                "what else",
                "who is",
                "what about",
                "are you sure",
                "what are your sources",
                "cite your sources",
                "where did you get that",
                "all of this is wrong",
                "elaborate",
                "yes",
                "yeah",
                "yep",
                "sure",
                "okay",
                "ok",
                "do it",
                "please do",
                "go ahead",
                "where is",
                "where was",
                "where are",
                "who was",
                "facts about",
                "how about",
                "spelled",
                "spelling",
                "search",
            )
            is_follow_up = any(p in u_low for p in follow_up_patterns)
            if not is_follow_up and self.history:
                last_asst = next(
                    (
                        m.get("content", "")
                        for m in reversed(self.history)
                        if m.get("role") == "assistant"
                    ),
                    "",
                )
                search_cues = ("search", "found", "look", "judge", "suburb", "results", "?")
                if any(w in last_asst.lower() for w in search_cues):
                    is_follow_up = True

        if intent in TOOLLESS_INTENTS or (intent == "chit_chat" and not is_follow_up):
            turn_tools = []
            logger.info(
                "tool_gating_suppressed",
                intent=intent,
                reason="conversational or dangerous intent — tools withheld",
            )

        self._stream_llm_speech(
            trace=trace,
            user_msg=user_text,
            decision_id=decision_id,
            current_text=eval_user_text or user_text,
            memories=mem_hits,
            epistemic_context=epistemic_ctx,
            tools=turn_tools,
        )

    def _synthesize_chunk(self, trace: TurnTrace, chunk_id: int, text: str) -> None:
        if chunk_id == 0:
            trace.t_tts_first_sent = now_ns()

        speed_mult = self.affect_tracker.get_tts_speed_multiplier()
        try:
            _done = self.tts.synthesize(
                chunk_id=chunk_id,
                text=text,
                speed=speed_mult,
                is_first=(chunk_id == 0),
            )
        except TypeError:
            _done = self.tts.synthesize(
                chunk_id=chunk_id,
                text=text,
                is_first=(chunk_id == 0),
            )

        if chunk_id == 0:
            trace.t_tts_first_done = now_ns()
        trace.t_tts_last_done = now_ns()
        trace.chunks += 1

    def _tts_worker(self) -> None:
        """Background worker thread (core-tts) consuming chunks from _tts_queue."""
        while self._tts_running:
            try:
                item = self._tts_queue.get(timeout=0.2)
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
                    self._synthesize_chunk(trace, chunk_id, text)

                if done_event is not None:
                    done_event.set()
            except Exception as exc:  # noqa: BLE001
                logger.error("tts_worker_chunk_error", error=str(exc))
                if len(item) >= 4 and item[3] is not None:
                    item[3].set()

    def _speak_text(self, trace: TurnTrace, text: str) -> None:
        clean_text = sanitize_for_voice(text)
        if not clean_text:
            return
        self.play_ring.clear_flag(FLAG_ABORT)
        self.play_ring.clear_flag(FLAG_EOS)
        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        self._publish_bus(begin_env)
        self._set_state("speaking")
        self._publish_caption(clean_text, source="assistant", is_final=True)
        trace.t_tts_first_sent = now_ns()
        speed_mult = self.affect_tracker.get_tts_speed_multiplier()
        try:
            self.tts.synthesize(chunk_id=0, text=clean_text, speed=speed_mult, is_first=True)
        except TypeError:
            self.tts.synthesize(chunk_id=0, text=clean_text, is_first=True)
        trace.t_tts_first_done = now_ns()
        trace.t_tts_last_done = trace.t_tts_first_done
        trace.chunks += 1
        self.play_ring.set_flag(FLAG_EOS)

    def _describe_tool_action(self, name: str, args: dict[str, JsonValue]) -> str:
        if name == "launch_app":
            app = str(args.get("app_name", "the application"))
            return f"launch {app}"
        if name == "write_file":
            path = str(args.get("path", "the file"))
            return f"write to {path}"
        if name == "delete_file":
            path = str(args.get("path", "the file"))
            return f"delete {path}"
        if name == "run_python":
            return "run the python script"
        if name == "fetch_url":
            url = str(args.get("url", "the web page"))
            return f"fetch {url}"
        return f"execute {name}"

    def _request_confirmation(
        self,
        trace: TurnTrace,
        name: str,
        args: dict[str, JsonValue],
        timeout_s: float = 15.0,
    ) -> bool:
        action_desc = self._describe_tool_action(name, args)
        prompt_text = f"Do you want me to {action_desc}? Say yes or no."

        self._confirm_result = False
        self._confirm_event.clear()
        self._pending_confirmation_active = True
        with self._confirm_lock:
            self._confirm_audio = None
            self._confirm_via = None

        self._set_state("confirm_wait", detail=action_desc)

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
        self._publish_bus(confirm_env)

        # Speak prompt
        self._speak_text(trace, prompt_text)
        # Restore confirm_wait state in case TTS set it to speaking
        if self._pending_confirmation_active:
            self._set_state("confirm_wait", detail=action_desc)

        # Wait for user confirmation
        got_signal = self._confirm_event.wait(timeout=timeout_s)
        self._pending_confirmation_active = False

        if not got_signal:
            logger.info("confirmation_timeout", tool=name)
            return False

        with self._confirm_lock:
            confirm_audio = self._confirm_audio
            self._confirm_audio = None
            confirm_via = self._confirm_via

        if confirm_via == "voice" and confirm_audio is not None:
            # F-CORE-015: transcribe on this turn worker thread, outside the
            # ingest path. The slice is read late, so stale-window detection
            # (F-SENS-003) applies: an overwritten window yields an empty
            # transcript, which parses as "unknown" and cancels the action.
            pcm_samples = self.cap_ring.read_slice(
                confirm_audio.capture_seq_start, confirm_audio.capture_seq_end
            )
            transcript_text = ""
            if self.asr and len(pcm_samples) > 0:
                asr_res = self.asr.transcribe(pcm_samples)
                transcript_text = asr_res.text
            decision = parse_confirmation_response(transcript_text)
            # A click or barge-in may have superseded the voice answer while
            # ASR was running; the explicit user act always wins.
            with self._confirm_lock:
                superseded = self._confirm_via in ("click", "abort")
                final_result = self._confirm_result if superseded else decision == "confirm"
            if superseded:
                logger.info("voice_confirmation_superseded", via=self._confirm_via)
            else:
                logger.info("voice_confirmation_parsed", decision=decision)
            return final_result

        return self._confirm_result

    def _handle_tool_call(
        self,
        trace: TurnTrace,
        name: str,
        args: dict[str, JsonValue],
        speak: bool = True,
    ) -> ToolResult | None:
        self.executed_tools.append((name, args))
        call_id = str(ulid.ULID())
        self.current_turn_tool_calls.append(ToolCall(tool=name, args=dict(args), call_id=call_id))
        if not self.execute_tools:
            return None

        # Speculative BDI Invariant Validation (Milestone 4)
        bdi_validator = getattr(self, "bdi_validator", None)
        if bdi_validator is not None:
            bdi_res = bdi_validator.validate_tool_call(
                name,
                args,
                taint_flags=getattr(self.sandbox, "taint_flags", 0),
            )
            if not bdi_res.is_valid:
                logger.warning(
                    "bdi_invariant_violation",
                    tool=name,
                    reason=bdi_res.reason,
                    elapsed_us=bdi_res.elapsed_us,
                )
                self.current_turn_tool_ok = False
                affect_tracker = getattr(self, "affect_tracker", None)
                if affect_tracker is not None:
                    affect_tracker.record_signal(
                        AffectSignal.DEONTIC_REJECTION, custom_cause=bdi_res.reason
                    )
                self._record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=f"Speculative Invariant Violation: {bdi_res.reason}. Action prohibited.",
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-4,
                    stderr=f"Speculative Invariant Violation: {bdi_res.reason}. Action prohibited.",
                    elapsed_ms=bdi_res.elapsed_us / 1000.0,
                )

        # invoke_skill dispatch tool (T1.2)
        if name == "invoke_skill":
            skill_id = str(args.get("skill_id", ""))
            raw_skill_args = args.get("args")
            skill_args: dict[str, JsonValue] = (
                dict(raw_skill_args) if isinstance(raw_skill_args, dict) else {}
            )
            manifest_ids = getattr(self, "current_manifest_skill_ids", None)
            ok, reason, payload = dispatch_invoke_skill(
                skill_id=skill_id,
                args=skill_args,
                rule_engine=self.rule_engine,
                manifest_skill_ids=manifest_ids,
            )
            if not ok:
                self.current_turn_tool_ok = False
                self._record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=reason,
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=reason,
                    structured=payload,
                    elapsed_ms=0.0,
                )

            # Contract step 4: Execute the rule's plan through existing plan executor
            rule_entry = self.rule_engine.rules[skill_id]
            rule_state = self._build_rule_state(
                str(skill_args.get("query") or self.current_turn_transcript or "")
            )
            for k, v in skill_args.items():
                if k != "query" and isinstance(v, str):
                    rule_state.entities.setdefault(k, []).append(v)
            outcome = evaluate_plan(rule_entry.definition, rule_state)
            if outcome.plan:
                sub_results: list[str] = []
                for sub_action in outcome.plan.actions:
                    if isinstance(sub_action, ToolCall):
                        sub_res = self._handle_tool_call(
                            trace, sub_action.tool, dict(sub_action.args), speak=False
                        )
                        sub_status = (
                            "ok" if (sub_res is None or getattr(sub_res, "ok", True)) else "failed"
                        )
                        sub_results.append(f"{sub_action.tool}->{sub_status}")
                    elif isinstance(sub_action, Say) and speak:
                        self._speak_text(trace, sub_action.text)
                has_failures = any("->failed" in s for s in sub_results)
                skill_signal: Literal["tool_exit_zero", "pydantic_valid"] = (
                    "pydantic_valid" if has_failures else "tool_exit_zero"
                )
                self.rule_engine.emit_execution_triple(
                    rule_id=skill_id,
                    plan=outcome.plan,
                    signal=skill_signal,
                    detail=f"invoke_skill {', '.join(sub_results)}",
                )
                res_content = (
                    f"Skill '{skill_id}' fired. "
                    f"Rationale: {outcome.plan.rationale or 'completed'}. "
                    f"Actions: {', '.join(sub_results) or 'none'}"
                )
                self._record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=True,
                    output=res_content,
                    error=None,
                )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    content=res_content,
                    elapsed_ms=float(outcome.elapsed_us) / 1000.0,
                )
            else:
                err_msg = outcome.error or "conditions not met"
                self.current_turn_tool_ok = False
                self._record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=f"Skill '{skill_id}' evaluated but did not fire: {err_msg}",
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    stderr=f"Skill '{skill_id}' evaluated but did not fire: {err_msg}",
                    elapsed_ms=float(outcome.elapsed_us) / 1000.0,
                )

        # Check if this is a MicroScheme skill invocation (Proposal A / D-REAS-04)
        target_rule_id = None
        if name.startswith("skill_"):
            target_rule_id = name[6:].replace("_", "-")
        elif name in self.rule_engine.rules:
            target_rule_id = name

        if target_rule_id and target_rule_id in self.rule_engine.rules:
            rule_entry = self.rule_engine.rules[target_rule_id]
            rule_state = self._build_rule_state(
                str(args.get("query") or self.current_turn_transcript or "")
            )
            outcome = evaluate_rule(rule_entry.definition, rule_state)
            if outcome.plan:
                sub_results: list[str] = []
                for sub_action in outcome.plan.actions:
                    if isinstance(sub_action, ToolCall):
                        sub_res = self._handle_tool_call(
                            trace, sub_action.tool, dict(sub_action.args), speak=False
                        )
                        sub_status = (
                            "ok" if (sub_res is None or getattr(sub_res, "ok", True)) else "failed"
                        )
                        sub_results.append(f"{sub_action.tool}->{sub_status}")
                    elif isinstance(sub_action, Say) and speak:
                        self._speak_text(trace, sub_action.text)
                res = ToolResult(
                    call_id=call_id,
                    ok=True,
                    content=(
                        f"Skill '{target_rule_id}' fired. "
                        f"Rationale: {outcome.plan.rationale or 'completed'}. "
                        f"Actions: {', '.join(sub_results) or 'none'}"
                    ),
                    elapsed_ms=float(outcome.elapsed_us) / 1000.0,
                )
            else:
                err_msg = outcome.error or "conditions not met"
                res = ToolResult(
                    call_id=call_id,
                    ok=False,
                    stderr=f"Skill '{target_rule_id}' evaluated but did not fire: {err_msg}",
                    elapsed_ms=float(outcome.elapsed_us) / 1000.0,
                )
            if not res.ok:
                self.current_turn_tool_ok = False
            self._record_tool_receipt(
                name=name,
                call_id=call_id,
                args=args,
                ok=res.ok,
                output=res.content,
                error=res.stderr,
            )
            return res

        # Check confirmation requirement (WRITE / LAUNCH)
        if self.sandbox.check_confirmation_needed(name):
            confirmed = self._request_confirmation(trace, name, args)
            if not confirmed:
                logger.info("tool_execution_cancelled_by_user", tool=name)
                cancel_msg = "Cancelled."
                print(f"[Lucca] {cancel_msg}", flush=True)
                if speak:
                    self._speak_text(trace, cancel_msg)
                    self.current_turn_tool_spoken.append(cancel_msg)
                self.current_turn_tool_ok = False
                self._record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error="cancelled by user",
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-3,
                    stderr="cancelled by user",
                    elapsed_ms=0.0,
                )

        # Corrective Search Query Injection & Category Grounding
        if name == "search_web" and "query" in args and isinstance(args["query"], str):
            q = str(args["query"])
            detected = getattr(self, "active_detected_words", [])
            for target_w in detected:
                for tok in re.findall(r"\b[a-zA-Z]{3,}\b", q):
                    if (
                        tok.lower() != target_w.lower()
                        and _levenshtein_distance(tok.lower(), target_w.lower()) <= 2
                    ):
                        q = re.sub(rf"\b{re.escape(tok)}\b", target_w, q)
                if target_w.lower() not in q.lower():
                    q = f'"{target_w}" {q}'.strip()

            # Preserve category & location keywords from transcript or context if missing from query
            recent_ctx = " ".join(
                m.get("content", "") for m in self.history[-2:] if isinstance(m, dict)
            )
            context_text = f"{self.current_turn_transcript or ''} {recent_ctx}".lower()
            category_keywords = (
                "suburb",
                "judge",
                "court",
                "station",
                "school",
                "hospital",
                "city",
                "province",
                "victoria",
                "australia",
                "philippines",
                "manila",
            )
            for kw in category_keywords:
                if kw in context_text and kw not in q.lower():
                    q = f"{q} {kw}".strip()
            args["query"] = q

        res = self.sandbox.execute_tool(
            call_id=call_id,
            tool_name=name,
            args=args,
            confirmed=True,
        )
        affect_tracker = getattr(self, "affect_tracker", None)
        if not res.ok:
            self.current_turn_tool_ok = False
            if affect_tracker is not None:
                affect_tracker.record_signal(
                    AffectSignal.TOOL_FAILURE, custom_cause=res.stderr or f"{name} failed"
                )
        elif affect_tracker is not None:
            affect_tracker.record_signal(
                AffectSignal.TASK_SUCCESS, custom_cause=f"{name} completed successfully"
            )
        self._record_tool_receipt(
            name=name,
            call_id=call_id,
            args=args,
            ok=res.ok,
            output=res.content,
            error=res.stderr,
        )
        logger.info("tool_executed", tool=name, ok=res.ok, exit_code=res.exit_code)
        spoken_msg: str | None = None
        if res.ok:
            if name == "launch_app":
                app_name = str(args.get("app_name", "app"))
                spoken_msg = f"Launched {app_name}."
            elif name == "write_file":
                path = str(args.get("path", "file"))
                spoken_msg = f"Saved {path}."
            elif name == "delete_file":
                path = str(args.get("path", "file"))
                spoken_msg = f"Deleted {path}."
            elif name == "run_python":
                spoken_msg = "Python script executed."
            elif name == "query_capabilities":
                cat = str(args.get("category", "all")).lower()
                if cat in ("applications", "apps", "whitelisted_apps"):
                    spoken_msg = (
                        "I can launch desktop applications including Calculator, Notepad, and Edge."
                    )
                elif cat in ("hardware", "hardware_substrates"):
                    spoken_msg = (
                        "I run locally across an RTX 5080 dGPU, Intel AI Boost NPU, "
                        "and Core Ultra 9 CPU."
                    )
                elif cat in ("memory", "memory_subsystem"):
                    spoken_msg = (
                        "I have persistent episodic and semantic memory backed by "
                        "SQLite and vector embeddings."
                    )
                else:
                    spoken_msg = (
                        "I can launch desktop applications like Calculator, Notepad, and Edge, "
                        "read and write files in your workspace, and remember our conversations "
                        "with persistent memory."
                    )
            elif name == "read_file":
                path = str(args.get("path", "file"))
                content = str(res.content or "").strip()
                if 0 < len(content) <= 150:
                    spoken_msg = f"Here is what's in {path}: {content}"
                else:
                    spoken_msg = f"I read {path}."
            elif name == "fetch_url":
                url = str(args.get("url", "the page"))
                spoken_msg = f"I fetched {url}."
            else:
                spoken_msg = f"Executed {name}."
        elif res.exit_code == -2 or "sandbox unavailable" in (res.stderr or ""):
            spoken_msg = "My file sandbox isn't available — Docker isn't reachable."
        else:
            spoken_msg = f"Error: {res.stderr or 'action failed'}."

        if speak and spoken_msg:
            print(f"[Lucca] {spoken_msg}", flush=True)
            self._speak_text(trace, spoken_msg)
            self.current_turn_tool_spoken.append(spoken_msg)
        elif spoken_msg:
            self._last_unspoken_tool_msg = spoken_msg
        return res

    def _heartbeat_loop(self) -> None:
        while self.running:
            try:
                env = Envelope(
                    type="sys.ping",
                    trace_id="",
                    ts_ns=now_ns(),
                    src="core",
                    payload={},
                )
                self._publish_bus(env)
            except Exception as exc:  # noqa: BLE001
                logger.debug("heartbeat_ping_error", error=str(exc))
            time.sleep(2.0)

    def stop(self) -> None:
        self.running = False
        self._tts_running = False
        self._confirm_event.set()
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
            except queue.Empty:
                break
        try:
            self._tts_queue.put_nowait(None)
        except queue.Full:
            logger.debug("orchestrator_tts_queue_full_on_stop")
        if hasattr(self, "_tts_thread") and self._tts_thread.is_alive():
            self._tts_thread.join(timeout=1.0)
        if self.active_turn_thread and self.active_turn_thread.is_alive():
            t = self.active_turn_thread
            self._abort_turn()
            if t.is_alive():
                t.join(timeout=1.0)
        try:
            self.ctl_sock.close(linger=0)
            self.bus_sock.close(linger=0)
            self.ingest_sock.close(linger=0)
        except (zmq.ZMQError, OSError) as exc:
            logger.debug("orchestrator_stop_socket_close_error", error=str(exc))
        self.ctx.destroy(linger=0)
        try:
            self.cap_ring.unlink()
        except Exception as exc:  # noqa: BLE001
            logger.debug("orchestrator_unlink_cap_ring_error", error=str(exc))
        try:
            self.play_ring.unlink()
        except Exception as exc:  # noqa: BLE001
            logger.debug("orchestrator_unlink_play_ring_error", error=str(exc))
