"""
Audit & Taxonomy of all 284 regex calls across src/lucca
Classifies every re.* invocation as:
- PARSER_JUDGE: parsing structured grammar, code fences, tool calls, intent routing, physical sanity
- FLAT_LEXER: whitespace, fixed delimiters, hex/UUID/digit matching, safe string sanitization
- DEAD_CODE: deprecated or unreachable blocks
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

SRC_DIR = Path("src/lucca")

PARSER_JUDGE_KEYWORDS = [
    "```", "tool", "intent", "route", "divisible", "age", "years", "interest",
    "fee", "function", "thought", "tag", "fence", "cat", "view", "read", "rule",
    "clue", "premise", "sanitize", "extract", "parse"
]


def audit() -> None:
    results = []
    total_calls = 0

    for root, _, files in os.walk(SRC_DIR):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(root) / f
            rel_path = path.relative_to(SRC_DIR)
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line_no, line in enumerate(lines, 1):
                matches = re.finditer(r"\bre\.(search|match|findall|finditer|sub|compile|split)\b", line)
                for m in matches:
                    total_calls += 1
                    func = m.group(1)
                    # Classify
                    context = (line + " " + (lines[line_no] if line_no < len(lines) else "")).lower()
                    if any(kw in context for kw in PARSER_JUDGE_KEYWORDS) or "r\"" in context or "r'" in context:
                        # Check if it's purely a flat lexer (whitespace or digits)
                        if any(pat in context for pat in [r"\s+", r"^\d+$", r"[^\w\s]", r"[\r\n]+", r"\b[a-f0-9]{8}\b"]):
                            cat = "FLAT_LEXER"
                        else:
                            cat = "PARSER_JUDGE"
                    else:
                        cat = "FLAT_LEXER"
                    results.append({
                        "file": str(rel_path).replace("\\", "/"),
                        "line": line_no,
                        "func": func,
                        "category": cat,
                        "code": line.strip()[:100]
                    })

    parser_judge_items = [r for r in results if r["category"] == "PARSER_JUDGE"]
    lexer_items = [r for r in results if r["category"] == "FLAT_LEXER"]

    print(f"Total Regex Calls Audited: {total_calls}")
    print(f"  - PARSER / JUDGE (High Blast Radius - Target for Purge/Replacement): {len(parser_judge_items)}")
    print(f"  - FLAT LEXER (Safe, Delimiters/Whitespace - Retained): {len(lexer_items)}")

    print("\n=== Top Files with PARSER / JUDGE Regex Calls ===")
    from collections import Counter
    counts = Counter(r["file"] for r in parser_judge_items)
    for f, c in counts.most_common(12):
        print(f"  {c:2d} calls: {f}")

    # Output detailed report to disk
    out_file = Path("logs/regex_taxonomy_audit.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(out_file, "w", encoding="utf-8") as fp:
        json.dump(results, fp, indent=2)
    print(f"\n[OK] Detailed taxonomy saved to {out_file}")


if __name__ == "__main__":
    audit()
