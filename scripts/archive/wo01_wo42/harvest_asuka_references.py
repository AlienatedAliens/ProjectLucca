"""
Script: harvest_asuka_references.py
Automated high-yield acoustic harvester for Asuka Langley Soryu (Tiffany Grant) reference stems.
Pipeline:
  1. Ingest audio via yt-dlp or local paths.
  2. Isolate dry vocal stems via Demucs (CUDA on RTX 5080).
  3. Whisper base.en transcription with word-level timestamps (3.5s to 7.5s optimal prompt windows).
  4. Acoustic fundamental frequency (F0) tracking via YIN (F0 >= 240 Hz rejects male speakers automatically).
  5. Affective stance classification (RMS energy + F0 excursion) mapped to Lucca PAD states.
  6. 24kHz mono resampling + boundary padding (50ms leading, 100ms trailing).
  7. Manifest generation (manifest.json) for CosyVoice 3 prompt conditioning.
"""

import os
import re
import sys
import glob
import json
import shutil
import subprocess
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import soundfile as sf
import librosa
import torch
import whisper

# Ensure .venv-voice\Scripts (which contains ffmpeg.exe) is in PATH
VENV_SCRIPTS = Path(r"C:\Projects\ProjectLucca\.venv-voice\Scripts")
if VENV_SCRIPTS.exists():
    os.environ["PATH"] = str(VENV_SCRIPTS) + os.pathsep + os.environ.get("PATH", "")

SOURCES = [
    # Source 1: Evangelion ADV Dub Debut & Classic Dialogue Scenes
    "https://www.youtube.com/watch?v=s4B-ky5PxAw",
    # Source 2: Anime USA 2022 Panel with Tiffany Grant (Clean Stage Mic)
    "https://www.youtube.com/watch?v=BsbDPj6oa1k",
]

PROJECT_ROOT = Path(r"C:\Projects\ProjectLucca")
HARVEST_DIR = PROJECT_ROOT / "harvest"
RAW_DIR = HARVEST_DIR / "raw"
VOCAL_DIR = HARVEST_DIR / "vocals"
OUTPUT_DIR = PROJECT_ROOT / "models" / "tts" / "references" / "asuka" / "harvested"

RAW_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download_sources():
    print("=" * 65)
    print("Step 1: Downloading & Ingesting Audio Sources")
    print("=" * 65)
    for idx, src in enumerate(SOURCES):
        if src.startswith("http"):
            out_base = RAW_DIR / f"source_{idx:02d}"
            target_wav = RAW_DIR / f"source_{idx:02d}.wav"
            if target_wav.exists() and target_wav.stat().st_size > 1000:
                print(f"[SKIP] Source {idx:02d} already downloaded: {target_wav.name}")
                continue
            print(f"Downloading Source {idx:02d} from {src} via yt_dlp...")
            import yt_dlp
            ffmpeg_path = r"C:\Projects\ProjectLucca\.venv-voice\Scripts\ffmpeg.exe"
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": str(out_base) + ".%(ext)s",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "wav",
                        "preferredquality": "192",
                    }
                ],
                "quiet": False,
                "ffmpeg_location": ffmpeg_path if os.path.exists(ffmpeg_path) else None,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([src])
            print(f"Downloaded {target_wav.name}")
        elif os.path.exists(src):
            target_wav = RAW_DIR / f"source_{idx:02d}_{Path(src).stem}.wav"
            if not target_wav.exists():
                shutil.copy2(src, target_wav)
                print(f"Copied local file: {target_wav.name}")


def run_demucs_isolation():
    print("\n" + "=" * 65)
    print("Step 2: Stripping BGM & Sound Effects with Demucs on RTX 5080")
    print("=" * 65)
    raw_wavs = sorted(glob.glob(str(RAW_DIR / "*.wav")))
    if not raw_wavs:
        print("ERROR: No raw WAV files found to separate!")
        return

    # Filter to only WAVs that don't have separated vocals yet
    wavs_to_separate = []
    for rw in raw_wavs:
        stem_name = Path(rw).stem
        expected_vocal = VOCAL_DIR / "htdemucs" / stem_name / "vocals.wav"
        if not expected_vocal.exists():
            wavs_to_separate.append(rw)

    if not wavs_to_separate:
        print("All sources already have separated vocal stems in Demucs directory.")
        return

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Running Demucs on {len(wavs_to_separate)} files using device: {device}...")
    cmd = [
        "demucs",
        "--two-stems=vocals",
        "-o", str(VOCAL_DIR),
        "-d", device
    ] + wavs_to_separate
    subprocess.run(cmd, check=True)
    print("Demucs vocal separation complete!")


