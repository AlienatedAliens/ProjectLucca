import json

data = json.load(open("data/eval/true_audited_100.json", encoding="utf-8"))
for r in data["results"]:
    if r["id"] in [4, 15, 17, 84, 86]:
        print("=" * 60)
        print(f"Test #{r['id']:03d}: {r['prompt']}")
        print(f"Auto-Passed: {r['auto_passed']} | Real Verdict: {r['real_verdict']}")
        print(f"Critique: {r['audit_critique']}")
        print("-" * 60)
        print(r["response_text"])
        print()
