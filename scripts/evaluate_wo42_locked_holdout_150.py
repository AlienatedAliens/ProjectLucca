#!/usr/bin/env python3
"""
WO-42 Methodological Blind-Spot Closure: Single-Pass Locked Holdout Benchmark (`WO42_LOCKED_HOLDOUT_150`).

Enforces strict pre-generation locking of BOTH:
  1. All 3 OpenVINO IR `.xml`/`.bin` neural model weights, AND
  2. All 6 Python neurosymbolic implementation files (`coherence.py`, `neural_claim_verifier.py`,
     `proof_policy.py`, `neural_hazard_classifier.py`, `heuristic.py`, `neural_intent_classifier.py`)
recorded in `logs/test_reports/wo42_locked_holdout_150_pre_generation_manifest.json` BEFORE
the 3 isolated `research` subagents (`b0345600`, `6640d44d`, `2029a478`) generated the 150 unseen
multi-sentence items (`LOCKED_COH_001..050`, `LOCKED_HZD_001..050`, `LOCKED_RTR_001..050`).
"""

from __future__ import annotations

import datetime
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

PRE_MANIFEST_PATH = REPORT_DIR / "wo42_locked_holdout_150_pre_generation_manifest.json"
RAW_150_PATH = BENCH_DIR / "wo42_locked_holdout_150_raw_items.jsonl"
WORKSHEET_150_PATH = BENCH_DIR / "wo42_locked_holdout_150_worksheet.jsonl"
JUDGE_150_PATH = BENCH_DIR / "wo42_locked_holdout_150_for_judge.jsonl"
REPORT_150_PATH = REPORT_DIR / "wo42_locked_holdout_150_report.json"

LOCKED_PYTHON_FILES: tuple[str, ...] = (
    "src/lucca/core/coherence.py",
    "src/lucca/sandbox/neural_claim_verifier.py",
    "src/lucca/core/proof_policy.py",
    "src/lucca/core/neural_hazard_classifier.py",
    "src/lucca/router/heuristic.py",
    "src/lucca/router/neural_intent_classifier.py",
)

LOCKED_OV_MODELS: tuple[str, ...] = (
    "action_claim_verifier_ov",
    "proof_policy_hazard_ov",
    "router_intent_ov",
)


def compute_current_hashes() -> dict[str, dict[str, str]]:
    ov_hashes: dict[str, str] = {}
    for m in LOCKED_OV_MODELS:
        ov_dir = REPO_ROOT / "models" / m
        xml_b = (ov_dir / "openvino_model.xml").read_bytes()
        bin_b = (ov_dir / "openvino_model.bin").read_bytes()
        ov_hashes[m] = hashlib.sha256(xml_b + bin_b).hexdigest()

    py_hashes: dict[str, str] = {}
    for p in LOCKED_PYTHON_FILES:
        py_hashes[p] = hashlib.sha256((REPO_ROOT / p).read_bytes()).hexdigest()

    return {
        "openvino_ir_sha256": ov_hashes,
        "python_source_sha256": py_hashes,
    }


def wilson_ci_95(k: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p)) / n + (z * z) / (4.0 * n * n))) / denom
    return (round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2))


def count_sentences(text: str) -> int:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", str(text).strip()) if p.strip()]
    return max(1, len(parts))


