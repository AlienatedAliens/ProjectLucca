"""Build WO-45 R-33 causal pre-registration lock before authoring fresh holdout corpus."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "logs" / "test_reports" / "wo45" / "r33_sybil_holdout_prereg_lock.json"

FILES_TO_LOCK = [
    "src/lucca/core/proof_policy.py",
    "src/lucca/core/corroboration.py",
    "src/lucca/core/walton_schemes/__init__.py",
    "src/lucca/core/walton_schemes/evaluators.py",
    "src/lucca/core/walton_schemes/dedup.py",
    "src/lucca/core/neural_hazard_classifier.py",
    "models/proof_policy_hazard_v3_ov/openvino_model.xml",
    "models/proof_policy_hazard_v3_ov/openvino_model.bin",
    "models/proof_policy_hazard_v3_ov/tokenizer.json",
    "models/verifier_deberta_v3_xsmall_ov/openvino_model.xml",
    "models/verifier_deberta_v3_xsmall_ov/openvino_model.bin",
    "models/verifier_deberta_v3_xsmall_ov/tokenizer.json",
    "logs/test_reports/wo45/prompts/r33_sybil_holdout_author_prompt.txt",
    "logs/test_reports/wo45/r33_pre_dedup_dev_baseline.json",
    "scripts/wo45/eval_r33_sybil_dedup.py",
]


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    locked: dict[str, str] = {}
    for rel in FILES_TO_LOCK:
        p = REPO / rel
        if not p.exists():
            raise FileNotFoundError(f"Missing required lock file: {rel}")
        locked[rel] = _sha256(p)

    doc = {
        "preregistration_id": "WO45-R33-SYBIL-DEDUP-HOLDOUT-v1",
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "sample_size": 45,
        "strata": {
            "verbatim_3domain": 15,
            "wire_syndicated_3outlet": 15,
            "sybil_3_vs_1_contrary": 15,
        },
        "disjoint_domain_set": "Domain Set B (maritime navigation, metallurgy, architectural acoustics, civil hydrology, compiler optimization, clinical toxicology, NIST/FIPS cryptography, aviation meteorology)",
        "primary_endpoint": "false_corroboration_rate (independent_sources_count > 1 on copied/syndicated sets OR missed dispute / sybil inflation on sybil_3_vs_1_contrary)",
        "secondary_endpoints": [
            "false_burden_pass_rate_on_should_fail",
            "false_dispute_on_non_disputed",
        ],
        "locked_files_sha256": locked,
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(locked)} files, SHA-256={_sha256(OUT)})")


if __name__ == "__main__":
    main()
