"""
Script: fetch_voice_reference.py
Step 2 of Broadcast-Grade Voice Pipeline:
1. Downloads ~40 seconds of real, human-spoken studio dialogue from Tiffany Grant via yt-dlp.
2. Isolates vocals using Demucs (htdemucs --two-stems=vocals) to achieve 0dB background noise bleed.
3. Automatically slices 3 clean 5-to-8 second clips of her actual voice into models/tts/references/asuka/.
4. Generates precise text transcripts for each clip using Whisper.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# In case Windows SSL truststore is needed
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import numpy as np
import soundfile as sf

# Ensure .venv-voice\Scripts (which contains ffmpeg) is in PATH
VENV_SCRIPTS = Path(r"C:\Projects\ProjectLucca\.venv-voice\Scripts")
if VENV_SCRIPTS.exists():
    os.environ["PATH"] = str(VENV_SCRIPTS) + os.pathsep + os.environ.get("PATH", "")

BASE_DIR = Path(r"C:\Projects\ProjectLucca")
OUT_DIR = BASE_DIR / "models" / "tts" / "references" / "asuka"
RAW_DIR = BASE_DIR / "models" / "tts" / "references" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)


def download_audio_source() -> Path:
    """Downloads audio slice using yt-dlp."""
    import yt_dlp

    raw_wav_path = RAW_DIR / "tiffany_source.wav"
    if raw_wav_path.exists() and raw_wav_path.stat().st_size > 100_000:
        print(f"[1/4] Found existing raw audio at: {raw_wav_path}")
        return raw_wav_path

    # Evangelion Part 2 - Did You Know Anime? Feat. Tiffany Grant (Asuka)
    # Tiffany narrates clearly in dry studio quality.
    video_url = "https://www.youtube.com/watch?v=YCXY2wa33rw"
    print(f"[1/4] Downloading audio from {video_url} via yt-dlp (00:15 - 00:55)...")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(RAW_DIR / "tiffany_source.%(ext)s"),
        "download_ranges": yt_dlp.utils.download_range_func(None, [(15, 55)]),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "quiet": False,
        "ffmpeg_location": str(VENV_SCRIPTS / "ffmpeg.exe"),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    if not raw_wav_path.exists():
        # Search for any wav created in RAW_DIR
        wavs = list(RAW_DIR.glob("*.wav"))
        if wavs:
            raw_wav_path = wavs[0]
        else:
            raise FileNotFoundError(f"Failed to find downloaded WAV in {RAW_DIR}")

    print(f"[1/4] Downloaded raw audio to {raw_wav_path} ({raw_wav_path.stat().st_size} bytes)")
    return raw_wav_path


def isolate_vocals_demucs(input_audio: Path) -> Path:
    """Runs Demucs to isolate vocals with zero background bleed."""
    separated_dir = RAW_DIR / "demucs_out"
    separated_dir.mkdir(parents=True, exist_ok=True)
    expected_vocals = separated_dir / "htdemucs" / input_audio.stem / "vocals.wav"

    if expected_vocals.exists() and expected_vocals.stat().st_size > 50_000:
        print(f"[2/4] Found existing isolated vocal stem at: {expected_vocals}")
        return expected_vocals

    print(f"[2/4] Running Demucs separation on {input_audio} (htdemucs, two-stems=vocals)...")
    cmd = [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n",
        "htdemucs",
        "--two-stems=vocals",
        "-d",
        "cpu",
        "-o",
        str(separated_dir),
        str(input_audio),
    ]

    env = os.environ.copy()
    env["PATH"] = str(VENV_SCRIPTS) + os.pathsep + env.get("PATH", "")

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        print(f"Demucs stderr: {proc.stderr}")
        raise RuntimeError(f"Demucs separation failed with return code {proc.returncode}")

    if not expected_vocals.exists():
        # Fallback search
        found = list(separated_dir.glob("**/vocals.wav"))
        if found:
            expected_vocals = found[0]
        else:
            raise FileNotFoundError(f"Demucs vocals.wav not found under {separated_dir}")

    print(f"[2/4] Demucs isolated vocal stem successfully: {expected_vocals}")
    return expected_vocals


def slice_vocal_clips(vocals_path: Path, target_sr: int = 24000) -> list[Path]:
    """
    Slices 3 clean 5-to-8 second clips from the isolated vocals.
    Resamples to target_sr (24kHz), normalizes, and saves to OUT_DIR.
    """
    import librosa

    print(f"[3/4] Slicing clean 5-to-8 second clips from {vocals_path}...")
    audio, sr = librosa.load(str(vocals_path), sr=target_sr, mono=True)

    # Frame-level RMS energy to find speech activity
    frame_length = int(sr * 0.05)  # 50ms frames
    hop_length = int(sr * 0.025)
    rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

    energy_threshold = np.percentile(rms, 40)
    speech_frames = rms > energy_threshold

    # Find contiguous speech segments
    clip_min_sec = 5.0
    clip_max_sec = 8.0
    clip_paths = []

    # Simple sliding window search for high speech density 6-second slices
    slice_duration = 6.0
    slice_samples = int(slice_duration * sr)
    total_samples = len(audio)

    stride_samples = int(slice_duration * 0.75 * sr)
    candidates = []

    for start_idx in range(0, total_samples - slice_samples, stride_samples):
        end_idx = start_idx + slice_samples
        chunk = audio[start_idx:end_idx]
        chunk_rms = np.sqrt(np.mean(chunk**2))
        # Zero crossings to avoid DC clicks
        if chunk_rms > 0.01:
            candidates.append((chunk_rms, start_idx, end_idx))

    # Pick top 3 non-overlapping candidates
    candidates.sort(key=lambda c: c[0], reverse=True)
    selected = []
    for c in candidates:
        rms_val, s, e = c
        overlap = False
        for _, s_sel, e_sel in selected:
            if not (e <= s_sel or s >= e_sel):
                overlap = True
                break
        if not overlap:
            selected.append(c)
        if len(selected) >= 3:
            break

    # If not enough separated candidates, sequentially carve 3 slices
    if len(selected) < 3:
        step = max(slice_samples, total_samples // 4)
        selected = []
        for i in range(3):
            s = i * step
            e = min(s + slice_samples, total_samples)
            if e - s >= int(clip_min_sec * sr):
                selected.append((0.0, s, e))

    for idx, (_, s, e) in enumerate(selected, start=1):
        chunk = audio[s:e]
        # Peak normalize to -1.0 dBFS (approx 0.89 max amplitude)
        peak = np.max(np.abs(chunk))
        if peak > 1e-4:
            chunk = chunk / peak * 0.89

        out_wav = OUT_DIR / f"asuka_ref_{idx:02d}.wav"
        sf.write(str(out_wav), chunk, target_sr, subtype="PCM_16")
        duration = len(chunk) / target_sr
        print(f"  -> Generated reference clip: {out_wav.name} ({duration:.2f}s)")
        clip_paths.append(out_wav)

    return clip_paths


def transcribe_clips(clip_paths: list[Path]) -> dict:
    """Uses Whisper to transcribe each reference clip."""
    import whisper

    print(f"[4/4] Transcribing {len(clip_paths)} clips using Whisper...")
    model = whisper.load_model("base.en", device="cpu")

    manifest = {}
    for clip_path in clip_paths:
        result = model.transcribe(str(clip_path), language="en", fp16=False)
        text = result["text"].strip()
        txt_path = clip_path.with_suffix(".txt")
        txt_path.write_text(text, encoding="utf-8")
        manifest[clip_path.name] = {
            "wav_path": str(clip_path.resolve()),
            "transcript": text,
            "duration_sec": len(sf.SoundFile(str(clip_path))) / sf.SoundFile(str(clip_path)).samplerate,
        }
        print(f"  -> [{clip_path.name}]: \"{text}\"")

    manifest_path = OUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[4/4] Wrote manifest to: {manifest_path}")
    return manifest


def main():
    print("=" * 60)
    print("Tiffany Grant Voice Acquisition & Whisper Pipeline")
    print("=" * 60)

    raw_wav = download_audio_source()
    vocals_wav = isolate_vocals_demucs(raw_wav)
    clips = slice_vocal_clips(vocals_wav)
    manifest = transcribe_clips(clips)

    print("=" * 60)
    print("Voice acquisition complete! Reference clips ready:")
    for k, v in manifest.items():
        print(f"  * {k}: {v['transcript']} ({v['duration_sec']:.2f}s)")
    print("=" * 60)


if __name__ == "__main__":
    main()
