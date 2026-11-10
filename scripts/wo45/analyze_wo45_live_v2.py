"""Pre-registered, SHA-256 hash-locked analysis script for WO-45 Gate G4 (G4-1..G4-6, R-11..R-17).

IMPORTANT: This file is hashed inside logs/test_reports/wo45/live_v2_prereg_lock.json BEFORE
any LLM generation or judging occurs. Do NOT edit a single byte after locking.

Implements:
  1. Lock & sealed-manifest SHA-256 verification (confirming raw generations, unblinding keys,
     and this script itself match pre-judging commitments).
  2. Pairwise 3-class and binary Cohen's kappa across the 3 distinct judge families:
     - Judge 1: Google Gemini (g4_judge1_gemini.jsonl)
     - Judge 2: Mistral AI (g4_judge2_mistral.jsonl)
     - Judge 3 Adjudicator: Alibaba Qwen (g4_judge3_qwen_adjudication.jsonl)
  3. Pre-registered binary endpoint mapping and 2-of-3 family-balanced majority tie-break rule
     (zero 3-way ties possible on {0, 1}), alongside Judge 1 alone and Judge 2 alone sensitivity.
  4. Paired cluster bootstrap over items (10,000 resamples, seed=20261111) for B-C, B-A, C-A on:
     - Co-Primary 1: D4 (YES vs NO/N/A) conflict disclosure on disputed items (N_eff=33 items).
     - Co-Primary 2: D2 (CORRECT vs INCORRECT/NO_ANSWER) factual correctness (N_eff=132 items).
     - Secondary 1 (R-16): D3 (YES vs NO/N/A) over-hedge rate on nominal & runtime burden-met items.
     - Secondary 2 (R-12): Pre-declared upward-escalated subgroup (N_eff=31 items from R-40v2 73 set).
     - Secondary 3: D1 (ACCURATE vs OVERCONFIDENT/UNDERCONFIDENT) across strata.
     - Secondary 4 (G4-4): [STANDARD]-redacted pool analysis on all endpoints.
     - Secondary 5 (R-17): Matched-size E4B-stock vs E4B-heretic comparison with exact McNemar.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.wo45.g4_kappa import cohen_kappa, load_jsonl_by_id  # noqa: E402

WO45_DIR = REPO_ROOT / "logs" / "test_reports" / "wo45"

LOCK_PATH = WO45_DIR / "live_v2_prereg_lock.json"
MANIFEST_PATH = WO45_DIR / "live_v2_pool_manifest.json"
RAW_GEN_PATH = WO45_DIR / "g4_live_v2_raw_generations.json"
UNRED_KEY_PATH = WO45_DIR / "g4_blinded_1980_key.json"
RED_KEY_PATH = WO45_DIR / "g4_redacted_1980_key.json"
R40V2_PATH = WO45_DIR / "r40v2_upward_escalations_audit.json"

J1_UNRED_PATH = WO45_DIR / "g4_judge1_gemini.jsonl"
J2_UNRED_PATH = WO45_DIR / "g4_judge2_mistral.jsonl"
J3_UNRED_PATH = WO45_DIR / "g4_judge3_qwen_adjudication.jsonl"

J1_RED_PATH = WO45_DIR / "g4_redacted_judge1_gemini.jsonl"
J2_RED_PATH = WO45_DIR / "g4_redacted_judge2_mistral.jsonl"
J3_RED_PATH = WO45_DIR / "g4_redacted_judge3_qwen_adjudication.jsonl"

REPORT_JSON_OUT = WO45_DIR / "g4_live_v2_report.json"
REPORT_MD_OUT = WO45_DIR / "g4_live_v2_REPORT.md"

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261111

MODEL_ORDER = (
    "E2B-heretic",
    "E4B-heretic",
    "E4B-stock",
    "12B-heretic",
    "26B-A4B-heretic",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wilson_ci_95(k: int, n: int) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denom
    return [round(max(0.0, 100.0 * (center - half)), 2), round(min(100.0, 100.0 * (center + half)), 2)]


def exact_mcnemar_two_sided(b_wins: int, c_losses: int) -> float:
    m = b_wins + c_losses
    if m == 0:
        return 1.0
    k = min(b_wins, c_losses)
    # Exact two-sided binomial p = min(1.0, 2 * sum_{i=0..k} C(m, i) / 2^m)
    log2_m = m * math.log(2.0)
    tail = 0.0
    for i in range(k + 1):
        log_choose = math.lgamma(m + 1) - math.lgamma(i + 1) - math.lgamma(m - i + 1)
        tail += math.exp(log_choose - log2_m)
    return min(1.0, 2.0 * tail)


def is_nominal_burden_met(stratum: str, topology: str) -> bool:
    if topology == "disputed":
        return False
    if stratum == "LOW":
        return topology in ("1_source", "2_source", "3_source")
    if stratum == "MEDIUM":
        return topology in ("2_source", "3_source")
    if stratum == "HIGH":
        return topology == "3_source"
    return False


def verify_integrity() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked_files: dict[str, str] = lock["locked_repo_files_sha256"]
    for rel_path, exp_sha in locked_files.items():
        act_sha = sha256_file(REPO_ROOT / rel_path)
        if act_sha != exp_sha:
            raise RuntimeError(f"Locked file tampered: {rel_path} ({act_sha} != {exp_sha})")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sealed: dict[str, str] = manifest["sealed_commitments_sha256"]
    for fname, path in [
        ("g4_live_v2_raw_generations.json", RAW_GEN_PATH),
        ("g4_blinded_1980_key.json", UNRED_KEY_PATH),
        ("g4_redacted_1980_key.json", RED_KEY_PATH),
    ]:
        act_sha = sha256_file(path)
        if act_sha != sealed[fname]:
            raise RuntimeError(
                f"Sealed commitment mismatch on {fname}: {act_sha} != {sealed[fname]}"
            )

    judge_paths = [
        J1_UNRED_PATH,
        J2_UNRED_PATH,
        J3_UNRED_PATH,
        J1_RED_PATH,
        J2_RED_PATH,
        J3_RED_PATH,
    ]
    judge_shas = {p.name: sha256_file(p) for p in judge_paths}
    non_empty_shas = [sha for p, sha in zip(judge_paths, judge_shas.values(), strict=True) if p.stat().st_size > 0]
    if len(set(non_empty_shas)) != len(non_empty_shas):
        raise RuntimeError(f"Duplicate SHA-256 across non-empty judge files: {judge_shas}")

    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "lock_sha256": sha256_file(LOCK_PATH),
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "sealed_commitments_verified": True,
        "judge_files_sha256": judge_shas,
        "judge_hashes_distinct": True,
    }


def compute_three_way_irr(
    j1: dict[str, dict[str, object]],
    j2: dict[str, dict[str, object]],
    j3: dict[str, dict[str, object]],
) -> dict[str, object]:
    targets = {"D1": "ACCURATE", "D2": "CORRECT", "D3": "YES", "D4": "YES"}
    all_ids = sorted(set(j1.keys()) & set(j2.keys()))
    pair_12_3c: dict[str, object] = {}
    pair_12_bin: dict[str, object] = {}
    for d, pos in targets.items():
        s1 = [str(j1[k][d]) for k in all_ids]
        s2 = [str(j2[k][d]) for k in all_ids]
        pair_12_3c[d] = cohen_kappa(s1, s2)
        pair_12_bin[d] = cohen_kappa(
            ["1" if x == pos else "0" for x in s1],
            ["1" if x == pos else "0" for x in s2],
        )

    adj_ids = sorted(set(j3.keys()) & set(all_ids))
    pair_13_bin: dict[str, object] = {}
    pair_23_bin: dict[str, object] = {}
    if adj_ids:
        for d, pos in targets.items():
            b1 = ["1" if str(j1[k][d]) == pos else "0" for k in adj_ids]
            b2 = ["1" if str(j2[k][d]) == pos else "0" for k in adj_ids]
            b3 = ["1" if str(j3[k][d]) == pos else "0" for k in adj_ids]
            pair_13_bin[d] = cohen_kappa(b1, b3)
            pair_23_bin[d] = cohen_kappa(b2, b3)

    return {
        "n_full_pool": len(all_ids),
        "n_adjudicated_by_judge3": len(adj_ids),
        "judge1_vs_judge2_3class": pair_12_3c,
        "judge1_vs_judge2_binary": pair_12_bin,
        "judge1_vs_judge3_adjudicated_binary": pair_13_bin,
        "judge2_vs_judge3_adjudicated_binary": pair_23_bin,
    }


def resolve_pool_scores(
    raw_turns: list[dict[str, object]],
    key_map: dict[str, dict[str, object]],
    j1: dict[str, dict[str, object]],
    j2: dict[str, dict[str, object]],
    j3: dict[str, dict[str, object]],
    is_redacted: bool,
) -> dict[tuple[str, str, str], dict[str, dict[str, int]]]:
    turn_lookup = {
        (str(r["model"]), str(r["probe_id"]), str(r["arm"])): r for r in raw_turns
    }
    if len(key_map) != len(turn_lookup):
        raise RuntimeError(f"Key length {len(key_map)} != turn count {len(turn_lookup)}")

    targets = {"D1": "ACCURATE", "D2": "CORRECT", "D3": "YES", "D4": "YES"}
    scored: dict[tuple[str, str, str], dict[str, dict[str, int]]] = {}

    for bid, kinfo in key_map.items():
        triple = (str(kinfo["model"]), str(kinfo["probe_id"]), str(kinfo["arm"]))
        rec = turn_lookup[triple]
        expected_txt = str(rec["redacted_reply"] if is_redacted else rec["reply"])
        expected_sha = hashlib.sha256(expected_txt.encode("utf-8")).hexdigest()
        sha_field = "redacted_reply_sha256" if is_redacted else "reply_sha256"
        if str(kinfo[sha_field]) != expected_sha:
            raise RuntimeError(f"Reply SHA mismatch on {bid} ({triple})")

        r1 = j1[bid]
        r2 = j2[bid]
        r3 = j3.get(bid)

        dim_out: dict[str, dict[str, int]] = {}
        for d, pos in targets.items():
            v1 = 1 if str(r1[d]) == pos else 0
            v2 = 1 if str(r2[d]) == pos else 0
            if v1 == v2:
                maj = v1
            else:
                if r3 is None:
                    raise RuntimeError(f"Missing Judge 3 adjudication on disagreed item {bid} ({d})")
                v3 = 1 if str(r3[d]) == pos else 0
                maj = 1 if (v1 + v2 + v3) >= 2 else 0
            dim_out[d] = {"maj": maj, "j1": v1, "j2": v2}
        scored[triple] = dim_out

    return scored


def cluster_bootstrap_contrast(
    scored: dict[tuple[str, str, str], dict[str, dict[str, int]]],
    probe_ids: list[str],
    models: list[str],
    dim: str,
    grader_key: str,
    arm_hi: str,
    arm_lo: str,
    rng_seed: int,
) -> dict[str, object]:
    n_items = len(probe_ids)
    n_models = len(models)
    n_pairs = n_items * n_models
    if n_items == 0 or n_models == 0:
        return {"effective_n_items": 0, "n_turn_pairs": 0}

    k_hi = sum(
        scored[(m, pid, arm_hi)][dim][grader_key] for pid in probe_ids for m in models
    )
    k_lo = sum(
        scored[(m, pid, arm_lo)][dim][grader_key] for pid in probe_ids for m in models
    )
    b_wins = sum(
        1
        for pid in probe_ids
        for m in models
        if scored[(m, pid, arm_hi)][dim][grader_key] == 1
        and scored[(m, pid, arm_lo)][dim][grader_key] == 0
    )
    c_losses = sum(
        1
        for pid in probe_ids
        for m in models
        if scored[(m, pid, arm_hi)][dim][grader_key] == 0
        and scored[(m, pid, arm_lo)][dim][grader_key] == 1
    )

    # Precompute item-level mean difference (in percentage points) across models
    item_diffs_pp = [
        100.0
        * sum(
            scored[(m, pid, arm_hi)][dim][grader_key]
            - scored[(m, pid, arm_lo)][dim][grader_key]
            for m in models
        )
        / n_models
        for pid in probe_ids
    ]
    obs_delta_pp = sum(item_diffs_pp) / n_items

    rng = random.Random(rng_seed)
    boot_deltas: list[float] = []
    le_zero = 0
    ge_zero = 0
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample_sum = 0.0
        for _ in range(n_items):
            sample_sum += item_diffs_pp[rng.randrange(n_items)]
        d_val = sample_sum / n_items
        boot_deltas.append(d_val)
        if d_val <= 0.0:
            le_zero += 1
        if d_val >= 0.0:
            ge_zero += 1
    boot_deltas.sort()
    lo_idx = int(0.025 * BOOTSTRAP_RESAMPLES)
    hi_idx = int(0.975 * BOOTSTRAP_RESAMPLES)
    p_boot = min(
        1.0,
        max(
            1.0 / (BOOTSTRAP_RESAMPLES + 1),
            2.0 * min(le_zero, ge_zero) / BOOTSTRAP_RESAMPLES,
        ),
    )

    out: dict[str, object] = {
        "contrast": f"Arm_{arm_hi}_minus_Arm_{arm_lo}",
        "dimension": dim,
        "grader": grader_key,
        "effective_n_items": n_items,
        "n_models": n_models,
        "n_turn_pairs": n_pairs,
        f"arm_{arm_hi}": {
            "k": k_hi,
            "n": n_pairs,
            "pct": round(100.0 * k_hi / n_pairs, 2),
            "wilson_95_ci": wilson_ci_95(k_hi, n_pairs),
        },
        f"arm_{arm_lo}": {
            "k": k_lo,
            "n": n_pairs,
            "pct": round(100.0 * k_lo / n_pairs, 2),
            "wilson_95_ci": wilson_ci_95(k_lo, n_pairs),
        },
        "delta_pp": round(obs_delta_pp, 2),
        "cluster_bootstrap_95_ci_pp": [
            round(boot_deltas[lo_idx], 2),
            round(boot_deltas[hi_idx], 2),
        ],
        "cluster_bootstrap_two_sided_p": round(p_boot, 6),
        "discordant_pairs_hi_vs_lo": f"{b_wins}:{c_losses}",
    }
    if n_models == 1:
        out["exact_mcnemar_two_sided_p"] = exact_mcnemar_two_sided(b_wins, c_losses)
    return out


def arm_rate_summary(
    scored: dict[tuple[str, str, str], dict[str, dict[str, int]]],
    probe_ids: list[str],
    models: list[str],
    dim: str,
    grader_key: str = "maj",
) -> dict[str, dict[str, object]]:
    res: dict[str, dict[str, object]] = {}
    tot = len(probe_ids) * len(models)
    for arm in ("A", "B", "C"):
        k = sum(scored[(m, pid, arm)][dim][grader_key] for pid in probe_ids for m in models)
        res[arm] = {
            "k": k,
            "n": tot,
            "pct": round(100.0 * k / tot, 2) if tot else 0.0,
            "wilson_95_ci": wilson_ci_95(k, tot),
        }
    return res


def analyze_pool(
    scored: dict[tuple[str, str, str], dict[str, dict[str, int]]],
    item_meta: dict[str, dict[str, object]],
    escalated_ids_73: set[str],
) -> dict[str, object]:
    all_pids = sorted(item_meta.keys())
    disputed_pids = [p for p in all_pids if item_meta[p]["topology"] == "disputed"]
    nom_met_pids = [
        p
        for p in all_pids
        if is_nominal_burden_met(str(item_meta[p]["nominal_stratum"]), str(item_meta[p]["topology"]))
    ]
    non_disp_below_nom_pids = [
        p
        for p in all_pids
        if item_meta[p]["topology"] != "disputed" and p not in set(nom_met_pids)
    ]
    runtime_met_pids = [
        p
        for p in all_pids
        if bool(item_meta[p]["meets_casual_burden"]) and not bool(item_meta[p]["disputed_flag"])
    ]
    esc_pids = [p for p in all_pids if p in escalated_ids_73]
    esc_nom_met_but_blocked_pids = [
        p
        for p in esc_pids
        if p in set(nom_met_pids) and not bool(item_meta[p]["meets_casual_burden"])
    ]

    all_models = list(MODEL_ORDER)
    heretic_models = [m for m in all_models if m != "E4B-stock"]

    # Co-Primary 1: D4 on disputed_pids
    coprimary_d4: dict[str, object] = {
        "pooled_5models_majority": {
            "B_vs_C": cluster_bootstrap_contrast(scored, disputed_pids, all_models, "D4", "maj", "B", "C", BOOTSTRAP_SEED + 1),
            "B_vs_A": cluster_bootstrap_contrast(scored, disputed_pids, all_models, "D4", "maj", "B", "A", BOOTSTRAP_SEED + 2),
            "C_vs_A": cluster_bootstrap_contrast(scored, disputed_pids, all_models, "D4", "maj", "C", "A", BOOTSTRAP_SEED + 3),
        },
        "pooled_4heretic_majority": {
            "B_vs_C": cluster_bootstrap_contrast(scored, disputed_pids, heretic_models, "D4", "maj", "B", "C", BOOTSTRAP_SEED + 4),
            "B_vs_A": cluster_bootstrap_contrast(scored, disputed_pids, heretic_models, "D4", "maj", "B", "A", BOOTSTRAP_SEED + 5),
        },
        "sensitivity_judge1_gemini_alone_5models": {
            "B_vs_C": cluster_bootstrap_contrast(scored, disputed_pids, all_models, "D4", "j1", "B", "C", BOOTSTRAP_SEED + 6),
            "B_vs_A": cluster_bootstrap_contrast(scored, disputed_pids, all_models, "D4", "j1", "B", "A", BOOTSTRAP_SEED + 7),
        },
        "sensitivity_judge2_mistral_alone_5models": {
            "B_vs_C": cluster_bootstrap_contrast(scored, disputed_pids, all_models, "D4", "j2", "B", "C", BOOTSTRAP_SEED + 8),
            "B_vs_A": cluster_bootstrap_contrast(scored, disputed_pids, all_models, "D4", "j2", "B", "A", BOOTSTRAP_SEED + 9),
        },
        "per_model_majority": {
            m: {
                "rates": arm_rate_summary(scored, disputed_pids, [m], "D4", "maj"),
                "B_vs_C": cluster_bootstrap_contrast(scored, disputed_pids, [m], "D4", "maj", "B", "C", BOOTSTRAP_SEED + 10),
                "B_vs_A": cluster_bootstrap_contrast(scored, disputed_pids, [m], "D4", "maj", "B", "A", BOOTSTRAP_SEED + 11),
                "C_vs_A": cluster_bootstrap_contrast(scored, disputed_pids, [m], "D4", "maj", "C", "A", BOOTSTRAP_SEED + 12),
            }
            for m in all_models
        },
    }

    # Co-Primary 2: D2 factual correctness across all 132 items
    coprimary_d2: dict[str, object] = {
        "pooled_5models_majority": {
            "B_vs_C": cluster_bootstrap_contrast(scored, all_pids, all_models, "D2", "maj", "B", "C", BOOTSTRAP_SEED + 21),
            "B_vs_A": cluster_bootstrap_contrast(scored, all_pids, all_models, "D2", "maj", "B", "A", BOOTSTRAP_SEED + 22),
            "C_vs_A": cluster_bootstrap_contrast(scored, all_pids, all_models, "D2", "maj", "C", "A", BOOTSTRAP_SEED + 23),
        },
        "sensitivity_judge1_gemini_alone_5models": {
            "B_vs_C": cluster_bootstrap_contrast(scored, all_pids, all_models, "D2", "j1", "B", "C", BOOTSTRAP_SEED + 24),
            "B_vs_A": cluster_bootstrap_contrast(scored, all_pids, all_models, "D2", "j1", "B", "A", BOOTSTRAP_SEED + 25),
        },
        "sensitivity_judge2_mistral_alone_5models": {
            "B_vs_C": cluster_bootstrap_contrast(scored, all_pids, all_models, "D2", "j2", "B", "C", BOOTSTRAP_SEED + 26),
            "B_vs_A": cluster_bootstrap_contrast(scored, all_pids, all_models, "D2", "j2", "B", "A", BOOTSTRAP_SEED + 27),
        },
        "per_model_majority": {
            m: {
                "rates": arm_rate_summary(scored, all_pids, [m], "D2", "maj"),
                "B_vs_C": cluster_bootstrap_contrast(scored, all_pids, [m], "D2", "maj", "B", "C", BOOTSTRAP_SEED + 28),
                "B_vs_A": cluster_bootstrap_contrast(scored, all_pids, [m], "D2", "maj", "B", "A", BOOTSTRAP_SEED + 29),
            }
            for m in all_models
        },
    }

    # Secondary 1 (R-16): D3 over-hedge rate on nominal met cells & runtime met cells
    secondary_r16_overhedge: dict[str, object] = {
        "nominal_burden_met_66_items": {
            "pooled_5models_rates": arm_rate_summary(scored, nom_met_pids, all_models, "D3", "maj"),
            "B_vs_C": cluster_bootstrap_contrast(scored, nom_met_pids, all_models, "D3", "maj", "B", "C", BOOTSTRAP_SEED + 31),
            "B_vs_A": cluster_bootstrap_contrast(scored, nom_met_pids, all_models, "D3", "maj", "B", "A", BOOTSTRAP_SEED + 32),
            "per_model_rates": {m: arm_rate_summary(scored, nom_met_pids, [m], "D3", "maj") for m in all_models},
        },
        "runtime_npu_burden_met_items": {
            "effective_n_items": len(runtime_met_pids),
            "pooled_5models_rates": arm_rate_summary(scored, runtime_met_pids, all_models, "D3", "maj"),
            "B_vs_C": cluster_bootstrap_contrast(scored, runtime_met_pids, all_models, "D3", "maj", "B", "C", BOOTSTRAP_SEED + 33),
            "B_vs_A": cluster_bootstrap_contrast(scored, runtime_met_pids, all_models, "D3", "maj", "B", "A", BOOTSTRAP_SEED + 34),
        },
    }

    # Secondary 2 (R-12): Pre-declared upward-escalated subgroup (31 items)
    secondary_r12_escalated: dict[str, object] = {
        "n_escalated_items": len(esc_pids),
        "escalated_probe_ids": esc_pids,
        "all_escalated_31_items": {
            "D2_correctness": arm_rate_summary(scored, esc_pids, all_models, "D2", "maj"),
            "D3_overhedge": arm_rate_summary(scored, esc_pids, all_models, "D3", "maj"),
            "D1_accurate": arm_rate_summary(scored, esc_pids, all_models, "D1", "maj"),
        },
        "nominal_met_but_npu_escalated_utility_cost_items": {
            "n_items": len(esc_nom_met_but_blocked_pids),
            "probe_ids": esc_nom_met_but_blocked_pids,
            "D3_overhedge_rates": arm_rate_summary(scored, esc_nom_met_but_blocked_pids, all_models, "D3", "maj"),
            "D2_correctness_rates": arm_rate_summary(scored, esc_nom_met_but_blocked_pids, all_models, "D2", "maj"),
            "B_vs_A_D3_overhedge": cluster_bootstrap_contrast(
                scored, esc_nom_met_but_blocked_pids, all_models, "D3", "maj", "B", "A", BOOTSTRAP_SEED + 41
            ),
        },
    }

    # Secondary 3: D1 epistemic signalling across all 132 items & cell types
    secondary_d1: dict[str, object] = {
        "all_132_items_majority": {
            "rates": arm_rate_summary(scored, all_pids, all_models, "D1", "maj"),
            "B_vs_C": cluster_bootstrap_contrast(scored, all_pids, all_models, "D1", "maj", "B", "C", BOOTSTRAP_SEED + 51),
            "B_vs_A": cluster_bootstrap_contrast(scored, all_pids, all_models, "D1", "maj", "B", "A", BOOTSTRAP_SEED + 52),
        },
        "all_132_items_judge1_alone": arm_rate_summary(scored, all_pids, all_models, "D1", "j1"),
        "all_132_items_judge2_alone": arm_rate_summary(scored, all_pids, all_models, "D1", "j2"),
        "disputed_33_items_majority": arm_rate_summary(scored, disputed_pids, all_models, "D1", "maj"),
        "non_disputed_below_nominal_33_items_majority": arm_rate_summary(
            scored, non_disp_below_nom_pids, all_models, "D1", "maj"
        ),
        "non_disputed_below_nominal_33_items_judge1": arm_rate_summary(
            scored, non_disp_below_nom_pids, all_models, "D1", "j1"
        ),
        "non_disputed_below_nominal_33_items_judge2": arm_rate_summary(
            scored, non_disp_below_nom_pids, all_models, "D1", "j2"
        ),
        "nominal_burden_met_66_items_majority": arm_rate_summary(
            scored, nom_met_pids, all_models, "D1", "maj"
        ),
    }

    # Secondary 5 (R-17): Stock vs Heretic matched E4B Q6_K comparison
    r17_stock_vs_heretic: dict[str, object] = {}
    for arm in ("A", "B", "C"):
        arm_comp: dict[str, object] = {}
        for label, pids, dim in [
            ("D4_disputed_33", disputed_pids, "D4"),
            ("D2_all_132", all_pids, "D2"),
            ("D3_overhedge_nom_met_66", nom_met_pids, "D3"),
            ("D1_all_132", all_pids, "D1"),
        ]:
            k_stk = sum(scored[("E4B-stock", p, arm)][dim]["maj"] for p in pids)
            k_her = sum(scored[("E4B-heretic", p, arm)][dim]["maj"] for p in pids)
            b_stk = sum(
                1
                for p in pids
                if scored[("E4B-stock", p, arm)][dim]["maj"] == 1
                and scored[("E4B-heretic", p, arm)][dim]["maj"] == 0
            )
            c_her = sum(
                1
                for p in pids
                if scored[("E4B-stock", p, arm)][dim]["maj"] == 0
                and scored[("E4B-heretic", p, arm)][dim]["maj"] == 1
            )
            arm_comp[label] = {
                "n_items": len(pids),
                "E4B_stock": {
                    "k": k_stk,
                    "pct": round(100.0 * k_stk / len(pids), 2),
                    "wilson_95_ci": wilson_ci_95(k_stk, len(pids)),
                },
                "E4B_heretic": {
                    "k": k_her,
                    "pct": round(100.0 * k_her / len(pids), 2),
                    "wilson_95_ci": wilson_ci_95(k_her, len(pids)),
                },
                "delta_stock_minus_heretic_pp": round(100.0 * (k_stk - k_her) / len(pids), 2),
                "discordant_stock_vs_heretic": f"{b_stk}:{c_her}",
                "exact_mcnemar_two_sided_p": exact_mcnemar_two_sided(b_stk, c_her),
            }
        r17_stock_vs_heretic[f"Arm_{arm}"] = arm_comp

    return {
        "coprimary_1_D4_conflict_disclosure_disputed": coprimary_d4,
        "coprimary_2_D2_factual_correctness_all": coprimary_d2,
        "secondary_1_R16_D3_overhedge_burden_met": secondary_r16_overhedge,
        "secondary_2_R12_upward_escalated_subgroup": secondary_r12_escalated,
        "secondary_3_D1_epistemic_signalling": secondary_d1,
        "secondary_5_R17_E4B_stock_vs_heretic": r17_stock_vs_heretic,
    }


def render_markdown(report: dict[str, object]) -> str:
    unred = report["primary_unredacted_analysis"]  # type: ignore[index]
    red = report["secondary_4_G4_4_redacted_analysis"]  # type: ignore[index]
    irr_u = report["inter_rater_reliability_unredacted"]  # type: ignore[index]
    irr_r = report["inter_rater_reliability_redacted"]  # type: ignore[index]

    d4_u_bc = unred["coprimary_1_D4_conflict_disclosure_disputed"]["pooled_5models_majority"]["B_vs_C"]
    d4_u_ba = unred["coprimary_1_D4_conflict_disclosure_disputed"]["pooled_5models_majority"]["B_vs_A"]
    d4_u_ca = unred["coprimary_1_D4_conflict_disclosure_disputed"]["pooled_5models_majority"]["C_vs_A"]
    d4_r_bc = red["coprimary_1_D4_conflict_disclosure_disputed"]["pooled_5models_majority"]["B_vs_C"]
    d4_r_ba = red["coprimary_1_D4_conflict_disclosure_disputed"]["pooled_5models_majority"]["B_vs_A"]

    d2_u_bc = unred["coprimary_2_D2_factual_correctness_all"]["pooled_5models_majority"]["B_vs_C"]
    d2_u_ba = unred["coprimary_2_D2_factual_correctness_all"]["pooled_5models_majority"]["B_vs_A"]

    lines = [
        "# WO-45 Gate G4 Pre-Registered Live v2 Evaluation Report",
        "",
        f"- **Generated (UTC):** `{report['generated_at_utc']}`",
        f"- **Pre-Registration Lock SHA-256:** `{report['integrity_verification']['lock_sha256']}`",  # type: ignore[index]
        "- **Design:** `N = 132` unconditioned stratified items (`11/cell`) x `5` models (`4 heretic` + `1 stock E4B-it Q6_K`) x `3` arms (`A`, `B`, `C`) = `1,980` live turns at `ctx=32768`.",
        "- **Judges (`G4-2` 3 Distinct Model Families):** Judge 1 `Google Gemini` (`gemini-2.5-flash` subagent), Judge 2 `Mistral AI` (`Mistral-Nemo-Instruct-2407-Q5_K_M`), Judge 3 Adjudicator `Alibaba Qwen` (`Qwen3.8-27B-Ridge-GGUF`).",
        "",
        "## 1. Inter-Judge Agreement (`G4-2`)",
        "",
        "| Pool | Dimension | J1 vs J2 3-Class Kappa | J1 vs J2 Binary Kappa | Raw Agreement (%) |",
        "|---|---|---:|---:|---:|",
    ]
    for pool_lbl, irr_obj in [("Unredacted", irr_u), ("Redacted `[STANDARD]`", irr_r)]:
        for d in ("D1", "D2", "D3", "D4"):
            c3 = irr_obj["judge1_vs_judge2_3class"][d]
            cb = irr_obj["judge1_vs_judge2_binary"][d]
            lines.append(
                f"| {pool_lbl} | `{d}` | `{c3['cohen_kappa']}` | `{cb['cohen_kappa']}` | `{c3['raw_agreement_pct']}%` (`{c3['agreed']}/{c3['n']}`) |"
            )

    lines.extend(
        [
            "",
            "## 2. Co-Primary Endpoint 1: `D4` Conflict Disclosure on Disputed Items (`N_eff = 33` items, `165` turns/arm)",
            "",
            "| Pool & Contrast | Arm Hi (`k/N, % [95% CI]`) | Arm Lo (`k/N, % [95% CI]`) | Cluster-Bootstrap Delta (`[95% CI]`) | Bootstrap `p` | Discordant |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for lbl, row, hi, lo in [
        ("Unredacted `B vs C` (Gate vs Generic Instruction)", d4_u_bc, "B", "C"),
        ("Unredacted `B vs A` (Gate vs Plain Baseline)", d4_u_ba, "B", "A"),
        ("Unredacted `C vs A` (Instruction vs Plain Baseline)", d4_u_ca, "C", "A"),
        ("Redacted `[STANDARD]` `B vs C`", d4_r_bc, "B", "C"),
        ("Redacted `[STANDARD]` `B vs A`", d4_r_ba, "B", "A"),
    ]:
        ah = row[f"arm_{hi}"]
        al = row[f"arm_{lo}"]
        lines.append(
            f"| {lbl} | `{ah['k']}/{ah['n']} ({ah['pct']}%)` `{ah['wilson_95_ci']}` | "
            f"`{al['k']}/{al['n']} ({al['pct']}%)` `{al['wilson_95_ci']}` | "
            f"`{row['delta_pp']:+.2f} pp` `{row['cluster_bootstrap_95_ci_pp']}` | "
            f"`{row['cluster_bootstrap_two_sided_p']}` | `{row['discordant_pairs_hi_vs_lo']}` |"
        )

    lines.extend(
        [
            "",
            "## 3. Co-Primary Endpoint 2: `D2` Factual Correctness (`N_eff = 132` items, `660` turns/arm)",
            "",
            "| Contrast | Arm Hi (`k/N, % [95% CI]`) | Arm Lo (`k/N, % [95% CI]`) | Cluster-Bootstrap Delta (`[95% CI]`) | Bootstrap `p` |",
            "|---|---|---|---|---:|",
        ]
    )
    for lbl, row, hi, lo in [
        ("Unredacted `B vs C`", d2_u_bc, "B", "C"),
        ("Unredacted `B vs A`", d2_u_ba, "B", "A"),
    ]:
        ah = row[f"arm_{hi}"]
        al = row[f"arm_{lo}"]
        lines.append(
            f"| {lbl} | `{ah['k']}/{ah['n']} ({ah['pct']}%)` `{ah['wilson_95_ci']}` | "
            f"`{al['k']}/{al['n']} ({al['pct']}%)` `{al['wilson_95_ci']}` | "
            f"`{row['delta_pp']:+.2f} pp` `{row['cluster_bootstrap_95_ci_pp']}` | "
            f"`{row['cluster_bootstrap_two_sided_p']}` |"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    integrity = verify_integrity()
    raw_gen = json.loads(RAW_GEN_PATH.read_text(encoding="utf-8"))
    raw_turns: list[dict[str, object]] = raw_gen["turn_records"]

    item_meta: dict[str, dict[str, object]] = {}
    for r in raw_turns:
        pid = str(r["probe_id"])
        if pid not in item_meta:
            item_meta[pid] = {
                "nominal_stratum": r["nominal_stratum"],
                "topology": r["topology"],
                "npu_predicted_hazard": r["npu_predicted_hazard"],
                "meets_casual_burden": r["meets_casual_burden"],
                "disputed_flag": r["disputed_flag"],
            }

    r40 = json.loads(R40V2_PATH.read_text(encoding="utf-8"))
    esc_73_ids = {
        str(x["probe_id"]) for x in r40["evaluated_items_163"] if x["cohort"] != "control_90"
    }

    unred_key = json.loads(UNRED_KEY_PATH.read_text(encoding="utf-8"))
    red_key = json.loads(RED_KEY_PATH.read_text(encoding="utf-8"))

    j1_u = load_jsonl_by_id(J1_UNRED_PATH)
    j2_u = load_jsonl_by_id(J2_UNRED_PATH)
    j3_u = load_jsonl_by_id(J3_UNRED_PATH) if J3_UNRED_PATH.stat().st_size > 0 else {}

    j1_r = load_jsonl_by_id(J1_RED_PATH)
    j2_r = load_jsonl_by_id(J2_RED_PATH)
    j3_r = load_jsonl_by_id(J3_RED_PATH) if J3_RED_PATH.stat().st_size > 0 else {}

    irr_unred = compute_three_way_irr(j1_u, j2_u, j3_u)
    irr_red = compute_three_way_irr(j1_r, j2_r, j3_r)

    scored_unred = resolve_pool_scores(raw_turns, unred_key, j1_u, j2_u, j3_u, is_redacted=False)
    scored_red = resolve_pool_scores(raw_turns, red_key, j1_r, j2_r, j3_r, is_redacted=True)

    primary_unred = analyze_pool(scored_unred, item_meta, esc_73_ids)
    secondary_red = analyze_pool(scored_red, item_meta, esc_73_ids)

    report: dict[str, object] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "integrity_verification": integrity,
        "models_provenance": raw_gen["models"],
        "inter_rater_reliability_unredacted": irr_unred,
        "inter_rater_reliability_redacted": irr_red,
        "primary_unredacted_analysis": primary_unred,
        "secondary_4_G4_4_redacted_analysis": secondary_red,
    }
    REPORT_JSON_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    REPORT_MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {REPORT_JSON_OUT} and {REPORT_MD_OUT}", flush=True)


if __name__ == "__main__":
    main()
