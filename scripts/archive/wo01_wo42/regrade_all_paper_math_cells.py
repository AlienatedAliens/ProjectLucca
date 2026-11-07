import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_modern_2024_benchmarks import compare_math_strict, compare_math_lenient
DIR = REPO_ROOT / "logs" / "test_reports" / "pal_off_ablation"

files = [
    ("12B R0 (1k cap)", "gemma-4-12b_math500_r0_100.json"),
    ("12B P2 (1k cap)", "gemma-4-12b_math500_p2_100.json"),
    ("12B R1 (6k cap)", "gemma-4-12b_math500_r1_100.json"),
    ("E4B R0 (1.5k cap)", "gemma-4-e4b_math500_r0_100.json"),
    ("E4B R1 (4k cap)", "gemma-4-e4b_math500_r1_100.json"),
    ("E4B P2 (2k cap)", "gemma-4-e4b_math500_p2_cap2048_100.json"),
    ("E4B Held-Out R1 (6k)", "gemma-4-e4b_math500_routed_heldout_100.json"),
    ("E4B Held-Out P2 (2k)", "gemma-4-e4b_math500_p2_heldout_cap2048_100.json"),
    ("E2B R0 (1.5k cap)", "gemma-4-e2b_math500_r0_100.json"),
    ("E2B P2 (1k cap)", "gemma-4-e2b_math500_p2_100.json"),
    ("E2B P2 (2k cap)", "gemma-4-e2b_math500_p2_cap2048_100.json"),
    ("E2B P3 (Think+Code)", "gemma-4-e2b_math500_p3_100.json"),
    ("E2B R1 (4k cap)", "gemma-4-e2b_math500_r1_100.json"),
    ("E2B R1 (6k cap)", "gemma-4-e2b_math500_r1_think6144_100.json"),
]

print(f"{'Cell Description':<25} | {'Reported File':<42} | {'Strict':<8} | {'Lenient':<8} | {'Discrep'}")
print("-" * 105)

for desc, fname in files:
    fpath = DIR / fname
    if not fpath.exists():
        print(f"{desc:<25} | {fname:<42} | MISSING")
        continue
    raw = json.loads(fpath.read_text(encoding="utf-8"))
    items = raw["results"] if isinstance(raw, dict) and "results" in raw else raw
    
    strict_count = 0
    lenient_count = 0
    for itm in items:
        pred = str(itm.get("predicted_ans", "")).strip()
        exp = str(itm.get("expected_ans") or itm.get("ground_truth", "")).strip()
        if compare_math_strict(pred, exp):
            strict_count += 1
        if compare_math_lenient(pred, exp):
            lenient_count += 1
            
    total = len(items)
    discrep = lenient_count - strict_count
    print(f"{desc:<25} | {fname:<42} | {strict_count}/{total:<4} ({strict_count/total*100:.1f}%) | {lenient_count}/{total:<4} ({lenient_count/total*100:.1f}%) | +{discrep} pp")
