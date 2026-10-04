"""
Generates the comprehensive PAL_OFF_FACTORIAL_REPORT_100.md from all experimental run JSONs.
Ensures:
1. All models and arms (dev and held-out) are cleanly represented.
2. McNemar is ONLY run on paired items within the identical split.
3. Cross-split comparisons use independent two-proportion z-tests and Wilson CIs.
4. Discordant pairs are explicitly labeled: 'Arm A only (b) : Arm B only (c)'.
"""

import json
import math
import re
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("logs/test_reports/pal_off_ablation")

def exact_binomial_p(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    half_p = sum(math.comb(n, i) * (0.5 ** n) for i in range(k + 1))
    return min(1.0, 2.0 * half_p)

def two_proportion_z_test(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    p1 = x1 / n1
    p2 = x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    p_val = 2 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2))))
    return z, p_val

def get_item_idx(iid: str) -> int:
    m = re.findall(r"\d+", iid)
    return int(m[-1]) if m else 0

def run_paired_mcnemar(results_a: list[dict], results_b: list[dict]):
    map_a = {get_item_idx(r["item_id"]): bool(r.get("strict_pass")) for r in results_a}
    map_b = {get_item_idx(r["item_id"]): bool(r.get("strict_pass")) for r in results_b}
    common = sorted(set(map_a.keys()) & set(map_b.keys()))

    both_pass = 0
    both_fail = 0
    a_only_b = 0
    b_only_c = 0

    for idx in common:
        pa = map_a[idx]
        pb = map_b[idx]
        if pa and pb: both_pass += 1
        elif not pa and not pb: both_fail += 1
        elif pa and not pb: a_only_b += 1
        elif not pa and pb: b_only_c += 1

    total_discordant = a_only_b + b_only_c
    k = min(a_only_b, b_only_c)
    p_val = exact_binomial_p(k, total_discordant)
    return {
        "n_paired": len(common),
        "both_pass": both_pass,
        "both_fail": both_fail,
        "a_only_b": a_only_b,
        "b_only_c": b_only_c,
        "p_val": p_val,
        "sig": p_val < 0.05,
    }

