"""
Project Lucca — TTS Subsystem (Kokoro-82M)
Spec 07 §5, ADR-008
"""

import time
from pathlib import Path
from typing import Literal

import kokoro_onnx
import numpy as np

from lucca.core.config import get_config
from lucca.core.ipc_schemas import TTSDonePayload
from lucca.senses.ring_buffer import FLAG_ABORT, SharedAudioRing


class TTSWorker:
    def __init__(self, play_ring: SharedAudioRing) -> None:
        self.config = get_config()
        self.play_ring = play_ring
        self.device: Literal["NPU", "GPU", "CPU"] = "CPU"

        model_path = Path(r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx")
        voices_path = Path(r"C:\ProjectLucca\models\tts\voices-v1.0.bin")

        self.active_voice = self.config.tts.voice
        self.active_speed = getattr(self.config.tts, "speed", 1.05)
        if not model_path.exists() or not voices_path.exists():
            # Fallback to dev/mock if models missing
            self.engine = None
        else:
            self.engine = kokoro_onnx.Kokoro(str(model_path), str(voices_path))

    def set_voice(self, voice: str) -> None:
        self.active_voice = voice

    def set_speed(self, speed: float) -> None:
        self.active_speed = speed

    def synthesize(
        self,
        chunk_id: int,
        text: str,
        voice: str | None = None,
        speed: float | None = None,
        is_first: bool = False,
    ) -> TTSDonePayload:
        t0 = time.perf_counter()

        if self.play_ring.has_flag(FLAG_ABORT):
            return TTSDonePayload(
                chunk_id=chunk_id, samples=0, elapsed_ms=0.0, device=self.device
            )

        clean_text = text.strip()
        if not clean_text or self.engine is None:
            return TTSDonePayload(
                chunk_id=chunk_id, samples=0, elapsed_ms=0.0, device=self.device
            )

        v = voice or self.active_voice
        s = speed if speed is not None else self.active_speed

        # Kokoro produces 24000 Hz float32 audio
        samples_f32, sr = self.engine.create(clean_text, voice=v, speed=s)
        dur_ms = (time.perf_counter() - t0) * 1000.0

        # Check abort again
        if self.play_ring.has_flag(FLAG_ABORT):
            return TTSDonePayload(
                chunk_id=chunk_id, samples=0, elapsed_ms=dur_ms, device=self.device
            )

        # Convert to int16 PCM [-32768, 32767]
        samples_int16 = (np.clip(samples_f32, -1.0, 1.0) * 32767).astype(np.int16)

        # Write directly into 24 kHz playback ring
        written = self.play_ring.write(samples_int16)

        return TTSDonePayload(
            chunk_id=chunk_id,
            samples=written,
            elapsed_ms=dur_ms,
            device=self.device,
        )
