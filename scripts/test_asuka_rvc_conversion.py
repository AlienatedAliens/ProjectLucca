"""
Project Lucca — Kokoro + Asuka RVC Two-Stage Voice Conversion Pipeline
Spec 07 §5, ADR-008

Demonstrates:
  Step 1: Text-to-Speech via Kokoro-82M ONNX (fast, high prosody anime cadence).
  Step 2: Timbre conversion to Asuka Langley Soryu via RVC v2 (asuka.pth + FAISS index) on GPU.
"""

import math
import os
import sys
import time
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import faiss
import numpy as np
import pyworld
import scipy.signal
import soundfile as sf
import torch
import torch.nn.functional as F

# PyTorch 2.6+ compatibility for legacy fairseq checkpoints
_orig_load = torch.load
torch.load = lambda *args, **kwargs: _orig_load(*args, **{**kwargs, "weights_only": False})

import fairseq
from kokoro_onnx import Kokoro
from lucca.speech.rvc.models import SynthesizerTrnMs768NSFsid

# Paths
MODELS_DIR = Path(r"C:\ProjectLucca\models\tts")
KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"
RVC_DIR = MODELS_DIR / "rvc"
HUBERT_PATH = RVC_DIR / "hubert_base.pt"
ASUKA_PTH = RVC_DIR / "asuka" / "asuka.pth"
ASUKA_INDEX = RVC_DIR / "asuka" / "added_IVF470_Flat_nprobe_1_asuka_v2.index"
OUTPUT_DIR = REPO_ROOT / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_kokoro_audio(text: str, voice: str = "af_sky") -> tuple[np.ndarray, int]:
    """Generates 24kHz audio from text using Kokoro-82M ONNX."""
    print(f"\n[1/3] Generating Kokoro base audio for: '{text}' (voice={voice})...")
    t0 = time.perf_counter()
    kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    samples, sr = kokoro.create(text, voice=voice, speed=1.05, lang="en-us")
    elapsed = time.perf_counter() - t0
    print(f"      Kokoro finished in {elapsed:.2f}s | {len(samples)} samples at {sr} Hz")
    return samples, sr


