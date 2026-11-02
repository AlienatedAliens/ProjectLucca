import json
from pathlib import Path
import httpx

task_path = Path('data/benchmarks/ConceptARC/MinimalTasks/CenterMinimal.json')
task = json.loads(task_path.read_text(encoding='utf-8'))

train_desc = ''
for i, ex in enumerate(task['train']):
    train_desc += f"Example {i+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

client = httpx.Client(timeout=60.0)
prompt = f"""Write a Python function `transform(grid: list[list[int]]) -> list[list[int]]` that solves this ARC grid transformation.
Analyze the input-to-output examples below, determine the exact pattern, and write the complete function.

{train_desc}
Respond ONLY with the complete Python code in a ```python ... ``` block.
"""

payload = {
    'messages': [{'role': 'user', 'content': prompt}],
    'stream': False,
    'max_tokens': 1024,
    'temperature': 0.1,
    'chat_template_kwargs': {'enable_thinking': False}
}

resp = client.post('http://127.0.0.1:8080/v1/chat/completions', json=payload)
data = resp.json()
print('RESPONSE CONTENT:')
print(data['choices'][0]['message']['content'])
