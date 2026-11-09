#!/usr/bin/env python3
"""
WO-45 Task R-31: Evaluation of Non-Trivial Baselines (Count-Only and Hazard-Only)
on the N=360 Web Evidentiary Burden Corpus (`data/benchmarks/web_evidentiary_burden_360.jsonl`).

Analysis Label: post-hoc analysis on the WO-44 corpus.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.core.corroboration import normalize_source_identity  # noqa: E402
from lucca.core.proof_policy import _extract_source_domain  # noqa: E402


def wilson_ci_95(k: int, n: int) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p)) / n + (z * z) / (4.0 * n * n))) / denom
    return [round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2)]


def exact_mcnemar(b: int, c: int) -> dict[str, float | str]:
    n = b + c
    if n == 0:
        return {"discordant_b_c": "0:0", "chi2_cc": 0.0, "exact_binomial_two_sided_p": 1.0}
    chi2 = ((abs(b - c) - 1.0) ** 2) / n if abs(b - c) > 0 else 0.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    p_val = min(1.0, 2.0 * tail)
    return {
        "discordant_b_c": f"{b}:{c}",
        "chi2_cc": round(chi2, 4),
        "exact_binomial_two_sided_p": p_val,
    }


def main() -> None:
    bench_path = REPO_ROOT / "data/benchmarks/web_evidentiary_burden_360.jsonl"
    report_path = REPO_ROOT / "logs/test_reports/web_evidentiary_burden_360_report.json"

    items = [
        json.loads(ln)
        for ln in bench_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    frozen_report = json.loads(report_path.read_text(encoding="utf-8"))
    probe_map = {str(r["probe_id"]): r for r in frozen_report["probe_results"]}

    n_total = len(items)
    assert n_total == 360

    # For each item, ground truth for casual synthesis gate:
    # gold_assert = True means burden is met (assert allowed); False means hedge/conflict disclosure required.
    # Also track unsafe under-hedge (predicting assert when gold_assert is False)
    # and conservative over-hedge (predicting hedge when gold_assert is True).

    methods: dict[str, list[bool]] = {
        "static_085_strawman": [],
        "count_only_no_dispute": [],
        "count_plus_dispute_no_hazard": [],
        "hazard_only_nominal": [],
        "hazard_only_npu": [],
        "lucca_2d_nominal_hazard": [],
        "lucca_2d_npu_end_to_end": [],
    }
    gold_assert_list: list[bool] = []

    for item in items:
        pid = str(item["probe_id"])
        p_res = probe_map[pid]

        gold_assert = bool(item["expected_meets_casual"]) and not bool(item["expected_disputed"])
        gold_assert_list.append(gold_assert)

        indep_count = int(p_res["independent_sources_count"])
        is_disputed = bool(p_res["disputed"])
        exp_h = str(item["expected_hazard"]).lower()
        pred_h = str(p_res["predicted_hazard"]).lower()

        raw_doms: set[str] = set()
        for idx_r, r_obj in enumerate(item["search_results"], 1):
            if isinstance(r_obj, dict):
                u_str = str(r_obj.get("url", "") or r_obj.get("source_url", "") or "").strip()
                d_str = str(r_obj.get("domain", "") or r_obj.get("source", "") or u_str).strip()
                raw_doms.add(normalize_source_identity(_extract_source_domain(d_str, idx_r)))
        raw_domain_count = len(raw_doms)

        # 0. Static 0.85 under nominal hazard (asserts on LOW/MEDIUM since 0.85 >= 0.75, hedges on HIGH since 0.85 < 0.95)
        methods["static_085_strawman"].append(exp_h in ("low", "medium"))

        # (a1) Count-only rule: 1 distinct domain -> hedge (False), >=2 distinct domains -> assert (True), ignoring hazard and dispute
        methods["count_only_no_dispute"].append(raw_domain_count >= 2)

        # (a2) Count + dispute rule (ignoring hazard): 1 source or disputed -> hedge (False), >=2 undisp -> assert (True)
        methods["count_plus_dispute_no_hazard"].append((raw_domain_count >= 2) and (not is_disputed))

        # (b1) Hazard-only rule (nominal hazard): HIGH always hedges (False), LOW/MEDIUM always asserts (True)
        methods["hazard_only_nominal"].append(exp_h != "high")

        # (b2) Hazard-only rule (NPU predicted hazard): pred HIGH always hedges (False), LOW/MEDIUM asserts (True)
        methods["hazard_only_npu"].append(pred_h != "high")

        # Lucca 2D with nominal/oracle hazard (Walton 2D specification)
        req_sources_nom = 1 if exp_h == "low" else (2 if exp_h == "medium" else 3)
        methods["lucca_2d_nominal_hazard"].append(
            (indep_count >= req_sources_nom) and (not is_disputed)
        )

        # Lucca 2D end-to-end with live NPU hazard classifier
        methods["lucca_2d_npu_end_to_end"].append(bool(p_res["meets_casual_burden"]))

    lucca_e2e_correct = [
        pred == gold for pred, gold in zip(methods["lucca_2d_npu_end_to_end"], gold_assert_list, strict=True)
    ]
    lucca_nom_correct = [
        pred == gold for pred, gold in zip(methods["lucca_2d_nominal_hazard"], gold_assert_list, strict=True)
    ]

    summary_table: dict[str, dict[str, object]] = {}
    for m_name, preds in methods.items():
        corr_vec = [p == g for p, g in zip(preds, gold_assert_list, strict=True)]
        k_corr = sum(1 for x in corr_vec if x)
        # Unsafe under-hedge: gold says hedge (g=False), model says assert (p=True)
        unsafe_under_hedge = sum(
            1 for p, g in zip(preds, gold_assert_list, strict=True) if p and not g
        )
        # Over-hedge: gold says assert (g=True), model says hedge (p=False)
        over_hedge = sum(
            1 for p, g in zip(preds, gold_assert_list, strict=True) if (not p) and g
        )
        # Safe compliance: never under-hedges (either matches gold or conservatively hedges)
        safe_count = n_total - unsafe_under_hedge

        # Paired McNemar vs Lucca 2D End-to-End (NPU)
        b_e2e = sum(1 for l_ok, m_ok in zip(lucca_e2e_correct, corr_vec, strict=True) if l_ok and not m_ok)
        c_e2e = sum(1 for l_ok, m_ok in zip(lucca_e2e_correct, corr_vec, strict=True) if (not l_ok) and m_ok)

        # Paired McNemar vs Lucca 2D Nominal Hazard
        b_nom = sum(1 for l_ok, m_ok in zip(lucca_nom_correct, corr_vec, strict=True) if l_ok and not m_ok)
        c_nom = sum(1 for l_ok, m_ok in zip(lucca_nom_correct, corr_vec, strict=True) if (not l_ok) and m_ok)

        summary_table[m_name] = {
            "casual_gate_accuracy": f"{k_corr}/{n_total}",
            "casual_gate_accuracy_pct": round(k_corr / n_total * 100.0, 2),
            "wilson_95_ci_pct": wilson_ci_95(k_corr, n_total),
            "unsafe_under_hedge_count": f"{unsafe_under_hedge}/180",
            "unsafe_under_hedge_pct": round(unsafe_under_hedge / 180.0 * 100.0, 2),
            "over_hedge_on_met_cells_count": f"{over_hedge}/180",
            "over_hedge_on_met_cells_pct": round(over_hedge / 180.0 * 100.0, 2),
            "conservative_safety_compliance": f"{safe_count}/{n_total}",
            "conservative_safety_pct": round(safe_count / n_total * 100.0, 2),
            "mcnemar_lucca_e2e_vs_method": exact_mcnemar(b_e2e, c_e2e),
            "mcnemar_lucca_nominal_vs_method": exact_mcnemar(b_nom, c_nom),
        }

    payload = {
        "task_id": "R-31",
        "analysis_label": "post-hoc analysis on the WO-44 corpus",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "dataset_path": "data/benchmarks/web_evidentiary_burden_360.jsonl",
        "dataset_sha256": hashlib.sha256(bench_path.read_bytes()).hexdigest(),
        "n_total": n_total,
        "n_hedge_required_cells": 180,
        "n_assert_allowed_cells": 180,
        "baselines_comparison": summary_table,
    }

    out_path = REPO_ROOT / "logs/test_reports/wo45/r31_nontrivial_baselines_360.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {out_path}")
    for k, v in summary_table.items():
        print(
            f"  {k:30s}: acc={v['casual_gate_accuracy']} ({v['casual_gate_accuracy_pct']}%) | "
            f"unsafe_under={v['unsafe_under_hedge_count']} | over_hedge={v['over_hedge_on_met_cells_count']} | "
            f"McNemar vs Lucca E2E: {v['mcnemar_lucca_e2e_vs_method']}"
        )


if __name__ == "__main__":
    main()
