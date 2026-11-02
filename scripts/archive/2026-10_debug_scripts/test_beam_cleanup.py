import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
import httpx
from scripts.run_concept_arc import execute_transform_code, generate_visual_diff, extract_python_code

task = json.loads(Path('data/benchmarks/ConceptARC/MinimalTasks/CleanUpMinimal.json').read_text(encoding='utf-8'))
train_desc = ''
for idx, ex in enumerate(task['train']):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

prompt = (
    "Write a concise Python function `transform(grid: list[list[int]]) -> list[list[int]]` that implements the exact transformation rule.\n"
    "Available helpers in sandbox:\n"
    "- `find_objects(grid)`: returns list of connected components with bounding box and coordinates\n"
    "- `flood_fill(grid, r, c, fill_color)`\n"
    "- `rot90`, `flip_h`, `flip_v`, `crop`, `paste`\n"
    "You may also use `np` and `scipy.ndimage`.\n"
    "Task training examples:\n"
    f"{train_desc}"
    "Keep code concise (< 35 lines). Output ONLY valid Python in a ```python ... ``` block."
)

for k in range(3):
    temp = 0.2 + k * 0.2
    resp = httpx.post('http://127.0.0.1:8080/v1/chat/completions', json={
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': temp,
        'max_tokens': 1200,
        'stream': False,
        'chat_template_kwargs': {'enable_thinking': False}
    }, timeout=60.0).json()

    code = extract_python_code(resp['choices'][0]['message']['content'])
    print(f"\n=== Candidate K={k+1} (T={temp:.1f}) ===")
    
    passed = 0
    err = None
    for idx, ex in enumerate(task['train']):
        try:
            pred = execute_transform_code(code, ex['input'])
            if pred == ex['output']:
                passed += 1
            else:
                err = f"Example {idx+1}: {generate_visual_diff(pred, ex['output'])}"
                break
        except Exception as e:
            err = f"Example {idx+1} raised {type(e).__name__}: {e}"
            break
            
    print(f"Train result: {passed}/{len(task['train'])} passed. Error: {err}")
    if passed == len(task['train']):
        print("Candidate PASSED all training examples!")
        print("--- Code ---")
        print(code)
        # Test on test set
        test_passed = 0
        for idx, ex in enumerate(task['test']):
            try:
                pred = execute_transform_code(code, ex['input'])
                if pred == ex['output']:
                    test_passed += 1
                else:
                    print(f"Test {idx+1} diff: {generate_visual_diff(pred, ex['output'])}")
            except Exception as e:
                print(f"Test {idx+1} exception: {e}")
        print(f"Test result: {test_passed}/{len(task['test'])} passed!")