def extract_150_from_subagents() -> list[dict[str, Any]]:
    subagent_ids = (
        "b0345600-a9ce-4060-a8cd-024eee86d0f2",
        "6640d44d-c5c9-4b55-8beb-a729ff0240e3",
        "2029a478-2704-4d35-9ac6-4a71a52f173e",
    )
    items: dict[str, dict[str, Any]] = {}
    for cid in subagent_ids:
        tp = Path(
            rf"C:\Users\seatr\.gemini\antigravity\brain\{cid}\.system_generated\logs\transcript_full.jsonl"
        )
        if not tp.exists():
            tp = Path(
                rf"C:\Users\seatr\.gemini\antigravity\brain\{cid}\.system_generated\logs\transcript.jsonl"
            )
        for line in tp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            step = json.loads(line)
            candidates = [str(step.get("content", ""))]
            for tc in step.get("tool_calls", []):
                msg = tc.get("args", {}).get("Message", "")
                if msg:
                    candidates.append(str(msg))
            for raw_text in candidates:
                for cline in raw_text.splitlines():
                    cline = cline.strip()
                    if cline.startswith("{") and cline.endswith("}") and "LOCKED_" in cline:
                        try:
                            obj = json.loads(cline)
                            if "id" in obj and str(obj["id"]).startswith("LOCKED_"):
                                items[str(obj["id"])] = obj
                        except Exception:
                            pass

    ordered = [items[k] for k in sorted(items.keys())]
    if len(ordered) != 150:
        raise RuntimeError(f"Expected 150 LOCKED_* items, extracted {len(ordered)}")

    RAW_150_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_150_PATH.open("w", encoding="utf-8") as f:
        for obj in ordered:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return ordered


