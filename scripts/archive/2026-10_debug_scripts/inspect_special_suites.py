import json
from pathlib import Path

ROOT = Path("C:/Projects/ProjectLucca")
LOGS = ROOT / "logs" / "test_reports"

def load_json(p):
    path = LOGS / p if not Path(p).is_absolute() else Path(p)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None

# Load files
z12 = load_json("zebra_logic_sweep_1791867032.json")
ze4 = load_json("zebra_logic_sweep_1791887039.json")
ze2 = load_json("zebra_logic_sweep_1791894250.json")

print("--- ZebraLogic Summary ---")
for tier_name, zdata in [("12B", z12), ("E4B", ze4), ("E2B", ze2)]:
    if zdata:
        tiers = zdata.get("summary", {}).get("tiers", {})
        print(f"[{tier_name}]")
        for k, v in tiers.items():
            print(f"  {k}: Direct={v.get('direct_pct')}%, Think={v.get('thinking_pct')}%, Oracle={v.get('oracle_z3_pct')}%, LLM_Z3={v.get('llm_z3_pct')}% (syntax={v.get('llm_z3_syntax_pct')}%)")

c12 = load_json("concept_arc_gbnf_minimal_1791874925.json")
ce4 = load_json("concept_arc_gbnf_minimal_1791890994.json")
ce2 = load_json("concept_arc_gbnf_minimal_1791896741.json")

print("\n--- ConceptARC Summary ---")
for tier_name, cdata in [("12B", c12), ("E4B", ce4), ("E2B", ce2)]:
    if cdata:
        tot = cdata.get("total_tasks", 16)
        a_pass = cdata.get("arm_a_passed", 0)
        b_pass = cdata.get("arm_b_passed", 0)
        print(f"[{tier_name}] Arm A (Direct) = {a_pass}/{tot} ({a_pass/tot*100:.1f}%), Arm B (CEGIS) = {b_pass}/{tot} ({b_pass/tot*100:.1f}%)")

p12 = load_json("contrastive_battery_20261013T070527Z.json")
pe4 = load_json("contrastive_battery_20261013T113131Z.json")
pe2 = load_json("contrastive_battery_20261013T130653Z.json")

print("\n--- Personhood Contrastive Summary ---")
for tier_name, pdata in [("12B", p12), ("E4B", pe4), ("E2B", pe2)]:
    if pdata:
        m = pdata.get("metrics", {})
        print(f"[{tier_name}] Overall Acc: {m.get('overall_accuracy')}, Abstention Acc: {m.get('abstention_accuracy')}, Boundary Acc: {m.get('boundary_accuracy')}")
