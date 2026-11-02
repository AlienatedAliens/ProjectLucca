import json
from pathlib import Path

report = json.loads(Path('logs/test_reports/concept_arc_gbnf_minimal_1791570856.json').read_text(encoding='utf-8'))
for t in report['tasks']:
    if not t['arm_b_success']:
        print(f"==================== {t['task_id']} ({t['concept']}) ====================")
        print(f"Arm A: {t['arm_a_success']}, Arm B Method: {t['arm_b_method']}, Fail Reason: {t['arm_b_failure_reason']}")
        print(f"Train passed: {t['arm_b_train_passed']}, Repair rounds: {t['arm_b_repair_rounds']}")
        task_data = json.loads(Path(f"data/benchmarks/ConceptARC/MinimalTasks/{t['task_id']}.json").read_text(encoding='utf-8'))
        print(f"Num train pairs: {len(task_data['train'])}, Num test pairs: {len(task_data['test'])}")
        print("Train 1 input shape:", len(task_data['train'][0]['input']), "x", len(task_data['train'][0]['input'][0]))
        print("Train 1 output shape:", len(task_data['train'][0]['output']), "x", len(task_data['train'][0]['output'][0]))
        print("Test 1 input shape:", len(task_data['test'][0]['input']), "x", len(task_data['test'][0]['input'][0]))
        print("Test 1 output shape:", len(task_data['test'][0]['output']), "x", len(task_data['test'][0]['output'][0]))
        print("\n--- Synthesized Code ---")
        print(t['arm_b_synthesized_code'])
        print()

