import httpx
import json
from lucca.reasoning.spatial_dsl import summarize_grid_objects

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

grammar = r"""
root ::= ws "[" ws row-list ws "]" ws
row-list ::= row (ws "," ws row)*
row ::= "[" ws int-list ws "]"
int-list ::= [0-9]+ (ws "," ws [0-9]+)*
ws ::= [ \t\n\r]*
"""

prompt = (
    "You are an expert ARC-AGI reasoning engine. Solve this spatial grid transformation task.\n"
    "Study the training examples and extracted object dimensions.\n\n"
    f"{train_desc}"
    f"Perceptual Object Manifest:\n{perceptual_manifest}"
    f"Test Input:\n{task['test'][0]['input']}\n\n"
    "Output the test output grid as a valid JSON 2D array of integers."
)

payload = {
    "messages": [{"role": "user", "content": prompt}],
    "grammar": grammar.strip(),
    "max_tokens": 500,
    "temperature": 0.1,
    "chat_template_kwargs": {"enable_thinking": False}
}

client = httpx.Client(timeout=60.0)
resp = client.post("http://127.0.0.1:8080/v1/chat/completions", json=payload)
data = resp.json()
parsed = json.loads(data["choices"][0]["message"]["content"])
print("STATUS:", resp.status_code)
print("MATCHES TEST OUTPUT WITH PERCEPTUAL MANIFEST?", parsed == task["test"][0]["output"])
if parsed == task["test"][0]["output"]:
    print("SUCCESS! Perceptual manifest solved SameDifferent via GBNF fallback!")
else:
    print("Color used in row 1:", parsed[1][1:4])
