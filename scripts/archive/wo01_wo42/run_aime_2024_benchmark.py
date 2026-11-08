#!/usr/bin/env python3
"""
Project Lucca — AIME 2024 (American Invitational Mathematics Examination) Benchmark Runner
Evaluates 30 high-difficulty Olympiad mathematics problems:
Direct Non-Thinking ($T=0.0$) vs Extended Thinking ($T=0.6$).
Integer target range: [000, 999].
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

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "aime_2024.jsonl"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 180.0


@dataclass
class AIMEResult:
    problem_idx: int
    problem: str
    target_answer: int
    direct_prediction: int | None
    direct_correct: bool
    direct_latency_s: float
    direct_finish_reason: str
    direct_tokens: int
    thinking_prediction: int | None
    thinking_correct: bool
    thinking_latency_s: float
    thinking_finish_reason: str
    thinking_tokens: int


def query_llm(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
    enable_thinking: bool = False,
) -> tuple[str, str, int]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert competition mathematician. Solve the problem carefully and conclude with your "
                "final numerical answer as an integer between 0 and 999 formatted as \\boxed{number} or 'The answer is number'."
            ),
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
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason") or "unknown"
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        msg = choice["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        if content.strip() and reasoning.strip():
            text = f"{content}\n[REASONING]\n{reasoning}"
        else:
            text = content if content.strip() else reasoning
        return text, finish_reason, completion_tokens


def extract_integer_answer(text: str) -> int | None:
    if not text:
        return None
    # 1. \boxed{123}
    m = re.findall(r"\\boxed\{([0-9]+)\}", text)
    if m:
        try:
            return int(m[-1])
        except ValueError:
            pass

    # 2. "The answer is 123"
    m = re.findall(r"(?:answer|is|equal(?:s)? to)[:\s]*\$?([0-9]+)\$?", text, re.IGNORECASE)
    if m:
        try:
            return int(m[-1])
        except ValueError:
            pass

    # 3. Final standalone integer
    m = re.findall(r"\b([0-9]{1,4})\b", text)
    if m:
        try:
            val = int(m[-1])
            if 0 <= val <= 999:
                return val
        except ValueError:
            pass
    return None


def run_aime_benchmark(
    limit: int = 30,
    model_tag: str = "E2B",
    direct_cap: int = 512,
    thinking_cap: int = 3072,
) -> None:
    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: AIME 2024 MATHEMATICS BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Model: {model_tag} | Direct Cap: {direct_cap} | Thinking Cap: {thinking_cap}", flush=True)
    print(f"Dataset: {DATA_FILE.name} (limit={limit})\n", flush=True)

    lines = [json.loads(l) for l in DATA_FILE.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
    items = lines[:limit]

    results: list[AIMEResult] = []

    for idx, it in enumerate(items, start=1):
        prompt_content = it["prompt"][0]["content"] if isinstance(it["prompt"], list) else it["prompt"]
        target = int(it["label"])

        print(f"[{idx:02d}/{len(items):02d}] AIME_2024_Q{idx:02d}... ", end="", flush=True)

        # 1. Direct
        t0 = time.perf_counter()
        try:
            d_out, d_finish, d_tok = query_llm(prompt_content, max_tokens=direct_cap, temperature=0.0, enable_thinking=False)
            d_sec = time.perf_counter() - t0
            d_pred = extract_integer_answer(d_out)
            d_ok = (d_pred == target)
        except Exception:
            d_out, d_finish, d_tok, d_pred, d_ok, d_sec = "", "error", 0, None, False, 0.0

        # 2. Thinking
        t0 = time.perf_counter()
        try:
            th_out, th_finish, th_tok = query_llm(prompt_content, max_tokens=thinking_cap, temperature=0.6, enable_thinking=True)
            th_sec = time.perf_counter() - t0
            th_pred = extract_integer_answer(th_out)
            th_ok = (th_pred == target)
        except Exception:
            th_out, th_finish, th_tok, th_pred, th_ok, th_sec = "", "error", 0, None, False, 0.0

        r = AIMEResult(
            problem_idx=idx,
            problem=prompt_content[:100],
            target_answer=target,
            direct_prediction=d_pred,
            direct_correct=d_ok,
            direct_latency_s=round(d_sec, 2),
            direct_finish_reason=d_finish,
            direct_tokens=d_tok,
            thinking_prediction=th_pred,
            thinking_correct=th_ok,
            thinking_latency_s=round(th_sec, 2),
            thinking_finish_reason=th_finish,
            thinking_tokens=th_tok,
        )
        results.append(r)

        d_flag = f"[TRUNC:{d_tok}]" if d_finish == "length" else f"[{d_tok}tok]"
        th_flag = f"[TRUNC:{th_tok}]" if th_finish == "length" else f"[{th_tok}tok]"
        print(f"Direct={'PASS' if d_ok else 'FAIL'} ({d_pred} {d_flag}) | Think={'PASS' if th_ok else 'FAIL'} ({th_pred} {th_flag}) [Target: {target}]", flush=True)

    # Summary
    n = len(results)
    total_d = sum(1 for r in results if r.direct_correct)
    total_th = sum(1 for r in results if r.thinking_correct)

    d_trunc = sum(1 for r in results if r.direct_finish_reason == "length")
    th_trunc = sum(1 for r in results if r.thinking_finish_reason == "length")

    b = sum(1 for r in results if r.direct_correct and not r.thinking_correct)
    c = sum(1 for r in results if not r.direct_correct and r.thinking_correct)
    try:
        from scipy.stats import binomtest
        p_val = binomtest(min(b, c), b + c, 0.5).pvalue if (b + c) > 0 else 1.0
    except Exception:
        p_val = math.erfc((abs(b - c) - 1) / math.sqrt(2 * (b + c))) if (b + c) > 0 else 1.0

    print("\n" + "=" * 60)
    print("AIME 2024 BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"TOTAL (n={n}): Direct = {total_d}/{n} ({total_d/n*100:.1f}%) [Truncated: {d_trunc}/{n}] | Thinking = {total_th}/{n} ({total_th/n*100:.1f}%) [Truncated: {th_trunc}/{n}]")
    print(f"McNemar Discordant Pairs: b (Direct+, Think-)={b}, c (Direct-, Think+)={c} | p-value = {p_val:.4f}")
    print("=" * 60)

    out_name = f"aime_2024_benchmark_{model_tag}_{int(time.time())}.json" if model_tag else f"aime_2024_benchmark_{int(time.time())}.json"
    out_file = REPO_ROOT / "logs" / "test_reports" / out_name
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "AIME_2024_Olympiad_Mathematics",
        "model_tag": model_tag or "E2B",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_problems": n,
        "direct_cap": direct_cap,
        "thinking_cap": thinking_cap,
        "direct_passed": total_d,
        "direct_pct": round(total_d / n * 100, 1),
        "direct_truncations": d_trunc,
        "direct_truncation_rate_pct": round(d_trunc / n * 100, 1),
        "thinking_passed": total_th,
        "thinking_pct": round(total_th / n * 100, 1),
        "thinking_truncations": th_trunc,
        "thinking_truncation_rate_pct": round(th_trunc / n * 100, 1),
        "discordant_b": b,
        "discordant_c": c,
        "mcnemar_p_value": round(p_val, 4),
        "results": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report written to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIME 2024 Benchmark Runner")
    parser.add_argument("--limit", type=int, default=30, help="Problem limit (default: 30)")
    parser.add_argument("--model-tag", type=str, default="E2B", help="Model tier tag (e.g. E2B, E4B, 12B)")
    parser.add_argument("--direct-cap", type=int, default=512, help="Direct token cap (default: 512)")
    parser.add_argument("--thinking-cap", type=int, default=3072, help="Thinking token cap (default: 3072)")
    args = parser.parse_args()
    run_aime_benchmark(
        limit=args.limit,
        model_tag=args.model_tag,
        direct_cap=args.direct_cap,
        thinking_cap=args.thinking_cap,
    )
