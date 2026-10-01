import glob
import json

files = sorted(glob.glob('logs/test_reports/*v1.2-baseline-heldout-400.json'))
if not files:
    print("No report found.")
    exit(1)

data = json.load(open(files[-1], encoding='utf-8'))
m = data['benchmarks']['math500']
results = m['results']
total = m['total']
passed = m['passed']

print(f"=== MATH-500 Held-Out 400 Baseline Summary ===")
print(f"Config Label: {data.get('config_label')}")
print(f"Context Size: {data.get('context_size')}")
print(f"Total Problems: {total}")
print(f"Strict Passed: {passed} ({m.get('accuracy_pct')}%)")
print(f"Total Elapsed Time: {m.get('elapsed_s')}s ({m.get('elapsed_s')/60:.1f} min)")

by_subj = {}
by_lvl = {}
failures = {
    'runtime_crash': 0,
    'equivalence_format_miss': 0,
    'prose_slip': 0,
    'genuine_derivation_miss': 0
}

for r in results:
    s = r.get('subject', 'Unknown')
    l = r.get('level', 0)
    p = r.get('passed', False)
    by_subj.setdefault(s, [0, 0])
    by_subj[s][1] += 1
    if p:
        by_subj[s][0] += 1

    by_lvl.setdefault(l, [0, 0])
    by_lvl[l][1] += 1
    if p:
        by_lvl[l][0] += 1

    if not p:
        stderr = r.get('stderr') or ''
        exit_code = r.get('exit_code', 0)
        pred = str(r.get('predicted_ans') or '').strip()
        exp = str(r.get('expected_ans') or '').strip()
        if exit_code != 0 or stderr:
            failures['runtime_crash'] += 1
        elif not pred:
            failures['prose_slip'] += 1
        elif any(c in exp for c in ('\\frac', '\\sqrt', '\\pi', 'pmatrix', 'Interval', '\\cup', 'circ', '\\', 'm^2', 'cm^2', '$')):
            failures['equivalence_format_miss'] += 1
        else:
            failures['genuine_derivation_miss'] += 1

print("\nAccuracy by Subject:")
for s in sorted(by_subj.keys()):
    p_cnt, t_cnt = by_subj[s]
    print(f"  {s:26s}: {p_cnt:3d} / {t_cnt:3d} ({p_cnt/t_cnt*100:5.1f}%)")

print("\nAccuracy by Difficulty Level:")
for l in sorted(by_lvl.keys()):
    p_cnt, t_cnt = by_lvl[l]
    print(f"  Level {l}: {p_cnt:3d} / {t_cnt:3d} ({p_cnt/t_cnt*100:5.1f}%)")

print(f"\nFailure Classification Breakdown (Total Failures: {total - passed}):")
for f, count in failures.items():
    pct = count / (total - passed) * 100
    print(f"  {f:26s}: {count:3d} ({pct:5.1f}%)")

lenient_pass = passed + failures['equivalence_format_miss']
print(f"\nLenient Accuracy (recovering formatting misses): {lenient_pass} / {total} ({lenient_pass/total*100:.2f}%)")
