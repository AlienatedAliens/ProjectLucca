"""
Project Lucca — Central Orchestrator & State Machine
Spec 01 §3, §4, §6, Spec 10, ADR-008
"""

import base64
import io
import subprocess
import threading
import time
import wave
from typing import Any, Literal

import structlog
import ulid
import zmq

from lucca.brain.chunker import StreamingChunker
from lucca.brain.llm_client import LLMClient
from lucca.core.config import get_config
from lucca.core.ipc_schemas import (
    Envelope,
    PlayAbortPayload,
    PlayBeginPayload,
    PTTReleasedPayload,
    UIStatePayload,
    decode_envelope,
    encode_envelope,
)
from lucca.core.schemas import TokenDelta, ToolCallEnd
from lucca.core.trace import TurnTrace, log_turn_trace
from lucca.senses.ring_buffer import (
    FLAG_ABORT,
    FLAG_EOS,
    get_capture_ring,
    get_playback_ring,
)
from lucca.senses.tts import TTSWorker

logger = structlog.get_logger(__name__)

TurnState = Literal[
    "idle", "listening", "thinking", "speaking", "confirm_wait", "postturn", "degraded"
]


class Orchestrator:
    def __init__(
        self,
        llm: LLMClient | None = None,
        tts: Any | None = None,
        execute_tools: bool = True,
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

        # Turn context
        self.active_trace: TurnTrace | None = None
        self.active_turn_thread: threading.Thread | None = None
        self.history: list[dict[str, str]] = []
        self.executed_tools: list[tuple[str, dict[str, object]]] = []
        self._turn_lock = threading.Lock()

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
            elif env.type == "audio.first_sample_played":
                if self.active_trace:
                    self.active_trace.t_first_sample = env.ts_ns

    def _on_ptt_pressed(self, ts_ns: int) -> None:
        if self.state in ("speaking", "thinking", "confirm_wait"):
            # Instant barge-in: abort LLM and playback
            self._abort_turn()

        self._set_state("listening")

    def _abort_turn(self) -> None:
        self.llm.abort()
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
        trace_id = str(ulid.ULID())
        trace = TurnTrace(
            trace_id=trace_id,
            mode=self.config.llm.mode,
            t_key_release=ts_ns,
        )
        self.active_trace = trace
        self._set_state("thinking")

        # Launch turn worker thread
        t = threading.Thread(target=self._run_turn, args=(trace, p), daemon=True)
        self.active_turn_thread = t
        t.start()

    def _run_turn(self, trace: TurnTrace, p: PTTReleasedPayload) -> None:
        trace.t_llm_sent = time.monotonic_ns()

        # Read audio slice from capture ring
        pcm_samples = self.cap_ring.read_slice(p.capture_seq_start, p.capture_seq_end)

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
        full_response_text = []

        try:
            for event in self.llm.stream_turn(current_audio_b64=wav_b64, history=self.history):
                if trace.interrupted:
                    break

                if isinstance(event, TokenDelta) and event.delta:
                    if not first_token_seen:
                        first_token_seen = True
                        trace.t_llm_first_token = time.monotonic_ns()

                    trace.tokens_out += 1
                    full_response_text.append(event.delta)

                    for chunk in self.chunker.feed(event.delta):
                        if trace.interrupted:
                            break
                        if chunk_index == 0:
                            trace.t_first_chunk = time.monotonic_ns()
                            self._set_state("speaking")

                        self._synthesize_chunk(trace, chunk.chunk_id, chunk.text)
                        chunk_index += 1

                elif isinstance(event, ToolCallEnd):
                    # Execute tool call
                    self._handle_tool_call(trace, event.call.tool, dict(event.call.args))

            # Flush remaining chunker text
            if not trace.interrupted:
                for chunk in self.chunker.flush():
                    self._synthesize_chunk(trace, chunk.chunk_id, chunk.text)
                    chunk_index += 1

                # Signal End of Speech on playback ring
                self.play_ring.set_flag(FLAG_EOS)

            trace.t_llm_done = time.monotonic_ns()

            # Record turn in history
            if full_response_text and not trace.interrupted:
                reply_str = "".join(full_response_text)
                self.history.append({"role": "assistant", "content": reply_str})

        except Exception as exc:  # noqa: BLE001
            if not trace.interrupted:
                logger.error("turn_execution_error", trace_id=trace.trace_id, error=str(exc))
            trace.interrupted = True
        finally:
            trace.t_postturn_done = time.monotonic_ns()
            log_turn_trace(trace)
            self._set_state("idle")

    def _synthesize_chunk(self, trace: TurnTrace, chunk_id: int, text: str) -> None:
        if chunk_id == 0:
            trace.t_tts_first_sent = time.monotonic_ns()

        _done = self.tts.synthesize(chunk_id=chunk_id, text=text, is_first=(chunk_id == 0))

        if chunk_id == 0:
            trace.t_tts_first_done = time.monotonic_ns()
        trace.chunks += 1

    def _handle_tool_call(self, trace: TurnTrace, name: str, args: dict[str, object]) -> None:
        self.executed_tools.append((name, args))
        if not self.execute_tools:
            return

        if name == "launch_app":
            app = str(args.get("app_name", ""))
            cmd_map: dict[str, list[str]] = {
                "calculator": ["calc.exe"],
                "notepad": ["notepad.exe"],
                "terminal": ["wt.exe"],
                "browser": ["cmd.exe", "/c", "start", "msedge"],
                "task_manager": ["taskmgr.exe"],
            }
            cmd = cmd_map.get(app)
            if cmd:
                try:
                    subprocess.Popen(cmd)  # noqa: S603
                except OSError as exc:
                    logger.warning("launch_app_failed", app=app, error=str(exc))

    def _heartbeat_loop(self) -> None:
        while self.running:
            time.sleep(2.0)

    def stop(self) -> None:
        self.running = False
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
