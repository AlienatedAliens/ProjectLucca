import json
from pathlib import Path

p1 = Path('logs/test_reports/checkpoint_math500_v1.3-feedback-16k-heldout-400.json')
p2 = Path('logs/test_reports/checkpoint_math500_v1.3-feedback-16k-heldout-remaining-120.json')

d1 = json.loads(p1.read_text(encoding='utf-8'))
d2 = json.loads(p2.read_text(encoding='utf-8'))

print(f"Part 1 items: {len(d1)}")
print(f"Part 2 items: {len(d2)}")

combined = d1 + d2
print(f"Combined total items: {len(combined)}")

passed_count = sum(1 for x in combined if x.get('passed'))
accuracy = passed_count / len(combined)
print(f"Total passed: {passed_count}/{len(combined)} ({accuracy*100:.2f}%)")

# Subject breakdown
subjects = {}
for item in combined:
    s = item.get('subject', 'Unknown')
    if s not in subjects:
        subjects[s] = {'total': 0, 'passed': 0}
    subjects[s]['total'] += 1
    if item.get('passed'):
        subjects[s]['passed'] += 1

print("\n--- Subject Breakdown ---")
for s, stats in sorted(subjects.items()):
    pct = stats['passed'] / stats['total'] * 100
    print(f"{s:25s}: {stats['passed']:3d}/{stats['total']:3d} ({pct:5.1f}%)")

out_path = Path('logs/test_reports/final_math500_v1.3_heldout_400_aggregate.json')
out_path.write_text(json.dumps({
    'total': len(combined),
    'passed': passed_count,
    'accuracy': accuracy,
    'subjects': subjects,
    'items': combined
}, indent=2), encoding='utf-8')
print(f"\nSaved aggregate report to: {out_path}")
