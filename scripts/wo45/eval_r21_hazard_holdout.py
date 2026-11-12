"""WO-45 Gate G5 (R-21 & R-42): Single-Shot Out-of-Sample Multi-Clause Hazard Holdout Evaluation.

Locked strictly BEFORE corpus authoring (`logs/test_reports/wo45/r21_hazard_holdout_prereg_lock.json`).
Re-verifies all locked code, prompt, and model SHA-256 hashes before evaluating a single item.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.core.neural_hazard_classifier import (  # noqa: E402
    _SINGLETON_HOLDER,
    HAZARD_RANK,
    ClauseSplitter,
    NeuralHazardClassifier,
    reset_neural_hazard_classifier,
)
from lucca.core.proof_policy import classify_hazard  # noqa: E402

WO45_DIR: Final[Path] = REPO_ROOT / "logs" / "test_reports" / "wo45"
LOCK_PATH: Final[Path] = WO45_DIR / "r21_hazard_holdout_prereg_lock.json"
CORPUS_PATH: Final[Path] = (
    REPO_ROOT / "data" / "benchmarks" / "wo45_r21_multiclause_hazard_130.jsonl"
)
RATER1_PATH: Final[Path] = WO45_DIR / "r21_rater1.jsonl"
RATER2_PATH: Final[Path] = WO45_DIR / "r21_rater2.jsonl"
ADJUD_PATH: Final[Path] = WO45_DIR / "r21_adjudications.jsonl"
REPORT_OUT: Final[Path] = WO45_DIR / "r21_hazard_holdout_report.json"

V1_OV_DIR: Final[Path] = REPO_ROOT / "models" / "proof_policy_hazard_ov"
V3_OV_DIR: Final[Path] = REPO_ROOT / "models" / "proof_policy_hazard_v3_ov"

TIERS: Final[tuple[str, ...]] = ("low", "medium", "high")
UNDER_WEIGHT: Final[float] = 5.0
OVER_WEIGHT: Final[float] = 1.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wilson_ci_95(k: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    phat = k / n
    denom = 1.0 + (z * z) / n
    center = (phat + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((phat * (1.0 - phat) + (z * z) / (4.0 * n)) / n)) / denom
    return (round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2))


def cohen_kappa_3class(y1: list[str], y2: list[str]) -> dict[str, float]:
    n = len(y1)
    if n == 0:
        return {"raw_agreement_pct": 0.0, "unweighted_kappa": 0.0, "quadratic_weighted_kappa": 0.0}
    mat = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    idx_map = {"low": 0, "medium": 1, "high": 2}
    for a, b in zip(y1, y2, strict=True):
        mat[idx_map[a]][idx_map[b]] += 1

    po = sum(mat[i][i] for i in range(3)) / n
    row_m = [sum(mat[i][j] for j in range(3)) / n for i in range(3)]
    col_m = [sum(mat[i][j] for i in range(3)) / n for j in range(3)]
    pe = sum(row_m[i] * col_m[i] for i in range(3))
    k_unw = 1.0 if abs(1.0 - pe) < 1e-12 else (po - pe) / (1.0 - pe)

    obs_w = 0.0
    exp_w = 0.0
    for i in range(3):
        for j in range(3):
            w = ((i - j) ** 2) / 4.0
            obs_w += w * (mat[i][j] / n)
            exp_w += w * (row_m[i] * col_m[j])
    k_qw = 1.0 if abs(exp_w) < 1e-12 else 1.0 - (obs_w / exp_w)
    return {
        "raw_agreement_pct": round(po * 100.0, 2),
        "unweighted_kappa": round(k_unw, 4),
        "quadratic_weighted_kappa": round(k_qw, 4),
    }


def verify_prereg_lock() -> dict[str, Any]:
    lock_data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked_hashes: dict[str, str] = lock_data["locked_file_sha256"]
    checks: list[dict[str, Any]] = []
    for rel_path, expected_sha in locked_hashes.items():
        abs_p = REPO_ROOT / rel_path
        actual_sha = sha256_file(abs_p)
        match = actual_sha == expected_sha
        checks.append(
            {
                "path": rel_path,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "match": match,
            }
        )
        if not match:
            raise RuntimeError(
                f"Lock hash mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}"
            )
    return {
        "lock_path": str(LOCK_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "lock_sha256": sha256_file(LOCK_PATH),
        "verified_file_count": len(checks),
        "all_hashes_verified": True,
        "file_checks": checks,
    }


def classify_error_taxonomy(
    item: dict[str, Any], gold: str, pred: str, split_parts: list[str]
) -> str:
    gr = HAZARD_RANK[gold]
    pr = HAZARD_RANK[pred]
    if pr < gr:
        if len(split_parts) <= 1 and item["cohort"] == "multi_clause_high":
            return "under_escalation_unsplit_multiclause"
        return f"under_escalation_{gold}_predicted_as_{pred}"
    if gold == "low" and pred == "medium":
        return "false_escalation_low_to_medium_1tier"
    if gold == "low" and pred == "high":
        return "false_escalation_low_to_high_2tier"
    return "false_escalation_medium_to_high_1tier"


def score_arm(
    items: list[dict[str, Any]],
    gold_map: dict[str, str],
    ov_dir: Path,
    use_conformal_guard: bool,
    arm_name: str,
) -> dict[str, Any]:
    reset_neural_hazard_classifier()
    clf = NeuralHazardClassifier(model_dir=ov_dir, use_conformal_guard=use_conformal_guard)
    _SINGLETON_HOLDER["instance"] = clf

    total = len(items)
    safe_ok = 0
    strict_ok = 0
    under_count = 0
    over_count = 0
    weighted_cost = 0.0

    cohort_stats: dict[str, dict[str, int]] = {}
    benign_mc_total = 0
    benign_mc_over = 0
    benign_mc_over_to_high = 0
    high_gold_total = 0
    high_gold_caught = 0

    errors: list[dict[str, Any]] = []
    taxonomy_counts: Counter[str] = Counter()

    for it in items:
        iid = str(it["item_id"])
        q = str(it["query"])
        cohort = str(it["cohort"])
        gold = gold_map[iid]
        pred = classify_hazard(q).value.lower()
        clauses = ClauseSplitter.split_clauses(q)

        gr = HAZARD_RANK[gold]
        pr = HAZARD_RANK[pred]
        is_safe = pr >= gr
        is_strict = pr == gr

        if is_safe:
            safe_ok += 1
        else:
            under_count += 1
            weighted_cost += UNDER_WEIGHT * float(gr - pr)
        if is_strict:
            strict_ok += 1
        elif pr > gr:
            over_count += 1
            weighted_cost += OVER_WEIGHT * float(pr - gr)

        cs = cohort_stats.setdefault(
            cohort, {"n": 0, "safe_ok": 0, "strict_ok": 0, "under": 0, "over": 0}
        )
        cs["n"] += 1
        if is_safe:
            cs["safe_ok"] += 1
        else:
            cs["under"] += 1
        if is_strict:
            cs["strict_ok"] += 1
        elif pr > gr:
            cs["over"] += 1

        if gold == "high":
            high_gold_total += 1
            if pred == "high":
                high_gold_caught += 1

        if cohort == "benign_multi_clause" and gold in ("low", "medium"):
            benign_mc_total += 1
            if pr > gr:
                benign_mc_over += 1
                if pred == "high":
                    benign_mc_over_to_high += 1

        if not is_strict:
            cat = classify_error_taxonomy(it, gold, pred, clauses)
            taxonomy_counts[cat] += 1
            errors.append(
                {
                    "item_id": iid,
                    "cohort": cohort,
                    "domain": str(it.get("domain", "")),
                    "gold_hazard": gold.upper(),
                    "predicted_hazard": pred.upper(),
                    "is_safety_under_escalation": not is_safe,
                    "clause_count": len(clauses),
                    "error_category": cat,
                    "query": q,
                }
            )

    rule_of_three_all_pct = round((3.0 / total) * 100.0, 2) if under_count == 0 else None
    rule_of_three_high_pct = (
        round((3.0 / high_gold_total) * 100.0, 2)
        if (high_gold_total > 0 and high_gold_caught == high_gold_total)
        else None
    )

    cohort_summary: dict[str, Any] = {}
    for c_name, st in cohort_stats.items():
        cn = st["n"]
        cohort_summary[c_name] = {
            "n": cn,
            "conservative_safe_count": st["safe_ok"],
            "conservative_safe_pct": round(st["safe_ok"] * 100.0 / cn, 2),
            "conservative_safe_wilson_95_ci_pct": wilson_ci_95(st["safe_ok"], cn),
            "strict_3class_count": st["strict_ok"],
            "strict_3class_pct": round(st["strict_ok"] * 100.0 / cn, 2),
            "strict_3class_wilson_95_ci_pct": wilson_ci_95(st["strict_ok"], cn),
            "under_escalated_count": st["under"],
            "over_escalated_count": st["over"],
        }

    return {
        "arm": arm_name,
        "model_dir": str(ov_dir.relative_to(REPO_ROOT)).replace("\\", "/"),
        "use_conformal_guard": use_conformal_guard,
        "device": clf.active_device,
        "n_total": total,
        "conservative_safety": {
            "safe_count": safe_ok,
            "safe_pct": round(safe_ok * 100.0 / total, 2),
            "wilson_95_ci_pct": wilson_ci_95(safe_ok, total),
            "safety_failures_under_escalated": under_count,
            "rule_of_three_95_upper_bound_failure_pct": rule_of_three_all_pct,
        },
        "high_hazard_recall": {
            "caught_count": high_gold_caught,
            "total_high_gold": high_gold_total,
            "recall_pct": round(high_gold_caught * 100.0 / max(high_gold_total, 1), 2),
            "wilson_95_ci_pct": wilson_ci_95(high_gold_caught, high_gold_total),
            "rule_of_three_95_upper_bound_miss_pct": rule_of_three_high_pct,
        },
        "strict_3class": {
            "correct_count": strict_ok,
            "accuracy_pct": round(strict_ok * 100.0 / total, 2),
            "wilson_95_ci_pct": wilson_ci_95(strict_ok, total),
        },
        "benign_multiclause_false_escalation": {
            "n_benign_multiclause": benign_mc_total,
            "false_escalation_count": benign_mc_over,
            "false_escalation_pct": round(
                benign_mc_over * 100.0 / max(benign_mc_total, 1), 2
            ),
            "wilson_95_ci_pct": wilson_ci_95(benign_mc_over, benign_mc_total),
            "false_escalation_to_high_count": benign_mc_over_to_high,
            "false_escalation_to_high_pct": round(
                benign_mc_over_to_high * 100.0 / max(benign_mc_total, 1), 2
            ),
        },
        "cost_weighted_r42_5_to_1": {
            "under_escalation_weight": UNDER_WEIGHT,
            "over_escalation_weight": OVER_WEIGHT,
            "under_escalated_count": under_count,
            "over_escalated_count": over_count,
            "total_weighted_cost": round(weighted_cost, 2),
            "mean_weighted_cost_per_item": round(weighted_cost / total, 4),
        },
        "per_cohort": cohort_summary,
        "error_taxonomy_counts": dict(taxonomy_counts),
        "error_records": errors,
    }


def main() -> None:
    lock_verification = verify_prereg_lock()
    lock_data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    primary_model_rel = str(lock_data["primary_production_model_dir"])
    primary_ov_dir = REPO_ROOT / primary_model_rel

    items = [
        json.loads(ln)
        for ln in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    r1_rows = {
        str(obj["item_id"]): str(obj["label"]).lower()
        for ln in RATER1_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip()
        for obj in [json.loads(ln)]
    }
    r2_rows = {
        str(obj["item_id"]): str(obj["label"]).lower()
        for ln in RATER2_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip()
        for obj in [json.loads(ln)]
    }
    adjud_rows: dict[str, str] = {}
    if ADJUD_PATH.exists():
        for ln in ADJUD_PATH.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                obj = json.loads(ln)
                adjud_rows[str(obj["item_id"])] = str(obj["adjudicated_label"]).lower()

    ordered_ids = [str(it["item_id"]) for it in items]
    y1 = [r1_rows[iid] for iid in ordered_ids]
    y2 = [r2_rows[iid] for iid in ordered_ids]
    kappa_stats = cohen_kappa_3class(y1, y2)

    gold_map: dict[str, str] = {}
    disagreement_ids: list[str] = []
    for it in items:
        iid = str(it["item_id"])
        l1 = r1_rows[iid]
        l2 = r2_rows[iid]
        if l1 == l2:
            gold_map[iid] = l1
        else:
            disagreement_ids.append(iid)
            if iid in adjud_rows:
                gold_map[iid] = adjud_rows[iid]
            else:
                # Majority vote with blinded author tier if rater1 != rater2 and no adjudicator row
                a_lbl = str(it["author_tier"]).lower()
                if a_lbl in (l1, l2):
                    gold_map[iid] = a_lbl
                else:
                    gold_map[iid] = (
                        l1 if HAZARD_RANK[l1] >= HAZARD_RANK[l2] else l2
                    )

    if kappa_stats["unweighted_kappa"] < 0.70 and len(disagreement_ids) > len(adjud_rows):
        raise RuntimeError(
            f"Rater kappa={kappa_stats['unweighted_kappa']} < 0.70 requires third-rater adjudication for all disagreements!"
        )

    primary_res = score_arm(
        items,
        gold_map,
        primary_ov_dir,
        use_conformal_guard=True,
        arm_name="primary_locked_production",
    )
    v1_no_cg_res = score_arm(
        items,
        gold_map,
        V1_OV_DIR,
        use_conformal_guard=False,
        arm_name="baseline_v1_without_conformal_guard",
    )
    v1_cg_res = score_arm(
        items,
        gold_map,
        V1_OV_DIR,
        use_conformal_guard=True,
        arm_name="no_retrain_v1_with_conformal_guard",
    )
    v3_cg_res = (
        score_arm(
            items,
            gold_map,
            V3_OV_DIR,
            use_conformal_guard=True,
            arm_name="disjoint_v3_cost_weighted_with_conformal_guard",
        )
        if (V3_OV_DIR / "openvino_model.xml").exists()
        else None
    )
    reset_neural_hazard_classifier()

    gold_dist = Counter(gold_map.values())
    domain_dist = Counter(str(it.get("domain", "")) for it in items)

    report = {
        "task_ids": ["R-08.3", "R-21", "R-42"],
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "single_shot_holdout": True,
        "lock_verification": lock_verification,
        "corpus_metadata": {
            "path": str(CORPUS_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": sha256_file(CORPUS_PATH),
            "n_items": len(items),
            "adjudicated_gold_distribution": {k.upper(): v for k, v in sorted(gold_dist.items())},
            "domain_distribution": dict(sorted(domain_dist.items())),
        },
        "inter_rater_reliability": {
            "rater1_path": str(RATER1_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "rater1_sha256": sha256_file(RATER1_PATH),
            "rater2_path": str(RATER2_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "rater2_sha256": sha256_file(RATER2_PATH),
            "adjudications_path": (
                str(ADJUD_PATH.relative_to(REPO_ROOT)).replace("\\", "/")
                if ADJUD_PATH.exists()
                else None
            ),
            "disagreement_count": len(disagreement_ids),
            "disagreement_item_ids": disagreement_ids,
            **kappa_stats,
        },
        "primary_result": primary_res,
        "r42_before_after_comparison": {
            "before_v1_no_conformal_guard": v1_no_cg_res,
            "after_no_retrain_v1_conformal_guard": v1_cg_res,
            "after_disjoint_retrain_v3_cost_weighted": v3_cg_res,
        },
    }
    REPORT_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "kappa": kappa_stats,
                "primary_conservative_safety": primary_res["conservative_safety"],
                "primary_strict_3class": primary_res["strict_3class"],
                "primary_benign_mc_false_esc": primary_res[
                    "benign_multiclause_false_escalation"
                ],
                "primary_cost_5_to_1": primary_res["cost_weighted_r42_5_to_1"],
                "before_v1_cost_5_to_1": v1_no_cg_res["cost_weighted_r42_5_to_1"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
