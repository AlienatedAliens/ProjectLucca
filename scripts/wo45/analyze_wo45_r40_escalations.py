#!/usr/bin/env python3
"""
WO-45 Task R-40: Analyze dual blinded rater hazard labels on the 73 upward-escalated
items from `web_evidentiary_burden_360_report.json`.
Computes Cohen's kappa, adjudicates disagreements, and classifies each item into
`{label_error, true_over_escalation, ambiguous}`.
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


def cohen_kappa(labels_1: list[str], labels_2: list[str], classes: list[str]) -> tuple[float, float]:
    assert len(labels_1) == len(labels_2)
    n = len(labels_1)
    if n == 0:
        return 0.0, 0.0
    agree = sum(1 for a, b in zip(labels_1, labels_2, strict=True) if a == b)
    p_o = agree / n
    c1 = Counter(labels_1)
    c2 = Counter(labels_2)
    p_e = sum((c1[c] / n) * (c2[c] / n) for c in classes)
    if abs(1.0 - p_e) < 1e-12:
        return 1.0, round(p_o * 100.0, 2)
    return round((p_o - p_e) / (1.0 - p_e), 4), round(p_o * 100.0, 2)


def wilson_ci_95(k: int, n: int) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p)) / n + (z * z) / (4.0 * n * n))) / denom
    return [round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2)]


def main() -> None:
    key_path = WO45_DIR / "r40_blinded_73_key.json"
    r1_path = WO45_DIR / "r40_rater1.jsonl"
    r2_path = WO45_DIR / "r40_rater2.jsonl"
    r3_path = WO45_DIR / "r40_rater3_adjudication.jsonl"

    key_map = json.loads(key_path.read_text(encoding="utf-8"))
    r1_map = {
        obj["item_id"]: obj
        for obj in (json.loads(ln) for ln in r1_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    }
    r2_map = {
        obj["item_id"]: obj
        for obj in (json.loads(ln) for ln in r2_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    }
    r3_map: dict[str, dict[str, str]] = {}
    if r3_path.exists():
        r3_map = {
            obj["item_id"]: obj
            for obj in (json.loads(ln) for ln in r3_path.read_text(encoding="utf-8").splitlines() if ln.strip())
        }

    ordered_ids = sorted(key_map.keys())
    assert len(ordered_ids) == 73

    l1 = [str(r1_map[bid]["rater_hazard"]).lower() for bid in ordered_ids]
    l2 = [str(r2_map[bid]["rater_hazard"]).lower() for bid in ordered_ids]
    kappa_3class, raw_agree_pct = cohen_kappa(l1, l2, ["low", "medium", "high"])

    rank = {"low": 0, "medium": 1, "high": 2}
    per_item_records: list[dict[str, object]] = []
    counts = {"label_error": 0, "true_over_escalation": 0, "ambiguous": 0}
    by_transition: dict[str, dict[str, int]] = {}

    for bid in ordered_ids:
        meta = key_map[bid]
        exp_h = str(meta["expected_hazard"]).lower()
        pred_h = str(meta["predicted_hazard"]).lower()
        h1 = str(r1_map[bid]["rater_hazard"]).lower()
        h2 = str(r2_map[bid]["rater_hazard"]).lower()
        h3 = str(r3_map[bid]["rater_hazard"]).lower() if bid in r3_map else None

        votes = [h1, h2] + ([h3] if h3 else [])
        vote_counts = Counter(votes)
        top_label, top_count = vote_counts.most_common(1)[0]

        if h1 == h2:
            adjudicated_hazard = h1
            if rank[adjudicated_hazard] > rank[exp_h]:
                category = "label_error"
            else:
                category = "true_over_escalation"
        elif h3 is not None and top_count >= 2:
            adjudicated_hazard = top_label
            if rank[adjudicated_hazard] > rank[exp_h]:
                category = "label_error"
            else:
                category = "true_over_escalation"
        else:
            # Raters split without majority
            if rank[h1] > rank[exp_h] and rank[h2] > rank[exp_h]:
                # Both raters agree it is higher than nominal!
                adjudicated_hazard = h1 if rank[h1] <= rank[h2] else h2
                category = "label_error"
            else:
                adjudicated_hazard = "ambiguous"
                category = "ambiguous"

        counts[category] += 1
        trans_key = f"{exp_h}_to_{pred_h}"
        by_transition.setdefault(
            trans_key, {"total": 0, "label_error": 0, "true_over_escalation": 0, "ambiguous": 0}
        )
        by_transition[trans_key]["total"] += 1
        by_transition[trans_key][category] += 1

        per_item_records.append(
            {
                "blind_id": bid,
                "probe_id": meta["probe_id"],
                "stratum": meta["stratum"],
                "topology": meta["topology"],
                "nominal_expected_hazard": exp_h,
                "npu_predicted_hazard": pred_h,
                "rater1_hazard": h1,
                "rater1_rationale": r1_map[bid].get("rationale", ""),
                "rater2_hazard": h2,
                "rater2_rationale": r2_map[bid].get("rationale", ""),
                "rater3_adjudication_hazard": h3,
                "adjudicated_hazard": adjudicated_hazard,
                "audit_classification": category,
                "query": meta["query"],
            }
        )

    per_item_records.sort(key=lambda r: str(r["probe_id"]))

    payload = {
        "task_id": "R-40",
        "analysis_label": "post-hoc blinded dual-rater audit of the 73 upward hazard escalations on the WO-44 N=360 corpus",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "n_escalated_items": 73,
        "rater_prompt_path": "logs/test_reports/wo45/prompts/r40_hazard_rater_prompt.md",
        "rater1_labels_path": "logs/test_reports/wo45/r40_rater1.jsonl",
        "rater2_labels_path": "logs/test_reports/wo45/r40_rater2.jsonl",
        "inter_rater_reliability": {
            "cohen_kappa_3class": kappa_3class,
            "raw_agreement_pct": raw_agree_pct,
            "agreed_items": sum(1 for a, b in zip(l1, l2, strict=True) if a == b),
            "total_items": 73,
        },
        "summary_counts": {
            "label_error": counts["label_error"],
            "label_error_pct": round(counts["label_error"] / 73.0 * 100.0, 2),
            "label_error_wilson_95_ci_pct": wilson_ci_95(counts["label_error"], 73),
            "true_over_escalation": counts["true_over_escalation"],
            "true_over_escalation_pct": round(counts["true_over_escalation"] / 73.0 * 100.0, 2),
            "true_over_escalation_wilson_95_ci_pct": wilson_ci_95(counts["true_over_escalation"], 73),
            "ambiguous": counts["ambiguous"],
            "ambiguous_pct": round(counts["ambiguous"] / 73.0 * 100.0, 2),
            "ambiguous_wilson_95_ci_pct": wilson_ci_95(counts["ambiguous"], 73),
        },
        "by_nominal_to_predicted_transition": by_transition,
        "adjudicated_items": per_item_records,
    }

    out_path = WO45_DIR / "r40_upward_escalations_73_audit.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {out_path} (SHA-256: {hashlib.sha256(out_path.read_bytes()).hexdigest()})")
    print("IRR:", payload["inter_rater_reliability"])
    print("Counts:", payload["summary_counts"])
    print("By transition:", payload["by_nominal_to_predicted_transition"])


if __name__ == "__main__":
    main()
