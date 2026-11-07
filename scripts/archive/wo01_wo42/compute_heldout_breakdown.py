import json

raw_data = [
    json.loads(line)
    for line in open("data/benchmarks/math_fresh_heldout_500.jsonl", encoding="utf-8")
][:100]
d_r1 = json.load(
    open("logs/test_reports/checkpoint_math500_e4b-heldout-routed_strict_posthoc.json")
)
d_p2 = json.load(
    open("logs/test_reports/checkpoint_math500_e4b-p2-cap2048_strict_posthoc.json")
)

by_subject: dict[str, dict[str, int]] = {}
by_level: dict[str, dict[str, int]] = {}

for item, r1_res, p2_res in zip(raw_data, d_r1, d_p2, strict=True):
    subj = item.get("subject", "unknown")
    lvl = item.get("level", "unknown")
    r1_pass = r1_res.get("strict_pass", False)
    p2_pass = p2_res.get("strict_pass", False)

    if subj not in by_subject:
        by_subject[subj] = {"total": 0, "r1": 0, "p2": 0}
    by_subject[subj]["total"] += 1
    if r1_pass:
        by_subject[subj]["r1"] += 1
    if p2_pass:
        by_subject[subj]["p2"] += 1

    if lvl not in by_level:
        by_level[lvl] = {"total": 0, "r1": 0, "p2": 0}
    by_level[lvl]["total"] += 1
    if r1_pass:
        by_level[lvl]["r1"] += 1
    if p2_pass:
        by_level[lvl]["p2"] += 1

print("=== HELD-OUT PER-LEVEL BREAKDOWN (Strict CAS) ===")
for lvl, v in sorted(by_level.items()):
    t = v["total"]
    r1_pct = v["r1"] / t * 100
    p2_pct = v["p2"] / t * 100
    r1_c = v["r1"]
    p2_c = v["p2"]
    delta = r1_pct - p2_pct
    print(
        f"{lvl} (n={t:2d}): R1={r1_c:2d}/{t:2d} ({r1_pct:5.1f}%) | "
        f"P2={p2_c:2d}/{t:2d} ({p2_pct:5.1f}%) | delta={delta:+5.1f}pp"
    )

print("\n=== HELD-OUT PER-SUBJECT BREAKDOWN (Strict CAS) ===")
for subj, v in sorted(by_subject.items()):
    t = v["total"]
    r1_pct = v["r1"] / t * 100
    p2_pct = v["p2"] / t * 100
    r1_c = v["r1"]
    p2_c = v["p2"]
    delta = r1_pct - p2_pct
    print(
        f"{subj:25s} (n={t:2d}): R1={r1_c:2d}/{t:2d} ({r1_pct:5.1f}%) | "
        f"P2={p2_c:2d}/{t:2d} ({p2_pct:5.1f}%) | delta={delta:+5.1f}pp"
    )
