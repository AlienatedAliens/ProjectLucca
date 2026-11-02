import json
import httpx
from lucca.reasoning.spatial_dsl import summarize_grid_objects
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

test_in_summary = summarize_grid_objects(task["test"][0]["input"])
perceptual_manifest += f"Test Input Objects: {test_in_summary}\n\n"

# Stage 1: Abduction
abduction_prompt = (
    "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples and their extracted object structures.\n"
    "Core Inductive Priors:\n"
    "- Color integers are arbitrary symbolic tokens. Never deduce rules based on color arithmetic.\n"
    "- The rule is governed by abstract geometry: shape equality/identity, symmetry, counts, enclosure, relative size, or directional motion relative to boundaries/other objects.\n\n"
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
        "max_tokens": 300,
        "chat_template_kwargs": {"enable_thinking": False}
    }
)
abducted = resp.json()["choices"][0]["message"]["content"]
print("=== ABDUCTED CONCEPT ===")
print(abducted)

synthesis_prompt = (
    "Write a concise Python function `transform(grid: list[list[int]]) -> list[list[int]]` implementing this rule:\n"
    f"{abducted}\n\n"
    "Available helpers: `find_objects`, `count_objects`, `fill_holes`, `dominant_object`, `unique_colors`, `is_enclosed`, `flood_fill`, `rot90`, `flip_h`, `flip_v`, `crop`, `paste`.\n"
    "Rules:\n"
    "- Operate on components, shapes, and counts. Do not hardcode specific color values unless 0 for background.\n"
    "- Output ONLY the Python code in a ```python ... ``` block. Do NOT write conversational comments inside the code.\n\n"
    f"{train_desc}"
)

resp2 = client.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={
        "messages": [{"role": "user", "content": synthesis_prompt}],
        "temperature": 0.2,
        "max_tokens": 500,
        "chat_template_kwargs": {"enable_thinking": False}
    }
)
code = extract_python_code(resp2.json()["choices"][0]["message"]["content"])
print("=== SYNTHESIZED CODE ===")
print(code)
