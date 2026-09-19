"""
Project Lucca — Comparative ASR Benchmark: CUDA vs CPU, Greedy vs Beam 5
Measures faster-whisper distil-small.en:
- CUDA float16 vs CPU int8
- beam_size=1 (greedy) vs beam_size=5 (beam search)
- VRAM delta on NVIDIA RTX 5080 Laptop GPU
- Across real fixture clips of varying lengths
"""

import json
import os
import subprocess
import time
from pathlib import Path
import numpy as np

# Ensure cublas from llama-server is on PATH for CUDA faster-whisper
os.environ["PATH"] = r"C:\ProjectLucca\app\llama-server;" + os.environ["PATH"]
import faster_whisper


def get_vram_mb():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
            text=True
        ).strip()
        used, free = [int(x.strip()) for x in out.split(",")]
        return {"used_mib": used, "free_mib": free}
    except Exception as e:
        return {"error": str(e)}


def benchmark():
    output_path = Path("data/eval/milestone1_baseline/asr_cuda_cpu_bench_raw.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    vram_before = get_vram_mb()
    print(f"[VRAM] Before Whisper: {vram_before}")

    clips = [
        {"path": "tests/fixtures/audio_tool_calls/calc_01.wav", "label": "calc_01 (short command)"},
        {"path": "tests/fixtures/audio_tool_calls/browser_01.wav", "label": "browser_01 (short command)"},
        {"path": "tests/fixtures/conversational_speech.wav", "label": "conversational_speech (medium speech)"},
        {"path": "tests/fixtures/conversational_hello.wav", "label": "conversational_hello (medium speech)"},
    ]

    results = {
        "timestamp": time.time(),
        "vram_before_model_load": vram_before,
        "configurations": {}
    }

    # Configuration 1: CUDA float16, beam_size=5 & beam_size=1
    print("\n" + "=" * 60)
    print("  LOADING CUDA MODEL (distil-small.en, float16)")
    print("=" * 60)
    t0_load = time.perf_counter()
    cuda_model = faster_whisper.WhisperModel(
        "distil-small.en",
        device="cuda",
        compute_type="float16"
    )
    cuda_load_time_s = time.perf_counter() - t0_load
    vram_after_cuda_load = get_vram_mb()
    vram_cuda_delta_mib = vram_after_cuda_load["used_mib"] - vram_before["used_mib"]
    print(f"[CUDA] Loaded in {cuda_load_time_s:.2f}s. VRAM after load: {vram_after_cuda_load} (Delta: +{vram_cuda_delta_mib} MiB)")

    results["vram_after_cuda_load"] = vram_after_cuda_load
    results["vram_cuda_delta_mib"] = vram_cuda_delta_mib

    # Warmup CUDA
    print("[CUDA] Warming up...")
    list(cuda_model.transcribe(clips[0]["path"], beam_size=1))
    vram_after_cuda_warmup = get_vram_mb()
    results["vram_after_cuda_warmup"] = vram_after_cuda_warmup
    print(f"[CUDA] VRAM after warmup/first inference: {vram_after_cuda_warmup} (Total Delta from baseline: +{vram_after_cuda_warmup['used_mib'] - vram_before['used_mib']} MiB)")

    for beam in [1, 5]:
        cfg_key = f"cuda_float16_beam_{beam}"
        print(f"\n--- Testing CUDA (beam_size={beam}) ---")
        cfg_results = {}
        for clip in clips:
            p = clip["path"]
            latencies = []
            transcripts = []
            # 5 runs per clip
            for run_i in range(5):
                t0 = time.perf_counter()
                segments, info = cuda_model.transcribe(p, beam_size=beam, language="en")
                text = " ".join([s.text for s in segments]).strip()
                lat_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(lat_ms)
                transcripts.append(text)
            audio_dur_s = info.duration
            mean_ms = float(np.mean(latencies))
            p50_ms = float(np.percentile(latencies, 50))
            p95_ms = float(np.percentile(latencies, 95))
            min_ms = float(np.min(latencies))
            max_ms = float(np.max(latencies))
            rtf = (mean_ms / 1000.0) / audio_dur_s if audio_dur_s > 0 else 0
            cfg_results[clip["label"]] = {
                "audio_duration_s": round(audio_dur_s, 2),
                "transcript": transcripts[0],
                "p50_ms": round(p50_ms, 2),
                "mean_ms": round(mean_ms, 2),
                "p95_ms": round(p95_ms, 2),
                "min_ms": round(min_ms, 2),
                "max_ms": round(max_ms, 2),
                "real_time_factor": round(rtf, 4),
                "latencies_ms": [round(x, 2) for x in latencies],
            }
            print(f"[{clip['label']}] P50: {p50_ms:.1f}ms | Mean: {mean_ms:.1f}ms | RTF: {rtf:.4f} | Text: '{transcripts[0]}'")
        results["configurations"][cfg_key] = cfg_results

    # Free CUDA model reference
    del cuda_model
    import gc
    gc.collect()

    # Configuration 2: CPU int8, cpu_threads=6, beam_size=5 & beam_size=1
    print("\n" + "=" * 60)
    print("  LOADING CPU MODEL (distil-small.en, int8, cpu_threads=6)")
    print("=" * 60)
    t0_load = time.perf_counter()
    cpu_model = faster_whisper.WhisperModel(
        "distil-small.en",
        device="cpu",
        compute_type="int8",
        cpu_threads=6
    )
    cpu_load_time_s = time.perf_counter() - t0_load
    print(f"[CPU] Loaded in {cpu_load_time_s:.2f}s.")

    # Warmup CPU
    list(cpu_model.transcribe(clips[0]["path"], beam_size=1))

    for beam in [1, 5]:
        cfg_key = f"cpu_int8_beam_{beam}"
        print(f"\n--- Testing CPU (beam_size={beam}) ---")
        cfg_results = {}
        for clip in clips:
            p = clip["path"]
            latencies = []
            transcripts = []
            for run_i in range(5):
                t0 = time.perf_counter()
                segments, info = cpu_model.transcribe(p, beam_size=beam, language="en")
                text = " ".join([s.text for s in segments]).strip()
                lat_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(lat_ms)
                transcripts.append(text)
            audio_dur_s = info.duration
            mean_ms = float(np.mean(latencies))
            p50_ms = float(np.percentile(latencies, 50))
            p95_ms = float(np.percentile(latencies, 95))
            min_ms = float(np.min(latencies))
            max_ms = float(np.max(latencies))
            rtf = (mean_ms / 1000.0) / audio_dur_s if audio_dur_s > 0 else 0
            cfg_results[clip["label"]] = {
                "audio_duration_s": round(audio_dur_s, 2),
                "transcript": transcripts[0],
                "p50_ms": round(p50_ms, 2),
                "mean_ms": round(mean_ms, 2),
                "p95_ms": round(p95_ms, 2),
                "min_ms": round(min_ms, 2),
                "max_ms": round(max_latencies := max(latencies), 2),
                "real_time_factor": round(rtf, 4),
                "latencies_ms": [round(x, 2) for x in latencies],
            }
            print(f"[{clip['label']}] P50: {p50_ms:.1f}ms | Mean: {mean_ms:.1f}ms | RTF: {rtf:.4f} | Text: '{transcripts[0]}'")
        results["configurations"][cfg_key] = cfg_results

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n[DONE] Results written to {output_path.resolve()}")
    return results


if __name__ == "__main__":
    benchmark()
