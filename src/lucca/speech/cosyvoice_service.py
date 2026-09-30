"""
Project Lucca — CosyVoice 3 Frontier Neural Voice Service
Spec 07 §5, Spec 16 §4, ADR-008, WO-27

Resident GPU worker process running inside Python 3.10 (.venv-voice).
Binds to local ZeroMQ REP port 47005, serving low-latency zero-shot diffusion synthesis
with live 3D PAD affective stance instruction prompting.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Final

# Force UTF-8 encoding on Windows stdio
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

import numpy as np
import torch
import zmq

# Add CosyVoice to sys.path
COSYVOICE_DIR: Final[Path] = Path(r"C:\ProjectLucca\app\CosyVoice")
if str(COSYVOICE_DIR) not in sys.path:
    sys.path.insert(0, str(COSYVOICE_DIR))
    sys.path.insert(0, str(COSYVOICE_DIR / "third_party" / "Matcha-TTS"))

# Ensure src/ is in sys.path for lucca imports
SRC_DIR = Path(__file__).resolve().parent.parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cosyvoice.cli.cosyvoice import CosyVoice3
from lucca.senses.ring_buffer import FLAG_ABORT, PLAY_RING_NAME, SharedAudioRing

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("lucca.cosyvoice")

MODEL_DIR: Final[Path] = Path(r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512")
ENGLISH_VOICE_STEMS: Final[dict[str, Path]] = {
    "inventor": Path(r"C:\ProjectLucca\models\tts\samples\sample_systems_check_base.wav"),
    "companion": Path(r"C:\ProjectLucca\models\tts\samples\sample_intimate_reassurance_base.wav"),
    "heroine": Path(r"C:\ProjectLucca\models\tts\samples\sample_anta_baka_base.wav"),
}
DEFAULT_PROMPT_WAV: Final[Path] = ENGLISH_VOICE_STEMS["inventor"]
PORT: Final[int] = 47005


class CosyVoice3Service:
    """Resident CosyVoice 3 worker serving synthesis requests over ZeroMQ."""

    def __init__(self, port: int = PORT) -> None:
        self.port = port
        self.running = False
        logger.info("Initializing CosyVoice 3 model on CUDA...")
        t0 = time.perf_counter()
        self.cv3 = CosyVoice3(str(MODEL_DIR), fp16=True)
        init_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(f"CosyVoice 3 initialized in {init_ms:.1f}ms")

        # torch.compile the DiT estimator for fused CUDA kernel speedup (~1.5× on Blackwell SM120)
        # reduce-overhead mode: persistent CUDA graphs, minimal Python overhead per call
        # First inference call will trigger a ~90s tracing warmup; all subsequent calls are fast.
        logger.info("Compiling DiT estimator with torch.compile (reduce-overhead)...")
        try:
            self.cv3.model.flow.decoder.estimator = torch.compile(
                self.cv3.model.flow.decoder.estimator,
                mode="reduce-overhead",
                fullgraph=False,  # CausalConditionalCFM has data-dependent control flow
            )
            logger.info("DiT estimator compiled successfully.")
        except Exception as compile_exc:
            logger.warning("torch.compile failed, running uncompiled: %s", compile_exc)


        # Open shared memory audio playback ring buffer
        try:
            self.play_ring = SharedAudioRing(PLAY_RING_NAME)
            logger.info("Attached to shared audio ring buffer: %s", PLAY_RING_NAME)
        except Exception as exc:
            logger.warning("Could not attach to shared audio ring (%s); running in socket-only mode", exc)
            self.play_ring = None

        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.REP)
        self.socket.bind(f"tcp://127.0.0.1:{self.port}")
        logger.info(f"CosyVoice 3 service bound on tcp://127.0.0.1:{self.port}")

    def run(self) -> None:
        self.running = True
        logger.info("CosyVoice 3 service ready and waiting for requests.")
        while self.running:
            try:
                msg_bytes = self.socket.recv()
                req = json.loads(msg_bytes.decode("utf-8"))
                cmd = req.get("cmd", "synthesize")

                if cmd == "ping":
                    self.socket.send_json({
                        "status": "ok",
                        "engine": "CosyVoice 3 (Fun-CosyVoice3-0.5B-2512)",
                        "device": "CUDA",
                        "port": self.port,
                    })
                    continue

                if cmd == "shutdown":
                    self.socket.send_json({"status": "ok", "message": "shutting down"})
                    self.running = False
                    break

                if cmd in ("synthesize", "test_audio"):
                    resp = self._handle_synthesize(req, return_audio=(cmd == "test_audio"))
                    self.socket.send_json(resp)
                else:
                    self.socket.send_json({"status": "error", "error": f"Unknown command: {cmd}"})

            except zmq.ZMQError as exc:
                if not self.running:
                    break
                logger.error(f"ZMQ Error: {exc}")
            except Exception as exc:
                logger.exception(f"Unhandled error in request loop: {exc}")
                try:
                    self.socket.send_json({"status": "error", "error": str(exc)})
                except Exception as send_exc:
                    logger.debug("send_error_json_failed: %s", send_exc)

        self.socket.close(linger=0)
        self.ctx.destroy(linger=0)
        logger.info("CosyVoice 3 service terminated cleanly.")

    def _handle_synthesize(self, req: dict, return_audio: bool = False) -> dict:
        text = str(req.get("text", "")).strip()
        if not text:
            return {"status": "ok", "samples": 0, "elapsed_ms": 0.0}

        # Format instruct prompt
        instruct = req.get("instruct", "")
        if not instruct:
            instruct = "You are a helpful assistant. Please speak in English with a natural, clear cadence.<|endofprompt|>"
        if not instruct.endswith("<|endofprompt|>"):
            instruct = f"{instruct.strip()}<|endofprompt|>"

        # Determine reference audio path
        profile = str(req.get("profile", "inventor")).lower()
        prompt_wav = req.get("prompt_wav")
        if not prompt_wav or not Path(prompt_wav).exists():
            prompt_wav = str(ENGLISH_VOICE_STEMS.get(profile, DEFAULT_PROMPT_WAV))

        speed = float(req.get("speed", 1.0))
        stream = bool(req.get("stream", True))
        direct_ring = bool(req.get("direct_ring", True)) and (self.play_ring is not None)

        t0 = time.perf_counter()
        total_samples = 0
        chunks_emitted = 0
        collected_chunks = []

        try:
            for model_output in self.cv3.inference_instruct2(
                text,
                instruct,
                prompt_wav=prompt_wav,
                stream=stream,
                speed=speed,
            ):
                if self.play_ring and self.play_ring.has_flag(FLAG_ABORT):
                    logger.info("Synthesis aborted via play_ring FLAG_ABORT")
                    break

                chunk_f32 = model_output["tts_speech"].squeeze().cpu().numpy()
                if chunk_f32.ndim == 0:
                    continue

                total_samples += len(chunk_f32)
                chunks_emitted += 1

                if return_audio:
                    collected_chunks.append(chunk_f32)

                if direct_ring and self.play_ring is not None:
                    # Clip and convert to 16-bit PCM for 24kHz audio ring
                    chunk_i16 = (np.clip(chunk_f32, -1.0, 1.0) * 32767.0).astype(np.int16)
                    self.play_ring.write(chunk_i16)

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            resp: dict = {
                "status": "ok",
                "samples": total_samples,
                "elapsed_ms": round(elapsed_ms, 1),
                "chunks": chunks_emitted,
                "sample_rate": 24000,
            }

            if return_audio and collected_chunks:
                full_audio = np.concatenate(collected_chunks)
                audio_i16 = (np.clip(full_audio, -1.0, 1.0) * 32767.0).astype(np.int16)
                resp["audio_b64"] = base64.b64encode(audio_i16.tobytes()).decode("ascii")

            return resp

        except Exception as exc:
            logger.exception("Synthesis generation error: %s", exc)
            return {"status": "error", "error": str(exc)}


def main() -> None:
    service = CosyVoice3Service()
    try:
        service.run()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, stopping...")
        service.running = False


if __name__ == "__main__":
    main()
