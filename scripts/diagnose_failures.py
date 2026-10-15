import json
from pathlib import Path

report_path = Path("logs/test_reports/concept_arc_16concepts_tier0.json")
data = json.loads(report_path.read_text(encoding="utf-8"))

records = data.get("records", [])
print(f"Total evaluated tasks: {len(records)}")

failed_train = [r for r in records if not r.get("train_solved")]
train_passed_test_failed = [r for r in records if r.get("train_solved") and not r.get("test_solved")]
test_passed = [r for r in records if r.get("test_solved")]

print(f"Test Passed (100% Correct): {len(test_passed)}")
print(f"Train Passed but Test Failed (Overfitting/Generalization Gap): {len(train_passed_test_failed)}")
print(f"Train Failed (Could not satisfy demonstrations in 3 turns): {len(failed_train)}")

print("\n=== Category 1: Train Passed but Test Failed (Generalization / Incomplete Abduction) ===")
for r in train_passed_test_failed:
    print(f"Task: {r['task_id']} ({r['concept']}) in {r['turns_taken']} turns")

print("\n=== Category 2: Train Failed (CEGIS Budget Exhausted / Turn Breakdown) ===")
by_concept_fails = {}
for r in failed_train:
    by_concept_fails.setdefault(r["concept"], []).append(r["task_id"])

for concept, task_ids in sorted(by_concept_fails.items()):
    print(f"Concept '{concept}': {len(task_ids)} tasks failed -> {', '.join(task_ids)}")
