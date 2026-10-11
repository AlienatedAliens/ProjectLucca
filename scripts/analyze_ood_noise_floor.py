#!/usr/bin/env python3
"""
Project Lucca — OOD Benchmark Noise Floor & Stability Analyzer
==============================================================
Analyzes multiple repeats of the 60-problem OOD generality audit.
Measures:
1. Run-to-run variance across repeats (Arm A Bare vs Arm B PAL).
2. Item-level stability: discordant pairs, flip counts, McNemar test.
3. Problem-level non-regression invariance: tests if Arm B >= Arm A on EVERY item across ALL runs.
4. Finish-reason breakdown (stop vs length/truncation).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from scipy.stats import binomtest


@dataclass
class ProblemTrace:
    problem_id: str
    domain: str
    expected: str
    arm_a_results: list[bool]
    arm_b_results: list[bool]
    arm_a_finishes: list[str]
    arm_b_finishes: list[str]


def compute_mcnemar(b: int, c: int) -> float:
    """Computes exact two-sided binomial p-value on discordant pairs (b, c)."""
    n = b + c
    if n == 0:
        return 1.0
    res = binomtest(k=b, n=n, p=0.5, alternative="two-sided")
    return float(res.pvalue)


def analyze_runs(report_paths: list[Path]) -> None:
    print(f"=================================================================")
    print(f"=== PROJECT LUCCA: OOD BENCHMARK NOISE FLOOR & STABILITY AUDIT ===")
    print(f"=================================================================")
    print(f"Analyzing {len(report_paths)} audit runs:")
    for i, p in enumerate(report_paths, 1):
        print(f"  Run {i}: {p.name}")
    print()

    loaded_reports: list[dict[str, Any]] = []
    for p in report_paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        loaded_reports.append(data)

    n_runs = len(loaded_reports)
    n_problems = len(loaded_reports[0]["problems"])

    # 1. Headline summary per run
    print("--- [1] Headline Scores Per Run ---")
    print(f"{'Run':<6} | {'Arm A Bare':<15} | {'Arm B PAL':<15} | {'Non-Crux (n=40)':<18} | {'Lift (B - A)':<15}")
    print("-" * 75)
    for i, rep in enumerate(loaded_reports, 1):
        a_pass = rep["architectural_transfer"]["arm_a_total_passed"]
        b_pass = rep["architectural_transfer"]["arm_b_total_passed"]
        tot = rep["total_problems"]
        a_pct = (a_pass / tot) * 100.0
        b_pct = (b_pass / tot) * 100.0
        lift = b_pct - a_pct

        # Non-crux
        doms = rep["architectural_transfer"]["domains"]
        nc_a = doms["SpatialNavigation"]["arm_a_passed"] + doms["LogicalDeduction"]["arm_a_passed"]
        nc_b = doms["SpatialNavigation"]["arm_b_passed"] + doms["LogicalDeduction"]["arm_b_passed"]
        nc_tot = doms["SpatialNavigation"]["total"] + doms["LogicalDeduction"]["total"]
        nc_str = f"A:{nc_a}/{nc_tot} -> B:{nc_b}/{nc_tot}"

        print(f"Run {i:<2} | {a_pass}/{tot} ({a_pct:5.1f}%)    | {b_pass}/{tot} ({b_pct:5.1f}%)    | {nc_str:<18} | +{lift:5.1f} pp")
    print()

    # 2. Build item traces
    prob_traces: dict[str, ProblemTrace] = {}
    for p_entry in loaded_reports[0]["problems"]:
        pid = p_entry["problem_id"]
        prob_traces[pid] = ProblemTrace(
            problem_id=pid,
            domain=p_entry["domain"],
            expected=p_entry["expected_answer"],
            arm_a_results=[],
            arm_b_results=[],
            arm_a_finishes=[],
            arm_b_finishes=[],
        )

    for rep in loaded_reports:
        for p_entry in rep["problems"]:
            pid = p_entry["problem_id"]
            trace = prob_traces[pid]
            trace.arm_a_results.append(bool(p_entry["arm_a_success"]))
            trace.arm_b_results.append(bool(p_entry["arm_b_success"]))
            trace.arm_a_finishes.append(str(p_entry.get("arm_a_finish_reason", "stop")))
            trace.arm_b_finishes.append(str(p_entry.get("arm_b_finish_reason", "stop")))

    # 3. Item-level stability & flip count
    arm_a_always_pass = 0
    arm_a_always_fail = 0
    arm_a_flips = 0

    arm_b_always_pass = 0
    arm_b_always_fail = 0
    arm_b_flips = 0

    negative_flips: list[tuple[str, int]] = []  # (problem_id, run_idx) where Arm A won and Arm B lost

    for pid, trace in prob_traces.items():
        # Arm A
        a_sum = sum(trace.arm_a_results)
        if a_sum == n_runs:
            arm_a_always_pass += 1
        elif a_sum == 0:
            arm_a_always_fail += 1
        else:
            arm_a_flips += 1

        # Arm B
        b_sum = sum(trace.arm_b_results)
        if b_sum == n_runs:
            arm_b_always_pass += 1
        elif b_sum == 0:
            arm_b_always_fail += 1
        else:
            arm_b_flips += 1

        # Non-regression invariant check: Arm B >= Arm A on every run
        for r_idx in range(n_runs):
            if trace.arm_a_results[r_idx] and not trace.arm_b_results[r_idx]:
                negative_flips.append((pid, r_idx + 1))

    print("--- [2] Item-Level Consistency Across All Runs ---")
    print(f"Arm A (Bare): Always Pass: {arm_a_always_pass}/{n_problems} | Always Fail: {arm_a_always_fail}/{n_problems} | Flipped: {arm_a_flips}/{n_problems}")
    print(f"Arm B (PAL) : Always Pass: {arm_b_always_pass}/{n_problems} | Always Fail: {arm_b_always_fail}/{n_problems} | Flipped: {arm_b_flips}/{n_problems}")
    print()

    print("--- [3] Problem-Level Non-Regression Invariant (Arm B >= Arm A) ---")
    if not negative_flips:
        print(f"PASS: 100% Verified across all {n_problems * n_runs} problem-evaluations.")
        print(f"Zero instances where Arm A succeeded and Arm B failed.")
    else:
        print(f"VIOLATIONS FOUND ({len(negative_flips)} instances):")
        for pid, r_idx in negative_flips:
            print(f"  - Problem {pid} in Run {r_idx}: Arm A passed, Arm B failed!")
    print()

    # 4. Pairwise discordant counts
    print("--- [4] Pairwise Run Discordant Counts & McNemar Stability ---")
    for i in range(n_runs):
        for j in range(i + 1, n_runs):
            # Arm A discordant
            a_b = 0  # pass in i, fail in j
            a_c = 0  # fail in i, pass in j
            # Arm B discordant
            b_b = 0
            b_c = 0

            for pid, trace in prob_traces.items():
                if trace.arm_a_results[i] and not trace.arm_a_results[j]:
                    a_b += 1
                elif not trace.arm_a_results[i] and trace.arm_a_results[j]:
                    a_c += 1

                if trace.arm_b_results[i] and not trace.arm_b_results[j]:
                    b_b += 1
                elif not trace.arm_b_results[i] and trace.arm_b_results[j]:
                    b_c += 1

            p_val_a = compute_mcnemar(a_b, a_c)
            p_val_b = compute_mcnemar(b_b, b_c)
            print(f"Runs {i+1} vs {j+1}:")
            print(f"  Arm A Discordant: {a_b} (lost in {j+1}) vs {a_c} (gained in {j+1}) | Discordant Total: {a_b + a_c} | McNemar p={p_val_a:.4f}")
            print(f"  Arm B Discordant: {b_b} (lost in {j+1}) vs {b_c} (gained in {j+1}) | Discordant Total: {b_b + b_c} | McNemar p={p_val_b:.4f}")
    print()

    # 5. Finish Reason Breakdown
    print("--- [5] Truncation Rate Analysis (finish_reason) ---")
    a_len_total = 0
    b_len_total = 0
    tot_evals = n_problems * n_runs
    for trace in prob_traces.values():
        a_len_total += trace.arm_a_finishes.count("length")
        b_len_total += trace.arm_b_finishes.count("length")
    print(f"Arm A Length Truncations: {a_len_total}/{tot_evals} ({a_len_total / tot_evals * 100:.1f}%)")
    print(f"Arm B Length Truncations: {b_len_total}/{tot_evals} ({b_len_total / tot_evals * 100:.1f}%)")
    print("=================================================================")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze multiple OOD audit runs for noise floor and stability")
    parser.add_argument("reports", nargs="+", type=Path, help="Paths to ood_generality_audit JSON reports")
    args = parser.parse_args()
    analyze_runs(args.reports)


if __name__ == "__main__":
    main()
