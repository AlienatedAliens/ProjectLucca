"""
Project Lucca — Central Orchestrator & State Machine
Spec 01 §3, §4, §6, Spec 10, ADR-008
"""

import asyncio
import base64
import io
import os
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import structlog
import ulid
import zmq
from pydantic import JsonValue

from lucca.brain.chunker import StreamingChunker
from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import set_persona
from lucca.core.config import get_config
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
    DecisionRecord,
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
    UnsignedPayload,
)
from lucca.core.trace import TurnTrace, log_turn_trace
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import UserSpeechSigner, create_user_speech_signer
from lucca.ports import MemoryStorePort, STTPort, TTSPort
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.router.heuristic import HeuristicRouter
from lucca.router.labeler import derive_label, persist_decision_label
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

        # Audio rings
        self.cap_ring = get_capture_ring(create=True)
        self.play_ring = get_playback_ring(create=True)

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

        # Rule Engine (Spec 05 §6 & §8)
        self.rule_engine = rule_engine or RuleLifecycleManager()

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
        self.current_turn_tool_ok: bool = True

        # Confirmation State
        self._confirm_event = threading.Event()
        self._confirm_result: bool = False
        self._pending_confirmation_active: bool = False

        # Turn context
        self.active_trace: TurnTrace | None = None
        self.active_turn_thread: threading.Thread | None = None
        self.history: list[dict[str, str]] = []
        self.executed_tools: list[tuple[str, dict[str, JsonValue]]] = []
        self._turn_lock = threading.Lock()
        self._last_pong: dict[str, float] = {}
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

        self.current_turn_transcript: str | None = None

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
            ts_ns=time.monotonic_ns(),
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
            ts_ns=time.monotonic_ns(),
            src="core",
            payload=PlayAbortPayload(trace_id=trace_id).model_dump(),
        )
        self._publish_bus(abort_env)
        shutdown_env = Envelope(
            type="sys.shutdown",
            trace_id="",
            ts_ns=time.monotonic_ns(),
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
            ts_ns=time.monotonic_ns(),
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
                if (
                    p_cfg.persona_archetype is not None
                    or p_cfg.formality is not None
                    or p_cfg.custom_system_prompt is not None
                ):
                    set_persona(
                        archetype=p_cfg.persona_archetype,
                        formality=p_cfg.formality,
                        custom_prompt=p_cfg.custom_system_prompt,
                    )
                # Re-publish onto bus_sock so AudioProcess receives ptt_key and audio settings
                self._publish_bus(env)
                logger.info(
                    "ui_config_updated",
                    voice=p_cfg.voice,
                    speed=p_cfg.speed,
                    archetype=p_cfg.persona_archetype,
                    formality=p_cfg.formality,
                )
            elif env.type == "audio.first_sample_played":
                if self.active_trace:
                    self.active_trace.t_first_sample = env.ts_ns
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
        target_trace_id = self.active_trace.trace_id if self.active_trace else None
        self.llm.abort(trace_id=target_trace_id)
        self.chunker.reset()
        self.play_ring.set_flag(FLAG_ABORT)

        # Notify audio to abort output immediately
        trace_id = self.active_trace.trace_id if self.active_trace else ""
        abort_env = Envelope(
            type="play.abort",
            trace_id=trace_id,
            ts_ns=time.monotonic_ns(),
            src="core",
            payload=PlayAbortPayload(trace_id=trace_id).model_dump(),
        )
        self._publish_bus(abort_env)

        if self.active_trace:
            self.active_trace.interrupted = True

    def _on_ptt_released(self, ts_ns: int, p: PTTReleasedPayload) -> None:
        if self._pending_confirmation_active:
            # PTT response to confirmation prompt
            pcm_samples = self.cap_ring.read_slice(p.capture_seq_start, p.capture_seq_end)
            transcript_text = ""
            if self.asr and len(pcm_samples) > 0:
                asr_res = self.asr.transcribe(pcm_samples)
                transcript_text = asr_res.text

            decision = parse_confirmation_response(transcript_text)
            self._confirm_result = decision == "confirm"
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

        trace_id = str(ulid.ULID())
        trace = TurnTrace(
            trace_id=trace_id,
            mode=self.config.llm.mode,
            t_key_release=ts_ns,
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
        if self.state in ("speaking", "thinking", "confirm_wait"):
            self._abort_turn()

        trace_id = str(ulid.ULID())
        trace = TurnTrace(
            trace_id=trace_id,
            mode="transcript",
            t_key_release=ts_ns,
        )
        self.active_trace = trace

        print(f'\n[User] "{user_text}"', flush=True)
        self._publish_caption(user_text, source="user", is_final=True)
        self._publish_caption("Thinking... ⚙️", source="status", is_final=False)
        self._set_state("thinking")

        t = threading.Thread(target=self._run_text_turn, args=(trace, user_text), daemon=True)
        self.active_turn_thread = t
        t.start()

    def _build_rule_state(self, transcript: str, mode: Literal["audio", "transcript"]) -> RuleState:
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

    def _commit_transcript(self, text: str, trace: TurnTrace) -> None:
        if not self.memory_store or not text.strip():
            return
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("transcript_commit_failed", error=str(exc))

    def _finalize_turn(self, trace: TurnTrace, decision_id: str | None) -> None:
        self._set_state("postturn")
        if self.current_turn_transcript:
            self._commit_transcript(self.current_turn_transcript, trace)
            self.current_turn_transcript = None

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

        trace.t_postturn_done = time.monotonic_ns()
        log_turn_trace(trace)
        self._set_state("idle")

    def _run_turn(self, trace: TurnTrace, p: PTTReleasedPayload) -> None:
        trace.t_llm_sent = time.monotonic_ns()
        self.sandbox.reset_turn()
        self.play_ring.clear_flag(FLAG_ABORT)
        self.play_ring.clear_flag(FLAG_EOS)
        self.current_turn_tool_calls = []
        self.current_turn_tool_ok = True
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

        # Transcribe audio with ASR
        transcribed_text = ""
        if self.asr and len(pcm_samples) > 0:
            asr_res = self.asr.transcribe(pcm_samples)
            transcribed_text = asr_res.text.strip()
            self.current_turn_transcript = transcribed_text

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
        if self.prev_decision_record and self.db is not None:
            try:
                next_intent, next_conf, _ = self.router.classify_intent(transcribed_text)
                time_to_next = (time.time() - self.prev_turn_ts) if self.prev_turn_ts else None
                label, reason = derive_label(
                    self.prev_decision_record,
                    next_transcript=transcribed_text,
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
        rule_state = self._build_rule_state(transcribed_text, mode=mode)
        shadow_outcomes = self.rule_engine.evaluate(rule_state, mode="shadow")
        any_quarantine_fired = any(o.fired for o in shadow_outcomes)

        active_outcomes = self.rule_engine.evaluate(rule_state, mode="active")
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

        if route_decision and route_decision.action == RouteAction.RULE:
            winning_outcome: RuleOutcome | None = None
            for outcome in active_outcomes:
                if outcome.fired and not outcome.errored and outcome.plan is not None:
                    winning_outcome = outcome
                    break

            if winning_outcome and winning_outcome.plan:
                try:
                    for action in winning_outcome.plan.actions:
                        if isinstance(action, Say):
                            self._speak_text(trace, action.text)
                            self._publish_caption(action.text, source="assistant", is_final=True)
                        elif isinstance(action, ToolCall):
                            self._handle_tool_call(trace, action.tool, dict(action.args))

                    user_msg = transcribed_text or "[Voice audio]"
                    assistant_msg = (
                        " ".join(a.text for a in winning_outcome.plan.actions if isinstance(a, Say))
                        or f"[Rule executed: {winning_outcome.rule_id}]"
                    )
                    self.history.append({"role": "user", "content": user_msg})
                    self.history.append({"role": "assistant", "content": assistant_msg})
                    self.play_ring.set_flag(FLAG_EOS)
                finally:
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

        # Arm audio playback
        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=time.monotonic_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        self._publish_bus(begin_env)

        chunk_index = 0
        first_token_seen = False
        full_response_text: list[str] = []

        try:
            llm_audio = wav_b64 if self.config.llm.mode == "audio" else None
            is_trans_mode = self.config.llm.mode == "transcript"
            llm_text = transcribed_text if (is_trans_mode or not llm_audio) else None

            mem_hits = self._search_memories(transcribed_text) if transcribed_text else []
            print("[Lucca] ", end="", flush=True)
            for event in self.llm.stream_turn(
                current_audio_b64=llm_audio,
                current_text=llm_text,
                history=self.history,
                memories=mem_hits if mem_hits else None,
                trace_id=trace.trace_id,
            ):
                if trace.interrupted:
                    break

                if isinstance(event, TokenDelta) and event.delta:
                    if not first_token_seen:
                        first_token_seen = True
                        trace.t_llm_first_token = time.monotonic_ns()

                    trace.tokens_out += 1
                    full_response_text.append(event.delta)
                    print(event.delta, end="", flush=True)

                    accumulated = "".join(full_response_text)
                    self._publish_caption(accumulated, source="assistant", is_final=False)

                    for chunk in self.chunker.feed(event.delta):
                        if trace.interrupted:
                            break
                        if chunk_index == 0:
                            trace.t_first_chunk = time.monotonic_ns()
                            self._set_state("speaking")

                        self._synthesize_chunk(trace, chunk.chunk_id, chunk.text)
                        chunk_index += 1

                elif isinstance(event, ToolCallEnd):
                    # Execute tool call via SandboxService with confirmation checks
                    self._handle_tool_call(trace, event.call.tool, dict(event.call.args))

            # Flush remaining chunker text
            if not trace.interrupted:
                for chunk in self.chunker.flush():
                    self._synthesize_chunk(trace, chunk.chunk_id, chunk.text)
                    chunk_index += 1

                # Signal End of Speech on playback ring
                self.play_ring.set_flag(FLAG_EOS)

            trace.t_llm_done = time.monotonic_ns()
            print("\n", flush=True)

            # Record turn in history
            if full_response_text and not trace.interrupted:
                reply_str = "".join(full_response_text)
                user_msg = transcribed_text or "[Voice audio]"
                self.history.append({"role": "user", "content": user_msg})
                self.history.append({"role": "assistant", "content": reply_str})
                self._publish_caption(reply_str, source="assistant", is_final=True)

        except Exception as exc:  # noqa: BLE001
            if not trace.interrupted:
                logger.error("turn_execution_error", trace_id=trace.trace_id, error=str(exc))
                print(f"\n[Error] {exc}", flush=True)
                self._publish_caption(
                    "Sorry, I had trouble processing that audio. "
                    "Try speaking again or typing your message!",
                    source="status",
                    is_final=True,
                )
            trace.interrupted = True
        finally:
            self._finalize_turn(trace, decision_id)

    def _run_text_turn(self, trace: TurnTrace, user_text: str) -> None:
        trace.t_llm_sent = time.monotonic_ns()
        self.sandbox.reset_turn()
        self.play_ring.clear_flag(FLAG_ABORT)
        self.play_ring.clear_flag(FLAG_EOS)
        self.current_turn_tool_calls = []
        self.current_turn_tool_ok = True
        self.current_turn_transcript = user_text
        decision_id: str | None = None

        # Update label for previous turn if present
        if self.prev_decision_record and self.db is not None:
            try:
                next_intent, next_conf, _ = self.router.classify_intent(user_text)
                time_to_next = (time.time() - self.prev_turn_ts) if self.prev_turn_ts else None
                label, reason = derive_label(
                    self.prev_decision_record,
                    next_transcript=user_text,
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
        rule_state = self._build_rule_state(user_text, mode="transcript")
        shadow_outcomes = self.rule_engine.evaluate(rule_state, mode="shadow")
        any_quarantine_fired = any(o.fired for o in shadow_outcomes)

        active_outcomes = self.rule_engine.evaluate(rule_state, mode="active")
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

        if route_decision and route_decision.action == RouteAction.RULE:
            winning_outcome: RuleOutcome | None = None
            for outcome in active_outcomes:
                if outcome.fired and not outcome.errored and outcome.plan is not None:
                    winning_outcome = outcome
                    break

            if winning_outcome and winning_outcome.plan:
                try:
                    for action in winning_outcome.plan.actions:
                        if isinstance(action, Say):
                            self._speak_text(trace, action.text)
                            self._publish_caption(action.text, source="assistant", is_final=True)
                        elif isinstance(action, ToolCall):
                            self._handle_tool_call(trace, action.tool, dict(action.args))

                    user_msg = user_text
                    assistant_msg = (
                        " ".join(a.text for a in winning_outcome.plan.actions if isinstance(a, Say))
                        or f"[Rule executed: {winning_outcome.rule_id}]"
                    )
                    self.history.append({"role": "user", "content": user_msg})
                    self.history.append({"role": "assistant", "content": assistant_msg})
                    self.play_ring.set_flag(FLAG_EOS)
                finally:
                    self._finalize_turn(trace, decision_id)
                return

        # Arm audio playback
        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=time.monotonic_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        self._publish_bus(begin_env)

        chunk_index = 0
        first_token_seen = False
        full_response_text: list[str] = []

        try:
            mem_hits = self._search_memories(user_text) if user_text else []
            print("[Lucca] ", end="", flush=True)
            for event in self.llm.stream_turn(
                current_text=user_text,
                history=self.history,
                memories=mem_hits if mem_hits else None,
                trace_id=trace.trace_id,
            ):
                if trace.interrupted:
                    break

                if isinstance(event, TokenDelta) and event.delta:
                    if not first_token_seen:
                        first_token_seen = True
                        trace.t_llm_first_token = time.monotonic_ns()

                    trace.tokens_out += 1
                    full_response_text.append(event.delta)
                    print(event.delta, end="", flush=True)

                    accumulated = "".join(full_response_text)
                    self._publish_caption(accumulated, source="assistant", is_final=False)

                    for chunk in self.chunker.feed(event.delta):
                        if trace.interrupted:
                            break
                        if chunk_index == 0:
                            trace.t_first_chunk = time.monotonic_ns()
                            self._set_state("speaking")

                        self._synthesize_chunk(trace, chunk.chunk_id, chunk.text)
                        chunk_index += 1

                elif isinstance(event, ToolCallEnd):
                    self._handle_tool_call(trace, event.call.tool, dict(event.call.args))

            # Flush remaining chunker text
            if not trace.interrupted:
                for chunk in self.chunker.flush():
                    self._synthesize_chunk(trace, chunk.chunk_id, chunk.text)
                    chunk_index += 1

                self.play_ring.set_flag(FLAG_EOS)

            trace.t_llm_done = time.monotonic_ns()
            print("\n", flush=True)

            if full_response_text and not trace.interrupted:
                reply_str = "".join(full_response_text)
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": reply_str})
                self._publish_caption(reply_str, source="assistant", is_final=True)

        except Exception as exc:  # noqa: BLE001
            if not trace.interrupted:
                logger.error("text_turn_execution_error", trace_id=trace.trace_id, error=str(exc))
                print(f"\n[Error] {exc}", flush=True)
            trace.interrupted = True
        finally:
            self._finalize_turn(trace, decision_id)

    def _synthesize_chunk(self, trace: TurnTrace, chunk_id: int, text: str) -> None:
        if chunk_id == 0:
            trace.t_tts_first_sent = time.monotonic_ns()

        _done = self.tts.synthesize(chunk_id=chunk_id, text=text, is_first=(chunk_id == 0))

        if chunk_id == 0:
            trace.t_tts_first_done = time.monotonic_ns()
        trace.chunks += 1

    def _speak_text(self, trace: TurnTrace, text: str) -> None:
        self.play_ring.clear_flag(FLAG_ABORT)
        self.play_ring.clear_flag(FLAG_EOS)
        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=time.monotonic_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        self._publish_bus(begin_env)
        self._set_state("speaking")
        self._publish_caption(text, source="assistant", is_final=True)
        self.tts.synthesize(chunk_id=0, text=text, is_first=True)
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

        self._set_state("confirm_wait", detail=action_desc)

        confirm_env = Envelope(
            type="ui.confirm",
            trace_id=trace.trace_id,
            ts_ns=time.monotonic_ns(),
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

        return self._confirm_result

    def _handle_tool_call(
        self,
        trace: TurnTrace,
        name: str,
        args: dict[str, JsonValue],
    ) -> ToolResult | None:
        self.executed_tools.append((name, args))
        call_id = str(ulid.ULID())
        self.current_turn_tool_calls.append(ToolCall(tool=name, args=dict(args), call_id=call_id))
        if not self.execute_tools:
            return None

        # Check confirmation requirement (WRITE / LAUNCH)
        if self.sandbox.check_confirmation_needed(name):
            confirmed = self._request_confirmation(trace, name, args)
            if not confirmed:
                logger.info("tool_execution_cancelled_by_user", tool=name)
                self._speak_text(trace, "Cancelled.")
                self.current_turn_tool_ok = False
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-3,
                    stderr="cancelled by user",
                    elapsed_ms=0.0,
                )

        res = self.sandbox.execute_tool(
            call_id=call_id,
            tool_name=name,
            args=args,
            confirmed=True,
        )
        if not res.ok:
            self.current_turn_tool_ok = False
        logger.info("tool_executed", tool=name, ok=res.ok, exit_code=res.exit_code)
        if res.ok:
            if name == "launch_app":
                app_name = str(args.get("app_name", "app"))
                self._speak_text(trace, f"Launched {app_name}.")
            elif name == "write_file":
                path = str(args.get("path", "file"))
                self._speak_text(trace, f"Saved {path}.")
            elif name == "delete_file":
                path = str(args.get("path", "file"))
                self._speak_text(trace, f"Deleted {path}.")
            elif name == "run_python":
                self._speak_text(trace, "Python script executed.")
        elif res.exit_code == -2 or "sandbox unavailable" in (res.stderr or ""):
            self._speak_text(trace, "My file sandbox isn't available — Docker isn't reachable.")
        else:
            self._speak_text(trace, f"Error: {res.stderr or 'action failed'}.")
        return res

    def _heartbeat_loop(self) -> None:
        while self.running:
            try:
                env = Envelope(
                    type="sys.ping",
                    trace_id="",
                    ts_ns=time.monotonic_ns(),
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
        if self.active_turn_thread and self.active_turn_thread.is_alive():
            self._abort_turn()
            self.active_turn_thread.join(timeout=1.0)
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
