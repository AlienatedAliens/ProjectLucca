import json

with open('data/audit_full_results.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

# Fix C040 verdict to CONTRADICTION
for it in items:
    if it['id'] == 'C040':
        it['verdict'] = 'CONTRADICTION'
        it['method'] = 'Code inspection `src/lucca/senses/asr.py` vs doc'
        it['raw_output'] = 'Code uses CUDA float16 (commit 70a903c); doc asserts Queued on CPU int8'

with open('data/audit_full_results.json', 'w', encoding='utf-8') as f:
    json.dump(items, f, indent=2)

counts = {}
for it in items:
    v = it['verdict']
    counts[v] = counts.get(v, 0) + 1

print("Verified final counts:", counts)
