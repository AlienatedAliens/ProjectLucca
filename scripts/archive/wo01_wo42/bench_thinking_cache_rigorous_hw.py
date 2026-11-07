"""
Rigorous Empirical Benchmark for Dynamic Thinking (When2Think) & KV-Cache Behavior.
Spec §7, D-BRAIN-05 v2, D-META-01.

Protocol:
1. Warmup turn to eliminate server cold-start artifacts.
2. Condition A: 10 consecutive turns with enable_thinking=False (baseline conversational).
3. Condition B: 10 consecutive turns with enable_thinking=True (deliberation mode).
4. Condition C: 10 consecutive turns with enable_thinking=False (post-thinking recovery).
5. All turns require genuine TokenDelta generation (reject tokens_out == 0).
6. Computes p50, mean, stddev, min, and max TTFT and generation metrics.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from lucca.brain.llm_client import LLMClient
from lucca.core.schemas import TokenDelta
from lucca.core.trace import TurnTrace, now_ns


def run_benchmark(sample_count: int = 10) -> dict[str, object]:
    client = LLMClient()
    print("=" * 80)
    print("Project Lucca — Rigorous TTFT & Thinking Mode Empirical Benchmark")
    print(f"Hardware: native llama-server on :8080 (Gemma-4-12B-Heretic Q6_K)")
    print(f"Protocol: {sample_count} samples per condition, strict tokens_out > 0 validation")
    print("=" * 80)

    # Conversational prompts that produce direct text without tool triggering
    test_prompts = [
        "What are three good habits for software engineers?",
        "Explain in two sentences what makes Python popular.",
        "Give me a short greeting for an engineering standup.",
        "What is your favorite topic in computer architecture?",
        "Describe the concept of recursion simply.",
        "Share a quick tip for debugging async Python code.",
        "What is the difference between a process and a thread?",
        "How does a cache improve memory access speeds?",
        "What is the primary benefit of version control?",
        "Say hello and tell me one interesting fact about compilers.",
    ]

    # Warmup
    print("\n[Phase 0] Warming up llama-server prefix cache...")
    warmup_trace = TurnTrace(trace_id="warmup")
    t0 = now_ns()
    warmup_tokens = 0
    for event in client.stream_turn(
        current_text="Hello Lucca, are you ready?",
        max_tokens=32,
        trace_id=warmup_trace.trace_id,
        enable_thinking=False,
        tools=[],
    ):
        if isinstance(event, TokenDelta) and event.delta:
            warmup_tokens += 1
    warmup_ttft = (now_ns() - t0) / 1_000_000.0
    print(f"[Warmup Complete] {warmup_tokens} tokens, {warmup_ttft:.1f}ms total")

    def execute_condition(
        condition_name: str,
        enable_thinking: bool,
    ) -> list[dict[str, object]]:
        print(f"\n[Running Condition: {condition_name}] enable_thinking={enable_thinking}")
        samples: list[dict[str, object]] = []

        for idx in range(sample_count):
            prompt = test_prompts[idx % len(test_prompts)]
            trace_id = f"{condition_name}-{idx + 1}"
            first_token_ns: int | None = None
            tokens: list[str] = []

            t_sent = now_ns()
            for event in client.stream_turn(
                current_text=prompt,
                max_tokens=256,
                trace_id=trace_id,
                enable_thinking=enable_thinking,
                tools=[],
            ):
                if isinstance(event, TokenDelta) and event.delta:
                    if first_token_ns is None:
                        first_token_ns = now_ns()
                    tokens.append(event.delta)

            t_done = now_ns()

            if first_token_ns is None or len(tokens) == 0:
                print(f"  Sample {idx + 1}: REJECTED (tokens_out == 0)")
                continue

            ttft_ms = (first_token_ns - t_sent) / 1_000_000.0
            total_ms = (t_done - t_sent) / 1_000_000.0
            tok_count = len(tokens)
            decode_tok_s = (
                (tok_count / ((t_done - first_token_ns) / 1_000_000_000.0))
                if (t_done > first_token_ns and tok_count > 1)
                else 0.0
            )

            sample_record = {
                "sample_id": idx + 1,
                "prompt": prompt,
                "ttft_ms": round(ttft_ms, 2),
                "total_ms": round(total_ms, 2),
                "tokens_out": tok_count,
                "tok_per_sec": round(decode_tok_s, 2),
                "snippet": "".join(tokens)[:60].replace("\n", " "),
            }
            samples.append(sample_record)
            print(
                f"  Sample {idx + 1:2d}: TTFT={ttft_ms:6.1f}ms | "
                f"Total={total_ms:6.1f}ms | Tokens={tok_count:2d} | "
                f"Decode={decode_tok_s:4.1f} tok/s | '{sample_record['snippet']}'"
            )
            time.sleep(0.2)

        return samples

    # Run the 3 conditions
    cond_a = execute_condition("Condition_A_Baseline_NoThink", enable_thinking=False)
    cond_b = execute_condition("Condition_B_Thinking_Enabled", enable_thinking=True)
    cond_c = execute_condition("Condition_C_PostThink_Recovery", enable_thinking=False)

    def compute_stats(samples: list[dict[str, object]]) -> dict[str, float]:
        if not samples:
            return {}
        ttfts = [float(s["ttft_ms"]) for s in samples]
        totals = [float(s["total_ms"]) for s in samples]
        speeds = [float(s["tok_per_sec"]) for s in samples if float(s["tok_per_sec"]) > 0]
        return {
            "count": len(samples),
            "ttft_p50_ms": round(statistics.median(ttfts), 2),
            "ttft_mean_ms": round(statistics.mean(ttfts), 2),
            "ttft_stddev_ms": round(statistics.stdev(ttfts), 2) if len(ttfts) > 1 else 0.0,
            "ttft_min_ms": round(min(ttfts), 2),
            "ttft_max_ms": round(max(ttfts), 2),
            "total_mean_ms": round(statistics.mean(totals), 2),
            "decode_mean_tok_s": round(statistics.mean(speeds), 2) if speeds else 0.0,
        }

    stats_a = compute_stats(cond_a)
    stats_b = compute_stats(cond_b)
    stats_c = compute_stats(cond_c)

    print("\n" + "=" * 80)
    print("EMPIRICAL BENCHMARK SUMMARY")
    print("=" * 80)
    print(
        f"Condition A (Warm No-Think)    : TTFT p50 = {stats_a.get('ttft_p50_ms')} ms | "
        f"Mean = {stats_a.get('ttft_mean_ms')} ms (±{stats_a.get('ttft_stddev_ms')} ms) | "
        f"Range = [{stats_a.get('ttft_min_ms')} - {stats_a.get('ttft_max_ms')}] ms"
    )
    print(
        f"Condition B (Thinking Enabled) : TTFT p50 = {stats_b.get('ttft_p50_ms')} ms | "
        f"Mean = {stats_b.get('ttft_mean_ms')} ms (±{stats_b.get('ttft_stddev_ms')} ms) | "
        f"Range = [{stats_b.get('ttft_min_ms')} - {stats_b.get('ttft_max_ms')}] ms"
    )
    print(
        f"Condition C (Post-Think Recov) : TTFT p50 = {stats_c.get('ttft_p50_ms')} ms | "
        f"Mean = {stats_c.get('ttft_mean_ms')} ms (±{stats_c.get('ttft_stddev_ms')} ms) | "
        f"Range = [{stats_c.get('ttft_min_ms')} - {stats_c.get('ttft_max_ms')}] ms"
    )

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": "RTX 5080 Laptop, llama-server b11026, Gemma-4-12B-Heretic Q6_K",
        "protocol": "10 samples per condition, pure TokenDelta text output, no tools",
        "statistics": {
            "baseline_nothink": stats_a,
            "thinking_enabled": stats_b,
            "post_think_recovery": stats_c,
        },
        "deltas": {
            "thinking_ttft_p50_delta_ms": round(
                (stats_b.get("ttft_p50_ms", 0) - stats_a.get("ttft_p50_ms", 0)), 2
            ),
            "recovery_vs_baseline_p50_delta_ms": round(
                (stats_c.get("ttft_p50_ms", 0) - stats_a.get("ttft_p50_ms", 0)), 2
            ),
        },
        "raw_samples": {
            "condition_a": cond_a,
            "condition_b": cond_b,
            "condition_c": cond_c,
        },
    }

    out_file = Path("logs/test_reports/bench_thinking_cache_hw.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nDetailed report written to: {out_file}")
    return report


if __name__ == "__main__":
    run_benchmark(sample_count=10)
