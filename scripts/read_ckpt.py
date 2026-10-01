import json

p = 'logs/test_reports/checkpoint_math500_v1.3-feedback-16k-heldout-400.json'
try:
    res = json.load(open(p, encoding='utf-8'))
    total = len(res)
    passed = sum(1 for r in res if r.get('passed'))
    print(f"Completed: {total} / 400")
    print(f"Passed: {passed} / {total} ({passed/total*100:.2f}%)")
    fails = [r for r in res if not r.get('passed')]
    print(f"Total Fails so far: {len(fails)}")
    for f in fails:
        print(f"  Item {f['idx']} ({f['subject']} L{f['level']}):")
        print(f"    ExitCode: {f.get('exit_code')}")
        print(f"    Pred:     {f.get('predicted_ans')}")
        print(f"    Expected: {f.get('expected_ans')}")
        print(f"    Stderr:   {f.get('stderr', '')[:80]}")
        print(f"    CodeLen:  {len(f.get('generated_code', ''))}")
except Exception as e:
    print("Error:", e)
