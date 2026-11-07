import json
import re
from pathlib import Path

ROOT = Path("C:/Projects/ProjectLucca")
REPORTS_DIR = ROOT / "logs" / "test_reports" / "rebench_master_v140"

p_12b = REPORTS_DIR / "rebench_12B_1791875339.json"
p_e4b = REPORTS_DIR / "rebench_E4B_1791891169.json"
p_e2b = REPORTS_DIR / "rebench_E2B_1791896880.json"

d_12b = json.loads(p_12b.read_text(encoding="utf-8"))
d_e4b = json.loads(p_e4b.read_text(encoding="utf-8"))
d_e2b = json.loads(p_e2b.read_text(encoding="utf-8"))

print("="*90)
print(f"{'SUITE NAME':35s} | {'12B COMPOUND':16s} | {'E4B COMPOUND':16s} | {'E2B COMPOUND':16s}")
print("="*90)

for r12, re4, re2 in zip(d_12b['results'], d_e4b['results'], d_e2b['results']):
    name = r12['name'][:35]
    s12 = r12.get('tail_snippet', '')
    se4 = re4.get('tail_snippet', '')
    se2 = re2.get('tail_snippet', '')
    print(f"\n>>> {r12['name']}")
    for tag, snip in [("12B", s12), ("E4B", se4), ("E2B", se2)]:
        last_lines = [l for l in snip.split("\n") if l.strip()]
        relevant = [l for l in last_lines if any(k in l for k in ["TOTAL", "Accuracy", "Compound", "Passed", "Pass@1", "Recall", "Summary", "Rate", "OVERALL"])]
        summary_str = relevant[-1] if relevant else (last_lines[-1] if last_lines else "N/A")
        print(f"  [{tag:3s}] {summary_str}")
