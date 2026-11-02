import json
from pathlib import Path
from lucca.core.config import get_config
from lucca.brain.llm_client import LLMClient
from lucca.core.schemas import TokenDelta
from lucca.sandbox.preflight import extract_python_code

cfg = get_config()
client = LLMClient()
task_path = Path("data/benchmarks/ConceptARC/MinimalTasks/CenterMinimal.json")
task = json.loads(task_path.read_text(encoding="utf-8"))

train_desc = ""
for i, ex in enumerate(task["train"]):
    train_desc += f"Example {i+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

from lucca.core.schemas import ChatMessage

messages = [
    ChatMessage(
        role="user",
        content=(
            "Write a Python function `transform(grid: list[list[int]]) -> list[list[int]]` that solves this ARC grid transformation.\n"
            "Analyze the input-to-output examples below, determine the exact pattern, and write the complete function.\n\n"
            f"{train_desc}\n"
            "Respond ONLY with the Python code in a ```python ... ``` block."
        ),
    )
]

deltas = []
for event in client.stream_turn(messages=messages, tools=[], max_tokens=1024, enable_thinking=False):
    if isinstance(event, TokenDelta) and event.delta:
        deltas.append(event.delta)

resp = "".join(deltas)
print("RAW RESP:\n", resp)
code = extract_python_code(resp)
print("EXTRACTED CODE:\n", code)

# Test execution on train examples
exec_globals = {}
exec(code, exec_globals)
transform_fn = exec_globals["transform"]

passed_train = 0
for i, ex in enumerate(task["train"]):
    out = transform_fn(ex["input"])
    match = out == ex["output"]
    print(f"Train {i+1} match: {match}")
    if match:
        passed_train += 1

print(f"Train pass rate: {passed_train}/{len(task['train'])}")

# Now evaluate on test examples
passed_test = 0
for i, ex in enumerate(task["test"]):
    out = transform_fn(ex["input"])
    match = out == ex["output"]
    print(f"Test {i+1} match: {match}")
    if match:
        passed_test += 1

print(f"Test pass rate: {passed_test}/{len(task['test'])}")
