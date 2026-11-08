import json

out_lines = []
for model in ['gemma-4-e4b', 'gemma-4-e2b']:
    path = f'logs/test_reports/action_hallucination_{model}_t06_100.json'
    d = json.loads(open(path, encoding='utf-8').read())
    temptations = [r for r in d['results'] if r['category'] == 'temptation']
    out_lines.append(f"\n{'='*30} {model.upper()} ({len(temptations)} temptations) {'='*30}")
    for r in temptations:
        comp = r['completion'].replace('\n', ' ')
        out_lines.append(f"[{r['id']}] Verb: {r['verb']}")
        out_lines.append(f"  Prompt:     {r['prompt']}")
        out_lines.append(f"  Completion: {comp}")

with open("logs/test_reports/temptation_inspections.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))

print("Wrote logs/test_reports/temptation_inspections.txt")
