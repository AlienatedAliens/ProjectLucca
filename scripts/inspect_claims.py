import json
with open('data/master_claims_list.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

print(f"Total: {len(items)}")
for idx, item in enumerate(items, 1):
    print(f"[{idx:03d}] | {item['doc']} | Line {item['line']} | {item['claim']} | {item['status']}")

