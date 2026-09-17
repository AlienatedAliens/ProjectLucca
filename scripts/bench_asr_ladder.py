"""
Spike 0.3 — ASR Device Ladder & Latency Benchmark
Tests Whisper-large-v3-turbo on NPU, Intel Arc iGPU (GPU.0), and CPU.
"""

import time
import wave
from pathlib import Path

import numpy as np
import openvino_genai as ov_genai

MODEL_DIR = r"C:\ProjectLucca\models\asr\whisper-large-v3-turbo-ov"
SAMPLE_WAV = r"C:\projects\ProjectLucca\tests\fixtures\audio_tool_calls\calc_01.wav"

# Read sample WAV (16kHz mono)
with wave.open(SAMPLE_WAV, "rb") as wf:
    n_frames = wf.getnframes()
    pcm = wf.readframes(n_frames)
    audio_int16 = np.frombuffer(pcm, dtype=np.int16)
    audio_float = audio_int16.astype(np.float32) / 32768.0
    sr = wf.getframerate()
    duration_s = len(audio_float) / sr

print(f"Loaded reference speech clip: '{SAMPLE_WAV}' ({duration_s:.2f}s, {sr}Hz)")

devices_to_test = ["NPU", "GPU.0", "CPU"]

for dev in devices_to_test:
    print(f"\n==========================================")
    print(f"  Testing Whisper on {dev}")
    print(f"==========================================")
    try:
        t0 = time.time()
        pipe = ov_genai.WhisperPipeline(MODEL_DIR, dev)
        print(f"  Loaded/compiled on {dev} in {time.time() - t0:.2f}s")

        # Warmup
        print(f"  Warming up...")
        res = pipe.generate(audio_float, language="<|en|>", task="transcribe")
        print(f"  Transcription: '{res.texts[0] if hasattr(res, 'texts') else res}'")

        # 5 runs to measure latency
        latencies = []
        for i in range(5):
            t_start = time.perf_counter()
            res = pipe.generate(audio_float, language="<|en|>", task="transcribe")
            dur_ms = (time.perf_counter() - t_start) * 1000.0
            latencies.append(dur_ms)
            print(f"    Run {i + 1}: {dur_ms:.1f} ms")

        p50 = float(np.percentile(latencies, 50))
        p95 = float(np.percentile(latencies, 95))
        rtf = (p50 / 1000.0) / duration_s
        print(f"  Summary on {dev}: p50={p50:.1f} ms, p95={p95:.1f} ms, RTF={rtf:.3f}")
    except Exception as e:
        print(f"  [FAIL] Whisper on {dev} failed: {e}")
