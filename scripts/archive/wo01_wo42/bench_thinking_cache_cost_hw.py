"""
Empirical benchmark for WO-13.3: KV-Cache Invalidation and TTFT Cost of enable_thinking.
Spec §7, D-BRAIN-05 v2, D-META-01.

Measures:
1. Warm KV cache TTFT with enable_thinking=False (routine conversational baseline).
2. Cold/invalidated TTFT with enable_thinking=True (thinking toggle penalty).
3. Recovery TTFT returning to enable_thinking=False.
Saves findings to logs/test_reports/bench_thinking_cache_hw.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from lucca.brain.llm_client import LLMClient
from lucca.core.trace import TurnTrace


def run_benchmark() -> dict[str, object]:
    client = LLMClient()
    traces: list[dict[str, object]] = []

    # Sequence of turns testing cache behavior
    turns = [
        ("warmup", "Hello Lucca, good morning.", False),
        ("routine_warm", "What time is it in Tokyo?", False),
        ("thinking_cold", "Please think step by step: why is the sky blue?", True),
        ("routine_post_thinking", "Thanks, that was helpful.", False),
        ("routine_warm_2", "Can you tell me a short joke?", False),
    ]

    print("=== WO-13.3 KV-Cache & TTFT Thinking Benchmark ===")

    for name, prompt, think_flag in turns:
        trace = TurnTrace(trace_id=f"bench-{name}")
        t_start = time.perf_counter_ns()
        first_token_ts: int | None = None
        token_count = 0
        response_text: list[str] = []

        try:
            for event in client.stream_turn(
                current_text=prompt,
                max_tokens=64,
                trace_id=trace.trace_id,
                enable_thinking=think_flag,
            ):
                if first_token_ts is None:
                    first_token_ts = time.perf_counter_ns()
                if hasattr(event, "delta") and event.delta:
                    token_count += 1
                    response_text.append(event.delta)
                elif hasattr(event, "name"):
                    token_count += 1
                    response_text.append(f"[Tool: {getattr(event, 'name', '')}]")
        except Exception as e:
            print(f"Error on {name}: {e}")
            continue

        t_end = time.perf_counter_ns()
        ttft_ms = (
            ((first_token_ts - t_start) / 1_000_000.0) if first_token_ts is not None else -1.0
        )
        total_ms = (t_end - t_start) / 1_000_000.0

        res_data = {
            "name": name,
            "prompt": prompt,
            "enable_thinking": think_flag,
            "ttft_ms": round(ttft_ms, 2),
            "total_ms": round(total_ms, 2),
            "tokens_out": token_count,
            "sample_snippet": "".join(response_text)[:80],
        }
        traces.append(res_data)
        print(
            f"[{name}] think={think_flag} -> TTFT: {ttft_ms:.1f}ms | "
            f"Total: {total_ms:.1f}ms | Tokens: {token_count}"
        )
        # Settle brief interval
        time.sleep(0.5)

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "routine_warm_ttft_ms": next(
                (t["ttft_ms"] for t in traces if t["name"] == "routine_warm"), None
            ),
            "thinking_cold_ttft_ms": next(
                (t["ttft_ms"] for t in traces if t["name"] == "thinking_cold"), None
            ),
            "routine_post_thinking_ttft_ms": next(
                (t["ttft_ms"] for t in traces if t["name"] == "routine_post_thinking"), None
            ),
        },
        "traces": traces,
    }

    out_path = Path("logs/test_reports/bench_thinking_cache_hw.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to {out_path}")
    return report


if __name__ == "__main__":
    run_benchmark()
