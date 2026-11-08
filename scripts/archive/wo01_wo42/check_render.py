import json

with open('data/audit_full_results.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

print(f"Total: {len(items)}")

# Check formatting
p0_lines = [f"[{it['id']}] | {it['doc']} | Line {it['line']} | {it['claim']} | {it['status']}" for it in items]
p1_rows = [f"| {it['id']} | {it['claim']} | {it['method']} | {it['raw_output']} | {it['verdict']} |" for it in items]

p0_text = "\n".join(p0_lines)
p1_text = "| ID | Claim | Command/Method | Raw Output | Verdict |\n|---|---|---|---|---|\n" + "\n".join(p1_rows)

total = p0_text + "\n\n" + p1_text
print("Total length in chars:", len(total))
print("Total lines:", len(total.splitlines()))

