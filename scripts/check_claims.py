#!/usr/bin/env python3
"""Phase 1 gate: validate data/claims.yaml against the manifest, the
filesystem, and the canonical docs.

Checks (per the 2026-10-06 criticism plan, step 1.3):
  (a) every claim `record_id` resolves to a record in data/benchmarks/MANIFEST.yaml
  (b) every claim `artifact` path exists on disk
  (c) every numeric pattern (NN.N% or N/M) in a canonical doc appears in at
      least one claims.yaml row (by normalized number string)

Exit code 0 = pass; 1 = violations found (printed).
Status: Phase 1 infrastructure. The claims inventory is expected to FAIL
this check until curation completes (that is the point).
"""
from __future__ import annotations

import glob
import io
import re
import sys
from pathlib import Path

import yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / "data" / "claims.yaml"
MANIFEST = ROOT / "data" / "benchmarks" / "MANIFEST.yaml"

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

NUM_PAT = re.compile(r"\b\d{1,3}\.\d+%|\b\d{1,4}\s*/\s*\d{1,4}\b")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def main() -> int:
    claims = yaml.safe_load(CLAIMS.read_text(encoding="utf-8")) or []
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    record_ids = {r["benchmark_id"] for r in manifest.get("records", [])}

    violations: list[str] = []

    # (a) record_id resolution
    known_numbers: set[str] = set()
    for c in claims:
        rid = c.get("record_id")
        if rid and rid not in record_ids:
            violations.append(f"(a) {c.get('claim_id')}: record_id {rid!r} not in MANIFEST.yaml")
        art = c.get("artifact")
        if art and not (ROOT / art).exists():
            violations.append(f"(b) {c.get('claim_id')}: artifact {art!r} does not exist")
        num = c.get("number")
        if num:
            known_numbers.add(norm(str(num)))
            # also register plain variants
            known_numbers.add(norm(str(num)).replace("%", ""))

    # (d) unresolved claims: no record_id, no artifact, no type
    unresolved = sum(
        1 for c in claims if not c.get("record_id") and not c.get("artifact") and not c.get("type")
    )
    if unresolved:
        violations.append(f"(d) {unresolved} claims unresolved (no record_id/artifact/type) — Phase 1 curation backlog")

    # (c) coverage of numeric patterns in canonical docs
    missing = 0
    for doc in CANONICAL_DOCS:
        p = ROOT / doc
        if not p.exists():
            violations.append(f"(c) canonical doc missing: {doc}")
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in NUM_PAT.finditer(line):
                num = norm(m.group(0))
                if num not in known_numbers:
                    missing += 1
                    if missing <= 40:
                        violations.append(f"(c) {doc}:{i}: uncovered number {m.group(0)!r} :: {line.strip()[:110]}")
    if missing > 40:
        violations.append(f"(c) ... and {missing - 40} more uncovered numbers")

    print(f"claims: {len(claims)} | manifest records: {len(record_ids)} | unresolved: {unresolved}")
    print(f"violations: {len(violations)}")
    for v in violations:
        print(" ", v)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
