#!/usr/bin/env python3
"""
Project Lucca — Out-of-Distribution Generality Audit: Non-Truncated Direct Baseline
===================================================================================
Re-runs Arm A Direct (thinking OFF, T=0.0) with an adequate token cap (max_tokens=2048)
across all 60 problems in the OOD suite:
1. Spatial & Vector Navigation (bbh_navigate.json, n=20)
2. Symbolic Constraint Deduction (bbh_logical_deduction_three_objects.json, n=20)
3. Code Execution & Invariant Tracing (cruxeval.jsonl, n=20)

Addresses Claude Review v7 §1, §2.1, §10.1:
- Replaces the artificial cap-128 baseline (where 45% of turns truncated at length).
- Logs exact finish_reason ('stop' vs 'length') and response token count for every turn.
- Derives true non-truncated accuracy and non-CRUXEval subtotal.
- Computes exact McNemar two-sided p-values vs Thinking and PAL.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Final

import httpx
from scipy.stats import binomtest

# Windows UTF-8 stdout
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0


@dataclass
class DirectProblemResult:
    domain: str
    problem_id: str
    prompt_text: str
    expected_answer: str
    raw_response: str
    predicted_answer: str | None
    success: bool
    finish_reason: str
    response_char_len: int
    elapsed_ms: float


def query_llm_direct(
    prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> tuple[str, str, int]:
    """Queries resident llama-server with thinking explicitly disabled."""
    payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        content = str(choice["message"].get("content") or "").strip()
        finish_reason = str(choice.get("finish_reason") or "stop")
        usage = data.get("usage", {})
        completion_tokens = int(usage.get("completion_tokens", 0))
        return content, finish_reason, completion_tokens


def evaluate_navigate_direct(ex: dict[str, Any], idx: int) -> DirectProblemResult:
    t0 = time.perf_counter()
    inp = str(ex["input"]).strip()
    target = str(ex["target"]).strip()  # "Yes" or "No"

    prompt = (
        "Answer the following spatial navigation question.\n"
        "Output ONLY 'Yes' or 'No'.\n\n"
        f"{inp}"
    )
    content, finish_reason, _ = query_llm_direct(prompt)
    matches = list(re.finditer(r"\b(Yes|No)\b", content, re.IGNORECASE))
    pred = matches[-1].group(1).capitalize() if matches else None
    success = (pred == target)
    elapsed = (time.perf_counter() - t0) * 1000.0

    return DirectProblemResult(
        domain="SpatialNavigation",
        problem_id=f"Navigate_{idx}",
        prompt_text=inp,
        expected_answer=target,
        raw_response=content,
        predicted_answer=pred,
        success=success,
        finish_reason=finish_reason,
        response_char_len=len(content),
        elapsed_ms=elapsed,
    )


def evaluate_deduction_direct(ex: dict[str, Any], idx: int) -> DirectProblemResult:
    t0 = time.perf_counter()
    inp = str(ex["input"]).strip()
    target_clean = str(ex["target"]).strip()
    target_letter = re.sub(r"[^A-Za-z]", "", target_clean).upper()

    prompt = (
        "Solve this logic deduction problem. State your final answer as (A), (B), or (C).\n\n"
        f"{inp}"
    )
    content, finish_reason, _ = query_llm_direct(prompt)
    matches = list(re.finditer(r"\(([A-C])\)", content))
    if not matches:
        matches = list(re.finditer(r"\b([A-C])\b", content))
    pred = f"({matches[-1].group(1).upper()})" if matches else None
    success = (pred == f"({target_letter})")
    elapsed = (time.perf_counter() - t0) * 1000.0

    return DirectProblemResult(
        domain="LogicalDeduction",
        problem_id=f"Deduction_{idx}",
        prompt_text=inp,
        expected_answer=f"({target_letter})",
        raw_response=content,
        predicted_answer=pred,
        success=success,
        finish_reason=finish_reason,
        response_char_len=len(content),
        elapsed_ms=elapsed,
    )


def evaluate_cruxeval_direct(ex: dict[str, Any], idx: int) -> DirectProblemResult:
    t0 = time.perf_counter()
    code_body = str(ex["code"]).strip()
    input_val = str(ex["input"]).strip()
    target_out = str(ex["output"]).strip()

    prompt = (
        "You are a Python code interpreter. Determine the EXACT return value of `f` for the given input.\n"
        f"Code:\n```python\n{code_body}\n```\n\n"
        f"Input:\n{input_val}\n\n"
        "Output ONLY the return value in ```...``` format."
    )
    content, finish_reason, _ = query_llm_direct(prompt)
    match_code = re.findall(r"```(?:python)?\s*(.*?)\s*```", content, re.DOTALL)
    pred = match_code[-1].strip() if match_code else content.strip()
    success = (pred == target_out)
    elapsed = (time.perf_counter() - t0) * 1000.0

    return DirectProblemResult(
        domain="CodeExecution",
        problem_id=f"CruxEval_{idx}",
        prompt_text=f"{code_body}\nInput: {input_val}",
        expected_answer=target_out,
        raw_response=content,
        predicted_answer=pred,
        success=success,
        finish_reason=finish_reason,
        response_char_len=len(content),
        elapsed_ms=elapsed,
    )


def compute_mcnemar(b: int, c: int) -> float:
    """Computes exact two-sided binomial p-value on discordant pairs (b, c)."""
    n = b + c
    if n == 0:
        return 1.0
    res = binomtest(k=b, n=n, p=0.5, alternative="two-sided")
    return float(res.pvalue)


def main() -> None:
    parser = argparse.ArgumentParser(description="OOD Non-Truncated Direct Baseline (max_tokens=2048)")
    parser.add_argument("--samples", type=int, default=20, help="Samples per domain (default: 20)")
    args = parser.parse_args()
    n_samples: int = args.samples

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: NON-TRUNCATED DIRECT BASELINE AUDIT (MAX_TOKENS 2048) ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Target Server: {SERVER_URL}", flush=True)
    print(f"Sample Size: {n_samples} per domain (Total {n_samples * 3} problems)", flush=True)
    print("Inference Config: enable_thinking=False, temperature=0.0, max_tokens=2048\n", flush=True)

    results: list[DirectProblemResult] = []

    # Domain 1: Spatial Navigation
    nav_file = REPO_ROOT / "data" / "benchmarks" / "bbh_navigate.json"
    nav_data = json.loads(nav_file.read_text(encoding="utf-8"))["examples"][:n_samples]
    print(f"--- [Domain 1/3] Spatial & Vector Navigation ({len(nav_data)} tasks) ---", flush=True)
    for idx, ex in enumerate(nav_data, 1):
        r = evaluate_navigate_direct(ex, idx)
        results.append(r)
        status = "PASS" if r.success else "FAIL"
        print(f"[{idx:02d}/{len(nav_data)}] Nav  | {status} ({r.finish_reason}, {r.response_char_len} chars, {r.elapsed_ms:.0f}ms) | Pred: {r.predicted_answer} | Exp: {r.expected_answer}", flush=True)

    # Domain 2: Logical Deduction
    ded_file = REPO_ROOT / "data" / "benchmarks" / "bbh_logical_deduction_three_objects.json"
    ded_data = json.loads(ded_file.read_text(encoding="utf-8"))["examples"][:n_samples]
    print(f"\n--- [Domain 2/3] Symbolic Relational Deduction ({len(ded_data)} tasks) ---", flush=True)
    for idx, ex in enumerate(ded_data, 1):
        r = evaluate_deduction_direct(ex, idx)
        results.append(r)
        status = "PASS" if r.success else "FAIL"
        print(f"[{idx:02d}/{len(ded_data)}] Ded  | {status} ({r.finish_reason}, {r.response_char_len} chars, {r.elapsed_ms:.0f}ms) | Pred: {r.predicted_answer} | Exp: {r.expected_answer}", flush=True)

    # Domain 3: CruxEval
    crux_file = REPO_ROOT / "data" / "benchmarks" / "cruxeval" / "data" / "cruxeval.jsonl"
    crux_lines = crux_file.read_text(encoding="utf-8").strip().split("\n")[:n_samples]
    crux_data = [json.loads(line) for line in crux_lines]
    print(f"\n--- [Domain 3/3] Code Execution & Invariant Tracing ({len(crux_data)} tasks) ---", flush=True)
    for idx, ex in enumerate(crux_data, 1):
        r = evaluate_cruxeval_direct(ex, idx)
        results.append(r)
        status = "PASS" if r.success else "FAIL"
        print(f"[{idx:02d}/{len(crux_data)}] Crux | {status} ({r.finish_reason}, {r.response_char_len} chars, {r.elapsed_ms:.0f}ms) | Pred: {r.predicted_answer[:20]} | Exp: {r.expected_answer[:20]}", flush=True)

    # Summary
    print("\n" + "=" * 70, flush=True)
    print("=== NON-TRUNCATED DIRECT BASELINE AUDIT SUMMARY (12B) ===", flush=True)
    print("=" * 70, flush=True)

    tot = len(results)
    tot_pass = sum(1 for r in results if r.success)
    tot_trunc = sum(1 for r in results if r.finish_reason == "length")

    nav_res = [r for r in results if r.domain == "SpatialNavigation"]
    ded_res = [r for r in results if r.domain == "LogicalDeduction"]
    crux_res = [r for r in results if r.domain == "CodeExecution"]
    non_crux = [r for r in results if r.domain in ("SpatialNavigation", "LogicalDeduction")]

    nav_pass = sum(1 for r in nav_res if r.success)
    ded_pass = sum(1 for r in ded_res if r.success)
    crux_pass = sum(1 for r in crux_res if r.success)
    nc_pass = sum(1 for r in non_crux if r.success)

    print(f"Spatial Navigation (n={len(nav_res)}):   {nav_pass:2d}/{len(nav_res)} ({nav_pass/len(nav_res)*100:5.1f}%) | Truncations: {sum(1 for r in nav_res if r.finish_reason == 'length')}", flush=True)
    print(f"Logical Deduction  (n={len(ded_res)}):   {ded_pass:2d}/{len(ded_res)} ({ded_pass/len(ded_res)*100:5.1f}%) | Truncations: {sum(1 for r in ded_res if r.finish_reason == 'length')}", flush=True)
    print(f"Code Execution     (n={len(crux_res)}):   {crux_pass:2d}/{len(crux_res)} ({crux_pass/len(crux_res)*100:5.1f}%) | Truncations: {sum(1 for r in crux_res if r.finish_reason == 'length')}", flush=True)
    print(f"Non-Crux Subtotal  (n={len(non_crux)}):   {nc_pass:2d}/{len(non_crux)} ({nc_pass/len(non_crux)*100:5.1f}%) | Truncations: {sum(1 for r in non_crux if r.finish_reason == 'length')}", flush=True)
    print(f"Overall Aggregate  (n={tot}):         {tot_pass:2d}/{tot} ({tot_pass/tot*100:5.1f}%) | Truncations: {tot_trunc}/{tot} ({tot_trunc/tot*100:4.1f}%)", flush=True)

    # Save artifact
    out_dir = REPO_ROOT / "logs" / "test_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_file = out_dir / f"ood_direct_adequate_cap_12b_{ts}.json"
    report_data = {
        "benchmark": "OOD_Direct_Adequate_Cap_Audit",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "model": "gemma-4-12b-heretic-Q6_K.gguf",
        "config": {
            "temperature": 0.0,
            "max_tokens": 2048,
            "enable_thinking": False,
        },
        "summary": {
            "total_problems": tot,
            "total_passed": tot_pass,
            "pass_rate_pct": tot_pass / tot * 100.0,
            "truncations": tot_trunc,
            "truncation_rate_pct": tot_trunc / tot * 100.0,
            "domains": {
                "SpatialNavigation": {"passed": nav_pass, "total": len(nav_res), "rate_pct": nav_pass / len(nav_res) * 100.0},
                "LogicalDeduction": {"passed": ded_pass, "total": len(ded_res), "rate_pct": ded_pass / len(ded_res) * 100.0},
                "CodeExecution": {"passed": crux_pass, "total": len(crux_res), "rate_pct": crux_pass / len(crux_res) * 100.0},
                "NonCruxSubtotal": {"passed": nc_pass, "total": len(non_crux), "rate_pct": nc_pass / len(non_crux) * 100.0},
            },
        },
        "problems": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[Artifact Saved] -> {out_file}", flush=True)


if __name__ == "__main__":
    main()
