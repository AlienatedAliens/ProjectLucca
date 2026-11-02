import json
import concurrent.futures
from pathlib import Path
from lucca.reasoning.spatial_dsl import summarize_grid_objects, column_heights, find_objects, dominant_object
from lucca.sandbox.preflight import extract_python_code
from lucca.reasoning.cost import python_ast_cost
import httpx

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

task = json.load(open("data/benchmarks/ConceptARC/MinimalTasks/OrderMinimal.json"))
train_pairs = task["train"]
test_pair = task["test"][0]

train_desc = ""
perceptual_manifest = ""
for idx, ex in enumerate(train_pairs):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"
    in_summary = summarize_grid_objects(ex["input"])
    out_summary = summarize_grid_objects(ex["output"])
    diff_summary = compute_grid_diff(ex["input"], ex["output"])
    in_col_h = column_heights(ex["input"])
    out_col_h = column_heights(ex["output"])
    perceptual_manifest += (
        f"Example {idx+1} Input Objects: {in_summary}\n"
        f"Example {idx+1} Output Objects: {out_summary}\n"
        f"Example {idx+1} Column Heights: {in_col_h} -> Output: {out_col_h}\n"
        f"Example {idx+1} Diffs: {diff_summary}\n\n"
    )

test_in_summary = summarize_grid_objects(test_pair["input"])
test_in_col_h = column_heights(test_pair["input"])
perceptual_manifest += (
    f"Test Input Objects: {test_in_summary}\n"
    f"Test Input Column Heights: {test_in_col_h}\n\n"
)

client = httpx.Client(timeout=60.0)

abduction_prompt = (
    "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples, object structures, column projections, and coordinate diffs.\n"
    "Core Inductive Priors:\n"
    "- Color integers are arbitrary symbolic tokens. Never deduce rules based on color arithmetic.\n"
    "- The rule is governed by abstract spatial relations: relative positioning, motion toward boundary, shape identity/equality, enclosure, symmetry, order, or size.\n\n"
    f"{train_desc}"
    f"Perceptual Object Manifest, Column Projections & Diffs:\n{perceptual_manifest}"
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
print("=== ABDUCTED ===")
print(abducted)

synthesis_prompt = (
    "Write a concise Python function `transform(grid: list[list[int]]) -> list[list[int]]` implementing this rule:\n"
    f"{abducted}\n\n"
    "Available helpers:\n"
    "- Objects: `find_objects(grid, background=0)` (has .color, .dimensions (height, width), .bbox (min_r, min_c, max_r, max_c), .area, .is_hollow, .coords; do NOT recompute them), `count_objects(grid)`, `count_cells(grid, color=None)` (counts individual pixels), `dominant_object(grid)`, `unique_colors(grid)`\n"
    "- Ordering: `sort_objects(objects, key='height'|'width'|'area'|'min_r'|'min_c', reverse=False)`, `column_heights(grid)`, `row_widths(grid)`\n"
    "- Morphology: `denoise(grid, min_size=2)`, `majority_filter(grid, radius=1)`, `fill_holes(grid, color)`, `flood_fill(grid, r, c, color)`\n"
    "- Geometry & Symmetry: `complete_symmetry(grid, axis='vertical'|'horizontal')`, `crop(grid, min_r, min_c, max_r, max_c)`, `crop_to_content(grid)`, `bbox_of_all(grid)`, `paste(dest, src, r, c)`\n"
    "- Lines & Motion: `draw_line(grid, r1, c1, r2, c2, color)`, `move_until_contact(grid, obj, dr, dc)`, `rot90(grid, k=1)`, `flip_h(grid)`, `flip_v(grid)`\n\n"
    "Rules:\n"
    "- Operate on components, shapes, and counts. If the task introduces specific indicator colors (e.g. 4 for true/same, 5 for false/different), output those target colors.\n"
    "- For column/bar ordering, use column_heights(grid) and place sorted heights starting from left.\n"
    "- For shape completion, complete_symmetry(grid) completes partial symmetric frames.\n"
    "- CRITICAL: Write clean executable Python code with NO comments whatsoever. Do NOT write '# ...' comments. Start immediately with 'def transform(grid):'.\n\n"
    f"{train_desc}"
)

def _query_candidate(temp: float) -> str:
    try:
        r = client.post(
            "http://127.0.0.1:8080/v1/chat/completions",
            json={"messages": [{"role": "user", "content": synthesis_prompt}], "temperature": temp, "max_tokens": 1024, "chat_template_kwargs": {"enable_thinking": False}}
        )
        return extract_python_code(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        return ""

beam_temps = [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    codes = list(executor.map(_query_candidate, beam_temps))

print(f"\nGenerated {len(codes)} candidates:")
exec_globals = {
    "find_objects": find_objects,
    "dominant_object": dominant_object,
    "column_heights": column_heights,
}

for idx, c in enumerate(codes):
    if not c:
        print(f"Cand {idx+1}: EMPTY / PARSE ERROR")
        continue
    cost = python_ast_cost(c)
    try:
        ns = dict(exec_globals)
        exec(c, ns)
        fn = ns["transform"]
        passed = sum(1 for ex in train_pairs if fn(ex["input"]) == ex["output"])
        print(f"Cand {idx+1}: PASSED {passed}/{len(train_pairs)} (Cost: {cost:.1f})")
        if passed == len(train_pairs):
            print(">>> VERIFIED CANDIDATE CODE:")
            print(c)
    except Exception as e:
        print(f"Cand {idx+1}: EXEC ERROR: {type(e).__name__}: {e} (Cost: {cost:.1f})")
