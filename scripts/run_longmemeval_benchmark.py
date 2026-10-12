#!/usr/bin/env python3
"""
Project Lucca — LongMemEval (Long-Term Conversational Memory & Temporal Reasoning) Benchmark Runner
Evaluates 30 multi-session conversational scenarios across:
1. knowledge-update (10 items): Superseded facts & preference updates across time
2. temporal-reasoning (10 items): Timeline ordering & relative elapsed duration calculations
3. multi-session (10 items): Cross-session associative fact aggregation
Direct Non-Thinking ($T=0.0$) vs Extended Thinking ($T=0.6$).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "longmemeval_oracle.json"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 180.0


@dataclass
class LongMemResult:
    question_id: str
    question_type: str
    question: str
    ground_truth: str
    direct_response: str
    direct_correct: bool
    direct_latency_s: float
    thinking_response: str
    thinking_correct: bool
    thinking_latency_s: float


def query_llm(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
    enable_thinking: bool = False,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an assistant with access to the user's past conversational memory across multiple sessions. "
                "Carefully consider session timestamps, order of events, and any fact updates. Provide a concise, direct answer."
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
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        if content.strip() and reasoning.strip():
            return f"{content}\n[REASONING]\n{reasoning}"
        return content if content.strip() else reasoning


def evaluate_memory_answer(prediction: str, ground_truth: str) -> bool:
    if not prediction:
        return False
    pred_lower = prediction.lower()
    gt_lower = ground_truth.lower()

    # Direct substring check
    if gt_lower in pred_lower:
        return True

    # Check key alternative phrases if ground truth has 'or' / 'acceptable'
    for part in re.split(r"\s+or\s+|\.|\(|\)", gt_lower):
        part = part.strip()
        if len(part) > 3 and part in pred_lower:
            return True

    # Check numeric extraction if ground truth contains numbers (e.g. "4 days", "25:50")
    gt_nums = re.findall(r"\b\d+(?::\d+)?\b", gt_lower)
    if gt_nums:
        pred_nums = re.findall(r"\b\d+(?::\d+)?\b", pred_lower)
        if any(gn in pred_nums for gn in gt_nums):
            # Also check if main noun or verb matches
            keywords = [w for w in re.findall(r"\b\w{4,}\b", gt_lower) if w not in ("days", "time", "date", "acceptable")]
            if not keywords or any(kw in pred_lower for kw in keywords):
                return True

    # Entity keyword overlap
    gt_words = set(re.findall(r"\b\w{3,}\b", gt_lower)) - {"the", "and", "was", "for", "with", "also", "acceptable"}
    pred_words = set(re.findall(r"\b\w{3,}\b", pred_lower))
    if gt_words and (len(gt_words & pred_words) / len(gt_words) >= 0.75):
        return True

    return False


def format_memory_prompt(item: dict[str, Any]) -> str:
    sections = []
    dates = item.get("haystack_dates", [])
    sessions = item.get("haystack_sessions", [])

    for idx, (dt, s) in enumerate(zip(dates, sessions), start=1):
        lines = [f"[Session {idx} - Date: {dt}]"]
        for turn in s:
            role_label = "User" if turn["role"] == "user" else "Assistant"
            lines.append(f"{role_label}: {turn['content']}")
        sections.append("\n".join(lines))

    history_str = "\n\n".join(sections)
    q_date = item.get("question_date", "")
    q_text = item.get("question", "")

    return (
        f"--- PAST CONVERSATIONAL MEMORY SESSIONS ---\n"
        f"{history_str}\n\n"
        f"--- CURRENT QUERY ---\n"
        f"Current Date: {q_date}\n"
        f"User Question: {q_text}\n\n"
        f"Answer the question directly based on past memory:"
    )


def run_longmem_benchmark(limit_per_type: int = 10, seed: int = 42) -> None:
    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: LongMemEval CONVERSATIONAL MEMORY BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Dataset: {DATA_FILE.name} (limit={limit_per_type} per type)\n", flush=True)

    data = json.load(open(DATA_FILE, encoding="utf-8"))
    types = ["knowledge-update", "temporal-reasoning", "multi-session"]

    rng = random.Random(seed)
    selected_items: list[dict[str, Any]] = []

    for t in types:
        sub = [x for x in data if x.get("question_type") == t]
        rng.shuffle(sub)
        selected_items.extend(sub[:limit_per_type])

    results: list[LongMemResult] = []

    for idx, it in enumerate(selected_items, start=1):
        qid = it["question_id"]
        qtype = it["question_type"]
        qtext = it["question"]
        gt = str(it["answer"])

        prompt = format_memory_prompt(it)
        print(f"[{idx:02d}/{len(selected_items):02d}] [{qtype}] {qid}... ", end="", flush=True)

        # 1. Direct
        t0 = time.perf_counter()
        try:
            d_out = query_llm(prompt, max_tokens=256, temperature=0.0, enable_thinking=False)
            d_sec = time.perf_counter() - t0
            d_ok = evaluate_memory_answer(d_out, gt)
        except Exception:
            d_out, d_ok, d_sec = "", False, 0.0

        # 2. Thinking
        t0 = time.perf_counter()
        try:
            th_out = query_llm(prompt, max_tokens=1024, temperature=0.6, enable_thinking=True)
            th_sec = time.perf_counter() - t0
            th_ok = evaluate_memory_answer(th_out, gt)
        except Exception:
            th_out, th_ok, th_sec = "", False, 0.0

        r = LongMemResult(
            question_id=qid,
            question_type=qtype,
            question=qtext,
            ground_truth=gt,
            direct_response=d_out[:120].replace("\n", " "),
            direct_correct=d_ok,
            direct_latency_s=round(d_sec, 2),
            thinking_response=th_out[:120].replace("\n", " "),
            thinking_correct=th_ok,
            thinking_latency_s=round(th_sec, 2),
        )
        results.append(r)

        print(f"Direct={'PASS' if d_ok else 'FAIL'} | Think={'PASS' if th_ok else 'FAIL'} [GT: {str(gt)[:40]}]", flush=True)

    # Summary
    print("\n" + "=" * 60)
    print("LongMemEval BENCHMARK SUMMARY")
    print("=" * 60)
    for qtype in types:
        sub_res = [r for r in results if r.question_type == qtype]
        d_acc = sum(1 for r in sub_res if r.direct_correct) / len(sub_res) * 100
        th_acc = sum(1 for r in sub_res if r.thinking_correct) / len(sub_res) * 100
        print(f"Type [{qtype:<20}] (n={len(sub_res)}): Direct = {d_acc:5.1f}% | Thinking = {th_acc:5.1f}%")

    n = len(results)
    total_d = sum(1 for r in results if r.direct_correct)
    total_th = sum(1 for r in results if r.thinking_correct)

    b = sum(1 for r in results if r.direct_correct and not r.thinking_correct)
    c = sum(1 for r in results if not r.direct_correct and r.thinking_correct)
    try:
        from scipy.stats import binomtest
        p_val = binomtest(min(b, c), b + c, 0.5).pvalue if (b + c) > 0 else 1.0
    except Exception:
        p_val = math.erfc((abs(b - c) - 1) / math.sqrt(2 * (b + c))) if (b + c) > 0 else 1.0

    print("-" * 60)
    print(f"TOTAL (n={n}): Direct = {total_d}/{n} ({total_d/n*100:.1f}%) | Thinking = {total_th}/{n} ({total_th/n*100:.1f}%)")
    print(f"McNemar Discordant Pairs: b (Direct+, Think-)={b}, c (Direct-, Think+)={c} | p-value = {p_val:.4f}")
    print("=" * 60)

    out_file = REPO_ROOT / "logs" / "test_reports" / f"longmemeval_benchmark_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "LongMemEval_MultiSession_Memory",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_problems": n,
        "direct_passed": total_d,
        "direct_pct": round(total_d / n * 100, 1),
        "thinking_passed": total_th,
        "thinking_pct": round(total_th / n * 100, 1),
        "discordant_b": b,
        "discordant_c": c,
        "mcnemar_p_value": round(p_val, 4),
        "results": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report written to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LongMemEval Benchmark Runner")
    parser.add_argument("--limit", type=int, default=10, help="Items per category (default: 10)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    args = parser.parse_args()
    run_longmem_benchmark(limit_per_type=args.limit, seed=args.seed)
