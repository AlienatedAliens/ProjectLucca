"""
Comprehensive forensic analysis of the 100-problem Phase 1 extraction audit.
Computes:
- Total evaluated N
- Raw empty count before retry vs after retry
- 95% Clopper-Pearson / Wilson score confidence interval on empty rate
- Extraction stage distribution (fenced, unfenced, longest_ast_slice, empty)
- Exit code & syntax error distribution
- Accuracy (strict LaTeX & SymPy match)
- Hand-audit 20 extracted code snippets (problem, extracted code, predicted, expected, substantive check)
"""

from __future__ import annotations

import glob
import json
import math
import os
import sys
from pathlib import Path

REPORTS_DIR = Path("logs/test_reports")


def find_latest_report() -> Path | None:
    files = list(REPORTS_DIR.glob("*v1.3-phase1-extraction-audit-100*.json"))
    if not files:
        # Check checkpoints
        files = list(REPORTS_DIR.glob("*checkpoint*extraction-audit-100*.json"))
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def wilson_score_interval(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Calculates Wilson score interval for binomial proportion."""
    if n == 0:
        return 0.0, 0.0
    z = 1.95996  # 95% confidence
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    spread = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return max(0.0, center - spread), min(1.0, center + spread)


def audit() -> None:
    target = find_latest_report()
    if not target:
        print("No audit report found yet.")
        return

    print(f"=== Auditing Report: {target.name} ===")
    with open(target, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    if isinstance(data, dict) and "benchmarks" in data:
        results = data["benchmarks"]["math500"]["results"]
    elif isinstance(data, list):
        results = data
    else:
        results = []

    n = len(results)
    if n == 0:
        print("Report contains 0 results.")
        return

    print(f"\n1. Sample Size: N = {n}")

    # Stage distribution
    stages: dict[str, int] = {}
    retry_triggered_count = 0
    empty_after_retry = 0
    exit_codes: dict[int, int] = {}
    runtime_errors: dict[str, int] = {}

    for r in results:
        stage = r.get("extraction_stage", "fenced" if r.get("generated_code") else "empty")
        stages[stage] = stages.get(stage, 0) + 1
        if r.get("extraction_retry_triggered"):
            retry_triggered_count += 1
        code = r.get("generated_code", "").strip()
        if not code:
            empty_after_retry += 1

        ec = r.get("exit_code")
        exit_codes[ec] = exit_codes.get(ec, 0) + 1

        stderr = r.get("stderr", "")
        if stderr and ec != 0:
            err_type = stderr.splitlines()[-1] if stderr.splitlines() else "UnknownError"
            err_type_clean = err_type.split(":")[0].strip()
            runtime_errors[err_type_clean] = runtime_errors.get(err_type_clean, 0) + 1

    # Empty-code metrics
    raw_empty_rate = retry_triggered_count / n
    final_empty_rate = empty_after_retry / n
    low_ci, high_ci = wilson_score_interval(empty_after_retry, n)

    print("\n2. Extraction Empty-Code Statistics:")
    print(f"   - Raw Empty Count (before 1-shot retry): {retry_triggered_count} / {n} ({raw_empty_rate * 100:.1f}%)")
    print(f"   - Final Empty Count (after 1-shot retry):  {empty_after_retry} / {n} ({final_empty_rate * 100:.1f}%)")
    print(f"   - 95% Wilson Score CI on Final Empty Rate: [{low_ci * 100:.2f}%, {high_ci * 100:.2f}%]")

    print("\n3. Extraction Stage Breakdown:")
    for st, count in sorted(stages.items(), key=lambda x: -x[1]):
        print(f"   - Stage '{st}': {count} / {n} ({count / n * 100:.1f}%)")

    print("\n4. Execution & Exit Code Distribution:")
    for ec, count in sorted(exit_codes.items(), key=lambda x: -x[1]):
        print(f"   - Exit Code {ec}: {count} / {n} ({count / n * 100:.1f}%)")

    if runtime_errors:
        print("\n   Runtime Error Types (Non-Zero Exits):")
        for et, count in sorted(runtime_errors.items(), key=lambda x: -x[1]):
            print(f"     * {et}: {count}")

    # Accuracy
    passed_count = sum(1 for r in results if r.get("passed"))
    acc = passed_count / n
    p_low, p_high = wilson_score_interval(passed_count, n)
    print("\n5. Accuracy (1-Turn Baseline on Dev Set):")
    print(f"   - Passed: {passed_count} / {n} ({acc * 100:.1f}%)")
    print(f"   - 95% Wilson Score CI: [{p_low * 100:.2f}%, {p_high * 100:.2f}%]")

    # Hand-Audit: Sample 20 items (prioritizing non-fenced / fallback stages)
    print("\n" + "=" * 60)
    print("6. HAND-AUDIT SAMPLE (20 SNIPPETS)")
    print("=" * 60)
    non_fenced = [r for r in results if r.get("extraction_stage") != "fenced"]
    fenced = [r for r in results if r.get("extraction_stage") == "fenced"]

    sample_items = non_fenced + fenced[:max(0, 20 - len(non_fenced))]
    sample_items = sample_items[:20]

    for i, it in enumerate(sample_items, 1):
        tid = it.get("idx")
        stage = it.get("extraction_stage", "unknown")
        code = it.get("generated_code", "")
        pred = it.get("predicted_ans")
        exp = it.get("expected_ans")
        passed = it.get("passed")
        ec = it.get("exit_code")

        print(f"\n--- [Audit #{i:02d}] Task ID: {tid} | Stage: '{stage}' | Exit: {ec} | Passed: {passed} ---")
        print(f"Problem: {it.get('problem', '')[:90]}...")
        print(f"Predicted: {pred!r} | Expected: {exp!r}")
        print("Extracted Code (first 3 lines):")
        code_preview = "\n".join(code.splitlines()[:3]) if code else "[EMPTY]"
        print(f"  {code_preview}")
        print(f"Total Code Lines: {len(code.splitlines())}")


if __name__ == "__main__":
    audit()
