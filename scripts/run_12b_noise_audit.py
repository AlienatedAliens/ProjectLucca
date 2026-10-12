#!/usr/bin/env python3
"""
Project Lucca — 12B Extended Thinking 3-Repeat Noise & Footprint Audit
=====================================================================
Evaluates stability, per-item flips, and whole-system hardware footprint:
- Model: Gemma 4 12B Heretic Q6_K on single-slot (--parallel 1)
- Arm: Extended Thinking (enable_thinking=True, T=0.6, top_p=0.95, max_tokens=3072)
- Seeds: [42, 43, 44] across 3 independent repeats
- Scope: Non-Crux Algorithmic Suite (bbh_navigate n=20 + bbh_logical_deduction n=20)
- Hardware Monitoring: Continuous background FootprintMonitor (GPU VRAM, Temp, Host RAM)

Addresses Claude Review v7 §2.3, §2.4, §6, §10 (Item 2 & 3):
- Replaces point estimates with exact 3-repeat min/max/mean noise bounds.
- Records exact per-item flip count across seeds.
- Profiles whole-system hardware footprint (peak VRAM, peak RAM, power).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Final

import httpx

# Windows UTF-8 stdout
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.measure_footprint import FootprintMonitor

SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0


@dataclass
class ProblemEvaluation:
    problem_id: str
    domain: str
    prompt: str
    expected: str
    seed: int
    predicted: str | None
    success: bool
    finish_reason: str
    reasoning_chars: int
    content_chars: int
    elapsed_ms: float


def query_llm_think(
    prompt: str,
    seed: int,
    temperature: float = 0.6,
    top_p: float = 0.95,
    max_tokens: int = 3072,
) -> tuple[str, str, str]:
    """Queries resident llama-server with thinking enabled and fixed seed."""
    payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "seed": seed,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        content = str(choice["message"].get("content") or "").strip()
        reasoning = str(choice["message"].get("reasoning_content") or "").strip()
        finish_reason = str(choice.get("finish_reason") or "stop")
        return content, reasoning, finish_reason


def eval_navigate(ex: dict[str, Any], idx: int, seed: int) -> ProblemEvaluation:
    t0 = time.perf_counter()
    inp = str(ex["input"]).strip()
    target = str(ex["target"]).strip()
    prompt = (
        "Answer the following spatial navigation question.\n"
        "Output ONLY 'Yes' or 'No' as your final answer.\n\n"
        f"{inp}"
    )
    content, reasoning, finish = query_llm_think(prompt, seed=seed)
    matches = list(re.finditer(r"\b(Yes|No)\b", content, re.IGNORECASE))
    pred = matches[-1].group(1).capitalize() if matches else None
    if pred is None and reasoning:
        matches_r = list(re.finditer(r"\b(Yes|No)\b", reasoning[-500:], re.IGNORECASE))
        if matches_r:
            pred = matches_r[-1].group(1).capitalize()
    success = (pred == target)
    elapsed = (time.perf_counter() - t0) * 1000.0

    return ProblemEvaluation(
        problem_id=f"Navigate_{idx}",
        domain="SpatialNavigation",
        prompt=inp,
        expected=target,
        seed=seed,
        predicted=pred,
        success=success,
        finish_reason=finish,
        reasoning_chars=len(reasoning),
        content_chars=len(content),
        elapsed_ms=elapsed,
    )


def eval_deduction(ex: dict[str, Any], idx: int, seed: int) -> ProblemEvaluation:
    t0 = time.perf_counter()
    inp = str(ex["input"]).strip()
    target_clean = str(ex["target"]).strip()
    target_letter = re.sub(r"[^A-Za-z]", "", target_clean).upper()
    prompt = (
        "Solve this logic deduction problem. State your final answer as (A), (B), or (C).\n\n"
        f"{inp}"
    )
    content, reasoning, finish = query_llm_think(prompt, seed=seed)
    matches = list(re.finditer(r"\(([A-C])\)", content))
    if not matches:
        matches = list(re.finditer(r"\b([A-C])\b", content))
    pred = f"({matches[-1].group(1).upper()})" if matches else None
    if pred is None and reasoning:
        matches_r = list(re.finditer(r"\(([A-C])\)", reasoning[-500:]))
        if not matches_r:
            matches_r = list(re.finditer(r"\b([A-C])\b", reasoning[-500:]))
        if matches_r:
            pred = f"({matches_r[-1].group(1).upper()})"
    success = (pred == f"({target_letter})")
    elapsed = (time.perf_counter() - t0) * 1000.0

    return ProblemEvaluation(
        problem_id=f"Deduction_{idx}",
        domain="LogicalDeduction",
        prompt=inp,
        expected=f"({target_letter})",
        seed=seed,
        predicted=pred,
        success=success,
        finish_reason=finish,
        reasoning_chars=len(reasoning),
        content_chars=len(content),
        elapsed_ms=elapsed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="12B Thinking 3-Repeat Noise Audit")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44], help="Seeds for repeats")
    args = parser.parse_args()
    seeds: list[int] = args.seeds

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: 12B EXTENDED THINKING 3-REPEAT NOISE AUDIT ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Target Server: {SERVER_URL}", flush=True)
    print(f"Seeds: {seeds} ({len(seeds)} repeats)", flush=True)
    print("Scope: Non-Crux Algorithmic Suite (bbh_navigate n=20 + bbh_logical_deduction n=20)\n", flush=True)

    nav_file = REPO_ROOT / "data" / "benchmarks" / "bbh_navigate.json"
    nav_data = json.loads(nav_file.read_text(encoding="utf-8"))["examples"][:20]

    ded_file = REPO_ROOT / "data" / "benchmarks" / "bbh_logical_deduction_three_objects.json"
    ded_data = json.loads(ded_file.read_text(encoding="utf-8"))["examples"][:20]

    all_repeats: dict[int, list[ProblemEvaluation]] = {}

    with FootprintMonitor(interval_s=1.0) as monitor:
        for r_idx, seed in enumerate(seeds, 1):
            print(f"\n=======================================================", flush=True)
            print(f"=== REPEAT {r_idx}/{len(seeds)} (Seed: {seed}) ===", flush=True)
            print(f"=======================================================", flush=True)
            run_evals: list[ProblemEvaluation] = []

            # 1. Navigation
            for idx, ex in enumerate(nav_data, 1):
                ev = eval_navigate(ex, idx, seed=seed)
                run_evals.append(ev)
                status = "PASS" if ev.success else "FAIL"
                print(f"[Seed {seed} | Nav {idx:02d}/20] {status} ({ev.finish_reason}, {ev.reasoning_chars}ch think, {ev.elapsed_ms:.0f}ms) | Pred: {ev.predicted} | Exp: {ev.expected}", flush=True)

            # 2. Deduction
            for idx, ex in enumerate(ded_data, 1):
                ev = eval_deduction(ex, idx, seed=seed)
                run_evals.append(ev)
                status = "PASS" if ev.success else "FAIL"
                print(f"[Seed {seed} | Ded {idx:02d}/20] {status} ({ev.finish_reason}, {ev.reasoning_chars}ch think, {ev.elapsed_ms:.0f}ms) | Pred: {ev.predicted} | Exp: {ev.expected}", flush=True)

            pass_count = sum(1 for e in run_evals if e.success)
            trunc_count = sum(1 for e in run_evals if e.finish_reason == "length")
            print(f"\n>> Repeat {r_idx} (Seed {seed}) Summary: {pass_count}/40 ({pass_count/40*100:.1f}%) | Truncations: {trunc_count}/40 ({trunc_count/40*100:.1f}%)", flush=True)
            all_repeats[seed] = run_evals

    footprint_summary = monitor.get_summary()

    # Noise analysis
    scores = [sum(1 for e in evals if e.success) for evals in all_repeats.values()]
    rates = [s / 40.0 * 100.0 for s in scores]

    # Per-item stability check
    item_results: dict[str, list[bool]] = {}
    for seed, evals in all_repeats.items():
        for e in evals:
            item_results.setdefault(e.problem_id, []).append(e.success)

    always_pass = sum(1 for res in item_results.values() if all(res))
    always_fail = sum(1 for res in item_results.values() if not any(res))
    flipping = sum(1 for res in item_results.values() if any(res) and not all(res))

    print("\n" + "=" * 70, flush=True)
    print("=== 12B EXTENDED THINKING NOISE & FOOTPRINT AUDIT SUMMARY ===", flush=True)
    print("=" * 70, flush=True)
    for i, seed in enumerate(seeds):
        sc = scores[i]
        print(f"Run {i+1} (Seed {seed}): {sc}/40 ({sc/40*100:.1f}%)", flush=True)
    print(f"\nAccuracy Range:    {min(rates):.1f}% – {max(rates):.1f}% (Mean: {sum(rates)/len(rates):.1f}%)")
    print(f"Noise Drift Range: ±{(max(rates) - min(rates))/2:.1f} pp")
    print(f"Item Stability:    Always Pass: {always_pass}/40 | Always Fail: {always_fail}/40 | Flips: {flipping}/40 ({flipping/40*100:.1f}%)")
    print("\nHardware Footprint During Run:")
    print(f"  GPU Name:          {footprint_summary['gpu']['name']}")
    print(f"  Peak VRAM Used:    {footprint_summary['gpu']['peak_vram_used_mib']:.1f} MiB")
    print(f"  Peak GPU Temp:     {footprint_summary['gpu']['peak_temperature_c']} °C")
    print(f"  Peak Host RAM:     {footprint_summary['ram']['peak_ram_used_mb']:.1f} MB")
    print(f"  Peak llama-server: {footprint_summary['ram']['peak_llama_server_ram_mb']:.1f} MB")

    # Save report
    out_dir = REPO_ROOT / "logs" / "test_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_file = out_dir / f"ood_12b_thinking_3x_noise_{ts}.json"
    report_data = {
        "benchmark": "12B_Extended_Thinking_Noise_Audit",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "model": "gemma-4-12b-heretic-Q6_K.gguf",
        "seeds": seeds,
        "sample_size": 40,
        "runs": [
            {
                "seed": seed,
                "passed": scores[i],
                "accuracy_pct": rates[i],
                "problems": [asdict(e) for e in all_repeats[seed]],
            }
            for i, seed in enumerate(seeds)
        ],
        "noise_statistics": {
            "min_accuracy_pct": min(rates),
            "max_accuracy_pct": max(rates),
            "mean_accuracy_pct": round(sum(rates) / len(rates), 2),
            "drift_pp": round((max(rates) - min(rates)) / 2, 2),
            "always_pass_count": always_pass,
            "always_fail_count": always_fail,
            "flipping_count": flipping,
        },
        "hardware_footprint": footprint_summary,
    }
    out_file.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[Artifact Saved] -> {out_file}", flush=True)


if __name__ == "__main__":
    main()
