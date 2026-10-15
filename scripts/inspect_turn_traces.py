import json
from pathlib import Path
from lucca.reasoning.cegis_unshackled import execute_unshackled_python, compute_detailed_grid_diff

def inspect_task_failure(task_id: str):
    task_file = list(Path("data/benchmarks/ConceptARC/corpus").glob(f"**/{task_id}.json"))[0]
    task_data = json.loads(task_file.read_text(encoding="utf-8"))
    print(f"\n========================================================")
    print(f"TASK: {task_id}")
    print(f"========================================================")
    for idx, p in enumerate(task_data["train"]):
        print(f"Train {idx+1}: In {len(p['input'])}x{len(p['input'][0])} -> Out {len(p['output'])}x{len(p['output'][0])}")
    for idx, p in enumerate(task_data["test"]):
        print(f"Test {idx+1}: In {len(p['input'])}x{len(p['input'][0])} -> Out {len(p.get('output', []))}x{len(p.get('output', [[]])[0]) if p.get('output') else 0}")

for tid in ["Count1", "CompleteShape1", "SameDifferent1", "TopBottom2D1"]:
    inspect_task_failure(tid)
