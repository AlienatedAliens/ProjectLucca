#!/usr/bin/env python3
"""
Project Lucca — Out-of-Distribution Generality Audit: Extended-Thinking Baseline (Option 2)
========================================================================================
Compares 3 arms across the 60 OOD problems on identical weights:
1. Arm A Direct   : enable_thinking=False, T=0.0, max_tokens=128 (Direct baseline)
2. Arm A Thinking : enable_thinking=True,  T=0.6, top_p=0.95, max_tokens=3072 (Extended-thinking reasoning baseline)
3. Arm B PAL      : enable_thinking=False, T=0.1, max_tokens=384, Python execution in Docker container

Addresses Claude Review v4 Section 2.5:
- Unbiased evaluation of LLM mental computation free of artificial token cap truncations.
- Logs finish_reason ('stop' vs 'length') and reasoning length for every problem.
- Computes true scaffold lift over both Direct and Extended-Thinking baselines.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any, Final

import httpx
from scipy.stats import binomtest

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.sandbox.preflight import extract_python_code  # type: ignore[import-untyped]
from lucca.sandbox.rpc import DockerRPCTransport  # type: ignore[import-untyped]

SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0

_DOCKER_RPC: DockerRPCTransport | None = None


def get_docker_rpc() -> DockerRPCTransport:
    global _DOCKER_RPC
    if _DOCKER_RPC is None:
        _DOCKER_RPC = DockerRPCTransport(
            container_name="lucca-file-sandbox", use_direct_fallback=False
        )
        if not _DOCKER_RPC.is_container_running():
            _DOCKER_RPC.ensure_container_running()
        try:
            _DOCKER_RPC.execute(
                call_id="warmup-init",
                tool="run_python",
                args={"code": "pass"},
                timeout_s=15.0,
            )
        except Exception:
            pass
    return _DOCKER_RPC


def query_llm(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.1,
    top_p: float = 1.0,
    max_tokens: int = 512,
    enable_thinking: bool = False,
) -> tuple[str, str, str]:
    """
    Queries resident llama-server instance synchronously.
    Returns: (content, reasoning_content, finish_reason).
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        content = str(choice["message"].get("content") or "").strip()
        reasoning = str(choice["message"].get("reasoning_content") or "").strip()
        finish_reason = str(choice.get("finish_reason") or "stop")
        return content, reasoning, finish_reason


def execute_sandboxed_python(code: str, timeout: float = 10.0) -> tuple[bool, str, str]:
    """Executes synthesized Python script inside hardened Docker container."""
    try:
        rpc = get_docker_rpc()
        call_id = f"audit-{time.time_ns()}"
        res = rpc.execute(
            call_id=call_id,
            tool="run_python",
            args={"code": code},
            timeout_s=timeout,
        )
        if res.ok:
            return True, str(res.content or "").strip(), ""
        err = str(res.stderr or res.content or "execution_failed").strip()
        return False, "", err
    except Exception as e:
        return False, "", f"{type(e).__name__}: {e}"


