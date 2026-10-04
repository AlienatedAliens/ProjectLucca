import json

data = json.load(open("logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_routed_heldout_100.json", encoding="utf-8"))
res = data["results"]
total = len(res)
strict = sum(1 for r in res if r["strict_pass"])
lenient = sum(1 for r in res if r["lenient_pass"])
trunc = sum(1 for r in res if r.get("truncated", False))
avg_tok = sum(r["completion_tokens"] for r in res) / total
avg_lat = sum(r["latency_s"] for r in res) / total

print(f"=== HELD-OUT RESULTS (n={total}) ===")
print(f"Strict Pass: {strict}/{total} ({strict/total:.1%})")
print(f"Lenient Pass: {lenient}/{total} ({lenient/total:.1%})")
print(f"Truncations: {trunc}/{total} ({trunc/total:.1%})")
print(f"Mean Tokens: {avg_tok:.1f}")
print(f"Mean Latency: {avg_lat:.2f}s")

by_level = {}
for r in res:
    lvl = r.get("level", "unknown")
    if lvl not in by_level:
        by_level[lvl] = {"total": 0, "strict": 0, "lenient": 0}
    by_level[lvl]["total"] += 1
    if r["strict_pass"]:
        by_level[lvl]["strict"] += 1
    if r["lenient_pass"]:
        by_level[lvl]["lenient"] += 1

print("\n=== BY LEVEL ===")
for lvl in sorted(by_level.keys(), key=lambda x: str(x)):
    d = by_level[lvl]
    print(f"Level {lvl}: Strict {d['strict']}/{d['total']} ({d['strict']/d['total']:.1%}), Lenient {d['lenient']}/{d['total']} ({d['lenient']/d['total']:.1%})")

by_subj = {}
for r in res:
    subj = r.get("subject", "unknown")
    if subj not in by_subj:
        by_subj[subj] = {"total": 0, "strict": 0, "lenient": 0}
    by_subj[subj]["total"] += 1
    if r["strict_pass"]:
        by_subj[subj]["strict"] += 1
    if r["lenient_pass"]:
        by_subj[subj]["lenient"] += 1

print("\n=== BY SUBJECT ===")
for subj in sorted(by_subj.keys()):
    d = by_subj[subj]
    print(f"{subj}: Strict {d['strict']}/{d['total']} ({d['strict']/d['total']:.1%}), Lenient {d['lenient']}/{d['total']} ({d['lenient']/d['total']:.1%})")
