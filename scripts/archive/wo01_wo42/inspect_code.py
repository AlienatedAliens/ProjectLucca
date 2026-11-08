import json

p = 'logs/test_reports/checkpoint_math500_v1.3-feedback-16k-heldout-400.json'
res = json.load(open(p, encoding='utf-8'))
for r in res:
    if r['idx'] in (9, 20):
        print(f"=== ITEM {r['idx']} GENERATED CODE ===")
        code = r.get('generated_code', '')
        print("Total chars:", len(code))
        print("Lines count:", len(code.splitlines()))
        print("First 15 lines:")
        for l in code.splitlines()[:15]:
            print("  ", l)
        print("Last 15 lines:")
        for l in code.splitlines()[-15:]:
            print("  ", l)
