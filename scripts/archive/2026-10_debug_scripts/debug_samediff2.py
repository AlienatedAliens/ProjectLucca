import json
import httpx
from lucca.reasoning.spatial_dsl import summarize_grid_objects, find_objects, normalize_grid
from lucca.sandbox.preflight import extract_python_code

task = json.load(open("data/benchmarks/ConceptARC/MinimalTasks/SameDifferentMinimal.json"))
train_desc = ""
perceptual_manifest = ""
for idx, ex in enumerate(task["train"]):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"
    perceptual_manifest += (
        f"Example {idx+1} Input Objects: {summarize_grid_objects(ex['input'])}\n"
        f"Example {idx+1} Output Objects: {summarize_grid_objects(ex['output'])}\n\n"
    )

# Stage 1: Abduction with explicit target color request
abduction_prompt = (
    "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples and their extracted object structures.\n"
    "Core Inductive Priors:\n"
    "- Identify the abstract relational condition (e.g., shape equality, size, symmetry).\n"
    "- Identify any specific output indicator colors (e.g., color X if condition A, color Y if condition B).\n\n"
    f"{train_desc}"
    f"Perceptual Object Manifest:\n{perceptual_manifest}"
    "Task: State the exact relational rule and specific output colors in 2-3 precise sentences."
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
    "- `find_objects(grid)`: returns list of SpatialObjects. Each object ALREADY has attributes: .color, .dimensions (height, width), .bbox (min_r, min_c, max_r, max_c), .area, .is_hollow, .coords. DO NOT write helper functions to recompute them.\n"
    "- `unique_colors(grid)`, `count_objects(grid)`, `dominant_object(grid)`\n\n"
    "Rules:\n"
    "- Start immediately with `def transform(grid):`.\n"
    "- NO comments inside the code.\n\n"
    f"{train_desc}"
)

resp2 = client.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={
        "messages": [{"role": "user", "content": synthesis_prompt}],
        "temperature": 0.2,
        "max_tokens": 1000,
        "chat_template_kwargs": {"enable_thinking": False}
    }
)
raw_code = resp2.json()["choices"][0]["message"]["content"]
code = extract_python_code(raw_code)
print("=== SYNTHESIZED CODE ===")
print(code)

# Test against training examples!
exec_globals = {
    "find_objects": find_objects,
    "normalize_grid": normalize_grid,
}
exec(code, exec_globals)
fn = exec_globals["transform"]
train_passed = 0
for idx, ex in enumerate(task["train"]):
    pred = fn(ex["input"])
    if pred == ex["output"]:
        train_passed += 1
        print(f"Train {idx+1}: PASS")
    else:
        print(f"Train {idx+1}: FAIL")

print(f"Total Train Passed: {train_passed}/{len(task['train'])}")

# Test against test examples!
for idx, ex in enumerate(task["test"]):
    pred = fn(ex["input"])
    if pred == ex["output"]:
        print(f"Test {idx+1}: PASS")
    else:
        print(f"Test {idx+1}: FAIL")
