"""Build `logs/test_reports/nli_verifier_v2_prereg_lock.json` BEFORE authoring `nli_holdout_v2_120.jsonl`."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_LOCK_PATH = REPO_ROOT / "logs" / "test_reports" / "nli_verifier_v2_prereg_lock.json"
HOLDOUT_V2_PATH = REPO_ROOT / "data" / "benchmarks" / "nli_holdout_v2_120.jsonl"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if HOLDOUT_V2_PATH.exists():
        raise RuntimeError(
            f"Holdout corpus {HOLDOUT_V2_PATH} already exists! Lock must precede corpus generation."
        )

    files_to_lock = [
        "src/lucca/senses/verifier.py",
        "scripts/export_nli_deberta_v3_xsmall.py",
        "scripts/eval_nli_verifier_v2.py",
        "logs/test_reports/wo45/prompts/nli_v2_holdout_author_prompt.txt",
        "models/verifier_deberta_v3_xsmall_ov/openvino_model.xml",
        "models/verifier_deberta_v3_xsmall_ov/openvino_model.bin",
        "models/verifier_deberta_v3_xsmall_ov/tokenizer.json",
        "models/verifier_deberta_v3_xsmall_ov/config.json",
        "models/verifier_minilm/openvino_model.xml",
        "models/verifier_minilm/openvino_model.bin",
    ]
    locked_hashes: dict[str, str] = {}
    for rel in files_to_lock:
        fpath = REPO_ROOT / rel
        if not fpath.exists():
            fpath = Path(r"C:\ProjectLucca") / rel
        locked_hashes[rel] = sha256_file(fpath)

    payload = {
        "preregistration_id": "WO45-STEP4A-NLI-VERIFIER-V2-PREREG",
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "causal_order_rule": "Commit 1: lock + .ots -> Commit 2: blinded N=120 holdout corpus -> Commit 3: single-shot evaluation report",
        "candidate_model_id": "cross-encoder/nli-deberta-v3-xsmall",
        "baseline_model_id": "cross-encoder/nli-MiniLM2-L6-H768",
        "decision_policy_unchanged": {
            "uncertainty_band": [0.40, 0.60],
            "dominant_prob_threshold": 0.60,
            "timeout_ms": 50.0,
            "static_seq_len": 128,
        },
        "planned_holdout_corpus": {
            "path": "data/benchmarks/nli_holdout_v2_120.jsonl",
            "n_items": 120,
            "class_counts": {"ENTAILMENT": 40, "CONTRADICTION": 40, "NEUTRAL": 40},
            "domains": [
                "companion_memory",
                "desktop_tool_state",
                "schedule_logistics",
                "technical_system",
            ],
            "authoring_protocol": "Blinded subagent with zero repo/model/pairs_v1 access using verbatim prompt logs/test_reports/wo45/prompts/nli_v2_holdout_author_prompt.txt",
        },
        "acceptance_criteria": {
            "latency_p95_ms_max": 50.0,
            "entailment_recall_improvement_vs_minilm": "strictly higher on out-of-sample nli_holdout_v2_120",
            "contradiction_recall_floor": 0.90,
            "polarity_inversions_ent_con_max": 1,
        },
        "locked_files_sha256": locked_hashes,
    }
    OUT_LOCK_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[LOCK WRITTEN] {OUT_LOCK_PATH} (sha256={sha256_file(OUT_LOCK_PATH)})")


if __name__ == "__main__":
    main()
