import json
from pathlib import Path

ckpt_path = Path("logs/test_reports/checkpoint_math500_v1.3-ablation-no-injection-heldout-400.json")
base_path = Path("logs/test_reports/v1.3/checkpoint_math500_v1.2-baseline-heldout-400.json")
fb_path = Path("logs/test_reports/final_math500_v1.3_heldout_400_aggregate.json")

cur = json.loads(ckpt_path.read_text(encoding="utf-8"))
base = json.loads(base_path.read_text(encoding="utf-8"))
fb = json.loads(fb_path.read_text(encoding="utf-8"))["items"]

print(f"=== TOTAL PASS COUNTS (400 items) ===")
c_pass = sum(1 for x in cur if x.get("passed"))
b_pass = sum(1 for x in base if x.get("passed"))
f_pass = sum(1 for x in fb if x.get("passed"))

print(f"Ablation Run (no injection): {c_pass}/400 ({c_pass/400*100:.2f}%)")
print(f"v1.2 Baseline:              {b_pass}/400 ({b_pass/400*100:.2f}%)")
print(f"v1.3 Aggregate:             {f_pass}/400 ({f_pass/400*100:.2f}%)")

# Deltas
gained_vs_v12 = [i+1 for i, (c, b) in enumerate(zip(cur, base)) if not b.get("passed") and c.get("passed")]
lost_vs_v12   = [i+1 for i, (c, b) in enumerate(zip(cur, base)) if b.get("passed") and not c.get("passed")]

gained_vs_v13 = [i+1 for i, (c, f) in enumerate(zip(cur, fb)) if not f.get("passed") and c.get("passed")]
lost_vs_v13   = [i+1 for i, (c, f) in enumerate(zip(cur, fb)) if f.get("passed") and not c.get("passed")]

print(f"\n=== VS v1.2 BASELINE (258/400) ===")
print(f"Gained (+{len(gained_vs_v12)}): {gained_vs_v12}")
print(f"Lost   (-{len(lost_vs_v12)}): {lost_vs_v12}")
print(f"Net Delta vs v1.2: +{len(gained_vs_v12) - len(lost_vs_v12)} ({c_pass - b_pass})")

print(f"\n=== VS v1.3 AGGREGATE (253/400) ===")
print(f"Gained (+{len(gained_vs_v13)}): {gained_vs_v13}")
print(f"Lost   (-{len(lost_vs_v13)}): {lost_vs_v13}")
print(f"Net Delta vs v1.3: +{len(gained_vs_v13) - len(lost_vs_v13)} ({c_pass - f_pass})")

# Resolution of the 60 lost problems
lost_60 = [8, 24, 25, 37, 39, 41, 50, 51, 54, 71, 74, 80, 85, 87, 94, 98, 102, 109, 110, 111, 120, 124, 126, 127, 138, 145, 152, 153, 181, 190, 193, 204, 205, 210, 212, 217, 229, 231, 233, 234, 236, 258, 274, 287, 289, 295, 303, 311, 333, 339, 359, 365, 373, 376, 381, 383, 384, 395, 398, 399]
recovered = [idx for idx in lost_60 if cur[idx-1].get("passed")]
still_lost = [idx for idx in lost_60 if not cur[idx-1].get("passed")]

print(f"\n=== RESOLUTION OF THE 60 LOST PROBLEMS ===")
print(f"Total in list: {len(lost_60)}")
print(f"Recovered by disabling injection: {len(recovered)}/60 ({len(recovered)/60*100:.1f}%)")
print(f"Recovered IDs ({len(recovered)}): {recovered}")
print(f"Still Failing ({len(still_lost)}/60): {still_lost}")

# Feedback loop metrics in this run
fb_trig = sum(1 for x in cur if x.get("feedback_triggered"))
fb_succ = sum(1 for x in cur if x.get("feedback_succeeded"))
print(f"\n=== 2-TURN FEEDBACK IN CURRENT RUN ===")
print(f"Feedback Triggered: {fb_trig}")
print(f"Feedback Succeeded: {fb_succ} ({fb_succ/fb_trig*100:.1f}% recovery)")

# Subject breakdown
subjects = {}
for x in cur:
    s = x.get("subject", "Unknown")
    subjects.setdefault(s, {"total": 0, "passed": 0})
    subjects[s]["total"] += 1
    if x.get("passed"):
        subjects[s]["passed"] += 1

print(f"\n=== SUBJECT BREAKDOWN ===")
for s, st in sorted(subjects.items()):
    pct = st["passed"] / st["total"] * 100
    p = st["passed"]
    t = st["total"]
    print(f"{s:25s}: {p:3d}/{t:3d} ({pct:5.1f}%)")
