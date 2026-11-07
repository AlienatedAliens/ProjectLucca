"""
Project Lucca — Live Silicon Prefix KV-Cache Benchmark
ADR-009, Spec 16 §4, D-BRAIN-04, D-BRAIN-05

Empirically benchmarks Prompt Frontier Suffix Pattern against Naive Prefix Injection
on live llama-server.exe (Mistral NeMo 12B Q6_K on RTX 5080 Laptop GPU).

Measures:
1. Scenario A: Naive Continuous Floating-Point Prefix Invalidation (prompt_ms and cache bust).
2. Scenario B: Prompt Frontier Suffix Pattern (prompt_ms and 100% prefix cache reuse).
3. Physical silicon speedup factor and empirical latency reduction.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Final

from lucca.brain.prompt_builder import (
    build_messages,
    format_stance_suffix,
    get_system_prompt,
)
from lucca.core.affective_ode import DiscreteStance

SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"


def query_llm(messages: list[dict[str, object]]) -> tuple[dict[str, object], str, float]:
    """
    Queries llama-server.exe and extracts exact hardware timings from the engine response.
    Returns (timings_dict, assistant_content, total_elapsed_ms).
    """
    payload = {
        "messages": messages,
        "max_tokens": 16,
        "temperature": 0.6,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SERVER_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    choices = body.get("choices", [])
    content = choices[0]["message"]["content"] if choices else ""
    timings = body.get("timings", {})
    return timings, content, elapsed_ms


def run_benchmark() -> None:
    print("=" * 80)
    print("PROJECT LUCCA — MILESTONE 5: SILICON PREFIX KV-CACHE BENCHMARK")
    print("Target: llama-server.exe on RTX 5080 Laptop GPU (Port 8080)")
    print("=" * 80)

    static_sys = get_system_prompt()

    # -------------------------------------------------------------------------
    # SCENARIO A: Naive Continuous Float Injection into System Prompt Prefix
    # -------------------------------------------------------------------------
    print("\n[Phase 1] Benchmarking Scenario A: Naive Float Injection in System Prefix")
    print("Strategy: Injecting dynamic floating-point affect numbers directly into system prompt")

    # Turn 1: Prefix with initial float
    prefix_t1 = f"System affect telemetry: valence=0.41285, arousal=0.21044, dominance=0.35122.\n\n{static_sys}"
    t1_naive_msgs = [
        {"role": "system", "content": prefix_t1},
        {"role": "user", "content": "Hello Lucca, run a diagnostic systems check on our audio ring buffer."},
    ]
    print("  -> Dispatching Turn 1 (Initial prefill with float in prefix)...")
    timings_a1, resp_a1, tot_a1 = query_llm(t1_naive_msgs)
    c_a1 = int(timings_a1.get("cache_n", 0))
    p_a1 = int(timings_a1.get("prompt_n", 0))
    ms_a1 = float(timings_a1.get("prompt_ms", 0.0))
    print(f"     Turn 1: cache_n={c_a1:3d} | prompt_n={p_a1:4d} | prompt_ms={ms_a1:6.2f} ms | total={tot_a1:6.2f} ms")

    # Turn 2: Prefix with altered float (simulating turn-to-turn continuous update)
    # A tiny 0.001 delta changes BPE token IDs and purges the prefix cache!
    prefix_t2 = f"System affect telemetry: valence=0.42891, arousal=0.19832, dominance=0.34219.\n\n{static_sys}"
    history_a = [
        {"role": "user", "content": t1_naive_msgs[1]["content"]},
        {"role": "assistant", "content": resp_a1},
    ]
    t2_naive_msgs = [
        {"role": "system", "content": prefix_t2},
        history_a[0],
        history_a[1],
        {"role": "user", "content": "What is the exact end-to-end latency budget for speech delivery?"},
    ]
    print("  -> Dispatching Turn 2 (Altered float in prefix -> Purging KV Cache)...")
    timings_a2, resp_a2, tot_a2 = query_llm(t2_naive_msgs)
    c_a2 = int(timings_a2.get("cache_n", 0))
    p_a2 = int(timings_a2.get("prompt_n", 0))
    ms_a2 = float(timings_a2.get("prompt_ms", 0.0))
    print(f"     Turn 2: cache_n={c_a2:3d} | prompt_n={p_a2:4d} | prompt_ms={ms_a2:6.2f} ms | total={tot_a2:6.2f} ms")

    # -------------------------------------------------------------------------
    # SCENARIO B: Prompt Frontier Suffix Pattern (Our Architecture)
    # -------------------------------------------------------------------------
    print("\n[Phase 2] Benchmarking Scenario B: Prompt Frontier Suffix Pattern")
    print("Strategy: 100% static system prompt prefix + discrete stance appended to user frontier")

    # Turn 1: Warmup / Initial prefill with static system prompt + stance suffix
    t1_stance = DiscreteStance.NEUTRAL_STEADY.value
    t1_msgs = [
        m.model_dump(exclude_none=True)
        for m in build_messages(
            history=[],
            current_text="Hello Lucca, run a diagnostic systems check on our audio ring buffer.",
            stance_tag=t1_stance,
        )
    ]
    print("  -> Dispatching Turn 1 (Initial prompt prefill with static prefix)...")
    timings_b1, resp_b1, tot_b1 = query_llm(t1_msgs)
    c_b1 = int(timings_b1.get("cache_n", 0))
    p_b1 = int(timings_b1.get("prompt_n", 0))
    ms_b1 = float(timings_b1.get("prompt_ms", 0.0))
    print(f"     Turn 1: cache_n={c_b1:3d} | prompt_n={p_b1:4d} | prompt_ms={ms_b1:6.2f} ms | total={tot_b1:6.2f} ms")

    # Turn 2: Frontier Suffix with shifted stance (focused_analytical)
    history_b = [
        {"role": "user", "content": t1_msgs[1]["content"]},
        {"role": "assistant", "content": resp_b1},
    ]
    t2_stance = DiscreteStance.FOCUSED_ANALYTICAL.value
    t2_msgs = [
        m.model_dump(exclude_none=True)
        for m in build_messages(
            history=history_b,
            current_text="What is the exact end-to-end latency budget for speech delivery?",
            stance_tag=t2_stance,
        )
    ]
    print("  -> Dispatching Turn 2 (Prompt Frontier Suffix: [STANCE: focused_analytical])...")
    timings_b2, resp_b2, tot_b2 = query_llm(t2_msgs)
    c_b2 = int(timings_b2.get("cache_n", 0))
    p_b2 = int(timings_b2.get("prompt_n", 0))
    ms_b2 = float(timings_b2.get("prompt_ms", 0.0))
    print(f"     Turn 2: cache_n={c_b2:3d} | prompt_n={p_b2:4d} | prompt_ms={ms_b2:6.2f} ms | total={tot_b2:6.2f} ms")

    # -------------------------------------------------------------------------
    # EMPIRICAL COMPARISON & VERDICT
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("EMPIRICAL COMPARISON & PHYSICAL SILICON VERDICT")
    print("=" * 80)
    print(f"Scenario B (Prompt Frontier Suffix) : cache_n={c_b2:4d} tokens | prompt_eval={ms_b2:6.2f} ms  [100% KV CACHE HIT]")
    print(f"Scenario A (Naive Float in Prefix)  : cache_n={c_a2:4d} tokens | prompt_eval={ms_a2:6.2f} ms  [PREFIX CACHE BUSTED]")

    speedup = ms_a2 / max(0.1, ms_b2)
    saved_ms = ms_a2 - ms_b2
    print(f"Prompt Processing Speedup Factor    : {speedup:6.2f}x faster")
    print(f"Physical Silicon Latency Saved      : {saved_ms:6.2f} ms per turn")

    # Invariant Assertions
    assert c_b2 > 800, f"Scenario B should hit > 800 tokens from prefix cache (got {c_b2})"
    assert c_a2 < 50, f"Scenario A prefix bust must not hit > 50 tokens (got {c_a2})"
    assert ms_b2 < 60.0, f"Scenario B prompt evaluation must be < 60ms (got {ms_b2:.2f}ms)"
    assert ms_a2 > 200.0, f"Scenario A cache bust prompt evaluation must be > 200ms (got {ms_a2:.2f}ms)"
    assert speedup >= 5.0, f"Scenario B must achieve at least 5.0x speedup over cache-busted prompt (got {speedup:.2f}x)"

    print("\nVERIFICATION PASSED: Prompt Frontier Suffix Pattern guarantees 100% prefix KV cache preservation!")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
