import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scipy.stats import binomtest
from scripts.run_modern_2024_benchmarks import compare_math_strict, compare_math_lenient

def main() -> None:
    p2_data = json.load(open('logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_p2_heldout_cap2048_100.json'))
    r1_data = json.load(open('logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_routed_heldout_100.json'))

    p2_res = p2_data.get('results', p2_data)
    r1_res = r1_data.get('results', r1_data)

    p2_strict_correct = []
    r1_strict_correct = []
    p2_lenient_correct = []
    r1_lenient_correct = []

    for i in range(100):
        p = p2_res[i]
        r = r1_res[i]
        assert p['item_id'] == r['item_id'], f"Mismatch at item {i}: {p['item_id']} vs {r['item_id']}"
        assert p['ground_truth'] == r['ground_truth'], f"GT mismatch at item {i}"
        
        gt = str(p['ground_truth'])
        
        p2_s = compare_math_strict(p['predicted_ans'], gt)
        r1_s = compare_math_strict(r['predicted_ans'], gt)
        p2_strict_correct.append(p2_s)
        r1_strict_correct.append(r1_s)
        
        p2_l = compare_math_lenient(p['predicted_ans'], gt)
        r1_l = compare_math_lenient(r['predicted_ans'], gt)
        p2_lenient_correct.append(p2_l)
        r1_lenient_correct.append(r1_l)

    def mcnemar(a_correct, b_correct, name_a, name_b):
        a_only = sum(1 for a, b in zip(a_correct, b_correct) if a and not b)
        b_only = sum(1 for a, b in zip(a_correct, b_correct) if not a and b)
        both = sum(1 for a, b in zip(a_correct, b_correct) if a and b)
        neither = sum(1 for a, b in zip(a_correct, b_correct) if not a and not b)
        total_disc = a_only + b_only
        p_val = binomtest(min(a_only, b_only), total_disc, 0.5).pvalue if total_disc > 0 else 1.0
        print(f"=== {name_a} vs {name_b} ===")
        print(f"{name_a} Acc: {sum(a_correct)}/{len(a_correct)} ({sum(a_correct)/len(a_correct)*100:.1f}%)")
        print(f"{name_b} Acc: {sum(b_correct)}/{len(b_correct)} ({sum(b_correct)/len(b_correct)*100:.1f}%)")
        print(f"Both correct: {both}, Neither: {neither}")
        print(f"{name_a} only (b): {a_only}, {name_b} only (c): {b_only}")
        print(f"Discordant pairs (b:c): {a_only} : {b_only}, Exact binomial p-value: {p_val:.4f}")
        return {
            "name_a": name_a,
            "name_b": name_b,
            "acc_a": sum(a_correct),
            "acc_b": sum(b_correct),
            "both": both,
            "neither": neither,
            "b": a_only,
            "c": b_only,
            "p_val": p_val
        }

    mcnemar(p2_strict_correct, r1_strict_correct, "Held-Out P2 (PAL @ 2k)", "Held-Out R1 (Thinking @ 6k) [Strict]")
    print()
    mcnemar(p2_lenient_correct, r1_lenient_correct, "Held-Out P2 (PAL @ 2k)", "Held-Out R1 (Thinking @ 6k) [Lenient]")

if __name__ == "__main__":
    main()
