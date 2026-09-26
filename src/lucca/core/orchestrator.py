"""
Project Lucca — Central Orchestrator & State Machine
Spec 01 §3, §4, §6, Spec 10, ADR-008
"""

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
from typing import Final, Literal

import structlog

logger = structlog.get_logger(__name__)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001, S110
        logger.debug("reconfigure_stdout_failed", error=str(exc))
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001, S110
        logger.debug("reconfigure_stderr_failed", error=str(exc))

import ulid
import zmq
from pydantic import JsonValue

from lucca.brain.chunker import StreamingChunker, sanitize_for_voice
from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import (
    get_all_tool_definitions,
    set_persona,
)
from lucca.core.affect import AffectSignal, AffectTracker
from lucca.core.bdi_validator import SpeculativeBDIValidator
from lucca.core.capabilities import dispatch_invoke_skill
from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.coherence import (
    ToolReceipt,
    detect_promised_action_claims,
    detect_ungrounded_action_claims,
)
from lucca.core.config import get_config, load_heuristics
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
    AssertFact,
    ChatMessage,
    DecisionRecord,
    ExecutionTier,
    InferenceStep,
    MemoryHit,
    Provenance,
    RetrievalQuery,
    RouteAction,
    RouteDecision,
    RuleOutcome,
    RuleState,
    Say,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
    ToolResult,
    TTSChunk,
    SignedPayload,
    UnsignedPayload,
    canonicalize_predicate,
    is_valid_predicate,
)
from lucca.brain.prompt_builder import build_deduction_messages
from lucca.core.reasoning_context import ProofTraceStep, ReasoningContext
from lucca.core.trace import TurnTrace, log_turn_trace, now_ns
from lucca.core.turn_pipeline import TurnInput, TurnPipeline, normalize_spelled_words
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine, is_rollup_due
from lucca.core.memory_commit_service import (
    MemoryCommitService,
    STANCE_MARKERS,
    _DEMONYMS,
    _HYPOTHETICAL_MARKERS,
    _NEGATION_PATTERN,
    _PASSIVE_FACT_PATTERNS,
    _REPORTED_SPEECH_PATTERN,
    _extract_stance_topic,
    _sentence_containing,
)
from lucca.core.belief_service import BeliefService
from lucca.core.confirmation_manager import ConfirmationManager
from lucca.core.speech_output_manager import SpeechOutputManager
from lucca.core.signer_factory import SignerFactory
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    ToolResultSigner,
    UserSpeechSigner,
)
from lucca.core.clock import SystemClock
from lucca.ports import (
    ClockPort,
    MemoryStorePort,
    SandboxPort,
    SpeechLLMPort,
    STTPort,
    TTSPort,
)
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.eval import evaluate_plan, evaluate_rule
from lucca.router.calibration import fit_guard_from_db
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

__all__ = [
    "Orchestrator",
    "TurnInput",
    "TurnPipeline",
    "TurnState",
    "normalize_spelled_words",
]


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



