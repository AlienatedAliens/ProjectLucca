"""
Project Lucca — Studio-Grade Asuka Voice Synthesis (Praat PM + Kaiser Sinc)
Spec 07 §5, ADR-008

Acoustic Pipeline:
  1. Base Audio: Kokoro-82M anime heroine blend (70% af_sky + 30% jf_alpha).
  2. Anti-Aliasing Resampling: torchaudio 64-tap Kaiser-windowed sinc filter (zero Gibbs ringing).
  3. Pitch Tracking: Praat acoustic autocorrelation (parselmouth to_pitch_ac) with 160 Hz floor.
  4. Temporal Quantization: Discrete frame repetition (repeat_interleave(2)) without ghost phonemes.
  5. Neural Vocoder: Asuka v2 SynthesizerTrnMs768NSFsid (40 kHz) on RTX 5080 Laptop GPU.
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
import parselmouth
import soundfile as sf
import torch
import torchaudio

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
    print("\n[1/4] Synthesizing Kokoro base audio...")
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


def resample_kaiser_sinc(audio: np.ndarray, orig_sr: int = 24000, new_sr: int = 16000) -> np.ndarray:
    """High-order Kaiser-windowed sinc filter: eliminates FFT Gibbs ringing."""
    tensor = torch.from_numpy(audio).float().unsqueeze(0)
    resampler = torchaudio.transforms.Resample(
        orig_freq=orig_sr,
        new_freq=new_sr,
        lowpass_filter_width=64,
        rolloff=0.99,
        resampling_method="sinc_interp_kaiser",
        beta=14.769656459379492,  # 100dB stopband attenuation
    )
    resampled = resampler(tensor).squeeze(0).numpy()
    max_val = np.abs(resampled).max()
    if max_val > 0.001:
        resampled = resampled / max_val * 0.95
    return resampled


def extract_f0_praat(audio_16k: np.ndarray, sr: int = 16000, f0_up_key: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """
    Praat acoustic autocorrelation pitch tracking (RVC 'pm' method).
    Completely eliminates sub-band harmonic phase flutter from PyWorld harvest.
    """
    sound = parselmouth.Sound(audio_16k.astype(np.float64), sampling_frequency=sr)
    # 10ms frame period (time_step = 0.010)
    pitch_obj = sound.to_pitch_ac(
        time_step=0.010,
        pitch_floor=160.0,
        pitch_ceiling=1100.0,
        very_accurate=True,
    )
    f0 = pitch_obj.selected_array["frequency"].copy()

    # Continuous F0 interpolation across unvoiced gaps (Official RVC NSF fix)
    # Prevents neural sine generator from shutting off mid-vowel on nasals ("morning", "until") and diphthongs ("out")
    f0_cont = f0.copy()
    uv = f0_cont == 0
    if np.any(uv) and np.any(~uv):
        f0_cont[uv] = np.interp(np.where(uv)[0], np.where(~uv)[0], f0_cont[~uv])

    # Shift pitch (semitones)
    if f0_up_key != 0:
        f0_cont = f0_cont * (2 ** (f0_up_key / 12.0))
        f0[f0 > 0] = f0[f0 > 0] * (2 ** (f0_up_key / 12.0))

    # Apply 3-frame median smoothing on continuous pitch
    if len(f0_cont) > 3:
        for i in range(1, len(f0_cont) - 1):
            f0_cont[i] = np.median([f0_cont[i - 1], f0_cont[i], f0_cont[i + 1]])

    # Official RVC Coarse pitch binning (1-255)
    f0_min = 50.0
    f0_max = 1100.0
    f0_mel_min = 1127 * np.log(1 + f0_min / 700)
    f0_mel_max = 1127 * np.log(1 + f0_max / 700)

    f0_mel = 1127 * np.log(1 + f0 / 700)
    f0_mel[f0_mel > 0] = (f0_mel[f0_mel > 0] - f0_mel_min) * 254 / (f0_mel_max - f0_mel_min) + 1
    f0_mel[f0_mel <= 1] = 1
    f0_mel[f0_mel > 255] = 255
    f0_coarse = np.rint(f0_mel).astype(np.int64)

    return f0_cont.astype(np.float32), f0_coarse


def run_studio_render():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print("=" * 65)
    print("  PROJECT LUCCA — STUDIO-GRADE ASUKA RVC SYNTHESIS")
    print(f"  Device: {device} | Pitch Method: Praat Autocorrelation (PM)")
    print(f"  Anti-Aliasing: 64-Tap Kaiser-Sinc Filter | Pitch Shift: +8 st")
    print("=" * 65)

    # 1. Base Audio
    source_audio, source_sr = generate_blended_kokoro(TEST_LINES)

    # 2. Kaiser Sinc Resampling
    print("\n[2/4] Applying 64-tap Kaiser-windowed sinc anti-aliasing resampling...")
    audio_16k = resample_kaiser_sinc(source_audio, orig_sr=source_sr, new_sr=16000)

    # 3. HuBERT Feature Extraction
    print("\n[3/4] Extracting HuBERT features on GPU...")
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

    # 4. Render lower pitch editions: +4, +5, and +6 semitones
    shifts = [4, 5, 6]
    rendered_files = []

    print("\n[4/4] Synthesizing Asuka 40kHz balanced pitch editions (+4, +5, +6 st)...")
    for shift in shifts:
        t0 = time.perf_counter()
        f0_cont, f0_coarse = extract_f0_praat(audio_16k, sr=16000, f0_up_key=shift)

        feats_t = torch.from_numpy(raw_feats_np).unsqueeze(0).to(device)
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
        out_path = OUTPUT_DIR / f"asuka_balanced_plus_{shift}st.wav"
        sf.write(str(out_path), out_audio, target_sr)
        rendered_files.append((shift, out_path, len(out_audio)/target_sr, elapsed))
        print(f"      Rendered +{shift} semitones -> {out_path.name} ({len(out_audio)/target_sr:.1f}s in {elapsed:.2f}s)")

    print("\n" + "=" * 65)
    print("BALANCED PITCH RENDERS COMPLETE!")
    for shift, path, dur, el in rendered_files:
        print(f"  Shift +{shift:02d} st: {path}")
    print("=" * 65)


if __name__ == "__main__":
    run_studio_render()
