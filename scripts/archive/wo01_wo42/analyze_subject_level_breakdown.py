"""
Full Comparative Subject and Level Breakdown Report Generator.
Computes side-by-side performance across subjects and levels for Dev vs Held-out.
"""

import json
import re
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("logs/test_reports/pal_off_ablation")
DATA_DIR = Path("data/benchmarks")

def load_meta(split: str, samples: int = 100) -> dict[int, dict]:
    file_path = DATA_DIR / ("math_fresh_heldout_500.jsonl" if split == "heldout" else "math500_test.jsonl")
    lines = [json.loads(l) for l in file_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    meta = {}
    for idx, itm in enumerate(lines[:samples], 1):
        subj = itm.get("subject", "unknown").lower().replace(" ", "_")
        lvl = str(itm.get("level", "0")).replace("Level ", "")
        meta[idx] = {"subject": subj, "level": lvl}
    return meta

def parse_run(file_path: Path, meta: dict[int, dict]):
    if not file_path.exists():
        return None
    data = json.loads(file_path.read_text(encoding="utf-8"))
    results = data["results"]
    by_subj = defaultdict(lambda: {"total": 0, "strict": 0, "lenient": 0})
    by_lvl = defaultdict(lambda: {"total": 0, "strict": 0, "lenient": 0})
    item_map = {}

    for r in results:
        iid = r["item_id"]
        m_idx = re.findall(r"\d+", iid)
        idx = int(m_idx[-1]) if m_idx else 0
        m = meta.get(idx, {"subject": "unknown", "level": "0"})
        subj = m["subject"]
        lvl = m["level"]

        sp = bool(r.get("strict_pass", False))
        lp = bool(r.get("lenient_pass", False))

        by_subj[subj]["total"] += 1
        if sp: by_subj[subj]["strict"] += 1
        if lp: by_subj[subj]["lenient"] += 1

        by_lvl[lvl]["total"] += 1
        if sp: by_lvl[lvl]["strict"] += 1
        if lp: by_lvl[lvl]["lenient"] += 1

        item_map[idx] = {"strict": sp, "lenient": lp, "subject": subj, "level": lvl}

    return {
        "strict_acc": data.get("strict_accuracy"),
        "lenient_acc": data.get("lenient_accuracy"),
        "by_subj": dict(by_subj),
        "by_lvl": dict(by_lvl),
        "items": item_map,
    }

def print_discordant_table(run_a, run_b, label_a, label_b, title):
    if not run_a or not run_b:
        print(f"Skipping {title}: missing run files")
        return
    common = sorted(set(run_a["items"].keys()) & set(run_b["items"].keys()))
    a_only = 0
    b_only = 0
    subj_disc = defaultdict(lambda: {"a_only": 0, "b_only": 0, "total": 0})
    lvl_disc = defaultdict(lambda: {"a_only": 0, "b_only": 0, "total": 0})

    for idx in common:
        ia = run_a["items"][idx]
        ib = run_b["items"][idx]
        s = ia["subject"]
        l = ia["level"]
        subj_disc[s]["total"] += 1
        lvl_disc[l]["total"] += 1

        if ia["strict"] and not ib["strict"]:
            a_only += 1
            subj_disc[s]["a_only"] += 1
            lvl_disc[l]["a_only"] += 1
        elif not ia["strict"] and ib["strict"]:
            b_only += 1
            subj_disc[s]["b_only"] += 1
            lvl_disc[l]["b_only"] += 1

    print(f"\n### {title}")
    print(f"- Overall Strict: {label_a} = {run_a['strict_acc']}% | {label_b} = {run_b['strict_acc']}%")
    print(f"- Discordant Pairs: `{label_a}_only (b) = {a_only}` : `{label_b}_only (c) = {b_only}` (Total discordant: {a_only + b_only})")
    print("\n| Subject | Total Items | " + f"{label_a} only (b) | {label_b} only (c) |")
    print("| :--- | :---: | :---: | :---: |")
    for s in sorted(subj_disc.keys()):
        print(f"| `{s}` | {subj_disc[s]['total']} | {subj_disc[s]['a_only']} | {subj_disc[s]['b_only']} |")

    print("\n| Difficulty Level | Total Items | " + f"{label_a} only (b) | {label_b} only (c) |")
    print("| :--- | :---: | :---: | :---: |")
    for l in sorted(lvl_disc.keys(), key=lambda x: int(x) if x.isdigit() else 99):
        print(f"| Level {l} | {lvl_disc[l]['total']} | {lvl_disc[l]['a_only']} | {lvl_disc[l]['b_only']} |")

if __name__ == "__main__":
    dev_meta = load_meta("dev")
    heldout_meta = load_meta("heldout")

    # 1. 12B R0 vs P2 on Dev & Heldout
    r_12b_dev_r0 = parse_run(BASE_DIR / "gemma-4-12b_math500_r0_100.json", dev_meta)
    r_12b_dev_p2 = parse_run(BASE_DIR / "gemma-4-12b_math500_p2_100.json", dev_meta)
    print_discordant_table(r_12b_dev_r0, r_12b_dev_p2, "12B R0", "12B P2", "12B Dev Split: R0 (Direct) vs P2 (PAL)")

    r_12b_h_r0 = parse_run(BASE_DIR / "gemma-4-12b_math500_r0_heldout_cap4096_100.json", heldout_meta)
    r_12b_h_p2 = parse_run(BASE_DIR / "gemma-4-12b_math500_p2_heldout_cap2048_100.json", heldout_meta)
    print_discordant_table(r_12b_h_r0, r_12b_h_p2, "12B R0", "12B P2", "12B Held-Out Split: R0 (Direct) vs P2 (PAL)")

    # 2. E4B R1 vs P2 on Dev & Heldout
    r_e4b_dev_r1 = parse_run(BASE_DIR / "gemma-4-e4b_math500_r1_100.json", dev_meta)
    r_e4b_dev_p2 = parse_run(BASE_DIR / "gemma-4-e4b_math500_p2_cap2048_100.json", dev_meta)
    print_discordant_table(r_e4b_dev_r1, r_e4b_dev_p2, "E4B R1", "E4B P2", "E4B Dev Split: R1 (Thinking) vs P2 (PAL)")

    r_e4b_h_r1 = parse_run(BASE_DIR / "gemma-4-e4b_math500_routed_heldout_100.json", heldout_meta)
    r_e4b_h_p2 = parse_run(BASE_DIR / "gemma-4-e4b_math500_p2_heldout_cap2048_100.json", heldout_meta)
    print_discordant_table(r_e4b_h_r1, r_e4b_h_p2, "E4B R1", "E4B P2", "E4B Held-Out Split: R1 (Thinking) vs P2 (PAL)")

    # 3. E2B R1 vs P2 on Dev & Heldout
    r_e2b_dev_r1 = parse_run(BASE_DIR / "gemma-4-e2b_math500_r1_100.json", dev_meta)
    r_e2b_dev_p2 = parse_run(BASE_DIR / "gemma-4-e2b_math500_p2_cap2048_100.json", dev_meta)
    print_discordant_table(r_e2b_dev_r1, r_e2b_dev_p2, "E2B R1", "E2B P2", "E2B Dev Split: R1 (Thinking) vs P2 (PAL)")

    r_e2b_h_r1 = parse_run(BASE_DIR / "gemma-4-e2b_math500_r1_heldout_think6144_100.json", heldout_meta)
    r_e2b_h_p2 = parse_run(BASE_DIR / "gemma-4-e2b_math500_p2_heldout_cap2048_100.json", heldout_meta)
    print_discordant_table(r_e2b_h_r1, r_e2b_h_p2, "E2B R1", "E2B P2", "E2B Held-Out Split: R1 (Thinking) vs P2 (PAL)")
