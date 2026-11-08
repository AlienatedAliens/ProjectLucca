import json

with open('logs/test_reports/checkpoint_math500_v1.2-baseline-heldout-400.json', 'r', encoding='utf-8') as f:
    base = json.load(f)
with open('logs/test_reports/final_math500_v1.3_heldout_400_aggregate.json', 'r', encoding='utf-8') as f:
    fb = json.load(f)

base_items = base if isinstance(base, list) else base.get('results', [])
fb_items = fb.get('items', [])

print(f"Base items: {len(base_items)}, FB items: {len(fb_items)}")

base_pass = sum(1 for x in base_items if x.get('passed'))
fb_pass = sum(1 for x in fb_items if x.get('passed'))
print(f"Base passed: {base_pass} ({base_pass/len(base_items)*100:.2f}%)")
print(f"FB passed: {fb_pass} ({fb_pass/len(fb_items)*100:.2f}%)")

fb_fixes = []
fb_regressions = []
fb_triggered_count = 0
fb_succeeded_count = 0

for b, f in zip(base_items, fb_items):
    b_p = b.get('passed')
    f_p = f.get('passed')
    trig = f.get('feedback_triggered', False)
    succ = f.get('feedback_succeeded', False)
    if trig:
        fb_triggered_count += 1
    if succ:
        fb_succeeded_count += 1
    if not b_p and f_p:
        fb_fixes.append((b, f))
    elif b_p and not f_p:
        fb_regressions.append((b, f))

print(f"Total Feedback Triggered in FB Run: {fb_triggered_count}")
print(f"Total Feedback Succeeded in FB Run: {fb_succeeded_count}")
print(f"Net flips: +{len(fb_fixes)} gained, -{len(fb_regressions)} lost")
print("\nSample gains (+):")
for b, f in fb_fixes[:8]:
    idx = f.get('idx')
    print(f"  Idx {idx}: Base pred={b.get('predicted_ans')!r} (exit {b.get('exit_code')}) -> FB pred={f.get('predicted_ans')!r} (trig={f.get('feedback_triggered')}) | exp={f.get('expected_ans')!r}")

print("\nSample losses (-):")
for b, f in fb_regressions[:8]:
    idx = f.get('idx')
    print(f"  Idx {idx}: Base pred={b.get('predicted_ans')!r} -> FB pred={f.get('predicted_ans')!r} (trig={f.get('feedback_triggered')}) | exp={f.get('expected_ans')!r}")
