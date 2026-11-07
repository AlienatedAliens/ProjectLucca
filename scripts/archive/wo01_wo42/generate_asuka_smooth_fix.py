"""
Project Lucca — Asuka Voice Warping Elimination & Smoothing
Fixes:
  1. Replaces linear interpolation with discrete frame repeat (repeat_interleave(2)),
     eliminating artificial "ghost phoneme" blending.
  2. Suppresses unvoiced pitch bleed on fricatives ("s", "t", "k").
  3. Tests Index Rate 0.30 (subtle natural anchor) vs Index Rate 0.0 (pure smooth neural synthesis).
"""

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

# PyTorch 2.6+ compatibility for legacy fairseq checkpoints
_orig_load = torch.load
torch.load = lambda *args, **kwargs: _orig_load(*args, **{**kwargs, "weights_only": False})

import fairseq
from kokoro_onnx import Kokoro
from lucca.speech.rvc.models import SynthesizerTrnMs768NSFsid

MODELS_DIR = Path(r"C:\ProjectLucca\models\tts")
KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"
RVC_DIR = MODELS_DIR / "rvc"
HUBERT_PATH = RVC_DIR / "hubert_base.pt"
ASUKA_PTH = RVC_DIR / "asuka" / "asuka.pth"
ASUKA_INDEX = RVC_DIR / "asuka" / "added_IVF470_Flat_nprobe_1_asuka_v2.index"
OUTPUT_DIR = REPO_ROOT / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEST_LINES = [
    "Anta baka?! What took you so long to figure this out?",
    "Honestly, if I didn't step in, you'd probably be sitting here staring at that terminal until tomorrow morning!",
]


def generate_blended_kokoro(lines: list[str]) -> tuple[np.ndarray, int]:
    print("\n[1/3] Synthesizing Kokoro base audio...")
    kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    v_sky = kokoro.get_voice_style("af_sky")
    v_alpha = kokoro.get_voice_style("jf_alpha")
    min_len = min(len(v_sky), len(v_alpha))
    blended_voice = 0.70 * v_sky[:min_len] + 0.30 * v_alpha[:min_len]

    sr = 24000
    combined = []
    pause = np.zeros(int(sr * 0.25), dtype=np.float32)

    for idx, line in enumerate(lines):
        seg, _ = kokoro.create(line, voice=blended_voice, speed=1.05, lang="en-us")
        combined.append(seg)
        if idx < len(lines) - 1:
            combined.append(pause)

    audio = np.concatenate(combined)
    return audio, sr


