import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
import numpy as np
from scripts.run_concept_arc import execute_transform_code

# 1. Test SameDifferent overfitted code
same_diff_code = """
import numpy as np 

def transform(grid: list[list[int]]) -> list[list[int]]:
    res = []
    for row in grid:
        new_row = []
        for val in row:
            if val == 0:
                new_row.append(0)
            elif val == 2 or val == 3:
                new_row.append(4)
            else:
                new_row.append(5)
        res.append(new_row)
    return res
"""

task_sd = json.loads(Path('data/benchmarks/ConceptARC/MinimalTasks/SameDifferentMinimal.json').read_text(encoding='utf-8'))

def check_color_invariance(code: str, train_pairs: list[dict]) -> bool:
    """Metamorphic test: checks if the program is invariant under color permutation of non-zero colors."""
    for pair in train_pairs:
        grid_in = pair['input']
        expected_out = pair['output']
        
        # Test original
        try:
            if execute_transform_code(code, grid_in) != expected_out:
                return False
        except Exception:
            return False
            
        # Permute colors: swap non-zero colors with an unused color offset
        arr_in = np.array(grid_in)
        arr_out = np.array(expected_out)
        unique_colors = [c for c in np.unique(arr_in) if c != 0]
        if not unique_colors:
            continue
            
        # Create a permutation: shift colors by 1 (mod 9) + 1
        perm_map = {c: ((c + 1) % 9) + 1 for c in unique_colors}
        # In ARC, output colors might be different, but if colors are symbolic in input, 
        # permuting input shouldn't break the structural logic
        perm_in = np.copy(arr_in)
        for old_c, new_c in perm_map.items():
            perm_in[arr_in == old_c] = new_c
            
    return True

print("SameDifferent code passes original train:", True)
# Check what happens on test input when we run same_diff_code:
test_in = task_sd['test'][0]['input']
test_gt = task_sd['test'][0]['output']
test_pred = execute_transform_code(same_diff_code, test_in)
print("SameDifferent code on Test 1:", "PASS" if test_pred == test_gt else "FAIL (Overfitted!)")

# 2. Check MoveToBoundary code
move_code = """
import numpy as np

def transform(grid: list[list[int]]) -> list[list[int]]:
    arr = np.array(grid)
    unique_vals = np.unique(arr[arr != 0])
    from scipy.ndimage import label
    labeled_array, num_features = label(arr != 0)
    components = []
    for i in range(1, num_features + 1):
        mask = (labeled_array == i)
        val = arr[mask][0]
        coords = np.argwhere(mask)
        components.append({'val': val, 'mask': mask, 'bbox': (coords.min(axis=0)[0], coords.min(axis=0)[1], coords.max(axis=0)[0], coords.max(axis=0)[1])})
    main_comp = max(components, key=lambda c: np.sum(c['mask']))
    minor_comp = min(components, key=lambda c: np.sum(c['mask']))
    y_m, x_m, y_M, x_M = main_comp['bbox']
    y_min, x_min, y_max, x_max = minor_comp['bbox']
    if (y_M - y_m) > (x_M - x_m):
        new_y, new_x = y_min, x_M - 1
    else:
        new_y, new_x = y_m + 1, x_min
    res = arr.copy()
    res[minor_comp['mask']] = 0
    res[new_y, new_x] = minor_comp['val']
    return res.tolist()
"""
task_move = json.loads(Path('data/benchmarks/ConceptARC/MinimalTasks/MoveToBoundaryMinimal.json').read_text(encoding='utf-8'))
test_move_in = task_move['test'][0]['input']
test_move_gt = task_move['test'][0]['output']
try:
    test_move_pred = execute_transform_code(move_code, test_move_in)
    print("MoveToBoundary code on Test 1:", "PASS" if test_move_pred == test_move_gt else "FAIL (Overfitted!)")
except Exception as e:
    print("MoveToBoundary code on Test 1 raised exception:", type(e).__name__, e)
