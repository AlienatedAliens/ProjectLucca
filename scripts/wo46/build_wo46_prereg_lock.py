"""Build WO-46 causal pre-registration lock BEFORE authoring or scraping `real_web_v2`."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_prereg_lock.json"

FILES_TO_LOCK = [
    "src/lucca/core/proof_policy.py",
    "src/lucca/core/corroboration.py",
    "src/lucca/core/walton_schemes/__init__.py",
    "src/lucca/core/walton_schemes/evaluators.py",
    "src/lucca/core/walton_schemes/dedup.py",
    "src/lucca/core/walton_schemes/web_relevance.py",
    "src/lucca/core/neural_hazard_classifier.py",
    "src/lucca/sandbox/research_tool.py",
    "src/lucca/sandbox/search_tool.py",
    "src/lucca/sandbox/web_tool.py",
    "models/proof_policy_hazard_v3_ov/openvino_model.xml",
    "models/proof_policy_hazard_v3_ov/openvino_model.bin",
    "models/proof_policy_hazard_v3_ov/tokenizer.json",
    "models/verifier_deberta_v3_xsmall_ov/openvino_model.xml",
    "models/verifier_deberta_v3_xsmall_ov/openvino_model.bin",
    "models/verifier_deberta_v3_xsmall_ov/tokenizer.json",
    "scripts/wo46/collect_wo46_real_web_v2.py",
    "scripts/wo46/eval_wo46_real_web_v2.py",
    "logs/test_reports/wo46/prompts/real_web_v2_rater1_prompt.txt",
    "logs/test_reports/wo46/prompts/real_web_v2_rater2_prompt.txt",
    "logs/test_reports/wo46/prompts/real_web_v2_adjudicator_prompt.txt",
]


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    locked: dict[str, str] = {}
    for rel in FILES_TO_LOCK:
        p = REPO / rel
        if not p.exists():
            raise FileNotFoundError(f"Missing required WO-46 lock file: {rel}")
        locked[rel] = _sha256(p)

    doc = {
        "preregistration_id": "WO46-REAL-WEB-SCRAPLING-v2",
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "sample_size": 64,
        "nominal_strata": {"low": 22, "medium": 22, "high": 20},
        "query_disjointness_rule": "0 normalized query overlap with web_evidentiary_burden_real_v1.jsonl and web_evidentiary_burden_360.jsonl; authored by blinded subagent AFTER this lock is pushed to origin/main",
        "retrieval_stack": "lucca.sandbox.research_tool.research_topic(max_sources=4, include_raw_html=True) -> search_web + web_tool.fetch_url (Scrapling/Trafilatura + DOM injection sanitizer)",
        "ground_truth_protocol": ">=2 independent blinded raters labeling independent_source_count (0..3), dispute_present (bool), and hazard_tier (low/medium/high), with 3rd blinded adjudicator resolving any disagreements",
        "primary_endpoint": "burden_decision_accuracy (evaluate_web_evidence_burden.meets_casual_burden vs adjudicated rater ground truth)",
        "locked_files_sha256": locked,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(locked)} files, SHA-256={_sha256(OUT)})")


if __name__ == "__main__":
    main()
