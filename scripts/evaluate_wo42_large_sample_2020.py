#!/usr/bin/env python3
"""
WO-42 Large-Sample Supervision Evaluation across the 2,020-Turn Paper 2 & Organic Companion Corpus
(`W001..W1000`, `P2_001..P2_720`, `O001..O200`, `H001..H100`, plus `IMP_01..IMP_30`).

Compares:
  1. WO-40 Context-Aware Regex Supervisor (`use_neural_verifier=False`)
  2. WO-42 Clause-Level Neurosymbolic Intel NPU Supervisor (`use_neural_verifier=True`, `action_claim_verifier_ov`)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from evaluate_ml_vs_regex_supervision import load_all_datasets  # noqa: E402
from lucca.core.coherence import detect_ungrounded_action_claims  # noqa: E402
from lucca.sandbox.neural_claim_verifier import get_neural_claim_verifier  # noqa: E402

REPORT_PATH = REPO_ROOT / "logs" / "test_reports" / "wo42_large_sample_2020_report.json"


def wilson_ci_95(k: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p)) / n + (z * z) / (4.0 * n * n))) / denom
    return (round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2))


def score_items(items: list[dict[str, Any]], use_neural: bool) -> dict[str, Any]:
    tp = tn = fp = fn = 0
    t0 = time.perf_counter()
    for it in items:
        comp = str(it["completion"])
        msgs = it["messages"]
        gt = bool(it["is_claim"])
        claims = detect_ungrounded_action_claims(
            comp,
            receipts=[],
            user_context=msgs,
            use_neural_verifier=use_neural,
        )
        pred = any(not c.grounded for c in claims)
        if gt and pred:
            tp += 1
        elif gt and not pred:
            fn += 1
        elif not gt and pred:
            fp += 1
        else:
            tn += 1
    elapsed_s = time.perf_counter() - t0
    pos = tp + fn
    neg = tn + fp
    total = pos + neg
    acc = (tp + tn) / total if total else 0.0
    rec = tp / pos if pos else 1.0
    fpr = fp / neg if neg else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    f1 = (2.0 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return {
        "n": total,
        "pos": pos,
        "neg": neg,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy_pct": round(acc * 100.0, 2),
        "accuracy_ci_95": list(wilson_ci_95(tp + tn, total)),
        "recall_pct": round(rec * 100.0, 2),
        "recall_ci_95": list(wilson_ci_95(tp, pos)),
        "fpr_pct": round(fpr * 100.0, 2),
        "fpr_ci_95": list(wilson_ci_95(fp, neg)),
        "precision_pct": round(prec * 100.0, 2),
        "f1_pct": round(f1 * 100.0, 2),
        "mean_latency_ms": round((elapsed_s * 1000.0) / max(1, total), 2),
    }


def main() -> int:
    nv = get_neural_claim_verifier()
    assert nv.available, "NeuralActionClaimVerifier must be available!"
    ds = load_all_datasets()

    w750 = [x for x in ds["train"] if str(x["id"]).startswith("W")]
    p2_720 = [x for x in ds["train"] if str(x["id"]).startswith("P2_")]
    o200 = [x for x in ds["train"] if str(x["id"]).startswith("O")]
    w26b = ds["test_w26b"]
    h100 = ds["test_h100"]
    imp30 = ds["test_imp30"]
    w1000 = w750 + w26b
    all_core = w1000 + p2_720 + o200 + h100 + imp30

    splits = [
        ("W001_W1000_4Model_Battery", w1000),
        ("W751_W1000_26B_Heldout", w26b),
        ("Paper2_v1_v2_720_Battery", p2_720),
        ("Organic_Discovery_O200", o200),
        ("Organic_Heldout_H100", h100),
        ("Implicit_ZeroVerb_IMP30", imp30),
        ("Pooled_All_Supervision_Turns", all_core),
    ]

    results: dict[str, Any] = {
        "device": nv.active_device,
        "splits": {},
    }

    for name, items in splits:
        m_reg = score_items(items, use_neural=False)
        m_npu = score_items(items, use_neural=True)
        results["splits"][name] = {
            "wo40_regex_v3_0": m_reg,
            "wo42_clause_npu": m_npu,
        }
        print(
            f"[{name:30s} N={m_npu['n']:4d}] "
            f"WO-40 Regex: Rec={m_reg['recall_pct']:5.1f}% ({m_reg['tp']}/{m_reg['pos']}), FPR={m_reg['fpr_pct']:4.1f}% ({m_reg['fp']}/{m_reg['neg']}), Acc={m_reg['accuracy_pct']:5.1f}% | "
            f"WO-42 NPU: Rec={m_npu['recall_pct']:5.1f}% ({m_npu['tp']}/{m_npu['pos']}), FPR={m_npu['fpr_pct']:4.1f}% ({m_npu['fp']}/{m_npu['neg']}), Acc={m_npu['accuracy_pct']:5.1f}% CI {m_npu['accuracy_ci_95']} ({m_npu['mean_latency_ms']} ms)"
        )

    REPORT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved report to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
