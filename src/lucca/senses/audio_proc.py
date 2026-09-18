"""
Project Lucca — Audio Process (`lucca-audio`)
Spec 01 §1, §4, §5, Spec 07, ADR-008
"""

import math
import threading
import time
from typing import Final

import numpy as np
import numpy.typing as npt
import sounddevice as sd
import structlog
import zmq

from lucca.core.config import get_config
from lucca.core.exceptions import IPCError
from lucca.core.ipc_schemas import (
    AudioFirstSamplePlayedPayload,
    AudioRMSPayload,
    AudioUnderrunPayload,
    Envelope,
    PTTPressedPayload,
    PTTReleasedPayload,
    SysPongPayload,
    UIConfigUpdatePayload,
    decode_envelope,
    encode_envelope,
)
from lucca.senses.ptt import PTTListener
from lucca.senses.ring_buffer import (
    FLAG_ABORT,
    FLAG_EOS,
    get_capture_ring,
    get_playback_ring,
)
from lucca.senses.vad import EnergyVAD

PRE_ROLL_SAMPLES_16K: Final[int] = 3200  # 200 ms at 16 kHz
NON_SILENT_THRESHOLD_DBFS: Final[float] = -50.0

logger = structlog.get_logger(__name__)


class AudioProcess:
    def __init__(self) -> None:
        self.config = get_config()
        self.running = False

        # Rings
        self.cap_ring = get_capture_ring(create=False)
        self.play_ring = get_playback_ring(create=False)

        # State tracking
        self.active_trace_id: str | None = None
        self.first_sample_emitted = False
        self.is_playing = False
        self.underrun_count = 0
        self.jitter_ms = self.config.audio.jitter_ms
        self.jitter_samples = (self.config.audio.playback_rate * self.jitter_ms) // 1000

        self.ptt_press_seq = 0
        self.vad = EnergyVAD(sample_rate=self.config.audio.capture_rate)

        # ZeroMQ
        self.ctx = zmq.Context()
        self.ingest_sock = self.ctx.socket(zmq.PUSH)
        self.ctl_sock = self.ctx.socket(zmq.DEALER)
        self.bus_sock = self.ctx.socket(zmq.SUB)

        # Streams
        self.input_stream: sd.InputStream | None = None
        self.output_stream: sd.OutputStream | None = None

        # PTT (Right-Ctrl or Alt-Gr)
        self.ptt = PTTListener(
            on_pressed=self._on_ptt_pressed,
            on_released=self._on_ptt_released,
            max_duration_s=self.config.ptt.max_seconds,
            key_name=self.config.ptt.key,
        )

    def _on_ptt_pressed(self, ts_ns: int) -> None:
        # Snapshot ring write index with 200ms pre-roll
        current_w = self.cap_ring.write_idx
        self.ptt_press_seq = max(0, current_w - PRE_ROLL_SAMPLES_16K)

        # Immediate barge-in if currently playing
        if self.is_playing:
            self._handle_barge_in()

        print("\n[AUDIO] PTT Pressed -> Capturing microphone...", flush=True)
        env = Envelope(
            type="ptt.pressed",
            trace_id="",
            ts_ns=ts_ns,
            src="audio",
            payload=PTTPressedPayload(t_ns=ts_ns).model_dump(),
        )
        self._send_ingest(env)

    def _on_ptt_released(self, ts_ns: int, duration_ms: float) -> None:
        capture_end = self.cap_ring.write_idx
        capture_start = self.ptt_press_seq

        # Run VAD over captured slice
        slice_samples = self.cap_ring.read_slice(capture_start, capture_end)
        vad_ms, _, _ = self.vad.process(slice_samples)

        print(f"[AUDIO] PTT Released ({duration_ms:.0f}ms, speech: {vad_ms:.0f}ms)", flush=True)
        env = Envelope(
            type="ptt.released",
            trace_id="",
            ts_ns=ts_ns,
            src="audio",
            payload=PTTReleasedPayload(
                t_ns=ts_ns,
                capture_seq_start=capture_start,
                capture_seq_end=capture_end,
                duration_ms=duration_ms,
                vad_speech_ms=vad_ms,
            ).model_dump(),
        )
        self._send_ingest(env)

    def _handle_barge_in(self) -> None:
        """Instantly terminates playback and drains output ring (< 5 ms)."""
        self.play_ring.set_flag(FLAG_ABORT)
        self.is_playing = False
        self.first_sample_emitted = False
        self.active_trace_id = None

    def _input_callback(
        self,
        indata: npt.NDArray[np.int16],
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        # Fast write into 16 kHz capture ring (latency < 0.1 ms)
        self.cap_ring.write(indata.copy())

    def _output_callback(
        self,
        outdata: npt.NDArray[np.int16],
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        # Fast non-blocking read from 24 kHz playback ring
        avail = self.play_ring.available_read
        is_eos = self.play_ring.has_flag(FLAG_EOS)

        # Check jitter buffer gate before starting playback
        if not self.is_playing:
            if avail >= self.jitter_samples or is_eos:
                self.is_playing = True
            else:
                outdata.fill(0)
                return

        samples = self.play_ring.read(frames)
        n = len(samples)
        if n == frames:
            outdata[:, 0] = samples
        elif n > 0:
            outdata[:n, 0] = samples
            outdata[n:, 0] = 0
        else:
            outdata.fill(0)

        # Calculate RMS & check first non-silent sample
        if len(samples) > 0:
            samples_f = samples.astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples_f**2) + 1e-12))
            dbfs = 20.0 * math.log10(max(rms, 1e-6))

            if not self.first_sample_emitted and dbfs > NON_SILENT_THRESHOLD_DBFS:
                self.first_sample_emitted = True
                if self.active_trace_id:
                    now_ns = time.monotonic_ns()
                    env = Envelope(
                        type="audio.first_sample_played",
                        trace_id=self.active_trace_id,
                        ts_ns=now_ns,
                        src="audio",
                        payload=AudioFirstSamplePlayedPayload(
                            trace_id=self.active_trace_id, t_ns=now_ns
                        ).model_dump(),
                    )
                    self._send_ingest(env)

            # Publish RMS for UI lip-flap (rate-limited)
            if self.is_playing:
                rms_env = Envelope(
                    type="audio.rms",
                    trace_id=self.active_trace_id or "",
                    ts_ns=time.monotonic_ns(),
                    src="audio",
                    payload=AudioRMSPayload(t_ns=time.monotonic_ns(), dbfs=dbfs).model_dump(),
                )
                self._send_ingest(rms_env)

        # Check for completion: ring drained and EOS reached
        if avail == 0 and is_eos and self.is_playing:
            self.is_playing = False
            self.first_sample_emitted = False
            self.play_ring.clear_flag(FLAG_EOS)

        # Check for underrun if ring ran dry while turn still active
        elif avail == 0 and not is_eos and self.is_playing:
            self.underrun_count += 1
            if self.underrun_count % 3 == 0:
                self.jitter_ms = min(120, self.jitter_ms + 20)
                self.jitter_samples = (self.config.audio.playback_rate * self.jitter_ms) // 1000
            env = Envelope(
                type="audio.underrun",
                trace_id=self.active_trace_id or "",
                ts_ns=time.monotonic_ns(),
                src="audio",
                payload=AudioUnderrunPayload(count=self.underrun_count).model_dump(),
            )
            self._send_ingest(env)

    def _send_ingest(self, env: Envelope) -> None:
        try:
            self.ingest_sock.send(encode_envelope(env), zmq.NOBLOCK)
        except zmq.ZMQError as exc:
            logger.debug("audio_send_ingest_zmq_error", error=str(exc))

    def start(self) -> None:
        self.running = True

        # Connect sockets
        self.ingest_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.ingest_port}")
        self.ctl_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.ctl_port}")
        self.bus_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.bus_port}")
        self.bus_sock.setsockopt_string(zmq.SUBSCRIBE, "")

        # Resolve audio devices
        dev_in: int | str | None = None
        if self.config.audio.capture_device:
            try:
                dev_in = int(self.config.audio.capture_device)
            except ValueError:
                dev_in = self.config.audio.capture_device

        dev_out: int | str | None = None
        if self.config.audio.playback_device:
            try:
                dev_out = int(self.config.audio.playback_device)
            except ValueError:
                dev_out = self.config.audio.playback_device

        # Open audio devices
        self.input_stream = sd.InputStream(
            device=dev_in,
            samplerate=self.config.audio.capture_rate,
            channels=1,
            dtype="int16",
            callback=self._input_callback,
            blocksize=320,  # 20 ms
        )
        self.output_stream = sd.OutputStream(
            device=dev_out,
            samplerate=self.config.audio.playback_rate,
            channels=1,
            dtype="int16",
            callback=self._output_callback,
            blocksize=480,  # 20 ms
        )
        self.input_stream.start()
        self.output_stream.start()

        # Start PTT
        self.ptt.start()

        # Start control listener thread
        ctl_thread = threading.Thread(target=self._ctl_loop, name="audio-ctl", daemon=True)
        ctl_thread.start()

    def _ctl_loop(self) -> None:
        poller = zmq.Poller()
        poller.register(self.ctl_sock, zmq.POLLIN)
        poller.register(self.bus_sock, zmq.POLLIN)

        while self.running:
            try:
                socks = dict(poller.poll(timeout=100))
            except zmq.ZMQError as exc:
                if not self.running:
                    break
                logger.debug("audio_poller_zmq_error", error=str(exc))
                continue

            if self.ctl_sock in socks:
                try:
                    raw = self.ctl_sock.recv()
                    env = decode_envelope(raw)
                    if env.type == "sys.ping":
                        pong = Envelope(
                            type="sys.pong",
                            trace_id=env.trace_id,
                            ts_ns=time.monotonic_ns(),
                            src="audio",
                            payload=SysPongPayload(rss_mb=50.0, queue_depth=0).model_dump(),
                        )
                        self.ctl_sock.send(encode_envelope(pong))
                    elif env.type == "play.begin":
                        self.active_trace_id = env.trace_id
                        self.first_sample_emitted = False
                        self.play_ring.clear_flag(FLAG_ABORT)
                        self.play_ring.clear_flag(FLAG_EOS)
                    elif env.type == "play.abort":
                        self._handle_barge_in()
                    elif env.type == "sys.shutdown":
                        self.running = False
                        break
                except (IPCError, zmq.ZMQError) as exc:
                    logger.debug("audio_ctl_message_error", error=str(exc))

            if self.bus_sock in socks:
                try:
                    raw = self.bus_sock.recv()
                    env = decode_envelope(raw)
                    if env.type == "play.abort":
                        self._handle_barge_in()
                    elif env.type == "sys.shutdown":
                        self.running = False
                        break
                    elif env.type == "play.begin":
                        self.active_trace_id = env.trace_id
                        self.first_sample_emitted = False
                        self.play_ring.clear_flag(FLAG_ABORT)
                        self.play_ring.clear_flag(FLAG_EOS)
                    elif env.type == "ui.config_update":
                        p_cfg = UIConfigUpdatePayload.model_validate(env.payload)
                        if p_cfg.ptt_key:
                            self.ptt.set_key(p_cfg.ptt_key)
                            print(
                                f"[AUDIO] PTT target key reconfigured to: {p_cfg.ptt_key}",
                                flush=True,
                            )
                    elif env.type == "ui.talk_press":
                        self._on_ptt_pressed(env.ts_ns)
                    elif env.type == "ui.talk_release":
                        dur_ms = 1000.0
                        if isinstance(env.payload, dict) and "duration_ms" in env.payload:
                            dur_ms = float(str(env.payload["duration_ms"]))
                        self._on_ptt_released(env.ts_ns, dur_ms)
                except (IPCError, zmq.ZMQError) as exc:
                    logger.debug("audio_bus_message_error", error=str(exc))

    def stop(self) -> None:
        self.running = False
        self.ptt.stop()
        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop()
            self.output_stream.close()
        self.ctx.term()


def main() -> None:
    proc = AudioProcess()
    try:
        proc.start()
        while proc.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        proc.stop()


if __name__ == "__main__":
    main()
