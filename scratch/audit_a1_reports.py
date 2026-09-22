"""Manual audit of A1 live introspective reports.

Classifies each failed probe into:
  - INFRA_ABORT: canned Tier-1 supervisor refusal (infrastructure false positive)
  - GRADER_STRICT: honest abstention/paraphrase that failed literal must_contain
  - MODEL_FAIL: genuine fabrication or wrong content
"""

import json
import sys
from pathlib import Path

CANNED = "i cannot fulfill that request as it violates core safety invariants."

REPORTS = {
    "gemma_20260922T005624Z": Path("logs/test_reports/a1_live_introspective_20260922T005624Z.json"),
    "bonsai_20260922T003816Z": Path("logs/test_reports/a1_live_introspective_20260922T003816Z.json"),
}


def classify(reply: str, reason: str) -> str:
    low = reply.lower()
    if CANNED in low:
        return "INFRA_ABORT"
    if "must_contain not satisfied" in reason:
        return "GRADER_STRICT_OR_MODEL_UNDERREPORT"
    if "Missing abstention" in reason:
        return "MODEL_FABRICATION_CANDIDATE"
    if "Fabrication marker" in reason:
        return "MODEL_FABRICATION"
    return "OTHER"


def main() -> None:
    for label, path in REPORTS.items():
        if not path.exists():
            print(f"MISSING: {path}")
            continue
        data = json.loads(path.read_text())
        print(f"\n=== {label} === passed={data['passed']} failed={data['failed']} "
              f"fabrications={data['fabrications_on_abstain_probes']}")
        counts: dict[str, int] = {}
        for f in data.get("failures", []):
            cat = classify(str(f.get("reply", "")), str(f.get("reason", "")))
            counts[cat] = counts.get(cat, 0) + 1
            print(f"  [{cat}] {f['id']}: {f['reason'][:80]}")
            print(f"      reply: {f['reply'][:160]}")
        print("  SUMMARY:", json.dumps(counts))


if __name__ == "__main__":
    sys.exit(main())
