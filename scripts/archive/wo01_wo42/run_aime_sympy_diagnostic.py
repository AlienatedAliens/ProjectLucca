#!/usr/bin/env python3
"""
Project Lucca — AIME 2024 SymPy Formalization & Execution Benchmark Runner
Evaluates Olympiad competition mathematics via neurosymbolic translation:
Arm A: Bare Extended Thinking (Mental Calculation with internal monologue)
Arm B: Compound SymPy / Python Sandbox Formal Execution (Docker lucca-file-sandbox)
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.sandbox.preflight import extract_python_code
from lucca.reasoning.cegis_python import PythonCEGISEngine

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "aime_2024.jsonl"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0


@dataclass
class AIMESymPyResult:
    problem_idx: int
    problem: str
    target_answer: int
    mental_prediction: int | None
    mental_correct: bool
    mental_tokens: int
    sympy_prediction: int | None
    sympy_correct: bool
    sympy_executed: bool
    sympy_exec_ms: float
    turns_taken: int
    method: str
    stdout: str


def query_llm(
    messages: list[dict[str, str]],
    max_tokens: int = 1536,
    temperature: float = 0.0,
    enable_thinking: bool = False,
) -> tuple[str, str, int]:
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        res = client.post(SERVER_URL, json=payload)
        res.raise_for_status()
        data = res.json()
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason") or "unknown"
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        msg = choice["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        text = f"{content}\n[REASONING]\n{reasoning}" if (content.strip() and reasoning.strip()) else (content if content.strip() else reasoning)
        return text, finish_reason, completion_tokens


def extract_integer_answer(text: str) -> int | None:
    if not text:
        return None
    # \boxed{123}
    m = re.findall(r"\\boxed\{([0-9]+)\}", text)
    if m:
        try:
            return int(m[-1])
        except ValueError:
            pass
    # The answer is 123
    m2 = re.findall(r"(?:answer\s+is|result\s+is|=)\s*([0-9]{1,4})\b", text, re.IGNORECASE)
    if m2:
        try:
            return int(m2[-1])
        except ValueError:
            pass
    # Standalone last integer
    nums = re.findall(r"\b([0-9]{1,4})\b", text)
    if nums:
        try:
            return int(nums[-1])
        except ValueError:
            pass
    return None


from lucca.sandbox.rpc import DockerRPCTransport

_rpc_instance: DockerRPCTransport | None = None


def get_rpc() -> DockerRPCTransport:
    global _rpc_instance
    if _rpc_instance is None:
        _rpc_instance = DockerRPCTransport(container_name="lucca-file-sandbox")
        if not _rpc_instance.is_container_running():
            _rpc_instance.ensure_container_running()
    return _rpc_instance


def execute_python_docker(code: str, timeout_s: float = 15.0) -> tuple[int | None, str, float]:
    """Executes Python code inside WSL2 lucca-file-sandbox container via persistent RPC bridge."""
    t0 = time.perf_counter()
    try:
        rpc = get_rpc()
        call_id = f"aime-{time.time_ns()}"
        res = rpc.execute(call_id=call_id, tool="run_python", args={"code": code}, timeout_s=timeout_s)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        out = str(res.content or "").strip()
        m = re.findall(r"\b([0-9]+)\b", out)
        if m:
            val = int(m[-1])
            return val % 1000 if val >= 1000 else val, out, elapsed_ms
        err = str(res.stderr or "").strip()
        return None, err or out, elapsed_ms
    except Exception as exc:
        return None, str(exc), (time.perf_counter() - t0) * 1000.0


def clean_math_prompt(raw: str) -> str:
    """Removes single dollar signs that trigger placeholder confusion on edge models."""
    cleaned = re.sub(r"\$([^\$]+)\$", r"\1", raw)
    return cleaned.strip()


def run_benchmark(limit: int = 5, model_tag: str = "E4B") -> None:
    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: AIME 2024 SYMPY NEUROSYMBOLIC BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Model: {model_tag} | Limit: {limit}\n", flush=True)

    items = []
    with open(DATA_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    items = items[:limit]
    results: list[AIMESymPyResult] = []

    mental_correct_total = 0
    sympy_correct_total = 0

    for idx, it in enumerate(items, start=1):
        raw_prompt = it["prompt"][0]["content"]
        clean_prompt = clean_math_prompt(raw_prompt)
        target = int(it["label"])

        print(f"[{idx:02d}/{len(items):02d}] Problem {idx} (Target: {target})... ", end="", flush=True)

        # 1. Bare Mental Extended Thinking
        mental_messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert competition mathematician. Solve the problem carefully and conclude with your "
                    "final numerical answer as an integer between 0 and 999 formatted as \\boxed{number}."
                ),
            },
            {"role": "user", "content": raw_prompt},
        ]
        try:
            m_raw, m_fin, m_tok = query_llm(mental_messages, max_tokens=1536, temperature=0.6, enable_thinking=True)
            m_pred = extract_integer_answer(m_raw)
            m_ok = (m_pred == target)
        except Exception:
            m_pred, m_ok, m_tok = None, False, 0

        # 2. Compound SymPy Formal Translation & CEGIS Sandbox Self-Repair Execution
        sympy_messages = [
            {
                "role": "system",
                "content": (
                    "You are a Python programmer solving contest math problems using SymPy or computation. "
                    "Write concise executable Python code. Do not write introductory prose or explanatory comments. "
                    "The code must compute the final integer answer and print it using print(ans). "
                    "Output only ```python ... ```."
                ),
            },
            {
                "role": "user",
                "content": "Problem: A list of integers from 1 to 10 has sum S. Find S.",
            },
            {
                "role": "assistant",
                "content": "```python\nfrom sympy import symbols, solve\nans = sum(range(1, 11))\nprint(ans)\n```",
            },
            {
                "role": "user",
                "content": f"Problem: {clean_prompt}\nSolve using Python/SymPy:",
            },
        ]
        try:
            cegis_engine = PythonCEGISEngine(
                container_name="lucca-file-sandbox",
                timeout_s=15.0,
                max_turns=3,
                server_url=SERVER_URL,
            )
            cegis_res = cegis_engine.synthesize_checked_formalization(
                task_prompt=f"Problem: {clean_prompt}\nFind the integer answer (if AIME, take remainder modulo 1000 if specified).",
                output_pattern=r"\b([0-9]+)\b",
            )
            if not cegis_res.success or not cegis_res.predicted_output:
                cegis_res = cegis_engine.synthesize_and_repair(
                    task_prompt=f"Problem: {clean_prompt}\nSolve using Python/SymPy:",
                    exemplar_messages=sympy_messages,
                    max_tokens=2048,
                    temperature=0.0,
                    output_pattern=r"\b([0-9]+)\b",
                )
            s_pred = extract_integer_answer(cegis_res.predicted_output) if cegis_res.predicted_output else None
            s_ok = (s_pred == target)
            s_exec = len(cegis_res.traces) > 0
            s_ms = cegis_res.total_elapsed_ms
            s_turns = cegis_res.turns_taken
            s_method = cegis_res.method
            s_out = cegis_res.predicted_output or (cegis_res.traces[-1].stderr if cegis_res.traces else "")
        except Exception as exc:
            s_pred, s_out, s_ms, s_exec, s_ok = None, str(exc), 0.0, False, False
            s_turns, s_method = 1, "EXCEPTION"

        if m_ok:
            mental_correct_total += 1
        if s_ok:
            sympy_correct_total += 1

        res_obj = AIMESymPyResult(
            problem_idx=idx,
            problem=clean_prompt[:120] + "...",
            target_answer=target,
            mental_prediction=m_pred,
            mental_correct=m_ok,
            mental_tokens=m_tok,
            sympy_prediction=s_pred,
            sympy_correct=s_ok,
            sympy_executed=s_exec,
            sympy_exec_ms=s_ms,
            turns_taken=s_turns,
            method=s_method,
            stdout=s_out[:200] if s_out else "",
        )
        results.append(res_obj)

        m_status = "PASS" if m_ok else "FAIL"
        s_status = "PASS" if s_ok else "FAIL"
        print(f"Mental: {m_status} ({m_pred}) | SymPy: {s_status} ({s_pred})")

    print("\n======================================================================")
    print(f"Total Evaluated: {len(items)}")
    print(f"Bare Extended Thinking: {mental_correct_total}/{len(items)} ({(mental_correct_total/len(items))*100:.1f}%)")
    print(f"Compound SymPy Sandbox:  {sympy_correct_total}/{len(items)} ({(sympy_correct_total/len(items))*100:.1f}%)")
    print("======================================================================")

    # Save report
    report_file = REPO_ROOT / "logs" / "test_reports" / f"aime_sympy_diagnostic_{model_tag}_{int(time.time())}.json"
    data = {
        "benchmark": "AIME-2024-SymPy-Diagnostic",
        "model_tag": model_tag,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_problems": len(items),
        "mental_pct": (mental_correct_total / len(items)) * 100.0,
        "sympy_pct": (sympy_correct_total / len(items)) * 100.0,
        "results": [asdict(r) for r in results],
    }
    report_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[+] Saved diagnostic report to: {report_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--model-tag", type=str, default="E4B")
    args = parser.parse_args()
    run_benchmark(limit=args.limit, model_tag=args.model_tag)