def harvest_and_filter():
    print("\n" + "=" * 65)
    print("Step 3 & 4: Whisper Transcription, Pitch Tracking & Affect Tagging")
    print("=" * 65)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Whisper base.en on {device}...")
    whisper_model = whisper.load_model("base.en", device=device)

    vocal_stems = sorted(glob.glob(str(VOCAL_DIR / "htdemucs" / "*" / "vocals.wav")))
    if not vocal_stems:
        print("ERROR: No Demucs vocals.wav files found!")
        return

    manifest = {}
    sample_idx = 0

    for stem_path in vocal_stems:
        source_name = Path(stem_path).parent.name
        print(f"\n--- Processing Stem: {source_name} ---")
        audio, sr = sf.read(stem_path)
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)

        total_dur = len(audio) / sr
        print(f"Audio duration: {total_dur:.1f}s at {sr} Hz. Running Whisper transcription...")

        result = whisper_model.transcribe(stem_path, word_timestamps=True)
        segments = result.get("segments", [])
        print(f"Found {len(segments)} candidate segments. Evaluating pitch and acoustic filters...")

        for seg in segments:
            text = seg["text"].strip()
            start_sec = max(0.0, seg["start"] - 0.05)  # 50ms leading padding
            end_sec = min(total_dur, seg["end"] + 0.10)  # 100ms trailing padding
            duration = end_sec - start_sec

            # Length bounds optimal for CosyVoice 3 prompt conditioning (3.5s - 7.5s)
            if duration < 3.2 or duration > 7.5:
                continue

            # Text filter: must contain at least 4 words and some letters
            words = text.split()
            if len(words) < 4 or not re.search(r"[a-zA-Z]", text):
                continue

            start_samp = int(start_sec * sr)
            end_samp = int(end_sec * sr)
            chunk = audio[start_samp:end_samp]

            if len(chunk) < sr * 3:
                continue

            # 1. Fundamental Frequency Tracking (YIN)
            # Downsample to 16kHz for fast, accurate pitch tracking
            chunk_16k = librosa.resample(chunk, orig_sr=sr, target_sr=16000)
            f0 = librosa.yin(chunk_16k, fmin=120, fmax=550, sr=16000)
            valid_f0 = f0[~np.isnan(f0)]

            if len(valid_f0) == 0:
                continue

            median_pitch = float(np.median(valid_f0))

            # Pitch gate: Tiffany Grant Asuka sits >= 240 Hz.
            # Males (Shinji, Gendo, Kaji) sit below 215 Hz.
            if median_pitch < 240.0:
                continue

            # 2. Resample to CosyVoice 3 Native 24,000 Hz Mono
            chunk_24k = librosa.resample(chunk, orig_sr=sr, target_sr=24000)

            # 3. RMS Energy & Affective Categorization
            rms = float(np.sqrt(np.mean(chunk_24k**2)))
            max_amp = float(np.max(np.abs(chunk_24k)))

            # Normalize peak to -1 dBFS (0.89) to prevent clipping while maintaining dynamic range
            if max_amp > 0:
                chunk_24k = (chunk_24k / max_amp) * 0.89

            # Affect classification mapped to PAD octants
            if rms > 0.075 and median_pitch > 330.0:
                category = "anger_arousal"
                stance = "RIGHTEOUS_ANGER"
            elif median_pitch > 305.0:
                category = "energetic_tease"
                stance = "PLAYFUL_TEASING"
            elif rms < 0.028:
                category = "subdued_whisper"
                stance = "INTIMATE_WHISPER"
            else:
                category = "focused_analytical"
                stance = "FOCUSED_ANALYTICAL"

            # Clean filename from text
            clean_text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()[:28]
            fname = f"asuka_{sample_idx:03d}_{category}_{clean_text}.wav"
            out_file = OUTPUT_DIR / fname

            sf.write(str(out_file), chunk_24k, 24000)

            manifest[fname] = {
                "text": text,
                "duration": round(duration, 2),
                "f0_hz": round(median_pitch, 1),
                "rms": round(rms, 4),
                "category": category,
                "stance": stance,
                "source": source_name,
            }

            print(f"[{sample_idx:03d}] {duration:.1f}s | F0: {median_pitch:.0f}Hz | RMS: {rms:.3f} | [{stance}]")
            print(f"      File: {fname}")
            print(f"      Text: \"{text}\"")
            sample_idx += 1

    # Save structured manifest
    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 65)
    print(f"Harvest Complete! Extracted {sample_idx} studio-dry 24kHz Asuka stems.")
    print(f"Stems and manifest saved to: {OUTPUT_DIR}")
    print("=" * 65)


def main():
    download_sources()
    run_demucs_isolation()
    harvest_and_filter()


if __name__ == "__main__":
    main()
