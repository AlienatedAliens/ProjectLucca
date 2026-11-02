import json

d = json.load(open("logs/test_reports/concept_arc_gbnf_minimal_1791605268.json"))
for t in d["tasks"]:
    if t["concept"] in ["CleanUp", "CompleteShape", "Order", "SameDifferent"]:
        print("=" * 60)
        print(f"CONCEPT: {t['concept']}")
        print(f"Arm A Grid: {t['arm_a_predicted_grid'] is not None}")
        print(f"Arm B Predicted: {t['arm_b_predicted_grid'] is not None}")
        print(f"Fail Reason: {t['arm_b_failure_reason']}")