def wilson_ci(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Computes Wilson score interval for binomial proportions."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.95996
    p = k / n
    denom = 1.0 + z**2 / n
    center = (p + z**2 / (2.0 * n)) / denom
    margin = (z * math.sqrt((p * (1.0 - p) / n) + (z**2 / (4.0 * n**2)))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass
class ProblemEvaluation:
    domain: str
    problem_id: str
    prompt_text: str
    expected_answer: str

    # Arm A Direct (Thinking OFF, max_tokens=128)
    direct_predicted: str | None
    direct_success: bool
    direct_finish_reason: str

    # Arm A Extended Thinking (Thinking ON, max_tokens=3072)
    thinking_predicted: str | None
    thinking_success: bool
    thinking_finish_reason: str
    thinking_reasoning_len: int

    # Arm B PAL (Python in Container)
    pal_method: str
    pal_code: str | None
    pal_predicted: str | None
    pal_success: bool
    pal_finish_reason: str
    pal_failure_stage: str | None

    elapsed_ms: float


def evaluate_navigate(ex: dict[str, Any], idx: int) -> ProblemEvaluation:
    t0 = time.perf_counter()
    inp = str(ex["input"]).strip()
    target = str(ex["target"]).strip()  # "Yes" or "No"

    # 1. Arm A Direct (Thinking OFF, T=0.0, max_tokens=64)
    direct_prompt = (
        "Answer the following spatial navigation question.\n"
        "Output ONLY 'Yes' or 'No'.\n\n"
        f"{inp}"
    )
    d_content, _, d_finish = query_llm(direct_prompt, temperature=0.0, max_tokens=64, enable_thinking=False)
    d_match = re.search(r"\b(Yes|No)\b", d_content, re.IGNORECASE)
    d_pred = d_match.group(1).capitalize() if d_match else None
    d_success = (d_pred == target)

    # 2. Arm A Extended Thinking (Thinking ON, T=0.6, top_p=0.95, max_tokens=3072)
    th_prompt = (
        "Answer the following spatial navigation question.\n"
        "Output ONLY 'Yes' or 'No' as your final answer.\n\n"
        f"{inp}"
    )
    th_content, th_reasoning, th_finish = query_llm(
        th_prompt, temperature=0.6, top_p=0.95, max_tokens=3072, enable_thinking=True
    )
    # Parse prediction: check content first, then reasoning tail if truncated
    th_pred: str | None = None
    if th_content:
        th_match = list(re.finditer(r"\b(Yes|No)\b", th_content, re.IGNORECASE))
        if th_match:
            th_pred = th_match[-1].group(1).capitalize()
    if th_pred is None and th_reasoning:
        th_match_r = list(re.finditer(r"\b(Yes|No)\b", th_reasoning[-500:], re.IGNORECASE))
        if th_match_r:
            th_pred = th_match_r[-1].group(1).capitalize()
    th_success = (th_pred == target)

    # 3. Arm B PAL (Python in Container, T=0.1, max_tokens=384)
    pal_prompt = (
        "You are a spatial reasoning engine. Write a concise Python script "
        "to simulate the following navigation steps starting at (0, 0) facing forward (heading 0).\n"
        "Track (x, y) coordinates. If final position is (0, 0), print 'Yes', else print 'No'.\n"
        "Write executable Python with NO comments. Output in a ```python ... ``` block.\n\n"
        f"{inp}"
    )
    pal_content, _, pal_finish = query_llm(pal_prompt, temperature=0.1, max_tokens=384, enable_thinking=False)
    code = extract_python_code(pal_content)
    ok_exec = False
    stdout_val = ""
    exec_err = ""
    pal_pred: str | None = None
    pal_method = "INTERNAL_FALLBACK"
    if code:
        ok_exec, stdout_val, exec_err = execute_sandboxed_python(code)
        if ok_exec and stdout_val in ("Yes", "No"):
            pal_pred = stdout_val
            pal_method = "VERIFIED_PROGRAM"

    if pal_pred is None:
        pal_pred = d_pred

    pal_success = (pal_pred == target)
    pal_failure_stage: str | None = None
    if not pal_success:
        if pal_finish == "length":
            pal_failure_stage = "TRUNCATION_TOKEN_BUDGET"
        elif not code:
            pal_failure_stage = "TRANSLATION_NO_CODE"
        elif not ok_exec:
            if "TimeoutError" in exec_err or "timed out" in exec_err.lower():
                pal_failure_stage = "SANDBOX_TIMEOUT_OR_RESOURCE_LIMIT"
            else:
                pal_failure_stage = "EXECUTION_RUNTIME_ERROR"
        else:
            pal_failure_stage = "LLM_REASONING_LOGIC"

    elapsed = (time.perf_counter() - t0) * 1000.0

    return ProblemEvaluation(
        domain="SpatialNavigation",
        problem_id=f"Navigate_{idx}",
        prompt_text=inp,
        expected_answer=target,
        direct_predicted=d_pred,
        direct_success=d_success,
        direct_finish_reason=d_finish,
        thinking_predicted=th_pred,
        thinking_success=th_success,
        thinking_finish_reason=th_finish,
        thinking_reasoning_len=len(th_reasoning),
        pal_method=pal_method,
        pal_code=code if pal_method == "VERIFIED_PROGRAM" else None,
        pal_predicted=pal_pred,
        pal_success=pal_success,
        pal_finish_reason=pal_finish,
        pal_failure_stage=pal_failure_stage,
        elapsed_ms=elapsed,
    )


def evaluate_logical_deduction(ex: dict[str, Any], idx: int) -> ProblemEvaluation:
    t0 = time.perf_counter()
    inp = str(ex["input"]).strip()
    target_clean = str(ex["target"]).strip()
    target_letter = re.sub(r"[^A-Za-z]", "", target_clean).upper()

    # 1. Arm A Direct
    direct_prompt = (
        "Solve this logic deduction problem. State your final answer as (A), (B), or (C).\n\n"
        f"{inp}"
    )
    d_content, _, d_finish = query_llm(direct_prompt, temperature=0.0, max_tokens=128, enable_thinking=False)
    opt_match = re.search(r"\(([A-C])\)", d_content)
    if not opt_match:
        opt_match = re.search(r"\b([A-C])\b", d_content)
    d_pred = f"({opt_match.group(1).upper()})" if opt_match else None
    d_success = (d_pred == f"({target_letter})")

    # 2. Arm A Extended Thinking
    th_prompt = (
        "Solve this logic deduction problem. State your final answer as (A), (B), or (C).\n\n"
        f"{inp}"
    )
    th_content, th_reasoning, th_finish = query_llm(
        th_prompt, temperature=0.6, top_p=0.95, max_tokens=3072, enable_thinking=True
    )
    th_pred: str | None = None
    if th_content:
        matches = list(re.finditer(r"\(([A-C])\)", th_content))
        if not matches:
            matches = list(re.finditer(r"\b([A-C])\b", th_content))
        if matches:
            th_pred = f"({matches[-1].group(1).upper()})"
    if th_pred is None and th_reasoning:
        matches_r = list(re.finditer(r"\(([A-C])\)", th_reasoning[-500:]))
        if not matches_r:
            matches_r = list(re.finditer(r"\b([A-C])\b", th_reasoning[-500:]))
        if matches_r:
            th_pred = f"({matches_r[-1].group(1).upper()})"
    th_success = (th_pred == f"({target_letter})")

    # 3. Arm B PAL
    pal_prompt = (
        "You are a symbolic constraint satisfaction engine. Write a concise Python script "
        "that tests all permutations of the objects to find the one satisfying the clues, "
        "evaluates which option is true, and prints the option letter e.g. print('(A)').\n"
        "Write executable Python with NO comments. Output in a ```python ... ``` block.\n\n"
        f"{inp}"
    )
    pal_content, _, pal_finish = query_llm(pal_prompt, temperature=0.1, max_tokens=384, enable_thinking=False)
    code = extract_python_code(pal_content)
    pal_pred = None
    ok_exec = False
    stdout_val = ""
    exec_err = ""
    match_out = None
    pal_method = "INTERNAL_FALLBACK"
    if code:
        ok_exec, stdout_val, exec_err = execute_sandboxed_python(code)
        match_out = re.search(r"\(([A-C])\)", stdout_val)
        if not match_out:
            match_out = re.search(r"\b([A-C])\b", stdout_val)
        if ok_exec and match_out:
            pal_pred = f"({match_out.group(1).upper()})"
            pal_method = "VERIFIED_PROGRAM"

    if pal_pred is None:
        pal_pred = d_pred

    pal_success = (pal_pred == f"({target_letter})")
    pal_failure_stage: str | None = None
    if not pal_success:
        if pal_finish == "length":
            pal_failure_stage = "TRUNCATION_TOKEN_BUDGET"
        elif not code:
            pal_failure_stage = "TRANSLATION_NO_CODE"
        elif not ok_exec:
            if "TimeoutError" in exec_err or "timed out" in exec_err.lower():
                pal_failure_stage = "SANDBOX_TIMEOUT_OR_RESOURCE_LIMIT"
            else:
                pal_failure_stage = "EXECUTION_RUNTIME_ERROR"
        elif not match_out:
            pal_failure_stage = "GRADER_FORMAT_MISMATCH"
        else:
            pal_failure_stage = "LLM_REASONING_LOGIC"

    elapsed = (time.perf_counter() - t0) * 1000.0

    return ProblemEvaluation(
        domain="LogicalDeduction",
        problem_id=f"Deduction_{idx}",
        prompt_text=inp,
        expected_answer=f"({target_letter})",
        direct_predicted=d_pred,
        direct_success=d_success,
        direct_finish_reason=d_finish,
        thinking_predicted=th_pred,
        thinking_success=th_success,
        thinking_finish_reason=th_finish,
        thinking_reasoning_len=len(th_reasoning),
        pal_method=pal_method,
        pal_code=code if pal_method == "VERIFIED_PROGRAM" else None,
        pal_predicted=pal_pred,
        pal_success=pal_success,
        pal_finish_reason=pal_finish,
        pal_failure_stage=pal_failure_stage,
        elapsed_ms=elapsed,
    )


def evaluate_cruxeval(ex: dict[str, Any], idx: int) -> ProblemEvaluation:
    t0 = time.perf_counter()
    code_body = str(ex["code"]).strip()
    input_val = str(ex["input"]).strip()
    target_out = str(ex["output"]).strip()

    # 1. Arm A Direct
    direct_prompt = (
        "You are a Python code interpreter. Determine the EXACT return value of `f` for the given input.\n"
        f"Code:\n```python\n{code_body}\n```\n\n"
        f"Input:\n{input_val}\n\n"
        "Output ONLY the return value in ```...``` format."
    )
    d_content, _, d_finish = query_llm(direct_prompt, temperature=0.0, max_tokens=128, enable_thinking=False)
    match_code = re.findall(r"```(?:python)?\s*(.*?)\s*```", d_content, re.DOTALL)
    d_pred = match_code[-1].strip() if match_code else d_content.strip()
    d_success = (d_pred == target_out)

    # 2. Arm A Extended Thinking
    th_prompt = (
        "You are a Python code interpreter. Determine the EXACT return value of `f` for the given input.\n"
        f"Code:\n```python\n{code_body}\n```\n\n"
        f"Input:\n{input_val}\n\n"
        "Output the return value in ```...``` format."
    )
    th_content, th_reasoning, th_finish = query_llm(
        th_prompt, temperature=0.6, top_p=0.95, max_tokens=3072, enable_thinking=True
    )
    th_pred: str | None = None
    if th_content:
        match_code_th = re.findall(r"```(?:python)?\s*(.*?)\s*```", th_content, re.DOTALL)
        th_pred = match_code_th[-1].strip() if match_code_th else th_content.strip()
    if not th_pred and th_reasoning:
        match_code_r = re.findall(r"```(?:python)?\s*(.*?)\s*```", th_reasoning, re.DOTALL)
        if match_code_r:
            th_pred = match_code_r[-1].strip()
    th_success = (th_pred == target_out)

    # 3. Arm B PAL (Container Execution)
    harness_code = (
        f"{code_body}\n\n"
        f"res = f({input_val})\n"
        f"print(repr(res))\n"
    )
    ok_exec, stdout_val, exec_err = execute_sandboxed_python(harness_code)
    pal_pred: str | None = None
    pal_method = "INTERNAL_FALLBACK"
    if ok_exec and stdout_val:
        pal_pred = stdout_val
        pal_method = "VERIFIED_PROGRAM"
    else:
        pal_pred = d_pred

    pal_success = (pal_pred == target_out)
    pal_failure_stage: str | None = None
    if not pal_success:
        if not ok_exec:
            if "TimeoutError" in exec_err or "timed out" in exec_err.lower():
                pal_failure_stage = "SANDBOX_TIMEOUT_OR_RESOURCE_LIMIT"
            else:
                pal_failure_stage = "EXECUTION_RUNTIME_ERROR"
        else:
            pal_failure_stage = "GRADER_FORMAT_MISMATCH"

    elapsed = (time.perf_counter() - t0) * 1000.0

    return ProblemEvaluation(
        domain="CodeExecution",
        problem_id=f"CruxEval_{idx}",
        prompt_text=f"{code_body}\nInput: {input_val}",
        expected_answer=target_out,
        direct_predicted=d_pred,
        direct_success=d_success,
        direct_finish_reason=d_finish,
        thinking_predicted=th_pred,
        thinking_success=th_success,
        thinking_finish_reason=th_finish,
        thinking_reasoning_len=len(th_reasoning),
        pal_method=pal_method,
        pal_code=harness_code if pal_method == "VERIFIED_PROGRAM" else None,
        pal_predicted=pal_pred,
        pal_success=pal_success,
        pal_finish_reason="stop",
        pal_failure_stage=pal_failure_stage,
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
    parser = argparse.ArgumentParser(description="OOD Extended-Thinking Baseline Audit (Option 2)")
    parser.add_argument("--samples", type=int, default=20, help="Number of samples per domain (default: 20)")
    args = parser.parse_args()

    n_samples: int = args.samples
    print("=================================================================", flush=True)
    print("=== PROJECT LUCCA: EXTENDED-THINKING BASELINE AUDIT (OPTION 2) ===", flush=True)
    print("=================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Target Server: {SERVER_URL}", flush=True)
    print(f"Sample Size: {n_samples} per domain (Total {n_samples * 3} problems)", flush=True)
    print("Comparing 3 Arms on Identical Weights (Gemma 4 12B Heretic Q6_K):", flush=True)
    print("  1. Arm A Direct   : T=0.0, max_tokens=128 (Direct, thinking off)", flush=True)
    print("  2. Arm A Thinking : T=0.6, top_p=0.95, max_tokens=3072 (Extended-thinking reasoning)", flush=True)
    print("  3. Arm B PAL      : T=0.1, max_tokens=384, Docker sandbox (Program synthesis)\n", flush=True)

    results: list[ProblemEvaluation] = []

    # Domain 1: Spatial Navigation
    nav_file = REPO_ROOT / "data" / "benchmarks" / "bbh_navigate.json"
    nav_data = json.loads(nav_file.read_text(encoding="utf-8"))["examples"][:n_samples]
    print(f"--- [Domain 1/3] Spatial & Vector Navigation ({len(nav_data)} tasks) ---", flush=True)
    for idx, ex in enumerate(nav_data, 1):
        res = evaluate_navigate(ex, idx)
        results.append(res)
        d_tag = "P" if res.direct_success else "F"
        th_tag = "P" if res.thinking_success else "F"
        pal_tag = "P" if res.pal_success else "F"
        print(
            f"[{idx:02d}/{len(nav_data)}] Nav  | Direct: {d_tag} ({res.direct_finish_reason}) | "
            f"Think: {th_tag} ({res.thinking_finish_reason}, {res.thinking_reasoning_len}ch) | "
            f"PAL: {pal_tag} ({res.pal_method}) ({res.elapsed_ms:.0f}ms)",
            flush=True,
        )

    # Domain 2: Logical Deduction
    ded_file = REPO_ROOT / "data" / "benchmarks" / "bbh_logical_deduction_three_objects.json"
    ded_data = json.loads(ded_file.read_text(encoding="utf-8"))["examples"][:n_samples]
    print(f"\n--- [Domain 2/3] Symbolic Relational Deduction ({len(ded_data)} tasks) ---", flush=True)
    for idx, ex in enumerate(ded_data, 1):
        res = evaluate_logical_deduction(ex, idx)
        results.append(res)
        d_tag = "P" if res.direct_success else "F"
        th_tag = "P" if res.thinking_success else "F"
        pal_tag = "P" if res.pal_success else "F"
        print(
            f"[{idx:02d}/{len(ded_data)}] Ded  | Direct: {d_tag} ({res.direct_finish_reason}) | "
            f"Think: {th_tag} ({res.thinking_finish_reason}, {res.thinking_reasoning_len}ch) | "
            f"PAL: {pal_tag} ({res.pal_method}) ({res.elapsed_ms:.0f}ms)",
            flush=True,
        )

    # Domain 3: CruxEval
    crux_file = REPO_ROOT / "data" / "benchmarks" / "cruxeval" / "data" / "cruxeval.jsonl"
    crux_lines = crux_file.read_text(encoding="utf-8").strip().split("\n")[:n_samples]
    crux_data = [json.loads(line) for line in crux_lines]
    print(f"\n--- [Domain 3/3] Code Execution & Invariant Tracing ({len(crux_data)} tasks) ---", flush=True)
    for idx, ex in enumerate(crux_data, 1):
        res = evaluate_cruxeval(ex, idx)
        results.append(res)
        d_tag = "P" if res.direct_success else "F"
        th_tag = "P" if res.thinking_success else "F"
        pal_tag = "P" if res.pal_success else "F"
        print(
            f"[{idx:02d}/{len(crux_data)}] Crux | Direct: {d_tag} ({res.direct_finish_reason}) | "
            f"Think: {th_tag} ({res.thinking_finish_reason}, {res.thinking_reasoning_len}ch) | "
            f"PAL: {pal_tag} ({res.pal_method}) ({res.elapsed_ms:.0f}ms)",
            flush=True,
        )

    # Summary
    print("\n" + "=" * 70, flush=True)
    print("=== EXTENDED-THINKING BASELINE AUDIT SUMMARY (OPTION 2) ===", flush=True)
    print("=" * 70, flush=True)

    tot = len(results)
    d_tot_pass = sum(1 for r in results if r.direct_success)
    th_tot_pass = sum(1 for r in results if r.thinking_success)
    pal_tot_pass = sum(1 for r in results if r.pal_success)

    # Non-crux (Nav + Ded, n=40)
    nc_results = [r for r in results if r.domain in ("SpatialNavigation", "LogicalDeduction")]
    nc_tot = len(nc_results)
    nc_d_pass = sum(1 for r in nc_results if r.direct_success)
    nc_th_pass = sum(1 for r in nc_results if r.thinking_success)
    nc_pal_pass = sum(1 for r in nc_results if r.pal_success)

    print(f"Overall Accuracy Across All 3 Domains (n={tot}):", flush=True)
    print(f"  • Arm A Direct   : {d_tot_pass}/{tot} ({d_tot_pass / tot * 100:.1f}%) | Wilson: {wilson_ci(d_tot_pass, tot)}", flush=True)
    print(f"  • Arm A Thinking : {th_tot_pass}/{tot} ({th_tot_pass / tot * 100:.1f}%) | Wilson: {wilson_ci(th_tot_pass, tot)}", flush=True)
    print(f"  • Arm B PAL      : {pal_tot_pass}/{tot} ({pal_tot_pass / tot * 100:.1f}%) | Wilson: {wilson_ci(pal_tot_pass, tot)}", flush=True)
    print(flush=True)
    print(f"Non-CruxEval Subtotal (Spatial Navigation + Logic Deduction, n={nc_tot}):", flush=True)
    print(f"  • Arm A Direct   : {nc_d_pass}/{nc_tot} ({nc_d_pass / nc_tot * 100:.1f}%)", flush=True)
    print(f"  • Arm A Thinking : {nc_th_pass}/{nc_tot} ({nc_th_pass / nc_tot * 100:.1f}%)", flush=True)
    print(f"  • Arm B PAL      : {nc_pal_pass}/{nc_tot} ({nc_pal_pass / nc_tot * 100:.1f}%)", flush=True)
    print(f"  • True Lift of Thinking over Direct: +{(nc_th_pass - nc_d_pass) / nc_tot * 100:.1f} pp", flush=True)
    print(f"  • True Lift of PAL over Thinking   : +{(nc_pal_pass - nc_th_pass) / nc_tot * 100:.1f} pp", flush=True)
    print(flush=True)

    # Truncation analysis
    d_trunc = sum(1 for r in results if r.direct_finish_reason == "length")
    th_trunc = sum(1 for r in results if r.thinking_finish_reason == "length")
    pal_trunc = sum(1 for r in results if r.pal_finish_reason == "length")
    print("Truncation Ceiling Rates (finish_reason == 'length'):", flush=True)
    print(f"  • Arm A Direct   : {d_trunc}/{tot} ({d_trunc / tot * 100:.1f}%)", flush=True)
    print(f"  • Arm A Thinking : {th_trunc}/{tot} ({th_trunc / tot * 100:.1f}%)", flush=True)
    print(f"  • Arm B PAL      : {pal_trunc}/{tot} ({pal_trunc / tot * 100:.1f}%)", flush=True)
    print(flush=True)

    # McNemar tests
    # 1. Direct vs Thinking
    dt_b = sum(1 for r in results if r.direct_success and not r.thinking_success)
    dt_c = sum(1 for r in results if not r.direct_success and r.thinking_success)
    p_dt = compute_mcnemar(dt_b, dt_c)
    print("Pairwise Discordance & McNemar Tests:", flush=True)
    print(f"  • Direct vs Thinking : Direct won {dt_b}, Thinking won {dt_c} | McNemar p = {p_dt:.4e}", flush=True)

    # 2. Thinking vs PAL
    tp_b = sum(1 for r in results if r.thinking_success and not r.pal_success)
    tp_c = sum(1 for r in results if not r.thinking_success and r.pal_success)
    p_tp = compute_mcnemar(tp_b, tp_c)
    print(f"  • Thinking vs PAL    : Thinking won {tp_b}, PAL won {tp_c} | McNemar p = {p_tp:.4e}", flush=True)
    print(flush=True)

    # Save sealed report
    report_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_problems": tot,
        "summary": {
            "direct": {"passed": d_tot_pass, "pct": d_tot_pass / tot * 100.0, "truncation_rate": d_trunc / tot},
            "thinking": {"passed": th_tot_pass, "pct": th_tot_pass / tot * 100.0, "truncation_rate": th_trunc / tot},
            "pal": {"passed": pal_tot_pass, "pct": pal_tot_pass / tot * 100.0, "truncation_rate": pal_trunc / tot},
            "non_crux": {
                "direct_passed": nc_d_pass,
                "thinking_passed": nc_th_pass,
                "pal_passed": nc_pal_pass,
                "lift_thinking_over_direct_pp": (nc_th_pass - nc_d_pass) / nc_tot * 100.0,
                "lift_pal_over_thinking_pp": (nc_pal_pass - nc_th_pass) / nc_tot * 100.0,
            },
            "mcnemar": {
                "direct_vs_thinking": {"b": dt_b, "c": dt_c, "p_value": p_dt},
                "thinking_vs_pal": {"b": tp_b, "c": tp_c, "p_value": p_tp},
            },
        },
        "problems": [asdict(r) for r in results],
    }

    report_dir = REPO_ROOT / "logs" / "test_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    report_file = report_dir / f"ood_thinking_baseline_{ts}.json"
    report_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"[REPORT SEALED] Report saved to {report_file}", flush=True)


if __name__ == "__main__":
    main()
