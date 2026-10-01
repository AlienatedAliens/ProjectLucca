import json
import statistics
from pathlib import Path

REPORTS_DIR = Path("logs/test_reports")
f_319 = REPORTS_DIR / "checkpoint_math500_v1.3-empty-feedback-heldout-400.json"
f_a = REPORTS_DIR / "reprompt_variant_stub_108.json"
f_b = REPORTS_DIR / "reprompt_variant_clean_108.json"
f_c = REPORTS_DIR / "reprompt_variant_stripped_108.json"

d_319 = {x["idx"]: x for x in json.loads(f_319.read_text(encoding="utf-8")) if x.get("feedback_triggered")}
res_a = {x["idx"]: x for x in json.loads(f_a.read_text(encoding="utf-8"))}
res_b = {x["idx"]: x for x in json.loads(f_b.read_text(encoding="utf-8"))}
res_c = {x["idx"]: x for x in json.loads(f_c.read_text(encoding="utf-8"))}

print("=== 1. SANITY CHECK: VARIANT A vs 319 BASELINE (108 items) ===")
corr_319 = sum(1 for x in d_319.values() if x["passed"])
corr_a = sum(1 for x in res_a.values() if x["passed"])
print(f"319 run correct on 108: {corr_319}")
print(f"Variant A correct on 108: {corr_a}")

diffs_a_319 = []
for idx in sorted(d_319.keys()):
    p_319 = d_319[idx]["passed"]
    p_a = res_a[idx]["passed"]
    if p_319 != p_a:
        diffs_a_319.append((idx, p_319, p_a))
print(f"Differences count: {len(diffs_a_319)}")
for idx, p3, pa in diffs_a_319:
    print(f"Idx {idx:03d}: 319={p3} -> A={pa}")

print("\n=== 2. THREE-WAY SUMMARY TABLE ===")
def get_stats(name, data):
    corr = sum(1 for x in data.values() if x["passed"])
    equiv = 274 + corr
    t2_lats = [x["turn2_latency_s"] for x in data.values()]
    mean_lat = statistics.mean(t2_lats)
    med_lat = statistics.median(t2_lats)
    t2_toks = [x["turn2_tokens"] for x in data.values()]
    mean_tok = statistics.mean(t2_toks)
    empty_rate = sum(1 for x in data.values() if x.get("turn2_empty_or_no_code", False)) / len(data) * 100
    tot_lats = [x.get("llm_latency_s", 0) for x in data.values()]
    mean_tot_lat = statistics.mean(tot_lats)
    return {
        "name": name,
        "corr": corr,
        "equiv": equiv,
        "mean_t2_lat": mean_lat,
        "med_t2_lat": med_lat,
        "mean_tok": mean_tok,
        "empty_rate": empty_rate,
        "mean_tot_lat": mean_tot_lat
    }

stats_a = get_stats("Variant A (stub)", res_a)
stats_b = get_stats("Variant B (clean)", res_b)
stats_c = get_stats("Variant C (stripped)", res_c)

print(f"| Variant | Correct on 108 | Equiv Full-400 (274+score) | Mean T2 Lat (s) | Med T2 Lat (s) | Mean T2 Tok | T2 Empty/No-Code Rate | Mean Tot Lat (s) |")
for s in [stats_a, stats_b, stats_c]:
    print(f"| {s['name']} | {s['corr']}/108 ({s['corr']/108*100:.1f}%) | {s['equiv']}/400 ({s['equiv']/400*100:.1f}%) | {s['mean_t2_lat']:.2f}s | {s['med_t2_lat']:.2f}s | {s['mean_tok']:.1f} | {s['empty_rate']:.1f}% | {s['mean_tot_lat']:.2f}s |")

print("\n=== 3. PAIRED FLIPS ===")
def compare_variants(name1, d1, name2, d2):
    gained = []
    lost = []
    for idx in sorted(d1.keys()):
        p1 = d1[idx]["passed"]
        p2 = d2[idx]["passed"]
        if not p1 and p2:
            gained.append(idx)
        elif p1 and not p2:
            lost.append(idx)
    net = len(gained) - len(lost)
    print(f"{name1} -> {name2}: Gained {len(gained)}, Lost {len(lost)}, Net {net:+d}")
    print(f"  Gained ({len(gained)}): {gained}")
    print(f"  Lost ({len(lost)}): {lost}")

compare_variants("A (stub)", res_a, "B (clean)", res_b)
compare_variants("A (stub)", res_a, "C (stripped)", res_c)
compare_variants("B (clean)", res_b, "C (stripped)", res_c)

print("\n=== 4. VARIANT C SPECIFIC METRICS ===")
c_stripped_empty = sum(1 for x in res_c.values() if x.get("stripped_empty", False))
c_comments_removed = [x.get("comment_lines_removed", 0) for x in res_c.values()]
mean_comments_removed = statistics.mean(c_comments_removed)
print(f"stripped_empty count: {c_stripped_empty}/108")
print(f"Mean comment lines removed: {mean_comments_removed:.1f} (Total: {sum(c_comments_removed)})")

print("\n=== 5. RECOVERY AUDIT OF 10 NON-EARLY-ABORT LOSSES ===")
losses_10 = [2, 24, 129, 180, 183, 233, 248, 282, 302, 311]
for idx in losses_10:
    p_319 = d_319.get(idx, {}).get("passed", False)
    pa = res_a.get(idx, {}).get("passed", False)
    pb = res_b.get(idx, {}).get("passed", False)
    pc = res_c.get(idx, {}).get("passed", False)
    print(f"Idx {idx:03d} | 319: {p_319} | A (stub): {pa} | B (clean): {pb} | C (stripped): {pc}")

print("\n=== 6. DEEP DIVE: 6 DIFFERING ITEMS BETWEEN 319 AND VARIANT A ===")
for idx, p3, pa in diffs_a_319:
    b = d_319[idx]
    a = res_a[idx]
    print(f"--- Idx {idx:03d} (319={p3} -> A={pa}) ---")
    print(f"  Expected: {b['expected_ans']}")
    print(f"  319 Pred: '{b.get('predicted_ans')}'")
    print(f"  A Pred:   '{a.get('predicted_ans')}'")
    print(f"  A T2 Finish: {a['turn2_finish_reason']} | T2 Tok: {a['turn2_tokens']} | T2 Lat: {a['turn2_latency_s']}s")

