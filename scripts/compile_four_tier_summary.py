import json
from pathlib import Path

dir_path = Path("logs/test_reports/comparative_four_tier")
tiers = [
    ("Tier 0 (Flagship 26B-A4B)", "tier0"),
    ("Tier 1 (Companion 12B)", "tier1"),
    ("Tier 2 (Edge E4B)", "tier2"),
    ("Tier 3 (Edge E2B)", "tier3"),
]

print("=" * 135)
print(f"{'Model Tier':<26} | {'ConceptARC Test':<16} | {'CRUXEval Direct':<16} | {'CRUXEval CEGIS':<16} | {'Zebra Direct':<14} | {'Zebra Z3 SMT':<14} | {'MATH Direct':<12} | {'MATH CAS':<12}")
print("-" * 135)

for display, k in tiers:
    ca = json.loads((dir_path / f"concept_arc_{k}.json").read_text(encoding="utf-8"))
    crux = json.loads((dir_path / f"cruxeval_smoke_{k}.json").read_text(encoding="utf-8"))
    z = json.loads((dir_path / f"zebra_logic_{k}.json").read_text(encoding="utf-8"))
    m = json.loads((dir_path / f"math500_{k}.json").read_text(encoding="utf-8"))

    ca_str = f"{ca['test_solved']}/{ca['total_tasks']} ({ca['test_accuracy']*100:.1f}%)"
    crux_dir = f"{crux['summary']['arm_a_rate']*100:.1f}%"
    crux_cegis = f"{crux['summary']['arm_b_rate']*100:.1f}% (+{crux['summary']['net_lift_pp']:+.0f}pp)"
    
    z_probs = z.get("problems", [])
    z_dir = f"{sum(1 for p in z_probs if p.get('direct_ok'))}/{len(z_probs)} ({sum(1 for p in z_probs if p.get('direct_ok'))/len(z_probs)*100:.0f}%)"
    z_z3 = f"{sum(1 for p in z_probs if p.get('llm_z3_ok'))}/{len(z_probs)} ({sum(1 for p in z_probs if p.get('llm_z3_ok'))/len(z_probs)*100:.0f}%)"

    m_dir = f"{m['arm_a_control']['pass_rate']*100:.1f}%"
    m_cas = f"{m['arm_b_augmented']['pass_rate']*100:.1f}%"

    print(f"{display:<26} | {ca_str:<16} | {crux_dir:<16} | {crux_cegis:<16} | {z_dir:<14} | {z_z3:<14} | {m_dir:<12} | {m_cas:<12}")

print("=" * 135)
