"""
Project Lucca — Asuka RVC Real-Time Voice Conversion Engine
Spec 07 §5, ADR-008

Plugs into TTSWorker to provide low-latency (~90ms on RTX 5080) neural voice conversion
from Kokoro base speech into Asuka Langley Soryu character timbre.
Supports direct GPU in-process execution (Python 3.10 / .venv-voice) and
cross-environment IPC delegation when invoked from Python 3.12 (.venv).
"""

from __future__ import annotations

import atexit
import os
import struct
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
MODELS_DIR = Path(r"C:\ProjectLucca\models\tts")
RVC_DIR = MODELS_DIR / "rvc"
HUBERT_PATH = RVC_DIR / "hubert_base.pt"
ASUKA_PTH = RVC_DIR / "asuka" / "asuka.pth"
ASUKA_INDEX = RVC_DIR / "asuka" / "added_IVF470_Flat_nprobe_1_asuka_v2.index"

# Detect whether GPU PyTorch + Fairseq are present in the current Python interpreter
try:
    import faiss
    import fairseq
    import parselmouth
    import torch
    import torchaudio
    from lucca.speech.rvc.models import SynthesizerTrnMs768NSFsid

    _LOCAL_GPU_RVC_CAPABLE = True
except ImportError:
    _LOCAL_GPU_RVC_CAPABLE = False


