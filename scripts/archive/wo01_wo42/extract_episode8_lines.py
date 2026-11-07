"""
Script: extract_episode8_lines.py
Extracts, slices, and categorizes every dialogue line from the Episode 8 isolated vocal track.
Displays the exact lines for immediate user review.
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
import torch
import whisper

VOCALS_FILE = Path(r"C:\Projects\ProjectLucca\harvest\vocals\htdemucs\source_00\vocals.wav")
OUT_DIR = Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\episode08")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("=" * 70)
    print("Episode 8 Dialogue Extraction & Acoustic Analysis (Tiffany Grant / Asuka)")
    print("=" * 70)

    if not VOCALS_FILE.exists():
        print(f"Error: {VOCALS_FILE} does not exist!")
        return

    audio, sr = sf.read(str(VOCALS_FILE))
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)

    total_dur = len(audio) / sr
    print(f"Loaded isolated vocal track: {total_dur:.2f}s at {sr} Hz (0dB BGM bleed).")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Whisper base.en on {device}...")
    model = whisper.load_model("base.en", device=device)

    print("Transcribing with word-level timestamps...")
    result = model.transcribe(str(VOCALS_FILE), word_timestamps=True)

    segments = result.get("segments", [])
    print(f"\nFound {len(segments)} spoken dialogue segments.\n")

    print(f"{'#':<3} | {'Time Window':<15} | {'Dur':<5} | {'Pitch (F0)':<10} | {'RMS':<6} | {'Speaker Tag':<16} | Dialogue")
    print("-" * 105)

    catalog = []
    for idx, seg in enumerate(segments):
        start_sec = max(0.0, seg["start"] - 0.05)
        end_sec = min(total_dur, seg["end"] + 0.10)
        dur = end_sec - start_sec
        text = seg["text"].strip()

        if dur < 1.0 or not re.search(r"[a-zA-Z]", text):
            continue

        start_samp = int(start_sec * sr)
        end_samp = int(end_sec * sr)
        chunk = audio[start_samp:end_samp]

        # Resample to 16kHz for pitch estimation
        chunk_16k = librosa.resample(chunk, orig_sr=sr, target_sr=16000)
        f0 = librosa.yin(chunk_16k, fmin=120, fmax=550, sr=16000)
        valid_f0 = f0[~np.isnan(f0)]

        if len(valid_f0) > 0:
            median_f0 = float(np.median(valid_f0))
        else:
            median_f0 = 0.0

        # Resample to 24kHz for CosyVoice 3
        chunk_24k = librosa.resample(chunk, orig_sr=sr, target_sr=24000)
        rms = float(np.sqrt(np.mean(chunk_24k**2)))
        max_amp = float(np.max(np.abs(chunk_24k)))

        # Normalize peak
        if max_amp > 0:
            chunk_24k = (chunk_24k / max_amp) * 0.89

        # Acoustic Speaker Discrimination:
        # Tiffany Grant's Asuka fundamental frequency: >= 240 Hz
        # Spike Spencer / male co-stars: < 230 Hz
        if median_f0 >= 240.0:
            speaker = "Asuka (Female)"
            is_asuka = True
        elif median_f0 > 0.0:
            speaker = "Shinji / Male"
            is_asuka = False
        else:
            speaker = "Unvoiced / SFX"
            is_asuka = False

        # Affective categorization
        if median_f0 > 340.0 and rms > 0.07:
            affect = "RIGHTEOUS_ANGER"
        elif median_f0 > 305.0:
            affect = "PLAYFUL_TEASING"
        elif rms < 0.028:
            affect = "INTIMATE_WHISPER"
        else:
            affect = "FOCUSED_ANALYTICAL"

        time_str = f"{seg['start']:05.2f}s - {seg['end']:05.2f}s"
        pitch_str = f"{median_f0:5.1f} Hz" if median_f0 > 0 else "N/A"

        # Save slice
        clean_text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()[:25]
        out_name = f"ep08_{idx:02d}_{'asuka' if is_asuka else 'other'}_{clean_text}.wav"
        out_file = OUT_DIR / out_name
        sf.write(str(out_file), chunk_24k, 24000)

        catalog.append({
            "index": idx,
            "filename": out_name,
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "duration": round(dur, 2),
            "f0_hz": round(median_f0, 1),
            "rms": round(rms, 4),
            "is_asuka": is_asuka,
            "speaker": speaker,
            "affect": affect,
            "text": text
        })

        tag_display = f"[{speaker}]"
        print(f"{idx:02d}  | {time_str:<15} | {dur:4.1f}s | {pitch_str:<10} | {rms:0.4f} | {tag_display:<16} | \"{text}\"")

    # Write JSON manifest
    manifest_path = OUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print(f"Extraction complete! Sliced {len(catalog)} audio clips into:")
    print(f"  {OUT_DIR}")
    print(f"Manifest written to: {manifest_path}")
    print("=" * 70)

if __name__ == "__main__":
    main()
