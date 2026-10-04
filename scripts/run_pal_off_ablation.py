#!/usr/bin/env python3
"""Project Lucca — PAL-Off Factorial Model-Scale Ablation Runner
===============================================================
Protocol ID: PROTO-LUCCA-2026-10-04-PAL-OFF
Ablation Design: 3 Models x 4 Scaffold Arms (R0, R1, P1, P2) x 2 Benchmarks (GSM-Symbolic, MATH-500)

Scaffold Arms:
  R0: Raw Direct        (enable_thinking=False, max_tokens=1536, \\boxed{...} text regex extraction)
  R1: Raw Thinking      (enable_thinking=True, max_tokens=4096, \\boxed{...} text regex extraction, finish_reason=length tracking)
  P1: PAL Turn 1        (enable_thinking=False, max_tokens=1024, Python/SymPy code -> Docker sandbox -> stdout regex)
  P2: PAL + Turn 2      (enable_thinking=False, max_tokens=1024, Turn 2 traceback/empty stdout reprompting -> Docker sandbox)

Benchmarks:
  gsm_symbolic: Stratified 100 templates x k instances (e.g. 5 instances = 500 items, or 1 instance = 100 items)
  math500: Full 500 problems from data/benchmarks/math500_test.jsonl (or first N items)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from lucca.reasoning.stats import wilson_score_interval
from lucca.sandbox.rpc import DockerRPCTransport
from scripts.run_modern_2024_benchmarks import (
    compare_math_lenient,
    compare_math_strict,
    extract_gsm_ground_truth,
    extract_math500_ground_truth,
    extract_math_answer_from_text,
    extract_python_code,
    extract_python_code_with_stage,
)

DATA_DIR = REPO_ROOT / "data" / "benchmarks"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "logs" / "test_reports" / "pal_off_ablation"


# ---------------------------------------------------------------------------
# Hardware & Telemetry Helpers
# ---------------------------------------------------------------------------

def get_gpu_vram_mib() -> int:
    """Query current GPU VRAM used in MiB via nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        )
        return int(out.strip().splitlines()[0])
    except Exception:
        return 0


def get_git_commit_hash() -> str:
    """Query current git commit hash for protocol provenance."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        )
        return out.strip()
    except Exception:
        return "unknown"


def get_server_model_name(port: int = 8080) -> str:
    """Query llama-server endpoint to identify active model name."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            if models:
                return models[0].get("id", "unknown")
    except Exception:
        pass
    return "unknown"


def query_llm_pal_off(
    prompt: str,
    max_tokens: int,
    enable_thinking: bool,
    port: int = 8080,
    retries: int = 2,
) -> tuple[str, str, str, int, float]:
    """Query llama-server OpenAI endpoint.
    Returns: (content, reasoning_content, finish_reason, completion_tokens, latency_s)
    """
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": 42,
        "cache_prompt": False,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    t0 = time.perf_counter()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                elapsed = time.perf_counter() - t0
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]
                msg = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "stop")
                usage = data.get("usage", {})
                completion_tokens = usage.get("completion_tokens", 0)
                content = (msg.get("content") or "").strip()
                reasoning = (msg.get("reasoning_content") or "").strip()
                return content, reasoning, finish_reason, completion_tokens, elapsed
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                elapsed = time.perf_counter() - t0
                print(f"   [WARN] LLM query failed after {retries} attempts: {exc}")
                return "", "", "error", 0, elapsed
    return "", "", "error", 0, 0.0


# ---------------------------------------------------------------------------
# Dataset Loaders
# ---------------------------------------------------------------------------