class AsukaRVCConverter:
    """
    Direct in-process GPU voice conversion engine for Asuka Langley Soryu.
    Applies calibrated pitch shift (+6 st), continuous F0 interpolation,
    Praat autocorrelation tracking, and 64-tap Kaiser sinc anti-aliasing.
    """

    def __init__(self, device: str = "cuda:0") -> None:
        self.device = device if (_LOCAL_GPU_RVC_CAPABLE and torch.cuda.is_available()) else "cpu"
        self._initialized = False
        self.hubert: Any = None
        self.net_g: Any = None
        self.faiss_index: Any = None
        self.rvc_sr = 40000
        self.f0_up_key = 6  # Calibrated sweet spot for Asuka (+6 semitones)
        self.index_rate = 0.0  # Pure neural generator (zero index jumping)

    def load_models(self) -> bool:
        if self._initialized:
            return True

        if not HUBERT_PATH.exists() or not ASUKA_PTH.exists():
            logger.warning("asuka_rvc_models_missing", hubert=str(HUBERT_PATH), pth=str(ASUKA_PTH))
            return False

        if not _LOCAL_GPU_RVC_CAPABLE:
            return False

        try:
            # 1. Load HuBERT
            _orig_load = torch.load
            torch.load = lambda *args, **kwargs: _orig_load(*args, **{**kwargs, "weights_only": False})

            hubert_models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task([str(HUBERT_PATH)])
            self.hubert = hubert_models[0].to(self.device).eval()

            # 2. Load Asuka Synthesizer
            cpt = torch.load(str(ASUKA_PTH), map_location="cpu", weights_only=False)
            target_sr = cpt.get("sr", 40000)
            if isinstance(target_sr, str) and target_sr.endswith("k"):
                target_sr = int(target_sr[:-1]) * 1000
            self.rvc_sr = target_sr

            self.net_g = SynthesizerTrnMs768NSFsid(*cpt["config"], is_half=False).to(self.device)
            self.net_g.load_state_dict(cpt["weight"], strict=False)
            self.net_g.eval()

            # 3. Load FAISS Index if available
            if ASUKA_INDEX.exists():
                self.faiss_index = faiss.read_index(str(ASUKA_INDEX))

            self._initialized = True
            logger.info("asuka_rvc_engine_loaded", device=self.device, sr=self.rvc_sr)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("asuka_rvc_load_failed", error=str(exc))
            return False

    def convert(
        self,
        audio_f32: np.ndarray,
        orig_sr: int = 24000,
        out_sr: int = 24000,
    ) -> np.ndarray:
        """
        Converts input float32 audio waveform into Asuka character speech.
        Returns float32 audio matching out_sr (default 24kHz for Lucca playback ring).
        """
        if not self._initialized and not self.load_models():
            return audio_f32

        if len(audio_f32) < 400:
            return audio_f32

        try:
            # 1. Resample to 16kHz for HuBERT via 64-tap Kaiser sinc
            audio_tensor = torch.from_numpy(audio_f32).float().unsqueeze(0)
            if orig_sr != 16000:
                resampler_16k = torchaudio.transforms.Resample(
                    orig_freq=orig_sr,
                    new_freq=16000,
                    lowpass_filter_width=64,
                    rolloff=0.99,
                    resampling_method="sinc_interp_kaiser",
                    beta=14.769656459379492,
                )
                audio_16k = resampler_16k(audio_tensor).squeeze(0).numpy()
            else:
                audio_16k = audio_f32

            max_val = np.abs(audio_16k).max()
            if max_val > 0.001:
                audio_16k = audio_16k / max_val * 0.95

            # 2. Extract HuBERT Layer 12 features
            wav_tensor = torch.from_numpy(audio_16k).float().unsqueeze(0).to(self.device)
            with torch.no_grad():
                feats_raw = self.hubert.extract_features(wav_tensor, padding_mask=None, output_layer=12)[0]

            feats_np = feats_raw.squeeze(0).cpu().numpy()

            # FAISS Index Retrieval
            if self.faiss_index is not None and self.index_rate > 0.0:
                score, idxs = self.faiss_index.search(feats_np.astype(np.float32), k=8)
                weight = np.square(1.0 / np.maximum(score, 1e-4))
                weight /= weight.sum(axis=1, keepdims=True)
                retrieved = np.sum(self.faiss_index.reconstruct_n(0, self.faiss_index.ntotal)[idxs] * weight[:, :, None], axis=1)
                feats_np = (1 - self.index_rate) * feats_np + self.index_rate * retrieved

            feats_t = torch.from_numpy(feats_np).unsqueeze(0).to(self.device)
            feats_up = feats_t.repeat_interleave(2, dim=1)

            # 3. Extract F0 via Praat Autocorrelation
            sound = parselmouth.Sound(audio_16k.astype(np.float64), sampling_frequency=16000)
            pitch_obj = sound.to_pitch_ac(
                time_step=0.010,
                pitch_floor=160.0,
                pitch_ceiling=1100.0,
                very_accurate=True,
            )
            f0 = pitch_obj.selected_array["frequency"].copy()

            # Continuous pitch interpolation across unvoiced gaps
            f0_cont = f0.copy()
            uv = f0_cont == 0
            if np.any(uv) and np.any(~uv):
                f0_cont[uv] = np.interp(np.where(uv)[0], np.where(~uv)[0], f0_cont[~uv])

            # Apply pitch shift (+6 semitones)
            if self.f0_up_key != 0:
                f0_cont = f0_cont * (2 ** (self.f0_up_key / 12.0))
                f0[f0 > 0] = f0[f0 > 0] * (2 ** (self.f0_up_key / 12.0))

            # 3-frame median smoothing
            if len(f0_cont) > 3:
                for i in range(1, len(f0_cont) - 1):
                    f0_cont[i] = np.median([f0_cont[i - 1], f0_cont[i], f0_cont[i + 1]])

            # Coarse pitch bins
            f0_min = 50.0
            f0_max = 1100.0
            f0_mel_min = 1127 * np.log(1 + f0_min / 700)
            f0_mel_max = 1127 * np.log(1 + f0_max / 700)

            f0_mel = 1127 * np.log(1 + f0 / 700)
            f0_mel[f0_mel > 0] = (f0_mel[f0_mel > 0] - f0_mel_min) * 254 / (f0_mel_max - f0_mel_min) + 1
            f0_mel[f0_mel <= 1] = 1
            f0_mel[f0_mel > 255] = 255
            f0_coarse = np.rint(f0_mel).astype(np.int64)

            # 4. Neural Vocoder Synthesis (40kHz)
            target_len = min(feats_up.shape[1], len(f0_coarse))
            curr_feats = feats_up[:, :target_len, :]
            p_coarse = torch.from_numpy(f0_coarse[:target_len]).unsqueeze(0).to(self.device)
            p_cont = torch.from_numpy(f0_cont[:target_len]).unsqueeze(0).to(self.device)
            lengths = torch.LongTensor([target_len]).to(self.device)
            sid = torch.LongTensor([0]).to(self.device)

            with torch.no_grad():
                out_audio = self.net_g.infer(curr_feats, lengths, p_coarse, p_cont, sid)[0][0, 0].cpu().numpy()

            # 5. Resample from 40kHz to out_sr (24kHz) for playback ring
            if self.rvc_sr != out_sr:
                out_tensor = torch.from_numpy(out_audio).float().unsqueeze(0)
                resampler_out = torchaudio.transforms.Resample(
                    orig_freq=self.rvc_sr,
                    new_freq=out_sr,
                    lowpass_filter_width=64,
                    rolloff=0.99,
                    resampling_method="sinc_interp_kaiser",
                )
                out_audio = resampler_out(out_tensor).squeeze(0).numpy()

            return out_audio.astype(np.float32)
        except Exception as exc:  # noqa: BLE001
            logger.error("asuka_rvc_conversion_failed", error=str(exc))
            return audio_f32


