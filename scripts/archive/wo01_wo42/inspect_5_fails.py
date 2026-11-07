import json

data = json.load(open('logs/test_reports/modern_benchmarks_2024_20260930T014420Z_v1.3-design-30-feedback.json', encoding='utf-8'))
results = data['benchmarks']['math500']['results']
fails = [r for r in results if not r['passed']]

print(f"Total Failures: {len(fails)}")
for i, f in enumerate(fails, 1):
    print("=" * 60)
    print(f"FAILURE #{i}: Task {f.get('idx')} | Subj: {f.get('subject')} (Level {f.get('level')})")
    print(f"Problem: {f.get('problem')}")
    print(f"Expected: {f.get('expected_ans')}")
    print(f"Predicted: '{f.get('predicted_ans')}'")
    print(f"Failure Class: {f.get('failure_class')}")
    print(f"Exit Code: {f.get('exit_code')}")
    print(f"Feedback Triggered: {f.get('feedback_triggered')} | Succeeded: {f.get('feedback_succeeded')}")
    print(f"Stderr: {f.get('stderr', '').strip()[:200]}")
    code = f.get('generated_code', '')
    print(f"Code (lines={len(code.splitlines())}):\n{code}")
