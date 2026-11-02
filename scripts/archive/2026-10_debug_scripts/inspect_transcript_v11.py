import json
from pathlib import Path

TRANSCRIPT = Path(r"C:\Users\seatr\.gemini\antigravity\brain\98a93c11-488e-44ff-8a21-a4cb6071ce06\.system_generated\logs\transcript.jsonl")

target_indices = [17774, 17837, 17843]
with open(TRANSCRIPT, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx in target_indices:
            d = json.loads(line)
            content = d.get("content", "")
            step = d.get("step_index")
            tp = d.get("type")
            truncated = d.get("truncated_fields", [])
            print(f"Line {idx}: step={step}, type={tp}, trunc={truncated}, len={len(content)}")
            if "Review Notes" in content:
                print(f"--- MATCH at Line {idx} ---")
                out_path = Path("scratch_v11_notes.txt")
                out_path.write_text(content, encoding="utf-8")
                print(f"Wrote {len(content)} chars to {out_path}")
