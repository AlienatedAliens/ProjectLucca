import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

report_path = Path("logs/test_reports/modern_benchmarks_2024_20261001T192212Z_v1.3-final-fresh-500.json")
data = json.loads(report_path.read_text(encoding="utf-8"))
results = data["benchmarks"]["math500"]["results"]

total = len(results)
passed = sum(1 for r in results if r["passed"])
acc = passed / total

# Wilson score interval 95% (z = 1.95996)
z = 1.95996
p = acc
n = total
denominator = 1 + z**2 / n
center_adj = p + z**2 / (2 * n)
margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
ci_low = (center_adj - margin) / denominator
ci_high = (center_adj + margin) / denominator

print(f"Total: {total}, Passed: {passed}, Accuracy: {acc*100:.2f}%")
print(f"95% Wilson CI: [{ci_low*100:.2f}%, {ci_high*100:.2f}%]")

# Feedback stats
fb_triggered = sum(1 for r in results if r.get("feedback_triggered"))
fb_succeeded = sum(1 for r in results if r.get("feedback_succeeded"))
t1_passed = sum(1 for r in results if r["passed"] and not r.get("feedback_triggered"))
print(f"Turn 1 Passed: {t1_passed} ({t1_passed/total*100:.1f}%)")
print(f"Feedback Triggered: {fb_triggered} ({fb_triggered/total*100:.1f}%)")
print(f"Feedback Recovered: {fb_succeeded} ({fb_succeeded/fb_triggered*100:.1f}% recovery rate)")

# Latency & Tokens
lats = [r["llm_latency_s"] for r in results]
print(f"Mean Latency: {statistics.mean(lats):.2f}s, Median: {statistics.median(lats):.2f}s, P90: {sorted(lats)[int(0.9*len(lats))]:.2f}s")

toks = [r.get("completion_tokens", 0) for r in results if r.get("completion_tokens")]
if toks:
    print(f"Mean Completion Tokens: {statistics.mean(toks):.1f}, Median: {statistics.median(toks)}")

# By Subject
by_subj = defaultdict(lambda: {"total": 0, "passed": 0})
for r in results:
    s = r.get("subject", "unknown")
    by_subj[s]["total"] += 1
    if r["passed"]:
        by_subj[s]["passed"] += 1

print("\n--- By Subject ---")
for s, v in sorted(by_subj.items(), key=lambda x: x[1]["passed"]/x[1]["total"], reverse=True):
    sub_acc = v["passed"] / v["total"] * 100
    print(f"{s:25s}: {v['passed']:3d}/{v['total']:3d} ({sub_acc:5.1f}%)")

# By Level
by_lvl = defaultdict(lambda: {"total": 0, "passed": 0})
for r in results:
    l = r.get("level", "unknown")
    by_lvl[l]["total"] += 1
    if r["passed"]:
        by_lvl[l]["passed"] += 1

print("\n--- By Level ---")
for l, v in sorted(by_lvl.items(), key=lambda x: str(x[0])):
    lvl_acc = v["passed"] / v["total"] * 100
    print(f"Level {l}: {v['passed']:3d}/{v['total']:3d} ({lvl_acc:5.1f}%)")

# Failures breakdown
failures = [r for r in results if not r["passed"]]
print(f"\nTotal Failures: {len(failures)}")
f_classes = defaultdict(int)
for f in failures:
    fc = f.get("failure_class", "unknown")
    f_classes[fc] += 1
for fc, cnt in sorted(f_classes.items(), key=lambda x: -x[1]):
    print(f"{fc:30s}: {cnt:2d} ({cnt/len(failures)*100:5.1f}%)")
