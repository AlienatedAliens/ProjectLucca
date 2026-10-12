#!/usr/bin/env python3
"""
Project Lucca — MuSR (Multistep Soft Reasoning) Benchmark Runner
Evaluates complex non-mathematical multistep deduction across 3 domains:
1. Murder Mystery (10 problems): Deduce the killer from alibis, motives, and clues
2. Team Allocation (10 problems): Constraint satisfaction task allocation
3. Object Placements (10 problems): Spatial state tracking across narrative movements
Direct Non-Thinking ($T=0.0$) vs Extended Thinking ($T=0.6$).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DATA_DIR: Final[Path] = REPO_ROOT / "data" / "benchmarks"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0


@dataclass
class MuSRResult:
    problem_id: str
    domain: str
    question: str
    target_letter: str
    target_choice: str
    direct_prediction: str | None
    direct_correct: bool
    direct_latency_s: float
    thinking_prediction: str | None
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
                "You are an expert logical detective and analytical reasoner. "
                "Read the story carefully, analyze all clues, and state your final answer as (A), (B), (C), or (D)."
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
        # Combine content and reasoning for extraction
        if content.strip() and reasoning.strip():
            return f"{content}\n[REASONING]\n{reasoning}"
        return content if content.strip() else reasoning


def extract_answer(text: str) -> str | None:
    if not text:
        return None
    # Strip thinking blocks if in raw string
    cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    # Look for explicit conclusion
    m = re.search(r"(?:answer|choice|option|conclusion)(?:\s+is)?[:\s]*\(?([A-E])\)?", cleaned, re.IGNORECASE)
    if m:
        return f"({m.group(1).upper()})"

    m_tail = re.search(r"\(([A-E])\)\s*$", cleaned)
    if m_tail:
        return f"({m_tail.group(1).upper()})"

    matches = re.findall(r"\(([A-E])\)", cleaned)
    if matches:
        return f"({matches[-1].upper()})"

    matches_bare = re.findall(r"\b([A-E])\b", cleaned)
    if matches_bare:
        return f"({matches_bare[-1].upper()})"
    return None


def run_benchmark(per_domain_limit: int = 10, seed: int = 42) -> None:
    domains = [
        ("murder_mystery", DATA_DIR / "musr_murder_mystery.json"),
        ("team_allocation", DATA_DIR / "musr_team_allocation.json"),
        ("object_placements", DATA_DIR / "musr_object_placements.json"),
    ]

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: MuSR MULTISTEP SOFT REASONING BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Domains: Murder Mystery, Team Allocation, Object Placements ({per_domain_limit} each)\n", flush=True)

    results: list[MuSRResult] = []

    for dom_name, path in domains:
        print(f"--- [Domain: {dom_name}] ---", flush=True)
        raw_items = json.loads(path.read_text(encoding="utf-8"))
        rng = random.Random(seed)
        rng.shuffle(raw_items)
        items = raw_items[:per_domain_limit]

        for idx, it in enumerate(items, start=1):
            pid = f"{dom_name}_{idx:02d}"
            context = it["context"].strip()
            q_obj = it["questions"][0]
            question = q_obj["question"].strip()
            choices = q_obj["choices"]
            ans_idx = q_obj["answer"]

            letters = ["(A)", "(B)", "(C)", "(D)", "(E)"][:len(choices)]
            target_letter = letters[ans_idx]
            target_choice = choices[ans_idx]

            choices_str = "\n".join(f"{letters[i]} {choices[i]}" for i in range(len(choices)))
            prompt = (
                f"Story:\n{context}\n\n"
                f"Question: {question}\n\n"
                f"Choices:\n{choices_str}\n\n"
                f"Conclude with your final answer as {', '.join(letters)}."
            )

            print(f"[{idx:02d}/{len(items):02d}] {pid}... ", end="", flush=True)

            # 1. Direct
            t0 = time.perf_counter()
            try:
                d_out = query_llm(prompt, max_tokens=512, temperature=0.0, enable_thinking=False)
                d_sec = time.perf_counter() - t0
                d_pred = extract_answer(d_out)
                d_ok = (d_pred == target_letter)
            except Exception as exc:
                d_pred, d_ok, d_sec = None, False, 0.0

            # 2. Thinking
            t0 = time.perf_counter()
            try:
                th_out = query_llm(prompt, max_tokens=1536, temperature=0.6, enable_thinking=True)
                th_sec = time.perf_counter() - t0
                th_pred = extract_answer(th_out)
                th_ok = (th_pred == target_letter)
            except Exception as exc:
                th_pred, th_ok, th_sec = None, False, 0.0

            r = MuSRResult(
                problem_id=pid,
                domain=dom_name,
                question=question,
                target_letter=target_letter,
                target_choice=target_choice,
                direct_prediction=d_pred,
                direct_correct=d_ok,
                direct_latency_s=round(d_sec, 2),
                thinking_prediction=th_pred,
                thinking_correct=th_ok,
                thinking_latency_s=round(th_sec, 2),
            )
            results.append(r)

            print(f"Direct={'PASS' if d_ok else 'FAIL'} ({d_pred}) | Think={'PASS' if th_ok else 'FAIL'} ({th_pred}) [Target: {target_letter}]", flush=True)

    # Domain summary
    print("\n" + "=" * 60)
    print("MuSR BENCHMARK SUMMARY")
    print("=" * 60)
    for dom_name, _ in domains:
        dom_res = [r for r in results if r.domain == dom_name]
        d_acc = sum(1 for r in dom_res if r.direct_correct) / len(dom_res) * 100
        th_acc = sum(1 for r in dom_res if r.thinking_correct) / len(dom_res) * 100
        print(f"Domain [{dom_name:<18}] (n={len(dom_res)}): Direct = {d_acc:5.1f}% | Thinking = {th_acc:5.1f}%")

    total_d = sum(1 for r in results if r.direct_correct)
    total_th = sum(1 for r in results if r.thinking_correct)
    n = len(results)

    # Discordant pairs for McNemar
    b = sum(1 for r in results if r.direct_correct and not r.thinking_correct) # Direct pass, Think fail
    c = sum(1 for r in results if not r.direct_correct and r.thinking_correct) # Direct fail, Think pass
    try:
        from scipy.stats import binomtest
        p_val = binomtest(min(b, c), b + c, 0.5).pvalue if (b + c) > 0 else 1.0
    except Exception:
        # Normal approximation with continuity correction
        import math
        p_val = math.erfc((abs(b - c) - 1) / math.sqrt(2 * (b + c))) if (b + c) > 0 else 1.0

    print("-" * 60)
    print(f"TOTAL: Direct = {total_d}/{n} ({total_d/n*100:.1f}%) | Thinking = {total_th}/{n} ({total_th/n*100:.1f}%)")
    print(f"McNemar Discordant Pairs: b (Direct+, Think-)={b}, c (Direct-, Think+)={c} | p-value = {p_val:.4f}")
    print("=" * 60)

    out_file = REPO_ROOT / "logs" / "test_reports" / f"musr_benchmark_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "MuSR_Multistep_Soft_Reasoning",
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
    parser = argparse.ArgumentParser(description="MuSR Benchmark Runner")
    parser.add_argument("--limit", type=int, default=5, help="Problems per domain (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    args = parser.parse_args()
    run_benchmark(per_domain_limit=args.limit, seed=args.seed)
