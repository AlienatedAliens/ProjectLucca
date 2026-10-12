#!/usr/bin/env python3
"""
Project Lucca — GPQA Diamond Benchmark Runner
Evaluates graduate-level Google-proof scientific reasoning (Rein et al., 2023)
across Chemistry, Physics, and Biology.
Direct ($T=0.0$) vs Native Extended Thinking ($T=0.6$).
"""

from __future__ import annotations

import argparse
import csv
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

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "gpqa_diamond.csv"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 90.0


@dataclass
class GPQAResult:
    record_id: str
    domain: str
    subdomain: str
    question: str
    choices: dict[str, str]
    correct_letter: str
    direct_prediction: str | None
    direct_correct: bool
    direct_latency_s: float
    thinking_prediction: str | None
    thinking_correct: bool
    thinking_latency_s: float


def load_gpqa_dataset(sample_limit: int = 50, seed: int = 42) -> list[dict[str, Any]]:
    with open(DATA_FILE, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Stratified sampling by domain
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        dom = r["High-level domain"]
        by_domain.setdefault(dom, []).append(r)

    rng = random.Random(seed)
    sampled: list[dict[str, Any]] = []

    # Proportional allocation
    total_rows = len(rows)
    for dom, dom_rows in sorted(by_domain.items()):
        dom_k = max(1, round(len(dom_rows) / total_rows * sample_limit))
        rng.shuffle(dom_rows)
        sampled.extend(dom_rows[:dom_k])

    sampled = sampled[:sample_limit]
    return sampled


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
                "You are an expert scientist with a PhD in physics, chemistry, and biology. "
                "Solve the scientific question carefully and conclude with your final answer as (A), (B), (C), or (D)."
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


def extract_answer(text: str) -> str | None:
    if not text:
        return None
    # Strip thoughts
    cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    # Search for explicit conclusion phrases first
    m = re.search(r"(?:answer|choice|option)(?:\s+is)?[:\s]*\(?([A-D])\)?", cleaned, re.IGNORECASE)
    if m:
        return f"({m.group(1).upper()})"

    # Fallback: find all standalone letters
    matches = re.findall(r"\b([A-D])\b|\(([A-D])\)", cleaned)
    if matches:
        last = matches[-1]
        letter = last[0] if last[0] else last[1]
        return f"({letter.upper()})"
    return None


def run_benchmark(limit: int = 50, seed: int = 42) -> None:
    dataset = load_gpqa_dataset(sample_limit=limit, seed=seed)
    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: GPQA DIAMOND SCIENTIFIC REASONING BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Stratified Sample: {len(dataset)} items across Chemistry, Physics, Biology\n", flush=True)

    results: list[GPQAResult] = []

    for idx, row in enumerate(dataset, start=1):
        rec_id = row.get("Record ID", f"GPQA-{idx}")
        domain = row.get("High-level domain", "Unknown")
        subdomain = row.get("Subdomain", "")
        q_text = row["Question"].strip()
        correct_ans = row["Correct Answer"].strip()
        distractors = [
            row["Incorrect Answer 1"].strip(),
            row["Incorrect Answer 2"].strip(),
            row["Incorrect Answer 3"].strip(),
        ]

        # Deterministic shuffle based on record_id
        q_rng = random.Random(f"{rec_id}-{seed}")
        all_choices = [correct_ans] + distractors
        q_rng.shuffle(all_choices)

        letters = ["(A)", "(B)", "(C)", "(D)"]
        choices_map = {letters[i]: all_choices[i] for i in range(4)}
        correct_letter = letters[all_choices.index(correct_ans)]

        prompt = (
            f"Question:\n{q_text}\n\n"
            f"Choices:\n"
            + "\n".join(f"{ltr} {txt}" for ltr, txt in choices_map.items())
            + "\n\nConclude with your final answer as (A), (B), (C), or (D)."
        )

        print(f"[{idx:02d}/{len(dataset):02d}] [{domain}] {rec_id}... ", end="", flush=True)

        # 1. Direct
        t0 = time.perf_counter()
        try:
            d_out = query_llm(prompt, max_tokens=2048, temperature=0.0, enable_thinking=False)
            d_sec = time.perf_counter() - t0
            d_pred = extract_answer(d_out)
            d_ok = (d_pred == correct_letter)
        except Exception as exc:
            d_pred, d_ok, d_sec = None, False, 0.0

        # 2. Thinking
        t0 = time.perf_counter()
        try:
            th_out = query_llm(prompt, max_tokens=2048, temperature=0.6, enable_thinking=True)
            th_sec = time.perf_counter() - t0
            th_pred = extract_answer(th_out)
            th_ok = (th_pred == correct_letter)
        except Exception as exc:
            th_pred, th_ok, th_sec = None, False, 0.0

        r = GPQAResult(
            record_id=rec_id,
            domain=domain,
            subdomain=subdomain,
            question=q_text,
            choices=choices_map,
            correct_letter=correct_letter,
            direct_prediction=d_pred,
            direct_correct=d_ok,
            direct_latency_s=round(d_sec, 2),
            thinking_prediction=th_pred,
            thinking_correct=th_ok,
            thinking_latency_s=round(th_sec, 2),
        )
        results.append(r)

        print(f"Direct={'PASS' if d_ok else 'FAIL'} ({d_pred}) | Think={'PASS' if th_ok else 'FAIL'} ({th_pred}) [Target: {correct_letter}]", flush=True)

    # Domain Breakdown
    print("\n" + "=" * 60)
    print("DOMAIN ACCURACY BREAKDOWN")
    print("=" * 60)
    domains = sorted(list(set(r.domain for r in results)))
    for dom in domains:
        dom_res = [r for r in results if r.domain == dom]
        d_acc = sum(1 for r in dom_res if r.direct_correct) / len(dom_res) * 100
        th_acc = sum(1 for r in dom_res if r.thinking_correct) / len(dom_res) * 100
        print(f"{dom:<15} (n={len(dom_res):2d}): Direct = {d_acc:5.1f}% | Thinking = {th_acc:5.1f}%")

    total_d = sum(1 for r in results if r.direct_correct)
    total_th = sum(1 for r in results if r.thinking_correct)
    n = len(results)
    print("-" * 60)
    print(f"TOTAL: Direct = {total_d}/{n} ({total_d/n*100:.1f}%) | Thinking = {total_th}/{n} ({total_th/n*100:.1f}%)")
    print("=" * 60)

    out_file = REPO_ROOT / "logs" / "test_reports" / f"gpqa_diamond_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "GPQA_Diamond_Stratified",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_problems": n,
        "direct_passed": total_d,
        "direct_pct": round(total_d / n * 100, 1),
        "thinking_passed": total_th,
        "thinking_pct": round(total_th / n * 100, 1),
        "results": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report written to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPQA Diamond Benchmark Runner")
    parser.add_argument("--limit", type=int, default=30, help="Number of questions (default: 30)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    args = parser.parse_args()
    run_benchmark(limit=args.limit, seed=args.seed)
