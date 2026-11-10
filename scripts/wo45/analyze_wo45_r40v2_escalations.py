#!/usr/bin/env python3
"""
WO-45 Task R-40 v2 (`REVIEW_G3.md`):
Analyze dual blinded rater hazard evaluations on the 163-item mixed pool
(`73` upward-escalated queries + `90` stratified non-escalated control queries).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WO45_DIR = REPO_ROOT / "logs/test_reports/wo45"
RANK = {"low": 0, "medium": 1, "high": 2}


def wilson_ci_95(k: int, n: int) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p)) / n + (z * z) / (4.0 * n * n))) / denom
    return [round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2)]


def cohen_kappa(labels_1: list[str], labels_2: list[str], classes: list[str]) -> dict[str, float | int]:
    assert len(labels_1) == len(labels_2)
    n = len(labels_1)
    agree = sum(1 for a, b in zip(labels_1, labels_2, strict=True) if a == b)
    p_o = agree / n if n > 0 else 0.0
    c1 = Counter(labels_1)
    c2 = Counter(labels_2)
    p_e = sum((c1[c] / n) * (c2[c] / n) for c in classes) if n > 0 else 0.0
    kappa = 1.0 if abs(1.0 - p_e) < 1e-12 else (p_o - p_e) / (1.0 - p_e)
    return {
        "n": n,
        "agreed": agree,
        "disagreed": n - agree,
        "raw_agreement_pct": round(p_o * 100.0, 2),
        "cohen_kappa": round(kappa, 4),
    }


def main() -> None:
    key_path = WO45_DIR / "r40v2_mixed_163_key.json"
    r1_path = WO45_DIR / "r40v2_rater1.jsonl"
    r2_path = WO45_DIR / "r40v2_rater2.jsonl"
    r3_path = WO45_DIR / "r40v2_rater3_adjudication.jsonl"

    r1_sha = hashlib.sha256(r1_path.read_bytes()).hexdigest()
    r2_sha = hashlib.sha256(r2_path.read_bytes()).hexdigest()
    assert r1_sha != r2_sha, f"FATAL: r40v2_rater1.jsonl and r40v2_rater2.jsonl have identical SHA-256 ({r1_sha})"

    key_map = json.loads(key_path.read_text(encoding="utf-8"))
    r1_map = {
        obj["blind_id"]: obj
        for obj in (json.loads(ln) for ln in r1_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    }
    r2_map = {
        obj["blind_id"]: obj
        for obj in (json.loads(ln) for ln in r2_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    }
    r3_map: dict[str, dict[str, object]] = {}
    if r3_path.exists():
        r3_map = {
            obj["blind_id"]: obj
            for obj in (json.loads(ln) for ln in r3_path.read_text(encoding="utf-8").splitlines() if ln.strip())
        }

    ordered_ids = sorted(key_map.keys())
    assert len(ordered_ids) == 163
    classes = ["low", "medium", "high"]

    all_l1 = [str(r1_map[bid]["rater_label"]).lower() for bid in ordered_ids]
    all_l2 = [str(r2_map[bid]["rater_label"]).lower() for bid in ordered_ids]
    kappa_all = cohen_kappa(all_l1, all_l2, classes)

    esc_ids = [bid for bid in ordered_ids if key_map[bid]["cohort"] == "escalated_73"]
    ctrl_ids = [bid for bid in ordered_ids if key_map[bid]["cohort"] == "control_90"]
    assert len(esc_ids) == 73
    assert len(ctrl_ids) == 90

    kappa_esc = cohen_kappa(
        [str(r1_map[bid]["rater_label"]).lower() for bid in esc_ids],
        [str(r2_map[bid]["rater_label"]).lower() for bid in esc_ids],
        classes,
    )
    kappa_ctrl = cohen_kappa(
        [str(r1_map[bid]["rater_label"]).lower() for bid in ctrl_ids],
        [str(r2_map[bid]["rater_label"]).lower() for bid in ctrl_ids],
        classes,
    )

    # Adjudicate & classify the 73 escalated items and 90 control items
    esc_counts = {"label_error": 0, "true_over_escalation": 0, "ambiguous": 0}
    by_transition: dict[str, dict[str, int]] = {}
    ctrl_by_stratum: dict[str, dict[str, int]] = {
        "low": {"n": 0, "exact_match_nominal": 0, "higher_than_nominal": 0, "lower_than_nominal": 0, "ambiguous": 0},
        "medium": {"n": 0, "exact_match_nominal": 0, "higher_than_nominal": 0, "lower_than_nominal": 0, "ambiguous": 0},
        "high": {"n": 0, "exact_match_nominal": 0, "higher_than_nominal": 0, "lower_than_nominal": 0, "ambiguous": 0},
    }
    evaluated_items: list[dict[str, object]] = []

    for bid in ordered_ids:
        meta = key_map[bid]
        l1 = str(r1_map[bid]["rater_label"]).lower()
        l2 = str(r2_map[bid]["rater_label"]).lower()
        l3 = str(r3_map[bid]["rater_label"]).lower() if bid in r3_map else None

        nom = str(meta["expected_hazard"]).lower()
        npu = str(meta["npu_hazard"]).lower()
        cohort = str(meta["cohort"])

        # Consensus / majority label
        votes = [l1, l2] + ([l3] if l3 is not None else [])
        top_lbl, top_cnt = Counter(votes).most_common(1)[0]
        has_consensus = (l1 == l2) or (l3 is not None and top_cnt >= 2)
        adjudicated_label = top_lbl if has_consensus else "ambiguous"

        verdict = ""
        if cohort == "escalated_73":
            trans_key = f"{nom} -> {npu}"
            by_transition.setdefault(
                trans_key, {"n": 0, "label_error": 0, "true_over_escalation": 0, "ambiguous": 0}
            )
            by_transition[trans_key]["n"] += 1
            if not has_consensus:
                verdict = "ambiguous"
            elif RANK[adjudicated_label] > RANK[nom]:
                # Raters agree the query genuinely has higher hazard than the nominal label
                verdict = "label_error"
            else:
                # Raters agree the query hazard is <= nominal, so NPU escalation was a true over-escalation
                verdict = "true_over_escalation"
            esc_counts[verdict] += 1
            by_transition[trans_key][verdict] += 1
        else:
            ctrl_by_stratum[nom]["n"] += 1
            if not has_consensus:
                verdict = "ambiguous"
                ctrl_by_stratum[nom]["ambiguous"] += 1
            elif adjudicated_label == nom:
                verdict = "exact_match_nominal"
                ctrl_by_stratum[nom]["exact_match_nominal"] += 1
            elif RANK[adjudicated_label] > RANK[nom]:
                verdict = "higher_than_nominal"
                ctrl_by_stratum[nom]["higher_than_nominal"] += 1
            else:
                verdict = "lower_than_nominal"
                ctrl_by_stratum[nom]["lower_than_nominal"] += 1

        evaluated_items.append(
            {
                "blind_id": bid,
                "probe_id": meta["probe_id"],
                "cohort": cohort,
                "nominal_hazard": nom,
                "npu_predicted_hazard": npu,
                "rater1_label": l1,
                "rater1_model": r1_map[bid]["judge_model"],
                "rater1_rationale": r1_map[bid]["rationale"],
                "rater2_label": l2,
                "rater2_model": r2_map[bid]["judge_model"],
                "rater2_rationale": r2_map[bid]["rationale"],
                "rater3_label": l3,
                "adjudicated_label": adjudicated_label,
                "verdict": verdict,
                "query": meta["query"],
            }
        )

    ctrl_exact_total = sum(v["exact_match_nominal"] for v in ctrl_by_stratum.values())
    ctrl_higher_total = sum(v["higher_than_nominal"] for v in ctrl_by_stratum.values())
    ctrl_lower_total = sum(v["lower_than_nominal"] for v in ctrl_by_stratum.values())
    ctrl_ambig_total = sum(v["ambiguous"] for v in ctrl_by_stratum.values())

    payload = {
        "task_id": "R-40-v2",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "prompt_path": "logs/test_reports/wo45/prompts/r40v2_hazard_rater_prompt.md",
        "pool_path": "logs/test_reports/wo45/r40v2_mixed_163_queries.jsonl",
        "rater1_path": "logs/test_reports/wo45/r40v2_rater1.jsonl",
        "rater1_sha256": r1_sha,
        "rater2_path": "logs/test_reports/wo45/r40v2_rater2.jsonl",
        "rater2_sha256": r2_sha,
        "hashes_distinct": r1_sha != r2_sha,
        "inter_rater_reliability": {
            "all_163_items": kappa_all,
            "escalated_73_subset": kappa_esc,
            "control_90_subset": kappa_ctrl,
        },
        "escalated_73_summary": {
            "n": 73,
            "label_error": {
                "count": esc_counts["label_error"],
                "pct": round(esc_counts["label_error"] / 73.0 * 100.0, 2),
                "wilson_95_ci": wilson_ci_95(esc_counts["label_error"], 73),
            },
            "true_over_escalation": {
                "count": esc_counts["true_over_escalation"],
                "pct": round(esc_counts["true_over_escalation"] / 73.0 * 100.0, 2),
                "wilson_95_ci": wilson_ci_95(esc_counts["true_over_escalation"], 73),
            },
            "ambiguous": {
                "count": esc_counts["ambiguous"],
                "pct": round(esc_counts["ambiguous"] / 73.0 * 100.0, 2),
                "wilson_95_ci": wilson_ci_95(esc_counts["ambiguous"], 73),
            },
            "by_transition": by_transition,
        },
        "control_90_label_noise_baseline": {
            "n": 90,
            "exact_match_nominal": {
                "count": ctrl_exact_total,
                "pct": round(ctrl_exact_total / 90.0 * 100.0, 2),
                "wilson_95_ci": wilson_ci_95(ctrl_exact_total, 90),
            },
            "higher_than_nominal": ctrl_higher_total,
            "lower_than_nominal": ctrl_lower_total,
            "ambiguous": ctrl_ambig_total,
            "by_nominal_stratum": ctrl_by_stratum,
        },
        "evaluated_items_163": evaluated_items,
    }

    out_json = WO45_DIR / "r40v2_upward_escalations_audit.json"
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    out_sha = hashlib.sha256(out_json.read_bytes()).hexdigest()
    print(f"Saved {out_json} (SHA-256: {out_sha})")
    print("IRR:", json.dumps(payload["inter_rater_reliability"], indent=2))
    print("Escalated 73:", json.dumps(payload["escalated_73_summary"], indent=2))
    print("Control 90:", json.dumps(payload["control_90_label_noise_baseline"], indent=2))


if __name__ == "__main__":
    main()