def extract_f0_pyworld(audio_16k: np.ndarray, sr: int = 16000, f0_up_key: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Extracts F0 and quantizes to 256 pitch bins using PyWorld harvest."""
    frame_period = 10.0  # 10ms hop
    f0, t = pyworld.harvest(
        audio_16k.astype(np.double),
        sr,
        f0_floor=50.0,
        f0_ceil=1100.0,
        frame_period=frame_period,
    )
    f0 = pyworld.stonemask(audio_16k.astype(np.double), f0, t, sr)

    # Pitch key shift (semitones)
    if f0_up_key != 0:
        f0 = f0 * (2 ** (f0_up_key / 12.0))

    # Quantize to 1-255 coarse pitch bins for NSF embedding
    f0_mel = 1127 * np.log(1 + f0 / 700)
    f0_mel[f0 <= 0] = 0
    f0_mel_min = 1127 * np.log(1 + 50.0 / 700)
    f0_mel_max = 1127 * np.log(1 + 1100.0 / 700)

    f0_coarse = (f0_mel - f0_mel_min) * 254 / (f0_mel_max - f0_mel_min) + 1
    f0_coarse[f0 <= 0] = 1
    f0_coarse[f0_coarse > 255] = 255
    f0_coarse = np.clip(np.round(f0_coarse), 1, 255).astype(np.int64)

    return f0.astype(np.float32), f0_coarse


def convert_rvc(
    audio: np.ndarray,
    orig_sr: int,
    device: str = "cuda:0",
    index_rate: float = 0.75,
    pitch_shift: int = 0,
) -> tuple[np.ndarray, int]:
    """Runs RVC v2 inference on input audio to convert timbre to Asuka."""
    print(f"\n[2/3] Loading HuBERT and Asuka RVC models onto {device}...")
    t0 = time.perf_counter()

    # Resample input audio to 16kHz for HuBERT
    if orig_sr != 16000:
        num_samples_16k = int(len(audio) * 16000 / orig_sr)
        audio_16k = scipy.signal.resample(audio, num_samples_16k)
    else:
        audio_16k = audio

    # Normalize audio
    max_val = np.abs(audio_16k).max()
    if max_val > 0.001:
        audio_16k = audio_16k / max_val * 0.95

    # 1. Load HuBERT
    hubert_models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task([str(HUBERT_PATH)])
    hubert = hubert_models[0].to(device).eval()

    # 2. Extract HuBERT features (Layer 12, 768-D)
    wav_tensor = torch.from_numpy(audio_16k).float().unsqueeze(0).to(device)
    with torch.no_grad():
        feats = hubert.extract_features(wav_tensor, padding_mask=None, output_layer=12)[0]
    # feats shape: (1, T_hubert, 768)
    feats_np = feats.squeeze(0).cpu().numpy()

    # 3. FAISS feature retrieval if index available
    if ASUKA_INDEX.exists() and index_rate > 0:
        print(f"      Retrieving timbre vectors from FAISS index (rate={index_rate})...")
        index = faiss.read_index(str(ASUKA_INDEX))
        score, idxs = index.search(feats_np.astype(np.float32), k=8)
        # Weighted nearest neighbor replacement
        weight = np.square(1.0 / np.maximum(score, 1e-4))
        weight /= weight.sum(axis=1, keepdims=True)
        retrieved_feats = np.sum(index.reconstruct_n(0, index.ntotal)[idxs] * weight[:, :, None], axis=1)
        feats_np = (1 - index_rate) * feats_np + index_rate * retrieved_feats
        feats = torch.from_numpy(feats_np).unsqueeze(0).to(device)

    # Interpolate HuBERT features to match pitch resolution (2x upsample: 50Hz -> 100Hz)
    feats_up = F.interpolate(feats.permute(0, 2, 1), scale_factor=2, mode="linear").permute(0, 2, 1)

    # 4. Extract F0
    print("      Extracting F0 pitch contour via PyWorld harvest...")
    f0_continuous, f0_coarse = extract_f0_pyworld(audio_16k, sr=16000, f0_up_key=pitch_shift)

    # Align lengths
    target_len = min(feats_up.shape[1], len(f0_coarse))
    feats_up = feats_up[:, :target_len, :]
    f0_coarse = torch.from_numpy(f0_coarse[:target_len]).unsqueeze(0).to(device)
    f0_continuous = torch.from_numpy(f0_continuous[:target_len]).unsqueeze(0).to(device)
    lengths = torch.LongTensor([target_len]).to(device)
    sid = torch.LongTensor([0]).to(device)

    # 5. Load Asuka Synthesizer
    cpt = torch.load(str(ASUKA_PTH), map_location="cpu", weights_only=False)
    target_sr = cpt.get("sr", 40000)
    if isinstance(target_sr, str) and target_sr.endswith("k"):
        target_sr = int(target_sr[:-1]) * 1000

    net_g = SynthesizerTrnMs768NSFsid(*cpt["config"], is_half=False).to(device)
    net_g.load_state_dict(cpt["weight"], strict=False)
    net_g.eval()

    # 6. Synthesize Asuka audio
    print(f"      Synthesizing Asuka voice on {device} (target_sr={target_sr} Hz)...")
    with torch.no_grad():
        out_audio = net_g.infer(feats_up, lengths, f0_coarse, f0_continuous, sid)[0][0, 0].cpu().numpy()

    elapsed = time.perf_counter() - t0
    print(f"      RVC conversion complete in {elapsed:.2f}s | {len(out_audio)} samples at {target_sr} Hz")
    return out_audio, target_sr


def main():
    test_line = "Anta baka?! What took you so long to figure this out?"
    device = "cuda:0" if torch.cuda.is_available() else "cpu"

    print("=" * 65)
    print("  PROJECT LUCCA — KOKORO + ASUKA RVC CONVERSION TEST")
    print(f"  Target Line: \"{test_line}\"")
    print(f"  Inference Device: {device}")
    print("=" * 65)

    # Step 1: Kokoro TTS
    source_audio, source_sr = generate_kokoro_audio(test_line, voice="af_sky")
    kokoro_out_path = OUTPUT_DIR / "test_kokoro_base.wav"
    sf.write(str(kokoro_out_path), source_audio, source_sr)
    print(f"      Saved base audio: {kokoro_out_path}")

    # Step 2: RVC Asuka Conversion
    asuka_audio, asuka_sr = convert_rvc(source_audio, source_sr, device=device, index_rate=0.75)
    asuka_out_path = OUTPUT_DIR / "asuka_voice_converted.wav"
    sf.write(str(asuka_out_path), asuka_audio, asuka_sr)
    print(f"\n[3/3] SUCCESS! Asuka voice audio saved to: {asuka_out_path}")
    print(f"      File size: {asuka_out_path.stat().st_size:,} bytes")
    print("=" * 65)


if __name__ == "__main__":
    main()
