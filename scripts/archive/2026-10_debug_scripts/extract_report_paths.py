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

def get_report_path(tail_snip):
    for l in tail_snip.split("\n"):
        m = re.search(r"(?:Saved|written to|report saved to|report to|Report written to):\s*([^\s]+\.json)", l)
        if m:
            p = m.group(1).strip()
            # Clean up potential leading/trailing artifacts
            if p.startswith("C:"):
                return Path(p)
            return ROOT / p
    return None

for i, (r12, re4, re2) in enumerate(zip(d_12b['results'], d_e4b['results'], d_e2b['results'])):
    print(f"=== [{i+1}] {r12['name']} ===")
    p12 = get_report_path(r12.get('tail_snippet', ''))
    pe4 = get_report_path(re4.get('tail_snippet', ''))
    pe2 = get_report_path(re2.get('tail_snippet', ''))
    print(f"  12B: {r12['ok']} ({r12['elapsed_s']}s) -> {p12.name if p12 else 'TIMEOUT'}")
    print(f"  E4B: {re4['ok']} ({re4['elapsed_s']}s) -> {pe4.name if pe4 else 'TIMEOUT'}")
    print(f"  E2B: {re2['ok']} ({re2['elapsed_s']}s) -> {pe2.name if pe2 else 'TIMEOUT'}")
