import json
from pathlib import Path

report = json.loads(Path('logs/test_reports/concept_arc_gbnf_minimal_1791570856.json').read_text(encoding='utf-8'))
print(f"{'Task ID':<26} {'Arm A':<8} {'Arm B':<8} {'Method':<20} {'Reason'}")
print("-" * 75)
for t in report['tasks']:
    a_res = "PASS" if t['arm_a_success'] else "FAIL"
    b_res = "PASS" if t['arm_b_success'] else "FAIL"
    method = t['arm_b_method']
    reason = t['arm_b_failure_reason'] or ""
    print(f"{t['task_id']:<26} {a_res:<8} {b_res:<8} {method:<20} {reason}")

print("-" * 75)
print(f"Summary: Arm A = {report['summary']['arm_a_accuracy']*100:.1f}%, Arm B = {report['summary']['arm_b_accuracy']*100:.1f}%")