def load_gsm_symbolic_stratified(samples: int = 500, split: str = "dev") -> list[dict[str, Any]]:
    """Load stratified GSM-Symbolic dataset.
    Guarantees exactly (samples // 100) instances per template across all 100 templates.
    split='dev': uses first k instances (offset 0).
    split='heldout': uses subsequent non-overlapping instances (offset k).
    """
    data_file = DATA_DIR / "GSM_symbolic.jsonl"
    if not data_file.exists():
        raise FileNotFoundError(f"GSM_symbolic.jsonl not found at {data_file}")

    lines = [json.loads(l) for l in data_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    template_groups = defaultdict(list)
    for item in lines:
        template_groups[item["original_id"]].append(item)

    assert len(template_groups) == 100, f"Expected 100 templates, found {len(template_groups)}"
    k = max(1, samples // 100)
    offset = k if split == "heldout" else 0

    stratified = []
    for orig_id in sorted(template_groups.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x)):
        items = template_groups[orig_id][offset : offset + k]
        for inst_idx, itm in enumerate(items, 1 + offset):
            stratified.append({
                "item_id": f"gsm-sym-t{orig_id}-i{inst_idx}",
                "template_id": orig_id,
                "instance_idx": inst_idx,
                "question": itm["question"],
                "answer_raw": itm["answer"],
                "ground_truth": extract_gsm_ground_truth(itm["answer"]),
            })

    return stratified[:samples]


def load_math500_dataset(samples: int = 500, split: str = "dev") -> list[dict[str, Any]]:
    """Load canonical MATH-500 test dataset (dev) or fresh heldout 500 (heldout)."""
    if split == "heldout":
        data_file = DATA_DIR / "math_fresh_heldout_500.jsonl"
    else:
        data_file = DATA_DIR / "math500_test.jsonl"

    if not data_file.exists():
        raise FileNotFoundError(f"Math dataset not found at {data_file}")

    lines = [json.loads(l) for l in data_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    selected = lines[:samples]

    dataset = []
    for idx, itm in enumerate(selected, 1):
        sol = itm.get("solution", "")
        gt = extract_math500_ground_truth(sol)
        dataset.append({
            "item_id": f"math500-{split}-{idx}",
            "idx": idx,
            "problem": itm.get("problem", ""),
            "solution_raw": sol,
            "ground_truth": gt,
            "subject": itm.get("subject", ""),
            "level": itm.get("level", 0),
            "unique_id": itm.get("unique_id", f"math500_{split}_{idx}"),
        })
    return dataset


# ---------------------------------------------------------------------------
# Output Parsing & Error Tagging
# ---------------------------------------------------------------------------

def parse_gsm_pred_value(text: str) -> float | None:
    """Extract numeric value from text or stdout."""
    if not text:
        return None
    # Check for \boxed{...} first
    boxed = extract_math_answer_from_text(text)
    candidate_text = boxed if boxed else text

    clean = candidate_text.strip().replace(",", "").replace("$", "")
    tokens = clean.split()
    if tokens:
        # Search backwards from the end
        for tok in reversed(tokens[-5:]):
            m = re.search(r"[-+]?\d*\.?\d+", tok)
            if m:
                try:
                    return float(m.group(0))
                except ValueError:
                    pass
    return None


def tag_failure_class(
    pred_str: str,
    gt_str: str,
    finish_reason: str,
    is_code: bool = False,
    exit_code: int = 0,
) -> str:
    """Classify failure root cause into protocol taxonomy:
    - length_truncation: Generation stopped due to max_tokens limit
    - format_miss: Model failed to format final answer / empty stdout
    - arithmetic_slip: Numerical divergence despite coherent answer
    - formulation_error: Wrong conceptual setup / symbolic divergence
    - docker_error: Script crashed with traceback in sandbox
    """
    if finish_reason == "length":
        return "length_truncation"
    if is_code and exit_code != 0:
        return "docker_error"
    if not pred_str or pred_str.strip().lower() in ("none", "null", ""):
        return "format_miss"

    # Numeric check for arithmetic slip
    m_p = re.search(r"[-+]?\d*\.?\d+", pred_str)
    m_g = re.search(r"[-+]?\d*\.?\d+", str(gt_str))
    if m_p and m_g:
        return "arithmetic_slip"

    return "formulation_error"


# ---------------------------------------------------------------------------
# Arm Executors
# ---------------------------------------------------------------------------

def execute_r0_item(
    item: dict[str, Any],
    benchmark: str,
    port: int,
) -> dict[str, Any]:
    """R0: Raw Direct (enable_thinking=False, max_tokens=1536)."""
    if benchmark == "gsm_symbolic":
        prompt = (
            "You are a precise mathematical assistant. Solve the following word problem step by step. "
            "State your final answer clearly at the end inside \\boxed{...}.\n\n"
            f"Problem: {item['question']}\n"
        )
        gt = item["ground_truth"]
    else:
        prompt = (
            "Solve the following mathematics problem step by step. "
            "State your final answer clearly at the end inside \\boxed{...}.\n\n"
            f"Problem: {item['problem']}\n"
        )
        gt = item["ground_truth"]

    content, reasoning, finish_reason, tokens, latency = query_llm_pal_off(
        prompt=prompt,
        max_tokens=1536,
        enable_thinking=False,
        port=port,
    )

    pred_str = extract_math_answer_from_text(content)
    if not pred_str:
        pred_str = extract_math_answer_from_text(reasoning)

    # Grading
    if benchmark == "gsm_symbolic":
        pred_val = parse_gsm_pred_value(pred_str) if pred_str else parse_gsm_pred_value(content)
        gt_val = float(gt) if gt is not None else None
        strict_pass = (gt_val is not None and pred_val is not None and abs(gt_val - pred_val) < 1e-4)
        lenient_pass = strict_pass
        predicted_record = str(pred_val) if pred_val is not None else pred_str
    else:
        strict_pass = compare_math_strict(pred_str, str(gt))
        lenient_pass = compare_math_lenient(pred_str, str(gt))
        predicted_record = pred_str

    fail_tag = "none" if (strict_pass or lenient_pass) else tag_failure_class(pred_str, str(gt), finish_reason)

    return {
        "item_id": item["item_id"],
        "arm": "r0",
        "benchmark": benchmark,
        "strict_pass": strict_pass,
        "lenient_pass": lenient_pass,
        "finish_reason": finish_reason,
        "completion_tokens": tokens,
        "thinking_tokens": 0,
        "latency_s": round(latency, 3),
        "predicted_ans": predicted_record,
        "ground_truth": str(gt),
        "failure_class": fail_tag,
        "truncated": (finish_reason == "length"),
    }


def execute_r1_item(
    item: dict[str, Any],
    benchmark: str,
    port: int,
    max_thinking_tokens: int = 4096,
) -> dict[str, Any]:
    """R1: Raw Thinking (enable_thinking=True, max_tokens=max_thinking_tokens)."""
    if benchmark == "gsm_symbolic":
        prompt = (
            "You are a precise mathematical assistant. Solve the following word problem step by step. "
            "State your final answer clearly at the end inside \\boxed{...}.\n\n"
            f"Problem: {item['question']}\n"
        )
        gt = item["ground_truth"]
    else:
        prompt = (
            "Solve the following mathematics problem step by step. "
            "State your final answer clearly at the end inside \\boxed{...}.\n\n"
            f"Problem: {item['problem']}\n"
        )
        gt = item["ground_truth"]

    content, reasoning, finish_reason, tokens, latency = query_llm_pal_off(
        prompt=prompt,
        max_tokens=max_thinking_tokens,
        enable_thinking=True,
        port=port,
    )

    # In thinking mode, final answer is usually in content, or in reasoning if cut off
    pred_str = extract_math_answer_from_text(content)
    if not pred_str and reasoning:
        pred_str = extract_math_answer_from_text(reasoning)

    # Grading
    if benchmark == "gsm_symbolic":
        pred_val = parse_gsm_pred_value(pred_str) if pred_str else parse_gsm_pred_value(content or reasoning)
        gt_val = float(gt) if gt is not None else None
        strict_pass = (gt_val is not None and pred_val is not None and abs(gt_val - pred_val) < 1e-4)
        lenient_pass = strict_pass
        predicted_record = str(pred_val) if pred_val is not None else pred_str
    else:
        strict_pass = compare_math_strict(pred_str, str(gt))
        lenient_pass = compare_math_lenient(pred_str, str(gt))
        predicted_record = pred_str

    fail_tag = "none" if (strict_pass or lenient_pass) else tag_failure_class(pred_str, str(gt), finish_reason)

    return {
        "item_id": item["item_id"],
        "arm": "r1",
        "benchmark": benchmark,
        "strict_pass": strict_pass,
        "lenient_pass": lenient_pass,
        "finish_reason": finish_reason,
        "completion_tokens": tokens,
        "has_reasoning": bool(reasoning),
        "latency_s": round(latency, 3),
        "predicted_ans": predicted_record,
        "ground_truth": str(gt),
        "failure_class": fail_tag,
        "truncated": (finish_reason == "length"),
    }


def execute_p1_item(
    item: dict[str, Any],
    benchmark: str,
    transport: DockerRPCTransport,
    port: int,
    max_code_tokens: int = 2048,
) -> dict[str, Any]:
    """P1: PAL Turn 1 Only (enable_thinking=False, max_tokens=max_code_tokens, Docker execution)."""
    if benchmark == "gsm_symbolic":
        prompt = (
            "You are a precise mathematical assistant. Solve the following word problem by writing "
            "a clean Python script that computes the answer and prints ONLY the final numeric value.\n"
            "Put all Python code inside a single ```python ... ``` block. Define all necessary variables.\n\n"
            f"Problem: {item['question']}\n"
        )
        gt = item["ground_truth"]
    else:
        prompt = (
            "Solve the following mathematics problem using Python and SymPy.\n"
            "Write a complete, standalone Python script inside ```python ... ``` that solves the problem "
            "and prints ONLY the final answer to standard output.\n\n"
            f"Problem: {item['problem']}\n"
        )
        gt = item["ground_truth"]

    content, reasoning, finish_reason, tokens, latency = query_llm_pal_off(
        prompt=prompt,
        max_tokens=max_code_tokens,
        enable_thinking=False,
        port=port,
    )

    code = extract_python_code(content)
    exec_res = transport.execute(f"pal-p1-{item['item_id']}", "run_python", {"code": code}, timeout_s=15)

    stdout_text = (exec_res.content or "").strip()
    lines = [l.strip() for l in stdout_text.splitlines() if l.strip()]
    pred_str = lines[-1] if lines else ""

    # Grading
    if benchmark == "gsm_symbolic":
        pred_val = parse_gsm_pred_value(stdout_text)
        gt_val = float(gt) if gt is not None else None
        strict_pass = (gt_val is not None and pred_val is not None and abs(gt_val - pred_val) < 1e-4)
        lenient_pass = strict_pass
        predicted_record = str(pred_val) if pred_val is not None else pred_str
    else:
        strict_pass = compare_math_strict(pred_str, str(gt))
        lenient_pass = compare_math_lenient(pred_str, str(gt))
        predicted_record = pred_str

    fail_tag = "none" if (strict_pass or lenient_pass) else tag_failure_class(
        pred_str, str(gt), finish_reason, is_code=True, exit_code=exec_res.exit_code
    )

    return {
        "item_id": item["item_id"],
        "arm": "p1",
        "benchmark": benchmark,
        "strict_pass": strict_pass,
        "lenient_pass": lenient_pass,
        "finish_reason": finish_reason,
        "completion_tokens": tokens,
        "latency_s": round(latency, 3),
        "predicted_ans": predicted_record,
        "ground_truth": str(gt),
        "exit_code": exec_res.exit_code,
        "failure_class": fail_tag,
        "truncated": (finish_reason == "length"),
    }


def execute_p2_item(
    item: dict[str, Any],
    benchmark: str,
    transport: DockerRPCTransport,
    port: int,
    max_code_tokens: int = 2048,
) -> dict[str, Any]:
    """P2: PAL + Turn 2 Feedback Loop (enable_thinking=False, max_tokens=max_code_tokens, Docker execution)."""
    # Run Turn 1 identical to P1
    p1_res = execute_p1_item(item, benchmark, transport, port, max_code_tokens=max_code_tokens)
    if p1_res["strict_pass"] or p1_res["lenient_pass"]:
        p1_res["arm"] = "p2"
        p1_res["feedback_triggered"] = False
        p1_res["feedback_succeeded"] = False
        return p1_res

    # If Turn 1 failed, trigger Turn 2 feedback loop
    if benchmark == "gsm_symbolic":
        problem_text = item["question"]
    else:
        problem_text = item["problem"]

    gt = item["ground_truth"]
    exit_code = p1_res.get("exit_code", 0)
    stdout_text = p1_res.get("predicted_ans", "")

    # Build Turn 2 prompt
    if exit_code != 0:
        err_msg = f"Execution returned exit code {exit_code} with error."
        feedback_prompt = (
            "You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem produced an execution error in the sandbox:\n\n"
            f"Problem: {problem_text}\n\n"
            f"Execution Error / Traceback in Docker:\n{err_msg}\n\n"
            "Please diagnose the error and output ONLY the corrected complete Python script in a ```python ... ``` block that prints ONLY the final answer."
        )
    else:
        feedback_prompt = (
            "You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem executed with exit code 0, but produced EMPTY stdout or an unprinted answer:\n\n"
            f"Problem: {problem_text}\n\n"
            "CRITICAL REQUIREMENT:\nThe script must compute the final exact answer and explicitly print it on stdout using print(answer).\n"
            "Output ONLY the corrected complete Python script in a ```python ... ``` block that prints ONLY the final answer."
        )

    c2, r2, finish2, tokens2, latency2 = query_llm_pal_off(
        prompt=feedback_prompt,
        max_tokens=max_code_tokens,
        enable_thinking=False,
        port=port,
    )

    code2, _ = extract_python_code_with_stage(c2)
    exec_res2 = transport.execute(f"pal-p2-{item['item_id']}", "run_python", {"code": code2}, timeout_s=15)
    stdout2 = (exec_res2.content or "").strip()
    lines2 = [l.strip() for l in stdout2.splitlines() if l.strip()]
    pred2_str = lines2[-1] if lines2 else ""

    # Grading Turn 2
    if benchmark == "gsm_symbolic":
        pred2_val = parse_gsm_pred_value(stdout2)
        gt_val = float(gt) if gt is not None else None
        strict_pass = (gt_val is not None and pred2_val is not None and abs(gt_val - pred2_val) < 1e-4)
        lenient_pass = strict_pass
        predicted_record = str(pred2_val) if pred2_val is not None else pred2_str
    else:
        strict_pass = compare_math_strict(pred2_str, str(gt))
        lenient_pass = compare_math_lenient(pred2_str, str(gt))
        predicted_record = pred2_str

    fail_tag = "none" if (strict_pass or lenient_pass) else tag_failure_class(
        pred2_str, str(gt), finish2, is_code=True, exit_code=exec_res2.exit_code
    )

    return {
        "item_id": item["item_id"],
        "arm": "p2",
        "benchmark": benchmark,
        "strict_pass": strict_pass,
        "lenient_pass": lenient_pass,
        "finish_reason": finish2,
        "completion_tokens": p1_res["completion_tokens"] + tokens2,
        "latency_s": round(p1_res["latency_s"] + latency2, 3),
        "predicted_ans": predicted_record,
        "ground_truth": str(gt),
        "exit_code": exec_res2.exit_code,
        "feedback_triggered": True,
        "feedback_succeeded": bool(strict_pass or lenient_pass),
        "failure_class": fail_tag,
        "truncated": (finish2 == "length"),
    }


def execute_p3_item(
    item: dict[str, Any],
    benchmark: str,
    transport: DockerRPCTransport,
    port: int,
    max_thinking_tokens: int = 6144,
) -> dict[str, Any]:
    """P3: PAL + Thinking ON (enable_thinking=True, Docker execution).
    Allows model to think through algebraic logic before synthesizing Python code.
    """
    if benchmark == "gsm_symbolic":
        prompt = (
            "You are a precise mathematical assistant. Solve the following word problem by writing "
            "a clean Python script that computes the answer and prints ONLY the final numeric value.\n"
            "Put all Python code inside a single ```python ... ``` block. Define all necessary variables.\n\n"
            f"Problem: {item['question']}\n"
        )
        gt = item["ground_truth"]
    else:
        prompt = (
            "Solve the following mathematics problem using Python and SymPy.\n"
            "Write a complete, standalone Python script inside ```python ... ``` that solves the problem "
            "and prints ONLY the final answer to standard output.\n\n"
            f"Problem: {item['problem']}\n"
        )
        gt = item["ground_truth"]

    content, reasoning, finish_reason, tokens, latency = query_llm_pal_off(
        prompt=prompt,
        max_tokens=max_thinking_tokens,
        enable_thinking=True,
        port=port,
    )

    code = extract_python_code(content)
    if not code and reasoning:
        code = extract_python_code(reasoning)

    exec_res = transport.execute(f"pal-p3-{item['item_id']}", "run_python", {"code": code}, timeout_s=15)
    stdout_text = (exec_res.content or "").strip()
    lines = [l.strip() for l in stdout_text.splitlines() if l.strip()]
    pred_str = lines[-1] if lines else ""

    # Grading Turn 1
    if benchmark == "gsm_symbolic":
        pred_val = parse_gsm_pred_value(stdout_text)
        gt_val = float(gt) if gt is not None else None
        strict_pass = (gt_val is not None and pred_val is not None and abs(gt_val - pred_val) < 1e-4)
        lenient_pass = strict_pass
        predicted_record = str(pred_val) if pred_val is not None else pred_str
    else:
        strict_pass = compare_math_strict(pred_str, str(gt))
        lenient_pass = compare_math_lenient(pred_str, str(gt))
        predicted_record = pred_str

    if strict_pass or lenient_pass:
        return {
            "item_id": item["item_id"],
            "arm": "p3",
            "benchmark": benchmark,
            "strict_pass": strict_pass,
            "lenient_pass": lenient_pass,
            "finish_reason": finish_reason,
            "completion_tokens": tokens,
            "latency_s": round(latency, 3),
            "predicted_ans": predicted_record,
            "ground_truth": str(gt),
            "exit_code": exec_res.exit_code,
            "feedback_triggered": False,
            "feedback_succeeded": False,
            "failure_class": "none",
            "truncated": (finish_reason == "length"),
        }

    # Turn 2 with thinking if Turn 1 failed
    problem_text = item["question"] if benchmark == "gsm_symbolic" else item["problem"]
    exit_code = exec_res.exit_code
    if exit_code != 0:
        err_msg = f"Execution returned exit code {exit_code} with error."
        feedback_prompt = (
            "You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem produced an execution error in the sandbox:\n\n"
            f"Problem: {problem_text}\n\n"
            f"Execution Error / Traceback in Docker:\n{err_msg}\n\n"
            "Please diagnose the error, reason through the fix, and output ONLY the corrected complete Python script in a ```python ... ``` block that prints ONLY the final answer."
        )
    else:
        feedback_prompt = (
            "You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem executed with exit code 0, but produced EMPTY stdout or an unprinted answer:\n\n"
            f"Problem: {problem_text}\n\n"
            "CRITICAL REQUIREMENT:\nThe script must compute the final exact answer and explicitly print it on stdout using print(answer).\n"
            "Please reason through the requirements and output ONLY the corrected complete Python script in a ```python ... ``` block that prints ONLY the final answer."
        )

    c2, r2, finish2, tokens2, latency2 = query_llm_pal_off(
        prompt=feedback_prompt,
        max_tokens=max_thinking_tokens,
        enable_thinking=True,
        port=port,
    )

    code2, _ = extract_python_code_with_stage(c2)
    if not code2 and r2:
        code2, _ = extract_python_code_with_stage(r2)

    exec_res2 = transport.execute(f"pal-p3-t2-{item['item_id']}", "run_python", {"code": code2}, timeout_s=15)
    stdout2 = (exec_res2.content or "").strip()
    lines2 = [l.strip() for l in stdout2.splitlines() if l.strip()]
    pred2_str = lines2[-1] if lines2 else ""

    # Grading Turn 2
    if benchmark == "gsm_symbolic":
        pred2_val = parse_gsm_pred_value(stdout2)
        gt_val = float(gt) if gt is not None else None
        strict_pass = (gt_val is not None and pred2_val is not None and abs(gt_val - pred2_val) < 1e-4)
        lenient_pass = strict_pass
        predicted_record = str(pred2_val) if pred2_val is not None else pred2_str
    else:
        strict_pass = compare_math_strict(pred2_str, str(gt))
        lenient_pass = compare_math_lenient(pred2_str, str(gt))
        predicted_record = pred2_str

    fail_tag = "none" if (strict_pass or lenient_pass) else tag_failure_class(
        pred2_str, str(gt), finish2, is_code=True, exit_code=exec_res2.exit_code
    )

    return {
        "item_id": item["item_id"],
        "arm": "p3",
        "benchmark": benchmark,
        "strict_pass": strict_pass,
        "lenient_pass": lenient_pass,
        "finish_reason": finish2,
        "completion_tokens": tokens + tokens2,
        "latency_s": round(latency + latency2, 3),
        "predicted_ans": predicted_record,
        "ground_truth": str(gt),
        "exit_code": exec_res2.exit_code,
        "feedback_triggered": True,
        "feedback_succeeded": bool(strict_pass or lenient_pass),
        "failure_class": fail_tag,
        "truncated": (finish2 == "length"),
    }


def execute_routed_item(
    item: dict[str, Any],
    benchmark: str,
    transport: DockerRPCTransport,
    port: int,
    model_label: str,
    max_thinking_tokens: int = 6144,
    max_code_tokens: int = 2048,
) -> dict[str, Any]:
    """Task-specific routing:
    - 12B: Raw direct (r0)
    - Arithmetic word problems (gsm_symbolic): PAL (p2 with max_code_tokens)
    - Competition math (math500): Thinking mode (r1 with max_thinking_tokens)
    """
    if "12b" in model_label.lower():
        res = execute_r0_item(item, benchmark, port)
        res["arm"] = "routed"
        res["routed_to"] = "r0_direct"
        return res

    if benchmark == "gsm_symbolic":
        res = execute_p2_item(item, benchmark, transport, port, max_code_tokens=max_code_tokens)
        res["arm"] = "routed"
        res["routed_to"] = "p2_pal"
        return res
    else:
        res = execute_r1_item(item, benchmark, port, max_thinking_tokens=max_thinking_tokens)
        res["arm"] = "routed"
        res["routed_to"] = "r1_thinking_6k"
        return res


# ---------------------------------------------------------------------------
# Statistics: McNemar Paired Testing & Wilson Confidence Intervals
# ---------------------------------------------------------------------------

def compute_wilson_ci(passed: int, total: int) -> tuple[float, float]:
    """Calculate 95% Wilson Score Confidence Interval."""
    if total == 0:
        return (0.0, 0.0)
    low, high = wilson_score_interval(passed, total, confidence=0.95)
    return (round(low * 100, 2), round(high * 100, 2))


def exact_mcnemar_test(arm1_results: list[dict], arm2_results: list[dict]) -> dict[str, Any]:
    """Perform exact McNemar paired test on discordant pairs."""
    from scipy.stats import binomtest

    map1 = {r["item_id"]: bool(r.get("strict_pass") or r.get("lenient_pass")) for r in arm1_results}
    map2 = {r["item_id"]: bool(r.get("strict_pass") or r.get("lenient_pass")) for r in arm2_results}

    common_ids = sorted(set(map1.keys()) & set(map2.keys()))
    n = len(common_ids)

    n11 = 0  # Both pass
    b = 0    # Arm 1 pass, Arm 2 fail
    c = 0    # Arm 1 fail, Arm 2 pass
    n00 = 0  # Both fail

    for iid in common_ids:
        p1 = map1[iid]
        p2 = map2[iid]
        if p1 and p2:
            n11 += 1
        elif p1 and not p2:
            b += 1
        elif not p1 and p2:
            c += 1
        else:
            n00 += 1

    discordant = b + c
    if discordant == 0:
        p_val = 1.0
        odds_ratio = 1.0
    else:
        res = binomtest(b, discordant, 0.5, alternative="two-sided")
        p_val = res.pvalue
        # Haldane-Anscombe odds ratio correction
        odds_ratio = (b + 0.5) / (c + 0.5)

    acc1 = sum(1 for iid in common_ids if map1[iid]) / n * 100 if n > 0 else 0.0
    acc2 = sum(1 for iid in common_ids if map2[iid]) / n * 100 if n > 0 else 0.0
    delta = acc1 - acc2

    return {
        "n_paired": n,
        "n11": n11,
        "b_arm1_only": b,
        "c_arm2_only": c,
        "n00": n00,
        "p_value": p_val,
        "odds_ratio": round(odds_ratio, 3),
        "acc_arm1": round(acc1, 2),
        "acc_arm2": round(acc2, 2),
        "delta": round(delta, 2),
        "significant_05": p_val < 0.05,
    }


# ---------------------------------------------------------------------------
# Runner Engine
# ---------------------------------------------------------------------------

def run_benchmark_arm(
    model_label: str,
    benchmark_name: str,
    arm: str,
    samples: int,
    output_dir: Path,
    port: int = 8080,
    resume: bool = True,
    transport: DockerRPCTransport | None = None,
    max_thinking_tokens: int = 4096,
    max_code_tokens: int = 2048,
    split: str = "dev",
) -> list[dict[str, Any]]:
    """Execute a single (model, benchmark, arm) experimental cell."""
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{split}" if split != "dev" else ""
    cap_suffix = ""
    if arm in ("p1", "p2") and max_code_tokens != 1024:
        cap_suffix = f"_cap{max_code_tokens}"
    elif arm == "r1" and max_thinking_tokens != 4096 and model_label != "gemma-4-12b":
        cap_suffix = f"_think{max_thinking_tokens}"
    out_file = output_dir / f"{model_label}_{benchmark_name}_{arm}{suffix}{cap_suffix}_{samples}.json"
    chk_file = output_dir / f"{model_label}_{benchmark_name}_{arm}{suffix}{cap_suffix}_{samples}.checkpoint.json"

    completed: dict[str, dict[str, Any]] = {}
    if resume and chk_file.exists():
        try:
            chk_data = json.loads(chk_file.read_text(encoding="utf-8"))
            for r in chk_data.get("results", []):
                completed[r["item_id"]] = r
            print(f"   [Resume] Loaded {len(completed)} existing results from checkpoint.")
        except Exception:
            pass

    # Load dataset
    if benchmark_name == "gsm_symbolic":
        dataset = load_gsm_symbolic_stratified(samples, split=split)
    else:
        dataset = load_math500_dataset(samples, split=split)

    print(f"\n>>> Running [{model_label.upper()}] | Benchmark: {benchmark_name.upper()} ({len(dataset)} items, Split: {split.upper()}) | Arm: {arm.upper()}")
    vram_start = get_gpu_vram_mib()
    print(f"   Hardware VRAM Start: {vram_start} MiB")

    results_list: list[dict[str, Any]] = []
    t_start = time.perf_counter()

    for idx, item in enumerate(dataset, 1):
        item_id = item["item_id"]
        if item_id in completed:
            results_list.append(completed[item_id])
            continue

        if arm == "r0":
            res = execute_r0_item(item, benchmark_name, port)
        elif arm == "r1":
            res = execute_r1_item(item, benchmark_name, port, max_thinking_tokens=max_thinking_tokens)
        elif arm == "p1":
            assert transport is not None
            res = execute_p1_item(item, benchmark_name, transport, port, max_code_tokens=max_code_tokens)
        elif arm == "p2":
            assert transport is not None
            res = execute_p2_item(item, benchmark_name, transport, port, max_code_tokens=max_code_tokens)
        elif arm == "p3":
            assert transport is not None
            res = execute_p3_item(item, benchmark_name, transport, port, max_thinking_tokens=max_thinking_tokens)
        elif arm == "routed":
            assert transport is not None
            res = execute_routed_item(
                item, benchmark_name, transport, port,
                model_label=model_label,
                max_thinking_tokens=max_thinking_tokens,
                max_code_tokens=max_code_tokens,
            )
        else:
            raise ValueError(f"Unknown arm: {arm}")

        results_list.append(res)
        completed[item_id] = res

        # Periodic / progressive checkpointing every 5 items
        if idx % 5 == 0 or idx == len(dataset):
            chk_payload = {
                "model_label": model_label,
                "benchmark": benchmark_name,
                "arm": arm,
                "samples": samples,
                "completed_count": len(results_list),
                "results": results_list,
            }
            chk_file.write_text(json.dumps(chk_payload, indent=2), encoding="utf-8")
            n_pass = sum(1 for r in results_list if (r.get("strict_pass") or r.get("lenient_pass")))
            acc = (n_pass / len(results_list)) * 100
            print(f"   [{idx}/{len(dataset)}] Passed: {n_pass}/{len(results_list)} ({acc:.1f}%) | Lat: {res['latency_s']}s | Tok: {res['completion_tokens']}", flush=True)

    t_total = time.perf_counter() - t_start
    vram_end = get_gpu_vram_mib()

    # Final save
    strict_passed = sum(1 for r in results_list if r.get("strict_pass"))
    lenient_passed = sum(1 for r in results_list if r.get("lenient_pass"))
    total_tokens = sum(r.get("completion_tokens", 0) for r in results_list)
    avg_tokens = total_tokens / len(results_list) if results_list else 0
    truncations = sum(1 for r in results_list if r.get("truncated"))

    ci_strict = compute_wilson_ci(strict_passed, len(results_list))
    ci_lenient = compute_wilson_ci(lenient_passed, len(results_list))

    summary = {
        "model_label": model_label,
        "benchmark": benchmark_name,
        "arm": arm,
        "samples": len(results_list),
        "split": split,
        "git_commit": get_git_commit_hash(),
        "max_thinking_tokens": max_thinking_tokens,
        "max_code_tokens": max_code_tokens,
        "strict_passed": strict_passed,
        "strict_accuracy": round((strict_passed / len(results_list)) * 100, 2),
        "strict_ci_95": ci_strict,
        "lenient_passed": lenient_passed,
        "lenient_accuracy": round((lenient_passed / len(results_list)) * 100, 2),
        "lenient_ci_95": ci_lenient,
        "total_tokens": total_tokens,
        "avg_tokens_per_item": round(avg_tokens, 1),
        "truncation_count": truncations,
        "truncation_rate_pct": round((truncations / len(results_list)) * 100, 2),
        "total_elapsed_s": round(t_total, 2),
        "avg_latency_s": round(t_total / len(results_list), 3) if results_list else 0,
        "vram_start_mib": vram_start,
        "vram_peak_mib": max(vram_start, vram_end),
        "results": results_list,
    }

    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if chk_file.exists():
        try:
            chk_file.unlink()
        except Exception:
            pass

    print(f"=== FINISHED {arm.upper()} | Accuracy: {summary['strict_accuracy']}% [{ci_strict[0]}%, {ci_strict[1]}%] | Time: {t_total:.1f}s ===")
    return results_list


# ---------------------------------------------------------------------------
# Report & Table Synthesis
# ---------------------------------------------------------------------------

def generate_comparative_report(
    output_dir: Path,
    models: list[str],
    benchmarks: list[str],
    samples: int,
) -> str:
    """Generate the full deliverable Markdown report with factorial table and McNemar appendix."""
    lines = []
    lines.append("# Project Lucca: Factorial PAL-Off Model-Scale Ablation Report")
    lines.append(f"**Sample Size:** Paired $n={samples}$ per Arm | **Confidence Level:** 95% Wilson Score CI\n")

    lines.append("## 1. Factorial Performance Scorecard (Model Size x Scaffold Arm)")
    lines.append("")
    lines.append("| Model | Arm | Scaffold / Thinking | Exec Substrate | Benchmark | Strict Acc (%) | Wilson 95% CI | Lenient Acc (%) | Avg Tok/Item | Avg Lat (s) | Peak VRAM | Trunc (%) |")
    lines.append("| :--- | :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    raw_results_store: dict[tuple[str, str, str], list[dict]] = {}

    for mod in models:
        for bm in benchmarks:
            for arm in ["r0", "r1", "p1", "p2"]:
                fpath = output_dir / f"{mod}_{bm}_{arm}_{samples}.json"
                if not fpath.exists():
                    continue
                d = json.loads(fpath.read_text(encoding="utf-8"))
                raw_results_store[(mod, bm, arm)] = d["results"]

                arm_name = {
                    "r0": "Raw Direct (`enable_thinking=F`)",
                    "r1": "Raw Thinking (`enable_thinking=T`)",
                    "p1": "PAL Turn 1",
                    "p2": "PAL + Turn 2 Feedback",
                }[arm]
                substrate = "None (Mental)" if arm.startswith("r") else "Docker Sandbox"

                strict_acc = f"{d['strict_accuracy']:.1f}%"
                ci_str = f"[{d['strict_ci_95'][0]}%, {d['strict_ci_95'][1]}%]"
                len_acc = f"{d['lenient_accuracy']:.1f}%"
                tok = f"{d['avg_tokens_per_item']:.0f}"
                lat = f"{d['avg_latency_s']:.2f}s"
                vram = f"{d['vram_peak_mib']} MiB"
                trunc = f"{d['truncation_rate_pct']:.1f}%"

                lines.append(f"| **{mod}** | **{arm.upper()}** | {arm_name} | {substrate} | {bm} | {strict_acc} | {ci_str} | {len_acc} | {tok} | {lat} | {vram} | {trunc} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Paired McNemar Statistical Appendix (Discordant Pairs & Significance)")
    lines.append("")
    lines.append("| Model | Benchmark | Arm Comparison | $N$ Paired | Arm A Acc | Arm B Acc | $\\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Odds Ratio | Significance ($p < 0.05$) |")
    lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    pairs = [
        ("p2", "r0", "P2 vs R0 (Total Scaffold Lift)"),
        ("p2", "r1", "P2 vs R1 (Scaffold vs Thinking)"),
        ("r1", "r0", "R1 vs R0 (Native Thinking Lift)"),
        ("p2", "p1", "P2 vs P1 (Turn-2 Reprompting Lift)"),
    ]

    for mod in models:
        for bm in benchmarks:
            for a1, a2, label in pairs:
                if (mod, bm, a1) in raw_results_store and (mod, bm, a2) in raw_results_store:
                    mc = exact_mcnemar_test(raw_results_store[(mod, bm, a1)], raw_results_store[(mod, bm, a2)])
                    sig_str = "**YES** (Significant)" if mc["significant_05"] else "NO (Parity / Noise)"
                    lines.append(
                        f"| {mod} | {bm} | **{a1.upper()} vs {a2.upper()}** | {mc['n_paired']} | {mc['acc_arm1']}% | {mc['acc_arm2']}% | {mc['delta']:+.2f} | {mc['b_arm1_only']} : {mc['c_arm2_only']} | {mc['p_value']:.4e} | {mc['odds_ratio']} | {sig_str} |"
                    )

    report_text = "\n".join(lines)
    report_file = output_dir / f"PAL_OFF_FACTORIAL_REPORT_{samples}.md"
    report_file.write_text(report_text, encoding="utf-8")
    print(f"\n[OK] Generated comprehensive report: {report_file}")
    return report_text


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="PAL-Off Factorial Model-Scale Ablation Runner")
    parser.add_argument("--model-label", type=str, default="auto", help="Model label (e.g. gemma-4-e2b, gemma-4-e4b, gemma-4-12b)")
    parser.add_argument("--arm", type=str, default="all", choices=["r0", "r1", "p1", "p2", "p3", "routed", "all"], help="Scaffold arm")
    parser.add_argument("--split", type=str, default="dev", choices=["dev", "heldout"], help="Dataset split (dev or heldout)")
    parser.add_argument("--benchmark", type=str, default="all", choices=["gsm_symbolic", "math500", "all"], help="Benchmark suite")
    parser.add_argument("--samples", type=int, default=500, help="Number of items to evaluate (100 or 500)")
    parser.add_argument("--max-thinking-tokens", type=int, default=4096, help="Max tokens for thinking mode / reasoning")
    parser.add_argument("--max-code-tokens", type=int, default=1024, help="Max tokens for PAL code generation")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    parser.add_argument("--port", type=int, default=8080, help="llama-server port")
    parser.add_argument("--no-resume", action="store_true", help="Do not resume from checkpoint")
    parser.add_argument("--report-only", action="store_true", help="Only generate report from existing result files")

    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.report_only:
        generate_comparative_report(
            out_dir,
            models=["gemma-4-e2b", "gemma-4-e4b", "gemma-4-12b"],
            benchmarks=["gsm_symbolic", "math500"],
            samples=args.samples,
        )
        return 0

    # Auto-detect model if label is 'auto'
    model_label = args.model_label
    if model_label == "auto":
        srv_name = get_server_model_name(args.port).lower()
        if "e2b" in srv_name:
            model_label = "gemma-4-e2b"
        elif "e4b" in srv_name:
            model_label = "gemma-4-e4b"
        elif "12b" in srv_name:
            model_label = "gemma-4-12b"
        else:
            model_label = "gemma-4-e2b"
    print(f"Active Model Label: {model_label}")

    arms = ["r0", "r1", "p1", "p2", "p3", "routed"] if args.arm == "all" else [args.arm]
    benchmarks = ["gsm_symbolic", "math500"] if args.benchmark == "all" else [args.benchmark]

    # Initialize Docker transport if PAL arms are requested
    transport = None
    if any(a in ("p1", "p2", "p3", "routed") for a in arms):
        print("Initializing DockerRPCTransport for PAL execution...")
        transport = DockerRPCTransport(container_name="lucca-file-sandbox")
        transport.ensure_container_running()

    for bm in benchmarks:
        for arm in arms:
            run_benchmark_arm(
                model_label=model_label,
                benchmark_name=bm,
                arm=arm,
                samples=args.samples,
                output_dir=out_dir,
                port=args.port,
                resume=not args.no_resume,
                transport=transport,
                max_thinking_tokens=args.max_thinking_tokens,
                max_code_tokens=args.max_code_tokens,
                split=args.split,
            )

    # Synthesize report
    generate_comparative_report(
        out_dir,
        models=[model_label],
        benchmarks=benchmarks,
        samples=args.samples,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
