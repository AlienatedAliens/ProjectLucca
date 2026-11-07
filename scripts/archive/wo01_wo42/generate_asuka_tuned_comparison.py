"""
Project Lucca — Asuka Voice Pitch Calibration & Comparison
Applies:
  1. Female Pitch Floor Clamp (160 Hz minimum, eliminates masculine octave errors)
  2. Anime Heroine Formant Blend (70% af_sky + 30% jf_alpha)
  3. Pitch Shifts (+6, +8, and +10 semitones) to match Tiffany Grant's natural vocal register
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
import torch.nn.functional as F

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

# 2 Key lines for comparison
TEST_LINES = [
    "Anta baka?! What took you so long to figure this out?",
    "Honestly, if I didn't step in, you'd probably be sitting here staring at that terminal until tomorrow morning!",
]


def generate_blended_kokoro(lines: list[str]) -> tuple[np.ndarray, int]:
    """Generates base audio using anime heroine blend (70% af_sky + 30% jf_alpha)."""
    print("\n[1/3] Generating bright anime heroine base audio with Kokoro...")
    kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    v_sky = kokoro.get_voice_style("af_sky")
    v_alpha = kokoro.get_voice_style("jf_alpha")
    # Truncate to matching length if needed
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
    print(f"      Kokoro base generated: {len(audio)/sr:.1f}s at {sr} Hz")
    return audio, sr


def extract_f0_female(audio_16k: np.ndarray, sr: int = 16000, f0_up_key: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """Extracts F0 with strict female pitch floor (160 Hz) and semitone shift."""
    frame_period = 10.0
    f0, t = pyworld.harvest(
        audio_16k.astype(np.double),
        sr,
        f0_floor=160.0,   # CLAMPED: 160 Hz minimum completely prevents male octave errors
        f0_ceil=1100.0,
        frame_period=frame_period,
    )
    f0 = pyworld.stonemask(audio_16k.astype(np.double), f0, t, sr)

    # Apply semitone pitch shift
    if f0_up_key != 0:
        f0 = f0 * (2 ** (f0_up_key / 12.0))

    f0_mel = 1127 * np.log(1 + f0 / 700)
    f0_mel[f0 <= 0] = 0
    f0_mel_min = 1127 * np.log(1 + 50.0 / 700)
    f0_mel_max = 1127 * np.log(1 + 1100.0 / 700)

    f0_coarse = (f0_mel - f0_mel_min) * 254 / (f0_mel_max - f0_mel_min) + 1
    f0_coarse[f0 <= 0] = 1
    f0_coarse[f0_coarse > 255] = 255
    f0_coarse = np.clip(np.round(f0_coarse), 1, 255).astype(np.int64)

    return f0.astype(np.float32), f0_coarse


def run_conversion_sweep():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print("=" * 65)
    print("  PROJECT LUCCA — ASUKA PITCH CALIBRATION SWEEP")
    print(f"  Device: {device}")
    print("=" * 65)

    # 1. Generate Kokoro Base
    source_audio, source_sr = generate_blended_kokoro(TEST_LINES)
    kokoro_out = OUTPUT_DIR / "kokoro_blended_base.wav"
    sf.write(str(kokoro_out), source_audio, source_sr)

    # Resample to 16kHz for HuBERT
    num_samples_16k = int(len(source_audio) * 16000 / source_sr)
    audio_16k = scipy.signal.resample(source_audio, num_samples_16k)
    max_val = np.abs(audio_16k).max()
    if max_val > 0.001:
        audio_16k = audio_16k / max_val * 0.95

    # 2. Extract HuBERT features
    print("\n[2/3] Extracting HuBERT features on GPU...")
    hubert_models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task([str(HUBERT_PATH)])
    hubert = hubert_models[0].to(device).eval()

    wav_tensor = torch.from_numpy(audio_16k).float().unsqueeze(0).to(device)
    with torch.no_grad():
        feats = hubert.extract_features(wav_tensor, padding_mask=None, output_layer=12)[0]
    feats_np = feats.squeeze(0).cpu().numpy()

    # FAISS Retrieval (0.65 blend rate for clean natural tone)
    if ASUKA_INDEX.exists():
        print("      Blending timbre features via Asuka FAISS index (rate=0.65)...")
        index = faiss.read_index(str(ASUKA_INDEX))
        score, idxs = index.search(feats_np.astype(np.float32), k=8)
        weight = np.square(1.0 / np.maximum(score, 1e-4))
        weight /= weight.sum(axis=1, keepdims=True)
        retrieved_feats = np.sum(index.reconstruct_n(0, index.ntotal)[idxs] * weight[:, :, None], axis=1)
        feats_np = 0.35 * feats_np + 0.65 * retrieved_feats
        feats = torch.from_numpy(feats_np).unsqueeze(0).to(device)

    feats_up = F.interpolate(feats.permute(0, 2, 1), scale_factor=2, mode="linear").permute(0, 2, 1)

    # 3. Load Asuka Model
    cpt = torch.load(str(ASUKA_PTH), map_location="cpu", weights_only=False)
    target_sr = 40000
    net_g = SynthesizerTrnMs768NSFsid(*cpt["config"], is_half=False).to(device)
    net_g.load_state_dict(cpt["weight"], strict=False)
    net_g.eval()

    # 4. Render 3 pitch variations: +6, +8, and +10 semitones
    shifts = [6, 8, 10]
    rendered_files = []

    print("\n[3/3] Rendering pitch calibration variants (+6, +8, +10 semitones)...")
    for shift in shifts:
        t0 = time.perf_counter()
        f0_cont, f0_coarse = extract_f0_female(audio_16k, sr=16000, f0_up_key=shift)

        target_len = min(feats_up.shape[1], len(f0_coarse))
        curr_feats = feats_up[:, :target_len, :]
        p_coarse = torch.from_numpy(f0_coarse[:target_len]).unsqueeze(0).to(device)
        p_cont = torch.from_numpy(f0_cont[:target_len]).unsqueeze(0).to(device)
        lengths = torch.LongTensor([target_len]).to(device)
        sid = torch.LongTensor([0]).to(device)

        with torch.no_grad():
            out_audio = net_g.infer(curr_feats, lengths, p_coarse, p_cont, sid)[0][0, 0].cpu().numpy()

        elapsed = time.perf_counter() - t0
        out_filename = OUTPUT_DIR / f"asuka_pitch_plus_{shift}st.wav"
        sf.write(str(out_filename), out_audio, target_sr)
        rendered_files.append((shift, out_filename, len(out_audio)/target_sr, elapsed))
        print(f"      Rendered +{shift} semitones -> {out_filename.name} ({len(out_audio)/target_sr:.1f}s in {elapsed:.2f}s)")

    print("\n" + "=" * 65)
    print("CALIBRATION SWEEP COMPLETE!")
    for shift, path, dur, el in rendered_files:
        print(f"  Shift +{shift:02d} st: {path}")
    print("=" * 65)


if __name__ == "__main__":
    run_conversion_sweep()
