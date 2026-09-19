"""
Project Lucca — Live Benchmark: 5-Substrate Epistemic Search Cascade on Workstation Silicon
Measures physical execution latency on Intel Core Ultra 9 275HX + RTX 5080 Laptop GPU.
"""

from __future__ import annotations

import time
import numpy as np

from lucca.core.cascade import (
    EpistemicSearchCascade,
    EpistemicSubstrate,
    classify_epistemic_intent,
    select_floor_cue,
)
from lucca.sandbox.service import SandboxService


def run_benchmark() -> None:
    print("=" * 70)
    print("PROJECT LUCCA — 5-SUBSTRATE EPISTEMIC SEARCH CASCADE BENCHMARK")
    print("Hardware: Intel Core Ultra 9 275HX | NVIDIA RTX 5080 Laptop GPU (16 GB)")
    print("=" * 70)

    cascade = EpistemicSearchCascade()

    # 1. Reflex Floor-Holding Cue Selection Latency (Target: < 1.0 ms, Budget: <= 120 ms)
    cue_times_us = []
    queries = [
        "What is the GPU VRAM load?",
        "Read the file at config/persona.toml",
        "Do you remember my preferred editor?",
        "Fetch the contents of https://example.com",
        "Who is your creator? What is their full real name?",
    ]
    for _ in range(100):
        for q in queries:
            t0 = time.perf_counter()
            _ = select_floor_cue(q)
            cue_times_us.append((time.perf_counter() - t0) * 1_000_000.0)

    cue_p50_us = np.percentile(cue_times_us, 50)
    cue_p95_us = np.percentile(cue_times_us, 95)
    print(f"\n[Floor-Holding Cue Selection] (N={len(cue_times_us)})")
    print(f"  P50: {cue_p50_us:.2f} µs ({cue_p50_us/1000.0:.4f} ms)")
    print(f"  P95: {cue_p95_us:.2f} µs ({cue_p95_us/1000.0:.4f} ms)")
    print(f"  Acoustic Reflex Budget: <= 120.00 ms (Margin: {120.0 - (cue_p50_us/1000.0):.2f} ms)")

    # 2. Substrate 0: Telemetry Latency (Target: <= 1.0 ms warm)
    # Warm up cache
    _ = cascade.query_substrate_0_telemetry("What is the GPU VRAM load?")
    sub0_times_ms = []
    for _ in range(100):
        t0 = time.perf_counter()
        _ = cascade.query_substrate_0_telemetry("What is the GPU VRAM load?")
        sub0_times_ms.append((time.perf_counter() - t0) * 1000.0)

    sub0_p50 = np.percentile(sub0_times_ms, 50)
    sub0_p95 = np.percentile(sub0_times_ms, 95)
    print(f"\n[Substrate 0: Telemetry (Tier 1 Hardware Truth)] (N=100)")
    print(f"  P50: {sub0_p50:.4f} ms")
    print(f"  P95: {sub0_p95:.4f} ms")
    print(f"  Target: <= 1.000 ms -> {'PASS' if sub0_p50 <= 1.0 else 'FAIL'}")

    # 3. Substrate 4: Calibrated Honest Abstention Latency (Target: <= 0.5 ms)
    sub4_times_ms = []
    for _ in range(100):
        t0 = time.perf_counter()
        res = cascade.query("Who is your creator? What is their full real name?", substrates=[])
        sub4_times_ms.append((time.perf_counter() - t0) * 1000.0)

    sub4_p50 = np.percentile(sub4_times_ms, 50)
    sub4_p95 = np.percentile(sub4_times_ms, 95)
    print(f"\n[Substrate 4: Calibrated Abstention (\\bot Ground Truth Gap)] (N=100)")
    print(f"  P50: {sub4_p50:.4f} ms")
    print(f"  P95: {sub4_p95:.4f} ms")
    print(f"  Target: <= 0.500 ms -> {'PASS' if sub4_p50 <= 0.5 else 'FAIL'}")

    # 4. Intent Classifier Latency
    intent_times_us = []
    for _ in range(100):
        for q in queries:
            t0 = time.perf_counter()
            _ = classify_epistemic_intent(q)
            intent_times_us.append((time.perf_counter() - t0) * 1_000_000.0)

    intent_p50_us = np.percentile(intent_times_us, 50)
    print(f"\n[Intent Classifier Latency] (N={len(intent_times_us)})")
    print(f"  P50: {intent_p50_us:.2f} µs ({intent_p50_us/1000.0:.4f} ms)")

    print("\n" + "=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
