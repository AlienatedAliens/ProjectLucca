"""
Project Lucca — ASR Whisper CPU Benchmark (Milestone 1)
Evaluates faster-whisper distil-small.en on CPU (int8) across 6 worker threads
for 1.0s, 3.0s, and 5.0s audio chunks.
Saves raw JSON benchmark to data/eval/milestone1_baseline/asr_bench_raw.json
"""

import argparse
import json
import time
from pathlib import Path

import faster_whisper
import numpy as np


def run_benchmark(output_path: Path | str = "data/eval/milestone1_baseline/asr_bench_raw.json", trials: int = 15):
    print("[BENCH] Loading faster-whisper distil-small.en on CPU (int8, cpu_threads=6)...")
    t0 = time.perf_counter()
    model = faster_whisper.WhisperModel(
        "distil-small.en",
        device="cpu",
        compute_type="int8",
        cpu_threads=6,
    )
    load_time_s = time.perf_counter() - t0
    print(f"[BENCH] Model loaded in {load_time_s:.2f}s")

    # Generate synthetic speech-like audio (16kHz mono float32)
    # Using 440 Hz modulated audio to exercise audio preprocessor and Mel spectrogram
    results = {}
    sr = 16000

    durations = [1.0, 3.0, 5.0]
    warmup_audio = np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr, dtype=np.float32))

    # Warmup
    print("[BENCH] Running model warmup...")
    list(model.transcribe(warmup_audio, language="en"))

    for dur in durations:
        print(f"\n[BENCH] Benchmarking {dur:.1f}s audio ({trials} trials)...")
        t_arr = np.linspace(0, dur, int(sr * dur), dtype=np.float32)
        # Synthetic audio
        test_audio = 0.5 * np.sin(2 * np.pi * 300 * t_arr) + 0.3 * np.sin(2 * np.pi * 600 * t_arr)

        latencies_ms = []
        for i in range(trials):
            t_start = time.perf_counter()
            segments, _ = model.transcribe(test_audio, language="en")
            _ = list(segments)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            latencies_ms.append(elapsed_ms)

        latencies_ms = sorted(latencies_ms)
        p50 = float(np.percentile(latencies_ms, 50))
        p95 = float(np.percentile(latencies_ms, 95))
        mean = float(np.mean(latencies_ms))
        min_lat = float(min(latencies_ms))
        max_lat = float(max(latencies_ms))
        rtf = (mean / 1000.0) / dur

        results[f"{dur:.1f}s"] = {
            "duration_s": dur,
            "trials": trials,
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "mean_ms": round(mean, 2),
            "min_ms": round(min_lat, 2),
            "max_ms": round(max_lat, 2),
            "real_time_factor": round(rtf, 4),
            "raw_latencies_ms": [round(x, 2) for x in latencies_ms],
        }
        print(f"  -> Duration {dur:.1f}s | Mean: {mean:.1f}ms | P50: {p50:.1f}ms | P95: {p95:.1f}ms | RTF: {rtf:.4f}")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    benchmark_payload = {
        "timestamp": time.time(),
        "model": "distil-small.en",
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": 6,
        "load_time_s": round(load_time_s, 2),
        "results": results,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(benchmark_payload, f, indent=2)

    print(f"\n[SAVE] ASR benchmark saved to: {out_file.resolve()}")
    return benchmark_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASR Whisper CPU Benchmark")
    parser.add_argument("--output", default="data/eval/milestone1_baseline/asr_bench_raw.json")
    parser.add_argument("--trials", type=int, default=15)
    args = parser.parse_args()
    run_benchmark(output_path=args.output, trials=args.trials)
