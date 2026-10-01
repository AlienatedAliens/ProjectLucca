import json
import sys
sys.path.insert(0, '.')
from scripts.run_modern_2024_benchmarks import compare_math_results

with open('logs/test_reports/final_math500_v1.3_heldout_400_aggregate.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

for x in d['items'][:15]:
    idx = x['idx']
    passed = x['passed']
    pred = x.get('predicted_ans', '')
    exp = x.get('expected_ans', '')
    sym_eval = compare_math_results(pred, exp, use_sympy=True)
    print(f"Idx {idx:3d} | passed={str(passed):5s} | sympy={str(sym_eval):5s} | pred={pred!r} | exp={exp!r}")
