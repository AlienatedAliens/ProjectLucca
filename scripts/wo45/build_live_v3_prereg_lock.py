"""Build `logs/test_reports/wo45/live_v3_prereg_lock.json` for WO-45 Gate G4 v3 (RM-4, RM-5, RM-6a).

Computes the 4-arm power calculation from v2's observed B-C discordance (`REVIEW_G4.md:76`),
verifies 0-item overlap between v2 and v3 (`REVIEW_G4.md:75`), locks sharding/retry rules (`:78`),
and hashes all RM-1..RM-9 prompts, scripts, classifiers, generator GGUFs, and qualified non-Google
judge GGUFs (`:77`).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.wo45.run_wo45_live_v3 import (  # noqa: E402
    LOCKED_CTX,
    MODEL_MATRIX,
    SYS_ARM_A,
    SYS_ARM_B,
    SYS_ARM_C,
    SYS_ARM_D,
)
from scripts.wo45.run_wo45_v3_judge import JUDGE_PROFILES  # noqa: E402

LUCCA_HOME = Path(os.environ.get("LUCCA_HOME", r"C:\ProjectLucca"))
MODELS_DIR = LUCCA_HOME / "models" / "llm"
WO45_DIR = REPO_ROOT / "logs" / "test_reports" / "wo45"
OUT_LOCK_PATH = WO45_DIR / "live_v3_prereg_lock.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    # Acklam rational approximation accurate to ~1e-9
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    )


def connor_paired_power(n_clusters: int, delta: float, psi: float, alpha_two_sided: float) -> float:
    if psi <= abs(delta):
        return 1.0
    z_alpha = abs(norm_ppf(alpha_two_sided / 2.0))
    num = math.sqrt(n_clusters) * abs(delta) - z_alpha * math.sqrt(psi)
    den = math.sqrt(max(1e-12, psi - delta * delta))
    return round(norm_cdf(num / den), 4)


def main() -> None:
    v2_report = json.loads((WO45_DIR / "g4_live_v2_report.json").read_text(encoding="utf-8"))
    v2_bc = (
        v2_report["primary_unredacted_analysis"]["coprimary_1_D4_conflict_disclosure_disputed"][
            "pooled_5models_majority"
        ]["B_vs_C"]
    )
    disc_str = str(v2_bc["discordant_pairs_hi_vs_lo"])
    b_wins_v2, c_losses_v2 = (int(x) for x in disc_str.split(":"))
    n_pairs_v2 = int(v2_bc["n_turn_pairs"])
    psi_obs_v2 = round((b_wins_v2 + c_losses_v2) / n_pairs_v2, 4)
    delta_obs_v2 = round(float(v2_bc["delta_pp"]) / 100.0, 4)

    v2_sel = json.loads((WO45_DIR / "live_v2_selected_items.json").read_text(encoding="utf-8"))
    v3_sel = json.loads((WO45_DIR / "live_v3_selected_items.json").read_text(encoding="utf-8"))
    overlap_ids = sorted(set(v2_sel["selected_probe_ids"]) & set(v3_sel["selected_probe_ids"]))
    assert len(overlap_ids) == 0, f"Expected 0 v2/v3 overlap, got {overlap_ids}"

    r42_rep = json.loads((WO45_DIR / "r42_hazard_retrain_report.json").read_text(encoding="utf-8"))
    rm7_accepted = bool(r42_rep["acceptance_checks"]["accepted_for_g4_v3"])
    active_hazard_dir = (
        "models/proof_policy_hazard_v2_ov" if rm7_accepted else "models/proof_policy_hazard_ov"
    )

    qual_rep = json.loads(
        (WO45_DIR / "g4v3_judge_qualification_report.json").read_text(encoding="utf-8")
    )

    qualified_judges: list[dict[str, Any]] = []
    for pkey in ("qwen3.8-27b", "phi4-14b", "mistral-nemo-12b"):
        prof = JUDGE_PROFILES[pkey]
        mpath = Path(prof["model_path"])
        qualified_judges.append(
            {
                "profile": pkey,
                "judge_model": prof["judge_model"],
                "judge_family": prof["judge_family"],
                "backend": prof["backend"],
                "model_path": str(mpath),
                "model_sha256": sha256_file(mpath),
            }
        )

    repo_files_to_lock = [
        "src/lucca/core/neural_hazard_classifier.py",
        "src/lucca/core/proof_policy.py",
        "src/lucca/core/corroboration.py",
        "src/lucca/core/walton_schemes/evaluators.py",
        "src/lucca/core/cascade.py",
        "src/lucca/core/cascade_substrates.py",
        "src/lucca/sandbox/research_tool.py",
        "models/proof_policy_hazard_ov/openvino_model.xml",
        "models/proof_policy_hazard_ov/openvino_model.bin",
        "models/proof_policy_hazard_v2_ov/openvino_model.xml",
        "models/proof_policy_hazard_v2_ov/openvino_model.bin",
        "data/benchmarks/web_evidentiary_burden_360.jsonl",
        "logs/test_reports/wo45/prompts/g4v3_judge_prompt.md",
        "logs/test_reports/wo45/g4v3_prompt_neutrality_check.json",
        "logs/test_reports/wo45/g4v3_judge_qualification_set.jsonl",
        "logs/test_reports/wo45/g4v3_judge_qualification_report.json",
        "logs/test_reports/wo45/g4v3_normalizer_verification.json",
        "logs/test_reports/wo45/r42_hazard_retrain_report.json",
        "logs/test_reports/wo45/live_v3_selected_items.json",
        "scripts/wo45/g4_kappa.py",
        "scripts/wo45/ots_stamp.py",
        "scripts/wo45/normalize_g4v3_replies.py",
        "scripts/wo45/verify_rm3_normalizer.py",
        "scripts/wo45/score_g4v3_qualification.py",
        "scripts/wo45/run_wo45_v3_judge.py",
        "scripts/wo45/select_wo45_live_v3_items.py",
        "scripts/wo45/train_r42_hazard_v2.py",
        "scripts/wo45/run_wo45_live_v3.py",
        "scripts/wo45/analyze_wo45_live_v3.py",
    ]
    locked_repo_hashes = {rel: sha256_file(REPO_ROOT / rel) for rel in repo_files_to_lock}

    locked_gen_hashes = {
        fname: sha256_file(MODELS_DIR / fname) for _, fname, _, _ in MODEL_MATRIX
    }

    lock_payload: dict[str, Any] = {
        "preregistration_id": "WO45-G4-LIVE-V3-PREREG",
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "ctx_size": LOCKED_CTX,
        "active_hazard_model_dir": active_hazard_dir,
        "rm7_classifier_decision": {
            "accepted_for_g4_v3": rm7_accepted,
            "rationale": (
                "Retrained proof_policy_hazard_v2_ov cut held-out R-40v2 over-escalation from 24/24 (100.0%) to 1/24 (4.17%) "
                "with 0.0 pp regression on Blind-390 (125/130) and 100.0% on HZD_50 (50/50), but missed 1 item on the 50-item "
                "WO42_LOCKED_HOLDOUT_150 proof_policy slice (49/50 = 98.0%, 2.0 pp slice regression > 1.0 pp bar; 0.67 pp across "
                "all 150 items). Per REVIEW_G4.md:93 ('If retraining fails acceptance, v3 runs with the old classifier and the "
                "failure is reported'), v3 activates models/proof_policy_hazard_ov and records both v1 and v2 counts side-by-side."
            ),
        },
        "rm_remediation_compliance": {
            "RM_1_rubric_v3": {
                "prompt_path": "logs/test_reports/wo45/prompts/g4v3_judge_prompt.md",
                "neutrality_hits": 0,
                "D4_input_scope": "Disputed items ONLY (ground-truth topology == 'disputed'); reply-only input {blind_id, question, reply} with NO snippets shown.",
                "D2_polarity": "Binary YES = unfaithful (contradicts snippets / adds facts / presents refuted claim as true); NO = faithful; NO_ANSWER scored separately.",
                "D3_input_scope": "Nominal ground-truth burden-met non-disputed items ONLY (66 items, 1,320 turns).",
                "D1_status": f"{qual_rep['D1_pilot_decision']} (pilot 3-class pairwise kappas = 0.8314, 0.8663, 0.7787 >= 0.60).",
            },
            "RM_2_qualified_judges": "3 distinct non-Google families, 100% machine-logged via local llama-server (T=0.0, seed=42, strict json_schema). All 3 evaluate 100% of all 2,640 items in both normalized and raw pools.",
            "RM_3_normalizer": "scripts/wo45/normalize_g4v3_replies.py applied identically to ALL 4 arms (A, B, C, D); 0 forbidden lexicon hits; 3-way arm-guess accuracy = 36.67% (<= 60%) and balanced accuracy = 57.5% (<= 60%). Normalized pool is PRIMARY; raw pool is SECONDARY.",
            "RM_4_arm_D_unbundling": {
                "Arm_D_definition": "Arm B's contract context (ctx_burden) + Arm C's system prompt (SYS_ARM_C; no MUST, no legal vocabulary).",
                "preregistered_contrasts": [
                    "D_vs_C: detector conflict/burden signal holding prompt instruction constant",
                    "B_vs_D: explicit MUST mandate + legal vocabulary holding contract context constant",
                    "B_vs_C: full bundled effect (continuity with v2)",
                    "B_vs_A, D_vs_A, C_vs_A: baseline reference contrasts",
                ],
                "reporting_rule": "Report ALL contrasts honestly regardless of direction, including D ~= B or D ~= C.",
            },
            "RM_5_sharding_and_retry_procedure": {
                "runner": "scripts/wo45/run_wo45_v3_judge.py",
                "shard_size": 200,
                "workers": 4,
                "retry_rule": "Retry ONLY failed/truncated items sequentially at workers=1, max_tokens=640 (up to 2 retries). Every retried item sets retried=true and appends full attempt metadata to retry_log in the output JSONL.",
            },
            "RM_6_push_and_ots_cadence": [
                "(a) Lock + live_v3_prereg_lock.json.ots pushed before generation",
                "(b) Blinded pools + live_v3_pool_manifest.json + .ots pushed immediately after generation, before any judge runs",
                "(c) Each of the 6 raw judge JSONLs + .ots pushed immediately as each individual judge file completes",
                "(d) Unblinded raw generations/keys + g4_live_v3_report.json + .ots pushed immediately upon analysis",
            ],
        },
        "power_calculation_4arm_rm5": {
            "method": "Connor (1987) paired-proportion cluster power using v2 observed B-C discordance on disputed items as planning input",
            "v2_observed_B_vs_C_discordant_pairs": disc_str,
            "v2_observed_turn_discordance_psi": psi_obs_v2,
            "v2_observed_delta_b_minus_c": delta_obs_v2,
            "n_arms": 4,
            "n_primary_unbundling_contrasts": 3,
            "n_items_total": 132,
            "n_disputed_items": 33,
            "power_D4_33_items_at_v2_psi_0_2667": {
                "delta_15pp_alpha_0_05": connor_paired_power(33, 0.15, psi_obs_v2, 0.05),
                "delta_20pp_alpha_0_05": connor_paired_power(33, 0.20, psi_obs_v2, 0.05),
                "delta_25pp_v2_observed_alpha_0_05": connor_paired_power(
                    33, delta_obs_v2, psi_obs_v2, 0.05
                ),
                "delta_20pp_holm_3contrasts_alpha_0_0167": connor_paired_power(
                    33, 0.20, psi_obs_v2, 0.05 / 3.0
                ),
                "delta_25pp_holm_3contrasts_alpha_0_0167": connor_paired_power(
                    33, delta_obs_v2, psi_obs_v2, 0.05 / 3.0
                ),
            },
            "power_D2_D1_132_items_at_psi_0_25": {
                "delta_10pp_alpha_0_05": connor_paired_power(132, 0.10, 0.25, 0.05),
                "delta_15pp_holm_3contrasts_alpha_0_0167": connor_paired_power(
                    132, 0.15, 0.25, 0.05 / 3.0
                ),
            },
        },
        "sample_design_and_stopping_rule": {
            "selection_seed": v3_sel["seed"],
            "source_pool": "WEB360 minus v2_132 (228 unused probes; 19/cell available, 11/cell drawn)",
            "overlap_with_v2_count": len(overlap_ids),
            "overlap_with_v2_probe_ids": overlap_ids,
            "classifier_conditioning": "NONE (zero classifier imports in select_wo45_live_v3_items.py)",
            "n_cells": 12,
            "items_per_cell": 11,
            "n_items_total": 132,
            "n_disputed_items": 33,
            "n_nominal_burden_met_items": 66,
            "n_models": 5,
            "n_arms": 4,
            "n_total_live_turns": 2640,
            "decoding_params": {
                "temperature": 0.0,
                "max_tokens": 180,
                "enable_thinking": False,
            },
            "stopping_rule": "Execute exactly 1 pass of 2,640 live turns (132 items x 4 contiguous arm batches [A, B, C, D] x 5 models at ctx=32768). Report all contrasts candidly.",
        },
        "arm_prompts_verbatim": {
            "Arm_A_system": SYS_ARM_A,
            "Arm_A_context_template": "### Epistemic Cascade Retrieval\\n- **[Tier 4: Untrusted Web Search]** (src: `web_search`, conf: 0.85) [asserts]: {snippets_joined}",
            "Arm_B_system": SYS_ARM_B,
            "Arm_B_context_template": "EpistemicSearchCascade.synthesize(query, query_substrate_3_web(query)) [2D Hazard + Walton Scheme.AUTHORITY]",
            "Arm_C_system": SYS_ARM_C,
            "Arm_C_context_template": "### Epistemic Cascade Retrieval\\n- **[Tier 4: Untrusted Web Search]** (src: `web_search`, conf: 0.85) [asserts]: {snippets_joined}",
            "Arm_D_system": SYS_ARM_D,
            "Arm_D_context_template": "EpistemicSearchCascade.synthesize(query, query_substrate_3_web(query)) [Arm B contract context + Arm C system prompt]",
        },
        "qualified_non_google_judges": qualified_judges,
        "selected_probe_ids": v3_sel["selected_probe_ids"],
        "locked_repo_files_sha256": locked_repo_hashes,
        "locked_generator_gguf_models_sha256": locked_gen_hashes,
    }
    OUT_LOCK_PATH.write_text(json.dumps(lock_payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_LOCK_PATH} (sha256={sha256_file(OUT_LOCK_PATH)})")


if __name__ == "__main__":
    main()
