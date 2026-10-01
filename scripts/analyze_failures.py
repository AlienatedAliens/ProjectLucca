import json

errors = {}
runtime_crashes = []
with open('logs/telemetry/flow_traces_v1.2_baseline.jsonl', encoding='utf-8') as f:
    for i, line in enumerate(f):
        t = json.loads(line)
        if t.get('verdict') != 'PASS':
            s6 = t.get('stages', {}).get('tank_6_sandbox_turbine', {})
            err = s6.get('stderr', '')
            out = s6.get('output', '')
            comb = err + "\n" + out
            fc = t.get('failure_class', 'unknown')
            errors[fc] = errors.get(fc, 0) + 1
            if 'Error' in comb:
                for l in comb.splitlines():
                    if 'Error:' in l:
                        err_name = l.strip().split(':')[0]
                        runtime_crashes.append(err_name)

print("Failure Classes in Baseline:")
for k, v in sorted(errors.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

from collections import Counter
print("\nTop Python Exceptions in Docker Sandbox:")
for err_type, count in Counter(runtime_crashes).most_common(15):
    print(f"  {err_type}: {count}")
