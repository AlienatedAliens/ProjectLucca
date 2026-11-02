import json
from pathlib import Path

names = [
    '009d5c81', '00dbd492', '03560426', '0692e18c',
    '08573cc6', '0a1d4ef5', '0becf7df', '0a2355a6'
]

for name in names:
    p = Path(f"data/benchmarks/arc_agi_1/{name}.json")
    with open(p) as f:
        d = json.load(f)
    print(f"=== {name} (train={len(d['train'])}) ===")
    ex = d['train'][0]
    in_h, in_w = len(ex['input']), len(ex['input'][0])
    out_h, out_w = len(ex['output']), len(ex['output'][0])
    print(f"Shape: ({in_h}, {in_w}) -> ({out_h}, {out_w})")
    in_colors = sorted(set(c for row in ex['input'] for c in row))
    out_colors = sorted(set(c for row in ex['output'] for c in row))
    print(f"In colors: {in_colors} | Out colors: {out_colors}")
