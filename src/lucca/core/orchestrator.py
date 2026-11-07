"""
Project Lucca — Central Orchestrator & State Machine
Spec 01 §3, §4, §6, Spec 10, ADR-008
"""

import base64
import io
import json
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time
import urllib.parse
import wave
from collections import deque
from collections.abc import Sequence
from typing import Literal

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
from pydantic import JsonValue, ValidationError

from lucca.brain.chunker import StreamingChunker, sanitize_for_voice
from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import (
    build_planning_messages,
    get_all_tool_definitions,
    set_persona,
)
from lucca.core.affect import AffectSignal, AffectTracker
from lucca.core.bdi_validator import SpeculativeBDIValidator
from lucca.core.belief_service import BeliefService
from lucca.core.capabilities import dispatch_invoke_skill
from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.clock import SystemClock
from lucca.core.coherence import (
    ToolReceipt,
    detect_promised_action_claims,
    detect_ungrounded_action_claims,
)
from lucca.core.config import get_config, load_heuristics
from lucca.core.confirmation_manager import ConfirmationManager
from lucca.core.corroboration import (
    CQAnswer,
    CriticalQuestionResult,
    Scheme,
    adjust_confidence,
    critical_questions,
    detect_premise_scheme,
    extract_receipt_source,
)
from lucca.core.cognitive_sink import CognitiveOutcomeSink
from lucca.core.episode_recall import EpisodeRecall
from lucca.memory.episodic_code_cache import EpisodicCodeCache
from lucca.core.ipc_schemas import (
    Envelope,
    PlayAbortPayload,
    PlayBeginPayload,
    PTTReleasedPayload,
    UIConfigUpdatePayload,
    UIConfirmResultPayload,
    UIStatePayload,
    UIUserTextPayload,
    decode_envelope,
    encode_envelope,
)
from lucca.core.memory_commit_service import (
    MemoryCommitService,
)
from lucca.core.proof_policy import (
    is_cross_reference_command,
    load_ratification_domains,
    meets_standard,
    required_standard,
    required_threshold,
)
from lucca.core.reasoning_context import ProofTraceStep, ReasoningContext, ReasoningEntry
from lucca.core.schemas import (
    AssertFact,
    ChatMessage,
    DecisionRecord,
    ExecutionTier,
    GoalPlan,
    InferenceStep,
    MemoryHit,
    PendingRatification,
    Provenance,
    RetrievalQuery,
    RouteAction,
    RouteDecision,
    RuleOutcome,
    RuleState,
    Say,
    SignedPayload,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
    ToolResult,
    TTSChunk,
    UnsignedPayload,
    canonicalize_predicate,
    is_valid_predicate,
    standard_for_confidence,
)
from lucca.core.self_diagnosis import Diagnosis, DiagnosisEngine
from lucca.core.signer_factory import SignerFactory
from lucca.core.speech_output_manager import SpeechOutputManager
from lucca.core.speech_stream_pipeline import SpeechStreamPipeline
from lucca.core.text_utils import normalize_transcript
from lucca.core.tool_dispatcher import ToolDispatcher
from lucca.core.trace import TurnTrace, log_turn_trace, now_ns
from lucca.core.turn_pipeline import (
    SubTurnScratchpadBuffer,
    TurnInput,
    TurnPipeline,
    normalize_spelled_words,
    synthesize_plan_narration,
)
from lucca.core.active_goals import ActiveGoalManager
from lucca.core.tool_shortlister import check_tool_fit
from lucca.core.user_model import UserModel
from lucca.core.visual_session import VisualSessionStore
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine, is_rollup_due
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    ToolResultSigner,
    UserSpeechSigner,
)
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
from lucca.sandbox.preflight import extract_python_code
from lucca.sandbox.schemas import EXTRA_TOOL_SCHEMAS, TOOL_ARG_SCHEMAS, PreflightResult
from lucca.sandbox.service import SandboxService
from lucca.senses.asr import ASRWorker
from lucca.senses.ring_buffer import (
    FLAG_ABORT,
    FLAG_EOS,
    get_capture_ring,
    get_playback_ring,
)
from lucca.senses.tts import TTSWorker
from lucca.senses.verifier import VerifierWorker

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
    "normalize_transcript",
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

    @property
    def _cancel_token(self) -> threading.Event:
        if not hasattr(self, "_cancel_token_evt") or self._cancel_token_evt is None:
            self._cancel_token_evt = threading.Event()
        return self._cancel_token_evt

    @_cancel_token.setter
    def _cancel_token(self, val: threading.Event) -> None:
        self._cancel_token_evt = val

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
        verifier: VerifierWorker | None = None,
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
        # Sovereignty covenant (owner decision): no content screen sits at the
        # speech boundary. Safety defenses guard actions (sandbox, tool
        # whitelist, SequenceGuard, output supervisor), never speech.
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
        self.last_turn_receipts: list[ToolReceipt] = []
        self.current_turn_plan: GoalPlan | None = None
        self.last_spoken_plan_narration: str | None = None
        self.last_spoken_diagnosis: str | None = None
        self.pending_spoken_updates: deque[str] = deque()
        self.current_turn_tier: ExecutionTier = ExecutionTier.FULL_LOOP

        # Confirmation Manager (Spec §3, §7, WO-9 A1, WO-18b)
        self.confirmations = ConfirmationManager(orchestrator=self)

        # Turn context
        self.active_trace: TurnTrace | None = None
        self.active_turn_thread: threading.Thread | None = None
        self._cancel_token: threading.Event = threading.Event()
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
                self.router.embed_worker = getattr(self.memory_store.embedding_port, "worker", None)

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
        self.action_signer: ToolResultSigner | None = self.signer_factory.tool_result()

        # MiniLM NLI Semantic Verifier Subsystem (Spec 04 §3, Spec 11 §4, WO-37 Phase 2)
        if verifier is not None:
            self.verifier: VerifierWorker | None = verifier
        else:
            try:
                v_cfg = getattr(self.config, "verifier", None)
                v_dir = (
                    Path(getattr(v_cfg, "model_dir", r"C:\ProjectLucca\models\verifier_minilm"))
                    if v_cfg
                    else Path(r"C:\ProjectLucca\models\verifier_minilm")
                )
                v_timeout = float(getattr(v_cfg, "timeout_ms", 50.0)) if v_cfg else 50.0
                self.verifier = VerifierWorker(model_dir=v_dir, timeout_ms=v_timeout)
            except Exception as _v_exc:
                logger.debug("orchestrator_verifier_init_skipped", error=str(_v_exc))
                self.verifier = None

        verifier_inst = self.verifier

        # Autobiographical Reflection Engine (Spec §7, D-MEM-04, WP-2 & WO-36 Milestone 36.3)
        if reflection_engine is not None:
            self.reflection_engine: ReflectionEngine | None = reflection_engine
        elif self.memory_store is not None and hasattr(self.memory_store, "db"):
            self.reflection_engine = ReflectionEngine(
                db=self.memory_store.db,
                store=self.memory_store,
                master_key=effective_key,
                rule_engine=self.rule_engine,
                verifier=verifier_inst,
                llm=self.llm,
            )
        elif self.db is not None and self.memory_store is not None:
            self.reflection_engine = ReflectionEngine(
                db=self.db,
                store=self.memory_store,
                master_key=effective_key,
                rule_engine=self.rule_engine,
                verifier=verifier_inst,
                llm=self.llm,
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

        # WO-21 Phase 3: Proactive Web-Fact Ratification & Cross-Reference
        self.ratification_domains: set[str] = load_ratification_domains()
        try:
            from lucca.core.neural_hazard_classifier import get_neural_hazard_classifier

            get_neural_hazard_classifier()
        except Exception as _nh_exc:  # noqa: BLE001
            logger.debug("orchestrator_hazard_classifier_warmup_skipped", error=str(_nh_exc))
        self._pending_ratification: PendingRatification | None = None
        self._ratification_offered_this_turn: bool = False
        self._last_ratified_claim: str | None = None
        self.cross_reference_search_fn: object = None

        # WO-36 Milestone 36.2: First-Class Shared Active Goal State Machine
        self.active_goals = ActiveGoalManager(db=self.db)
        if self.memory_store is not None and hasattr(self.memory_store, "retriever"):
            self.memory_store.retriever.active_goals = self.active_goals

        # WO-21 Phase 4 & WO-36: Semantic Theory of Mind User Model & Goal-Biased CBR Episode Recall
        embed_port = getattr(self.memory_store, "embedding_port", None) if self.memory_store else None
        self.user_model = UserModel(db=self.db, embedder=embed_port, verifier=verifier_inst)
        self.episode_recall = EpisodeRecall(
            db=self.db,
            embedder=embed_port,
            active_goals=self.active_goals,
        )

        # WO-22 Phase 2: Diagnostic Self-Reasoning Engine (Fault Model v1)
        self.diagnosis_engine = DiagnosisEngine(db=self.db)

        # WO-36: Sovereign Cognitive Outcome Sink (Milestone 36.1)
        self.cognitive_sink = CognitiveOutcomeSink(
            action_signer=self.action_signer,
            reasoning_context=self.current_reasoning_context,
            episode_recall=self.episode_recall,
            affect_machine=self.affect_tracker.ode_machine if self.affect_tracker else None,
            db=self.db,
        )
        self.cognitive_outcome_sink = self.cognitive_sink

        # WO-39 Milestone 2.2: Case-Based Reasoning (4 Rs) Episodic Code Cache & Impasse Backlog
        _cache_path = self.config.home_dir / self.config.paths.data / "episodic_solutions.json"
        self.episodic_code_cache = EpisodicCodeCache(cache_file=_cache_path, db=self.db)
        self._ensure_impasse_backlog_table()

        # WO-36 Milestone 36.3: Two-Cadence Inner Life & Waking Continuity
        self.last_turn_timestamp: float = time.time()
        self._last_idle_pulse_ts: float = 0.0
        self.idle_pulse = getattr(self.reflection_engine, "idle_pulse", None)
        self.dream_retrospective = getattr(self.reflection_engine, "dream_retrospective", None)

        # WO-37 Phase 0: Local Session Image Cache
        self._pending_image_b64: str | None = None
        _img_store_dir = self.config.home_dir / self.config.paths.data / "sessions" / "images"
        self.visual_session: VisualSessionStore = VisualSessionStore(_img_store_dir)

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
    def diagnosis_engine(self) -> DiagnosisEngine:
        engine = getattr(self, "_diagnosis_engine", None)
        if engine is None:
            engine = DiagnosisEngine(db=getattr(self, "db", None))
            self._diagnosis_engine = engine
        return engine

    @diagnosis_engine.setter
    def diagnosis_engine(self, value: DiagnosisEngine) -> None:
        self._diagnosis_engine = value

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
    def speech_stream(self) -> SpeechStreamPipeline:
        pipe = getattr(self, "_speech_stream", None)
        if pipe is None:
            pipe = SpeechStreamPipeline(orchestrator=self)
            self._speech_stream = pipe
        return pipe

    @speech_stream.setter
    def speech_stream(self, value: SpeechStreamPipeline) -> None:
        self._speech_stream = value

    @property
    def tool_dispatcher(self) -> ToolDispatcher:
        disp = getattr(self, '_tool_dispatcher', None)
        if disp is None:
            disp = ToolDispatcher(orchestrator=self)
            self._tool_dispatcher = disp
        return disp

    @tool_dispatcher.setter
    def tool_dispatcher(self, value: ToolDispatcher) -> None:
        self._tool_dispatcher = value

    @property
    def _tts_queue(
        self,
    ) -> queue.Queue[
        tuple[TurnTrace, int, str] | tuple[TurnTrace, int, str, threading.Event | None] | None
    ]:
        return self.speech_output.tts_queue

    @_tts_queue.setter
    def _tts_queue(
        self,
        val: queue.Queue[
            tuple[TurnTrace, int, str] | tuple[TurnTrace, int, str, threading.Event | None] | None
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
                self._on_user_text(env.ts_ns, p_text.text, p_text.image_b64)
            elif env.type == "ui.attach_image":
                raw_img = env.payload.get("image_b64") if isinstance(env.payload, dict) else None
                if raw_img and isinstance(raw_img, str):
                    self._pending_image_b64 = raw_img
                    if hasattr(self, "visual_session") and self.visual_session is not None:
                        self.visual_session.store_image(b64_jpeg=raw_img, description="user_upload")
                    logger.info("ui_image_attached_to_session", size_bytes=len(raw_img))
            elif env.type == "ui.clear_image":
                self._pending_image_b64 = None
                if hasattr(self, "visual_session") and self.visual_session is not None:
                    self.visual_session.clear()
                logger.debug("ui_image_cleared_from_session")
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
            elif env.type in ("ui.talk_press", "ui.talk_release", "audio.rms"):
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
        elif (
            self.state in ("speaking", "thinking")
            or (self.active_turn_thread is not None and self.active_turn_thread.is_alive())
        ):
            # Instant cooperative barge-in / cancellation (WO-26 Phase 2)
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

        # 1. Signal explicit cooperative cancellation token first (WO-26 Phase 2)
        self._cancel_token.set()
        if self.active_trace:
            self.active_trace.interrupted = True

        # 2. Terminate in-flight LLM streaming request (aborts socket/HTTP generator and releases slot)
        target_trace_id = self.active_trace.trace_id if self.active_trace else None
        self.llm.abort(trace_id=target_trace_id)
        self.chunker.reset()

        # 3. F-CORE-017: drain TTS synthesis queue before setting FLAG_ABORT
        self.speech_output.clear_queue()
        self.play_ring.set_flag(FLAG_ABORT)

        # 4. Notify audio to abort output immediately
        trace_id = self.active_trace.trace_id if self.active_trace else ""
        abort_env = Envelope(
            type="play.abort",
            trace_id=trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayAbortPayload(trace_id=trace_id).model_dump(),
        )
        self._publish_bus(abort_env)

        # 5. Cooperative drain: cleanly join running turn worker within 500ms (WO-26 Phase 2)
        if self.active_turn_thread and self.active_turn_thread is not threading.current_thread():
            self.active_turn_thread.join(timeout=0.5)
            if self.active_turn_thread.is_alive():
                logger.warning("turn_thread_drain_timeout", thread=self.active_turn_thread.name)
            else:
                logger.debug("turn_thread_drained_cleanly", thread=self.active_turn_thread.name)
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

    def _on_user_text(self, ts_ns: int, user_text: str, image_b64: str | None = None) -> None:
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

        if image_b64:
            self._pending_image_b64 = image_b64
            if hasattr(self, "visual_session") and self.visual_session is not None:
                self.visual_session.store_image(b64_jpeg=image_b64, description="user_upload")

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
        self, transcript: str, mode: Literal["audio", "transcript", "vision"] = "transcript"
    ) -> RuleState:
        norm_transcript = normalize_transcript(transcript)
        local_now = time.localtime()
        last_tool_val = self.executed_tools[-1][0] if self.executed_tools else None
        intent, auto_conf, entities = self.router.classify_intent(
            norm_transcript, last_tool=last_tool_val
        )
        return RuleState(
            schema_version=1,
            transcript=norm_transcript,
            transcript_lower=norm_transcript.strip().lower(),
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
        self,
        action: AssertFact,
        trace: TurnTrace | None = None,
        *,
        llm_inferred: bool = False,
    ) -> SignedPayload | None:
        """Commits an AssertFact action as a signed envelope (WO-20 Phase 1).

        P0 provenance split: deterministic rule-engine output is signed
        LISP_ASSERTION (grounding-eligible); LLM-proposed deduction steps are
        signed LLM_INFERRED_ASSERTION (memory-eligible, never grounding-eligible
        until re-derived deterministically or Z3-verified).
        """
        if not self.memory_store:
            return None
        if llm_inferred:
            signer = self.signer_factory.inferred_assertion()
            provenance = Provenance.LLM_INFERRED_ASSERTION
        else:
            signer = self.signer_factory.lisp_assertion()
            provenance = Provenance.LISP_ASSERTION
        now = self.clock.now_utc() if hasattr(self, "clock") and self.clock else time.time()
        trace_id = trace.trace_id if trace else f"trace-{ulid.ULID()}"
        unsigned = UnsignedPayload(
            content=f"{action.s} {action.p} {action.o}",
            provenance=provenance,
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

        # WO-21 Phase 1: Check standard of proof for memory_commit_inferred (CLEAR_AND_CONVINCING = 0.75)
        if not meets_standard(confidence, "memory_commit_inferred"):
            logger.info(
                "finalize_chain_refused_below_standard",
                confidence=confidence,
                required=required_threshold("memory_commit_inferred"),
                standard=required_standard("memory_commit_inferred").value,
                conclusion=f"{final_entry.s} {final_entry.p} {final_entry.o}",
            )
            return None

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
                "proof_standard": standard_for_confidence(confidence).value,
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

    def _validate_premise(self, premise: str, context: ReasoningContext) -> tuple[bool, str | None]:
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

        # 2. Direct signed tool receipt check
        receipts = getattr(self, "current_turn_receipts", []) or []
        executed = getattr(self, "executed_tools", []) or []
        clean_lower = clean.lower()
        for r in list(receipts) + list(executed):
            ok = getattr(r, "ok", True)
            if not ok:
                continue
            out = (
                str(getattr(r, "output", "") or "")
                or str(getattr(r, "content", "") or "")
                or str(getattr(r, "structured", "") or "")
            ).lower()
            if clean_lower in out or all(
                word in out for word in clean_lower.split() if len(word) > 2
            ):
                return (True, None)

        # 3. Reasoning context check (intermediate facts in current chain)
        if context.resolve_premise(clean) is not None:
            return (True, None)
        for intermediate in context.intermediates:
            if (
                intermediate.conclusion.lower() == clean.lower()
                or intermediate.envelope_id == clean
            ):
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

                    # Structured (s, p, o) triple or multi-token grounded proposition check
                    cur.execute(
                        """
                        SELECT m.content, e.payload_json
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1
                          AND m.valid_to IS NULL
                        ORDER BY m.created_at DESC
                        LIMIT 100
                        """
                    )
                    rows = cur.fetchall()
                    verifier_inst = getattr(self, "verifier", None)
                    for row_content, row_payload_json in rows:
                        mem_text = str(row_content or "").strip()
                        if not mem_text:
                            continue
                        # Structured (s, p, o) triple match
                        if row_payload_json:
                            try:
                                pj = json.loads(str(row_payload_json))
                                st = pj.get("structured") if isinstance(pj, dict) else None
                                if isinstance(st, dict) and {"s", "p", "o"} <= set(st.keys()):
                                    triple_str = f"{st['s']} {st['p']} {st['o']}".strip().lower()
                                    if triple_str == clean.lower():
                                        return (True, None)
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("premise_struct_json_parse_error", error=str(exc))
                        # VerifierWorker NLI entailment check (>= 0.75)
                        if verifier_inst is not None and hasattr(
                            verifier_inst, "check_consistency"
                        ):
                            try:
                                v_res = verifier_inst.check_consistency(
                                    premise=mem_text, hypothesis=clean
                                )
                                if (
                                    not getattr(v_res, "degraded", False)
                                    and str(getattr(v_res, "label", "")).upper().endswith("ENTAILMENT")
                                    and float(getattr(v_res, "score", 0.0)) >= 0.75
                                ):
                                    return (True, None)
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("premise_verifier_check_error", error=str(exc))
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
                        if clean.lower() in h.content.lower() or (
                            words and all(w in h.content.lower() for w in words)
                        ):
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

    def _evaluate_step_corroboration(
        self, step: InferenceStep, context: ReasoningContext | None = None
    ) -> list[CriticalQuestionResult]:
        """Evaluates Walton critical questions for attributed or grounding premises (WO-21/23)."""
        has_attributed = any(
            re.match(r"^(.+?)\s+asserts\s+(.+)$", p.strip(), re.IGNORECASE) for p in step.premises
        )
        receipts = list(getattr(self, "current_turn_receipts", []) or []) + list(
            getattr(self, "executed_tools", []) or []
        )
        scheme, ambig_note = detect_premise_scheme(step)

        if has_attributed or scheme != Scheme.AUTHORITY:
            if ambig_note and ambig_note not in step.conditions and len(step.conditions) < 8:
                step.conditions.append(ambig_note)
            try:
                q_results = critical_questions(
                    scheme, step, store=self.memory_store, receipts=receipts
                )
                eff_conf, new_conditions = adjust_confidence(
                    step.confidence, q_results, scheme=scheme
                )
                step.confidence = eff_conf
                for cond in new_conditions:
                    if cond not in step.conditions and len(step.conditions) < 8:
                        step.conditions.append(cond)
                return q_results
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "critical_questions_failed", scheme=str(scheme), error=str(exc)
                )
                return []

        # Check if supported by >= 2 independent grounding premises (WO-21 Phase 6)
        effective_ctx = context or getattr(self, "current_reasoning_context", None)
        ctx_conclusions = {
            e.conclusion.lower() for e in (effective_ctx.intermediates if effective_ctx else [])
        }
        ctx_env_ids = {
            e.envelope_id for e in (effective_ctx.intermediates if effective_ctx else [])
        }
        if len(step.premises) >= 2 and self.db is not None:
            try:
                premise_eids: list[str] = []
                with self.db.read_cursor() as cur:
                    for prem in step.premises:
                        clean_prem = prem.strip()
                        if clean_prem.lower() in ctx_conclusions or clean_prem in ctx_env_ids:
                            continue
                        cur.execute(
                            """
                            SELECT m.entry_id
                            FROM memories m
                            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                            WHERE e.grounding_eligible = 1
                              AND m.valid_to IS NULL
                              AND (m.content = ? OR m.content = ? OR m.content LIKE ?)
                            """,
                            (clean_prem, clean_prem.lower(), f"%{clean_prem}%"),
                        )
                        for r in cur.fetchall():
                            if str(r[0]) not in premise_eids and str(r[0]) not in ctx_env_ids:
                                premise_eids.append(str(r[0]))
                                break

                if len(premise_eids) >= 2:
                    q_corrob = CriticalQuestionResult(
                        question=(
                            "Is the claim corroborated by an independent grounding-eligible fact?"
                        ),
                        answer=CQAnswer.SATISFIED,
                        count=len(premise_eids),
                        evidence_entry_ids=premise_eids,
                        sources=["store"],
                        detail=(
                            f"Corroborated by {len(premise_eids)} independent "
                            "grounding premises in store"
                        ),
                    )
                    # Check for conflicting facts in store
                    dispute_eids: list[str] = []
                    dispute_details: list[str] = []
                    if step.s and step.p:
                        with self.db.read_cursor() as cur:
                            cur.execute(
                                """
                                SELECT m.entry_id, m.content, e.signer_id
                                FROM memories m
                                JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                                WHERE e.grounding_eligible = 1
                                  AND m.valid_to IS NULL
                                  AND m.content LIKE ?
                                """,
                                (f"{step.s} {step.p} %",),
                            )
                            for row in cur.fetchall():
                                eid, content, signer = row
                                parts = content.strip().split()
                                if len(parts) >= 3 and parts[2].lower() != step.o.lower():
                                    dispute_eids.append(str(eid))
                                    dispute_details.append(
                                        f"{content} contradicts {step.s} {step.p} {step.o}"
                                    )

                    if dispute_eids:
                        q_dispute = CriticalQuestionResult(
                            question="Is the claim disputed by any grounding-eligible fact?",
                            answer=CQAnswer.SATISFIED,
                            count=len(dispute_eids),
                            evidence_entry_ids=dispute_eids,
                            sources=["store"],
                            detail=dispute_details[0],
                        )
                    else:
                        q_dispute = CriticalQuestionResult(
                            question="Is the claim disputed by any grounding-eligible fact?",
                            answer=CQAnswer.UNKNOWN,
                            count=0,
                            evidence_entry_ids=[],
                            sources=[],
                            detail="No disputes found",
                        )

                    q_results = [q_corrob, q_dispute]
                    eff_conf, new_conditions = adjust_confidence(step.confidence, q_results)
                    step.confidence = eff_conf
                    for cond in new_conditions:
                        if cond not in step.conditions and len(step.conditions) < 8:
                            step.conditions.append(cond)
                    return q_results
            except Exception as exc:  # noqa: BLE001
                logger.warning("premise_corroboration_failed", error=str(exc))

        return []

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

        ctx = (
            context
            if context is not None
            else (getattr(self, "current_reasoning_context", None) or ReasoningContext())
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
        for r in getattr(self, "current_turn_receipts", []) or []:
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
                q_results = self._evaluate_step_corroboration(step)
                # P0 split: LLM-proposed step signs as LLM_INFERRED_ASSERTION
                # (never grounding-eligible until re-derived deterministically).
                action = AssertFact(s=step.s, p=step.p, o=step.o)
                signed = self._commit_lisp_assertion(action, trace, llm_inferred=True)
                env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
                ctx.add_intermediate(
                    envelope_id=env_id,
                    s=step.s,
                    p=step.p,
                    o=step.o,
                    confidence=step.confidence,
                    step_kind="llm_abductive",
                    rule_id="llm",
                    premises=list(step.premises),
                    conditions=list(step.conditions),
                    critical_questions=[q.to_dict() for q in q_results],
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
                        if (
                            prem not in step_to_evaluate.conditions
                            and len(step_to_evaluate.conditions) < 8
                        ):
                            step_to_evaluate.conditions.append(prem)
                    ok, _ = self._validate_premise(prem, ctx)
                    if not ok:
                        still_unverified.append(prem)

                if not still_unverified:
                    # Revised step accepted!
                    q_results = self._evaluate_step_corroboration(step_to_evaluate)
                    action = AssertFact(
                        s=step_to_evaluate.s, p=step_to_evaluate.p, o=step_to_evaluate.o
                    )
                    signed = self._commit_lisp_assertion(
                        action, trace, llm_inferred=True
                    )  # P0 split: LLM-proposed step
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
                        critical_questions=[q.to_dict() for q in q_results],
                    )
                    accepted_steps.append(step_to_evaluate)
                    continue

            # 2. Memory retry
            retry_premise = still_unverified[0] if still_unverified else missing_premise
            recovered = self._search_memory_for_premise(retry_premise)
            if recovered:
                target = step_to_evaluate if step_to_evaluate is not None else step
                q_results = self._evaluate_step_corroboration(target)
                action = AssertFact(s=target.s, p=target.p, o=target.o)
                signed = self._commit_lisp_assertion(
                    action, trace, llm_inferred=True
                )  # P0 split: LLM-proposed step
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
                    critical_questions=[q.to_dict() for q in q_results],
                )
                accepted_steps.append(target)
                continue

            # 3. Ask the user (named-gap question) vs 4. Named-gap abstention
            is_personal = any(
                k in retry_premise.lower()
                for k in ("user", "you", "live", "from", "born", "home", "partner")
            )
            if is_personal:
                spoken = f"I don't have anything verified about {retry_premise} — can you tell me about it?"
            else:
                spoken = f"I can't verify {retry_premise}, so I can't deduce that yet."

            logger.info("gather_ladder_terminated", outcome=spoken, missing_premise=retry_premise)
            if hasattr(self, "_speak_text") and trace:
                self._speak_text(trace, spoken)
            return (accepted_steps, spoken)

        if accepted_steps and len(ctx) > 0:
            committed = self.finalize_chain(ctx, trace)
            if committed is None:
                final_entry = ctx[-1]
                proof_trace_steps = ctx.proof_trace()
                conf = min(s.confidence for s in proof_trace_steps) if proof_trace_steps else 1.0
                if conf < 0.50:
                    spoken = f"I'm guessing {final_entry.s} {final_entry.p} {final_entry.o}, but that's just speculation."
                else:
                    spoken = f"I think {final_entry.s} {final_entry.p} {final_entry.o}, but I'm not sure enough to keep it."
                logger.info(
                    "chain_concluded_speculation",
                    confidence=conf,
                    spoken=spoken,
                    conclusion=f"{final_entry.s} {final_entry.p} {final_entry.o}",
                )
                if hasattr(self, "_speak_text") and trace:
                    self._speak_text(trace, spoken)
                return (accepted_steps, spoken)
            else:
                final_entry = ctx[-1]
                conditions = list(final_entry.conditions or [])
                if conditions:
                    spoken = self._format_conditioned_speech(final_entry, conditions)
                    if spoken:
                        logger.info(
                            "chain_concluded_conditioned",
                            confidence=final_entry.confidence,
                            spoken=spoken,
                            conclusion=f"{final_entry.s} {final_entry.p} {final_entry.o}",
                        )
                        if hasattr(self, "_speak_text") and trace:
                            self._speak_text(trace, spoken)
                        return (accepted_steps, spoken)
        return (accepted_steps, None)

    def _format_conditioned_speech(
        self, final_entry: ReasoningEntry, conditions: list[str]
    ) -> str | None:
        """Formats spoken output for a committed chain with carried conditions (WO-21 Phase 6)."""
        if not conditions:
            return None

        # Prioritize explicit 'if ...' condition
        if_cond = next(
            (
                c.strip()
                for c in conditions
                if re.match(r"^(?:…|\.\.\.)?\s*if\b", c.strip(), re.IGNORECASE)
            ),
            None,
        )
        if if_cond:
            clean = if_cond
            if not clean.startswith("…") and not clean.startswith("..."):
                clean = f"…{clean}"
            if not clean.endswith("."):
                clean = f"{clean}."
            return clean

        # Otherwise format from attributed premise condition '<source> asserts <claim>'
        attr_cond = next(
            (
                c.strip()
                for c in conditions
                if re.match(r"^(.+?)\s+asserts\s+(.+)$", c.strip(), re.IGNORECASE)
            ),
            None,
        )
        if attr_cond:
            m = re.match(r"^(.+?)\s+asserts\s+(.+)$", attr_cond, re.IGNORECASE)
            if m:
                src, claim = m.group(1).strip(), m.group(2).strip()
                return f"…if {src} is right about {claim}."

        # Fallback to general condition
        cond_text = conditions[0].strip()
        if not cond_text.startswith("…") and not cond_text.startswith("..."):
            cond_text = f"…{cond_text}"
        if not cond_text.endswith("."):
            cond_text = f"{cond_text}."
        return cond_text

    run_deduction_loop = run_deduction_step

    def _parse_and_validate_plan(
        self, text: str, default_goal: str
    ) -> tuple[GoalPlan | None, str | None]:
        """Parses and validates a GoalPlan from LLM response text (WO-22 Phase 1).

        Enforces:
        - JSON extraction and Pydantic GoalPlan schema (order contiguity 1..N, max 8 steps).
        - Registered tool check against TOOL_ARG_SCHEMAS / EXTRA_TOOL_SCHEMAS.
        - Tool argument schema validation.
        - Deontic pre-check via SpeculativeBDIValidator.
        """
        clean_text = text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
        if fence_match:
            clean_text = fence_match.group(1).strip()

        obj_match = re.search(r"\{[\s\S]*\}", clean_text)
        if not obj_match:
            return None, f"No JSON object found in response: {text[:100]}"

        try:
            raw_data = json.loads(obj_match.group(0))
        except Exception as exc:  # noqa: BLE001
            logger.debug("plan_json_parse_failed", error=str(exc))
            return None, f"Malformed JSON in plan: {exc}"

        if not isinstance(raw_data, dict):
            return None, "Expected a JSON object for GoalPlan, got list or scalar."

        if not raw_data.get("plan_id"):
            raw_data["plan_id"] = f"plan-{ulid.ULID()}"
        if not raw_data.get("goal"):
            raw_data["goal"] = default_goal

        try:
            plan = GoalPlan.model_validate(raw_data)
        except ValidationError as exc:
            return None, f"GoalPlan schema validation failed: {exc}"

        # Central Tool-Arg Validation Registry (WO-19a)
        for step in plan.steps:
            schema_cls = TOOL_ARG_SCHEMAS.get(step.tool) or EXTRA_TOOL_SCHEMAS.get(step.tool)
            if schema_cls is None:
                return None, f"Step {step.order}: Tool '{step.tool}' is not registered."
            try:
                schema_cls.model_validate(step.args)
            except ValidationError as exc:
                return (
                    None,
                    f"Step {step.order} ({step.tool}) argument schema validation failed: {exc}",
                )

        # Speculative BDI Invariant Pre-check (Milestone 4 / WO-22 Phase 1)
        bdi_validator = getattr(self, "bdi_validator", None)
        if bdi_validator is not None:
            taint = getattr(self.sandbox, "taint_flags", 0)
            for step in plan.steps:
                bdi_res = bdi_validator.validate_tool_call(step.tool, step.args, taint_flags=taint)
                if not bdi_res.is_valid:
                    reason = bdi_res.reason or "Action prohibited"
                    return (
                        None,
                        f"Step {step.order} ({step.tool}) deontic violation: {reason}",
                    )

        return plan, None

    def run_planning_step(
        self,
        goal: str,
        trace: TurnTrace | None = None,
        llm: object | None = None,
        context: ReasoningContext | None = None,
    ) -> GoalPlan | None:
        """Executes a bounded, validated means-ends plan for a goal (WO-22 Phase 1).

        1. Proposes a GoalPlan via LLM using the planning contract.
        2. Validates plan schema, tool registry, argument schema, and deontic invariants.
        3. On failure: allows one machine-readable revision attempt; if still invalid,
           issues an honest refusal and speaks it.
        4. On success: sets current_turn_plan and disposes steps through existing
           sandbox dispatch path (confirmations, sequence guard, taint tracking).
        5. Aggregates multi-action receipts into honest spoken narration (ITEM-017).
        """
        effective_llm = llm if llm is not None else getattr(self, "llm", None)
        if effective_llm is None:
            logger.warning("no_llm_available_for_planning")
            return None

        ctx = (
            context
            if context is not None
            else (getattr(self, "current_reasoning_context", None) or ReasoningContext())
        )
        self.current_reasoning_context = ctx

        if trace is None:
            trace = getattr(self, "active_trace", None) or TurnTrace(
                trace_id=f"plan-{ulid.ULID()}",
                session_id=getattr(self, "session_id", "session-plan"),
                origin="text",
            )
        trace_id = trace.trace_id

        available_tools = list(TOOL_ARG_SCHEMAS.keys())
        verified_facts: list[str] = [entry.conclusion for entry in ctx.intermediates]

        planning_msgs = build_planning_messages(
            goal=goal,
            available_tools=available_tools,
            verified_facts=verified_facts,
            history=getattr(self, "history", []),
        )

        full_text = ""
        for event in effective_llm.stream_turn(
            current_text=goal,
            memories=[],
            history=getattr(self, "history", []),
            trace_id=trace_id,
            messages=planning_msgs,
        ):
            if isinstance(event, TokenDelta):
                full_text += event.delta

        plan, err = self._parse_and_validate_plan(full_text, default_goal=goal)
        if plan is None:
            logger.warning("planning_initial_validation_failed", error=err, raw=full_text)
            revision_msgs = build_planning_messages(
                goal=goal,
                available_tools=available_tools,
                verified_facts=verified_facts,
                error_feedback=err,
                history=getattr(self, "history", []),
            )
            revised_text = ""
            for event in effective_llm.stream_turn(
                current_text=f"Revise plan to fix error: {err}",
                memories=[],
                history=getattr(self, "history", []),
                trace_id=trace_id,
                messages=revision_msgs,
            ):
                if isinstance(event, TokenDelta):
                    revised_text += event.delta

            plan, err = self._parse_and_validate_plan(revised_text, default_goal=goal)
            if plan is None:
                logger.warning("planning_revision_validation_failed", error=err, raw=revised_text)
                refusal_msg = f"I can't plan that safely because: {err}"
                self._speak_text(trace, refusal_msg)
                self.current_turn_tool_spoken.append(refusal_msg)
                return None

        # Plan ratified & validated — store on turn
        self.current_turn_plan = plan
        executed_tuples: list[tuple[str, dict[str, JsonValue], bool, str]] = []
        cancelled_tuples: list[tuple[str, dict[str, JsonValue]]] = []
        failed_step_order: int | None = None

        for i, step in enumerate(plan.steps):
            resolved_intermediates: list[str] = []
            if ctx is not None and step.purpose:
                resolved_entries = ctx.resolve_purpose_intermediates(step.purpose)
                resolved_intermediates = [e.envelope_id for e in resolved_entries]

            res = self._handle_tool_call(trace, step.tool, dict(step.args), speak=False)
            ok = (res is None) or getattr(res, "ok", True)
            raw_out = ""
            if res is not None:
                raw_out = str(
                    getattr(res, "content", "")
                    or getattr(res, "structured", "")
                    or getattr(res, "stderr", "")
                )

            receipt_entry: dict[str, JsonValue] = {
                "order": step.order,
                "tool": step.tool,
                "args": step.args,
                "ok": ok,
                "result": raw_out,
                "resolved_intermediates": resolved_intermediates,
            }
            plan.receipts.append(receipt_entry)
            executed_tuples.append((step.tool, dict(step.args), ok, raw_out))

            if not ok:
                failed_step_order = step.order
                for rem_step in plan.steps[i + 1 :]:
                    cancelled_tuples.append((rem_step.tool, dict(rem_step.args)))
                break

        # Multi-Action Narration Aggregation (ITEM-017 / D-HON-01)
        narration = synthesize_plan_narration(
            executed_steps=executed_tuples,
            cancelled_steps=cancelled_tuples if failed_step_order is not None else None,
            failed_step_order=failed_step_order,
        )
        plan.narration = narration
        self.last_spoken_plan_narration = narration
        self._speak_text(trace, narration)
        self.current_turn_tool_spoken.append(narration)

        return plan

    def run_self_diagnosis(
        self,
        observations: dict[str, object] | list[str] | str,
        trace: TurnTrace,
    ) -> tuple[list[Diagnosis], str]:
        """Runs the self-diagnosis engine over observed symptoms/telemetry and speaks
        the top diagnosis with hedged natural language (WO-22 Phase 2, Trap 1).

        Returns (diagnoses, spoken_text) so callers can reuse the formatted speech
        without re-invoking format_diagnosis_speech.
        """
        diagnoses = self.diagnosis_engine.diagnose(observations)
        if diagnoses:
            top = diagnoses[0]
            spoken_text = self.diagnosis_engine.format_diagnosis_speech(top)
            self._speak_text(trace, spoken_text)
            self._publish_caption(spoken_text, source="assistant", is_final=True)

            # Record diagnosis as a hedged intermediate in reasoning context (not a committed fact)
            ctx = getattr(self, "current_reasoning_context", None)
            if ctx is None:
                ctx = ReasoningContext()
                self.current_reasoning_context = ctx
            try:
                ctx.add_intermediate(
                    envelope_id=f"diag-{ulid.ULID()}",
                    s="lucca",
                    p="diagnosed_fault",
                    o=top.fault_id,
                    confidence=top.confidence,
                    step_kind="diagnosis",
                    conditions=[f"cause:{top.cause}", f"remedy:{top.suggested_remedy}"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("record_diagnosis_intermediate_failed", error=str(exc))
        else:
            spoken_text = self.diagnosis_engine.format_diagnosis_speech(None)
            self._speak_text(trace, spoken_text)
            self._publish_caption(spoken_text, source="assistant", is_final=True)

        self.last_spoken_diagnosis = spoken_text
        return diagnoses, spoken_text

    def _check_functional_coherence(
        self,
        narration: str,
        receipts: Sequence[ToolReceipt | dict[str, JsonValue] | object] | None = None,
        tool_calls: Sequence[ToolReceipt | dict[str, JsonValue] | object] | None = None,
        user_context: str | Sequence[dict[str, str]] | None = None,
    ) -> str | None:
        """
        Checks for discrepancy between spoken action claim and actual tool execution
        (Spec §3.3, WP-2). Returns breach description if discrepancy detected, else None.
        """
        if receipts is None:
            if tool_calls is not None and any(type(r) is object for r in tool_calls):
                return None
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
                        tool=str(r.get("tool") or r.get("tool_name") or r.get("action") or ""),
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
        claims = detect_ungrounded_action_claims(
            narration,
            norm_receipts,
            verifier=getattr(self, "verifier", None),
            user_context=user_context,
        )
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

            # Build multi-turn context for functional coherence check (Spec §3.3 / v3.0)
            turn_ctx: list[dict[str, str]] = []
            for h_item in getattr(self, "history", [])[-4:]:
                if isinstance(h_item, dict) and h_item.get("role") in ("user", "assistant"):
                    turn_ctx.append(
                        {
                            "role": str(h_item.get("role", "")),
                            "content": str(h_item.get("content", "")),
                        }
                    )
            if user_transcript_text:
                turn_ctx.append({"role": "user", "content": user_transcript_text})

            # Functional coherence check (Spec §3.3 / D-MEM-04 / WP-2)
            breach_msg = self._check_functional_coherence(
                reply_text,
                self.current_turn_receipts,
                user_context=turn_ctx if turn_ctx else user_transcript_text,
            )
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
        self.last_turn_receipts = list(getattr(self, "current_turn_receipts", []))
        self._commit_action_receipts(trace)

        # Contradiction detection on USER_EXPLICIT commit (Spec §7, WP-2)
        if committed_user_id and user_transcript_text:
            self._check_contradictions(committed_user_id, user_transcript_text, trace)
            # WO-9 A3: passive fact extraction from the user's own words
            self._maybe_extract_facts(trace)
            # WO-36 Milestone 36.2: Extract explicit user goal declarations into ActiveGoalManager
            active_goals_mgr = getattr(self, "active_goals", None)
            if active_goals_mgr is not None:
                goal_m = re.search(
                    r"\b(?:my\s+goal\s+is\s+to|our\s+goal\s+is\s+to|let'?s\s+set\s+a\s+goal\s+to)\s+([^.!?\n]+)",
                    user_transcript_text,
                    re.IGNORECASE,
                )
                if goal_m:
                    try:
                        active_goals_mgr.create_goal(
                            title=goal_m.group(1).strip(),
                            provenance=Provenance.USER_EXPLICIT,
                            provenance_envelope_id=committed_user_id,
                        )
                    except Exception as goal_err:  # noqa: BLE001
                        logger.debug("active_goal_extract_failed", error=str(goal_err))

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

    def maybe_run_idle_pulse(self, now: float | None = None) -> object | None:
        """Executes IdlePulse (60s cadence) when orchestrator is idle (WO-36 Milestone 36.3)."""
        if not getattr(self.config.reflection, "enabled", True):
            return None
        pulse_engine = getattr(self, "idle_pulse", None) or (
            getattr(self.reflection_engine, "idle_pulse", None) if self.reflection_engine else None
        )
        if pulse_engine is None:
            return None
        current_time = now if now is not None else time.time()
        idle_sec = float(getattr(self.config.reflection, "idle_seconds", 60))
        last_turn = getattr(self, "last_turn_timestamp", 0.0)
        last_pulse = getattr(self, "_last_idle_pulse_ts", 0.0)
        if (current_time - last_turn) >= idle_sec and (current_time - last_pulse) >= idle_sec:
            try:
                res = pulse_engine.pulse(now=current_time)
                self._last_idle_pulse_ts = current_time
                return res
            except Exception as exc:  # noqa: BLE001
                logger.debug("idle_pulse_execution_failed", error=str(exc))
        return None

    def maybe_run_nightly_rollup(self, now: float | None = None) -> int:
        """Executes nightly roll-up and DreamRetrospective if due and records persistent timestamp."""
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
        """Selects a natural verbal thinking cue (delegates to SpeechStreamPipeline)."""
        return self.speech_stream.select_verbal_cue(tool_name)

    def _stream_llm_speech(
        self,
        trace: TurnTrace,
        user_msg: str,
        decision_id: str | None,
        messages: list[ChatMessage] | None = None,
        current_audio_b64: str | None = None,
        current_image_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        tools: list[object] | None = None,
        max_rounds: int = 8,
        epistemic_context: str | None = None,
        enable_thinking: bool | None = None,
        user_model_directive: str | None = None,
        episode_hints: list[str] | str | None = None,
        grammar: str | None = None,
    ) -> None:
        """Executes streaming LLM response generation (delegates to SpeechStreamPipeline)."""
        self.speech_stream.stream_llm_speech(
            trace=trace,
            user_msg=user_msg,
            decision_id=decision_id,
            messages=messages,
            current_audio_b64=current_audio_b64,
            current_image_b64=current_image_b64,
            current_text=current_text,
            memories=memories,
            tools=tools,
            max_rounds=max_rounds,
            epistemic_context=epistemic_context,
            enable_thinking=enable_thinking,
            user_model_directive=user_model_directive,
            episode_hints=episode_hints,
            grammar=grammar,
        )

    def _ensure_impasse_backlog_table(self) -> None:
        if self.db is None or not hasattr(self.db, "write_transaction"):
            return
        try:
            with self.db.write_transaction() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS impasse_backlog (
                        id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        code TEXT NOT NULL,
                        error_trace TEXT NOT NULL,
                        resolved_code TEXT NOT NULL DEFAULT '',
                        surprise_score REAL NOT NULL DEFAULT 0.85,
                        created_at TEXT NOT NULL,
                        processed INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("impasse_backlog_table_init_error", error=str(exc))

    def _log_impasse_to_backlog(
        self,
        query: str,
        code: str,
        error_trace: str,
        resolved_code: str = "",
        surprise_score: float = 0.85,
    ) -> None:
        """Records a failed or repaired code synthesis episode into impasse_backlog for offline consolidation."""
        if self.db is None or not hasattr(self.db, "write_transaction"):
            return
        try:
            self._ensure_impasse_backlog_table()
            impasse_id = f"imp-{ulid.ULID()}"
            created_iso = str(time.time())
            with self.db.write_transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO impasse_backlog (
                        id, query, code, error_trace, resolved_code, surprise_score, created_at, processed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        impasse_id,
                        query[:1000],
                        code[:4000],
                        error_trace[:2000],
                        resolved_code[:4000],
                        float(surprise_score),
                        created_iso,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("log_impasse_to_backlog_failed", error=str(exc))

    def synthesize_code_with_preflight(
        self,
        prompt: str,
        initial_code: str | None = None,
        trace: TurnTrace | None = None,
        docstring_examples: list[str] | None = None,
        max_repair_rounds: int = 1,
        enable_preflight: bool = True,
    ) -> tuple[str, PreflightResult]:
        """WO-26 Phase 4 & WO-39 Milestone 2.2: Tier 3 Code Synthesis with Case-Based Reasoning (4 Rs)
        and Autonomous Docker Pre-Flight Verification Loop.

        1. Retrieve & Reuse: Queries EpisodicCodeCache for a matching precedent and adapts it.
        2. Revise: Verifies candidate in Docker sandbox; updates precedent (w+, w-) evidence.
        3. Retain: Stores verified programs in EpisodicCodeCache and logs impasses to impasse_backlog.
        """
        t0 = time.perf_counter()
        code_candidate = initial_code
        cbr_cache = getattr(self, "episodic_code_cache", None)
        used_precedent = None

        # CBR Step 1 & 2: Retrieve & Reuse precedent before raw LLM synthesis
        if code_candidate is None and cbr_cache is not None and prompt.strip():
            try:
                precedent = cbr_cache.retrieve_precedent(query=prompt)
                if precedent is not None:
                    adapted = cbr_cache.adapt_and_reuse(precedent, prompt)
                    if adapted and adapted.strip():
                        if not enable_preflight:
                            cbr_cache.record_reuse_outcome(precedent.task_hash, success=True)
                            elapsed = (time.perf_counter() - t0) * 1000.0
                            return adapted, PreflightResult(
                                success=True,
                                error_msg=None,
                                elapsed_ms=elapsed,
                                assertions_run=0,
                                fail_open=False,
                            )
                        cbr_check = self.sandbox.preflight_verify_code(
                            code=adapted, docstring_examples=docstring_examples
                        )
                        if cbr_check.success:
                            cbr_cache.record_reuse_outcome(precedent.task_hash, success=True)
                            cbr_cache.retain_episode(
                                query=prompt,
                                code=adapted,
                                method="CBR_REUSE",
                                turns_taken=1,
                            )
                            return adapted, cbr_check
                        cbr_cache.record_reuse_outcome(precedent.task_hash, success=False)
                        used_precedent = precedent
            except Exception as cbr_exc:  # noqa: BLE001
                logger.debug("cbr_retrieve_reuse_failed", error=str(cbr_exc))

        if code_candidate is None:
            instruction = (
                "Complete the following Python coding task. Put all Python code inside a ```python ... ``` block.\n\n"
                f"{prompt}"
            )
            if used_precedent is not None:
                instruction += (
                    f"\n\nNote: A prior precedent exists but required adaptation:\n"
                    f"```python\n{used_precedent.code}\n```"
                )
            resp_parts: list[str] = []
            for event in self.llm.stream_turn(
                current_text=instruction,
                max_tokens=1024,
                enable_thinking=False,
            ):
                if isinstance(event, TokenDelta) and event.delta:
                    resp_parts.append(event.delta)
            raw_resp = "".join(resp_parts)
            code_candidate = extract_python_code(raw_resp)

        if not enable_preflight:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return code_candidate, PreflightResult(
                success=True, error_msg=None, elapsed_ms=elapsed, assertions_run=0, fail_open=False
            )

        # CBR Step 3 (Revise): Preflight verification against Docker sandbox
        preflight_res = self.sandbox.preflight_verify_code(
            code=code_candidate, docstring_examples=docstring_examples
        )

        # If passed or fail-open honored (timeout/unavailable), return candidate
        if preflight_res.success or preflight_res.fail_open or max_repair_rounds <= 0:
            if preflight_res.success and cbr_cache is not None and code_candidate.strip():
                try:
                    cbr_cache.retain_episode(
                        query=prompt,
                        code=code_candidate,
                        method="PreflightCEGIS",
                        turns_taken=1,
                    )
                except Exception as retain_err:  # noqa: BLE001
                    logger.debug("cbr_retain_failed", error=str(retain_err))
            elif not preflight_res.success:
                self._log_impasse_to_backlog(
                    query=prompt,
                    code=code_candidate,
                    error_trace=str(preflight_res.error_msg or "PreflightVerificationError"),
                )
            sink = getattr(self, "cognitive_outcome_sink", None) or getattr(
                self, "cognitive_sink", None
            )
            if sink is not None:
                try:
                    sink.record_cegis_outcome(
                        task_id=trace.trace_id if trace else f"preflight-{ulid.ULID()}",
                        problem_summary=prompt.strip()[:120],
                        engine_name="PreflightCEGIS",
                        success=preflight_res.success,
                        turns_taken=1,
                        final_code=code_candidate,
                        turn_1_error=preflight_res.error_msg,
                        status_label="VERIFIED_PROGRAM" if preflight_res.success else "INTERNAL_FALLBACK",
                        reasoning_context=getattr(self, "current_reasoning_context", None),
                    )
                except Exception as sink_err:  # noqa: BLE001
                    logger.debug("preflight_sink_record_failed", error=str(sink_err))
            return code_candidate, preflight_res

        # 1-Shot Self-Repair Loop
        logger.warning(
            "preflight_verification_failed_triggering_self_repair",
            error=preflight_res.error_msg,
            assertions_run=preflight_res.assertions_run,
        )

        repair_prompt = (
            "The following Python code failed preflight verification against specification docstrings and test assertions in Docker:\n"
            f"```python\n{code_candidate}\n```\n\n"
            f"Preflight Error Details:\n{preflight_res.error_msg}\n\n"
            "Please fix the bug (check boundary conditions, empty sequences, zero/negative inputs, trailing punctuation, or rounding logic). "
            "Provide only the corrected complete Python implementation inside a ```python ... ``` block."
        )

        repair_parts: list[str] = []
        for event in self.llm.stream_turn(
            current_text=repair_prompt,
            max_tokens=1024,
            enable_thinking=False,
        ):
            if isinstance(event, TokenDelta) and event.delta:
                repair_parts.append(event.delta)

        repaired_raw = "".join(repair_parts)
        repaired_code = extract_python_code(repaired_raw)
        if not repaired_code or not repaired_code.strip():
            self._log_impasse_to_backlog(
                query=prompt,
                code=code_candidate,
                error_trace=str(preflight_res.error_msg or "PreflightVerificationError"),
            )
            return code_candidate, preflight_res

        repaired_res = self.sandbox.preflight_verify_code(
            code=repaired_code, docstring_examples=docstring_examples
        )
        self._log_impasse_to_backlog(
            query=prompt,
            code=code_candidate,
            error_trace=str(preflight_res.error_msg or "PreflightVerificationError"),
            resolved_code=repaired_code if repaired_res.success else "",
        )
        if repaired_res.success and cbr_cache is not None:
            try:
                cbr_cache.retain_episode(
                    query=prompt,
                    code=repaired_code,
                    method="PreflightRepair",
                    turns_taken=2,
                )
            except Exception as retain_err:  # noqa: BLE001
                logger.debug("cbr_repair_retain_failed", error=str(retain_err))
        sink = getattr(self, "cognitive_outcome_sink", None) or getattr(
            self, "cognitive_sink", None
        )
        if sink is not None:
            try:
                sink.record_cegis_outcome(
                    task_id=trace.trace_id if trace else f"preflight-{ulid.ULID()}",
                    problem_summary=prompt.strip()[:120],
                    engine_name="PreflightCEGIS",
                    success=repaired_res.success,
                    turns_taken=2,
                    final_code=repaired_code,
                    turn_1_error=preflight_res.error_msg,
                    verified_strategy="Preflight assertion self-repair",
                    status_label="VERIFIED_REPAIRED_PROGRAM" if repaired_res.success else "INTERNAL_FALLBACK",
                    reasoning_context=getattr(self, "current_reasoning_context", None),
                )
            except Exception as sink_err:  # noqa: BLE001
                logger.debug("preflight_repair_sink_record_failed", error=str(sink_err))
        return repaired_code, repaired_res

    def _stream_code_synthesis(
        self,
        trace: TurnTrace,
        user_msg: str,
        decision_id: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        epistemic_context: str | None = None,
    ) -> None:
        """WO-26 Phase 4: Tier 3 Code Synthesis Turn Handler.

        Executes preflight code verification loop before presenting code in chat or TTS.
        """
        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        self._publish_bus(begin_env)

        cue = "Testing implementation in the sandbox..."
        self._speak_text(trace, cue)

        prompt = current_text or user_msg
        code, preflight_res = self.synthesize_code_with_preflight(prompt=prompt, trace=trace)

        if preflight_res.success:
            spoken_summary = "I've written and verified the implementation in the sandbox."
            full_response = f"Here is the verified implementation:\n\n```python\n{code}\n```"
        else:
            spoken_summary = "I've generated the function, though an assertion warning was noted."
            full_response = f"```python\n{code}\n```\n\n*Note: Preflight check reported:* `{preflight_res.error_msg}`"

        self._publish_caption(full_response, source="assistant", is_final=True)
        self._speak_text(trace, spoken_summary)
        self.play_ring.set_flag(FLAG_EOS)

        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": full_response})
        self.current_turn_assistant_reply = full_response
        self._finalize_turn(trace, decision_id)

    def _reset_turn_state(self) -> None:
        """Reset per-turn state for sandbox, supervisor, flags, and tool tracking."""
        self.turn_pipeline.reset_turn_state()

    def _run_turn(self, trace: TurnTrace, p: PTTReleasedPayload) -> None:
        """
        Voice turn input adapter: reads audio from capture ring, performs
        silence/VAD check, transcribes via ASR, encodes WAV payload,
        and delegates to the unified TurnPipeline.
        """
        self._reset_turn_state()
        self._cancel_token.clear()

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

        if trace.interrupted or self._cancel_token.is_set():
            return

        # Transcribe audio with ASR
        transcribed_text = ""
        if self.asr and len(pcm_samples) > 0:
            trace.t_asr_sent = now_ns()
            asr_res = self.asr.transcribe(pcm_samples)
            trace.t_asr_done = now_ns()
            transcribed_text = asr_res.text.strip()
            self.current_turn_transcript = transcribed_text

        if trace.interrupted or self._cancel_token.is_set():
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

        if trace.interrupted or self._cancel_token.is_set():
            return

        pending_img = getattr(self, "_pending_image_b64", None)
        turn_input = TurnInput(
            user_text=transcribed_text,
            trace=trace,
            origin="voice",
            mode="vision" if pending_img else ("transcript" if is_trans_mode else "audio"),
            vad_speech_ms=p.vad_speech_ms,
            current_audio_b64=llm_audio,
            current_text=llm_text,
            image_b64=pending_img,
        )
        self.turn_pipeline.run(turn_input)

    def _run_text_turn(self, trace: TurnTrace, user_text: str) -> None:
        """
        Text turn input adapter: normalizes text payload and delegates to the
        unified TurnPipeline.
        """
        self._reset_turn_state()
        self._cancel_token.clear()
        if trace.interrupted or self._cancel_token.is_set():
            return
        pending_img = getattr(self, "_pending_image_b64", None)
        turn_input = TurnInput(
            user_text=user_text,
            trace=trace,
            origin="text",
            mode="vision" if pending_img else "transcript",
            vad_speech_ms=1000.0,
            current_text=user_text,
            image_b64=pending_img,
        )
        self.turn_pipeline.run(turn_input)

    def _tts_worker(self) -> None:
        """Background worker thread (core-tts) consuming chunks from speech_output."""
        self.speech_output.tts_worker()

    def _speak_text(self, trace: TurnTrace, text: str) -> None:
        if not text or not text.strip():
            return
        # WO-26 Phase 1: Mind-Mouth Interiority Barrier
        # Strictly quarantine internal system messages, revisions, or telemetry logs from TTS audio
        if (
            "[Lucca Revision]" in text
            or text.startswith("[System")
            or text.startswith("[Cognitive Bus")
            or text.startswith("I've revised a belief")
            or text.startswith("I had a belief")
        ):
            logger.info("tts_speech_quarantined_interiority", text=text[:100])
            return
        self.speech_output.speak_text(trace, text)

    # delegate — kept for test/back-compat
    def _describe_tool_action(self, name: str, args: dict[str, JsonValue]) -> str:
        return self.tool_dispatcher.describe_tool_action(name, args)

    # delegate — kept for test/back-compat
    def _handle_schedule_event(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self.tool_dispatcher.handle_schedule_event(call_id, args)

    def maybe_fire_due_events(self, now: float | None = None) -> list[str]:
        """Claims due scheduled events from the sandbox store, speaks reminders, and publishes bus notifications."""
        if not hasattr(self, "sandbox") or not hasattr(self.sandbox, "claim_due_events"):
            return []
        try:
            due_events = self.sandbox.claim_due_events(now=now)
        except Exception as exc:  # noqa: BLE001
            logger.debug("claim_due_events_failed", error=str(exc))
            return []

        fired_messages: list[str] = []
        for ev in due_events:
            msg_suffix = f" {ev.message}" if ev.message else ""
            spoken_msg = f"Reminder: {ev.event_name}.{msg_suffix}"
            fired_messages.append(spoken_msg)
            self.pending_spoken_updates.append(spoken_msg)
            try:
                bus_env = Envelope(
                    type="schedule.fired",
                    trace_id="",
                    ts_ns=now_ns(),
                    src="core",
                    payload={
                        "event_id": ev.event_id,
                        "event_name": ev.event_name,
                        "iso_datetime": ev.iso_datetime,
                        "message": ev.message or "",
                        "spoken": spoken_msg,
                    },
                )
                self._publish_bus(bus_env)
            except Exception as exc:  # noqa: BLE001
                logger.debug("publish_schedule_fired_failed", error=str(exc))
            if self.state == "idle":
                try:
                    trace = TurnTrace(
                        trace_id=f"sched-{ev.event_id}",
                        session_id=getattr(self, "session_id", "session-sched"),
                        origin="text",
                    )
                    self._speak_text(trace, spoken_msg)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("speak_schedule_fired_failed", error=str(exc))
        return fired_messages

    # delegate — kept for test/back-compat
    def _handle_artifact_verify(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self.tool_dispatcher.handle_artifact_verify(call_id, args)

    # delegate — kept for test/back-compat
    def _handle_clipboard_read(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self.tool_dispatcher.handle_clipboard_read(call_id, args)

    # delegate — kept for test/back-compat
    def _handle_inbox_handoff(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self.tool_dispatcher.handle_inbox_handoff(call_id, args)

    # delegate — kept for test/back-compat
    def _handle_screenshot_capture(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self.tool_dispatcher.handle_screenshot_capture(call_id, args)

    # delegate — kept for test/back-compat
    def _handle_self_history_search(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self.tool_dispatcher.handle_self_history_search(call_id, args)

    # delegate — kept for test/back-compat
    def _handle_memory_commit(
        self,
        trace: TurnTrace,
        call_id: str,
        name: str,
        args: dict[str, JsonValue],
        speak: bool,
    ) -> ToolResult:
        return self.tool_dispatcher.handle_memory_commit(trace, call_id, name, args, speak)

    # ------------------------------------------------------------------------
    # WO-21 Phase 3: Proactive Web-Fact Ratification & Cross-Reference
    # ------------------------------------------------------------------------

    def _extract_receipt_domain(self, r: ToolReceipt) -> str:
        args = getattr(r, "args", {}) or {}
        if isinstance(args, dict):
            domain_val = args.get("domain", "")
            if domain_val and isinstance(domain_val, str):
                return domain_val.strip().lower()
            url_val = args.get("url", "")
            if url_val and isinstance(url_val, str):
                try:
                    parsed = urllib.parse.urlsplit(url_val)
                    if parsed.netloc:
                        return parsed.netloc.lower().split(":")[0]
                except Exception as exc:  # noqa: BLE001
                    logger.debug("extract_receipt_domain_urlsplit_failed", error=str(exc))
        src = extract_receipt_source(r)
        if "." in src and not src.startswith("tool"):
            return src.lower()
        return ""

    def _is_domain_whitelisted(self, domain: str) -> bool:
        if not domain:
            return False
        d_clean = domain.strip().lower()
        whitelist = getattr(self, "ratification_domains", None) or set()
        if d_clean in whitelist:
            return True
        return any(d_clean == w or d_clean.endswith("." + w) for w in whitelist)

    def _extract_durable_claim(self, r: ToolReceipt) -> str | None:
        args = getattr(r, "args", {}) or {}
        if isinstance(args, dict) and "claim" in args and isinstance(args["claim"], str):
            c = args["claim"].strip()
            if c:
                return c

        text = str(getattr(r, "output", "") or getattr(r, "content", "") or "")
        return self._extract_durable_claim_from_text(text)

    def _extract_durable_claim_from_text(self, text: str) -> str | None:
        cleaned = text.strip()
        if not cleaned or len(cleaned) < 5:
            return None
        lower = cleaned.lower()
        if any(
            err in lower for err in ("error:", "404 not found", "access denied", "failed to fetch")
        ):
            return None

        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        copula_pattern = re.compile(
            r"\b(?:is|was|are|were|has|have|had|features|released|announced|supports|became|born|won|contains)\b",
            re.IGNORECASE,
        )
        for s in sentences:
            s_clean = s.strip()
            s_clean = re.sub(r"^#+\s*", "", s_clean)
            s_clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s_clean)
            if 10 <= len(s_clean) <= 150 and not s_clean.endswith("?"):
                if copula_pattern.search(s_clean):
                    return s_clean.rstrip(".! ")

        if 10 <= len(cleaned) <= 120 and not cleaned.endswith("?"):
            return cleaned.rstrip(".! ")
        return None

    def _check_and_offer_ratification(self, trace: TurnTrace) -> str | None:
        if getattr(self, "_ratification_offered_this_turn", False):
            return None
        receipts = getattr(self, "current_turn_receipts", []) or []
        for r in receipts:
            tool_name = getattr(r, "tool", "") or getattr(r, "tool_name", "")
            if tool_name not in ("fetch_url", "search_web", "web_search", "browse_page"):
                continue
            if not getattr(r, "ok", True):
                continue
            domain = self._extract_receipt_domain(r)
            if not domain or not self._is_domain_whitelisted(domain):
                continue
            claim = self._extract_durable_claim(r)
            if not claim:
                continue

            args = getattr(r, "args", {}) or {}
            url = ""
            if isinstance(args, dict):
                url = str(args.get("url", "") or args.get("domain", "") or domain)

            offer_text = f"I found on {domain} that {claim} \u2014 want me to remember that?"
            self._ratification_offered_this_turn = True

            self._pending_ratification = PendingRatification(
                call_id=getattr(r, "call_id", ""),
                domain=domain,
                claim=claim,
                source_url=url,
                fetch_receipt_entry_id=getattr(r, "entry_id", "") or getattr(r, "call_id", ""),
            )
            self._speak_text(trace, offer_text)
            self._publish_caption(offer_text, source="assistant", is_final=True)
            return offer_text
        return None

    def _commit_ratified_fact(self, pending: PendingRatification, trace: TurnTrace) -> str | None:
        if not self.memory_store:
            return None
        signer = self.signer_factory.derived_fact()
        now = self.clock.now_utc() if hasattr(self, "clock") and self.clock else time.time()
        source_id = pending.fetch_receipt_entry_id or f"fetch-{pending.call_id}"
        unsigned = UnsignedPayload(
            content=pending.claim,
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            nonce=os.urandom(16).hex(),
            created_at=now,
            trace_id=trace.trace_id,
            confidence=1.0,
            source_entry_ids=[source_id],
            structured={
                "source_url": pending.source_url,
                "fetch_receipt_entry_id": source_id,
                "confirmed_by_user": True,
            },
        )
        signed = signer.sign(unsigned)
        self.memory_store.commit(signed, now=now)
        self._last_ratified_claim = pending.claim
        return signed.entry_id

    def _is_cross_reference_command(self, text: str) -> bool:
        return is_cross_reference_command(text)

    def _resolve_cross_reference_claim(self, user_text: str) -> str | None:
        cross_ref_pat = (
            r"(?:cross[\s-]?reference|find more sources on|check more sources on|verify)"
            r"\s+(?:that\s+)?(.+)"
        )
        m = re.search(cross_ref_pat, user_text, re.IGNORECASE)
        if m:
            explicit_claim = m.group(1).strip().rstrip(".!?")
            if explicit_claim.lower() not in ("that", "this", "it"):
                return explicit_claim

        if getattr(self, "_pending_ratification", None) is not None:
            return self._pending_ratification.claim

        if getattr(self, "_last_ratified_claim", None):
            return self._last_ratified_claim

        for msg in reversed(self.history):
            if msg.get("role") == "assistant":
                content = str(msg.get("content", ""))
                offer_match = re.search(
                    r"I found on .+? that (.+?) [—\-] want me to remember that\?",
                    content,
                )
                if offer_match:
                    return offer_match.group(1).strip()
                c = self._extract_durable_claim_from_text(content)
                if c:
                    return c
        return None

    @staticmethod
    def _extract_claim_aligned_sentences(
        claim: str,
        page_text: str,
        fallback_snippet: str,
        max_sentences: int = 2,
    ) -> str:
        """Extracts the top 1-2 claim-aligned sentences from Scrapling page text.

        Prevents full-page negation/adversative pollution in compute_proposition_alignment
        (corroboration.py:666) while upgrading 150-char snippets with deep article facts.
        """
        if not page_text or not page_text.strip():
            return fallback_snippet
        claim_tokens = {
            tok
            for tok in re.findall(r"[a-z0-9]+", claim.lower())
            if len(tok) > 2
            and tok not in {"the", "and", "for", "that", "with", "from", "this", "what", "when", "where", "who", "was", "are", "is"}
        }
        if not claim_tokens:
            return fallback_snippet

        raw_sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+|\n+", page_text)
            if 15 <= len(s.strip()) <= 500
        ]
        if not raw_sentences:
            return fallback_snippet

        scored: list[tuple[float, int, str]] = []
        for idx, sent in enumerate(raw_sentences):
            sent_tokens = set(re.findall(r"[a-z0-9]+", sent.lower()))
            overlap = len(claim_tokens & sent_tokens)
            if overlap == 0:
                continue
            ratio = overlap / max(len(claim_tokens), 1)
            scored.append((ratio, -idx, sent))

        if not scored:
            return fallback_snippet

        scored.sort(reverse=True)
        top_sents = [s for _r, _i, s in scored[:max_sentences]]
        combined = " ".join(top_sents).strip()
        if fallback_snippet and fallback_snippet not in combined:
            return f"{fallback_snippet} {combined}".strip()
        return combined

    def _fetch_cross_reference_page(self, url: str) -> str:
        """Fetches clean article text via Scrapling web_tool for cross-reference corroboration."""
        if not url:
            return ""
        is_mock_sandbox = self.sandbox is not None and type(
            self.sandbox
        ).__module__.startswith("unittest.mock")
        default_enabled = not is_mock_sandbox
        if not getattr(self, "enable_deep_cross_reference", default_enabled):
            return ""
        try:
            from lucca.sandbox.web_tool import fetch_url

            structured, content = fetch_url(url=url, max_chars=6000)
            if structured.get("ok") and isinstance(content, str):
                return content
        except Exception as exc:  # noqa: BLE001
            logger.debug("cross_ref_deep_fetch_error", url=url, error=str(exc))
        return ""

    def _execute_cross_reference_searches(
        self, claim: str, max_searches: int = 3
    ) -> list[ToolReceipt]:
        custom_search = getattr(self, "cross_reference_search_fn", None)
        if custom_search is not None and callable(custom_search):
            res_list = custom_search(claim, max_searches)
            if isinstance(res_list, list):
                return [r for r in res_list if isinstance(r, ToolReceipt)]

        receipts: list[ToolReceipt] = []
        if self.sandbox:
            call_id = str(ulid.ULID())
            res = self.sandbox.execute_tool(
                call_id=call_id,
                tool_name="search_web",
                args={"query": claim, "max_results": max_searches},
                confirmed=True,
            )
            if (
                res.structured
                and "results" in res.structured
                and isinstance(res.structured["results"], list)
            ):
                for item in res.structured["results"][:max_searches]:
                    url = item.get("url", "")
                    domain = ""
                    if url:
                        try:
                            domain = urllib.parse.urlsplit(url).netloc.lower()
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("search_receipt_domain_urlsplit_error", error=str(exc))
                    content = f"{item.get('title', '')} {item.get('snippet', '')}".strip()
                    page_text = self._fetch_cross_reference_page(url) if url else ""
                    if page_text:
                        content = self._extract_claim_aligned_sentences(
                            claim=claim,
                            page_text=page_text,
                            fallback_snippet=content,
                        )
                    rcpt = ToolReceipt(
                        tool="search_web",
                        tool_name="search_web",
                        ok=True,
                        call_id=str(ulid.ULID()),
                        args={"url": url, "domain": domain, "query": claim},
                        output=content,
                        timestamp=time.time(),
                    )
                    receipts.append(rcpt)
                    self.current_turn_receipts.append(rcpt)
            elif res.content:
                rcpt = ToolReceipt(
                    tool="search_web",
                    tool_name="search_web",
                    ok=res.ok,
                    call_id=call_id,
                    args={"query": claim},
                    output=str(res.content),
                    timestamp=time.time(),
                )
                receipts.append(rcpt)
                self.current_turn_receipts.append(rcpt)
        return receipts

    def _handle_cross_reference(self, trace: TurnTrace, user_text: str) -> None:
        claim = self._resolve_cross_reference_claim(user_text)
        if not claim:
            msg = "I don't have a recent claim to cross-reference."
            self._speak_text(trace, msg)
            self._publish_caption(msg, source="assistant", is_final=True)
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": msg})
            self.play_ring.set_flag(FLAG_EOS)
            self._finalize_turn(trace, None)
            return

        if getattr(self, "_pending_ratification", None) is not None:
            self._pending_ratification = None

        receipts = self._execute_cross_reference_searches(claim, max_searches=3)
        step = InferenceStep(
            s=claim,
            p="is_verified",
            o="true",
            premises=[f"web asserts {claim}"],
            confidence=0.70,
            rationale="cross_reference",
        )
        q_results = critical_questions(
            scheme=Scheme.AUTHORITY,
            step=step,
            store=self.memory_store,
            receipts=receipts,
        )
        initial_conf = 0.70
        new_conf, conditions = adjust_confidence(initial_conf, q_results)
        std = standard_for_confidence(new_conf)

        q2 = next(
            (
                q
                for q in q_results
                if "corroborated" in q.question.lower() and q.answer == CQAnswer.SATISFIED
            ),
            None,
        )
        corrob_count = q2.count if q2 else 0
        disputes = [
            q
            for q in q_results
            if "disputed" in q.question.lower() and q.answer == CQAnswer.SATISFIED
        ]

        if disputes:
            report = (
                f"Cross-reference found disputing evidence. "
                f"Confidence docked to {new_conf:.2f} \u2014 {std.value}."
            )
        elif corrob_count > 0:
            sources_str = f"{corrob_count} independent source{'s' if corrob_count != 1 else ''}"
            report = (
                f"Cross-referenced across {sources_str}: "
                f"confidence {new_conf:.2f} \u2014 {std.value}."
            )
        else:
            report = (
                f"Cross-reference found no independent corroboration. "
                f"Confidence remains {new_conf:.2f} \u2014 {std.value}."
            )

        self._speak_text(trace, report)
        self._publish_caption(report, source="assistant", is_final=True)
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": report})
        self.play_ring.set_flag(FLAG_EOS)
        self._finalize_turn(trace, None)

    # delegate — kept for test/back-compat
    def _request_confirmation(
        self,
        trace: TurnTrace,
        name: str,
        args: dict[str, JsonValue],
        timeout_s: float = 15.0,
    ) -> bool:
        return self.confirmations.request_confirmation(trace, name, args, timeout_s=timeout_s)

    # delegate — kept for test/back-compat
    def _handle_tool_call(
        self,
        trace: TurnTrace,
        name: str,
        args: dict[str, JsonValue],
        speak: bool = True,
    ) -> ToolResult | None:
        return self.tool_dispatcher.handle_tool_call(trace, name, args, speak=speak)

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
                if self.state == "idle":
                    self.maybe_fire_due_events()
                    self.maybe_run_idle_pulse()
                    self.maybe_run_nightly_rollup()
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
        if hasattr(self.llm, "close"):
            try:
                self.llm.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("orchestrator_llm_close_error", error=str(exc))
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
