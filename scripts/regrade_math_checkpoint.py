#!/usr/bin/env python3
"""Step 3: Math Grader with Strict and Lenient Modes & Checkpoint Regrader.

Implements two grading modes per specification:
1. STRICT mode:
   - Normalized string equality or exact symbolic equivalence only.
   - Strictly NO decimal-for-fraction or decimal-for-irrational.
   - No float-eval fallback.
   - Strict ordered elements.
2. LENIENT mode:
   - All v1.3 rules (including float evaluation and SymPy equivalence).
   - Plus new normalizations:
     a) Multiple-choice letters: E vs \\text{(E)}, (E), \\mathbf{E}
     b) Stripped %: 33 vs 33\\% or 33%
     c) Unit labels: 10 vs 10\\;\\text{edges}, \\text{cm}, \\text{dollars}, etc.
     d) Set/list order: -1/12, 1/2 vs \\frac{1}{2}, -\\frac{1}{12}, (-3/4, 3/4) vs \\frac{3}{4}, -\\frac{3}{4}, [-3, 1] vs 1, -3
     e) Matrix rendering: [[1], [7]], Matrix([[-6], [9]]), Matrix([[1/5, 4/5], [0, 1]]) vs \\begin{pmatrix} ... \\end{pmatrix}
     f) Interval rendering: Interval(-oo, -3) vs (-\\infty, -3)

Regrades logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json in BOTH modes.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from lucca.reasoning.stats import wilson_score_interval
from scripts.run_modern_2024_benchmarks import (
    clean_latex_for_sympy,
    compare_intervals,
    compare_matrices_elements,
    compare_math_lenient,
    compare_math_results,
    compare_math_strict,
    compare_unordered_sets,
    evaluate_sympy_equivalence_with_timeout,
    is_decimal_for_fraction_or_irrational,
    normalize_math_str,
    normalize_mc_letter,
    parse_matrix_clean,
    strip_percent,
    strip_unit_labels,
)


# ===========================================================================
# Checkpoint Regrading Function
# ===========================================================================

def regrade_checkpoint(
    checkpoint_path: Path,
    label: str = "v1.3-fresh-500",
) -> dict:
    """Regrade an existing checkpoint in both STRICT and LENIENT modes."""
    print(f"\n=======================================================")
    print(f"Step 3: Post-Hoc Checkpoint Regrade in BOTH Modes")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Label: {label} (post-hoc: grader fixes designed after inspection)")
    print(f"=======================================================\n")

    items = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert len(items) == 500, f"Expected 500 items, got {len(items)}"

    strict_passes = []
    lenient_passes = []
    discrepancies = []

    for idx, item in enumerate(items, 1):
        pred = str(item.get("predicted_ans", "")).strip()
        exp = str(item.get("expected_ans", "")).strip()
        orig_passed = item.get("passed", False)

        is_strict = compare_math_strict(pred, exp)
        is_lenient = compare_math_lenient(pred, exp)

        strict_passes.append(is_strict)
        lenient_passes.append(is_lenient)

        if is_strict != is_lenient or is_lenient != orig_passed:
            discrepancies.append({
                "idx": item.get("idx", idx),
                "predicted": pred,
                "expected": exp,
                "orig_passed": orig_passed,
                "strict_passed": is_strict,
                "lenient_passed": is_lenient,
            })

        if idx % 100 == 0 or idx == len(items):
            print(f"[{idx:03d}/500] Evaluated -> Strict Passes: {sum(strict_passes)}, Lenient Passes: {sum(lenient_passes)}", flush=True)

    total = len(items)
    n_strict = sum(strict_passes)
    n_lenient = sum(lenient_passes)

    ci_strict_low, ci_strict_high = wilson_score_interval(n_strict, total)
    ci_lenient_low, ci_lenient_high = wilson_score_interval(n_lenient, total)

    # Build regraded item records
    strict_items = []
    lenient_items = []
    for item, s_p, l_p in zip(items, strict_passes, lenient_passes):
        item_strict = dict(item)
        item_strict["passed"] = s_p
        item_strict["grader_mode"] = "strict"
        item_strict["grader_label"] = "v1.35-strict-posthoc"
        strict_items.append(item_strict)

        item_lenient = dict(item)
        item_lenient["passed"] = l_p
        item_lenient["grader_mode"] = "lenient"
        item_lenient["grader_label"] = "v1.35-lenient-posthoc"
        lenient_items.append(item_lenient)

    # Save artifacts
    strict_file = REPO_ROOT / "logs" / "test_reports" / f"checkpoint_math500_{label}_strict_posthoc.json"
    lenient_file = REPO_ROOT / "logs" / "test_reports" / f"checkpoint_math500_{label}_lenient_posthoc.json"

    strict_file.write_text(json.dumps(strict_items, indent=2), encoding="utf-8")
    lenient_file.write_text(json.dumps(lenient_items, indent=2), encoding="utf-8")

    print("\n=======================================================")
    print("Post-Hoc Regrade Summary (checkpoint_math500_v1.3-final-fresh-500.json)")
    print(f"Total Problems (n):      {total}")
    print(f"Strict Pass Count:       {n_strict}/{total} ({n_strict/total*100:.2f}%) | Wilson 95% CI: [{ci_strict_low*100:.2f}%, {ci_strict_high*100:.2f}%]")
    print(f"Lenient Pass Count:      {n_lenient}/{total} ({n_lenient/total*100:.2f}%) | Wilson 95% CI: [{ci_lenient_low*100:.2f}%, {ci_lenient_high*100:.2f}%]")
    print(f"Grader Sensitivity Span: {n_strict/total*100:.2f}% – {n_lenient/total*100:.2f}% ({n_lenient - n_strict} problem discrepancy)")
    print(f"Strict Artifact:         {strict_file}")
    print(f"Lenient Artifact:        {lenient_file}")
    print("=======================================================\n")

    return {
        "total": total,
        "strict_passed": n_strict,
        "strict_failed": total - n_strict,
        "strict_acc_pct": round(n_strict / total * 100.0, 2),
        "strict_ci": [round(ci_strict_low * 100, 2), round(ci_strict_high * 100, 2)],
        "lenient_passed": n_lenient,
        "lenient_failed": total - n_lenient,
        "lenient_acc_pct": round(n_lenient / total * 100.0, 2),
        "lenient_ci": [round(ci_lenient_low * 100, 2), round(ci_lenient_high * 100, 2)],
        "strict_artifact": str(strict_file),
        "lenient_artifact": str(lenient_file),
        "discrepancies": discrepancies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Math Grader & Regrader")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default="logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json",
        help="Path to checkpoint JSON file to regrade",
    )
    args = parser.parse_args()

    ckpt_path = REPO_ROOT / args.checkpoint
    if not ckpt_path.exists():
        print(f"Error: checkpoint file not found at {ckpt_path}")
        return 1

    regrade_checkpoint(ckpt_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
