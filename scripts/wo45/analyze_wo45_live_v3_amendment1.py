"""Pre-unblinding Amendment-1 locked analysis script for WO-45 Gate G4 v3.

Preserves `scripts/wo45/analyze_wo45_live_v3.py` 100% byte-for-byte intact (as hashed in
`live_v3_prereg_lock.json`) and imports all statistical functions (`resolve_pool_scores`,
`analyze_pool`, `cohen_kappa`, `load_jsonl_by_id`, `sha256_file`, `verify_ots_matches_file`)
directly from it so every bootstrap seed (`20261112`), endpoint population, and contrast is
mathematically identical while evaluating the upgraded 3-family non-Google judge panel:
  - `J1`: `Qwen3.8-27B-Ridge-GGUF` (`Alibaba-Qwen`)
  - `J2`: `phi-4-Q6_K` (`Microsoft-Phi`)
  - `J3`: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL` (`NVIDIA-Nemotron`)

Hashed inside `logs/test_reports/wo45/live_v3_prereg_amendment1_judge3_nemotron.json` (+ `.ots`)
and pushed to `origin/main` STRICTLY PRIOR to unblinding `g4_live_v3_raw_generations.json`,
`g4v3_normalized_2640_key.json`, and `g4v3_raw_2640_key.json`.
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

from scripts.wo45.analyze_wo45_live_v3 import (  # noqa: E402
    J1_NORM_PATH,
    J1_RAW_PATH,
    J2_NORM_PATH,
    J2_RAW_PATH,
    LOCK_PATH,
    MANIFEST_PATH,
    NORM_KEY_PATH,
    R42_REPORT_PATH,
    RAW_GEN_PATH,
    RAW_KEY_PATH,
    REPORT_JSON_OUT,
    REPORT_MD_OUT,
    WO45_DIR,
    analyze_pool,
    resolve_pool_scores,
    sha256_file,
)
from scripts.wo45.g4_kappa import cohen_kappa, load_jsonl_by_id  # noqa: E402
from scripts.wo45.ots_stamp import verify_ots_matches_file  # noqa: E402

AMENDMENT1_LOCK_PATH = WO45_DIR / "live_v3_prereg_amendment1_judge3_nemotron.json"
J3_NEMOTRON_NORM_PATH = WO45_DIR / "g4v3_norm_judge3_nemotron35_30b.jsonl"
J3_NEMOTRON_RAW_PATH = WO45_DIR / "g4v3_raw_judge3_nemotron35_30b.jsonl"


def relabel_judge3_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            (
                k.replace("judge3_mistral_nemo_12b", "judge3_nemotron35_30b")
                .replace("qwen38_vs_mistral_nemo", "qwen38_vs_nemotron35")
                .replace("phi4_vs_mistral_nemo", "phi4_vs_nemotron35")
            ): relabel_judge3_keys(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [relabel_judge3_keys(x) for x in obj]
    return obj


def compute_endpoint_irr_amendment1(
    pool_rows: list[dict[str, Any]],
    j1: dict[str, dict[str, Any]],
    j2: dict[str, dict[str, Any]],
    j3: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    all_ids = [str(r["blind_id"]) for r in pool_rows]
    disp_ids = [str(r["blind_id"]) for r in pool_rows if bool(r.get("eval_D4", False))]
    bmet_ids = [str(r["blind_id"]) for r in pool_rows if bool(r.get("eval_D3", False))]

    pairs = [
        ("qwen38_vs_phi4", j1, j2),
        ("qwen38_vs_nemotron35", j1, j3),
        ("phi4_vs_nemotron35", j2, j3),
    ]

    d4_disputed: dict[str, Any] = {}
    d3_burden_met: dict[str, Any] = {}
    d2_unfaithful_all: dict[str, Any] = {}
    no_answer_all: dict[str, Any] = {}
    d2_faithful_substantive_all: dict[str, Any] = {}
    d1_3class_all: dict[str, Any] = {}
    d1_accurate_bin_all: dict[str, Any] = {}

    for pname, ja, jb in pairs:
        d4_disputed[pname] = cohen_kappa(
            [str(ja[bid]["D4"]) for bid in disp_ids],
            [str(jb[bid]["D4"]) for bid in disp_ids],
        )
        d3_burden_met[pname] = cohen_kappa(
            [str(ja[bid]["D3"]) for bid in bmet_ids],
            [str(jb[bid]["D3"]) for bid in bmet_ids],
        )
        d2_unfaithful_all[pname] = cohen_kappa(
            [str(ja[bid]["D2"]) for bid in all_ids],
            [str(jb[bid]["D2"]) for bid in all_ids],
        )
        no_answer_all[pname] = cohen_kappa(
            [str(ja[bid]["NO_ANSWER"]) for bid in all_ids],
            [str(jb[bid]["NO_ANSWER"]) for bid in all_ids],
        )
        d2_faithful_substantive_all[pname] = cohen_kappa(
            [
                "1" if (str(ja[bid]["D2"]) == "NO" and str(ja[bid]["NO_ANSWER"]) == "NO") else "0"
                for bid in all_ids
            ],
            [
                "1" if (str(jb[bid]["D2"]) == "NO" and str(jb[bid]["NO_ANSWER"]) == "NO") else "0"
                for bid in all_ids
            ],
        )
        d1_3class_all[pname] = cohen_kappa(
            [str(ja[bid]["D1"]) for bid in all_ids],
            [str(jb[bid]["D1"]) for bid in all_ids],
        )
        d1_accurate_bin_all[pname] = cohen_kappa(
            ["1" if str(ja[bid]["D1"]) == "ACCURATE" else "0" for bid in all_ids],
            ["1" if str(jb[bid]["D1"]) == "ACCURATE" else "0" for bid in all_ids],
        )

    min_d4_kappa = min(float(v["cohen_kappa"]) for v in d4_disputed.values())
    return {
        "scored_population_sizes": {
            "D4_disputed_turns": len(disp_ids),
            "D3_nominal_burden_met_turns": len(bmet_ids),
            "D2_and_D1_all_turns": len(all_ids),
        },
        "D4_disputed_only_660_turns": d4_disputed,
        "D4_disputed_min_pairwise_kappa": round(min_d4_kappa, 4),
        "D4_disputed_all_pairs_ge_0_60_judge_robust": min_d4_kappa >= 0.60,
        "D3_nominal_burden_met_only_1320_turns": d3_burden_met,
        "D2_unfaithful_yes_2640_turns": d2_unfaithful_all,
        "NO_ANSWER_yes_2640_turns": no_answer_all,
        "D2_faithful_substantive_2640_turns": d2_faithful_substantive_all,
        "D1_3class_2640_turns": d1_3class_all,
        "D1_accurate_binary_2640_turns": d1_accurate_bin_all,
    }


def verify_integrity_amendment1() -> dict[str, Any]:
    # 1. Verify original pre-generation lock (`4a6ecdd`) has 0 tampered files
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked_files: dict[str, str] = lock["locked_repo_files_sha256"]
    for rel_path, exp_sha in locked_files.items():
        act_sha = sha256_file(REPO_ROOT / rel_path)
        if act_sha != exp_sha:
            raise RuntimeError(f"Locked v3 file tampered: {rel_path} ({act_sha} != {exp_sha})")

    # 2. Verify pre-unblinding Amendment-1 lock has 0 tampered files
    amend = json.loads(AMENDMENT1_LOCK_PATH.read_text(encoding="utf-8"))
    amend_files: dict[str, str] = amend["amendment1_locked_repo_files_sha256"]
    for rel_path, exp_sha in amend_files.items():
        act_sha = sha256_file(REPO_ROOT / rel_path)
        if act_sha != exp_sha:
            raise RuntimeError(
                f"Locked Amendment-1 file tampered: {rel_path} ({act_sha} != {exp_sha})"
            )

    # 3. Verify pool manifest (`c5ec1fd`) zero-hit lexicon scan & sealed commitments
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not bool(manifest["normalized_pool_lexicon_scan"]["zero_hits_verified"]):
        raise RuntimeError("Normalized pool lexicon scan did not pass zero-hits check!")

    sealed: dict[str, str] = manifest["sealed_commitments_sha256"]
    for fname, path in [
        ("g4_live_v3_raw_generations.json", RAW_GEN_PATH),
        ("g4v3_normalized_2640_key.json", NORM_KEY_PATH),
        ("g4v3_raw_2640_key.json", RAW_KEY_PATH),
    ]:
        act_sha = sha256_file(path)
        if act_sha != sealed[fname]:
            raise RuntimeError(
                f"Sealed commitment mismatch on {fname}: {act_sha} != {sealed[fname]}"
            )

    # 4. Verify all 6 raw judge JSONLs exist with distinct SHA-256s + valid OTS proofs
    judge_paths = [
        J1_NORM_PATH,
        J2_NORM_PATH,
        J3_NEMOTRON_NORM_PATH,
        J1_RAW_PATH,
        J2_RAW_PATH,
        J3_NEMOTRON_RAW_PATH,
    ]
    judge_shas = {p.name: sha256_file(p) for p in judge_paths}
    if len(set(judge_shas.values())) != len(judge_paths):
        raise RuntimeError(f"Duplicate SHA-256 across judge files: {judge_shas}")

    ots_targets = [LOCK_PATH, AMENDMENT1_LOCK_PATH, MANIFEST_PATH, *judge_paths]
    ots_verified: dict[str, Any] = {}
    for tpath in ots_targets:
        ots_res = verify_ots_matches_file(tpath, Path(f"{tpath}.ots"))
        ots_verified[tpath.name] = ots_res["ots_sha256"]

    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "lock_sha256": sha256_file(LOCK_PATH),
        "amendment1_lock_sha256": sha256_file(AMENDMENT1_LOCK_PATH),
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "sealed_commitments_verified": True,
        "normalized_pool_zero_lexicon_hits_verified": True,
        "judge_files_sha256": judge_shas,
        "judge_hashes_distinct": True,
        "ots_proofs_sha256": ots_verified,
    }


def render_markdown_amendment1(report: dict[str, Any]) -> str:
    norm = report["primary_normalized_pool_analysis"]
    raw = report["secondary_raw_pool_analysis"]
    irr_n = report["inter_rater_reliability_normalized_primary"]
    irr_r = report["inter_rater_reliability_raw_secondary"]

    lines = [
        "# WO-45 Gate G4 v3 Pre-Registered Live Evaluation Report",
        "",
        f"- **Generated (UTC):** `{report['generated_at_utc']}`",
        f"- **Pre-Registration Lock SHA-256:** `{report['integrity_verification']['lock_sha256']}`",
        f"- **Pre-Unblinding Judge-3 Upgrade Amendment SHA-256:** `{report['integrity_verification']['amendment1_lock_sha256']}`",
        f"- **Active Hazard Classifier (`RM-7`):** `{report['active_hazard_model_dir']}`",
        "- **Design:** `N = 132` fresh stratified `WEB360` items (`0` overlap with `v2`; `11/cell`, `33` disputed) x `5` Gemma-4 `Q6_K` models (`4 heretic` + `1 stock E4B-it`) x `4` arms (`A`, `B`, `C`, `D`) = `2,640` live turns at `ctx=32768`.",
        "- **Judges (`RM-2` 3 Qualified Non-Google Families, Machine-Logged `T=0, seed=42`):** `J1` `Qwen3.8-27B-Ridge-GGUF` (`Alibaba-Qwen`), `J2` `phi-4-Q6_K` (`Microsoft-Phi`), `J3` `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL` (`NVIDIA-Nemotron`).",
        f"- **Disputed-Population `D4` Judge-Robustness Check (`kappa >= 0.60` all pairs):** Primary Normalized = `{irr_n['D4_disputed_all_pairs_ge_0_60_judge_robust']}` (min `kappa = {irr_n['D4_disputed_min_pairwise_kappa']}`); Secondary Raw = `{irr_r['D4_disputed_all_pairs_ge_0_60_judge_robust']}` (min `kappa = {irr_r['D4_disputed_min_pairwise_kappa']}`).",
        "",
        "## 1. Endpoint-Population Inter-Judge Agreement (`RM-9`)",
        "",
        "| Pool | Endpoint & Scored Population | `Qwen3.8` vs `Phi-4` | `Qwen3.8` vs `Nemotron-3.5-30B` | `Phi-4` vs `Nemotron-3.5-30B` |",
        "|---|---|---:|---:|---:|",
    ]
    for pool_lbl, irr_obj in [("Primary Normalized", irr_n), ("Secondary Raw", irr_r)]:
        for ep_lbl, key in [
            ("`D4` (`660` disputed turns ONLY)", "D4_disputed_only_660_turns"),
            ("`D3` (`1,320` nominal burden-met turns ONLY)", "D3_nominal_burden_met_only_1320_turns"),
            ("`D2` unfaithful `YES` (`2,640` turns)", "D2_unfaithful_yes_2640_turns"),
            ("`D2` faithful substantive (`2,640` turns)", "D2_faithful_substantive_2640_turns"),
            ("`D1` 3-class (`2,640` turns)", "D1_3class_2640_turns"),
        ]:
            m = irr_obj[key]
            lines.append(
                f"| {pool_lbl} | {ep_lbl} | "
                f"`{m['qwen38_vs_phi4']['cohen_kappa']}` (`{m['qwen38_vs_phi4']['raw_agreement_pct']}%`) | "
                f"`{m['qwen38_vs_nemotron35']['cohen_kappa']}` (`{m['qwen38_vs_nemotron35']['raw_agreement_pct']}%`) | "
                f"`{m['phi4_vs_nemotron35']['cohen_kappa']}` (`{m['phi4_vs_nemotron35']['raw_agreement_pct']}%`) |"
            )

    lines.extend(
        [
            "",
            "## 2. Co-Primary 1: `D4` Conflict Disclosure on Disputed Items (`N_eff = 33` items, `165` turns/arm)",
            "",
            "| Pool & Contrast | Arm Hi (`k/N, % [Item-Boot 95% CI]`) | Arm Lo (`k/N, % [Item-Boot 95% CI]`) | Cluster-Bootstrap Delta (`[95% CI]`) | Bootstrap `p` | Discordant |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for pool_lbl, pobj in [("Primary Normalized", norm), ("Secondary Raw", raw)]:
        c_map = pobj["coprimary_1_D4_conflict_disclosure_disputed"]["pooled_5models_majority"]
        for cname, desc, hi, lo in [
            ("D_vs_C", "`D vs C` (Detector Signal Alone)", "D", "C"),
            ("B_vs_D", "`B vs D` (Mandate + Legal Vocab)", "B", "D"),
            ("B_vs_C", "`B vs C` (Full Gate vs Generic Tip)", "B", "C"),
            ("B_vs_A", "`B vs A` (Full Gate vs Plain Baseline)", "B", "A"),
            ("D_vs_A", "`D vs A` (Contract Context + C Prompt vs Baseline)", "D", "A"),
            ("C_vs_A", "`C vs A` (Generic Tip vs Plain Baseline)", "C", "A"),
        ]:
            row = c_map[cname]
            ah = row[f"arm_{hi}"]
            al = row[f"arm_{lo}"]
            lines.append(
                f"| {pool_lbl} {desc} | `{ah['k']}/{ah['n']} ({ah['pct']}%)` `{ah['item_cluster_bootstrap_95_ci_pct']}` | "
                f"`{al['k']}/{al['n']} ({al['pct']}%)` `{al['item_cluster_bootstrap_95_ci_pct']}` | "
                f"`{row['delta_pp']:+.2f} pp` `{row['cluster_bootstrap_95_ci_pp']}` | "
                f"`{row['cluster_bootstrap_two_sided_p']}` | `{row['discordant_pairs_hi_vs_lo']}` |"
            )

    lines.extend(
        [
            "",
            "## 3. Co-Primary 2 (`D2`) & Co-Primary 3 (`D1`) Primary Normalized Contrasts (`N_eff = 132` items, `660` turns/arm)",
            "",
            "| Endpoint & Contrast | Arm Hi (`k/N, %`) | Arm Lo (`k/N, %`) | Cluster-Bootstrap Delta (`[95% CI]`) | Bootstrap `p` |",
            "|---|---|---|---|---:|",
        ]
    )
    for ep_lbl, c_map in [
        (
            "`D2` Unfaithful `YES` (lower better)",
            norm["coprimary_2_D2_faithfulness_all"]["D2_unfaithful_yes_lower_is_better"][
                "pooled_5models_majority"
            ],
        ),
        (
            "`D2` Faithful Substantive (higher better)",
            norm["coprimary_2_D2_faithfulness_all"][
                "D2_faithful_substantive_no_contradiction_and_answered"
            ]["pooled_5models_majority"],
        ),
        (
            "`D1` `ACCURATE` Calibration",
            norm["coprimary_3_D1_epistemic_calibration_all"]["all_132_items_majority"]["contrasts"],
        ),
    ]:
        for cname, hi, lo in [("D_vs_C", "D", "C"), ("B_vs_D", "B", "D"), ("B_vs_C", "B", "C")]:
            row = c_map[cname]
            ah = row[f"arm_{hi}"]
            al = row[f"arm_{lo}"]
            lines.append(
                f"| {ep_lbl} `{cname}` | `{ah['k']}/{ah['n']} ({ah['pct']}%)` | "
                f"`{al['k']}/{al['n']} ({al['pct']}%)` | "
                f"`{row['delta_pp']:+.2f} pp` `{row['cluster_bootstrap_95_ci_pp']}` | "
                f"`{row['cluster_bootstrap_two_sided_p']}` |"
            )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    integrity = verify_integrity_amendment1()
    raw_gen = json.loads(RAW_GEN_PATH.read_text(encoding="utf-8"))
    raw_turns: list[dict[str, Any]] = raw_gen["turn_records"]

    item_meta: dict[str, dict[str, Any]] = {}
    for r in raw_turns:
        pid = str(r["probe_id"])
        if pid not in item_meta:
            item_meta[pid] = {
                "nominal_stratum": r["nominal_stratum"],
                "topology": r["topology"],
                "nominal_burden_met": bool(r["nominal_burden_met"]),
                "active_hazard_model_dir": r["active_hazard_model_dir"],
                "npu_predicted_hazard": r["npu_predicted_hazard"],
                "meets_casual_burden": bool(r["meets_casual_burden"]),
                "disputed_flag": bool(r["disputed_flag"]),
                "v1_predicted_hazard": r["v1_predicted_hazard"],
                "v1_meets_casual_burden": bool(r["v1_meets_casual_burden"]),
                "v2_predicted_hazard": r["v2_predicted_hazard"],
                "v2_meets_casual_burden": bool(r["v2_meets_casual_burden"]),
            }

    norm_pool_rows = [
        json.loads(ln)
        for ln in (WO45_DIR / "g4v3_normalized_2640_replies.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    raw_pool_rows = [
        json.loads(ln)
        for ln in (WO45_DIR / "g4v3_raw_2640_replies.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]

    norm_key = json.loads(NORM_KEY_PATH.read_text(encoding="utf-8"))
    raw_key = json.loads(RAW_KEY_PATH.read_text(encoding="utf-8"))

    j1_n = load_jsonl_by_id(J1_NORM_PATH)
    j2_n = load_jsonl_by_id(J2_NORM_PATH)
    j3_n = load_jsonl_by_id(J3_NEMOTRON_NORM_PATH)

    j1_r = load_jsonl_by_id(J1_RAW_PATH)
    j2_r = load_jsonl_by_id(J2_RAW_PATH)
    j3_r = load_jsonl_by_id(J3_NEMOTRON_RAW_PATH)

    irr_norm = compute_endpoint_irr_amendment1(norm_pool_rows, j1_n, j2_n, j3_n)
    irr_raw = compute_endpoint_irr_amendment1(raw_pool_rows, j1_r, j2_r, j3_r)

    scored_norm = resolve_pool_scores(raw_turns, norm_key, j1_n, j2_n, j3_n, is_normalized=True)
    scored_raw = resolve_pool_scores(raw_turns, raw_key, j1_r, j2_r, j3_r, is_normalized=False)

    primary_norm = relabel_judge3_keys(analyze_pool(scored_norm, item_meta))
    secondary_raw = relabel_judge3_keys(analyze_pool(scored_raw, item_meta))

    r42_summary = (
        json.loads(R42_REPORT_PATH.read_text(encoding="utf-8"))["acceptance_checks"]
        if R42_REPORT_PATH.exists()
        else None
    )

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "active_hazard_model_dir": raw_gen["active_hazard_model_dir"],
        "rm7_r42_acceptance_summary": r42_summary,
        "integrity_verification": integrity,
        "models_provenance": raw_gen["models"],
        "inter_rater_reliability_normalized_primary": irr_norm,
        "inter_rater_reliability_raw_secondary": irr_raw,
        "primary_normalized_pool_analysis": primary_norm,
        "secondary_raw_pool_analysis": secondary_raw,
    }
    REPORT_JSON_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    REPORT_MD_OUT.write_text(render_markdown_amendment1(report), encoding="utf-8")
    print(f"Wrote {REPORT_JSON_OUT} and {REPORT_MD_OUT}", flush=True)


if __name__ == "__main__":
    main()
