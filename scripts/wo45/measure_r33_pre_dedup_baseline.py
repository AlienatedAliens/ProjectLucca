"""Measure pre-dedup ("before") false-corroboration rate on wo45_r33_sybil_dev_45.jsonl at pre-R33 HEAD."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime, timezone
from pathlib import Path

from lucca.core.proof_policy import evaluate_web_evidence_burden

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data" / "benchmarks" / "wo45_r33_sybil_dev_45.jsonl"
OUT = REPO / "logs" / "test_reports" / "wo45" / "r33_pre_dedup_dev_baseline.json"


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


def main() -> None:
    head_sha = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    )
    items = [
        json.loads(line)
        for line in CORPUS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(items) == 45, f"Expected 45 items, got {len(items)}"

    rows = []
    by_scen: dict[str, dict[str, int]] = {}
    for item in items:
        scen = str(item["scenario"])
        gt_indep = int(item["ground_truth_effective_independent_sources"])
        gt_disp = bool(item["ground_truth_disputed"])
        res = evaluate_web_evidence_burden(
            query_text=str(item["query"]),
            search_results=item["search_results"],
        )
        # False corroboration definition:
        # - On non-disputed copied/syndicated sets (gt_indep == 1, gt_disp == False):
        #   counting >= 2 independent sources (inflating confidence from 0.70 to 0.80/0.95).
        # - On sybil vs authoritative contrary (gt_disp == True):
        #   either failing to flag dispute (not res.disputed) OR inflating independent_sources_count > 1.
        inflated_sources = res.independent_sources_count > gt_indep
        missed_dispute = gt_disp and (not res.disputed)
        false_corroboration = inflated_sources or missed_dispute
        # End-to-end false burden pass: gate reports meets_casual_burden=True when ground truth
        # should FAIL casual burden (i.e. disputed, or hazard in {medium, high} with only 1 effective source).
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
                "false_burden_pass": 0,
                "gt_burden_should_fail": 0,
            },
        )
        st["n"] += 1
        st["false_corroboration"] += int(false_corroboration)
        st["inflated_sources"] += int(inflated_sources)
        st["missed_dispute"] += int(missed_dispute)
        st["false_burden_pass"] += int(false_burden_pass)
        st["gt_burden_should_fail"] += int(not gt_meets_casual)

        rows.append(
            {
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
                "false_corroboration": false_corroboration,
                "false_burden_pass": false_burden_pass,
            }
        )

    total_n = len(rows)
    total_fc = sum(int(r["false_corroboration"]) for r in rows)
    total_inf = sum(int(r["inflated_sources"]) for r in rows)
    total_md = sum(int(r["missed_dispute"]) for r in rows)
    total_fbp = sum(int(r["false_burden_pass"]) for r in rows)
    total_should_fail = sum(int(not r["gt_meets_casual"]) for r in rows)

    scen_summary = {}
    for scen, st in by_scen.items():
        n_s = st["n"]
        fc_s = st["false_corroboration"]
        scen_summary[scen] = {
            **st,
            "false_corroboration_rate": round(fc_s / n_s, 6),
            "false_corroboration_wilson_95ci": _wilson_ci(fc_s, n_s),
        }

    report = {
        "experiment": "WO-45 R-33 Pre-Deduplication Baseline (Dev Set N=45)",
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "git_head_sha": head_sha,
        "corpus_path": "data/benchmarks/wo45_r33_sybil_dev_45.jsonl",
        "corpus_sha256": _sha256(CORPUS),
        "code_sha256_before": {
            "src/lucca/core/proof_policy.py": _sha256(
                REPO / "src" / "lucca" / "core" / "proof_policy.py"
            ),
            "src/lucca/core/corroboration.py": _sha256(
                REPO / "src" / "lucca" / "core" / "corroboration.py"
            ),
            "src/lucca/core/walton_schemes/evaluators.py": _sha256(
                REPO / "src" / "lucca" / "core" / "walton_schemes" / "evaluators.py"
            ),
        },
        "overall": {
            "n": total_n,
            "false_corroboration_count": total_fc,
            "false_corroboration_rate": round(total_fc / total_n, 6),
            "false_corroboration_wilson_95ci": _wilson_ci(total_fc, total_n),
            "inflated_source_count": total_inf,
            "inflated_source_rate": round(total_inf / total_n, 6),
            "missed_dispute_on_sybil_c": f"{total_md}/15",
            "false_burden_pass_count": total_fbp,
            "gt_burden_should_fail_count": total_should_fail,
            "false_burden_pass_rate_on_should_fail": (
                round(total_fbp / total_should_fail, 6) if total_should_fail else 0.0
            ),
        },
        "by_scenario": scen_summary,
        "items": rows,
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["overall"], indent=2))
    print(json.dumps(report["by_scenario"], indent=2))


if __name__ == "__main__":
    main()
