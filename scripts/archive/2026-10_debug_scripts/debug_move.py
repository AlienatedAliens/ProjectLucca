import json
import httpx
from lucca.reasoning.spatial_dsl import summarize_grid_objects, find_objects
from lucca.sandbox.preflight import extract_python_code
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from run_concept_arc import execute_transform_code, generate_visual_diff

task = json.load(open("data/benchmarks/ConceptARC/MinimalTasks/MoveToBoundaryMinimal.json"))
train_pairs = task["train"]
test_pair = task["test"][0]

train_desc = ""
perceptual_manifest = ""
for idx, ex in enumerate(train_pairs):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"
    perceptual_manifest += (
        f"Example {idx+1} Input Objects: {summarize_grid_objects(ex['input'])}\n"
        f"Example {idx+1} Output Objects: {summarize_grid_objects(ex['output'])}\n\n"
    )

test_in_summary = summarize_grid_objects(test_pair["input"])
perceptual_manifest += f"Test Input Objects: {test_in_summary}\n\n"

# Stage 1: Abduction
abduction_prompt = (
    "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples and their extracted object structures.\n"
    "Core Inductive Priors:\n"
    "- Color integers are arbitrary symbolic tokens. Never deduce rules based on color arithmetic.\n"
    "- The rule is governed by abstract spatial relations: relative positioning (above/below, left/right of a divider), motion toward a wall/boundary (which can be along rows or along columns towards the wall), shape identity/equality, enclosure, symmetry, order, or size.\n\n"
    f"{train_desc}"
    f"Perceptual Object Manifest:\n{perceptual_manifest}"
    "Task: Deduce and state the exact relational transformation rule in 2-3 precise sentences."
)

client = httpx.Client(timeout=60.0)
resp = client.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={
        "messages": [{"role": "user", "content": abduction_prompt}],
        "temperature": 0.1,
        "max_tokens": 400,
        "chat_template_kwargs": {"enable_thinking": False}
    }
)
abducted = resp.json()["choices"][0]["message"]["content"]
print("=== ABDUCTED CONCEPT ===")
print(abducted)

synthesis_prompt = (
    "Write a concise Python function `transform(grid: list[list[int]]) -> list[list[int]]` implementing this rule:\n"
    f"{abducted}\n\n"
    "Available helpers:\n"
    "- `find_objects(grid)`: returns list of objects with fields: .color, .dimensions (height, width), .bbox (min_r, min_c, max_r, max_c), .area, .is_hollow, .coords\n"
    "- `crop_to_content(grid)`: crops grid to minimal bounding box of all non-zero cells; `bbox_of_all(grid)`: returns (min_r, min_c, max_r, max_c)\n"
    "- `crop(grid, min_r, min_c, max_r, max_c)`, `paste(dest_grid, src_grid, r, c)`\n"
    "- `rot90(grid, k=1)`, `flip_h(grid)`, `flip_v(grid)`, `flood_fill(grid, r, c, color)`\n\n"
    "Rules:\n"
    "- When an object moves 'until adjacent' to a wall or obstacle, advance step-by-step in a while loop until touching the wall, or place it at wall_pos ± 1.\n"
    "- CRITICAL: Write clean executable Python code with NO comments whatsoever. Do NOT write '# ...' comments. Start immediately with 'def transform(grid):'.\n\n"
    f"{train_desc}"
)

for temp in [0.15, 0.35, 0.55]:
    resp2 = client.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": synthesis_prompt}],
            "temperature": temp,
            "max_tokens": 1000,
            "chat_template_kwargs": {"enable_thinking": False}
        }
    )
    raw = resp2.json()["choices"][0]["message"]["content"]
    code = extract_python_code(raw)
    print(f"\n--- Temp {temp} Code ---")
    print(code)
    try:
        passed = 0
        for p_idx, pair in enumerate(train_pairs):
            pred = execute_transform_code(code, pair["input"])
            if pred == pair["output"]:
                passed += 1
            else:
                print(f"Failed Example {p_idx+1}: pred != exp")
                break
        print(f"Train pass: {passed}/{len(train_pairs)}")
        if passed == len(train_pairs):
            test_pred = execute_transform_code(code, test_pair["input"])
            print("Passed test?", test_pred == test_pair["output"])
    except Exception as e:
        print(f"Exec exception: {type(e).__name__}: {e}")
