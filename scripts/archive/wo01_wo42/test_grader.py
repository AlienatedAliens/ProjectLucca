import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_modern_2024_benchmarks import compare_math_results

test_cases = [
    ('(a + 5)*(b + 2)', r'(a+5)(b+2)'),
    ('4/3', r'\frac43'),
    ('106', r'106^\circ'),
    ('15.0', r'15\mbox{ cm}^2'),
    ('18.90', r'\$18.90'),
    ('8*n**2 + 4*n + 1', r'8n^2 + 4n + 1'),
    ('639/40', r'\frac{639}{40}'),
    ('2', r'2'),
    ('121', r'121'),
    ('-1', r'-1'),
    ('7/2', r'\frac{7}{2}'),
    ('1/4', r'0.25'),
    ('0.25', r'\frac{1}{4}'),
    ('y = 2x + 3', r'y = 2x + 3'),
    ('-2, 1', r'1, -2'),
]

all_passed = True
for p, e in test_cases:
    res = compare_math_results(p, e, use_sympy=True)
    if not res:
        all_passed = False
    print(f"Pred: {p:22s} | Exp: {e:22s} -> {res}")

print("\nALL CASES PASSED:", all_passed)
