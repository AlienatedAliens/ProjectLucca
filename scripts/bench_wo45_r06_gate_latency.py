#!/usr/bin/env python3
"""
WO-45 Task R-06: End-to-end combined gate latency measurement for
`evaluate_web_evidence_burden()` across all 360 items in
`data/benchmarks/web_evidentiary_burden_360.jsonl` after 3 warm-up calls,
on both Intel AI Boost NPU (`device="NPU"`) and CPU-only (`device="CPU"`).

Reports mean / p50 / p95 / p99 end-to-end wall-clock latency (not a sum of means),
alongside component latencies and OpenVINO device metadata.
"""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import openvino as ov  # noqa: E402
from lucca.core.neural_hazard_classifier import (  # noqa: E402
    NeuralHazardClassifier,
    _SINGLETON_HOLDER,
    _SINGLETON_LOCK,
)
from lucca.core.proof_policy import evaluate_web_evidence_burden  # noqa: E402


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    idx = (n - 1) * (pct / 100.0)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return round(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac, 3)


def summarize_latencies(vals: list[float]) -> dict[str, float]:
    s = sorted(vals)
    return {
        "n": len(s),
        "mean_ms": round(statistics.mean(s), 3),
        "stdev_ms": round(statistics.stdev(s), 3) if len(s) > 1 else 0.0,
        "min_ms": round(s[0], 3),
        "p50_ms": percentile(s, 50.0),
        "p95_ms": percentile(s, 95.0),
        "p99_ms": percentile(s, 99.0),
        "max_ms": round(s[-1], 3),
    }


def benchmark_device(device_name: str, items: list[dict[str, object]]) -> dict[str, object]:
    with _SINGLETON_LOCK:
        clf = NeuralHazardClassifier(preferred_devices=(device_name,))
        _SINGLETON_HOLDER["instance"] = clf

    if clf.active_device != device_name:
        raise RuntimeError(
            f"Requested device '{device_name}', but active_device is '{clf.active_device}'"
        )

    # 3 warm-up calls before timing
    for w_item in items[:3]:
        _ = evaluate_web_evidence_burden(
            query_text=str(w_item["query"]),
            search_results=w_item["search_results"],  # type: ignore[arg-type]
        )

    e2e_latencies_ms: list[float] = []
    npu_sub_latencies_ms: list[float] = []
    corrob_sub_latencies_ms: list[float] = []

    t_batch_start = time.perf_counter()
    for item in items:
        q = str(item["query"])
        sr = item["search_results"]
        assert isinstance(sr, list)
        t0 = time.perf_counter()
        res = evaluate_web_evidence_burden(query_text=q, search_results=sr)
        e2e_ms = (time.perf_counter() - t0) * 1000.0
        e2e_latencies_ms.append(e2e_ms)
        npu_sub_latencies_ms.append(res.npu_latency_ms)
        corrob_sub_latencies_ms.append(res.corroboration_latency_ms)
    total_wall_s = round(time.perf_counter() - t_batch_start, 4)

    return {
        "requested_device": device_name,
        "active_openvino_device": clf.active_device,
        "warmup_calls": 3,
        "n_timed_items": len(items),
        "total_wall_clock_s": total_wall_s,
        "combined_end_to_end_gate_ms": summarize_latencies(e2e_latencies_ms),
        "hazard_classifier_component_ms": summarize_latencies(npu_sub_latencies_ms),
        "walton_corroboration_component_ms": summarize_latencies(corrob_sub_latencies_ms),
    }


def main() -> None:
    bench_path = REPO_ROOT / "data/benchmarks/web_evidentiary_burden_360.jsonl"
    items = [
        json.loads(line)
        for line in bench_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(items) == 360

    core = ov.Core()
    hw_devices: dict[str, str] = {}
    for dev in core.available_devices:
        try:
            hw_devices[dev] = str(core.get_property(dev, "FULL_DEVICE_NAME"))
        except Exception:  # noqa: BLE001
            hw_devices[dev] = dev

    npu_res = benchmark_device("NPU", items)
    cpu_res = benchmark_device("CPU", items)

    # Restore NPU default
    with _SINGLETON_LOCK:
        _SINGLETON_HOLDER["instance"] = NeuralHazardClassifier(preferred_devices=("NPU", "CPU"))

    payload = {
        "task_id": "R-06",
        "description": "End-to-end combined wall-clock latency of evaluate_web_evidence_burden() across N=360 items (3 warm-ups) on Intel AI Boost NPU and CPU-only",
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "dataset_path": "data/benchmarks/web_evidentiary_burden_360.jsonl",
        "dataset_sha256": hashlib.sha256(bench_path.read_bytes()).hexdigest(),
        "hardware": {
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "openvino_version": ov.__version__,
            "openvino_devices": hw_devices,
        },
        "results": {
            "NPU": npu_res,
            "CPU": cpu_res,
        },
    }

    out_path = REPO_ROOT / "logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {out_path}")
    print("Hardware:", json.dumps(payload["hardware"], indent=2))
    print("NPU Combined E2E (ms):", npu_res["combined_end_to_end_gate_ms"])
    print("CPU Combined E2E (ms):", cpu_res["combined_end_to_end_gate_ms"])


if __name__ == "__main__":
    main()
