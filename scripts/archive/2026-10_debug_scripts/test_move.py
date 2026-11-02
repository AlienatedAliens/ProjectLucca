import json
import httpx

task = json.load(open("data/benchmarks/ConceptARC/MinimalTasks/MoveToBoundaryMinimal.json"))
train_desc = ""
for idx, ex in enumerate(task["train"]):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

prompt = (
    "You are an expert ARC-AGI reasoning engine. Solve this spatial grid transformation task.\n"
    "Study the training examples, deduce the underlying transformation rule, and output the EXACT "
    "test output grid for the test input.\n\n"
    f"{train_desc}"
    f"Test Input:\n{task['test'][0]['input']}\n\n"
    "Output ONLY the test output grid as a valid JSON 2D array inside a ```json ... ``` block."
)

client = httpx.Client(timeout=60.0)
resp = client.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 600,
        "chat_template_kwargs": {"enable_thinking": False}
    }
)
raw = resp.json()["choices"][0]["message"]["content"]
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from run_concept_arc import extract_grid_from_text
parsed = extract_grid_from_text(raw)
print("Matches ground truth test output?", parsed == task["test"][0]["output"])
