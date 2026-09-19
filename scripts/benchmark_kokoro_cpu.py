"""
Project Lucca — TTS Kokoro-82M CPU Benchmark (Milestone 1)
Evaluates Kokoro-82M ONNX model on CPU across short phrases (<=0.8s)
and full clauses (1.88s).
Saves raw JSON benchmark to data/eval/milestone1_baseline/tts_bench_raw.json
"""

import argparse
import json
import time
from pathlib import Path

import kokoro_onnx
import numpy as np


def run_benchmark(output_path: Path | str = "data/eval/milestone1_baseline/tts_bench_raw.json", trials: int = 15):
    model_path = Path(r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx")
    voices_path = Path(r"C:\ProjectLucca\models\tts\voices-v1.0.bin")

    print("[BENCH] Loading Kokoro-82M on CPU...")
    t0 = time.perf_counter()
    engine = kokoro_onnx.Kokoro(str(model_path), str(voices_path))
    load_time_s = time.perf_counter() - t0
    print(f"[BENCH] Loaded Kokoro in {load_time_s:.2f}s")

    test_phrases = {
        "short_ack": "Understood.",
        "medium_clause": "Checking the system status now.",
        "full_clause": "The deterministic micro-scheme engine verified all static invariants in under twenty microseconds.",
    }

    # Warmup
    print("[BENCH] Running Kokoro warmup...")
    _, _ = engine.create("Warmup.", voice="af_bella", speed=1.05)

    results = {}

    for name, text in test_phrases.items():
        print(f"\n[BENCH] Benchmarking '{name}' ('{text}') ({trials} trials)...")
        latencies_ms = []
        audio_durations_s = []

        for _ in range(trials):
            t_start = time.perf_counter()
            samples, sr = engine.create(text, voice="af_bella", speed=1.05)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            audio_dur_s = len(samples) / float(sr)
            latencies_ms.append(elapsed_ms)
            audio_durations_s.append(audio_dur_s)

        latencies_ms = sorted(latencies_ms)
        p50 = float(np.percentile(latencies_ms, 50))
        p95 = float(np.percentile(latencies_ms, 95))
        mean_ms = float(np.mean(latencies_ms))
        min_ms = float(min(latencies_ms))
        max_ms = float(max(latencies_ms))
        avg_audio_dur_s = float(np.mean(audio_durations_s))
        rtf = (mean_ms / 1000.0) / avg_audio_dur_s if avg_audio_dur_s > 0 else 0.0

        results[name] = {
            "text": text,
            "trials": trials,
            "audio_duration_s": round(avg_audio_dur_s, 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "mean_ms": round(mean_ms, 2),
            "min_ms": round(min_ms, 2),
            "max_ms": round(max_ms, 2),
            "real_time_factor": round(rtf, 4),
            "raw_latencies_ms": [round(x, 2) for x in latencies_ms],
        }
        print(f"  -> '{name}' | Audio: {avg_audio_dur_s:.2f}s | Mean: {mean_ms:.1f}ms | P50: {p50:.1f}ms | P95: {p95:.1f}ms | RTF: {rtf:.4f}")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.time(),
        "model": "Kokoro-82M",
        "device": "CPU",
        "voice": "af_bella",
        "speed": 1.05,
        "load_time_s": round(load_time_s, 2),
        "results": results,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[SAVE] TTS benchmark saved to: {out_file.resolve()}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TTS Kokoro CPU Benchmark")
    parser.add_argument("--output", default="data/eval/milestone1_baseline/tts_bench_raw.json")
    parser.add_argument("--trials", type=int, default=15)
    args = parser.parse_args()
    run_benchmark(output_path=args.output, trials=args.trials)
