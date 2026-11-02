import json
from pathlib import Path

TRANSCRIPT_FULL = Path(r"C:\Users\seatr\.gemini\antigravity\brain\98a93c11-488e-44ff-8a21-a4cb6071ce06\.system_generated\logs\transcript_full.jsonl")

with open(TRANSCRIPT_FULL, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx == 17774:
            d = json.loads(line)
            content = d.get("content", "")
            Path("v11_notes_full.md").write_text(content, encoding="utf-8")
            print(f"Extracted full v11 notes ({len(content)} characters, {len(content.splitlines())} lines) to v11_notes_full.md")
            break
