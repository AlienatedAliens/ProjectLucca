"""Inspect the latest A1 live battery reports (WO-9 verification)."""

import json
import glob

intro = sorted(glob.glob("logs/test_reports/a1_live_introspective*.json"))[-1]
stance = sorted(glob.glob("logs/test_reports/a1_live_stance_consistency*.json"))[-1]

print("=== INTROSPECTIVE:", intro)
data = json.load(open(intro, encoding="utf-8"))
print("passed/total:", data["passed"], "/", data["total"], "LB:", round(data["wilson_lb"], 4))
for f in data.get("failures", []):
    print("-", f["id"], "|", f["reason"][:90])
    print("  reply:", f["reply"][:250].replace("\n", " "))

print()
print("=== STANCE:", stance)
st = json.load(open(stance, encoding="utf-8"))
print("keys:", list(st.keys()))
for k in ("consistency", "agreement_rate", "silent_drifts", "drifts", "failures"):
    if k in st:
        print(k, "=", json.dumps(st[k], indent=1)[:1800])