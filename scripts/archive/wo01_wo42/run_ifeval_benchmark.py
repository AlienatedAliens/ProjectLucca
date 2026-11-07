#!/usr/bin/env python3
"""
Project Lucca — Google IFEval (Instruction Following Evaluation) Benchmark Runner
Evaluates 30 verifiable instruction-following tasks using Google Research's
official instruction verification engine (Zhou et al., 2023).
Direct Non-Thinking ($T=0.0$) vs Extended Thinking ($T=0.6$).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import random
import sys
import time
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.ifeval import instructions_registry as ir

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "ifeval_input_data.jsonl"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 90.0


@dataclass
class IFEvalItemResult:
    key: int
    prompt: str
    instruction_ids: list[str]
    direct_passed: bool
    direct_instructions_passed: list[bool]
    direct_latency_s: float
    thinking_passed: bool
    thinking_instructions_passed: list[bool]
    thinking_latency_s: float


def query_llm(
    prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    enable_thinking: bool = False,
) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are a precise, compliant assistant. Follow every constraint in the user's prompt strictly.",
        },
        {"role": "user", "content": prompt},
    ]
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
        return data["choices"][0]["message"]["content"]


def evaluate_instructions(
    response: str,
    instruction_ids: list[str],
    kwargs_list: list[dict[str, Any]],
) -> list[bool]:
    results = []
    for inst_id, kw in zip(instruction_ids, kwargs_list):
        if inst_id not in ir.INSTRUCTION_DICT:
            results.append(False)
            continue
        builder = ir.INSTRUCTION_DICT[inst_id]
        inst = builder(inst_id)
        # build description kwargs
        clean_kw = {k: v for k, v in kw.items() if v is not None}
        inst.build_description(**clean_kw)
        passed = bool(inst.check_following(response))
        results.append(passed)
    return results


def run_benchmark(limit: int = 30, seed: int = 42) -> None:
    lines = DATA_FILE.read_text(encoding="utf-8").splitlines()
    all_items = [json.loads(line) for line in lines if line.strip()]

    rng = random.Random(seed)
    rng.shuffle(all_items)
    items = all_items[:limit]

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: GOOGLE IFEVAL INSTRUCTION-FOLLOWING BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Sample size: {len(items)} prompts across verifiable rule types\n", flush=True)

    results: list[IFEvalItemResult] = []

    for idx, item in enumerate(items, start=1):
        key = item["key"]
        prompt = item["prompt"]
        inst_ids = item["instruction_id_list"]
        kw_list = item["kwargs"]

        print(f"[{idx:02d}/{len(items):02d}] Key {key} ({', '.join(inst_ids)})... ", end="", flush=True)

        # 1. Direct
        t0 = time.perf_counter()
        try:
            d_out = query_llm(prompt, max_tokens=1024, temperature=0.0, enable_thinking=False)
            d_sec = time.perf_counter() - t0
            d_checks = evaluate_instructions(d_out, inst_ids, kw_list)
            d_ok = all(d_checks)
        except Exception as exc:
            d_checks, d_ok, d_sec = [False] * len(inst_ids), False, 0.0

        # 2. Thinking
        t0 = time.perf_counter()
        try:
            th_out = query_llm(prompt, max_tokens=2048, temperature=0.6, enable_thinking=True)
            th_sec = time.perf_counter() - t0
            th_checks = evaluate_instructions(th_out, inst_ids, kw_list)
            th_ok = all(th_checks)
        except Exception as exc:
            th_checks, th_ok, th_sec = [False] * len(inst_ids), False, 0.0

        r = IFEvalItemResult(
            key=key,
            prompt=prompt,
            instruction_ids=inst_ids,
            direct_passed=d_ok,
            direct_instructions_passed=d_checks,
            direct_latency_s=round(d_sec, 2),
            thinking_passed=th_ok,
            thinking_instructions_passed=th_checks,
            thinking_latency_s=round(th_sec, 2),
        )
        results.append(r)

        print(f"Direct={'PASS' if d_ok else 'FAIL'} ({sum(d_checks)}/{len(inst_ids)}) | Think={'PASS' if th_ok else 'FAIL'} ({sum(th_checks)}/{len(inst_ids)})", flush=True)

    # Summary
    print("\n" + "=" * 60)
    print("IFEVAL INSTRUCTION-FOLLOWING SUMMARY")
    print("=" * 60)
    n = len(results)
    d_prompt_pass = sum(1 for r in results if r.direct_passed)
    th_prompt_pass = sum(1 for r in results if r.thinking_passed)

    total_inst = sum(len(r.instruction_ids) for r in results)
    d_inst_pass = sum(sum(r.direct_instructions_passed) for r in results)
    th_inst_pass = sum(sum(r.thinking_instructions_passed) for r in results)

    print(f"Strict Prompt-Level Accuracy: Direct = {d_prompt_pass}/{n} ({d_prompt_pass/n*100:.1f}%) | Thinking = {th_prompt_pass}/{n} ({th_prompt_pass/n*100:.1f}%)")
    print(f"Instruction-Level Accuracy:   Direct = {d_inst_pass}/{total_inst} ({d_inst_pass/total_inst*100:.1f}%) | Thinking = {th_inst_pass}/{total_inst} ({th_inst_pass/total_inst*100:.1f}%)")
    print("=" * 60)

    out_file = REPO_ROOT / "logs" / "test_reports" / f"ifeval_benchmark_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "Google_IFEval_Verifiable_Constraints",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_prompts": n,
        "direct_prompt_passed": d_prompt_pass,
        "direct_prompt_pct": round(d_prompt_pass / n * 100, 1),
        "thinking_prompt_passed": th_prompt_pass,
        "thinking_prompt_pct": round(th_prompt_pass / n * 100, 1),
        "total_instructions": total_inst,
        "direct_instructions_passed": d_inst_pass,
        "direct_instruction_pct": round(d_inst_pass / total_inst * 100, 1),
        "thinking_instructions_passed": th_inst_pass,
        "thinking_instruction_pct": round(th_inst_pass / total_inst * 100, 1),
        "results": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report written to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google IFEval Benchmark Runner")
    parser.add_argument("--limit", type=int, default=30, help="Number of prompts (default: 30)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    args = parser.parse_args()
    run_benchmark(limit=args.limit, seed=args.seed)
