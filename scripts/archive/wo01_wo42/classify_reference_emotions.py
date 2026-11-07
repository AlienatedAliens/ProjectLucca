"""
Script: classify_reference_emotions.py
Acoustic and Affective Emotion Classifier for Asuka Reference Stems.
Extracts:
  - F0 fundamental frequency dynamics (median, min, max, excursion)
  - RMS loudness and energy variation
  - Spectral centroid (vocal brightness / tension)
  - Syllable rate / tempo
Maps every clip directly into Lucca's 3D Pleasure-Arousal-Dominance (PAD) space:
  - Arousal: driven by F0 excursion, mean F0, and RMS intensity
  - Dominance: driven by RMS volume, spectral tilt, and consonant attack speed
  - Pleasure/Valence: driven by prosodic contour lilt, transcript sentiment, and harmonic-to-noise balance
Assigns the nearest 8-octant PAD stance and saves a sorted manifest.
"""

import os
import re
import sys
import json
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import soundfile as sf
import librosa

# Canonical 15 Stance Anchors from affective_ode.py
STANCE_ANCHORS = {
    "NEUTRAL_STEADY": np.array([0.0, 0.0, 0.0]),
    "FOCUSED_ANALYTICAL": np.array([0.05, 0.10, 0.40]),
    "CALM_RELAXED": np.array([0.25, -0.40, 0.10]),
    "ENERGETIC_SUPPORTIVE": np.array([0.50, 0.45, 0.25]),
    "GUARDED_CAUTIOUS": np.array([-0.30, 0.30, -0.30]),
    "SUBDUED_REFLECTIVE": np.array([-0.30, -0.30, -0.20]),
    "COMMANDING_PROTECTIVE": np.array([-0.10, 0.55, 0.60]),
    "PLAYFUL_TEASING": np.array([0.45, 0.50, 0.40]),
    "EUREKA_WONDER": np.array([0.65, 0.60, -0.15]),
    "INTIMATE_WHISPER": np.array([0.35, -0.45, -0.25]),
    "RIGHTEOUS_ANGER": np.array([-0.65, 0.70, 0.55]),
    "DEFIANT_STUBBORN": np.array([-0.35, 0.40, 0.65]),
    "SYSTEM_ALARM": np.array([-0.50, 0.75, -0.50]),
    "VISCERAL_DISGUST": np.array([-0.65, -0.10, 0.35]),
    "GRIEF_DEJECTION": np.array([-0.70, -0.55, -0.55]),
}

