import json
from pathlib import Path
from lucca.reasoning.cegis_unshackled import execute_unshackled_python, compute_detailed_grid_diff

report_path = Path("logs/test_reports/concept_arc_16concepts_tier0.json")
data = json.loads(report_path.read_text(encoding="utf-8"))

print("=== DEEP DIVE: Category 1 (Train Passed, Test Failed) ===")
for r in data["records"]:
    if r.get("train_solved") and not r.get("test_solved"):
        task_id = r["task_id"]
        concept = r["concept"]
        code = r["code"]
        task_file = list(Path("data/benchmarks/ConceptARC/corpus").glob(f"**/{task_id}.json"))[0]
        task_data = json.loads(task_file.read_text(encoding="utf-8"))
        
        test_inp = task_data["test"][0]["input"]
        test_exp = task_data["test"][0]["output"]
        outcome = execute_unshackled_python(code, test_inp)
        diff = compute_detailed_grid_diff(test_exp, outcome.output_grid or [])
        print(f"\nTask: {task_id} ({concept})")
        print(f"Summary Discrepancy on Test: {diff.summary_message}")
        print(f"Details:\n{diff.format_counterexample_prompt(max_examples=4)}")

print("\n=== DEEP DIVE: Category 2 (Representative Train Failures) ===")
sample_fails = ["Count1", "CompleteShape1", "SameDifferent1", "TopBottom2D1"]
for r in data["records"]:
    if r["task_id"] in sample_fails:
        task_id = r["task_id"]
        task_file = list(Path("data/benchmarks/ConceptARC/corpus").glob(f"**/{task_id}.json"))[0]
        task_data = json.loads(task_file.read_text(encoding="utf-8"))
        print(f"\nTask: {task_id} ({r['concept']}) - Error: {r.get('error_summary')}")
        train_pairs = task_data["train"]
        print(f"Train demonstrations: {len(train_pairs)} pairs. Input shapes: {[ (len(p['input']), len(p['input'][0])) for p in train_pairs ]}")
        print(f"Output shapes: {[ (len(p['output']), len(p['output'][0])) for p in train_pairs ]}")
