import json

p = 'logs/test_reports/modern_benchmarks_2024_20260930T005900Z_v1.3-phase1-extraction-trial.json'
with open(p, 'r', encoding='utf-8') as f:
    d = json.load(f)

results = d['benchmarks']['math500']['results']
print(f"Total problems evaluated: {len(results)}")
empty_code = [r for r in results if not r.get('generated_code', '').strip()]
print(f"Empty generated_code count: {len(empty_code)} / {len(results)}")
print(f"Empty-code rate: {len(empty_code) / len(results) * 100:.1f}%")

print("\n--- Detailed Breakdown ---")
for idx, r in enumerate(results):
    code_len = len(r.get('generated_code', ''))
    exit_c = r.get('exit_code')
    tid = r.get('idx')
    passed = r.get('passed')
    pred = r.get('predicted_ans')
    exp = r.get('expected_ans')
    print(f"Item {idx+1:02d} (task {tid:3d}): Exit={exit_c} | CodeLen={code_len:4d} | Passed={passed} | Pred={pred!r} | Exp={exp!r}")
