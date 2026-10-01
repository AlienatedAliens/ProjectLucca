import json
from pathlib import Path

r1 = json.loads(Path('logs/test_reports/v1.3/checkpoint_math500_v1.3-baseline-heldout-400.json').read_text(encoding='utf-8'))
r2 = json.loads(Path('logs/test_reports/checkpoint_math500_v1.3-baseline-heldout-400-noise-run2.json').read_text(encoding='utf-8'))

p1_count = sum(1 for x in r1 if x.get("passed"))
p2_count = sum(1 for x in r2 if x.get("passed"))

print(f"Run 1 Total: {len(r1)} | Passed: {p1_count} ({p1_count/len(r1)*100:.2f}%)")
print(f"Run 2 Total: {len(r2)} | Passed: {p2_count} ({p2_count/len(r2)*100:.2f}%)")

flips_1_to_0 = []
flips_0_to_1 = []
identical_predictions = 0
different_predictions = 0

for i, (a, b) in enumerate(zip(r1, r2)):
    idx = i + 1
    p1 = a.get("passed", False)
    p2 = b.get("passed", False)
    pred1 = a.get("predicted_ans", "")
    pred2 = b.get("predicted_ans", "")
    
    if pred1 == pred2:
        identical_predictions += 1
    else:
        different_predictions += 1
        
    if p1 and not p2:
        flips_1_to_0.append((idx, pred1, pred2, a.get("expected_ans")))
    elif not p1 and p2:
        flips_0_to_1.append((idx, pred1, pred2, a.get("expected_ans")))

print(f"\n=== RUN-TO-RUN NOISE AUDIT ===")
print(f"Identical Predictions across 400 items: {identical_predictions}/400 ({identical_predictions/400*100:.2f}%)")
print(f"Different Predictions across 400 items: {different_predictions}/400 ({different_predictions/400*100:.2f}%)")
print(f"Pass -> Fail Flips: {len(flips_1_to_0)}")
for idx, p1, p2, exp in flips_1_to_0:
    print(f"  Idx {idx}: R1={p1!r} -> R2={p2!r} | Exp={exp!r}")
print(f"Fail -> Pass Flips: {len(flips_0_to_1)}")
for idx, p1, p2, exp in flips_0_to_1:
    print(f"  Idx {idx}: R1={p1!r} -> R2={p2!r} | Exp={exp!r}")
print(f"Total verdict flips: {len(flips_1_to_0) + len(flips_0_to_1)}")

# Check feedback loop activity in Run 2 vs Run 1
fb_trig1 = sum(1 for x in r1 if x.get("feedback_triggered"))
fb_succ1 = sum(1 for x in r1 if x.get("feedback_succeeded"))
fb_trig2 = sum(1 for x in r2 if x.get("feedback_triggered"))
fb_succ2 = sum(1 for x in r2 if x.get("feedback_succeeded"))

print(f"\n=== 2-TURN FEEDBACK COMPARISON ===")
print(f"Run 1 Feedback Triggered: {fb_trig1} | Succeeded: {fb_succ1} ({fb_succ1/fb_trig1*100:.1f}%)")
print(f"Run 2 Feedback Triggered: {fb_trig2} | Succeeded: {fb_succ2} ({fb_succ2/fb_trig2*100:.1f}%)")
