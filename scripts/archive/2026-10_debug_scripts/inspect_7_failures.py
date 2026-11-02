import json
import sys
sys.path.append('.')
from pathlib import Path
from scripts.run_concept_arc import compute_grid_diff, analyze_symbolic_invariants

failing = [
    'CleanUp/CleanUp1.json',
    'ExtendToBoundary/ExtendToBoundary1.json',
    'HorizontalVertical/HorizontalVertical1.json',
    'Order/Order1.json',
    'SameDifferent/SameDifferent1.json',
    'TopBottom2D/TopBottom2D1.json',
    'TopBottom3D/TopBottom3D1.json',
]

base = Path('data/benchmarks/ConceptARC/corpus')
for rel in failing:
    p = base / rel
    t = json.load(open(p))
    inv = analyze_symbolic_invariants(t['train'])
    print('==============================')
    print('TASK:', rel)
    print('Shape preserving:', inv.is_shape_preserving)
    print('Pixel count conserved:', inv.is_pixel_count_conserved)
    print('Pixels only added:', inv.is_pixels_only_added)
    print('Hollow objects:', inv.has_hollow_objects)
    print('High symmetry:', inv.has_high_symmetry)
    for idx, ex in enumerate(t['train']):
        diff = compute_grid_diff(ex['input'], ex['output'])
        print(f'Train {idx+1} diff: {diff}')
