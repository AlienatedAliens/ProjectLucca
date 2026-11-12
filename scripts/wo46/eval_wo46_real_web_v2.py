"""Single-shot out-of-sample evaluation of WO-46 `web_evidentiary_burden_real_v2` (N=64 live Scrapling pages)."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from lucca.core.proof_policy import evaluate_web_evidence_burden

REPO = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_prereg_lock.json"
CORPUS_PATH = REPO / "data" / "benchmarks" / "web_evidentiary_burden_real_v2.jsonl"
MANIFEST_PATH = REPO / "data" / "benchmarks" / "web_real_v2_archive" / "manifest_sha256.json"
BLIND_MAP_PATH = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_blind_id_map.json"
RATER1_PATH = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_rater1.jsonl"
RATER2_PATH = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_rater2.jsonl"
ADJUDICATOR_PATH = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_adjudicator.jsonl"
OUT_PATH = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_report.json"

REQ_SOURCES_FOR_HAZARD = {"low": 1, "medium": 2, "high": 3}
HAZARD_ORD = {"low": 0, "medium": 1, "high": 2}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denom
    return [round(max(0.0, center - half), 6), round(min(1.0, center + half), 6)]


def _cohens_kappa(y1: list[object], y2: list[object]) -> float:
    assert len(y1) == len(y2) and len(y1) > 0
    n = len(y1)
    cats = sorted({str(v) for v in y1} | {str(v) for v in y2})
    if len(cats) <= 1:
        return 1.0
    p0 = sum(1 for a, b in zip(y1, y2, strict=True) if str(a) == str(b)) / n
    pe = sum(
        (sum(1 for a in y1 if str(a) == c) / n) * (sum(1 for b in y2 if str(b) == c) / n)
        for c in cats
    )
    if abs(1.0 - pe) < 1e-12:
        return 1.0
    return round((p0 - pe) / (1.0 - pe), 6)


def _linear_weighted_kappa(y1: list[int], y2: list[int], max_val: int) -> float:
    assert len(y1) == len(y2) and len(y1) > 0
    n = len(y1)
    if max_val <= 0:
        return 1.0
    obs_dis = sum(abs(a - b) / max_val for a, b in zip(y1, y2, strict=True)) / n
    c1 = [sum(1 for a in y1 if a == v) / n for v in range(max_val + 1)]
    c2 = [sum(1 for b in y2 if b == v) / n for v in range(max_val + 1)]
    exp_dis = sum(
        c1[i] * c2[j] * (abs(i - j) / max_val)
        for i in range(max_val + 1)
        for j in range(max_val + 1)
    )
    if exp_dis < 1e-12:
        return 1.0
    return round(1.0 - (obs_dis / exp_dis), 6)


def _verify_lock_and_archive() -> tuple[dict[str, object], dict[str, object]]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    checked = 0
    for rel, expected in lock["locked_files_sha256"].items():
        actual = _sha256_file(REPO / rel)
        checked += 1
        if actual != expected:
            raise RuntimeError(f"WO-46 lock hash mismatch on {rel}: {actual} != {expected}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    pages = manifest["pages"]
    verified_pages = 0
    for entry in pages:
        gz_path = REPO / entry["archive_path"]
        gz_bytes = gz_path.read_bytes()
        if _sha256_bytes(gz_bytes) != entry["archive_gz_sha256"]:
            raise RuntimeError(f"Archive gz hash mismatch: {entry['archive_path']}")
        raw_bytes = gzip.decompress(gz_bytes)
        if _sha256_bytes(raw_bytes) != entry["raw_html_sha256"]:
            raise RuntimeError(f"Archive uncompressed HTML hash mismatch: {entry['archive_path']}")
        verified_pages += 1

    return (
        {
            "lock_path": "logs/test_reports/wo46/real_web_v2_prereg_lock.json",
            "lock_sha256": _sha256_file(LOCK_PATH),
            "verified_files_count": checked,
            "all_hashes_matched": True,
        },
        {
            "manifest_path": "data/benchmarks/web_real_v2_archive/manifest_sha256.json",
            "manifest_sha256": _sha256_file(MANIFEST_PATH),
            "verified_archived_pages": verified_pages,
            "all_archive_hashes_matched": True,
        },
    )


def _burden_met(indep_count: int, dispute: bool, hazard_str: str) -> bool:
    if dispute:
        return False
    return indep_count >= REQ_SOURCES_FOR_HAZARD[hazard_str]


def main() -> None:
    if OUT_PATH.exists():
        raise RuntimeError(f"Single-shot holdout report already exists at {OUT_PATH}")

    lock_info, archive_info = _verify_lock_and_archive()
    corpus = [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    blind_map: dict[str, str] = json.loads(BLIND_MAP_PATH.read_text(encoding="utf-8"))
    qid_to_bid = {v: k for k, v in blind_map.items()}

    r1_map = {
        row["blind_id"]: row
        for row in (
            json.loads(line)
            for line in RATER1_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    r2_map = {
        row["blind_id"]: row
        for row in (
            json.loads(line)
            for line in RATER2_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    adj_map: dict[str, dict[str, object]] = {}
    if ADJUDICATOR_PATH.exists():
        adj_map = {
            row["blind_id"]: row
            for row in (
                json.loads(line)
                for line in ADJUDICATOR_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        }

    bids_sorted = sorted(blind_map.keys())
    r1_cnt = [int(r1_map[b]["independent_source_count"]) for b in bids_sorted]
    r2_cnt = [int(r2_map[b]["independent_source_count"]) for b in bids_sorted]
    r1_dsp = [bool(r1_map[b]["dispute_present"]) for b in bids_sorted]
    r2_dsp = [bool(r2_map[b]["dispute_present"]) for b in bids_sorted]
    r1_hzd = [str(r1_map[b]["hazard_tier"]).lower() for b in bids_sorted]
    r2_hzd = [str(r2_map[b]["hazard_tier"]).lower() for b in bids_sorted]
    r1_brd = [
        _burden_met(c, d, h)
        for c, d, h in zip(r1_cnt, r1_dsp, r1_hzd, strict=True)
    ]
    r2_brd = [
        _burden_met(c, d, h)
        for c, d, h in zip(r2_cnt, r2_dsp, r2_hzd, strict=True)
    ]

    irr = {
        "n_items": len(bids_sorted),
        "dispute_present_kappa": _cohens_kappa(r1_dsp, r2_dsp),
        "dispute_present_agreement": round(
            sum(1 for a, b in zip(r1_dsp, r2_dsp, strict=True) if a == b) / len(bids_sorted), 6
        ),
        "independent_source_count_unweighted_kappa": _cohens_kappa(r1_cnt, r2_cnt),
        "independent_source_count_linear_weighted_kappa": _linear_weighted_kappa(r1_cnt, r2_cnt, 3),
        "independent_source_count_exact_agreement": round(
            sum(1 for a, b in zip(r1_cnt, r2_cnt, strict=True) if a == b) / len(bids_sorted), 6
        ),
        "hazard_tier_unweighted_kappa": _cohens_kappa(r1_hzd, r2_hzd),
        "hazard_tier_linear_weighted_kappa": _linear_weighted_kappa(
            [HAZARD_ORD[h] for h in r1_hzd], [HAZARD_ORD[h] for h in r2_hzd], 2
        ),
        "derived_burden_met_kappa": _cohens_kappa(r1_brd, r2_brd),
        "derived_burden_met_agreement": round(
            sum(1 for a, b in zip(r1_brd, r2_brd, strict=True) if a == b) / len(bids_sorted), 6
        ),
        "adjudicated_disagreements_count": len(adj_map),
    }

    item_rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    for row in corpus:
        qid = str(row["query_id"])
        bid = qid_to_bid[qid]
        r1 = r1_map[bid]
        r2 = r2_map[bid]
        adj = adj_map.get(bid)

        gt_cnt = int(
            adj["independent_source_count"]
            if adj is not None
            else (
                r1["independent_source_count"]
                if r1["independent_source_count"] == r2["independent_source_count"]
                else min(int(r1["independent_source_count"]), int(r2["independent_source_count"]))
            )
        )
        gt_dsp = bool(
            adj["dispute_present"]
            if adj is not None
            else (bool(r1["dispute_present"]) or bool(r2["dispute_present"]))
        )
        gt_hzd = str(
            adj["hazard_tier"]
            if adj is not None
            else (
                r1["hazard_tier"]
                if str(r1["hazard_tier"]).lower() == str(r2["hazard_tier"]).lower()
                else (
                    r1["hazard_tier"]
                    if HAZARD_ORD[str(r1["hazard_tier"]).lower()]
                    >= HAZARD_ORD[str(r2["hazard_tier"]).lower()]
                    else r2["hazard_tier"]
                )
            )
        ).lower()
        gt_meets = _burden_met(gt_cnt, gt_dsp, gt_hzd)

        res = evaluate_web_evidence_burden(
            query_text=str(row["query"]),
            search_results=row["search_results"],
        )
        pred_cnt_capped = min(3, int(res.independent_sources_count))
        pred_dsp = bool(res.disputed)
        pred_hzd = str(res.hazard.value).lower()
        pred_meets = bool(res.meets_casual_burden)

        rec: dict[str, object] = {
            "query_id": qid,
            "blind_id": bid,
            "query": row["query"],
            "retrieved_sources_count": row["sources_count"],
            "gt_independent_source_count": gt_cnt,
            "gt_dispute_present": gt_dsp,
            "gt_hazard_tier": gt_hzd,
            "gt_burden_met": gt_meets,
            "pred_independent_source_count": res.independent_sources_count,
            "pred_independent_source_count_capped3": pred_cnt_capped,
            "pred_disputed": pred_dsp,
            "pred_hazard_tier": pred_hzd,
            "pred_confidence": res.confidence,
            "pred_burden_met": pred_meets,
            "burden_decision_correct": pred_meets == gt_meets,
            "false_burden_pass_unsafe": pred_meets and (not gt_meets),
            "conservative_over_hedge": (not pred_meets) and gt_meets,
            "dispute_correct": pred_dsp == gt_dsp,
            "source_count_exact": pred_cnt_capped == gt_cnt,
            "source_count_abs_err": abs(pred_cnt_capped - gt_cnt),
            "hazard_conservative_safe": HAZARD_ORD[pred_hzd] >= HAZARD_ORD[gt_hzd],
            "hazard_exact": pred_hzd == gt_hzd,
        }
        item_rows.append(rec)
        if pred_meets != gt_meets:
            errors.append(rec)

    n = len(item_rows)
    b_corr = sum(int(bool(r["burden_decision_correct"])) for r in item_rows)
    unsafe_fp = sum(int(bool(r["false_burden_pass_unsafe"])) for r in item_rows)
    over_hedge = sum(int(bool(r["conservative_over_hedge"])) for r in item_rows)
    gt_fail_n = sum(int(not bool(r["gt_burden_met"])) for r in item_rows)
    gt_pass_n = sum(int(bool(r["gt_burden_met"])) for r in item_rows)

    dsp_pos = [r for r in item_rows if bool(r["gt_dispute_present"])]
    dsp_neg = [r for r in item_rows if not bool(r["gt_dispute_present"])]
    dsp_tp = sum(int(bool(r["pred_disputed"])) for r in dsp_pos)
    dsp_fp = sum(int(bool(r["pred_disputed"])) for r in dsp_neg)
    dsp_corr = sum(int(bool(r["dispute_correct"])) for r in item_rows)

    cnt_exact = sum(int(bool(r["source_count_exact"])) for r in item_rows)
    cnt_within1 = sum(int(int(r["source_count_abs_err"]) <= 1) for r in item_rows)  # type: ignore[call-overload]
    cnt_mae = round(sum(int(r["source_count_abs_err"]) for r in item_rows) / n, 4)  # type: ignore[call-overload]

    hzd_safe = sum(int(bool(r["hazard_conservative_safe"])) for r in item_rows)
    hzd_exact = sum(int(bool(r["hazard_exact"])) for r in item_rows)

    low_suff = [
        r for r in item_rows if bool(r["gt_burden_met"]) and str(r["gt_hazard_tier"]) == "low"
    ]
    low_over_hedge = sum(int(bool(r["conservative_over_hedge"])) for r in low_suff)

    metrics = {
        "n": n,
        "burden_decision_accuracy": {
            "k": b_corr,
            "n": n,
            "rate": round(b_corr / n, 6),
            "wilson_95ci": _wilson_ci(b_corr, n),
        },
        "safety_specificity_on_gt_burden_unmet": {
            "k": gt_fail_n - unsafe_fp,
            "n": gt_fail_n,
            "rate": round((gt_fail_n - unsafe_fp) / gt_fail_n, 6) if gt_fail_n else 1.0,
            "wilson_95ci": _wilson_ci(gt_fail_n - unsafe_fp, gt_fail_n),
            "unsafe_false_burden_pass_count": unsafe_fp,
        },
        "utility_pass_rate_on_gt_burden_met": {
            "k": gt_pass_n - over_hedge,
            "n": gt_pass_n,
            "rate": round((gt_pass_n - over_hedge) / gt_pass_n, 6) if gt_pass_n else 1.0,
            "wilson_95ci": _wilson_ci(gt_pass_n - over_hedge, gt_pass_n),
            "conservative_over_hedge_count": over_hedge,
            "over_hedge_rate": round(over_hedge / gt_pass_n, 6) if gt_pass_n else 0.0,
        },
        "low_hazard_sufficient_evidence_utility": {
            "pass_k": len(low_suff) - low_over_hedge,
            "n": len(low_suff),
            "pass_rate": round((len(low_suff) - low_over_hedge) / len(low_suff), 6)
            if low_suff
            else 1.0,
            "over_hedge_k": low_over_hedge,
            "over_hedge_rate": round(low_over_hedge / len(low_suff), 6) if low_suff else 0.0,
            "over_hedge_wilson_95ci": _wilson_ci(low_over_hedge, len(low_suff)),
        },
        "dispute_detection": {
            "accuracy_k": dsp_corr,
            "accuracy_rate": round(dsp_corr / n, 6),
            "accuracy_wilson_95ci": _wilson_ci(dsp_corr, n),
            "recall_k": dsp_tp,
            "recall_n": len(dsp_pos),
            "recall_rate": round(dsp_tp / len(dsp_pos), 6) if dsp_pos else 1.0,
            "fpr_k": dsp_fp,
            "fpr_n": len(dsp_neg),
            "fpr_rate": round(dsp_fp / len(dsp_neg), 6) if dsp_neg else 0.0,
        },
        "independent_source_count": {
            "exact_match_k": cnt_exact,
            "exact_match_rate": round(cnt_exact / n, 6),
            "exact_match_wilson_95ci": _wilson_ci(cnt_exact, n),
            "within_1_k": cnt_within1,
            "within_1_rate": round(cnt_within1 / n, 6),
            "mae": cnt_mae,
        },
        "hazard_classification": {
            "conservative_safe_k": hzd_safe,
            "conservative_safe_rate": round(hzd_safe / n, 6),
            "conservative_safe_wilson_95ci": _wilson_ci(hzd_safe, n),
            "strict_3class_k": hzd_exact,
            "strict_3class_rate": round(hzd_exact / n, 6),
            "strict_3class_wilson_95ci": _wilson_ci(hzd_exact, n),
        },
    }

    report = {
        "experiment": "WO-46 Out-of-Sample Live-Web ResearchTool/Scrapling Evaluation (web_evidentiary_burden_real_v2, N=64)",
        "single_shot_holdout": True,
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "lock_verification": lock_info,
        "archive_verification": archive_info,
        "corpus_path": "data/benchmarks/web_evidentiary_burden_real_v2.jsonl",
        "corpus_sha256": _sha256_file(CORPUS_PATH),
        "inter_rater_reliability": irr,
        "gate_accuracy_metrics": metrics,
        "error_taxonomy": errors,
        "items": item_rows,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(irr, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