class SubprocessAsukaRVCConverter:
    """
    Subprocess bridge to .venv-voice (Python 3.10) for RVC voice conversion.
    Allows Python 3.12 Lucca runtime to access GPU-accelerated PyTorch CUDA 12.8
    and fairseq HuBERT without environment dependency collisions.
    """

    def __init__(self, python_exe: Path | None = None) -> None:
        self.python_exe = python_exe or (REPO_ROOT / ".venv-voice" / "Scripts" / "python.exe")
        self.proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._ensure_worker()
        atexit.register(self.close)

    def _ensure_worker(self) -> bool:
        if self.proc is not None and self.proc.poll() is None:
            return True

        if not self.python_exe.exists():
            logger.warning("asuka_voice_venv_missing", path=str(self.python_exe))
            return False

        try:
            log_dir = REPO_ROOT / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            self._stderr_file = open(log_dir / "rvc_worker.log", "a", encoding="utf-8")
            self.proc = subprocess.Popen(
                [str(self.python_exe), "-u", "src/lucca/speech/rvc/worker.py"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr_file,
                cwd=str(REPO_ROOT),
            )
            assert self.proc.stdout is not None
            ready = self.proc.stdout.readline()
            if b"READY" not in ready:
                logger.error("asuka_worker_startup_failed", ready=str(ready))
                return False
            logger.info("asuka_subprocess_worker_connected", pid=self.proc.pid)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("asuka_worker_spawn_error", error=str(exc))
            return False

    def convert(
        self,
        audio_f32: np.ndarray,
        orig_sr: int = 24000,
        out_sr: int = 24000,
    ) -> np.ndarray:
        with self._lock:
            if not self._ensure_worker() or self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
                return audio_f32

            try:
                raw_bytes = audio_f32.astype(np.float32).tobytes()
                header = struct.pack("<III", len(raw_bytes), int(orig_sr), int(out_sr))
                self.proc.stdin.write(header + raw_bytes)
                self.proc.stdin.flush()

                res_hdr = self.proc.stdout.read(4)
                if not res_hdr or len(res_hdr) < 4:
                    logger.error("asuka_worker_eof")
                    self.proc = None
                    return audio_f32

                (out_len,) = struct.unpack("<I", res_hdr)
                chunks: list[bytes] = []
                bytes_read = 0
                while bytes_read < out_len:
                    chunk = self.proc.stdout.read(min(out_len - bytes_read, 65536))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    bytes_read += len(chunk)

                res_bytes = b"".join(chunks)
                if len(res_bytes) != out_len:
                    logger.error("asuka_worker_truncated_read", expected=out_len, got=len(res_bytes))
                    return audio_f32

                return np.frombuffer(res_bytes, dtype=np.float32)
            except Exception as exc:  # noqa: BLE001
                logger.error("asuka_worker_convert_exception", error=str(exc))
                if self.proc is not None:
                    try:
                        self.proc.terminate()
                    except Exception as p_exc:  # noqa: BLE001
                        logger.debug("asuka_worker_term_failed", error=str(p_exc))
                    self.proc = None
                return audio_f32

    def close(self) -> None:
        with self._lock:
            if self.proc is not None:
                try:
                    if self.proc.stdin:
                        self.proc.stdin.close()
                    self.proc.terminate()
                    self.proc.wait(timeout=1.0)
                except Exception as w_exc:  # noqa: BLE001
                    logger.debug("asuka_worker_wait_failed", error=str(w_exc))
                self.proc = None
            if hasattr(self, "_stderr_file") and self._stderr_file:
                try:
                    self._stderr_file.close()
                except Exception as f_exc:  # noqa: BLE001
                    logger.debug("asuka_worker_stderr_close_failed", error=str(f_exc))


_GLOBAL_ASUKA_CONVERTER: AsukaRVCConverter | SubprocessAsukaRVCConverter | None = None


def get_asuka_converter() -> AsukaRVCConverter | SubprocessAsukaRVCConverter:
    global _GLOBAL_ASUKA_CONVERTER
    if _GLOBAL_ASUKA_CONVERTER is None:
        if _LOCAL_GPU_RVC_CAPABLE:
            _GLOBAL_ASUKA_CONVERTER = AsukaRVCConverter()
        else:
            _GLOBAL_ASUKA_CONVERTER = SubprocessAsukaRVCConverter()
    return _GLOBAL_ASUKA_CONVERTER
