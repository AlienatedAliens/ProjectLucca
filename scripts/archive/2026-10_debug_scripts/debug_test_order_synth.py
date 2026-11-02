import json
import httpx
from lucca.sandbox.preflight import extract_python_code
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
    flood_fill,
    crop,
    paste,
    bbox_of_all,
    crop_to_content,
    draw_line,
    move_until_contact,
    sort_objects,
    unique_colors,
    rot90,
    flip_h,
    flip_v,
    normalize_grid,
    SpatialObject
)

abducted = """1. Selection: The engine identifies the set of all non-zero cells (objects) and treats the grid as a collection of vertical columns.
2. Operation: The engine calculates the height (number of non-zero cells) of each column and reorders the columns such that they are sorted in non-decreasing order from left to right (ascending height). The relative vertical position of the non-zero cells within each column is preserved during this horizontal reordering.
3. Output Colors: The original color of each cell is retained and mapped to its new position based on the sorted column index."""

task = json.loads(open("data/benchmarks/ConceptARC/MinimalTasks/OrderMinimal.json").read())
train_desc = ""
for idx, ex in enumerate(task["train"]):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

synthesis_prompt = (
    "Write a concise Python function `transform(grid: list[list[int]]) -> list[list[int]]` implementing this rule:\n"
    f"{abducted}\n\n"
    "Available helpers:\n"
    "- Objects: `find_objects(grid, background=0)`, `count_objects(grid)`, `count_cells(grid, color=None)`, `dominant_object(grid)`, `unique_colors(grid)`\n"
    "- Ordering: `sort_objects(objects, key=...)`, `column_heights(grid)`, `row_widths(grid)`\n"
    "- Morphology: `denoise(grid, min_size=2)`, `majority_filter(grid, radius=1)`, `fill_holes(grid, color)`, `flood_fill(grid, r, c, color)`\n"
    "- Geometry & Symmetry: `complete_symmetry(grid, axis='vertical'|'horizontal')`, `crop(...)`, `paste(...)`\n\n"
    "Rules:\n"
    "- Start immediately with `def transform(grid):`.\n"
    "- NO comments inside the code.\n\n"
    f"{train_desc}"
)

client = httpx.Client(timeout=60.0)
for temp in [0.15, 0.35, 0.55]:
    print(f"--- TEMP {temp} ---")
    resp = client.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json={"messages": [{"role": "user", "content": synthesis_prompt}], "temperature": temp, "max_tokens": 1024, "chat_template_kwargs": {"enable_thinking": False}}
    )
    raw_code = resp.json()["choices"][0]["message"]["content"]
    code = extract_python_code(raw_code)
    print("CODE:\n", code)
    g = {
        "find_objects": find_objects,
        "dominant_object": dominant_object,
        "count_objects": count_objects,
        "count_cells": count_cells,
        "column_heights": column_heights,
        "row_widths": row_widths,
        "sort_objects": sort_objects,
        "complete_symmetry": complete_symmetry,
        "denoise": denoise,
        "majority_filter": majority_filter,
        "fill_holes": fill_holes,
        "flood_fill": flood_fill,
        "crop": crop,
        "paste": paste,
        "bbox_of_all": bbox_of_all,
        "crop_to_content": crop_to_content,
        "draw_line": draw_line,
        "move_until_contact": move_until_contact,
        "unique_colors": unique_colors,
    }
    try:
        exec(code, g)
        fn = g["transform"]
        for i, ex in enumerate(task["train"]):
            pred = fn(ex["input"])
            print(f"Train {i+1}:", "PASS" if pred == ex["output"] else f"FAIL")
            if pred != ex["output"]:
                print(f"  Got: {pred}")
                print(f"  Exp: {ex['output']}")
    except Exception as e:
        print("EXCEPTION:", type(e).__name__, e)