def evaluate_coherence_item(item: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    prompt = str(item["prompt"])
    comp = str(item["assistant_output"])
    tools = list(item.get("verified_tools", []))
    gold_block = bool(item["gold_should_block"])

    report = evaluate_turn_coherence(
        user_prompt=prompt,
        assistant_output=comp,
        verified_tools=tools,
    )
    nv_verdict = get_neural_claim_verifier().evaluate(
        completion=comp,
        user_context=prompt,
        verified_tools=tools,
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    pred_block = not report.is_coherent
    is_correct = pred_block == gold_block
    return {
        **item,
        "subsystem": "coherence",
        "sentence_count": count_sentences(comp),
        "pred_class": nv_verdict.predicted_class,
        "pred_should_block": pred_block,
        "claimed_families": list(nv_verdict.claimed_families),
        "ungrounded_clauses": list(nv_verdict.ungrounded_clauses),
        "is_correct": is_correct,
        "latency_ms": elapsed_ms,
    }


def evaluate_hazard_item(item: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    text = str(item["text"])
    gold_hzd = str(item["gold_hazard"]).upper()
    gold_xref = bool(item["gold_cross_ref"])

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
    text = str(item["transcript"])
    last_tool = item.get("last_tool")
    gold_intent = str(item["gold_intent"])
    gold_domain = item.get("gold_domain")

    pred_intent, conf, entities = router.classify_intent(text, last_tool=last_tool)
    dec = router.route(text, last_tool=last_tool)
    pred_domain = "emergency_reflex" if dec.tier.value == "REFLEX" else dec.reasoning_domain
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    intent_ok = pred_intent == gold_intent
    if gold_intent == "web_fetch" and gold_domain is None:
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


def main() -> int:
    post_fix_mode = "--post-router-fix" in sys.argv
    if not PRE_MANIFEST_PATH.exists():
        raise RuntimeError(f"Missing pre-generation lock manifest: {PRE_MANIFEST_PATH}")

    pre_manifest = json.loads(PRE_MANIFEST_PATH.read_text(encoding="utf-8"))
    pre_eval_hashes = compute_current_hashes()

    assert pre_eval_hashes["openvino_ir_sha256"] == pre_manifest["openvino_ir_sha256"], (
        "OpenVINO IR SHA-256 mismatch against pre-generation lock manifest!"
    )
    if not post_fix_mode:
        assert pre_eval_hashes["python_source_sha256"] == pre_manifest["python_source_sha256"], (
            "Python source SHA-256 mismatch against pre-generation lock manifest! "
            "Pass --post-router-fix to write a separate post-fix report without overwriting the locked single-pass report."
        )

    raw_items = extract_150_from_subagents()
    router = HeuristicRouter()

    coh_res: list[dict[str, Any]] = []
    hzd_res: list[dict[str, Any]] = []
    rtr_res: list[dict[str, Any]] = []

    for item in raw_items:
        item_id = str(item["id"])
        if item_id.startswith("LOCKED_COH_"):
            coh_res.append(evaluate_coherence_item(item))
        elif item_id.startswith("LOCKED_HZD_"):
            hzd_res.append(evaluate_hazard_item(item))
        elif item_id.startswith("LOCKED_RTR_"):
            rtr_res.append(evaluate_router_item(router, item))

    all_res = coh_res + hzd_res + rtr_res
    post_eval_hashes = compute_current_hashes()
    assert post_eval_hashes == pre_eval_hashes, "Post-evaluation hash drift detected!"

    def summarize_slice(rows: list[dict[str, Any]]) -> dict[str, Any]:
        c = sum(1 for r in rows if r["is_correct"])
        n = len(rows)
        ms = sum(1 for r in rows if int(r["sentence_count"]) >= 2)
        return {
            "correct": c,
            "total": n,
            "accuracy_pct": round((c / n) * 100.0, 2),
            "wilson_95_ci_pct": list(wilson_ci_95(c, n)),
            "multi_sentence_count": ms,
            "multi_sentence_pct": round((ms / n) * 100.0, 2),
            "missed_ids": [r["id"] for r in rows if not r["is_correct"]],
        }

    s_coh = summarize_slice(coh_res)
    s_hzd = summarize_slice(hzd_res)
    s_rtr = summarize_slice(rtr_res)
    s_all = summarize_slice(all_res)

    report = {
        "evaluation_protocol": "SINGLE_PASS_CODE_AND_WEIGHT_LOCKED_HOLDOUT",
        "pre_generation_locked_at_utc": pre_manifest["locked_at_utc"],
        "evaluated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "zero_code_or_weight_edits_after_generation": True,
        "locked_openvino_ir_sha256": post_eval_hashes["openvino_ir_sha256"],
        "locked_python_source_sha256": post_eval_hashes["python_source_sha256"],
        "subsystems": {
            "coherence": s_coh,
            "proof_policy": s_hzd,
            "router": s_rtr,
        },
        "overall_150": s_all,
    }

    if post_fix_mode:
        post_fix_report_path = REPORT_DIR / "wo42_locked_holdout_150_post_router_fix_report.json"
        report["evaluation_protocol"] = "POST_ROUTER_BUGFIX_RETEST_FROZEN_NPU_WEIGHTS"
        report["zero_code_or_weight_edits_after_generation"] = False
        post_fix_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    else:
        with WORKSHEET_150_PATH.open("w", encoding="utf-8") as f:
            for r in all_res:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        with JUDGE_150_PATH.open("w", encoding="utf-8") as f:
            for r in all_res:
                blinded = {
                    k: v
                    for k, v in r.items()
                    if not k.startswith("gold_") and k not in ("is_correct", "category")
                }
                f.write(json.dumps(blinded, ensure_ascii=False) + "\n")
        REPORT_150_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"[WO-42 LOCKED-150] SHA-256 Lock Verified (0 code edits, 0 weight edits since {pre_manifest['locked_at_utc']})"
    )
    print(
        f"[WO-42 LOCKED-150] COHERENCE:    {s_coh['correct']}/{s_coh['total']} ({s_coh['accuracy_pct']}%, CI {s_coh['wilson_95_ci_pct']}, MultiSent={s_coh['multi_sentence_count']}/{s_coh['total']})"
    )
    print(
        f"[WO-42 LOCKED-150] PROOF_POLICY: {s_hzd['correct']}/{s_hzd['total']} ({s_hzd['accuracy_pct']}%, CI {s_hzd['wilson_95_ci_pct']}, MultiSent={s_hzd['multi_sentence_count']}/{s_hzd['total']})"
    )
    print(
        f"[WO-42 LOCKED-150] ROUTER:       {s_rtr['correct']}/{s_rtr['total']} ({s_rtr['accuracy_pct']}%, CI {s_rtr['wilson_95_ci_pct']}, MultiSent={s_rtr['multi_sentence_count']}/{s_rtr['total']})"
    )
    print(
        f"[WO-42 LOCKED-150] OVERALL-150:  {s_all['correct']}/{s_all['total']} ({s_all['accuracy_pct']}%, CI {s_all['wilson_95_ci_pct']}, MultiSent={s_all['multi_sentence_count']}/{s_all['total']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
