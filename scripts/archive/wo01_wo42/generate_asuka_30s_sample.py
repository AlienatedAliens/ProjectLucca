"""
Project Lucca — Generate ~30-Second Asuka Langley Soryu Voice Sample
Kokoro-82M (base prosody) + Asuka RVC v2 (character timbre on RTX 5080)
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

DIALOGUE_LINES = [
    "Anta baka?! What took you so long to figure this out?",
    "Honestly, if I didn't step in, you'd probably be sitting here staring at that terminal until tomorrow morning!",
    "Look, I'm only going to say this once, so listen up.",
    "The neural audio pipeline is running, the RTX fifty-eighty is locked and loaded, and the conversion is completely under control.",
    "Don't go getting complacent on me now, idiot!",
]


def generate_full_kokoro_dialogue(lines: list[str], voice: str = "af_sky") -> tuple[np.ndarray, int]:
    """Generates contiguous audio across dialogue lines with natural pauses."""
    print(f"\n[1/3] Generating Kokoro base audio across {len(lines)} dialogue segments (voice={voice})...")
    kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    combined_audio = []
    sr = 24000
    pause_silence = np.zeros(int(sr * 0.25), dtype=np.float32)  # 250ms inter-sentence pause

    t0 = time.perf_counter()
    for idx, line in enumerate(lines, 1):
        print(f"      [{idx}/{len(lines)}] Synthesizing: \"{line[:50]}...\"")
        seg, seg_sr = kokoro.create(line, voice=voice, speed=1.05, lang="en-us")
        sr = seg_sr
        combined_audio.append(seg)
        if idx < len(lines):
            combined_audio.append(pause_silence)

    full_audio = np.concatenate(combined_audio)
    duration_s = len(full_audio) / sr
    elapsed = time.perf_counter() - t0
    print(f"      Total Kokoro Base Audio: {duration_s:.1f}s ({len(full_audio):,} samples) generated in {elapsed:.2f}s")
    return full_audio, sr


def extract_f0_pyworld(audio_16k: np.ndarray, sr: int = 16000, f0_up_key: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Extracts F0 and quantizes to 256 pitch bins using PyWorld harvest."""
    frame_period = 10.0
    f0, t = pyworld.harvest(
        audio_16k.astype(np.double),
        sr,
        f0_floor=50.0,
        f0_ceil=1100.0,
        frame_period=frame_period,
    )
    f0 = pyworld.stonemask(audio_16k.astype(np.double), f0, t, sr)

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


