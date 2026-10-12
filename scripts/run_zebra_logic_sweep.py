#!/usr/bin/env python3
"""
Project Lucca — ZebraLogic Parametric Difficulty Sweep Benchmark
================================================================
Evaluates the "curse of complexity" across 4 search-space tiers on logic grid puzzles:
- Tier 1: 2x2 (2 states)
- Tier 2: 3x3 (36 states)
- Tier 3: 4x4 (13,824 states)
- Tier 4: 5x5 (20,736,000 states)

Compares:
1. Arm A: Direct Non-Thinking (T=0.0)
2. Arm B: Native Extended Thinking (T=0.6, top_p=0.95)
3. Arm C: Symbolic Z3 SMT Constraint Path (Docker Sandbox)

Addresses Review Notes v7 §4.A:
- Measures whether neural mental simulation degrades with search-space size.
- Proves whether symbolic constraint solver maintains flat 100% precision.
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
class GridResult:
    problem_id: str
    tier: str
    states: int
    expected: str
    direct_pred: str | None
    direct_ok: bool
    thinking_pred: str | None
    thinking_ok: bool
    z3_pred: str | None
    z3_ok: bool
    z3_elapsed_ms: float


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


def extract_option(text: str) -> str | None:
    matches = list(re.finditer(r"\(([A-E])\)", text))
    if not matches:
        matches = list(re.finditer(r"\b([A-E])\b", text))
    return f"({matches[-1].group(1).upper()})" if matches else None


def solve_with_z3(p: dict[str, Any]) -> tuple[str | None, float]:
    """Executes certified Z3 SMT solver in Docker sandbox."""
    t0 = time.perf_counter()
    z3_code = p["z3_verification_code"]
    target_q = p["question"]
    # Extract target house from question
    m_h = re.search(r"house (\d+)", target_q)
    target_house = int(m_h.group(1)) if m_h else 1

    harness = f"""
{z3_code}

if solver.check() == z3.sat:
    m = solver.model()
    # Find which option value is at target house {target_house}
    options = {p['options']}
    res_opt = None
    for opt_letter, opt_val in options.items():
        if opt_val in house_of:
            val_h = m[house_of[opt_val]].as_long()
            if val_h == {target_house}:
                res_opt = opt_letter
                break
    print(f"SOLUTION:({{res_opt}})")
else:
    print("UNSAT")
"""
    rpc = get_docker_rpc()
    res = rpc.execute(call_id=f"z3-{time.time_ns()}", tool="run_python", args={"code": harness}, timeout_s=10.0)
    elapsed = (time.perf_counter() - t0) * 1000.0

    if res.ok and res.content:
        m = re.search(r"SOLUTION:\(([A-E])\)", str(res.content))
        if m:
            return f"({m.group(1).upper()})", elapsed
    return None, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="ZebraLogic Difficulty Sweep Benchmark")
    parser.add_argument("--samples-per-tier", type=int, default=5, help="Puzzles per tier (default: 5)")
    args = parser.parse_args()
    k: int = args.samples_per_tier

    suite_file = REPO_ROOT / "data" / "benchmarks" / "zebra_logic_grid_suite.json"
    suite = json.loads(suite_file.read_text(encoding="utf-8"))["problems"]

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: ZEBRALOGIC DIFFICULTY SWEEP BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Comparing: Direct vs Native Thinking vs Z3 SMT Solver in Docker\n", flush=True)

    results: list[GridResult] = []

    # Group by tier
    tiers = ["2x2", "3x3", "4x4", "5x5"]
    for t_name in tiers:
        tier_probs = [p for p in suite if f"_{t_name}_" in p["problem_id"]][:k]
        print(f"--- [Tier: {t_name}] ({tier_probs[0]['search_space_states']:,} states, {len(tier_probs)} problems) ---", flush=True)

        for p in tier_probs:
            prompt = p["prompt_text"]
            tgt = p["target_option"]

            # 1. Direct
            d_out = query_llm(prompt, max_tokens=512, temperature=0.0, enable_thinking=False)
            d_pred = extract_option(d_out)
            d_ok = (d_pred == tgt)

            # 2. Thinking
            th_out = query_llm(prompt, max_tokens=2048, temperature=0.6, enable_thinking=True)
            th_pred = extract_option(th_out)
            th_ok = (th_pred == tgt)

            # 3. Z3 SMT Solver in Docker
            z3_pred, z3_ms = solve_with_z3(p)
            z3_ok = (z3_pred == tgt)

            r = GridResult(
                problem_id=p["problem_id"],
                tier=t_name,
                states=p["search_space_states"],
                expected=tgt,
                direct_pred=d_pred,
                direct_ok=d_ok,
                thinking_pred=th_pred,
                thinking_ok=th_ok,
                z3_pred=z3_pred,
                z3_ok=z3_ok,
                z3_elapsed_ms=z3_ms,
            )
            results.append(r)
            print(f"[{p['problem_id']}] Direct: {'P' if d_ok else 'F'} | Think: {'P' if th_ok else 'F'} | Z3: {'P' if z3_ok else 'F'} ({z3_ms:.0f}ms)", flush=True)

    # Summary
    print("\n" + "=" * 70, flush=True)
    print("=== ZEBRALOGIC DIFFICULTY SWEEP SUMMARY ===", flush=True)
    print("=" * 70, flush=True)
    for t_name in tiers:
        t_res = [r for r in results if r.tier == t_name]
        d_p = sum(1 for r in t_res if r.direct_ok)
        th_p = sum(1 for r in t_res if r.thinking_ok)
        z3_p = sum(1 for r in t_res if r.z3_ok)
        states = t_res[0].states
        print(f"Tier {t_name} ({states:>10,d} states): Direct {d_p:2d}/{len(t_res)} ({d_p/len(t_res)*100:4.1f}%) | Think {th_p:2d}/{len(t_res)} ({th_p/len(t_res)*100:4.1f}%) | Z3 {z3_p:2d}/{len(t_res)} ({z3_p/len(t_res)*100:4.1f}%)", flush=True)

    out_dir = REPO_ROOT / "logs" / "test_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_file = out_dir / f"zebra_logic_sweep_{ts}.json"
    out_data = {
        "benchmark": "ZebraLogic_Difficulty_Sweep",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "summary": {
            "total_problems": len(results),
            "tiers": {
                t: {
                    "states": [r for r in results if r.tier == t][0].states,
                    "direct_pct": sum(1 for r in results if r.tier == t and r.direct_ok) / len([r for r in results if r.tier == t]) * 100.0,
                    "thinking_pct": sum(1 for r in results if r.tier == t and r.thinking_ok) / len([r for r in results if r.tier == t]) * 100.0,
                    "z3_pct": sum(1 for r in results if r.tier == t and r.z3_ok) / len([r for r in results if r.tier == t]) * 100.0,
                }
                for t in tiers
            },
        },
        "problems": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[Artifact Saved] -> {out_file}", flush=True)


if __name__ == "__main__":
    main()
