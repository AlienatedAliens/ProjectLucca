#!/usr/bin/env python3
"""Phase 1 generator: extract numeric claims from the canonical docs into
data/claims.yaml (draft). Pre-maps numbers with known manifest records.
Curation (type/n/ci/artifact per row) is the remaining Phase 1 work."""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
NUM_PAT = re.compile(r"\b\d{1,3}\.\d+%|\b\d{1,4}\s*/\s*\d{1,4}\b")

# numbers with known manifest records -> record_id
KNOWN: dict[str, str] = {
    "89.0%": "math500_heldout100_direct_r0_v1_35_6",
    "94.0%": "math500_heldout100_direct_r0_v1_35_6",
    "88.8%": "math500_heldout100_direct_r0_v1_35_6",
    "98/100": "math500_heldout100_direct_r0_v1_35_6",
    "89/100": "math500_heldout100_direct_r0_v1_35_6",
    "74.20%": "math500_fresh_heldout_500_v1_3_0",
    "78.80%": "math500_fresh_heldout_500_v1_3_0",
    "77.0%": "math500_pal_v1_3",
    "87.0%": "math500_pal_v1_3",
    "94.51%": "humaneval_canonical_paired_v1_35_6",
    "93.90%": "humaneval_canonical_paired_v1_35_6",
    "155/164": "humaneval_canonical_paired_v1_35_6",
    "154/164": "humaneval_canonical_paired_v1_35_6",
    "95.73%": "humaneval_zeroshot_academic_v1_3",
    "157/164": "humaneval_zeroshot_academic_v1_3",
    "91.46%": "humaneval_plus_v1_35_6",
    "92.07%": "humaneval_plus_v1_35_6",
    "90.9%": "humaneval_plus_v1_35_6",
    "150/164": "humaneval_plus_v1_35_6",
    "151/164": "humaneval_plus_v1_35_6",
    "149/164": "humaneval_plus_v1_35_6",
}

CANONICAL_DOCS = [
    "docs/research/STATE_OF_THE_UNION_2026-10.md",
    "docs/DECISIONS.md",
    "RESULTS.md",
    "README.md",
    "docs/USER_GUIDE_WHAT_LUCCA_DOES.md",
    "docs/LUCCA_V135_1_ARCHITECTURE.md",
    "docs/research/papers/01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md",
    "docs/research/NEUROSYMBOLIC_RESEARCH_PAPER.md",
    "docs/research/papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md",
    "docs/research/PERSONHOOD_RESCORE_V1356_2026-10-05.md",
    "docs/research/GRANT_PREP_EVIDENCE_COMPILATION_2026-10-05.md",
    "handover/HANDOVER_STATE_OF_THE_UNION_2026-10-05.md",
    "plans/2026-10-05_pre_wo30_shoring_and_ladder_resequencing.md",
    "docs/audit/findings/ADVERSARIAL_AUDIT_RESPONSE_2026-10-05.md",
]

rows: list[dict[str, object]] = []
seen: set[tuple[str, str]] = set()
cid = 0
for doc in CANONICAL_DOCS:
    p = ROOT / doc
    if not p.exists():
        print(f"MISSING canonical doc: {doc}")
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        nums = [m.group(0) for m in NUM_PAT.finditer(line)]
        if not nums:
            continue
        key = (doc, line.strip()[:120])
        if key in seen:
            continue
        seen.add(key)
        cid += 1
        rid = next((KNOWN[n] for n in nums if n in KNOWN), "")
        rows.append(
            {
                "claim_id": f"CLM-{cid:04d}",
                "doc": doc,
                "line": i,
                "number": nums[0],
                "all_numbers": nums,
                "text": line.strip()[:220],
                "record_id": rid,
                "artifact": "",
                "grader": "",
                "type": "measured" if rid else "",
                "n": "",
                "ci": "",
            }
        )

out = ROOT / "data" / "claims.yaml"
with open(out, "w", encoding="utf-8", newline="") as fh:
    yaml.safe_dump(rows, fh, allow_unicode=True, sort_keys=False, width=200)
print(f"wrote {len(rows)} draft claims to {out}")
mapped = sum(1 for r in rows if r["record_id"])
print(f"pre-mapped to manifest records: {mapped}; unmapped: {len(rows) - mapped}")
