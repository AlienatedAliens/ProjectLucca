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
from lucca.core.code_preflight_service import CodePreflightService
from lucca.core.deduction_runner import DeductionAndPlanningRunner
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
from lucca.memory.working import WorkingMemory
from lucca.reasoning.consolidation import ConsolidationEngine
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
    def working_memory(self) -> WorkingMemory | None:
        wm = getattr(self, "_working_memory", None)
        if wm is None and getattr(self, "db", None) is not None:
            wm = WorkingMemory(db=self.db)
            self._working_memory = wm
        return wm

    @working_memory.setter
    def working_memory(self, value: WorkingMemory | None) -> None:
        self._working_memory = value

    @property
    def consolidation_engine(self) -> ConsolidationEngine:
        ce = getattr(self, "_consolidation_engine", None)
        if ce is None:
            re_eng = getattr(self, "rule_engine", None)
            ce = ConsolidationEngine(
                lifecycle_manager=re_eng if isinstance(re_eng, RuleLifecycleManager) else None,
            )
            self._consolidation_engine = ce
        return ce

    @consolidation_engine.setter
    def consolidation_engine(self, value: ConsolidationEngine) -> None:
        self._consolidation_engine = value

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
    def deduction_runner(self) -> DeductionAndPlanningRunner:
        runner = getattr(self, '_deduction_runner', None)
        if runner is None:
            runner = DeductionAndPlanningRunner(orchestrator=self)
            self._deduction_runner = runner
        return runner

    @deduction_runner.setter
    def deduction_runner(self, value: DeductionAndPlanningRunner) -> None:
        self._deduction_runner = value

    @property
    def code_preflight(self) -> CodePreflightService:
        srv = getattr(self, '_code_preflight', None)
        if srv is None:
            srv = CodePreflightService(orchestrator=self)
            self._code_preflight = srv
        return srv

    @code_preflight.setter
    def code_preflight(self, value: CodePreflightService) -> None:
        self._code_preflight = value

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

    # delegate — kept for test/back-compat
    def evaluate_rules_chain(
        self,
        state: RuleState,
        trace: TurnTrace | None = None,
        max_depth: int = 8,
        context: ReasoningContext | None = None,
    ) -> tuple[list[RuleOutcome], RuleState]:
        return self.deduction_runner.evaluate_rules_chain(
            state, trace=trace, max_depth=max_depth, context=context
        )

    # delegate — kept for test/back-compat
    def finalize_chain(
        self,
        context: ReasoningContext | None = None,
        trace: TurnTrace | None = None,
    ) -> SignedPayload | None:
        return self.deduction_runner.finalize_chain(context=context, trace=trace)

    # delegate — kept for test/back-compat
    def proof_trace(self) -> list[ProofTraceStep]:
        return self.deduction_runner.proof_trace()

    # delegate — kept for test/back-compat
    def _validate_premise(self, premise: str, context: ReasoningContext) -> tuple[bool, str | None]:
        return self.deduction_runner.validate_premise(premise, context)

    # delegate — kept for test/back-compat
    def _search_memory_for_premise(self, premise: str) -> list[str]:
        return self.deduction_runner.search_memory_for_premise(premise)

    # delegate — kept for test/back-compat
    def _parse_inference_steps(self, text: str) -> list[InferenceStep]:
        return self.deduction_runner.parse_inference_steps(text)

    # delegate — kept for test/back-compat
    def _evaluate_step_corroboration(
        self, step: InferenceStep, context: ReasoningContext | None = None
    ) -> list[CriticalQuestionResult]:
        return self.deduction_runner.evaluate_step_corroboration(step, context=context)

    # delegate — kept for test/back-compat
    def run_deduction_step(
        self,
        goal: str,
        trace: TurnTrace | None = None,
        context: ReasoningContext | None = None,
        llm: object | None = None,
    ) -> tuple[list[InferenceStep], str | None]:
        return self.deduction_runner.run_deduction_step(
            goal, trace=trace, context=context, llm=llm
        )

    # delegate — kept for test/back-compat
    def _format_conditioned_speech(
        self, final_entry: ReasoningEntry, conditions: list[str]
    ) -> str | None:
        return self.deduction_runner.format_conditioned_speech(final_entry, conditions)

    run_deduction_loop = run_deduction_step

    # delegate — kept for test/back-compat
    def _parse_and_validate_plan(
        self, text: str, default_goal: str
    ) -> tuple[GoalPlan | None, str | None]:
        return self.deduction_runner.parse_and_validate_plan(text, default_goal)

    # delegate — kept for test/back-compat
    def run_planning_step(
        self,
        goal: str,
        trace: TurnTrace | None = None,
        llm: object | None = None,
        context: ReasoningContext | None = None,
    ) -> GoalPlan | None:
        return self.deduction_runner.run_planning_step(
            goal, trace=trace, llm=llm, context=context
        )

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

        tp = getattr(self, "turn_pipeline", None)
        if tp is not None and hasattr(tp, "on_turn_finalized"):
            tp.on_turn_finalized(trace, decision_id)

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
                try:
                    self.consolidation_engine.run_consolidation_cycle()
                except Exception as cons_exc:  # noqa: BLE001
                    logger.debug("consolidation_cycle_failed", error=str(cons_exc))
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

    # delegate — kept for test/back-compat
    def _ensure_impasse_backlog_table(self) -> None:
        self.code_preflight.ensure_impasse_backlog_table()

    # delegate — kept for test/back-compat
    def _log_impasse_to_backlog(
        self,
        query: str,
        code: str,
        error_trace: str,
        resolved_code: str = '',
        surprise_score: float = 0.85,
    ) -> None:
        self.code_preflight.log_impasse_to_backlog(
            query=query,
            code=code,
            error_trace=error_trace,
            resolved_code=resolved_code,
            surprise_score=surprise_score,
        )

    # delegate — kept for test/back-compat
    def synthesize_code_with_preflight(
        self,
        prompt: str,
        initial_code: str | None = None,
        trace: TurnTrace | None = None,
        docstring_examples: list[str] | None = None,
        max_repair_rounds: int = 1,
        enable_preflight: bool = True,
    ) -> tuple[str, PreflightResult]:
        return self.code_preflight.synthesize_code_with_preflight(
            prompt=prompt,
            initial_code=initial_code,
            trace=trace,
            docstring_examples=docstring_examples,
            max_repair_rounds=max_repair_rounds,
            enable_preflight=enable_preflight,
        )

    # delegate — kept for test/back-compat
    def _stream_code_synthesis(
        self,
        trace: TurnTrace,
        user_msg: str,
        decision_id: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        epistemic_context: str | None = None,
    ) -> None:
        self.code_preflight.stream_code_synthesis(
            trace=trace,
            user_msg=user_msg,
            decision_id=decision_id,
            current_text=current_text,
            memories=memories,
            epistemic_context=epistemic_context,
        )

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

    # delegate — kept for test/back-compat
    def _extract_receipt_domain(self, r: ToolReceipt) -> str:
        return self.deduction_runner.extract_receipt_domain(r)

    # delegate — kept for test/back-compat
    def _is_domain_whitelisted(self, domain: str) -> bool:
        return self.deduction_runner.is_domain_whitelisted(domain)

    # delegate — kept for test/back-compat
    def _extract_durable_claim(self, r: ToolReceipt) -> str | None:
        return self.deduction_runner.extract_durable_claim(r)

    # delegate — kept for test/back-compat
    def _extract_durable_claim_from_text(self, text: str) -> str | None:
        return self.deduction_runner.extract_durable_claim_from_text(text)

    # delegate — kept for test/back-compat
    def _check_and_offer_ratification(self, trace: TurnTrace) -> str | None:
        return self.deduction_runner.check_and_offer_ratification(trace)

    # delegate — kept for test/back-compat
    def _commit_ratified_fact(self, pending: PendingRatification, trace: TurnTrace) -> str | None:
        return self.deduction_runner.commit_ratified_fact(pending, trace)

    # delegate — kept for test/back-compat
    def _is_cross_reference_command(self, text: str) -> bool:
        return is_cross_reference_command(text)

    # delegate — kept for test/back-compat
    def _resolve_cross_reference_claim(self, user_text: str) -> str | None:
        return self.deduction_runner.resolve_cross_reference_claim(user_text)

    # delegate — kept for test/back-compat
    @staticmethod
    def _extract_claim_aligned_sentences(
        claim: str,
        page_text: str,
        fallback_snippet: str,
        max_sentences: int = 2,
    ) -> str:
        return DeductionAndPlanningRunner.extract_claim_aligned_sentences(
            claim=claim,
            page_text=page_text,
            fallback_snippet=fallback_snippet,
            max_sentences=max_sentences,
        )

    # delegate — kept for test/back-compat
    def _fetch_cross_reference_page(self, url: str) -> str:
        return self.deduction_runner.fetch_cross_reference_page(url)

    # delegate — kept for test/back-compat
    def _execute_cross_reference_searches(
        self, claim: str, max_searches: int = 3
    ) -> list[ToolReceipt]:
        return self.deduction_runner.execute_cross_reference_searches(
            claim, max_searches=max_searches
        )

    # delegate — kept for test/back-compat
    def _handle_cross_reference(self, trace: TurnTrace, user_text: str) -> None:
        self.deduction_runner.handle_cross_reference(trace, user_text)

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
