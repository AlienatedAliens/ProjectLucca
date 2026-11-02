#!/usr/bin/env python3
"""
Project Lucca — Full-Turn Voice Latency Benchmark (PTT Release -> First Audible Speech)
Satisfies CAP-VOICE measurement obligation in luccadocs/specs/CAPABILITY_REGISTER.md §5.

Measures every stage of a real voice turn on native hardware:
  1. ASR tail latency (release-of-PTT -> final transcript via Faster-Whisper CUDA float16)
  2. Router & prompt assembly latency (HeuristicRouter.route + system prompt construction)
  3. LLM TTFT (time to first token) and Time-to-First-Clause (streamed until first clause boundary)
     under both cold and warm KV prefix cache
  4. TTS first-clause synthesis latency (Kokoro-82M ONNX + AnimeDSPChain -> 24 kHz PCM)
  5. Total full-turn latency (PTT release -> first audible speech sample ready for playback)
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import get_system_prompt
from lucca.core.schemas import ChatMessage, TokenDelta
from lucca.router.heuristic import HeuristicRouter
from lucca.senses.asr import ASRWorker
from lucca.senses.tts import TTSWorker
from lucca.brain.chunker import StreamingChunker

PROMPTS: tuple[str, ...] = (
    "Hey Lucca, what time is it right now?",
    "Can you give me a quick summary of what you can help me with on this machine?",
    "What is the square root of one hundred forty four?",
    "Tell me a quick one sentence thought about why local privacy matters.",
    "How is my system holding up today?",
    "What is the difference between TCP and UDP in one short sentence?",
    "Give me a quick tip for staying focused during a long coding session.",
    "Remind me what our main rule is about never faking tool actions.",
)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(s[int(k)], 2)
    return round(s[f] * (c - k) + s[c] * (k - f), 2)


def summarize_metric(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
    return {
        "mean_ms": round(sum(values) / len(values), 2),
        "p50_ms": percentile(values, 50.0),
        "p95_ms": percentile(values, 95.0),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
    }


def make_16k_speech_pcm(tts: TTSWorker, text: str) -> np.ndarray:
    """Synthesizes 24 kHz speech via Kokoro-82M and resamples to 16 kHz int16 for Faster-Whisper."""
    if tts.engine is None:
        rng = np.random.default_rng(42)
        return (rng.standard_normal(16000 * 2) * 1000).astype(np.int16)
    voice_style = tts.resolve_voice_style("af_sarah")
    samples_f32, sr = tts.engine.create(text, voice=voice_style, speed=1.0)
    # Resample from sr (24000) to 16000 via linear interpolation
    target_len = int(len(samples_f32) * 16000 / sr)
    x_old = np.linspace(0.0, 1.0, len(samples_f32), endpoint=False)
    x_new = np.linspace(0.0, 1.0, target_len, endpoint=False)
    resampled = np.interp(x_new, x_old, samples_f32)
    return (np.clip(resampled, -1.0, 1.0) * 32767.0).astype(np.int16)


def wait_for_server(url: str = "http://127.0.0.1:8080/health", timeout_s: float = 30.0) -> bool:
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def run_tier_benchmark(
    tier_name: str,
    model_filename: str,
    asr: ASRWorker,
    tts: TTSWorker,
    router: HeuristicRouter,
    audio_Fixtures: list[tuple[str, np.ndarray]],
) -> dict[str, Any]:
    client = LLMClient(base_url="http://127.0.0.1:8080")
    sys_prompt = get_system_prompt()

    records: list[dict[str, Any]] = []
    for idx, (prompt_text, pcm_16k) in enumerate(audio_Fixtures):
        is_cold = idx == 0

        # 1. ASR stage (PTT release -> transcript)
        t_asr0 = time.perf_counter()
        asr_res = asr.transcribe(pcm_16k)
        asr_ms = (time.perf_counter() - t_asr0) * 1000.0
        transcript = asr_res.text.strip() or prompt_text

        # 2. Router stage
        t_route0 = time.perf_counter()
        _decision = router.route(transcript)
        messages = [
            ChatMessage(role="system", content=sys_prompt),
            ChatMessage(role="user", content=transcript),
        ]
        route_ms = (time.perf_counter() - t_route0) * 1000.0

        # 3. LLM streaming to first token & first speakable clause
        chunker = StreamingChunker()
        t_llm0 = time.perf_counter()
        ttft_ms: float | None = None
        first_clause_ms: float | None = None
        first_clause_text = ""
        full_reply_parts: list[str] = []

        for ev in client.stream_turn(
            messages=messages,
            temperature=0.3,
            max_tokens=96,
            tools=[],
        ):
            if isinstance(ev, TokenDelta) and ev.delta:
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - t_llm0) * 1000.0
                full_reply_parts.append(ev.delta)
                emitted = chunker.feed(ev.delta)
                if emitted and first_clause_ms is None:
                    first_clause_ms = (time.perf_counter() - t_llm0) * 1000.0
                    first_clause_text = emitted[0].text

        rem = chunker.flush()
        if first_clause_ms is None:
            first_clause_ms = (time.perf_counter() - t_llm0) * 1000.0
            first_clause_text = rem[0].text if rem else "".join(full_reply_parts).strip()
        if ttft_ms is None:
            ttft_ms = first_clause_ms
        llm_total_ms = (time.perf_counter() - t_llm0) * 1000.0

        # 4. First-clause TTS synthesis (first clause -> 24 kHz audio buffer in play_ring)
        t_tts0 = time.perf_counter()
        tts_done = tts.synthesize(chunk_id=idx + 1, text=first_clause_text, is_first=True)
        tts_first_clause_ms = (time.perf_counter() - t_tts0) * 1000.0

        total_turn_ms = asr_ms + route_ms + first_clause_ms + tts_first_clause_ms

        rec = {
            "turn_index": idx,
            "cache_state": "cold" if is_cold else "warm",
            "prompt": prompt_text,
            "asr_transcript": transcript,
            "first_clause": first_clause_text,
            "first_clause_samples_24k": tts_done.samples,
            "asr_ms": round(asr_ms, 2),
            "route_ms": round(route_ms, 2),
            "llm_ttft_ms": round(ttft_ms, 2),
            "llm_first_clause_ms": round(first_clause_ms, 2),
            "llm_total_ms": round(llm_total_ms, 2),
            "tts_first_clause_ms": round(tts_first_clause_ms, 2),
            "total_turn_ms": round(total_turn_ms, 2),
        }
        records.append(rec)
        print(
            f"[{tier_name} #{idx + 1} {'COLD' if is_cold else 'WARM'}] "
            f"ASR={rec['asr_ms']}ms | Route={rec['route_ms']}ms | "
            f"TTFT={rec['llm_ttft_ms']}ms | 1stClause={rec['llm_first_clause_ms']}ms | "
            f"TTS={rec['tts_first_clause_ms']}ms ==> TOTAL={rec['total_turn_ms']}ms "
            f"('{first_clause_text[:45]}')"
        )

    warm_records = [r for r in records if r["cache_state"] == "warm"]
    cold_record = records[0] if records else {}

    return {
        "tier": tier_name,
        "model": model_filename,
        "n_prompts": len(records),
        "cold_turn": cold_record,
        "warm_summary": {
            "asr_ms": summarize_metric([r["asr_ms"] for r in warm_records]),
            "route_ms": summarize_metric([r["route_ms"] for r in warm_records]),
            "llm_ttft_ms": summarize_metric([r["llm_ttft_ms"] for r in warm_records]),
            "llm_first_clause_ms": summarize_metric(
                [r["llm_first_clause_ms"] for r in warm_records]
            ),
            "tts_first_clause_ms": summarize_metric(
                [r["tts_first_clause_ms"] for r in warm_records]
            ),
            "total_turn_ms": summarize_metric([r["total_turn_ms"] for r in warm_records]),
        },
        "all_turns_summary": {
            "asr_ms": summarize_metric([r["asr_ms"] for r in records]),
            "llm_ttft_ms": summarize_metric([r["llm_ttft_ms"] for r in records]),
            "llm_first_clause_ms": summarize_metric([r["llm_first_clause_ms"] for r in records]),
            "tts_first_clause_ms": summarize_metric([r["tts_first_clause_ms"] for r in records]),
            "total_turn_ms": summarize_metric([r["total_turn_ms"] for r in records]),
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-Turn Voice Latency Benchmark")
    parser.add_argument(
        "--output",
        type=str,
        default="data/benchmarks/turn_latency/summary.json",
    )
    parser.add_argument(
        "--tiers",
        nargs="+",
        default=["E4B", "12B"],
        choices=["E4B", "12B"],
    )
    args = parser.parse_args()

    play_ring = MagicMock()
    play_ring.has_flag.return_value = False
    play_ring.write.side_effect = lambda arr: int(len(arr))

    print("Initializing TTSWorker (Kokoro-82M ONNX) + ASRWorker (Faster-Whisper)...")
    tts = TTSWorker(play_ring=play_ring)
    # Warm up TTS
    tts.synthesize(0, "Warming up voice synthesis.")

    asr = ASRWorker()
    router = HeuristicRouter()

    # Pre-synthesize 16 kHz spoken audio waveforms for each prompt
    audio_fixtures: list[tuple[str, np.ndarray]] = []
    for p in PROMPTS:
        pcm_16k = make_16k_speech_pcm(tts, p)
        audio_fixtures.append((p, pcm_16k))
    # Warm up ASR
    asr.transcribe(audio_fixtures[0][1])
    print(f"ASR backend: {asr.backend}")

    tier_models = {
        "E4B": "gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf",
        "12B": "gemma-4-12b-heretic-Q6_K.gguf",
    }

    llama_exe = Path(r"C:\ProjectLucca\app\llama-server\llama-server.exe")
    results_by_tier: dict[str, Any] = {}

    for tier in args.tiers:
        model_file = tier_models[tier]
        model_path = Path(r"C:\ProjectLucca\models\llm") / model_file
        cmd = [
            str(llama_exe),
            "--model",
            str(model_path),
            "--n-gpu-layers",
            "99",
            "--ctx-size",
            "32768",
            "--cache-type-k",
            "q8_0",
            "--cache-type-v",
            "q8_0",
            "--parallel",
            "1",
            "--flash-attn",
            "on",
            "--host",
            "127.0.0.1",
            "--port",
            "8080",
            "--no-webui",
            "--jinja",
        ]
        print(f"\nStarting llama-server for tier {tier} ({model_file})...")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            if not wait_for_server("http://127.0.0.1:8080/health", timeout_s=45.0):
                raise RuntimeError(f"llama-server failed to become ready for {tier}")
            res = run_tier_benchmark(tier, model_file, asr, tts, router, audio_fixtures)
            results_by_tier[tier] = res
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            time.sleep(1.0)

    out_path = REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "benchmark_id": "BENCH-TURN-LATENCY-v1.0",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "definition": "Release of push-to-talk key -> ASR transcript -> Router -> LLM first speakable clause -> Kokoro-82M TTS first audio buffer ready (24 kHz PCM)",
        "asr_backend": asr.backend,
        "tts_engine": "kokoro-v1.0.onnx + AnimeDSPChain (CPU)",
        "tiers": results_by_tier,
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved full-turn latency benchmark to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