class Orchestrator:
    quit_requested: bool = False
    _default_clock: ClockPort = SystemClock()

    @property
    def clock(self) -> ClockPort:
        return getattr(self, "_clock", None) or self._default_clock

    @clock.setter
    def clock(self, val: ClockPort) -> None:
        self._clock = val

    def __init__(
        self,
        llm: SpeechLLMPort | None = None,
        tts: TTSPort | type[TTSPort] | None = None,
        asr: STTPort | type[STTPort] | None = None,
        sandbox: SandboxPort | None = None,
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
        clock: ClockPort | None = None,
    ) -> None:
        self.config = get_config()
        self._clock = clock if clock is not None else self._default_clock
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

        # Speech Output Manager (WO-18b.5 / F-ARCH-103)
        self.speech_output = SpeechOutputManager(
            orchestrator=self,
            start_worker=True,
            maxsize=32,
        )

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

        # Database Manager fallback (Phase 1, WO-17)
        if db is not None:
            self.db = db
        else:
            from lucca.memory.db import DatabaseManager  # noqa: PLC0415
            db_path = self.config.home_dir / "data" / "memory.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db = DatabaseManager(db_path=db_path)
            try:
                self.db.migrate()
            except Exception as exc:  # noqa: BLE001
                logger.warning("db_migration_failed_on_fallback", error=str(exc))

        # Router & Decision Telemetry
        if router is not None:
            self.router = router
        else:
            log_path = self.config.home_dir / "logs" / "decisions.jsonl"
            intents_cfg = self.config.resolve_path("config/intents.toml")
            guard = fit_guard_from_db(self.db) if self.db is not None else None
            self.router = HeuristicRouter(
                db=self.db,
                log_path=log_path,
                config_path=intents_cfg if intents_cfg.exists() else None,
                conformal_guard=guard,
            )
            logger.info(
                "router_constructed",
                conformal_fitted=guard is not None and guard.q_hat is not None,
                q_hat=None if guard is None else guard.q_hat,
            )

        self.prev_decision_record: DecisionRecord | None = None
        self.prev_turn_ts: float | None = None
        self.current_turn_tool_calls: list[ToolCall] = []
        self.current_turn_tool_spoken: list[str] = []
        self.current_turn_tool_ok: bool = True
        self.current_turn_shadow_outcomes: list[RuleOutcome] = []
        self.current_turn_receipts: list[ToolReceipt] = []
        self.pending_spoken_updates: deque[str] = deque()
        self.current_turn_tier: ExecutionTier = ExecutionTier.FULL_LOOP

        # Confirmation Manager (Spec §3, §7, WO-9 A1, WO-18b)
        self.confirmations = ConfirmationManager(orchestrator=self)

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

        # Memory Store & Provenance Signer (Phase 1, WO-17, WO-18b)
        key = master_key
        if key is None and memory_store is not None:
            store_key = getattr(memory_store, "master_key", None)
            if isinstance(store_key, (bytes, bytearray)) and len(store_key) >= 32:
                key = bytes(store_key)

        if key is None and getattr(self.config, "master_key", None):
            cfg_k = self.config.master_key.encode("utf-8")
            if len(cfg_k) >= 32:
                key = cfg_k

        self.signer_factory = SignerFactory(master_key=key)
        effective_key = self.signer_factory.master_key

        if memory_store is not None:
            self.memory_store = memory_store
        else:
            from lucca.memory.store import MemoryStore  # noqa: PLC0415
            from lucca.senses.embed import EmbedWorker, LocalEmbeddingPort  # noqa: PLC0415

            self.memory_store = MemoryStore(
                db=self.db,
                master_key=effective_key,
                embedding_port=LocalEmbeddingPort(worker=EmbedWorker(device="CPU")),
            )

        if hasattr(self, "router") and hasattr(self.router, "embed_worker"):
            if self.router.embed_worker is None and hasattr(self.memory_store, "embedding_port"):
                self.router.embed_worker = getattr(
                    self.memory_store.embedding_port, "worker", None
                )

        if user_signer is not None:
            self.user_signer: UserSpeechSigner | None = user_signer
        else:
            self.user_signer = self.signer_factory.user_speech()

        self.session_id: str = str(ulid.ULID())
        self.current_turn_transcript: str | None = None

        self.commits = MemoryCommitService(
            memory_store=self.memory_store,
            signer_factory=self.signer_factory,
            clock=self.clock,
            orchestrator=self,
        )

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
        self.action_signer: ToolResultSigner | None = None

        # Autobiographical Reflection Engine (Spec §7, D-MEM-04, WP-2)
        if reflection_engine is not None:
            self.reflection_engine: ReflectionEngine | None = reflection_engine
        elif self.memory_store is not None and hasattr(self.memory_store, "db"):
            self.reflection_engine = ReflectionEngine(
                db=self.memory_store.db,
                store=self.memory_store,
                master_key=effective_key,
            )
        elif self.db is not None and self.memory_store is not None:
            self.reflection_engine = ReflectionEngine(
                db=self.db,
                store=self.memory_store,
                master_key=effective_key,
            )
        else:
            self.reflection_engine = None

        self.beliefs = BeliefService(
            db=self.db,
            reflection_engine=self.reflection_engine,
            clock=self.clock,
            orchestrator=self,
        )
        self.current_reasoning_context: ReasoningContext | None = None

    @property
    def signer_factory(self) -> SignerFactory:
        factory = getattr(self, "_signer_factory", None)
        if factory is None:
            ms = getattr(self, "memory_store", None)
            ms_k = getattr(ms, "master_key", None)
            cfg = getattr(self, "config", None)
            cfg_k = getattr(cfg, "master_key", None)
            k = ms_k or (cfg_k.encode("utf-8") if cfg_k and len(cfg_k) >= 32 else None)
            factory = SignerFactory(master_key=k)
            self._signer_factory = factory
        return factory

    @signer_factory.setter
    def signer_factory(self, value: SignerFactory) -> None:
        self._signer_factory = value

    @property
    def commits(self) -> MemoryCommitService:
        srv = getattr(self, "_commits", None)
        if srv is None:
            srv = MemoryCommitService(
                memory_store=getattr(self, "memory_store", None),
                signer_factory=self.signer_factory,
                clock=getattr(self, "clock", None),
                orchestrator=self,
            )
            self._commits = srv
        return srv

    @commits.setter
    def commits(self, value: MemoryCommitService) -> None:
        self._commits = value

    @property
    def beliefs(self) -> BeliefService:
        srv = getattr(self, "_beliefs", None)
        if srv is None:
            srv = BeliefService(
                db=getattr(self, "db", None),
                reflection_engine=getattr(self, "reflection_engine", None),
                clock=getattr(self, "clock", None),
                orchestrator=self,
            )
            self._beliefs = srv
        return srv

    @beliefs.setter
    def beliefs(self, value: BeliefService) -> None:
        self._beliefs = value

    @property
    def confirmations(self) -> ConfirmationManager:
        mgr = getattr(self, "_confirmations", None)
        if mgr is None:
            mgr = ConfirmationManager(orchestrator=self)
            self._confirmations = mgr
        return mgr

    @confirmations.setter
    def confirmations(self, value: ConfirmationManager) -> None:
        self._confirmations = value

    @property
    def _confirm_event(self) -> threading.Event:
        return self.confirmations.confirm_event

    @_confirm_event.setter
    def _confirm_event(self, val: threading.Event) -> None:
        self.confirmations.confirm_event = val

    @property
    def _confirm_result(self) -> bool:
        return self.confirmations.confirm_result

    @_confirm_result.setter
    def _confirm_result(self, val: bool) -> None:
        self.confirmations.confirm_result = val

    @property
    def _pending_confirmation_active(self) -> bool:
        return self.confirmations.pending_confirmation_active

    @_pending_confirmation_active.setter
    def _pending_confirmation_active(self, val: bool) -> None:
        self.confirmations.pending_confirmation_active = val

    @property
    def _confirm_audio(self) -> PTTReleasedPayload | None:
        return self.confirmations.confirm_audio

    @_confirm_audio.setter
    def _confirm_audio(self, val: PTTReleasedPayload | None) -> None:
        self.confirmations.confirm_audio = val

    @property
    def _confirm_via(self) -> str | None:
        return self.confirmations.confirm_via

    @_confirm_via.setter
    def _confirm_via(self, val: str | None) -> None:
        self.confirmations.confirm_via = val

    @property
    def _confirm_lock(self) -> threading.Lock:
        return self.confirmations.confirm_lock

    @_confirm_lock.setter
    def _confirm_lock(self, val: threading.Lock) -> None:
        self.confirmations.confirm_lock = val

    @property
    def speech_output(self) -> SpeechOutputManager:
        mgr = getattr(self, "_speech_output", None)
        if mgr is None:
            mgr = SpeechOutputManager(orchestrator=self)
            self._speech_output = mgr
        return mgr

    @speech_output.setter
    def speech_output(self, value: SpeechOutputManager) -> None:
        self._speech_output = value

    @property
    def _tts_queue(
        self,
    ) -> queue.Queue[
        tuple[TurnTrace, int, str]
        | tuple[TurnTrace, int, str, threading.Event | None]
        | None
    ]:
        return self.speech_output.tts_queue

    @_tts_queue.setter
    def _tts_queue(
        self,
        val: queue.Queue[
            tuple[TurnTrace, int, str]
            | tuple[TurnTrace, int, str, threading.Event | None]
            | None
        ],
    ) -> None:
        self.speech_output.tts_queue = val

    @property
    def _tts_running(self) -> bool:
        return self.speech_output.tts_running

    @_tts_running.setter
    def _tts_running(self, val: bool) -> None:
        self.speech_output.tts_running = val

    @property
    def _tts_thread(self) -> threading.Thread | None:
        return self.speech_output.tts_thread

    @_tts_thread.setter
    def _tts_thread(self, val: threading.Thread | None) -> None:
        self.speech_output.tts_thread = val

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

    @property
    def turn_pipeline(self) -> TurnPipeline:
        """Pipeline instance executing unified conversational turn logic."""
        pipe = getattr(self, "_turn_pipeline", None)
        if pipe is None:
            pipe = TurnPipeline(self)
            self._turn_pipeline = pipe
        return pipe

    @turn_pipeline.setter
    def turn_pipeline(self, pipeline: TurnPipeline) -> None:
        self._turn_pipeline = pipeline

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

    def _publish_mem_event(self, provenance: str, content: str) -> None:
        """WO-9 A10 (F17): publish a mem.commit bus event so the UI memory tab
        can live-refresh. The event types existed in events.py but no publisher
        ever emitted them (F17)."""
        try:
            env = Envelope(
                type="mem.commit",
                trace_id="",
                ts_ns=now_ns(),
                src="core",
                payload={
                    "provenance": provenance,
                    "content_preview": str(content)[:120],
                },
            )
            self._publish_bus(env)
        except Exception as exc:  # noqa: BLE001
            logger.debug("mem_commit_event_publish_failed", error=str(exc))

    def _emit_tts_overflow(self, trace_id: str = "", chunk_id: int = -1) -> None:
        """WO-17 Phase 7: emit a tts_queue_overflow telemetry event on the bus."""
        self.speech_output.emit_tts_overflow(trace_id=trace_id, chunk_id=chunk_id)

    def _enqueue_tts_chunk(self, trace: TurnTrace, chunk_id: int, text: str) -> None:
        """Enqueues a synthesized voice chunk with drop-oldest overflow policy (WO-17 Phase 7)."""
        self.speech_output.enqueue_tts_chunk(trace=trace, chunk_id=chunk_id, text=text)

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
        self.speech_output.publish_caption(text=text, source=source, is_final=is_final)

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

    # delegate — kept for test/back-compat
    def confirm_action(
        self,
        accepted: bool,
        via: Literal["voice", "click", "timeout", "abort"] = "click",
    ) -> None:
        self.confirmations.confirm_action(accepted, via=via)

    def _on_ptt_pressed(self, ts_ns: int) -> None:
        if self._pending_confirmation_active:
            # WO-9 A1 (F1): during confirm_wait a PTT press is the ANSWER
            # mechanism, not a barge-in. Stop the confirmation prompt audio so
            # the user can speak, but keep the pending confirmation alive so
            # _on_ptt_released can stash the captured slice for the waiting
            # turn worker (F-CORE-015 voice-answer path).
            self._abort_confirmation_prompt_playback()
        elif self.state in ("speaking", "thinking"):
            # Instant barge-in: abort LLM and playback
            self._abort_turn()

        print("\n[PTT] 🎙️ Listening... (Hold Alt-Gr or Right-Ctrl to speak)", flush=True)
        self._publish_caption("Listening... 🎙️", source="status", is_final=False)
        self._set_state("listening")

    # delegate — kept for test/back-compat
    def _abort_confirmation_prompt_playback(self) -> None:
        self.confirmations.abort_confirmation_prompt_playback()

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
        self.speech_output.clear_queue()

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
        if self._pending_confirmation_active:
            # WO-9 A1 (F1): typed input during confirm_wait is a confirmation
            # answer, not a new turn. The turn worker is blocked in
            # _confirm_event.wait(); aborting it here cancelled every typed
            # confirmation (confirmation_cancelled_by_barge_in). Parse the
            # text and resolve the pending action instead. Unknown input
            # cancels, mirroring the voice path's unknown -> cancel policy.
            decision = parse_confirmation_response(user_text)
            logger.info("text_confirmation_answer", decision=decision)
            self.confirm_action(accepted=decision == "confirm", via="click")
            return

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
        last_tool_val = self.executed_tools[-1][0] if self.executed_tools else None
        intent, auto_conf, entities = self.router.classify_intent(
            transcript, last_tool=last_tool_val
        )
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
            if isinstance(res, list):
                return res
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning("memory_search_failed", error=str(e))
            return []

    # delegate — kept for test/back-compat
    def _commit_transcript(self, text: str, trace: TurnTrace) -> str | None:
        return self.commits.commit_transcript(text, trace)

    # delegate — kept for test/back-compat
    def _commit_action_receipts(self, trace: TurnTrace) -> None:
        self.commits.commit_action_receipts(trace)

    # delegate — kept for test/back-compat
    def _maybe_extract_facts(self, trace: TurnTrace) -> None:
        self.commits.maybe_extract_facts(trace)

    # delegate — kept for test/back-compat
    def _commit_assistant_utterance(self, text: str, trace: TurnTrace) -> None:
        self.commits.commit_assistant_utterance(text, trace)

    def _commit_lisp_assertion(
        self, action: AssertFact, trace: TurnTrace | None = None
    ) -> SignedPayload | None:
        """Commits an AssertFact action as a signed LISP_ASSERTION envelope (WO-20 Phase 1)."""
        if not self.memory_store:
            return None
        signer = self.signer_factory.lisp_assertion()
        now = self.clock.now_utc() if hasattr(self, "clock") and self.clock else time.time()
        trace_id = trace.trace_id if trace else f"trace-{ulid.ULID()}"
        unsigned = UnsignedPayload(
            content=f"{action.s} {action.p} {action.o}",
            provenance=Provenance.LISP_ASSERTION,
            kind="fact",
            nonce=os.urandom(16).hex(),
            created_at=now,
            trace_id=trace_id,
            structured={"s": action.s, "p": action.p, "o": action.o},
        )
        signed = signer.sign(unsigned)
        self.memory_store.commit(signed, now=now)
        return signed

    def evaluate_rules_chain(
        self,
        state: RuleState,
        trace: TurnTrace | None = None,
        max_depth: int = 8,
        context: ReasoningContext | None = None,
    ) -> tuple[list[RuleOutcome], RuleState]:
        """Evaluates active rules with bounded re-evaluation loop (WO-20 Phase 1 & 2)."""
        ctx = context if context is not None else ReasoningContext()
        self.current_reasoning_context = ctx

        def _exec_assert(
            action: AssertFact, st: RuleState, rule_id: str | None = None
        ) -> RuleState:
            signed = self._commit_lisp_assertion(action, trace)
            env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
            conf = signed.confidence if signed and signed.confidence is not None else 1.0

            ctx.add_intermediate(
                envelope_id=env_id,
                s=action.s,
                p=action.p,
                o=action.o,
                confidence=conf,
                step_kind="lisp_rule",
                rule_id=rule_id,
            )
            return st.model_copy(
                update={"asserted_facts": st.asserted_facts | {(action.s, action.p, action.o)}}
            )

        outcomes, final_state = self.rule_engine.evaluate_chain(
            state, execute_assert=_exec_assert, max_depth=max_depth, context=ctx
        )
        if len(ctx) > 0:
            self.finalize_chain(ctx, trace)
        return outcomes, final_state

    def finalize_chain(
        self,
        context: ReasoningContext | None = None,
        trace: TurnTrace | None = None,
    ) -> SignedPayload | None:
        """Commits the conclusion of a completed chain as INFERRED with its proof trace (WO-20 Phase 4)."""
        ctx = context if context is not None else getattr(self, "current_reasoning_context", None)
        if ctx is None or len(ctx) == 0:
            return None
        if not self.memory_store:
            return None

        final_entry = ctx[-1]
        proof_trace_steps = ctx.proof_trace()
        proof_trace = [s.to_dict() for s in proof_trace_steps]
        confidence = min(s.confidence for s in proof_trace_steps) if proof_trace_steps else 1.0

        all_conditions: list[str] = []
        for s in proof_trace_steps:
            for cond in s.conditions:
                if cond not in all_conditions:
                    all_conditions.append(cond)

        signer = self.signer_factory.inferred_fact()
        now = self.clock.now_utc() if hasattr(self, "clock") and self.clock else time.time()
        trace_id = trace.trace_id if trace else f"trace-{ulid.ULID()}"

        unsigned = UnsignedPayload(
            content=f"{final_entry.s} {final_entry.p} {final_entry.o}",
            provenance=Provenance.INFERRED,
            kind="fact",
            confidence=confidence,
            nonce=os.urandom(16).hex(),
            created_at=now,
            trace_id=trace_id,
            structured={
                "s": final_entry.s,
                "p": final_entry.p,
                "o": final_entry.o,
                "confidence": confidence,
                "proof_trace": proof_trace,
                "conditions": all_conditions,
            },
        )
        signed = signer.sign(unsigned)
        self.memory_store.commit(signed, now=now)
        return signed

    def proof_trace(self) -> list[ProofTraceStep]:
        """Exposes the current turn's reasoning context proof trace (Spec D-REAS-09, WO-20 Phase 2/4)."""
        ctx = getattr(self, "current_reasoning_context", None)
        if ctx is None:
            return []
        return ctx.proof_trace()

    def _validate_premise(
        self, premise: str, context: ReasoningContext
    ) -> tuple[bool, str | None]:
        """Validates a premise against signed tool receipts, reasoning context, or the signed store.

        (Spec D-REAS-09, WO-20 Phase 3 / Amendment 2026-09-26).
        """
        clean = premise.strip()

        # 1. Attributed premise: "<source> asserts <claim>"
        attr_match = re.match(r"^(.+?)\s+asserts\s+(.+)$", clean, re.IGNORECASE)
        if attr_match:
            claim = attr_match.group(2).strip().lower()
            # Validates against current turn's signed tool receipts
            receipts = getattr(self, "current_turn_receipts", []) or []
            executed = getattr(self, "executed_tools", []) or []
            for r in list(receipts) + list(executed):
                ok = getattr(r, "ok", True)
                if not ok:
                    continue
                out = (
                    str(getattr(r, "output", "") or "")
                    or str(getattr(r, "content", "") or "")
                    or str(getattr(r, "structured", "") or "")
                ).lower()
                if claim in out or all(word in out for word in claim.split() if len(word) > 2):
                    return (True, None)
            return (False, "unverified_premise")

        # 2. Reasoning context check (intermediate facts in current chain)
        if context.resolve_premise(clean) is not None:
            return (True, None)
        for intermediate in context.intermediates:
            if intermediate.conclusion.lower() == clean.lower() or intermediate.envelope_id == clean:
                return (True, None)

        # 3. Signed memory store check
        if self.db is not None:
            try:
                with self.db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.content, e.entry_id, e.provenance
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1
                          AND (m.content = ? OR e.entry_id = ? OR m.content = ?)
                        """,
                        (clean, clean, clean.lower()),
                    )
                    if cur.fetchall():
                        return (True, None)

                    # Normalized triple check
                    parts = clean.split()
                    if len(parts) >= 2:
                        s_target = parts[0]
                        o_target = parts[-1]
                        cur.execute(
                            """
                            SELECT m.content
                            FROM memories m
                            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                            WHERE e.grounding_eligible = 1
                              AND m.content LIKE ? AND m.content LIKE ?
                            """,
                            (f"%{s_target}%", f"%{o_target}%"),
                        )
                        if cur.fetchall():
                            return (True, None)
            except Exception as exc:  # noqa: BLE001
                logger.debug("premise_validation_db_error", error=str(exc))

        return (False, "unverified_premise")

    def _search_memory_for_premise(self, premise: str) -> list[str]:
        """Runs memory_search for unverified premise (Gather Ladder Step 2)."""
        clean = premise.strip()
        hits: list[str] = []

        # Attributed premises ("<source> asserts <claim>") verify against current-turn tool receipts,
        # NOT against the fact store (AMENDMENT 2026-09-26).
        if re.match(r"^(.+?)\s+asserts\s+(.+)$", clean, re.IGNORECASE):
            return []

        # 1. Use MemoryStore search if available
        if self.memory_store is not None and hasattr(self.memory_store, "search"):
            try:
                q = RetrievalQuery(query_text=clean, k=5)
                res = self.memory_store.search(q)
                for h in res:
                    if getattr(h, "grounding_eligible", False):
                        words = [w.lower() for w in re.split(r"[\s_]+", clean) if len(w) > 2]
                        if clean.lower() in h.content.lower() or (words and all(w in h.content.lower() for w in words)):
                            hits.append(h.content)
            except Exception as exc:  # noqa: BLE001
                logger.debug("gather_ladder_search_error", error=str(exc))

        # 2. Database search fallback
        if not hits and self.db is not None:
            try:
                words = [w.lower() for w in re.split(r"[\s_]+", clean) if len(w) > 2]
                if words:
                    clauses = " AND ".join(["m.content LIKE ?" for _ in words])
                    params = [f"%{w}%" for w in words]
                    with self.db.read_cursor() as cur:
                        cur.execute(
                            f"""
                            SELECT m.content
                            FROM memories m
                            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                            WHERE e.grounding_eligible = 1 AND {clauses}
                            """,
                            tuple(params),
                        )
                        for r in cur.fetchall():
                            hits.append(r[0])
            except Exception as exc:  # noqa: BLE001
                logger.debug("gather_ladder_db_search_error", error=str(exc))

        return hits

    def _parse_inference_steps(self, text: str) -> list[InferenceStep]:
        """Extracts and validates InferenceStep models from LLM JSON response."""
        clean_text = text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
        if fence_match:
            clean_text = fence_match.group(1).strip()

        array_match = re.search(r"\[[\s\S]*\]", clean_text)
        obj_match = re.search(r"\{[\s\S]*\}", clean_text)

        raw_data: object = None
        if array_match:
            raw_data = json.loads(array_match.group(0))
        elif obj_match:
            raw_data = json.loads(obj_match.group(0))
        else:
            raw_data = json.loads(clean_text)

        steps: list[InferenceStep] = []
        if isinstance(raw_data, list):
            for item in raw_data:
                if isinstance(item, dict):
                    steps.append(InferenceStep.model_validate(item))
        elif isinstance(raw_data, dict):
            steps.append(InferenceStep.model_validate(raw_data))

        return steps

    def run_deduction_step(
        self,
        goal: str,
        trace: TurnTrace | None = None,
        context: ReasoningContext | None = None,
        llm: object | None = None,
    ) -> tuple[list[InferenceStep], str | None]:
        """Runs the abductive deduction loop with bounded gather ladder (Spec D-REAS-09, WO-20 Phase 3).

        Proposes InferenceSteps via LLM, validates premises against signed store/receipts,
        signs valid steps via SignerFactory as LISP_ASSERTION, and executes the Gather Ladder
        on unverified premises (Revise -> Memory Retry -> User Question -> Abstention).
        """
        effective_llm = llm if llm is not None else getattr(self, "llm", None)
        if effective_llm is None:
            logger.warning("no_llm_available_for_deduction")
            return ([], "No language model available for deduction.")

        ctx = context if context is not None else (
            getattr(self, "current_reasoning_context", None) or ReasoningContext()
        )
        self.current_reasoning_context = ctx
        trace_id = trace.trace_id if trace else f"trace-{ulid.ULID()}"

        # Collect verified fact context
        verified_facts: list[str] = [entry.conclusion for entry in ctx.intermediates]
        if self.db is not None:
            try:
                with self.db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.content
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1
                        ORDER BY m.created_at DESC
                        LIMIT 20
                        """
                    )
                    for row in cur.fetchall():
                        if row[0] not in verified_facts:
                            verified_facts.append(row[0])
            except Exception as exc:  # noqa: BLE001
                logger.debug("deduction_context_gather_error", error=str(exc))

        # Collect verified tool receipts
        attributed_receipts: list[str] = []
        for r in (getattr(self, "current_turn_receipts", []) or []):
            out = str(getattr(r, "output", "") or getattr(r, "content", "") or "")
            if out:
                attributed_receipts.append(f"{getattr(r, 'tool', 'tool')}: {out}")

        # Stream initial LLM turn
        full_text = ""
        for event in effective_llm.stream_turn(
            current_text=goal,
            memories=[],
            history=getattr(self, "history", []),
            trace_id=trace_id,
        ):
            if isinstance(event, TokenDelta):
                full_text += event.delta

        proposed_steps: list[InferenceStep] = []
        try:
            proposed_steps = self._parse_inference_steps(full_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("deduction_llm_parse_error", error=str(exc), raw=full_text)
            return ([], f"Failed to parse deduction steps: {exc}")

        accepted_steps: list[InferenceStep] = []

        for step in proposed_steps:
            # Check attributed premises and ensure presence in conditions
            for prem in step.premises:
                if re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE):
                    if prem not in step.conditions:
                        if len(step.conditions) < 8:
                            step.conditions.append(prem)

            # Validate all premises
            unverified: list[str] = []
            for prem in step.premises:
                ok, _ = self._validate_premise(prem, ctx)
                if not ok:
                    unverified.append(prem)

            if not unverified:
                # Valid step: Sign and commit as LISP_ASSERTION (TRAP 1: Orchestrator signs!)
                action = AssertFact(s=step.s, p=step.p, o=step.o)
                signed = self._commit_lisp_assertion(action, trace)
                env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
                conf = step.confidence if signed and signed.confidence is not None else step.confidence
                ctx.add_intermediate(
                    envelope_id=env_id,
                    s=step.s,
                    p=step.p,
                    o=step.o,
                    confidence=conf,
                    step_kind="llm_abductive",
                    rule_id="llm",
                    premises=list(step.premises),
                    conditions=list(step.conditions),
                )
                accepted_steps.append(step)
                continue

            # Gather Ladder (bounded to 1 pass per deduction turn)
            missing_premise = unverified[0]
            logger.info("gather_ladder_started", missing_premise=missing_premise)

            # 1. Revise once
            error_payload = json.dumps({"error": "unverified_premise", "premise": missing_premise})
            revised_text = ""
            for event in effective_llm.stream_turn(
                current_text=f"Revise inference step: {error_payload}",
                trace_id=trace_id,
            ):
                if isinstance(event, TokenDelta):
                    revised_text += event.delta

            revised_step: InferenceStep | None = None
            try:
                r_steps = self._parse_inference_steps(revised_text)
                if r_steps:
                    revised_step = r_steps[0]
            except Exception as exc:  # noqa: BLE001
                logger.warning("gather_ladder_revise_parse_failed", error=str(exc))

            step_to_evaluate = revised_step
            still_unverified: list[str] = []
            if step_to_evaluate is not None:
                for prem in step_to_evaluate.premises:
                    if re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE):
                        if prem not in step_to_evaluate.conditions and len(step_to_evaluate.conditions) < 8:
                            step_to_evaluate.conditions.append(prem)
                    ok, _ = self._validate_premise(prem, ctx)
                    if not ok:
                        still_unverified.append(prem)

                if not still_unverified:
                    # Revised step accepted!
                    action = AssertFact(s=step_to_evaluate.s, p=step_to_evaluate.p, o=step_to_evaluate.o)
                    signed = self._commit_lisp_assertion(action, trace)
                    env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
                    ctx.add_intermediate(
                        envelope_id=env_id,
                        s=step_to_evaluate.s,
                        p=step_to_evaluate.p,
                        o=step_to_evaluate.o,
                        confidence=step_to_evaluate.confidence,
                        step_kind="llm_abductive",
                        rule_id="llm",
                        premises=list(step_to_evaluate.premises),
                        conditions=list(step_to_evaluate.conditions),
                    )
                    accepted_steps.append(step_to_evaluate)
                    continue

            # 2. Memory retry
            retry_premise = still_unverified[0] if still_unverified else missing_premise
            recovered = self._search_memory_for_premise(retry_premise)
            if recovered:
                target = step_to_evaluate if step_to_evaluate is not None else step
                action = AssertFact(s=target.s, p=target.p, o=target.o)
                signed = self._commit_lisp_assertion(action, trace)
                env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
                ctx.add_intermediate(
                    envelope_id=env_id,
                    s=target.s,
                    p=target.p,
                    o=target.o,
                    confidence=target.confidence,
                    step_kind="llm_abductive",
                    rule_id="llm",
                    premises=list(target.premises),
                    conditions=list(target.conditions),
                )
                accepted_steps.append(target)
                continue

            # 3. Ask the user (named-gap question) vs 4. Named-gap abstention
            is_personal = any(k in retry_premise.lower() for k in ("user", "you", "live", "from", "born", "home", "partner"))
            if is_personal:
                spoken = f"I don't have anything verified about {retry_premise} — can you tell me about it?"
            else:
                spoken = f"I can't verify {retry_premise}, so I can't deduce that yet."

            logger.info("gather_ladder_terminated", outcome=spoken, missing_premise=retry_premise)
            if hasattr(self, "_speak_text") and trace:
                self._speak_text(trace, spoken)
            return (accepted_steps, spoken)

        if accepted_steps and len(ctx) > 0:
            self.finalize_chain(ctx, trace)
        return (accepted_steps, None)

    run_deduction_loop = run_deduction_step


    def _check_functional_coherence(
        self,
        narration: str,
        receipts: Sequence[ToolReceipt | dict[str, JsonValue] | object] | None = None,
        tool_calls: Sequence[ToolReceipt | dict[str, JsonValue] | object] | None = None,
    ) -> str | None:
        """
        Checks for discrepancy between spoken action claim and actual tool execution
        (Spec §3.3, WP-2). Returns breach description if discrepancy detected, else None.
        """
        if receipts is None:
            receipts = (
                tool_calls if tool_calls is not None else getattr(self, "current_turn_receipts", [])
            )
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
            else:
                generic_tools = (
                    "launch_app",
                    "write_file",
                    "delete_file",
                    "search_web",
                    "fetch_url",
                )
                for generic_tool in generic_tools:
                    norm_receipts.append(
                        ToolReceipt(
                            tool=generic_tool,
                            ok=True,
                            call_id="simulated",
                        )
                    )
        claims = detect_ungrounded_action_claims(narration, norm_receipts)
        un_grounded = [c for c in claims if not c.grounded]
        if un_grounded:
            return un_grounded[0].breach_description or "Ungrounded action claim detected"
        return None

    # delegate — kept for test/back-compat
    def _commit_coherence_breach(self, claim: str, trace: TurnTrace | None = None) -> None:
        self.commits.commit_coherence_breach(claim, trace)

    def _finalize_turn(self, trace: TurnTrace, decision_id: str | None) -> None:
        if self.active_trace is trace and not trace.interrupted:
            self._set_state("postturn")
        committed_user_id: str | None = None
        user_transcript_text: str | None = None
        if self.current_turn_transcript:
            user_transcript_text = self.current_turn_transcript
            committed_user_id = self._commit_transcript(self.current_turn_transcript, trace)
            self.current_turn_transcript = None
        elif getattr(self, "_early_transcript_commit", None):
            # WO-9 A2: transcript was committed early to ground a memory_commit
            # in this turn; reuse that commit for contradiction detection.
            committed_user_id, user_transcript_text = self._early_transcript_commit
            self._early_transcript_commit = None

        if hasattr(self, "current_turn_assistant_reply") and self.current_turn_assistant_reply:
            reply_text = self.current_turn_assistant_reply
            self._commit_assistant_utterance(reply_text, trace)

            # Functional coherence check (Spec §3.3 / D-MEM-04 / WP-2)
            breach_msg = self._check_functional_coherence(reply_text, self.current_turn_receipts)
            if breach_msg:
                self._commit_coherence_breach(breach_msg, trace)

            # WO-9 A12 (F9): stance claims during action turns are beliefs too —
            # the old zero-tool-call gate left a systematic blind spot exactly
            # on turns where Lucca was acting. Interrogatives are still
            # excluded inside _maybe_form_belief's caller chain.
            if self.current_turn_tier == ExecutionTier.FULL_LOOP:
                self._maybe_form_belief(reply_text, trace)

            self.current_turn_assistant_reply = None

        # WO-9 A9 (F8): persist ASSISTANT_ACTION receipts — including cancels,
        # timeouts, BDI rejections and provenance refusals — so "did you
        # actually do X?" is answerable from SELF_HISTORY instead of confabulated.
        self._commit_action_receipts(trace)

        # Contradiction detection on USER_EXPLICIT commit (Spec §7, WP-2)
        if committed_user_id and user_transcript_text:
            self._check_contradictions(committed_user_id, user_transcript_text, trace)
            # WO-9 A3: passive fact extraction from the user's own words
            self._maybe_extract_facts(trace)

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
        if not hasattr(self, "current_turn_receipts"):
            self.current_turn_receipts = []
        out_str = str(output) if output is not None and not isinstance(output, str) else output
        err_str = str(error) if error is not None and not isinstance(error, str) else error
        self.current_turn_receipts.append(
            ToolReceipt(
                tool=name,
                tool_name=name,
                ok=ok,
                call_id=call_id,
                args=dict(args),
                output=out_str,
                error=err_str,
                timestamp=time.time(),
            )
        )

    # delegate — kept for test/back-compat
    def _maybe_form_belief(self, reply_text: str, trace: TurnTrace) -> None:
        self.commits.maybe_form_belief(reply_text, trace)

    # delegate — kept for test/back-compat
    def _check_contradictions(self, new_entry_id: str, new_content: str, trace: TurnTrace) -> None:
        self.beliefs.check_contradictions(new_entry_id, new_content, trace)

    # delegate — kept for test/back-compat
    def _maybe_speak_pending_updates(self, trace: TurnTrace) -> None:
        self.beliefs.maybe_speak_pending_updates(trace)

    def maybe_run_nightly_rollup(self, now: float | None = None) -> int:
        """Executes nightly roll-up if due and records persistent timestamp."""
        if not self.reflection_engine:
            return 0
        current_time = now if now is not None else time.time()
        last_rollup = self.reflection_engine.get_last_rollup_at()
        rollup_hour = getattr(self.config.memory, "rollup_hour_local", 3)
        if is_rollup_due(last_rollup, current_time, rollup_hour):
            try:
                compressed = self.reflection_engine.nightly_rollup(now=current_time)
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
        max_rounds: int = 8,
        epistemic_context: str | None = None,
        enable_thinking: bool | None = None,
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
        # WO-9 A5: repeated-call guard state
        call_signatures: list[str] = []

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
            self.speech_output.clear_queue()
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
                round_response_text: list[str] = []
                round_failed_tools: list[str] = []
                print(f"[Lucca R{round_num}] " if round_num > 1 else "[Lucca] ", end="", flush=True)
                if round_num == 1:
                    trace.t_llm_sent = now_ns()

                # WO-9 A5: convergence loop — tools stay available every round
                # and the loop terminates when the model stops calling tools.
                # The hard cap is a runaway guard only: on the final round tools
                # are withdrawn and the model must summarise honestly.
                if round_num == max_rounds and tools:
                    tool_messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                "[Tool Budget Reached: You have used the maximum number "
                                "of tool rounds. Do not call any more tools. Summarise "
                                "what you found and what you could NOT verify; never "
                                "fabricate missing facts.]"
                            ),
                        )
                    )
                    trace.cap_hit = True
                    logger.info("tool_round_cap_reached", max_rounds=max_rounds)
                round_tools = [] if round_num == max_rounds else tools

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
                    enable_thinking=enable_thinking,
                ):
                    if trace.interrupted:
                        break

                    if isinstance(event, TokenDelta) and event.delta:
                        if not first_token_seen:
                            first_token_seen = True
                            trace.t_llm_first_token = now_ns()

                        trace.tokens_out += 1
                        full_response_text.append(event.delta)
                        round_response_text.append(event.delta)
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

                                self._enqueue_tts_chunk(trace, em_chunk.chunk_id, clean_chunk_text)
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
                            round_failed_tools.append(tool_name)
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
                                    content="",
                                    tool_calls=[
                                        {
                                            "id": call_id,
                                            "type": "function",
                                            "function": {
                                                "name": tool_name,
                                                "arguments": json.dumps(tool_args),
                                            },
                                        }
                                    ],
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
                            if not tool_res.ok:
                                round_failed_tools.append(tool_name)
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
                            elif not tool_res.ok:
                                content_str = f"Error: {tool_name} failed"
                            else:
                                content_str = "Success"
                        else:
                            content_str = "Action completed."

                        tool_messages.append(
                            ChatMessage(
                                role="assistant",
                                content="",
                                tool_calls=[
                                    {
                                        "id": call_id,
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": json.dumps(tool_args),
                                        },
                                    }
                                ],
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

                        # WO-9 A5: repeated-call guard — an identical
                        # (tool, args) call already returned this turn; force
                        # the model to use the result or change approach.
                        call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                        call_signatures.append(call_sig)
                        if call_signatures.count(call_sig) >= 2:
                            tool_messages.append(
                                ChatMessage(
                                    role="user",
                                    content=(
                                        "[Repeat Guard: You already issued this exact "
                                        "call and it returned a result above. Use that "
                                        "result, or try a different approach — do not "
                                        "repeat it.]"
                                    ),
                                )
                            )
                        # WO-13.1: Pre-Narration Sanity-Check Guard (Fault Mode C)
                        if tool_res is not None and tool_res.ok and content_str:
                            sanity_res = self.turn_pipeline.sanity_guard.validate(
                                tool_name=tool_name,
                                tool_args=tool_args,
                                tool_output=content_str,
                                user_query=user_msg,
                            )
                            if not sanity_res.is_valid and sanity_res.directive:
                                logger.warning(
                                    "tool_output_sanity_anomaly_detected",
                                    round_num=round_num,
                                    tool=tool_name,
                                    violation=sanity_res.violation_type,
                                    reason=sanity_res.reason,
                                )
                                tool_messages.append(
                                    ChatMessage(
                                        role="user",
                                        content=sanity_res.directive,
                                    )
                                )

                # WO-11.2: G1+G6 unified honesty & register nudge (D-HON-01)
                # If any tool failed in this round, inject honesty directive
                # instructing the model to state the failure plainly, forbid
                # guessing/fabrication (especially numbers), and bar celebration/confidence
                # register.
                if round_failed_tools:
                    failed_names = ", ".join(dict.fromkeys(round_failed_tools))
                    logger.info(
                        "tool_failure_honesty_nudge_injected",
                        round_num=round_num,
                        failed_tools=failed_names,
                    )
                    tool_messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                f"[Honesty Directive: A tool you called this turn failed "
                                f"({failed_names}). State the failure plainly. Never guess, "
                                "estimate, or fabricate the result the tool was supposed to "
                                "produce — especially numbers. Do not use celebration, "
                                "confidence, or success register when reporting failed or "
                                "unverified results.]"
                            ),
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
                                    "[Autonomous Research Directive: Do not output "
                                    "conversational filler, cheerleading, or empty promises. "
                                    "Do not ask rhetorical permission questions or request "
                                    "clarification. Execute search_web or fetch_url immediately "
                                    "to retrieve and present the verified facts.]"
                                ),
                            )
                        )
                        self.output_supervisor.turn_has_stalled = False
                        continue
                    # WO-9 A4 (F4): promise-without-action guard. If the model
                    # promised an action ("I'll go ahead and commit that right
                    # now") but issued no tool call, inject an honesty directive
                    # forcing it to either call the tool or state plainly that
                    # it has not done it.
                    if round_num < max_rounds and tools:
                        promises = detect_promised_action_claims("".join(round_response_text))
                        if promises:
                            logger.info(
                                "promised_action_without_tool_call_intercepted",
                                round_num=round_num,
                                promises=promises[:2],
                            )
                            tool_messages.append(
                                ChatMessage(
                                    role="user",
                                    content=(
                                        "[Honesty Directive: You stated you would perform "
                                        f"an action ({' ; '.join(promises[:2])}) but issued "
                                        "no tool call. Either call the appropriate tool "
                                        "now, or state plainly that you have NOT done it "
                                        "and will not pretend otherwise.]"
                                    ),
                                )
                            )
                            continue
                    break

            # WO-9 A5: convergence telemetry
            trace.rounds_used = round_num

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
                        self._enqueue_tts_chunk(trace, em_chunk.chunk_id, clean_chunk_text)
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
                            self._enqueue_tts_chunk(trace, em_chunk.chunk_id, clean_final_text)
                            chunk_index += 1

                if chunk_index > 0 and not trace.interrupted:
                    self.speech_output.wait_for_playback(trace)

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

    def _reset_turn_state(self) -> None:
        """Reset per-turn state for sandbox, supervisor, flags, and tool tracking."""
        self.turn_pipeline.reset_turn_state()

    def _execute_reflex(
        self,
        trace: TurnTrace,
        winning_outcome: RuleOutcome | None,
        user_text: str,
        decision_id: str | None,
    ) -> None:
        """
        Execute a REFLEX tier turn: run plan or built-in emergency reflex,
        emit triple, and finalize.
        """
        self.turn_pipeline.execute_reflex(
            trace=trace,
            winning_outcome=winning_outcome,
            user_text=user_text,
            decision_id=decision_id,
        )

    def _execute_act_then_narrate(
        self,
        trace: TurnTrace,
        winning_outcome: RuleOutcome,
        user_text: str,
        decision_id: str | None,
    ) -> None:
        """
        Execute an ACT_THEN_NARRATE tier turn: run plan tools, emit triple,
        and stream narration.
        """
        self.turn_pipeline.execute_act_then_narrate(
            trace=trace,
            winning_outcome=winning_outcome,
            user_text=user_text,
            decision_id=decision_id,
        )

    def _build_epistemic_context(
        self,
        user_text: str,
        yielded_context: dict[str, object] | None = None,
        route_decision: RouteDecision | None = None,
        spelling_hint: str | None = None,
        trace: TurnTrace | None = None,
    ) -> str | None:
        """
        Build epistemic context from search cascade, yield signals, F13 clarify hints,
        and spelling hints.
        """
        return self.turn_pipeline.build_epistemic_context(
            user_text=user_text,
            yielded_context=yielded_context,
            route_decision=route_decision,
            spelling_hint=spelling_hint,
            trace=trace,
        )

    def _detect_follow_up_and_gate_tools(
        self,
        rule_state: RuleState,
        text_for_gate: str,
    ) -> list[object] | None:
        """
        Intent-based tool gating — suppress tools ONLY for dangerous or pure chit-chat.
        Returns empty list if tools are suppressed, or None to let _stream_llm_speech decide.
        """
        return self.turn_pipeline.detect_follow_up_and_gate_tools(
            rule_state=rule_state,
            text_for_gate=text_for_gate,
        )

    def _run_turn(self, trace: TurnTrace, p: PTTReleasedPayload) -> None:
        """
        Voice turn input adapter: reads audio from capture ring, performs
        silence/VAD check, transcribes via ASR, encodes WAV payload,
        and delegates to the unified TurnPipeline.
        """
        self._reset_turn_state()

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
        if self.asr and len(pcm_samples) > 0:
            trace.t_asr_sent = now_ns()
            asr_res = self.asr.transcribe(pcm_samples)
            trace.t_asr_done = now_ns()
            transcribed_text = asr_res.text.strip()
            self.current_turn_transcript = transcribed_text

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

        turn_input = TurnInput(
            user_text=transcribed_text,
            trace=trace,
            origin="voice",
            mode="transcript" if is_trans_mode else "audio",
            vad_speech_ms=p.vad_speech_ms,
            current_audio_b64=llm_audio,
            current_text=llm_text,
        )
        self.turn_pipeline.run(turn_input)

    def _run_text_turn(self, trace: TurnTrace, user_text: str) -> None:
        """
        Text turn input adapter: normalizes text payload and delegates to the
        unified TurnPipeline.
        """
        turn_input = TurnInput(
            user_text=user_text,
            trace=trace,
            origin="text",
            mode="transcript",
            vad_speech_ms=1000.0,
            current_text=user_text,
        )
        self.turn_pipeline.run(turn_input)

    def _synthesize_chunk(self, trace: TurnTrace, chunk_id: int, text: str) -> None:
        self.speech_output.synthesize_chunk(trace, chunk_id, text)

    def _tts_worker(self) -> None:
        """Background worker thread (core-tts) consuming chunks from speech_output."""
        self.speech_output.tts_worker()

    def _speak_text(self, trace: TurnTrace, text: str) -> None:
        self.speech_output.speak_text(trace, text)

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
        if name == "memory_commit":
            # WO-9 A2 (ADR-010): read the fact back so the user confirms what
            # will actually be saved, not "execute memory_commit".
            o = str(args.get("o", "")).strip()
            p = str(args.get("p", "")).strip()
            if o and p:
                natural = {
                    "is_named": f"your name is {o}",
                    "lives_in": f"you live in {o}",
                    "works_at": f"you work at {o}",
                    "works_as": f"you work as {o}",
                    "born_on": f"you were born on {o}",
                    "birthday_is": f"your birthday is {o}",
                    "timezone_is": f"your timezone is {o}",
                }.get(p, f"{str(args.get('s', 'you')).strip()} {p.replace('_', ' ')} {o}")
                return f"save that {natural}"
            return "save a fact to memory"
        return f"execute {name}"

    def _handle_self_history_search(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        """WO-9 A14 (F18): expose the SELF_HISTORY substrate as a READ tool.

        Backed by query_substrate_self_history (execution_triples ∪
        ASSISTANT_ACTION ∪ ASSISTANT_UTTERANCE ∪ COHERENCE_BREACH ∪
        ASSISTANT_BELIEF). Depends on A9 for content worth querying.
        """
        from pydantic import ValidationError  # noqa: PLC0415

        from lucca.sandbox.schemas import TOOL_ARG_SCHEMAS  # noqa: PLC0415

        schema_cls = TOOL_ARG_SCHEMAS.get("self_history_search")
        if schema_cls is not None:
            try:
                parsed_sh = schema_cls.model_validate(args)
                query = str(getattr(parsed_sh, "query", "")).strip()
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
        else:
            query = str(args.get("query", "")).strip()
            if not query:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr="invalid_arguments: query is required",
                    elapsed_ms=0.0,
                )
        cascade = getattr(self, "cascade", None)
        if cascade is None:
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr="self-history substrate unavailable",
                elapsed_ms=0.0,
            )
        try:
            items = cascade.query_substrate_self_history(query)
        except Exception as exc:  # noqa: BLE001
            logger.debug("self_history_search_failed", error=str(exc))
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=f"self_history_search failed: {exc}",
                elapsed_ms=0.0,
            )
        lines = [f"- [{item.source}] {item.content}" for item in items[:10]]
        content = "\n".join(lines) if lines else "No self-history records match that query."
        self._record_tool_receipt(
            name="self_history_search",
            call_id=call_id,
            args=args,
            ok=True,
            output=content,
            error=None,
        )
        return ToolResult(
            call_id=call_id,
            ok=True,
            exit_code=0,
            content=content,
            structured={"count": len(items)},
            elapsed_ms=0.0,
        )

    def _handle_memory_commit(
        self,
        trace: TurnTrace,
        call_id: str,
        name: str,
        args: dict[str, JsonValue],
        speak: bool,
    ) -> ToolResult:
        """WO-9 A2 (ADR-010): grounded memory_commit.

        The model's {s, p, o, quote} is a CANDIDATE only. The fact is committed
        iff the quote is verbatim-grounded in the user's own words this turn
        (FactExtractor -> DerivedFactSigner -> USER_DERIVED, source_entry_ids
        citing the USER_EXPLICIT transcript). Model-authored prose is never
        stored (ADR-006); ungrounded candidates are refused with an honest
        error the model must narrate.
        """
        from pydantic import ValidationError  # noqa: PLC0415

        from lucca.memory.extraction import FactExtractor  # noqa: PLC0415
        from lucca.sandbox.schemas import TOOL_ARG_SCHEMAS, MemoryCommitArgs  # noqa: PLC0415

        if not self.memory_store:
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr="memory subsystem unavailable",
                elapsed_ms=0.0,
            )
        try:
            schema_cls = TOOL_ARG_SCHEMAS.get("memory_commit", MemoryCommitArgs)
            parsed = schema_cls.model_validate(args)
            if not isinstance(parsed, MemoryCommitArgs):
                parsed = MemoryCommitArgs.model_validate(args)
        except ValidationError as exc:
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    f"invalid_arguments: {exc}. Provide s, "
                    "p (lowercase snake_case slug, 2-41 chars), o, "
                    "and a verbatim quote from the user's words this turn."
                ),
                elapsed_ms=0.0,
            )

        canon_p = canonicalize_predicate(parsed.p)
        if not is_valid_predicate(canon_p):
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    f"invalid_predicate: '{parsed.p}' is not a valid "
                    "lowercase snake_case slug (2-41 chars)"
                ),
                elapsed_ms=0.0,
            )

        # Ensure the user's utterance is committed so the fact can cite it.
        transcript_payload = getattr(self, "_last_transcript_signed", None)
        payload_is_current = (
            transcript_payload is not None
            and getattr(transcript_payload, "trace_id", None) == trace.trace_id
        )
        if not payload_is_current and self.current_turn_transcript:
            entry_id = self._commit_transcript(self.current_turn_transcript, trace)
            if entry_id:
                self._early_transcript_commit = (entry_id, self.current_turn_transcript)
                self.current_turn_transcript = None
            transcript_payload = getattr(self, "_last_transcript_signed", None)
            payload_is_current = (
                transcript_payload is not None
                and getattr(transcript_payload, "trace_id", None) == trace.trace_id
            )
        if not payload_is_current or transcript_payload is None:
            self._record_tool_receipt(
                name=name,
                call_id=call_id,
                args=args,
                ok=False,
                output=None,
                error="no user utterance to ground against",
            )
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    "not_grounded: there is no user utterance this turn to ground the fact "
                    "against. Ask the user to state the fact in their own words first."
                ),
                elapsed_ms=0.0,
            )

        extractor = getattr(self, "_fact_extractor", None)
        if extractor is None:
            extractor = FactExtractor(master_key=self.signer_factory.master_key)
            self._fact_extractor = extractor

        try:
            signed_facts = extractor.extract_and_sign(
                transcript_payload,
                [{"s": parsed.s, "p": parsed.p, "o": parsed.o, "quote": parsed.quote}],
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("extract_and_sign_failed", error=str(exc))
            self._record_tool_receipt(
                name=name, call_id=call_id, args=args, ok=False, output=None, error=str(exc)
            )
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=f"memory_commit failed: {exc}",
                elapsed_ms=0.0,
            )

        if not signed_facts:
            self._record_tool_receipt(
                name=name,
                call_id=call_id,
                args=args,
                ok=False,
                output=None,
                error="quote not grounded in user utterance",
            )
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    "not_grounded: the fact was NOT saved because the quote does not appear "
                    "verbatim in the user's words this turn. Say plainly that you did not save "
                    "it, or ask the user to say the fact in their own words."
                ),
                structured={"error": "not_grounded", "memory_eligible": False},
                elapsed_ms=0.0,
            )

        now = self.clock.now_utc()
        saved_contents: list[str] = []
        for signed_fact in signed_facts:
            self.memory_store.commit(signed_fact, now=now)
            saved_contents.append(str(signed_fact.content))

        saved_str = "; ".join(saved_contents)
        self._record_tool_receipt(
            name=name, call_id=call_id, args=args, ok=True, output=saved_str, error=None
        )
        logger.info("grounded_memory_commit", facts=saved_str, trace_id=trace.trace_id)
        if speak:
            spoken = "Saved that to memory."
            self._speak_text(trace, spoken)
            self.current_turn_tool_spoken.append(spoken)
        return ToolResult(
            call_id=call_id,
            ok=True,
            exit_code=0,
            content=f"Saved to long-term memory: {saved_str}",
            structured={"saved": saved_contents, "provenance": "USER_DERIVED"},
            elapsed_ms=0.0,
        )

    # delegate — kept for test/back-compat
    def _request_confirmation(
        self,
        trace: TurnTrace,
        name: str,
        args: dict[str, JsonValue],
        timeout_s: float = 15.0,
    ) -> bool:
        return self.confirmations.request_confirmation(trace, name, args, timeout_s=timeout_s)

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
            from pydantic import ValidationError  # noqa: PLC0415

            from lucca.sandbox.schemas import TOOL_ARG_SCHEMAS, InvokeSkillArgs  # noqa: PLC0415

            schema_cls = TOOL_ARG_SCHEMAS.get("invoke_skill", InvokeSkillArgs)
            try:
                parsed_is = schema_cls.model_validate(args)
                skill_id = str(getattr(parsed_is, "skill_id", ""))
                raw_skill_args = getattr(parsed_is, "args", {})
                skill_args: dict[str, JsonValue] = (
                    dict(raw_skill_args) if isinstance(raw_skill_args, dict) else {}
                )
            except ValidationError as exc:
                self.current_turn_tool_ok = False
                self._record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=f"invalid_arguments: {exc}",
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
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
                    elif isinstance(sub_action, AssertFact):
                        self._commit_lisp_assertion(sub_action, trace)
                        sub_results.append(f"assert({sub_action.s} {sub_action.p} {sub_action.o})->ok")
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
                    elif isinstance(sub_action, AssertFact):
                        self._commit_lisp_assertion(sub_action, trace)
                        sub_results.append(f"assert({sub_action.s} {sub_action.p} {sub_action.o})->ok")
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
        human_confirmed = False
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
            human_confirmed = True

        # WO-9 A2 (ADR-010): grounded memory_commit — orchestrator-side dispatch
        # because it must cite the current-turn USER_EXPLICIT transcript payload.
        if name == "memory_commit":
            return self._handle_memory_commit(trace, call_id, name, args, speak)

        # WO-9 A14 (F18): model-callable self-history — "did you actually do X?"
        # answered from persisted records, never confabulated.
        if name == "self_history_search":
            return self._handle_self_history_search(call_id, args)

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
            # (WO-10.6: config-driven via heuristics.toml)
            recent_ctx = " ".join(
                m.get("content", "") for m in self.history[-2:] if isinstance(m, dict)
            )
            context_text = f"{self.current_turn_transcript or ''} {recent_ctx}".lower()
            category_keywords = load_heuristics("search_category_keywords")
            for kw in category_keywords:
                if kw in context_text and kw not in q.lower():
                    q = f"{q} {kw}".strip()
            args["query"] = q

        res = self.sandbox.execute_tool(
            call_id=call_id,
            tool_name=name,
            args=args,
            confirmed=True,
            human_confirmed=human_confirmed,
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
        self._confirm_event.set()
        self.speech_output.stop()
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
