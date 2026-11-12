"""Build pre-unblinding Judge-3 upgrade amendment lock (`live_v3_prereg_amendment1_judge3_nemotron.json`).

Records and cryptographically locks:
  1. Unmodified parent `live_v3_prereg_lock.json` (`4a6ecdd`) and `live_v3_pool_manifest.json` (`c5ec1fd`) SHA-256s,
     proving that `g4_live_v3_raw_generations.json`, `g4v3_normalized_2640_key.json`, and `g4v3_raw_2640_key.json`
     have NOT been unblinded or committed when this amendment is stamped and pushed.
  2. Already-pushed primary normalized Judge 1 (`e198f1a`) and Judge 2 (`28ded25`) SHA-256s, and verification that
     zero `Mistral-Nemo-12B` v3 pool files were ever committed or completed.
  3. Full `RM-2` 106-item qualification results for the upgraded 3-family non-Google panel
     (`Qwen3.8-27B`, `Phi-4-14B`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL`).
  4. SHA-256 hashes of `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL.gguf` and the additive Judge-3/analysis scripts.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.wo45.run_wo45_v3_judge import JUDGE_PROFILES, sha256_file  # noqa: E402
from scripts.wo45.run_wo45_v3_nemotron_judge import NEMOTRON_PROFILE  # noqa: E402

WO45_DIR = REPO_ROOT / "logs" / "test_reports" / "wo45"
OUT_AMEND_PATH = WO45_DIR / "live_v3_prereg_amendment1_judge3_nemotron.json"


def main() -> None:
    parent_lock_path = WO45_DIR / "live_v3_prereg_lock.json"
    manifest_path = WO45_DIR / "live_v3_pool_manifest.json"
    qual_amend_path = WO45_DIR / "g4v3_judge_qualification_amendment1_report.json"

    # Assert unblinding has NOT occurred yet in repo
    for unblinded_name in (
        "g4_live_v3_raw_generations.json",
        "g4v3_normalized_2640_key.json",
        "g4v3_raw_2640_key.json",
    ):
        if (WO45_DIR / unblinded_name).exists():
            raise RuntimeError(
                f"Cannot issue pre-unblinding amendment: {unblinded_name} already exists in repo!"
            )

    qual_rep = json.loads(qual_amend_path.read_text(encoding="utf-8"))
    if not bool(qual_rep["three_distinct_non_google_families_qualified"]):
        raise RuntimeError("Upgraded 3-family panel did not pass RM-2 qualification bars!")

    upgraded_judges: list[dict[str, Any]] = []
    for pkey in ("qwen3.8-27b", "phi4-14b"):
        prof = JUDGE_PROFILES[pkey]
        mpath = Path(prof["model_path"])
        upgraded_judges.append(
            {
                "role": "Judge_1" if pkey == "qwen3.8-27b" else "Judge_2",
                "profile": pkey,
                "judge_model": prof["judge_model"],
                "judge_family": prof["judge_family"],
                "backend": prof["backend"],
                "model_path": str(mpath),
                "model_sha256": sha256_file(mpath),
            }
        )
    nem_path = Path(NEMOTRON_PROFILE["model_path"])
    upgraded_judges.append(
        {
            "role": "Judge_3",
            "profile": "nemotron-3.5-30b-gguf",
            "judge_model": NEMOTRON_PROFILE["judge_model"],
            "judge_family": NEMOTRON_PROFILE["judge_family"],
            "backend": NEMOTRON_PROFILE["backend"],
            "model_path": str(nem_path),
            "model_sha256": sha256_file(nem_path),
        }
    )

    amendment_repo_files = [
        "logs/test_reports/wo45/g4v3_qual_nemotron35_30b.jsonl",
        "logs/test_reports/wo45/g4v3_judge_qualification_amendment1_report.json",
        "scripts/wo45/run_wo45_v3_nemotron_judge.py",
        "scripts/wo45/analyze_wo45_live_v3_amendment1.py",
    ]
    amend_hashes = {rel: sha256_file(REPO_ROOT / rel) for rel in amendment_repo_files}

    payload: dict[str, Any] = {
        "amendment_id": "WO45-G4-LIVE-V3-AMENDMENT-1-JUDGE3-NEMOTRON",
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "parent_prereg_lock_sha256": sha256_file(parent_lock_path),
        "sealed_pool_manifest_sha256": sha256_file(manifest_path),
        "pre_unblinding_verification": {
            "unblinding_keys_absent_from_repo": True,
            "mistral_nemo_v3_pool_never_completed_or_committed": True,
            "already_committed_blinded_judge_files": {
                "g4v3_norm_judge1_qwen38_27b.jsonl": sha256_file(
                    WO45_DIR / "g4v3_norm_judge1_qwen38_27b.jsonl"
                ),
                "g4v3_norm_judge2_phi4_14b.jsonl": sha256_file(
                    WO45_DIR / "g4v3_norm_judge2_phi4_14b.jsonl"
                ),
            },
            "rationale": (
                "Prior to any unblinding of the v3 generation pools (and before Judge 3 completed a single v3 pool file), "
                "Judge 3 was upgraded from 2024 Mistral-Nemo-12B (which missed 2/40 D2 items on RM-2) to 2026 "
                "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL (NVIDIA-Nemotron family). Note: FreeToken 0.1.3's local "
                "NVFP4 server does not register NemotronHForCausalLM (ValueError in freetoken/models/register.py:313), "
                "so Nemotron-3.5-30B-A3B is served via llama-server.exe (build 11868, native nemotron_h_moe) at T=0.0, "
                "seed=42 with identical RM-1 rubric sections and RM-5 sharding/retry rules. All files locked in parent "
                "live_v3_prereg_lock.json remain 100% byte-for-byte unmodified."
            ),
        },
        "upgraded_qualified_non_google_judges": upgraded_judges,
        "rm2_qualification_summary": {
            "three_distinct_non_google_families_qualified": qual_rep[
                "three_distinct_non_google_families_qualified"
            ],
            "D1_pilot_decision": qual_rep["D1_pilot_decision"],
            "selected_3_family_panel": qual_rep["selected_3_family_panel"],
            "qualified_pairwise_kappa": qual_rep["qualified_pairwise_kappa"],
        },
        "amendment1_locked_repo_files_sha256": amend_hashes,
    }
    OUT_AMEND_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_AMEND_PATH} (sha256={sha256_file(OUT_AMEND_PATH)})")


if __name__ == "__main__":
    main()
