import time
from pathlib import Path

import kokoro_onnx
import numpy as np


def benchmark_cpu(model_path: str, voices_path: str):
    print("--- Kokoro on CPU (ONNX Runtime) ---")
    t0 = time.time()
    tts = kokoro_onnx.Kokoro(model_path, voices_path)
    load_time = time.time() - t0
    print(f"Model loaded in {load_time:.2f}s")

    clause = "Hello, how can I help you today?"
    samples, sr = tts.create(clause, voice="af_heart", speed=1.0)
    dur_audio = len(samples) / sr
    print(f"Clause: '{clause}' -> audio duration: {dur_audio:.2f}s")

    latencies = []
    rtfs = []
    for i in range(10):
        t_start = time.perf_counter()
        samples, sr = tts.create(clause, voice="af_heart", speed=1.0)
        dur_synth = time.perf_counter() - t_start
        rtf = dur_synth / dur_audio
        latencies.append(dur_synth * 1000.0)
        rtfs.append(rtf)
        print(f"  Run {i + 1:2d}: synth={dur_synth * 1000.0:.1f} ms, RTF={rtf:.3f}")

    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    mean_rtf = float(np.mean(rtfs))
    print(f"CPU Summary: p50={p50:.1f}ms, p95={p95:.1f}ms, mean RTF={mean_rtf:.3f}")


if __name__ == "__main__":
    m_path = r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx"
    v_path = r"C:\ProjectLucca\models\tts\voices-v1.0.bin"
    benchmark_cpu(m_path, v_path)
