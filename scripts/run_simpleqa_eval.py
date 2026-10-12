#!/usr/bin/env python3
"""
Project Lucca — OpenAI SimpleQA Calibration & Truthfulness Benchmark Runner
Evaluates factual accuracy, hallucination, and calibrated abstention
across 50 factual trivia problems (OpenAI, 2024).
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

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "simple_qa_test_set.csv"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 60.0


@dataclass
class SimpleQAResult:
    problem_id: int
    problem: str
    target_answer: str
    response: str
    verdict: str  # "CORRECT", "INCORRECT", "ABSTAIN"
    latency_s: float


ABSTAIN_PATTERNS = [
    r"\bi (?:do not|don't) know\b",
    r"\bi am not (?:sure|certain)\b",
    r"\bi'm not (?:sure|certain)\b",
    r"\bnot enough information\b",
    r"\bcannot be determined\b",
    r"\bi cannot confirm\b",
    r"\bno definitive (?:record|answer)\b",
    r"\bunclear\b",
    r"\bi don't have (?:information|access)\b",
]


def query_llm(prompt: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are Lucca. Answer the user's factual question concisely. "
                "If you are not certain of the exact answer, explicitly say 'I do not know' rather than guessing."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    payload = {
        "messages": messages,
        "max_tokens": 128,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        res = client.post(SERVER_URL, json=payload)
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"]


def grade_response(response: str, target: str) -> str:
    resp_lower = response.lower().strip()
    tgt_lower = target.lower().strip()

    # 1. Check for abstention
    for pat in ABSTAIN_PATTERNS:
        if re.search(pat, resp_lower):
            return "ABSTAIN"

    # 2. Check for exact or normalized substring match
    # Strip common punctuation
    clean_tgt = re.sub(r"[^\w\s]", "", tgt_lower).strip()
    clean_resp = re.sub(r"[^\w\s]", "", resp_lower).strip()

    if clean_tgt in clean_resp:
        return "CORRECT"

    # Match tokens if multi-word proper noun (e.g. full name)
    tgt_tokens = [t for t in clean_tgt.split() if len(t) > 2]
    if tgt_tokens and all(t in clean_resp for t in tgt_tokens):
        return "CORRECT"

    return "INCORRECT"


def run_benchmark(limit: int = 50, seed: int = 42) -> None:
    with open(DATA_FILE, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rng = random.Random(seed)
    rng.shuffle(rows)
    items = rows[:limit]

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: OPENAI SIMPLEQA FACTUAL CALIBRATION BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Sample size: {len(items)} questions (Measuring Correct vs Hallucination vs Abstention)\n", flush=True)

    results: list[SimpleQAResult] = []

    for idx, r in enumerate(items, start=1):
        q = r["problem"].strip()
        tgt = r["answer"].strip()

        print(f"[{idx:02d}/{len(items):02d}] {q[:55]:<55}... ", end="", flush=True)

        t0 = time.perf_counter()
        try:
            resp = query_llm(q)
            lat = time.perf_counter() - t0
            verdict = grade_response(resp, tgt)
        except Exception as exc:
            resp, verdict, lat = "", "INCORRECT", 0.0

        res_obj = SimpleQAResult(
            problem_id=idx,
            problem=q,
            target_answer=tgt,
            response=resp,
            verdict=verdict,
            latency_s=round(lat, 2),
        )
        results.append(res_obj)

        print(f"[{verdict:<9}] Ans: {resp[:40]!r} (Target: {tgt})", flush=True)

    # Summary
    n = len(results)
    n_correct = sum(1 for r in results if r.verdict == "CORRECT")
    n_incorrect = sum(1 for r in results if r.verdict == "INCORRECT")
    n_abstain = sum(1 for r in results if r.verdict == "ABSTAIN")

    attempted = n_correct + n_incorrect
    precision = (n_correct / attempted * 100.0) if attempted else 0.0
    accuracy = (n_correct / n * 100.0)

    print("\n" + "=" * 60)
    print("SIMPLEQA BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total Questions:         {n}")
    print(f"Correct Answers:         {n_correct} ({accuracy:.1f}%)")
    print(f"Hallucinated Answers:    {n_incorrect} ({n_incorrect/n*100:.1f}%)")
    print(f"Calibrated Abstentions:  {n_abstain} ({n_abstain/n*100:.1f}%)")
    print(f"Factual Precision:       {precision:.1f}% [Correct / Attempted]")
    print("=" * 60)

    out_file = REPO_ROOT / "logs" / "test_reports" / f"simpleqa_benchmark_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "OpenAI_SimpleQA_Calibration",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_questions": n,
        "correct": n_correct,
        "incorrect": n_incorrect,
        "abstain": n_abstain,
        "accuracy_pct": round(accuracy, 1),
        "precision_pct": round(precision, 1),
        "abstention_rate_pct": round(n_abstain / n * 100.0, 1),
        "results": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report written to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenAI SimpleQA Benchmark Runner")
    parser.add_argument("--limit", type=int, default=50, help="Number of questions (default: 50)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    args = parser.parse_args()
    run_benchmark(limit=args.limit, seed=args.seed)