def generate_report():
    files = list(BASE_DIR.glob("*.json"))
    runs = {}
    for f in sorted(files):
        if "checkpoint" in f.name:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if "results" in d and len(d["results"]) > 0:
                runs[f.stem] = d
        except Exception:
            pass

    lines = []
    lines.append("# Project Lucca: Factorial PAL-Off Model-Scale Ablation Report")
    lines.append("**Confidence Level:** 95% Wilson Score CI | **Sample Size:** $n=100$ per Cell\n")

    lines.append("## 1. Factorial Performance Scorecard (Model Size x Scaffold Arm x Split)\n")
    lines.append("| Model | Benchmark | Split | Arm & Cap | Strict Acc [95% Wilson CI] | Lenient Acc [95% Wilson CI] | Trunc (%) | Avg Tok | Latency (s) |")
    lines.append("| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |")

    # Order of presentation: 12B, E4B, E2B
    model_order = ["gemma-4-12b", "gemma-4-e4b", "gemma-4-e2b"]
    
    def sort_key(name):
        d = runs[name]
        m = d.get("model_label", "")
        bm = d.get("benchmark", "")
        split = d.get("split", "dev")
        arm = d.get("arm", "")
        m_idx = model_order.index(m) if m in model_order else 99
        return (m_idx, bm, split, arm, name)

    for stem in sorted(runs.keys(), key=sort_key):
        d = runs[stem]
        m = d.get("model_label", "unknown")
        bm = d.get("benchmark", "unknown")
        split = d.get("split", "dev")
        arm = d.get("arm", "").upper()
        
        # Determine cap label
        cap_note = ""
        if "cap4096" in stem: cap_note = " @ 4k"
        elif "cap2048" in stem: cap_note = " @ 2k"
        elif "think6144" in stem: cap_note = " @ 6k"
        elif arm == "R1" and m != "gemma-4-12b": cap_note = " @ 4k"
        elif arm in ("P1", "P2"): cap_note = " @ 1k"
        elif arm == "R0": cap_note = " @ 1.5k"

        st_acc = f"{d.get('strict_accuracy', 0):.1f}%"
        st_ci = d.get("strict_ci_95", [0, 0])
        st_ci_str = f"[{st_ci[0]:.1f}%, {st_ci[1]:.1f}%]"

        len_acc = f"{d.get('lenient_accuracy', 0):.1f}%"
        len_ci = d.get("lenient_ci_95", [0, 0])
        len_ci_str = f"[{len_ci[0]:.1f}%, {len_ci[1]:.1f}%]"

        trunc = f"{d.get('truncation_rate_pct', 0):.1f}%"
        tok = f"{d.get('avg_tokens_per_item', 0):.0f}"
        lat = f"{d.get('avg_latency_s', 0):.2f}s"

        lines.append(f"| **{m}** | {bm} | {split} | **{arm}{cap_note}** | {st_acc} {st_ci_str} | {len_acc} {len_ci_str} | {trunc} | {tok} | {lat} |")

    lines.append("\n---\n")
    lines.append("## 2. Paired McNemar Statistical Appendix (Strict Accuracy)\n")
    lines.append("Evaluated strictly on identical problems within the same split ($n=100$). Column headers explicitly indicate direction of discordance.\n")
    lines.append("| Model | Split | Comparison (Arm A vs Arm B) | Arm A Acc | Arm B Acc | Delta (pp) | Arm A Only (b) | Arm B Only (c) | Exact p-Value | Significant ($p < 0.05$) |")
    lines.append("| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    # Important paired comparisons
    paired_configs = [
        # 12B Dev
        ("gemma-4-12b", "dev", "gemma-4-12b_math500_r0_100", "gemma-4-12b_math500_p2_100", "R0 @ 1.5k", "P2 @ 1k"),
        ("gemma-4-12b", "dev", "gemma-4-12b_math500_r0_100", "gemma-4-12b_math500_r1_100", "R0 @ 1.5k", "R1 @ 6k"),
        # 12B Heldout
        ("gemma-4-12b", "heldout", "gemma-4-12b_math500_r0_heldout_cap4096_100", "gemma-4-12b_math500_p2_heldout_cap2048_100", "R0 @ 4k", "P2 @ 2k"),

        # E4B Dev
        ("gemma-4-e4b", "dev", "gemma-4-e4b_math500_p2_cap2048_100", "gemma-4-e4b_math500_p2_100", "P2 @ 2k", "P2 @ 1k"),
        ("gemma-4-e4b", "dev", "gemma-4-e4b_math500_r1_100", "gemma-4-e4b_math500_p2_cap2048_100", "R1 @ 4k", "P2 @ 2k"),
        ("gemma-4-e4b", "dev", "gemma-4-e4b_math500_r0_cap4096_100", "gemma-4-e4b_math500_r0_100", "R0 @ 4k", "R0 @ 1.5k"),
        # E4B Heldout
        ("gemma-4-e4b", "heldout", "gemma-4-e4b_math500_routed_heldout_100", "gemma-4-e4b_math500_p2_heldout_cap2048_100", "R1 @ 6k", "P2 @ 2k"),
        ("gemma-4-e4b", "heldout", "gemma-4-e4b_math500_p2_heldout_cap2048_100", "gemma-4-e4b_math500_r0_heldout_cap4096_100", "P2 @ 2k", "R0 @ 4k"),
        ("gemma-4-e4b", "heldout", "gemma-4-e4b_math500_routed_heldout_100", "gemma-4-e4b_math500_r0_heldout_cap4096_100", "R1 @ 6k", "R0 @ 4k"),

        # E2B Dev
        ("gemma-4-e2b", "dev", "gemma-4-e2b_math500_p2_cap2048_100", "gemma-4-e2b_math500_p2_100", "P2 @ 2k", "P2 @ 1k"),
        ("gemma-4-e2b", "dev", "gemma-4-e2b_math500_r1_100", "gemma-4-e2b_math500_p2_cap2048_100", "R1 @ 4k", "P2 @ 2k"),
        ("gemma-4-e2b", "dev", "gemma-4-e2b_math500_r0_cap4096_100", "gemma-4-e2b_math500_r0_100", "R0 @ 4k", "R0 @ 1.5k"),
        # E2B Heldout
        ("gemma-4-e2b", "heldout", "gemma-4-e2b_math500_r1_heldout_think6144_100", "gemma-4-e2b_math500_p2_heldout_cap2048_100", "R1 @ 6k", "P2 @ 2k"),
        ("gemma-4-e2b", "heldout", "gemma-4-e2b_math500_p2_heldout_cap2048_100", "gemma-4-e2b_math500_r0_heldout_cap4096_100", "P2 @ 2k", "R0 @ 4k"),
        ("gemma-4-e2b", "heldout", "gemma-4-e2b_math500_r1_heldout_think6144_100", "gemma-4-e2b_math500_r0_heldout_cap4096_100", "R1 @ 6k", "R0 @ 4k"),
    ]

    for mod, split, key_a, key_b, lbl_a, lbl_b in paired_configs:
        if key_a in runs and key_b in runs:
            mc = run_paired_mcnemar(runs[key_a]["results"], runs[key_b]["results"])
            acc_a = runs[key_a]["strict_accuracy"]
            acc_b = runs[key_b]["strict_accuracy"]
            delta = acc_a - acc_b
            sig_str = "**YES**" if mc["sig"] else "NO"
            lines.append(f"| {mod} | {split} | **{lbl_a} vs {lbl_b}** | {acc_a:.1f}% | {acc_b:.1f}% | {delta:+.1f} | {mc['a_only_b']} | {mc['b_only_c']} | {mc['p_val']:.4e} | {sig_str} |")

    lines.append("\n---\n")
    lines.append("## 3. Cross-Split Generalization Analysis (Dev vs Held-Out)\n")
    lines.append("Because problems differ between Dev and Held-Out, McNemar is invalid. We report independent two-proportion z-tests and Wilson 95% CIs:\n")
    lines.append("| Model | Arm | Dev Strict Acc [95% CI] | Held-Out Strict Acc [95% CI] | Delta (pp) | z-Score | Two-Tailed p-Value | Generalization Assessment |")
    lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |")

    cross_split_configs = [
        ("gemma-4-12b", "R0 (Direct)", "gemma-4-12b_math500_r0_100", "gemma-4-12b_math500_r0_heldout_cap4096_100"),
        ("gemma-4-12b", "P2 (PAL)", "gemma-4-12b_math500_p2_100", "gemma-4-12b_math500_p2_heldout_cap2048_100"),
        ("gemma-4-e4b", "R1 (Thinking)", "gemma-4-e4b_math500_r1_100", "gemma-4-e4b_math500_routed_heldout_100"),
        ("gemma-4-e4b", "P2 (PAL)", "gemma-4-e4b_math500_p2_cap2048_100", "gemma-4-e4b_math500_p2_heldout_cap2048_100"),
        ("gemma-4-e2b", "R1 (Thinking)", "gemma-4-e2b_math500_r1_100", "gemma-4-e2b_math500_r1_heldout_think6144_100"),
        ("gemma-4-e2b", "P2 (PAL)", "gemma-4-e2b_math500_p2_cap2048_100", "gemma-4-e2b_math500_p2_heldout_cap2048_100"),
    ]

    for mod, arm_lbl, dev_key, heldout_key in cross_split_configs:
        if dev_key in runs and heldout_key in runs:
            d_dev = runs[dev_key]
            d_h = runs[heldout_key]
            x_dev = d_dev["strict_passed"]
            n_dev = len(d_dev["results"])
            x_h = d_h["strict_passed"]
            n_h = len(d_h["results"])

            z, p = two_proportion_z_test(x_dev, n_dev, x_h, n_h)
            delta = d_h["strict_accuracy"] - d_dev["strict_accuracy"]
            
            ci_dev = f"[{d_dev['strict_ci_95'][0]:.1f}%, {d_dev['strict_ci_95'][1]:.1f}%]"
            ci_h = f"[{d_h['strict_ci_95'][0]:.1f}%, {d_h['strict_ci_95'][1]:.1f}%]"

            verdict = "No statistically detectable difference" if p > 0.05 else ("Significant drop" if delta < 0 else "Significant lift")
            lines.append(f"| {mod} | {arm_lbl} | {d_dev['strict_accuracy']:.1f}% {ci_dev} | {d_h['strict_accuracy']:.1f}% {ci_h} | {delta:+.1f} | {z:.3f} | {p:.4f} | {verdict} |")

    report_text = "\n".join(lines)
    out_file = BASE_DIR / "PAL_OFF_FACTORIAL_REPORT_100.md"
    out_file.write_text(report_text, encoding="utf-8")
    print(f"Report written to {out_file}")

if __name__ == "__main__":
    generate_report()
