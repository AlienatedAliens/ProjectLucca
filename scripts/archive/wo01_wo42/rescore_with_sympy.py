"""
Project Lucca — Uniform Grader & Rescoring Engine
Evaluates saved benchmark JSON outputs with:
  1. Strict v1.2 Grader (Exact string, comma sets, float eval)
  2. Upgraded v1.3 Grader (Base subscripts, plus-minus sets, SymPy algebraic equivalence)
  3. Paired McNemar Test between two runs (e.g. baseline vs feedback loop on identical problems)

Usage:
  .venv\\Scripts\\python.exe scripts/rescore_with_sympy.py logs/test_reports/my_report.json
  .venv\\Scripts\\python.exe scripts/rescore_with_sympy.py --compare logs/report_v12.json logs/report_v13.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_modern_2024_benchmarks import (
    clean_latex_for_sympy,
    compare_math_results,
    normalize_math_str,
)


def rescore_math500_file(filepath: Path) -> dict:
    """Load a MATH-500 test report and evaluate both strict and SymPy accuracy."""
    data = json.loads(filepath.read_text(encoding="utf-8"))
    math_data = data.get("benchmarks", {}).get("math500", {})
    if not math_data:
        # Check if direct results
        math_data = data

    results = math_data.get("results", [])
    if not results:
        print(f"[WARN] No results found in {filepath}")
        return {}

    strict_pass = 0
    sympy_pass = 0
    per_item_strict = []
    per_item_sympy = []
    newly_accepted = []

    total = len(results)
    for idx, item in enumerate(results):
        pred = item.get("predicted_ans", "")
        exp = item.get("expected_ans", "")

        is_strict = compare_math_results(pred, exp, use_sympy=False)
        is_sympy = compare_math_results(pred, exp, use_sympy=True)

        if is_strict:
            strict_pass += 1
        if is_sympy:
            sympy_pass += 1

        if not is_strict and is_sympy:
            newly_accepted.append({
                "index": idx,
                "problem_idx": item.get("problem_idx", idx),
                "predicted": pred,
                "expected": exp,
            })

        per_item_strict.append(is_strict)
        per_item_sympy.append(is_sympy)

        if (idx + 1) % 25 == 0 or (idx + 1) == total:
            print(f"[{filepath.name}] Progress: {idx + 1}/{total} evaluated (Strict: {strict_pass}, SymPy: {sympy_pass}, Delta: +{sympy_pass - strict_pass})", flush=True)

    strict_acc = (strict_pass / total) * 100.0 if total else 0.0
    sympy_acc = (sympy_pass / total) * 100.0 if total else 0.0

    print(f"\n=======================================================", flush=True)
    print(f"Rescore Report: {filepath.name}", flush=True)
    print(f"Total Problems: {total}", flush=True)
    print(f"Strict v1.2 Exact/Float Match: {strict_pass}/{total} ({strict_acc:.2f}%)", flush=True)
    print(f"Upgraded SymPy Equivalence:   {sympy_pass}/{total} ({sympy_acc:.2f}%)", flush=True)
    print(f"Grader Syntax Delta:          +{sympy_pass - strict_pass} problems (+{sympy_acc - strict_acc:.2f}%)", flush=True)
    print(f"Newly Accepted Count:         {len(newly_accepted)}", flush=True)
    print(f"=======================================================", flush=True)

    if newly_accepted:
        audit_file = REPO_ROOT / "logs" / f"newly_accepted_{filepath.stem}.json"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        audit_file.write_text(json.dumps(newly_accepted, indent=2), encoding="utf-8")
        print(f"Saved {len(newly_accepted)} newly accepted items to: {audit_file}", flush=True)

    return {
        "filepath": str(filepath),
        "total": total,
        "strict_passed": strict_pass,
        "strict_accuracy_pct": round(strict_acc, 2),
        "sympy_passed": sympy_pass,
        "sympy_accuracy_pct": round(sympy_acc, 2),
        "newly_accepted_count": len(newly_accepted),
        "per_item_strict": per_item_strict,
        "per_item_sympy": per_item_sympy,
    }


def mcnemar_test(file_a: Path, file_b: Path, use_sympy: bool = False):
    """Compute 2x2 contingency table and McNemar test between two matched runs."""
    res_a = rescore_math500_file(file_a)
    res_b = rescore_math500_file(file_b)

    key = "per_item_sympy" if use_sympy else "per_item_strict"
    list_a = res_a.get(key, [])
    list_b = res_b.get(key, [])

    if len(list_a) != len(list_b):
        print(f"[ERROR] Cannot run paired McNemar test: unequal lengths ({len(list_a)} vs {len(list_b)})")
        return

    # a: Pass in both, b: Pass in A, Fail in B, c: Fail in A, Pass in B, d: Fail in both
    n_00 = 0  # Fail in both
    n_01 = 0  # Fail in A, Pass in B (B gained)
    n_10 = 0  # Pass in A, Fail in B (A gained / B regressed)
    n_11 = 0  # Pass in both

    for a, b in zip(list_a, list_b):
        if a and b:
            n_11 += 1
        elif a and not b:
            n_10 += 1
        elif not a and b:
            n_01 += 1
        else:
            n_00 += 1

    total = len(list_a)
    print(f"\n--- Paired McNemar Contingency Table ({'SymPy' if use_sympy else 'Strict'}) ---")
    print(f"Run A: {file_a.name}")
    print(f"Run B: {file_b.name}")
    print(f"Both Passed:              {n_11}")
    print(f"Both Failed:              {n_00}")
    print(f"Run A Passed, Run B Failed: {n_10} (Regressions in B)")
    print(f"Run A Failed, Run B Passed: {n_01} (Gains in B)")
    net_gain = n_01 - n_10
    print(f"Net Gain (B - A):         {net_gain:+d} problems ({net_gain/total*100:+.2f}%)")

    # McNemar chi-square with continuity correction: (|b - c| - 1)^2 / (b + c)
    b_c = n_10 + n_01
    if b_c > 0:
        chi2 = (abs(n_10 - n_01) - 1) ** 2 / b_c
        print(f"McNemar Chi-Square (corr): {chi2:.4f}")
        # Approx p-value from chi-square distribution with 1 df
        import scipy.stats
        try:
            p_val = 1.0 - scipy.stats.chi2.cdf(chi2, df=1)
            print(f"p-value:                   {p_val:.4e}")
            if p_val < 0.05:
                print("Result is STATISTICALLY SIGNIFICANT at alpha = 0.05")
            else:
                print("Result is NOT statistically significant at alpha = 0.05")
        except Exception:
            pass
    print("-------------------------------------------------------")


def main():
    parser = argparse.ArgumentParser(description="Rescore MATH-500 test reports with strict and SymPy checkers")
    parser.add_argument("files", nargs="+", help="Report JSON files to rescore")
    parser.add_argument("--compare", action="store_true", help="Run paired McNemar test between two files")
    parser.add_argument("--sympy", action="store_true", help="Use SymPy for comparison table")
    args = parser.parse_args()

    if args.compare and len(args.files) >= 2:
        mcnemar_test(Path(args.files[0]), Path(args.files[1]), use_sympy=args.sympy)
    else:
        for f in args.files:
            rescore_math500_file(Path(f))


if __name__ == "__main__":
    main()
