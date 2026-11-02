import json
import httpx
from pathlib import Path
from lucca.reasoning.spatial_dsl import (
    summarize_grid_objects,
    find_objects,
    dominant_object,
    count_objects,
    count_cells,
    column_heights,
    row_widths,
    complete_symmetry,
    denoise,
    majority_filter,
    fill_holes,
    crop,
    paste,
    bbox_of_all,
    crop_to_content,
    draw_line,
    move_until_contact,
)
from lucca.sandbox.preflight import extract_python_code
from lucca.reasoning.cost import python_ast_cost

def compute_grid_diff(in_grid, out_grid):
    h_in, w_in = len(in_grid), len(in_grid[0]) if in_grid else 0
    h_out, w_out = len(out_grid), len(out_grid[0]) if out_grid else 0
    if (h_in, w_in) != (h_out, w_out):
        return f"Dimensions changed: {h_in}x{w_in} -> {h_out}x{w_out}"
    changes = []
    for r in range(h_in):
        for c in range(w_in):
            if in_grid[r][c] != out_grid[r][c]:
                changes.append(f"({r},{c}): {in_grid[r][c]}->{out_grid[r][c]}")
    if not changes:
        return "No cell changes (identical)"
    if len(changes) > 25:
        return f"{len(changes)} cells modified across grid"
    return "Changed cells: " + ", ".join(changes)

client = httpx.Client(timeout=60.0)

for task_name in ["CleanUpMinimal", "CompleteShapeMinimal", "OrderMinimal", "SameDifferentMinimal"]:
    path = Path(f"data/benchmarks/ConceptARC/MinimalTasks/{task_name}.json")
    task = json.loads(path.read_text())
    print("\n" + "="*70)
    print(f"PROBING: {task_name}")
    print("="*70)
    
    train_desc = ""
    perceptual_manifest = ""
    for idx, ex in enumerate(task["train"]):
        train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"
        in_summary = summarize_grid_objects(ex["input"])
        out_summary = summarize_grid_objects(ex["output"])
        diff_summary = compute_grid_diff(ex["input"], ex["output"])
        perceptual_manifest += (
            f"Example {idx+1} Input Objects: {in_summary}\n"
            f"Example {idx+1} Output Objects: {out_summary}\n"
            f"Example {idx+1} Diffs: {diff_summary}\n\n"
        )
        
    abduction_prompt = (
        "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples, object structures, and coordinate diffs.\n"
        "Core Inductive Priors:\n"
        "- Color integers are arbitrary symbolic tokens. Never deduce rules based on color arithmetic.\n"
        "- The rule is governed by abstract spatial relations: relative positioning, motion toward boundary, shape identity/equality, enclosure, symmetry, order, or size.\n\n"
        f"{train_desc}"
        f"Perceptual Object Manifest & Diffs:\n{perceptual_manifest}"
        "Formulate an Operational Hypothesis stating the exact transformation rule across 3 concrete dimensions:\n"
        "1. Selection: Which objects/regions are selected or filtered? (e.g. largest/dominant object, small noise components, objects with specific shape/property, or columns/rows)\n"
        "2. Operation: What spatial transformation occurs? (e.g. sort columns by height, complete symmetry across an axis, fill enclosed holes, move object until contact, or extract bounding box)\n"
        "3. Output Colors: What specific output colors are assigned or retained for each region?\n"
        "Be precise, concise (3-4 sentences total), and algorithmic."
    )
    
    resp = client.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json={"messages": [{"role": "user", "content": abduction_prompt}], "temperature": 0.1, "max_tokens": 400, "chat_template_kwargs": {"enable_thinking": False}}
    )
    abducted = resp.json()["choices"][0]["message"]["content"]
    print("--- ABDUCTED ---")
    print(abducted)
    
    synthesis_prompt = (
        "Write a concise Python function `transform(grid: list[list[int]]) -> list[list[int]]` implementing this rule:\n"
        f"{abducted}\n\n"
        "Available helpers:\n"
        "- Objects: `find_objects(grid, background=0)` (has .color, .dimensions (height, width), .bbox (min_r, min_c, max_r, max_c), .area, .is_hollow, .coords), `count_objects(grid)`, `count_cells(grid, color=None)`, `dominant_object(grid)`, `unique_colors(grid)`\n"
        "- Ordering: `sort_objects(objects, key='height'|'width'|'area'|'min_r'|'min_c', reverse=False)`, `column_heights(grid)`, `row_widths(grid)`\n"
        "- Morphology: `denoise(grid, min_size=2)`, `majority_filter(grid, radius=1)`, `fill_holes(grid, color)`, `flood_fill(grid, r, c, color)`\n"
        "- Geometry & Symmetry: `complete_symmetry(grid, axis='vertical'|'horizontal')`, `crop(grid, min_r, min_c, max_r, max_c)`, `crop_to_content(grid)`, `bbox_of_all(grid)`, `paste(dest, src, r, c)`\n"
        "- Lines & Motion: `draw_line(grid, r1, c1, r2, c2, color)`, `move_until_contact(grid, obj, dr, dc)`, `rot90(grid, k=1)`, `flip_h(grid)`, `flip_v(grid)`\n\n"
        "Rules:\n"
        "- Start immediately with `def transform(grid):`.\n"
        "- NO comments inside the code.\n\n"
        f"{train_desc}"
    )
    
    resp2 = client.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json={"messages": [{"role": "user", "content": synthesis_prompt}], "temperature": 0.2, "max_tokens": 1024, "chat_template_kwargs": {"enable_thinking": False}}
    )
    raw_code = resp2.json()["choices"][0]["message"]["content"]
    code = extract_python_code(raw_code)
    print("--- SYNTHESIZED CODE ---")
    print(code)
    
    exec_globals = {
        "find_objects": find_objects,
        "dominant_object": dominant_object,
        "count_objects": count_objects,
        "count_cells": count_cells,
        "column_heights": column_heights,
        "row_widths": row_widths,
        "complete_symmetry": complete_symmetry,
        "denoise": denoise,
        "majority_filter": majority_filter,
        "fill_holes": fill_holes,
        "crop": crop,
        "paste": paste,
        "bbox_of_all": bbox_of_all,
        "crop_to_content": crop_to_content,
        "draw_line": draw_line,
        "move_until_contact": move_until_contact,
    }
    try:
        exec(code, exec_globals)
        fn = exec_globals["transform"]
        train_ok = True
        for i, ex in enumerate(task["train"]):
            pred = fn(ex["input"])
            if pred != ex["output"]:
                train_ok = False
                print(f"Train {i+1} FAIL: pred={pred[:2]}... want={ex['output'][:2]}...")
            else:
                print(f"Train {i+1} PASS")
        if train_ok:
            print(">>> ALL TRAIN PASSED! Testing on test set...")
            for j, tex in enumerate(task["test"]):
                tpred = fn(tex["input"])
                print(f"Test {j+1} {'PASS' if tpred == tex['output'] else 'FAIL'}")
    except Exception as e:
        print(f"EXEC EXCEPTION: {type(e).__name__}: {e}")