def extract_f0_clean(audio_16k: np.ndarray, sr: int = 16000, f0_up_key: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Clean F0 tracking with strictly zeroed unvoiced frames and pitch shift."""
    frame_period = 10.0
    f0, t = pyworld.harvest(
        audio_16k.astype(np.double),
        sr,
        f0_floor=160.0,
        f0_ceil=1100.0,
        frame_period=frame_period,
    )
    f0 = pyworld.stonemask(audio_16k.astype(np.double), f0, t, sr)

    # Shift pitch
    if f0_up_key != 0:
        f0 = f0 * (2 ** (f0_up_key / 12.0))

    # Coarse pitch bins
    f0_mel = 1127 * np.log(1 + f0 / 700)
    f0_mel[f0 <= 0] = 0
    f0_mel_min = 1127 * np.log(1 + 50.0 / 700)
    f0_mel_max = 1127 * np.log(1 + 1100.0 / 700)

    f0_coarse = (f0_mel - f0_mel_min) * 254 / (f0_mel_max - f0_mel_min) + 1
    f0_coarse[f0 <= 0] = 1
    f0_coarse[f0_coarse > 255] = 255
    f0_coarse = np.clip(np.round(f0_coarse), 1, 255).astype(np.int64)

    return f0.astype(np.float32), f0_coarse


def run_smooth_render():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print("=" * 65)
    print("  PROJECT LUCCA — ASUKA VOICE SMOOTHING & ANTI-WARP RENDER")
    print(f"  Device: {device} | Pitch Shift: +8 semitones")
    print("=" * 65)

    source_audio, source_sr = generate_blended_kokoro(TEST_LINES)
    num_samples_16k = int(len(source_audio) * 16000 / source_sr)
    audio_16k = scipy.signal.resample(source_audio, num_samples_16k)
    max_val = np.abs(audio_16k).max()
    if max_val > 0.001:
        audio_16k = audio_16k / max_val * 0.95

    # 1. Load HuBERT and extract features
    print("\n[2/3] Extracting HuBERT Layer 12 features...")
    hubert_models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task([str(HUBERT_PATH)])
    hubert = hubert_models[0].to(device).eval()

    wav_tensor = torch.from_numpy(audio_16k).float().unsqueeze(0).to(device)
    with torch.no_grad():
        feats_raw = hubert.extract_features(wav_tensor, padding_mask=None, output_layer=12)[0]
    raw_feats_np = feats_raw.squeeze(0).cpu().numpy()

    # Load Synthesizer
    cpt = torch.load(str(ASUKA_PTH), map_location="cpu", weights_only=False)
    target_sr = 40000
    net_g = SynthesizerTrnMs768NSFsid(*cpt["config"], is_half=False).to(device)
    net_g.load_state_dict(cpt["weight"], strict=False)
    net_g.eval()

    # Load FAISS Index
    faiss_index = faiss.read_index(str(ASUKA_INDEX)) if ASUKA_INDEX.exists() else None

    # Track F0 pitch
    f0_cont, f0_coarse = extract_f0_clean(audio_16k, sr=16000, f0_up_key=8)

    # 2. Render configurations
    configs = [
        ("pure_neural_index_00", 0.0),
        ("smooth_subtle_index_30", 0.30),
    ]

    print("\n[3/3] Rendering smoothed anti-warp audio...")
    for label, rate in configs:
        t0 = time.perf_counter()
        feats_np = raw_feats_np.copy()

        # FAISS index retrieval with gentle blending
        if faiss_index is not None and rate > 0.0:
            score, idxs = faiss_index.search(feats_np.astype(np.float32), k=8)
            weight = np.square(1.0 / np.maximum(score, 1e-4))
            weight /= weight.sum(axis=1, keepdims=True)
            retrieved = np.sum(faiss_index.reconstruct_n(0, faiss_index.ntotal)[idxs] * weight[:, :, None], axis=1)
            feats_np = (1 - rate) * feats_np + rate * retrieved

        feats_t = torch.from_numpy(feats_np).unsqueeze(0).to(device)

        # CRITICAL FIX: repeat_interleave(2) instead of linear interpolation
        # Preserves discrete phoneme identities without generating warped intermediate vectors
        feats_up = feats_t.repeat_interleave(2, dim=1)

        target_len = min(feats_up.shape[1], len(f0_coarse))
        curr_feats = feats_up[:, :target_len, :]
        p_coarse = torch.from_numpy(f0_coarse[:target_len]).unsqueeze(0).to(device)
        p_cont = torch.from_numpy(f0_cont[:target_len]).unsqueeze(0).to(device)
        lengths = torch.LongTensor([target_len]).to(device)
        sid = torch.LongTensor([0]).to(device)

        with torch.no_grad():
            out_audio = net_g.infer(curr_feats, lengths, p_coarse, p_cont, sid)[0][0, 0].cpu().numpy()

        elapsed = time.perf_counter() - t0
        out_path = OUTPUT_DIR / f"asuka_{label}.wav"
        sf.write(str(out_path), out_audio, target_sr)
        print(f"      Rendered [{label}] (index_rate={rate}) -> {out_path.name} ({len(out_audio)/target_sr:.1f}s in {elapsed:.2f}s)")

    print("\n" + "=" * 65)
    print("SMOOTHING RENDER COMPLETE!")
    print(f"  1. Pure Neural (Zero warping): {OUTPUT_DIR / 'asuka_pure_neural_index_00.wav'}")
    print(f"  2. Subtle Anchor (Index 0.30): {OUTPUT_DIR / 'asuka_smooth_subtle_index_30.wav'}")
    print("=" * 65)


if __name__ == "__main__":
    run_smooth_render()
