"""
Fake ASR Worker for Deterministic Unit and Integration Tests
Spec 10 §1
"""

import numpy as np
import numpy.typing as npt

from lucca.core.ipc_schemas import ASRResultPayload


class FakeASR:
    def __init__(self, transcript: str = "test input") -> None:
        self.transcript = transcript
        self.backend = "fake-asr"

    def transcribe(self, pcm_int16: npt.NDArray[np.int16]) -> ASRResultPayload:  # noqa: ARG002
        return ASRResultPayload(
            text=self.transcript,
            segments=[],
            avg_logprob=0.0,
            model=self.backend,
            audio_sha256="0" * 64,
            elapsed_ms=1.0,
        )
