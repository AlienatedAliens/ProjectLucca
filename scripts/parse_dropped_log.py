import json
import re
from pathlib import Path

log_path = Path(r"C:\Users\seatr\.gemini\antigravity\brain\640ae6a7-e6d5-40f0-8a7c-f97f614e138f\.system_generated\tasks\task-9624.log")
lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()

entries = []
curr = None
for line in lines:
    m = re.match(r"\[(\d+)/400\] (PASS|FAIL) \| Subj: (.*?) \(L(\d+)\) \| Pred: (.*?) \| Expected: (.*?) \| Latency: ([\d\.]+)s", line)
    if m:
        if curr:
            entries.append(curr)
        curr = {
            "idx": int(m.group(1)),
            "passed": m.group(2) == "PASS",
            "subject": m.group(3),
            "level": int(m.group(4)),
            "predicted_ans": m.group(5),
            "expected_ans": m.group(6),
            "llm_latency_s": float(m.group(7)),
            "stderr": "",
            "exit_code": 0 if m.group(2) == "PASS" else 1,
            "generated_code": "",
            "feedback_triggered": False,
            "feedback_succeeded": False,
        }
    elif curr and "Stderr:" in line:
        curr["stderr"] += line.replace("Stderr:", "").strip() + "\n"
    elif curr and curr["stderr"]:
        if not line.startswith("["):
            curr["stderr"] += line.strip() + "\n"

if curr:
    entries.append(curr)

print(f"Parsed {len(entries)} entries. Range: {entries[0]['idx']} to {entries[-1]['idx']}.")
passes = sum(1 for e in entries if e["passed"])
print(f"Passes: {passes}/{len(entries)} ({passes/len(entries)*100:.2f}%)")

out_file = Path("logs/test_reports/task_9624_extracted_292.json")
out_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")
print(f"Saved {len(entries)} partial results to {out_file}")
