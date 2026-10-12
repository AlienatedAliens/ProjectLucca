#!/usr/bin/env python3
"""
Project Lucca — Held-Out BBH Multi-Domain General Reasoning Suite
================================================================
Evaluates general reasoning across 5 untouched, held-out BBH tasks (10 problems each = 50 total):
1. Boolean Expressions: bbh_boolean_expressions.json
2. Date Understanding: bbh_date_understanding.json
3. Web of Lies: bbh_web_of_lies.json
4. Tracking Shuffled Objects: bbh_tracking_shuffled_objects_three_objects.json
5. Formal Fallacies: bbh_formal_fallacies.json

Addresses Review Notes v7 §4.A:
- Broader multi-domain evaluation beyond the initial 60-problem smoke suite.
- Tests whether compound reasoning lifts general multi-domain tasks.
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

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 60.0


@dataclass
class BBHProblemResult:
    task: str
    problem_id: str
    prompt: str
    expected: str
    direct_pred: str | None
    direct_ok: bool
    thinking_pred: str | None
    thinking_ok: bool
    elapsed_ms: float


def query_llm(
    prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
    enable_thinking: bool = False,
) -> str:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        content = str(choice["message"].get("content") or "").strip()
        reasoning = str(choice["message"].get("reasoning_content") or "").strip()
        return f"{content}\n{reasoning}" if reasoning else content


def extract_answer(task: str, text: str) -> str | None:
    if task in ("boolean_expressions", "web_of_lies"):
        matches = list(re.finditer(r"\b(True|False|Yes|No)\b", text, re.IGNORECASE))
        return matches[-1].group(1).capitalize() if matches else None
    elif task == "formal_fallacies":
        matches = list(re.finditer(r"\b(valid|invalid)\b", text, re.IGNORECASE))
        return matches[-1].group(1).lower() if matches else None
    else:
        # Multiple choice: (A), (B), (C), etc.
        matches = list(re.finditer(r"\(([A-E])\)", text))
        if not matches:
            matches = list(re.finditer(r"\b([A-E])\b", text))
        return f"({matches[-1].group(1).upper()})" if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Held-Out BBH Suite Benchmark")
    parser.add_argument("--samples-per-task", type=int, default=10, help="Problems per task")
    args = parser.parse_args()
    k: int = args.samples_per_task

    tasks = [
        ("boolean_expressions", "bbh_boolean_expressions.json"),
        ("date_understanding", "bbh_date_understanding.json"),
        ("web_of_lies", "bbh_web_of_lies.json"),
        ("tracking_shuffled_objects", "bbh_tracking_shuffled_objects_three_objects.json"),
        ("formal_fallacies", "bbh_formal_fallacies.json"),
    ]

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: HELD-OUT BBH MULTI-DOMAIN REASONING BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Target Server: {SERVER_URL}", flush=True)
    print(f"Sample Size: {k} per task (Total {k * len(tasks)} problems)\n", flush=True)

    results: list[BBHProblemResult] = []

    for task_name, file_name in tasks:
        p_path = REPO_ROOT / "data" / "benchmarks" / file_name
        data = json.loads(p_path.read_text(encoding="utf-8"))["examples"][:k]
        print(f"--- Running {task_name} ({len(data)} tasks) ---", flush=True)

        for idx, ex in enumerate(data, 1):
            t0 = time.perf_counter()
            inp = str(ex["input"]).strip()
            tgt = str(ex["target"]).strip()
            if task_name in ("date_understanding", "tracking_shuffled_objects"):
                clean_letter = re.sub(r"[^A-Za-z]", "", tgt).upper()
                tgt = f"({clean_letter})"

            # Direct
            d_out = query_llm(inp, max_tokens=1024, temperature=0.0, enable_thinking=False)
            d_pred = extract_answer(task_name, d_out)
            d_ok = (d_pred == tgt)

            # Thinking
            th_out = query_llm(inp, max_tokens=2048, temperature=0.6, enable_thinking=True)
            th_pred = extract_answer(task_name, th_out)
            th_ok = (th_pred == tgt)

            elapsed = (time.perf_counter() - t0) * 1000.0

            r = BBHProblemResult(
                task=task_name,
                problem_id=f"{task_name}_{idx:02d}",
                prompt=inp,
                expected=tgt,
                direct_pred=d_pred,
                direct_ok=d_ok,
                thinking_pred=th_pred,
                thinking_ok=th_ok,
                elapsed_ms=elapsed,
            )
            results.append(r)
            print(f"[{idx:02d}/{k}] {task_name[:15]:15s} | Direct: {'P' if d_ok else 'F'} | Think: {'P' if th_ok else 'F'} ({elapsed:.0f}ms)", flush=True)

    # Summary
    tot = len(results)
    d_tot = sum(1 for r in results if r.direct_ok)
    th_tot = sum(1 for r in results if r.thinking_ok)

    print("\n" + "=" * 70, flush=True)
    print("=== HELD-OUT BBH BENCHMARK SUMMARY ===", flush=True)
    print("=" * 70, flush=True)
    print(f"Direct Baseline   : {d_tot:2d}/{tot} ({d_tot/tot*100:5.1f}%)", flush=True)
    print(f"Thinking Baseline : {th_tot:2d}/{tot} ({th_tot/tot*100:5.1f}%)", flush=True)

    for task_name, _ in tasks:
        t_res = [r for r in results if r.task == task_name]
        d_p = sum(1 for r in t_res if r.direct_ok)
        th_p = sum(1 for r in t_res if r.thinking_ok)
        print(f"  - {task_name:25s}: Direct {d_p:2d}/{len(t_res)} ({d_p/len(t_res)*100:4.1f}%) | Think {th_p:2d}/{len(t_res)} ({th_p/len(t_res)*100:4.1f}%)", flush=True)

    out_dir = REPO_ROOT / "logs" / "test_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_file = out_dir / f"bbh_heldout_suite_{ts}.json"
    out_data = {
        "benchmark": "BBH_Heldout_Suite_Benchmark",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "summary": {
            "total": tot,
            "direct_passed": d_tot,
            "direct_pct": d_tot / tot * 100.0,
            "thinking_passed": th_tot,
            "thinking_pct": th_tot / tot * 100.0,
        },
        "problems": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[Artifact Saved] -> {out_file}", flush=True)


if __name__ == "__main__":
    main()
