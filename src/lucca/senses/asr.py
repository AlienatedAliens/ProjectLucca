"""
Project Lucca — ASR Subsystem
Spec 07 §4, ADR-001, D-02
"""

import hashlib
import threading
import time

import numpy as np
import numpy.typing as npt
import structlog

try:
    import faster_whisper
except ImportError:
    faster_whisper = None

from lucca.core.config import get_config
from lucca.core.ipc_schemas import ASRResultPayload
from lucca.core.schemas import Segment

logger = structlog.get_logger(__name__)


class ASRWorker:
    """
    Asynchronous Speech Transcription Worker.
    Runs faster-whisper int8 or OpenVINO iGPU.
    """

    def __init__(self) -> None:
        self.config = get_config()
        self.model = None
        self._lock = threading.Lock()
        self._init_model()

    def _init_model(self) -> None:
        # Ensure cublas DLL path is available for CUDA faster-whisper on Windows
        import os

        cublas_path = r"C:\ProjectLucca\app\llama-server"
        if os.path.exists(cublas_path) and cublas_path not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{cublas_path};" + os.environ.get("PATH", "")

        if faster_whisper is None:
            self.backend = "failed: faster_whisper not installed"
            logger.warning("faster_whisper_not_installed")
            return

        try:
            # Primary acceleration: CUDA float16 on discrete GPU (~68-85 ms latency)
            self.model = faster_whisper.WhisperModel(
                "distil-small.en",
                device="cuda",
                compute_type="float16",
            )
            self.backend = "faster-whisper-cuda-float16"
            logger.info("asr_initialized_cuda", backend=self.backend)
        except Exception as cuda_err:
            logger.info("asr_cuda_fallback_to_cpu", reason=str(cuda_err))
            try:
                # Fallback: CPU int8 with 6 worker threads
                self.model = faster_whisper.WhisperModel(
                    "distil-small.en",
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=6,
                )
                self.backend = "faster-whisper-cpu-int8"
                logger.info("asr_initialized_cpu_fallback", backend=self.backend)
            except (OSError, RuntimeError) as e:
                logger.warning("faster_whisper_init_failed", error=str(e))
                self.backend = f"failed: {e}"

    def transcribe(self, pcm_int16: npt.NDArray[np.int16]) -> ASRResultPayload:
        t0 = time.perf_counter()
        if len(pcm_int16) == 0:
            return ASRResultPayload(
                text="",
                segments=[],
                avg_logprob=0.0,
                model=self.backend,
                audio_sha256="",
                elapsed_ms=0.0,
            )

        audio_bytes = pcm_int16.tobytes()
        audio_sha256 = hashlib.sha256(audio_bytes).hexdigest()

        # Convert int16 to float32 [-1, 1]
        audio_f32 = pcm_int16.astype(np.float32) / 32768.0

        if self.model is None:
            return ASRResultPayload(
                text="",
                segments=[],
                avg_logprob=0.0,
                model=self.backend,
                audio_sha256=audio_sha256,
                elapsed_ms=0.0,
            )

        segments_out: list[Segment] = []
        full_text_parts: list[str] = []
        logprobs: list[float] = []

        with self._lock:
            try:
                segments_iter, _ = self.model.transcribe(
                    audio_f32,
                    language="en",
                    task="transcribe",
                    beam_size=1,
                    temperature=0.0,
                )

                for seg in segments_iter:
                    seg_text = seg.text.strip()
                    if seg_text:
                        full_text_parts.append(seg_text)
                        logprobs.append(float(seg.avg_logprob))
                        segments_out.append(
                            Segment(
                                t0=float(seg.start),
                                t1=float(seg.end),
                                text=seg_text,
                                avg_logprob=float(seg.avg_logprob),
                            )
                        )
            except RuntimeError as exc:
                logger.warning("asr_transcribe_runtime_error", error=str(exc))
                return ASRResultPayload(
                    text="",
                    segments=[],
                    avg_logprob=0.0,
                    model=self.backend,
                    audio_sha256=audio_sha256,
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )

        full_text = " ".join(full_text_parts)
        avg_logprob = float(np.mean(logprobs)) if logprobs else 0.0
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return ASRResultPayload(
            text=full_text,
            segments=segments_out,
            avg_logprob=avg_logprob,
            model=self.backend,
            audio_sha256=audio_sha256,
            elapsed_ms=elapsed_ms,
        )
