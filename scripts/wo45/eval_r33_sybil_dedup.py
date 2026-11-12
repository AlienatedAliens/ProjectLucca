"""Single-shot evaluation of WO-45 R-33 fresh adversarial sybil/syndication holdout (N=45)."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from lucca.core.proof_policy import evaluate_web_evidence_burden

REPO = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO / "logs" / "test_reports" / "wo45" / "r33_sybil_holdout_prereg_lock.json"
DEV_BASELINE_PATH = REPO / "logs" / "test_reports" / "wo45" / "r33_pre_dedup_dev_baseline.json"
HOLDOUT_PATH = REPO / "data" / "benchmarks" / "wo45_r33_sybil_holdout_45.jsonl"
OUT_PATH = REPO / "logs" / "test_reports" / "wo45" / "r33_sybil_dedup_report.json"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denom
    return [round(max(0.0, center - half), 6), round(min(1.0, center + half), 6)]


def _verify_lock() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked_files: dict[str, str] = lock["locked_files_sha256"]
    checked = 0
    mismatches: list[dict[str, str]] = []
    for rel, expected in locked_files.items():
        actual = _sha256(REPO / rel)
        checked += 1
        if actual != expected:
            mismatches.append({"file": rel, "expected": expected, "actual": actual})
    if mismatches:
        raise RuntimeError(f"R-33 preregistration lock hash mismatch: {mismatches}")
    return {
        "lock_path": "logs/test_reports/wo45/r33_sybil_holdout_prereg_lock.json",
        "lock_sha256": _sha256(LOCK_PATH),
        "verified_files_count": checked,
        "all_hashes_matched": True,
    }


def main() -> None:
    lock_check = _verify_lock()
    dev_before = json.loads(DEV_BASELINE_PATH.read_text(encoding="utf-8"))
    items = [
        json.loads(line)
        for line in HOLDOUT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(items) != 45:
        raise RuntimeError(f"Expected 45 holdout items, got {len(items)}")

    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    by_scen: dict[str, dict[str, int]] = {}

    for item in items:
        scen = str(item["scenario"])
        gt_indep = int(item["ground_truth_effective_independent_sources"])
        gt_disp = bool(item["ground_truth_disputed"])

        res = evaluate_web_evidence_burden(
            query_text=str(item["query"]),
            search_results=item["search_results"],
        )

        inflated_sources = res.independent_sources_count > gt_indep
        missed_dispute = gt_disp and (not res.disputed)
        false_dispute = (not gt_disp) and res.disputed
        false_corroboration = inflated_sources or missed_dispute

        gt_meets_casual = (not gt_disp) and (
            (res.hazard.value == "low" and gt_indep >= 1)
            or (res.hazard.value == "medium" and gt_indep >= 2)
            or (res.hazard.value == "high" and gt_indep >= 3)
        )
        false_burden_pass = bool(res.meets_casual_burden and not gt_meets_casual)

        st = by_scen.setdefault(
            scen,
            {
                "n": 0,
                "false_corroboration": 0,
                "inflated_sources": 0,
                "missed_dispute": 0,
                "false_dispute": 0,
                "false_burden_pass": 0,
                "gt_burden_should_fail": 0,
            },
        )
        st["n"] += 1
        st["false_corroboration"] += int(false_corroboration)
        st["inflated_sources"] += int(inflated_sources)
        st["missed_dispute"] += int(missed_dispute)
        st["false_dispute"] += int(false_dispute)
        st["false_burden_pass"] += int(false_burden_pass)
        st["gt_burden_should_fail"] += int(not gt_meets_casual)

        rec: dict[str, object] = {
            "item_id": item["item_id"],
            "scenario": scen,
            "domain_topic": item["domain_topic"],
            "query": item["query"],
            "hazard": res.hazard.value,
            "pred_independent_sources": res.independent_sources_count,
            "pred_disputed": res.disputed,
            "pred_confidence": res.confidence,
            "pred_meets_casual": res.meets_casual_burden,
            "gt_effective_independent_sources": gt_indep,
            "gt_disputed": gt_disp,
            "gt_meets_casual": gt_meets_casual,
            "inflated_sources": inflated_sources,
            "missed_dispute": missed_dispute,
            "false_dispute": false_dispute,
            "false_corroboration": false_corroboration,
            "false_burden_pass": false_burden_pass,
        }
        rows.append(rec)
        if false_corroboration or false_dispute or false_burden_pass:
            failures.append(rec)

    total_n = len(rows)
    total_fc = sum(int(bool(r["false_corroboration"])) for r in rows)
    total_inf = sum(int(bool(r["inflated_sources"])) for r in rows)
    total_md = sum(int(bool(r["missed_dispute"])) for r in rows)
    total_fd = sum(int(bool(r["false_dispute"])) for r in rows)
    total_fbp = sum(int(bool(r["false_burden_pass"])) for r in rows)
    total_should_fail = sum(int(not bool(r["gt_meets_casual"])) for r in rows)

    scen_summary: dict[str, object] = {}
    for scen, st in by_scen.items():
        n_s = st["n"]
        fc_s = st["false_corroboration"]
        scen_summary[scen] = {
            **st,
            "false_corroboration_rate": round(fc_s / n_s, 6),
            "false_corroboration_wilson_95ci": _wilson_ci(fc_s, n_s),
            "rule_of_three_95_upper": round(3.0 / n_s, 6) if fc_s == 0 else None,
        }

    report = {
        "experiment": "WO-45 R-33 Post-Deduplication Fresh Holdout Evaluation (N=45)",
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "lock_verification": lock_check,
        "holdout_corpus_path": "data/benchmarks/wo45_r33_sybil_holdout_45.jsonl",
        "holdout_corpus_sha256": _sha256(HOLDOUT_PATH),
        "before_pre_dedup_dev_baseline": {
            "corpus_path": dev_before["corpus_path"],
            "corpus_sha256": dev_before["corpus_sha256"],
            "git_head_sha": dev_before["git_head_sha"],
            "overall": dev_before["overall"],
            "by_scenario": dev_before["by_scenario"],
        },
        "after_post_dedup_fresh_holdout": {
            "n": total_n,
            "false_corroboration_count": total_fc,
            "false_corroboration_rate": round(total_fc / total_n, 6),
            "false_corroboration_wilson_95ci": _wilson_ci(total_fc, total_n),
            "rule_of_three_95_upper": round(3.0 / total_n, 6) if total_fc == 0 else None,
            "inflated_source_count": total_inf,
            "inflated_source_rate": round(total_inf / total_n, 6),
            "missed_dispute_on_sybil_c": f"{total_md}/15",
            "false_dispute_on_non_disputed": f"{total_fd}/30",
            "false_burden_pass_count": total_fbp,
            "gt_burden_should_fail_count": total_should_fail,
            "false_burden_pass_rate_on_should_fail": (
                round(total_fbp / total_should_fail, 6) if total_should_fail else 0.0
            ),
            "by_scenario": scen_summary,
        },
        "error_taxonomy": failures,
        "items": rows,
    }

    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["lock_verification"], indent=2))
    print(json.dumps(report["after_post_dedup_fresh_holdout"], indent=2))


if __name__ == "__main__":
    main()
