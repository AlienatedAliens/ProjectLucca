import json
from pathlib import Path

ROOT = Path("C:/Projects/ProjectLucca")
REPORTS_DIR = ROOT / "logs" / "test_reports" / "rebench_master_v140"

p_12b = REPORTS_DIR / "rebench_12B_1791875339.json"
p_e4b = REPORTS_DIR / "rebench_E4B_1791891169.json"
p_e2b = REPORTS_DIR / "rebench_E2B_1791896880.json"

d_12b = json.loads(p_12b.read_text(encoding="utf-8"))
d_e4b = json.loads(p_e4b.read_text(encoding="utf-8"))
d_e2b = json.loads(p_e2b.read_text(encoding="utf-8"))

print(f"12B: {d_12b['total_pass']}/{d_12b['total_suites']} in {d_12b['total_elapsed_s']/60:.1f}m")
print(f"E4B: {d_e4b['total_pass']}/{d_e4b['total_suites']} in {d_e4b['total_elapsed_s']/60:.1f}m")
print(f"E2B: {d_e2b['total_pass']}/{d_e2b['total_suites']} in {d_e2b['total_elapsed_s']/60:.1f}m")

print("\n--- Suite Durations (Seconds) ---")
for r12, re4, re2 in zip(d_12b['results'], d_e4b['results'], d_e2b['results']):
    print(f"{r12['name'][:40]:40s} | 12B: {r12['elapsed_s']:6.1f}s | E4B: {re4['elapsed_s']:6.1f}s | E2B: {re2['elapsed_s']:6.1f}s")