def convert_rvc(
    audio: np.ndarray,
    orig_sr: int,
    device: str = "cuda:0",
    index_rate: float = 0.75,
    pitch_shift: int = 0,
) -> tuple[np.ndarray, int]:
    """Runs RVC v2 inference on input audio to convert timbre to Asuka."""
    print(f"\n[2/3] Processing audio through Asuka RVC pipeline on {device}...")
    t0 = time.perf_counter()

    # Resample input audio to 16kHz for HuBERT
    if orig_sr != 16000:
        num_samples_16k = int(len(audio) * 16000 / orig_sr)
        audio_16k = scipy.signal.resample(audio, num_samples_16k)
    else:
        audio_16k = audio

    max_val = np.abs(audio_16k).max()
    if max_val > 0.001:
        audio_16k = audio_16k / max_val * 0.95

    # 1. Load HuBERT
    print("      Extracting speech representations via HuBERT Layer 12...")
    hubert_models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task([str(HUBERT_PATH)])
    hubert = hubert_models[0].to(device).eval()

    wav_tensor = torch.from_numpy(audio_16k).float().unsqueeze(0).to(device)
    with torch.no_grad():
        feats = hubert.extract_features(wav_tensor, padding_mask=None, output_layer=12)[0]
    feats_np = feats.squeeze(0).cpu().numpy()

    # 2. FAISS feature retrieval
    if ASUKA_INDEX.exists() and index_rate > 0:
        print(f"      Matching vocal characteristics against Asuka FAISS index (index_rate={index_rate})...")
        index = faiss.read_index(str(ASUKA_INDEX))
        score, idxs = index.search(feats_np.astype(np.float32), k=8)
        weight = np.square(1.0 / np.maximum(score, 1e-4))
        weight /= weight.sum(axis=1, keepdims=True)
        retrieved_feats = np.sum(index.reconstruct_n(0, index.ntotal)[idxs] * weight[:, :, None], axis=1)
        feats_np = (1 - index_rate) * feats_np + index_rate * retrieved_feats
        feats = torch.from_numpy(feats_np).unsqueeze(0).to(device)

    feats_up = F.interpolate(feats.permute(0, 2, 1), scale_factor=2, mode="linear").permute(0, 2, 1)

    # 3. F0 pitch contour
    print("      Tracking pitch trajectory via PyWorld harvest...")
    f0_continuous, f0_coarse = extract_f0_pyworld(audio_16k, sr=16000, f0_up_key=pitch_shift)

    target_len = min(feats_up.shape[1], len(f0_coarse))
    feats_up = feats_up[:, :target_len, :]
    f0_coarse = torch.from_numpy(f0_coarse[:target_len]).unsqueeze(0).to(device)
    f0_continuous = torch.from_numpy(f0_continuous[:target_len]).unsqueeze(0).to(device)
    lengths = torch.LongTensor([target_len]).to(device)
    sid = torch.LongTensor([0]).to(device)

    # 4. Neural Vocoder Synthesis
    cpt = torch.load(str(ASUKA_PTH), map_location="cpu", weights_only=False)
    target_sr = cpt.get("sr", 40000)
    if isinstance(target_sr, str) and target_sr.endswith("k"):
        target_sr = int(target_sr[:-1]) * 1000

    print(f"      Synthesizing Asuka 40kHz HiFi-GAN waveform on {device}...")
    net_g = SynthesizerTrnMs768NSFsid(*cpt["config"], is_half=False).to(device)
    net_g.load_state_dict(cpt["weight"], strict=False)
    net_g.eval()

    with torch.no_grad():
        out_audio = net_g.infer(feats_up, lengths, f0_coarse, f0_continuous, sid)[0][0, 0].cpu().numpy()

    elapsed = time.perf_counter() - t0
    final_duration = len(out_audio) / target_sr
    print(f"      RVC Conversion completed in {elapsed:.2f}s | Output Duration: {final_duration:.1f}s")
    return out_audio, target_sr


def main():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"

    print("=" * 65)
    print("  PROJECT LUCCA — GENERATING 30-SECOND ASUKA VOICE SAMPLE")
    print(f"  Target Device: {device} (RTX 5080 Laptop GPU)")
    print("=" * 65)

    # Step 1: Generate Kokoro multi-segment audio
    source_audio, source_sr = generate_full_kokoro_dialogue(DIALOGUE_LINES, voice="af_sky")
    kokoro_path = OUTPUT_DIR / "kokoro_base_30s.wav"
    sf.write(str(kokoro_path), source_audio, source_sr)
    print(f"      Saved base audio to: {kokoro_path}")

    # Step 2: RVC Conversion
    asuka_audio, asuka_sr = convert_rvc(source_audio, source_sr, device=device, index_rate=0.75)
    asuka_path = OUTPUT_DIR / "asuka_long_sample_30s.wav"
    sf.write(str(asuka_path), asuka_audio, asuka_sr)

    print("\n" + "=" * 65)
    print(f"[3/3] MASTER AUDIO READY: {asuka_path}")
    print(f"      Duration: {len(asuka_audio) / asuka_sr:.1f} seconds")
    print(f"      Sampling Rate: {asuka_sr} Hz")
    print(f"      File Size: {asuka_path.stat().st_size:,} bytes")
    print("=" * 65)


if __name__ == "__main__":
    main()
