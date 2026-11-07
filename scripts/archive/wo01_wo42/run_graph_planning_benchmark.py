#!/usr/bin/env python3
"""
Project Lucca — Parametric Graph & Classical Planning Benchmark Runner
Evaluates 40 graph and planning problems across 3 arms:
- Arm A: Direct Non-Thinking (T=0.0)
- Arm B: Native Extended Thinking (T=0.6)
- Arm C: Symbolic Execution via Docker Sandbox (pure Python / NetworkX / state search)
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
sys.path.insert(0, str(REPO_ROOT))

from lucca.sandbox.rpc import DockerRPCTransport

SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 60.0

_DOCKER_RPC: DockerRPCTransport | None = None


def get_docker_rpc() -> DockerRPCTransport:
    global _DOCKER_RPC
    if _DOCKER_RPC is None:
        _DOCKER_RPC = DockerRPCTransport(
            container_name="lucca-file-sandbox", use_direct_fallback=False
        )
        if not _DOCKER_RPC.is_container_running():
            _DOCKER_RPC.ensure_container_running()
    return _DOCKER_RPC


@dataclass
class ProblemResult:
    problem_id: str
    domain: str
    target_option: str
    direct_prediction: str | None
    direct_correct: bool
    direct_latency_ms: float
    thinking_prediction: str | None
    thinking_correct: bool
    thinking_latency_ms: float
    symbolic_prediction: str | None
    symbolic_correct: bool
    symbolic_latency_ms: float


def query_llm(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
    enable_thinking: bool = False,
) -> str:
    messages = [
        {"role": "system", "content": "You are a precise computer scientist and graph theorist. Solve the problem carefully and state your final answer as (A), (B), (C), or (D)."},
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


def extract_option(text: str) -> str | None:
    if not text:
        return None
    # Strip thinking blocks
    cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL)
    
    matches = re.findall(r"\b([A-D])\b|\(([A-D])\)", cleaned)
    if matches:
        last = matches[-1]
        letter = last[0] if last[0] else last[1]
        return f"({letter.upper()})"
    return None


def solve_symbolic(solver_code: str) -> tuple[str | None, float]:
    t0 = time.perf_counter()
    rpc = get_docker_rpc()
    res = rpc.execute(
        call_id=f"graph-{time.time_ns()}",
        tool="run_python",
        args={"code": solver_code},
        timeout_s=10.0,
    )
    elapsed = (time.perf_counter() - t0) * 1000.0
    if res.ok and res.content:
        m = re.search(r"SOLUTION:\(([A-D])\)", str(res.content))
        if m:
            return f"({m.group(1).upper()})", elapsed
    return None, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Parametric Graph & Planning Benchmark Runner")
    parser.add_argument("--limit", type=int, default=40, help="Max problems to run (default: 40)")
    args = parser.parse_args()

    suite_file = REPO_ROOT / "data" / "benchmarks" / "graph_planning_suite_40.json"
    suite = json.loads(suite_file.read_text(encoding="utf-8"))["problems"][:args.limit]

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: PARAMETRIC GRAPH & PLANNING BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Total problems: {len(suite)}\n", flush=True)

    results: list[ProblemResult] = []

    for idx, p in enumerate(suite, start=1):
        pid = p["problem_id"]
        domain = p["domain"]
        prompt = p["prompt_text"]
        tgt = p["target_option"]

        print(f"[{idx:02d}/{len(suite):02d}] {pid} ({domain})...", end="", flush=True)

        # 1. Direct
        t0 = time.perf_counter()
        try:
            d_out = query_llm(prompt, max_tokens=256, temperature=0.0, enable_thinking=False)
            d_ms = (time.perf_counter() - t0) * 1000.0
            d_pred = extract_option(d_out)
            d_ok = (d_pred == tgt)
        except Exception as exc:
            d_pred, d_ok, d_ms = None, False, 0.0

        # 2. Thinking
        t0 = time.perf_counter()
        try:
            th_out = query_llm(prompt, max_tokens=1536, temperature=0.6, enable_thinking=True)
            th_ms = (time.perf_counter() - t0) * 1000.0
            th_pred = extract_option(th_out)
            th_ok = (th_pred == tgt)
        except Exception as exc:
            th_pred, th_ok, th_ms = None, False, 0.0

        # 3. Symbolic execution in Docker
        sym_pred, sym_ms = solve_symbolic(p["solver_code"])
        sym_ok = (sym_pred == tgt)

        r = ProblemResult(
            problem_id=pid,
            domain=domain,
            target_option=tgt,
            direct_prediction=d_pred,
            direct_correct=d_ok,
            direct_latency_ms=round(d_ms, 1),
            thinking_prediction=th_pred,
            thinking_correct=th_ok,
            thinking_latency_ms=round(th_ms, 1),
            symbolic_prediction=sym_pred,
            symbolic_correct=sym_ok,
            symbolic_latency_ms=round(sym_ms, 1),
        )
        results.append(r)

        print(f" Direct={'PASS' if d_ok else 'FAIL'} | Think={'PASS' if th_ok else 'FAIL'} | Docker={'PASS' if sym_ok else 'FAIL'}", flush=True)

    # Domain aggregates
    domains = ["shortest_path", "topological_sort", "bipartite_check", "blocksworld_planning"]
    print("\n" + "=" * 60)
    print("AGGREGATE BENCHMARK RESULTS")
    print("=" * 60)
    domain_stats = {}
    for dom in domains:
        dom_res = [r for r in results if r.domain == dom]
        if not dom_res:
            continue
        d_acc = sum(1 for r in dom_res if r.direct_correct) / len(dom_res) * 100
        th_acc = sum(1 for r in dom_res if r.thinking_correct) / len(dom_res) * 100
        sym_acc = sum(1 for r in dom_res if r.symbolic_correct) / len(dom_res) * 100
        domain_stats[dom] = {
            "total": len(dom_res),
            "direct_pct": round(d_acc, 1),
            "thinking_pct": round(th_acc, 1),
            "symbolic_pct": round(sym_acc, 1),
        }
        print(f"Domain [{dom}] (n={len(dom_res)}): Direct={d_acc:.1f}% | Think={th_acc:.1f}% | Docker={sym_acc:.1f}%")

    total_d = sum(1 for r in results if r.direct_correct)
    total_th = sum(1 for r in results if r.thinking_correct)
    total_sym = sum(1 for r in results if r.symbolic_correct)
    n = len(results)

    print("-" * 60)
    print(f"TOTAL: Direct = {total_d}/{n} ({total_d/n*100:.1f}%) | Thinking = {total_th}/{n} ({total_th/n*100:.1f}%) | Docker Symbolic = {total_sym}/{n} ({total_sym/n*100:.1f}%)")
    print("=" * 60)

    # Save artifact
    out_dir = REPO_ROOT / "logs" / "test_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"graph_planning_benchmark_{int(time.time())}.json"
    payload = {
        "benchmark": "parametric_graph_planning_suite_40",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_problems": n,
        "direct_passed": total_d,
        "direct_pct": round(total_d / n * 100, 1),
        "thinking_passed": total_th,
        "thinking_pct": round(total_th / n * 100, 1),
        "symbolic_passed": total_sym,
        "symbolic_pct": round(total_sym / n * 100, 1),
        "domain_stats": domain_stats,
        "results": [asdict(r) for r in results],
    }
    report_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report written to: {report_file}")


if __name__ == "__main__":
    main()
