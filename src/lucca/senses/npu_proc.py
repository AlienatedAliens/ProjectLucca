"""
Project Lucca — NPU & AI Worker Process (`lucca-npu`)
Spec 01 §1, §4, Spec 07, ADR-008
"""

import psutil
import structlog
import zmq

from lucca.core.config import get_config
from lucca.core.exceptions import IPCError
from lucca.core.ipc_schemas import (
    ASRTranscribePayload,
    EmbedResultPayload,
    EmbedTextPayload,
    Envelope,
    IntentEncodePayload,
    IntentResultPayload,
    SysPongPayload,
    SysSelfTestResultPayload,
    TTSAbortedPayload,
    TTSSynthesizePayload,
    decode_envelope,
    encode_envelope,
)
from lucca.core.trace import now_ns
from lucca.senses.asr import ASRWorker
from lucca.senses.embed import EmbedWorker
from lucca.senses.ring_buffer import (
    FLAG_ABORT,
    SharedAudioRing,
    get_capture_ring,
    get_playback_ring,
)
from lucca.senses.tts import TTSWorker

logger = structlog.get_logger(__name__)


class NPUProcess:
    def __init__(
        self,
        cap_ring: SharedAudioRing | None = None,
        play_ring: SharedAudioRing | None = None,
        asr: ASRWorker | None = None,
        tts: TTSWorker | None = None,
        embed: EmbedWorker | None = None,
        ctx: zmq.Context[zmq.Socket[bytes]] | None = None,
    ) -> None:
        self.config = get_config()
        self.running = False

        # Attach to rings
        self.cap_ring = cap_ring if cap_ring is not None else get_capture_ring(create=False)
        self.play_ring = play_ring if play_ring is not None else get_playback_ring(create=False)

        # Workers
        self.asr = asr if asr is not None else ASRWorker()
        self.tts = tts if tts is not None else TTSWorker(self.play_ring)
        self.embed = embed if embed is not None else EmbedWorker()

        # ZeroMQ
        self.ctx = ctx if ctx is not None else zmq.Context()
        self.ctl_sock = self.ctx.socket(zmq.DEALER)
        self.bus_sock = self.ctx.socket(zmq.SUB)
        self.ingest_sock = self.ctx.socket(zmq.PUSH)

    def start(self) -> None:
        self.running = True
        self.ctl_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.ctl_port}")
        self.bus_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.bus_port}")
        self.bus_sock.setsockopt_string(zmq.SUBSCRIBE, "")
        self.ingest_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.ingest_port}")

        poller = zmq.Poller()
        poller.register(self.ctl_sock, zmq.POLLIN)
        poller.register(self.bus_sock, zmq.POLLIN)

        while self.running:
            try:
                socks = dict(poller.poll(timeout=100))
            except zmq.ZMQError:
                if not self.running:
                    break
                continue

            if self.ctl_sock in socks:
                try:
                    raw = self.ctl_sock.recv()
                    env = decode_envelope(raw)
                    self._handle_ctl_request(env)
                except (IPCError, zmq.ZMQError, ValueError) as e:
                    logger.warning("npu_ctl_request_error", error=str(e))

            if self.bus_sock in socks:
                try:
                    raw = self.bus_sock.recv()
                    env = decode_envelope(raw)
                    if env.type == "sys.ping":
                        rss_mb = psutil.Process().memory_info().rss / (1024.0 * 1024.0)
                        reply = Envelope(
                            type="sys.pong",
                            trace_id=env.trace_id,
                            ts_ns=now_ns(),
                            src="npu",
                            payload=SysPongPayload(rss_mb=rss_mb, queue_depth=0).model_dump(),
                        )
                        try:
                            self.ingest_sock.send(encode_envelope(reply), zmq.NOBLOCK)
                        except zmq.ZMQError as exc:
                            logger.debug("npu_send_pong_zmq_error", error=str(exc))
                    elif env.type in ("tts.abort", "play.abort"):
                        self.play_ring.set_flag(FLAG_ABORT)
                    elif env.type == "sys.shutdown":
                        self.running = False
                        break
                except (IPCError, zmq.ZMQError) as exc:
                    logger.debug("npu_bus_message_error", error=str(exc))

    def _handle_ctl_request(self, env: Envelope) -> None:
        ctl_ts_ns = now_ns()

        if env.type == "sys.ping":
            rss_mb = psutil.Process().memory_info().rss / (1024.0 * 1024.0)
            reply = Envelope(
                type="sys.pong",
                trace_id=env.trace_id,
                ts_ns=ctl_ts_ns,
                src="npu",
                payload=SysPongPayload(rss_mb=rss_mb, queue_depth=0).model_dump(),
            )
            self.ctl_sock.send(encode_envelope(reply))
            try:
                self.ingest_sock.send(encode_envelope(reply), zmq.NOBLOCK)
            except zmq.ZMQError as exc:
                logger.debug("npu_send_pong_zmq_error", error=str(exc))

        elif env.type == "sys.selftest":
            reply = Envelope(
                type="sys.selftest_result",
                trace_id=env.trace_id,
                ts_ns=ctl_ts_ns,
                src="npu",
                payload=SysSelfTestResultPayload(
                    asr_device=self.asr.backend,
                    tts_device=self.tts.device,
                    embed_device=self.embed.device,
                    compile_cache_hit=False,
                ).model_dump(),
            )
            self.ctl_sock.send(encode_envelope(reply))

        elif env.type == "asr.transcribe":
            p_asr = ASRTranscribePayload.model_validate(env.payload)
            # Read captured audio slice from shared memory
            slice_samples = self.cap_ring.read_slice(p_asr.capture_seq_start, p_asr.capture_seq_end)
            res = self.asr.transcribe(slice_samples)
            reply = Envelope(
                type="asr.result",
                trace_id=env.trace_id,
                ts_ns=now_ns(),
                src="npu",
                payload=res.model_dump(),
            )
            self.ctl_sock.send(encode_envelope(reply))

        elif env.type == "tts.synthesize":
            p_tts = TTSSynthesizePayload.model_validate(env.payload)
            done = self.tts.synthesize(
                chunk_id=p_tts.chunk_id,
                text=p_tts.text,
                voice=p_tts.voice,
                is_first=p_tts.is_first,
            )
            reply = Envelope(
                type="tts.done",
                trace_id=env.trace_id,
                ts_ns=now_ns(),
                src="npu",
                payload=done.model_dump(),
            )
            self.ctl_sock.send(encode_envelope(reply))

        elif env.type == "tts.abort":
            self.play_ring.set_flag(FLAG_ABORT)
            reply = Envelope(
                type="tts.aborted",
                trace_id=env.trace_id,
                ts_ns=now_ns(),
                src="npu",
                payload=TTSAbortedPayload(trace_id=env.trace_id).model_dump(),
            )
            self.ctl_sock.send(encode_envelope(reply))

        elif env.type == "embed.text":
            p_embed = EmbedTextPayload.model_validate(env.payload)
            vecs, dim, el = self.embed.embed_text(p_embed.texts)
            reply = Envelope(
                type="embed.result",
                trace_id=env.trace_id,
                ts_ns=now_ns(),
                src="npu",
                payload=EmbedResultPayload(vectors=vecs, dim=dim, elapsed_ms=el).model_dump(),
            )
            self.ctl_sock.send(encode_envelope(reply))

        elif env.type == "intent.encode":
            p_intent = IntentEncodePayload.model_validate(env.payload)
            vecs, dim, el = self.embed.embed_text([p_intent.text])
            reply = Envelope(
                type="intent.result",
                trace_id=env.trace_id,
                ts_ns=now_ns(),
                src="npu",
                payload=IntentResultPayload(vector=vecs[0], elapsed_ms=el).model_dump(),
            )
            self.ctl_sock.send(encode_envelope(reply))

    def stop(self) -> None:
        self.running = False
        try:
            self.ctl_sock.close(linger=0)
            self.bus_sock.close(linger=0)
            self.ingest_sock.close(linger=0)
        except (zmq.ZMQError, OSError) as exc:
            logger.debug("npu_stop_socket_close_error", error=str(exc))
        self.ctx.destroy(linger=0)


def main() -> None:
    proc = NPUProcess()
    try:
        proc.start()
    finally:
        proc.stop()


if __name__ == "__main__":
    main()
