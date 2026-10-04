"""
Reproducibility script for 98-item held-out evaluation robustness check.
Recomputes strict and lenient accuracy on the held-out split (math_fresh_heldout_500.jsonl)
excluding items 15 and 73 (zero-indexed indices 14 and 72).
"""

import json
from pathlib import Path

BASE_DIR = Path("logs/test_reports/pal_off_ablation")

HELDOUT_FILES = [
    ("12B Direct R0 @ 4k", BASE_DIR / "gemma-4-12b_math500_r0_heldout_cap4096_100.json"),
    ("12B PAL P2 @ 2k", BASE_DIR / "gemma-4-12b_math500_p2_heldout_cap2048_100.json"),
    ("E4B Routed R1 @ 6k", BASE_DIR / "gemma-4-e4b_math500_routed_heldout_100.json"),
    ("E4B PAL P2 @ 2k", BASE_DIR / "gemma-4-e4b_math500_p2_heldout_cap2048_100.json"),
    ("E4B Direct R0 @ 4k", BASE_DIR / "gemma-4-e4b_math500_r0_heldout_cap4096_100.json"),
    ("E2B Thinking R1 @ 6k", BASE_DIR / "gemma-4-e2b_math500_r1_heldout_think6144_100.json"),
    ("E2B PAL P2 @ 2k", BASE_DIR / "gemma-4-e2b_math500_p2_heldout_cap2048_100.json"),
    ("E2B Direct R0 @ 4k", BASE_DIR / "gemma-4-e2b_math500_r0_heldout_cap4096_100.json"),
]

def main() -> None:
    print(f"{'Arm':<24} | {'100-Item Full':<14} | {'Items 15 & 73':<14} | {'98-Item (Excl 15&73)':<20} | {'Delta':<8}")
    print("-" * 90)

    for label, filepath in HELDOUT_FILES:
        if not filepath.exists():
            print(f"File not found: {filepath}")
            continue

        data = json.loads(filepath.read_text(encoding="utf-8"))
        results = data["results"]
        total_100 = len(results)

        strict_100 = sum(1 for r in results if r.get("strict_pass"))
        lenient_100 = sum(1 for r in results if r.get("lenient_pass"))

        p15_strict = results[14].get("strict_pass", False)
        p73_strict = results[72].get("strict_pass", False)

        res_98 = [r for idx, r in enumerate(results) if idx not in (14, 72)]
        strict_98 = sum(1 for r in res_98 if r.get("strict_pass"))
        lenient_98 = sum(1 for r in res_98 if r.get("lenient_pass"))

        pct_100 = (strict_100 / total_100) * 100.0
        pct_98 = (strict_98 / 98) * 100.0
        delta = pct_98 - pct_100

        p15_str = "T" if p15_strict else "F"
        p73_str = "T" if p73_strict else "F"
        items_str = f"15:{p15_str}, 73:{p73_str}"

        print(f"{label:<24} | {strict_100:>3}/{total_100} ({pct_100:5.1f}%) | {items_str:<14} | {strict_98:>2}/98 ({pct_98:5.1f}%) strict | {delta:+5.1f} pp")

if __name__ == "__main__":
    main()
