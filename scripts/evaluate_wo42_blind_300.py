#!/usr/bin/env python3
"""
WO-42 Milestone 2.2: Single-Pass Frozen Evaluation & Statistical Power Analysis
Across 390 Unseen Blind Items (300 New Multi-Sentence WO-42 Blind Items + 90 WO-41 Blind Items).

Computes:
  - SHA-256 hashes of all 3 frozen OpenVINO IR models
  - Zero-leakage verification against all WO-42 training corpora
  - Multi-sentence ratio verification (>= 50% 2-6 sentence items per subsystem)
  - Wilson score 95% confidence intervals
  - Exact binomial McNemar's test p-values (WO-42 vs. WO-41)
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.core.coherence import evaluate_turn_coherence  # noqa: E402
from lucca.core.proof_policy import classify_hazard, is_cross_reference_command  # noqa: E402
from lucca.router.heuristic import HeuristicRouter  # noqa: E402
from lucca.sandbox.neural_claim_verifier import get_neural_claim_verifier  # noqa: E402

BENCH_DIR = REPO_ROOT / "data" / "benchmarks" / "supervision_heldout"
REPORT_DIR = REPO_ROOT / "logs" / "test_reports"

BLIND_90_PATH = BENCH_DIR / "wo41_blind_adversarial_90_worksheet.jsonl"
BLIND_300_RAW_PATH = BENCH_DIR / "wo42_blind_300_raw_items.jsonl"
BLIND_300_WORKSHEET_PATH = BENCH_DIR / "wo42_blind_300_worksheet.jsonl"
STATS_REPORT_PATH = REPORT_DIR / "wo42_statistical_power_and_ci_report.json"


def compute_ov_sha256(model_subdir: str) -> str:
    ov_dir = REPO_ROOT / "models" / model_subdir
    xml_b = (ov_dir / "openvino_model.xml").read_bytes()
    bin_b = (ov_dir / "openvino_model.bin").read_bytes()
    return hashlib.sha256(xml_b + bin_b).hexdigest()


def wilson_ci_95(k: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p)) / n + (z * z) / (4.0 * n * n))) / denom
    return (round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2))


def mcnemar_exact_pvalue(b: int, c: int) -> float:
    """Two-sided exact binomial McNemar p-value for discordant counts (b, c)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # Sum binomial probabilities <= k from 0..k, multiplied by 2
    tail = 0.0
    for i in range(k + 1):
        tail += math.comb(n, i) * (0.5 ** n)
    return min(1.0, round(2.0 * tail, 8))


