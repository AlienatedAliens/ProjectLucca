"""
Fake TTS Worker for Deterministic Unit and Integration Tests
Spec 10 §1
"""

import time

import numpy as np

from lucca.core.ipc_schemas import TTSDonePayload
from lucca.senses.ring_buffer import FLAG_ABORT, SharedAudioRing


class FakeTTS:
    def __init__(self, play_ring: SharedAudioRing) -> None:
        self.play_ring = play_ring
        self.synthesized_chunks: list[dict[str, object]] = []
        self.active_voice = "af_heart"
        self.active_speed = 1.0

    def set_voice(self, voice: str) -> None:
        self.active_voice = voice

    def set_speed(self, speed: float) -> None:
        self.active_speed = speed

    def set_dsp_config(self, pitch_semitones: float = 0.0, enabled: bool = True) -> None:
        pass

    def synthesize(
        self,
        chunk_id: int,
        text: str,
        voice: str = "af_heart",
        is_first: bool = False,
    ) -> TTSDonePayload:
        t0 = time.perf_counter()
        if self.play_ring.has_flag(FLAG_ABORT):
            return TTSDonePayload(chunk_id=chunk_id, samples=0, elapsed_ms=0.0, device="CPU")

        # Generate a 200 ms 24 kHz synthetic sine burst (4800 samples)
        n_samples = 4800
        t = np.linspace(0, 0.2, n_samples, endpoint=False)
        sine = (np.sin(2 * np.pi * 440 * t) * 0.2 * 32767).astype(np.int16)

        written = self.play_ring.write(sine)
        dur_ms = (time.perf_counter() - t0) * 1000.0

        self.synthesized_chunks.append({"chunk_id": chunk_id, "text": text, "samples": written})

        return TTSDonePayload(
            chunk_id=chunk_id,
            samples=written,
            elapsed_ms=dur_ms,
            device="CPU",
        )