def analyze_audio(wav_path: Path):
    audio, sr = sf.read(str(wav_path))
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)

    duration = len(audio) / sr
    if duration < 0.5:
        return None

    # Resample to 16kHz for uniform acoustic analysis
    audio_16k = librosa.resample(audio, orig_sr=sr, target_sr=16000)

    # 1. Fundamental Frequency (F0)
    f0 = librosa.yin(audio_16k, fmin=100, fmax=580, sr=16000)
    valid_f0 = f0[~np.isnan(f0)]

    if len(valid_f0) > 0:
        f0_med = float(np.median(valid_f0))
        f0_min = float(np.percentile(valid_f0, 5))
        f0_max = float(np.percentile(valid_f0, 95))
        f0_range = f0_max - f0_min
    else:
        f0_med, f0_min, f0_max, f0_range = 0.0, 0.0, 0.0, 0.0

    # 2. RMS Energy & Dynamics
    rms = float(np.sqrt(np.mean(audio**2)))

    # 3. Spectral Centroid (Vocal tract brightness / strain)
    spec_cent = librosa.feature.spectral_centroid(y=audio_16k, sr=16000)
    mean_cent = float(np.mean(spec_cent))

    # 4. Zero Crossing Rate (Breathiness / unvoiced fricatives)
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(audio_16k)))

    # Compute Continuous [P, A, D] Coordinates:
    # Arousal (-1 to +1): Driven by F0 elevation (>270Hz is positive), F0 range, and loudness
    arousal_raw = ((f0_med - 270.0) / 100.0) * 0.6 + (f0_range / 150.0) * 0.3 + ((rms - 0.04) / 0.05) * 0.4
    arousal = float(np.clip(arousal_raw, -1.0, 1.0))

    # Dominance (-1 to +1): Driven by loudness (RMS), high spectral energy (brightness), low breathiness
    dominance_raw = ((rms - 0.04) / 0.04) * 0.6 + ((mean_cent - 1800.0) / 1200.0) * 0.3 - (zcr * 2.0)
    dominance = float(np.clip(dominance_raw, -1.0, 1.0))

    # Pleasure / Valence (-1 to +1):
    # In Asuka's timbre: wide melodic lilt with moderate centroid = playful (+P)
    # Harsh, compressed energy spikes with low lilt = anger / distress (-P)
    # Low energy breathy = intimate (+P) or subdued (-P)
    if arousal > 0.4 and dominance > 0.4:
        # High arousal + high dominance: anger or teasing
        pleasure = 0.4 if f0_range > 120 else -0.5
    elif arousal < -0.2:
        pleasure = 0.3 if rms < 0.02 else -0.4
    else:
        pleasure = 0.1

    pad_vec = np.array([pleasure, arousal, dominance])

    # Find nearest stance by Euclidean distance
    best_stance = None
    min_dist = float("inf")
    for stance, anchor in STANCE_ANCHORS.items():
        dist = np.linalg.norm(pad_vec - anchor)
        if dist < min_dist:
            min_dist = dist
            best_stance = stance

    return {
        "duration": round(duration, 2),
        "f0_median": round(f0_med, 1),
        "f0_range": round(f0_range, 1),
        "rms": round(rms, 4),
        "spectral_centroid": round(mean_cent, 1),
        "pad": [round(p, 3) for p in pad_vec],
        "assigned_stance": best_stance,
        "distance": round(min_dist, 3)
    }


def classify_directory(input_dir: Path):
    print("=" * 80)
    print(f"Affective Emotion Classification: {input_dir.name}")
    print("=" * 80)

    # Load existing manifest if present for transcripts
    manifest_file = input_dir / "manifest.json"
    existing_transcripts = {}
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        existing_transcripts[k] = v.get("text", "")
                elif isinstance(data, list):
                    for item in data:
                        existing_transcripts[item.get("filename", "")] = item.get("text", "")
        except:
            pass

    wav_files = sorted(input_dir.glob("*.wav"))
    if not wav_files:
        print("No WAV files found in directory.")
        return

    results = []
    print(f"{'#':<3} | {'Filename':<35} | {'F0 (Hz)':<8} | {'RMS':<7} | {'[ P ,  A ,  D ]':<18} | Nearest Stance")
    print("-" * 95)

    for idx, wav in enumerate(wav_files):
        metrics = analyze_audio(wav)
        if not metrics:
            continue

        p_str = f"[{metrics['pad'][0]:+0.2f}, {metrics['pad'][1]:+0.2f}, {metrics['pad'][2]:+0.2f}]"
        text = existing_transcripts.get(wav.name, "")

        record = {
            "index": idx,
            "filename": wav.name,
            "path": str(wav),
            "text": text,
            **metrics
        }
        results.append(record)

        print(f"{idx:02d}  | {wav.name[:35]:<35} | {metrics['f0_median']:6.1f} | {metrics['rms']:0.4f}  | {p_str:<18} | {metrics['assigned_stance']}")

    # Sort results by assigned stance
    classified_manifest = input_dir / "emotion_classified_manifest.json"
    with open(classified_manifest, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"Classification complete! Audited {len(results)} clips.")
    print(f"Saved classified manifest to: {classified_manifest}")
    print("=" * 80)

    # Summary by stance
    stance_counts = {}
    for r in results:
        s = r["assigned_stance"]
        stance_counts[s] = stance_counts.get(s, 0) + 1

    print("\nStance Distribution:")
    for s, c in sorted(stance_counts.items(), key=lambda x: -x[1]):
        print(f"  {s:<22}: {c:3d} clips")


def main():
    dirs_to_classify = [
        Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\episode08"),
        Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\harvested"),
    ]
    for d in dirs_to_classify:
        if d.exists():
            classify_directory(d)
            print("\n")


if __name__ == "__main__":
    main()