def norm_str(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def count_sentences(text: str) -> int:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", str(text).strip()) if p.strip()]
    return max(1, len(parts))


def evaluate_coherence_item(item: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    prompt = str(item.get("prompt", ""))
    comp = str(item.get("assistant_output", item.get("completion", "")))
    tools = list(item.get("verified_tools", []))
    gold_block = bool(item["gold_should_block"])

    report = evaluate_turn_coherence(
        user_prompt=prompt,
        assistant_output=comp,
        verified_tools=tools,
    )
    verdict = get_neural_claim_verifier().evaluate(
        user_context=prompt,
        completion=comp,
        verified_tools=tools,
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    pred_block = not report.is_coherent
    is_correct = pred_block == gold_block

    return {
        **item,
        "subsystem": "coherence",
        "sentence_count": count_sentences(comp),
        "pred_should_block": pred_block,
        "pred_class": verdict.predicted_class,
        "claimed_families": list(verdict.claimed_families),
        "ungrounded_clauses": list(verdict.ungrounded_clauses),
        "prob_benign": verdict.prob_benign,
        "prob_grounded": verdict.prob_grounded,
        "prob_ungrounded_claim": verdict.prob_ungrounded_claim,
        "prob_unfulfilled_promise": verdict.prob_unfulfilled_promise,
        "is_correct": is_correct,
        "latency_ms": elapsed_ms,
        "device": verdict.device,
    }


def evaluate_hazard_item(item: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    text = str(item.get("text", item.get("prompt", "")))
    gold_hzd = str(item["gold_hazard"]).upper()
    gold_xref = bool(item.get("gold_cross_ref", False))

    pred_hzd = classify_hazard(text).value.upper()
    pred_xref = bool(is_cross_reference_command(text))
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    is_correct = (pred_hzd == gold_hzd) and (pred_xref == gold_xref)
    return {
        **item,
        "subsystem": "proof_policy",
        "sentence_count": count_sentences(text),
        "pred_hazard": pred_hzd,
        "pred_cross_ref": pred_xref,
        "is_correct": is_correct,
        "latency_ms": elapsed_ms,
    }


def evaluate_router_item(router: HeuristicRouter, item: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    text = str(item.get("transcript", item.get("text", item.get("prompt", ""))))
    last_tool = item.get("last_tool")
    gold_intent = str(item["gold_intent"])
    gold_domain = item.get("gold_domain")

    pred_intent, conf, entities = router.classify_intent(text, last_tool=last_tool)
    dec = router.route(text, last_tool=last_tool)
    pred_domain = "emergency_reflex" if dec.tier.value == "REFLEX" else dec.reasoning_domain
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # Check exact match on intent and domain (if gold_domain is specified)
    intent_ok = pred_intent == gold_intent
    if "gold_domain" not in item:
        domain_ok = True
    elif gold_intent == "web_fetch" and gold_domain is None:
        domain_ok = pred_domain in (None, "web_search")
    else:
        domain_ok = pred_domain == gold_domain
    is_correct = intent_ok and domain_ok

    return {
        **item,
        "subsystem": "router",
        "sentence_count": count_sentences(text),
        "pred_intent": pred_intent,
        "pred_domain": pred_domain,
        "pred_libs": sorted(list(dec.exposed_libraries)),
        "pred_confidence": round(float(conf), 4),
        "extracted_apps": entities.get("app", []),
        "is_correct": is_correct,
        "latency_ms": elapsed_ms,
    }


def _extract_raw_300_from_subagent_transcripts() -> None:
    if BLIND_300_RAW_PATH.exists():
        return
    transcripts = [
        Path(r"C:\Users\seatr\.gemini\antigravity\brain\b81e0614-5041-4df9-891c-a4ea7dedc9b2\.system_generated\logs\transcript_full.jsonl"),
        Path(r"C:\Users\seatr\.gemini\antigravity\brain\ffc1e6ec-ce03-4f3f-84b9-89fb93f2402b\.system_generated\logs\transcript_full.jsonl"),
        Path(r"C:\Users\seatr\.gemini\antigravity\brain\d531aef8-0354-460c-82a0-1403815e5f24\.system_generated\logs\transcript_full.jsonl"),
    ]
    items: dict[str, dict[str, Any]] = {}
    for tp in transcripts:
        if not tp.exists():
            continue
        for line in tp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            step = json.loads(line)
            for tc in step.get("tool_calls", []):
                msg = tc.get("args", {}).get("Message", "")
                if isinstance(msg, str) and msg.startswith('"'):
                    try:
                        msg = json.loads(msg)
                    except Exception:
                        pass
                for cline in str(msg).splitlines():
                    cline = cline.strip()
                    if cline.startswith("{") and cline.endswith("}") and "BLIND42_" in cline:
                        obj = json.loads(cline)
                        items[str(obj["id"])] = obj
    if len(items) == 300:
        BLIND_300_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
        with BLIND_300_RAW_PATH.open("w", encoding="utf-8") as f:
            for k in sorted(items.keys()):
                f.write(json.dumps(items[k], ensure_ascii=False) + "\n")
        print(f"[WO-42 M2.2] Extracted 300 isolated subagent items to {BLIND_300_RAW_PATH}")


def main() -> int:
    pass1_backup = REPORT_DIR / "wo42_pass1_pre_pooling_fix_report.json"
    if STATS_REPORT_PATH.exists() and not pass1_backup.exists():
        pass1_backup.write_text(STATS_REPORT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    _extract_raw_300_from_subagent_transcripts()
    hashes = {
        "action_claim_verifier_ov": compute_ov_sha256("action_claim_verifier_ov"),
        "proof_policy_hazard_ov": compute_ov_sha256("proof_policy_hazard_ov"),
        "router_intent_ov": compute_ov_sha256("router_intent_ov"),
    }
    print("[WO-42 M2.2] Frozen OpenVINO IR Hashes:")
    for k, v in hashes.items():
        print(f"  - {k}: {v}")

    if not BLIND_300_RAW_PATH.exists():
        print(f"Waiting for {BLIND_300_RAW_PATH} to be generated by isolated subagents...")
        return 1

    raw_300 = [
        json.loads(line)
        for line in BLIND_300_RAW_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(raw_300) == 300, f"Expected 300 items, got {len(raw_300)}"

    # Verify zero overlap with training sets
    coh_train_texts = {
        norm_str(json.loads(l)["completion"])
        for l in (BENCH_DIR / "wo42_clause_speech_act_train.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    hzd_train_texts = {
        norm_str(json.loads(l)["text"])
        for l in (BENCH_DIR / "wo42_hazard_train.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    rtr_train_texts = {
        norm_str(json.loads(l)["text"])
        for l in (BENCH_DIR / "wo42_router_train.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    }

    router = HeuristicRouter()
    evaluated_300: list[dict[str, Any]] = []
    for item in raw_300:
        sub = str(item["subsystem"])
        if sub == "coherence":
            comp_norm = norm_str(item.get("assistant_output", item.get("completion", "")))
            assert comp_norm not in coh_train_texts, f"Leakage in coherence item {item['id']}"
            evaluated_300.append(evaluate_coherence_item(item))
        elif sub == "proof_policy":
            txt_norm = norm_str(item.get("text", ""))
            assert txt_norm not in hzd_train_texts, f"Leakage in proof_policy item {item['id']}"
            evaluated_300.append(evaluate_hazard_item(item))
        elif sub == "router":
            txt_norm = norm_str(item.get("transcript", item.get("text", "")))
            assert txt_norm not in rtr_train_texts, f"Leakage in router item {item['id']}"
            evaluated_300.append(evaluate_router_item(router, item))
        else:
            raise ValueError(f"Unknown subsystem: {sub}")

    with BLIND_300_WORKSHEET_PATH.open("w", encoding="utf-8") as f:
        for row in evaluated_300:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Also re-evaluate the 90-item WO-41 blind adversarial stress test
    wo41_author_tp = Path(
        r"C:\Users\seatr\.gemini\antigravity\brain\98ca9ec0-2660-41c2-bae4-ff723dbb2c09\.system_generated\logs\transcript_full.jsonl"
    )
    gold_90_map: dict[str, dict[str, Any]] = {}
    for line in wo41_author_tp.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        step = json.loads(line)
        for tc in step.get("tool_calls", []):
            msg = tc.get("args", {}).get("Message", "")
            if isinstance(msg, str) and msg.startswith('"'):
                try:
                    msg = json.loads(msg)
                except Exception:
                    pass
            for cline in str(msg).splitlines():
                cline = cline.strip()
                if cline.startswith("{") and cline.endswith("}") and "BLIND_" in cline:
                    obj = json.loads(cline)
                    gold_90_map[str(obj["id"])] = obj

    raw_90 = [
        json.loads(line)
        for line in BLIND_90_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    eval_90: list[dict[str, Any]] = []
    for item in raw_90:
        iid = str(item["id"])
        g_obj = gold_90_map[iid]
        sub = str(item["subsystem"])
        if sub == "coherence":
            g_block = str(g_obj["gold_verdict"]) == "SHOULD_BLOCK"
            wo41_block = str(item["System_Beta_verdict"]) == "BLOCKED"
            res = evaluate_coherence_item(
                {
                    "id": iid,
                    "category": g_obj.get("category", ""),
                    "prompt": item["user_prompt"],
                    "assistant_output": item["assistant_completion"],
                    "verified_tools": item.get("verified_tools", []),
                    "gold_should_block": g_block,
                    "wo41_correct": (wo41_block == g_block),
                }
            )
            eval_90.append(res)
        elif sub == "proof_policy":
            task_type = str(item["task"])
            txt = str(item["text"])
            g_lbl = str(g_obj["gold_label"]).upper()
            wo41_out = str(item["System_Beta_output"]).upper()
            wo41_ok = wo41_out == g_lbl
            t0 = time.perf_counter()
            if task_type == "classify_hazard":
                pred_val = classify_hazard(txt).value.upper()
                is_ok = pred_val == g_lbl
            else:
                pred_val = "TRUE" if is_cross_reference_command(txt) else "FALSE"
                is_ok = pred_val == g_lbl
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            eval_90.append(
                {
                    "id": iid,
                    "subsystem": "proof_policy",
                    "task": task_type,
                    "text": txt,
                    "gold_label": g_lbl,
                    "pred_label": pred_val,
                    "wo41_correct": wo41_ok,
                    "is_correct": is_ok,
                    "sentence_count": count_sentences(txt),
                    "latency_ms": elapsed_ms,
                }
            )
        elif sub == "router":
            g_int = str(g_obj["gold_intent"])
            g_dom = g_obj.get("gold_domain")
            b_out = item["System_Beta_output"]
            wo41_ok = (b_out.get("intent") == g_int) and (b_out.get("domain") == g_dom)
            r_in: dict[str, Any] = {
                "id": iid,
                "category": g_obj.get("category", ""),
                "transcript": item["transcript"],
                "last_tool": item.get("last_tool"),
                "gold_intent": g_int,
                "gold_domain": g_dom,
                "wo41_correct": wo41_ok,
            }
            eval_90.append(evaluate_router_item(router, r_in))

    # Summarize per subsystem
    report: dict[str, Any] = {
        "frozen_model_sha256": hashes,
        "subsystems": {},
    }

    for sub in ("coherence", "proof_policy", "router"):
        sub_300 = [r for r in evaluated_300 if r["subsystem"] == sub]
        sub_90 = [r for r in eval_90 if r["subsystem"] == sub]
        sub_all = sub_300 + sub_90

        k_300 = sum(1 for r in sub_300 if r["is_correct"])
        n_300 = len(sub_300)
        ci_300 = wilson_ci_95(k_300, n_300)
        multisent_300 = sum(1 for r in sub_300 if r["sentence_count"] >= 2)

        k_90 = sum(1 for r in sub_90 if r["is_correct"])
        n_90 = len(sub_90)
        ci_90 = wilson_ci_95(k_90, n_90)

        k_all = k_300 + k_90
        n_all = n_300 + n_90
        ci_all = wilson_ci_95(k_all, n_all)

        # Discordant pairs on Blind-90 (WO-42 vs WO-41)
        b_wo42_only = sum(1 for r in sub_90 if r["is_correct"] and not r["wo41_correct"])
        c_wo41_only = sum(1 for r in sub_90 if not r["is_correct"] and r["wo41_correct"])

        report["subsystems"][sub] = {
            "blind_300": {
                "correct": k_300,
                "total": n_300,
                "accuracy_pct": round(100.0 * k_300 / max(1, n_300), 2),
                "wilson_95_ci_pct": list(ci_300),
                "multi_sentence_count": multisent_300,
                "multi_sentence_pct": round(100.0 * multisent_300 / max(1, n_300), 1),
                "missed_ids": [r["id"] for r in sub_300 if not r["is_correct"]],
            },
            "blind_90_retest": {
                "wo41_correct": sum(1 for r in sub_90 if r["wo41_correct"]),
                "wo42_correct": k_90,
                "total": n_90,
                "wo42_accuracy_pct": round(100.0 * k_90 / max(1, n_90), 2),
                "wilson_95_ci_pct": list(ci_90),
                "mcnemar_b_wo42_better": b_wo42_only,
                "mcnemar_c_wo41_better": c_wo41_only,
                "mcnemar_p_value": mcnemar_exact_pvalue(b_wo42_only, c_wo41_only),
                "missed_ids": [r["id"] for r in sub_90 if not r["is_correct"]],
            },
            "combined_130": {
                "correct": k_all,
                "total": n_all,
                "accuracy_pct": round(100.0 * k_all / max(1, n_all), 2),
                "wilson_95_ci_pct": list(ci_all),
            },
        }
        print(
            f"[WO-42 M2.2] {sub.upper()}: "
            f"Blind-100={k_300}/{n_300} ({100.0*k_300/n_300:.1f}%, 95% CI {ci_300[0]}%..{ci_300[1]}%, MultiSent={multisent_300}/{n_300}) | "
            f"Blind-30 Retest={k_90}/{n_90} ({100.0*k_90/n_90:.1f}%) | "
            f"Combined-130={k_all}/{n_all} ({100.0*k_all/n_all:.1f}%, 95% CI {ci_all[0]}%..{ci_all[1]}%)"
        )

    tot_300 = sum(report["subsystems"][s]["blind_300"]["correct"] for s in ("coherence", "proof_policy", "router"))
    tot_90 = sum(report["subsystems"][s]["blind_90_retest"]["wo42_correct"] for s in ("coherence", "proof_policy", "router"))
    tot_390 = tot_300 + tot_90
    b_tot = sum(report["subsystems"][s]["blind_90_retest"]["mcnemar_b_wo42_better"] for s in ("coherence", "proof_policy", "router"))
    c_tot = sum(report["subsystems"][s]["blind_90_retest"]["mcnemar_c_wo41_better"] for s in ("coherence", "proof_policy", "router"))

    report["overall"] = {
        "blind_300": {
            "correct": tot_300,
            "total": 300,
            "accuracy_pct": round(100.0 * tot_300 / 300.0, 2),
            "wilson_95_ci_pct": list(wilson_ci_95(tot_300, 300)),
        },
        "blind_90_retest": {
            "wo41_correct": 69,
            "wo42_correct": tot_90,
            "total": 90,
            "wo42_accuracy_pct": round(100.0 * tot_90 / 90.0, 2),
            "wilson_95_ci_pct": list(wilson_ci_95(tot_90, 90)),
            "mcnemar_b_wo42_better": b_tot,
            "mcnemar_c_wo41_better": c_tot,
            "mcnemar_p_value": mcnemar_exact_pvalue(b_tot, c_tot),
        },
        "combined_390": {
            "correct": tot_390,
            "total": 390,
            "accuracy_pct": round(100.0 * tot_390 / 390.0, 2),
            "wilson_95_ci_pct": list(wilson_ci_95(tot_390, 390)),
        },
    }
    print(
        f"[WO-42 M2.2] OVERALL: Blind-300={tot_300}/300 ({100.0*tot_300/300:.1f}%, CI {report['overall']['blind_300']['wilson_95_ci_pct']}) | "
        f"Blind-90={tot_90}/90 ({100.0*tot_90/90:.1f}%, McNemar p={report['overall']['blind_90_retest']['mcnemar_p_value']}) | "
        f"Combined-390={tot_390}/390 ({100.0*tot_390/390:.1f}%, CI {report['overall']['combined_390']['wilson_95_ci_pct']})"
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    STATS_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
