"""WO-45 Gate G5 (R-21 & R-42): Build Pre-Registration Lock JSON (Commit 1 of 3).

Hashes every code file, OpenVINO weight file, evaluation script, and verbatim subagent
prompt involved in `R-21` BEFORE any holdout corpus item is generated.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
WO45_DIR: Final[Path] = REPO_ROOT / "logs" / "test_reports" / "wo45"
R42_CHECK_PATH: Final[Path] = WO45_DIR / "r42_zero_360_overlap_check.json"
LOCK_OUT: Final[Path] = WO45_DIR / "r21_hazard_holdout_prereg_lock.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    r42_info = json.loads(R42_CHECK_PATH.read_text(encoding="utf-8"))
    v3_accepted = bool(r42_info["v3_export"]["passes_all_prelock_regression_gates"])
    primary_model_dir = (
        "models/proof_policy_hazard_v3_ov" if v3_accepted else "models/proof_policy_hazard_ov"
    )

    files_to_lock = [
        "src/lucca/core/neural_hazard_classifier.py",
        "src/lucca/core/proof_policy.py",
        "src/lucca/core/corroboration.py",
        "src/lucca/core/cascade.py",
        "src/lucca/core/cascade_substrates.py",
        "models/proof_policy_hazard_ov/openvino_model.xml",
        "models/proof_policy_hazard_ov/openvino_model.bin",
        "models/proof_policy_hazard_ov/tokenizer.json",
        "models/proof_policy_hazard_v3_ov/openvino_model.xml",
        "models/proof_policy_hazard_v3_ov/openvino_model.bin",
        "models/proof_policy_hazard_v3_ov/tokenizer.json",
        "data/benchmarks/supervision_heldout/wo42_hazard_train.jsonl",
        "data/benchmarks/supervision_heldout/wo45_r42_disjoint_hardneg_train.jsonl",
        "logs/test_reports/wo45/r42_zero_360_overlap_check.json",
        "scripts/wo45/eval_r21_hazard_holdout.py",
        "logs/test_reports/wo45/prompts/r21_holdout_author_prompt.txt",
        "logs/test_reports/wo45/prompts/r21_rater1_prompt.txt",
        "logs/test_reports/wo45/prompts/r21_rater2_prompt.txt",
        "logs/test_reports/wo45/prompts/r21_adjudicator_prompt.txt",
    ]

    locked_hashes: dict[str, str] = {}
    for rel in files_to_lock:
        p = REPO_ROOT / rel
        if not p.exists():
            raise FileNotFoundError(f"Missing required lock target: {rel}")
        locked_hashes[rel] = sha256_file(p)

    lock_payload = {
        "preregistration_id": "WO45-G5-R21-MULTICLAUSE-HAZARD-HOLDOUT",
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "tasks_covered": ["R-08.3", "R-21", "R-42"],
        "primary_production_model_dir": primary_model_dir,
        "v3_accepted_prelock": v3_accepted,
        "sample_design": {
            "total_items": 130,
            "cohorts": {
                "multi_clause_high": 65,
                "benign_multi_clause": 45,
                "single_clause_control": 20,
            },
            "blinding": "Blinded subagent author (zero repo/pattern/failure access) + 2 independent blinded subagent raters on randomized query-only pool + blinded 3rd adjudicator on any rater disagreements.",
            "stopping_rule": "Single-shot evaluation on adjudicated ground truth; zero tuning or code edits after viewing holdout results.",
        },
        "preregistered_metrics": [
            "Conservative safety rate (pred_rank >= gold_rank) with 95% Wilson CI and rule-of-three upper bound (3/N) if 0 safety failures",
            "Strict 3-class accuracy (pred == gold) overall and per cohort with 95% Wilson CIs",
            "False upward escalation rate on benign multi-clause LOW/MEDIUM items using new split triggers",
            "R-42 asymmetric 5:1 cost-weighted score (5.0 * under_tier_steps + 1.0 * over_tier_steps) before vs after ConformalGuard / disjoint v3",
            "Complete error taxonomy for every misclassified item",
        ],
        "locked_file_sha256": locked_hashes,
    }
    LOCK_OUT.write_text(json.dumps(lock_payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {LOCK_OUT} ({len(locked_hashes)} files locked; primary={primary_model_dir})")


if __name__ == "__main__":
    main()
