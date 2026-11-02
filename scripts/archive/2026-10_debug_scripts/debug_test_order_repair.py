import json
import httpx
from lucca.sandbox.preflight import extract_python_code
from lucca.reasoning.spatial_dsl import *

task = json.loads(open("data/benchmarks/ConceptARC/MinimalTasks/OrderMinimal.json").read())
train_desc = ""
for idx, ex in enumerate(task["train"]):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

cand_code = """def transform(grid: list[list[int]]) -> list[list[int]]:
    rows = len(grid)
    cols = len(grid[0])
    column_data = []
    for c in range(cols):
        col_values = [grid[r][c] for r in range(rows)]
        height = sum(1 for val in col_values if val != 0)
        column_data.append((height, col_values))

    sorted_columns = sorted(column_data, key=lambda x: x[0])

    new_grid = [[0] * cols for _ in range(rows)]
    for c in range(cols):
        col_values = sorted_columns[c][1]
        for r in range(rows):
            new_grid[r][c] = col_values[r]

    return new_grid"""

err_msg = """Failed on Example 1: Cell value mismatches (8 cells differ). Examples: [row 4, col 1: expected 4, got 0; row 4, col 4: expected 0, got 4; row 5, col 0: expected 4, got 0].
Expected grid:
[[0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 4, 4, 4, 0, 0], [4, 4, 4, 4, 0, 0]]
Your function produced:
[[0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 4], [0, 0, 0, 0, 4, 4], [0, 0, 0, 4, 4, 4], [0, 0, 4, 4, 4, 4]]"""

repair_prompt = (
    "Your previous Python code failed verification against the training examples.\n\n"
    f"Current Code:\n```python\n{cand_code}\n```\n\n"
    f"Verification Failure:\n{err_msg}\n\n"
    f"Task Examples for context:\n{train_desc}\n\n"
    "Notice: empty columns of height 0 should NOT be placed before the non-zero bars. Non-zero bars should be sorted by height and placed starting from column 0.\n"
    "Please fix the transformation function. Keep it concise (< 40 lines).\n"
    "CRITICAL: Write clean Python with NO comments. Output in a ```python ... ``` block."
)

client = httpx.Client(timeout=60.0)
resp = client.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={"messages": [{"role": "user", "content": repair_prompt}], "temperature": 0.15, "max_tokens": 1024, "chat_template_kwargs": {"enable_thinking": False}}
)
repaired = extract_python_code(resp.json()["choices"][0]["message"]["content"])
print("REPAIRED CODE:\n", repaired)

g = dict(globals())
exec(repaired, g)
fn = g["transform"]
for i, ex in enumerate(task["train"]):
    pred = fn(ex["input"])
    print(f"Train {i+1}:", "PASS" if pred == ex["output"] else "FAIL")
for j, tex in enumerate(task["test"]):
    tpred = fn(tex["input"])
    print(f"Test {j+1}:", "PASS" if tpred == tex["output"] else "FAIL")
