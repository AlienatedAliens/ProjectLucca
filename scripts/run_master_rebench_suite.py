"""
Project Lucca — Master Re-Benchmarking Orchestrator (v1.40)
===========================================================
Executes the Canonical Representative Evaluation Splits across all 24
benchmark families and 3 resident model tiers (12B, E4B, E2B).

Features:
- Real-time unbuffered stdout streaming per task
- Configurable evaluation arms (--arms all, compound, direct_compound)
- Generous timeout budgets (1800s for full multi-arm evaluations)
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path("C:/Projects/ProjectLucca")
PYTHON_EXE = ROOT / ".venv" / "Scripts" / "python.exe"
REPORTS_DIR = ROOT / "logs" / "test_reports" / "rebench_master_v140"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Ensure UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def fetch_runtime_environment(base_url: str = "http://127.0.0.1:8080") -> dict[str, object]:
    """Captures live llama-server endpoint props and system hardware for full audit provenance."""
    env_info: dict[str, object] = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "llama_server_url": base_url,
    }
    # 1. Probe llama-server /props
    try:
        import urllib.request
        req = urllib.request.Request(f"{base_url}/props")
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        env_info["model_path"] = data.get("model_path", "")
        env_info["model_alias"] = data.get("model_alias", "")
        env_info["total_slots"] = data.get("total_slots", 1)
        gen = data.get("default_generation_settings", {})
        env_info["n_ctx"] = gen.get("n_ctx", 32768)
        env_info["build_info"] = data.get("build_info", "")
    except Exception as exc:
        env_info["props_error"] = str(exc)

    # 2. Probe GPU hardware
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            env_info["gpu_hardware"] = res.stdout.strip()
    except Exception as exc:
        env_info["gpu_error"] = str(exc)

    # 3. Pinned server flags convention
    env_info["server_pinned_flags"] = {
        "cache_type_k": "f16",
        "cache_type_v": "f16",
        "parallel_slots": env_info.get("total_slots", 1),
        "flash_attention": "on",
        "n_gpu_layers": 99,
        "mmproj": "none",
    }
    return env_info


def run_benchmark_command(name: str, args: list[str], timeout_s: float = 1800.0) -> tuple[bool, float, str]:
    cmd = [str(PYTHON_EXE), *args]
    print(f"\n{'='*78}\n[START BENCHMARK] {name}\nCommand: {' '.join(cmd)}\nTimeout: {timeout_s:.0f}s\n{'='*78}", flush=True)
    t0 = time.perf_counter()
    lines_captured: list[str] = []

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        deadline = time.time() + timeout_s
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                lines_captured.append(line.rstrip())
            elif proc.poll() is not None:
                break
            else:
                if time.time() > deadline:
                    proc.kill()
                    print(f"\n[TIMEOUT] {name} exceeded timeout limit of {timeout_s:.0f}s", flush=True)
                    return False, time.perf_counter() - t0, "TIMEOUT"
                time.sleep(0.05)

        proc.wait()
        elapsed = time.perf_counter() - t0
        ok = proc.returncode == 0
        tail_snip = "\n".join(lines_captured[-10:])
        status_str = "PASS" if ok else f"FAIL (exit {proc.returncode})"
        print(f"\n[FINISHED] {name} in {elapsed:.1f}s -> {status_str}", flush=True)
        return ok, elapsed, tail_snip

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"\n[ERROR] {name} failed with exception: {exc}", flush=True)
        return False, elapsed, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Master Re-Benchmarking Orchestrator")
    parser.add_argument("--tier", choices=["26B", "12B", "E4B", "E2B", "26b", "12b", "e4b", "e2b"], default="26B", help="Active model tier")
    parser.add_argument(
        "--arms",
        choices=["all", "compound", "direct_compound"],
        default="all",
        help="Evaluation arms: 'all' (Direct+Thinking+Compound), 'compound' (Compound only), or 'direct_compound'",
    )
    parser.add_argument("--repeats", type=int, default=1, help="Repetitions per suite for non-deterministic sampling")
    parser.add_argument("--start-phase", type=int, default=1, help="Starting phase (1-6)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without running")
    args = parser.parse_args()

    tier_tag = args.tier.upper()
    print(f"\n{'#'*78}\nPROJECT LUCCA: MASTER RE-BENCHMARKING CAMPAIGN (TIER: {tier_tag} | ARMS: {args.arms} | REPEATS: {args.repeats})\n{'#'*78}", flush=True)

    runtime_env = fetch_runtime_environment()
    print(f"[*] Live Server Model: {runtime_env.get('model_path', 'unknown')}")
    print(f"[*] GPU Hardware:     {runtime_env.get('gpu_hardware', 'unknown')}")
    print(f"[*] Server Context:    {runtime_env.get('n_ctx', 'unknown')} | Slots: {runtime_env.get('total_slots', 'unknown')}\n", flush=True)

    sealed_timeout = 1800.0 if args.arms == "all" else 400.0

    # Format: (phase, name, split_type, cmd_args, timeout_s)
    # Per Review Notes v11: All current test suites are formally classified as DEV / Curated Regression Splits
    suite_definitions: list[tuple[int, str, str, list[str], float]] = [
        # Phase 1: Exact Symbolic & Neurosymbolic
        (1, "Curated Parametric Hard Suite (N=25)", "DEV", ["scripts/run_sealed_parametric_suite.py", "--dataset", "data/benchmarks/sealed_parametric_v139_hard_suite.json", "--limit-per-suite", "5", "--model-tag", f"{tier_tag}_REBENCH", "--arms", args.arms], sealed_timeout),
        (1, "Curated Parametric Standard Suite (N=25)", "DEV", ["scripts/run_sealed_parametric_suite.py", "--dataset", "data/benchmarks/sealed_parametric_v138_suite.json", "--limit-per-suite", "5", "--model-tag", f"{tier_tag}_REBENCH", "--arms", args.arms], sealed_timeout),
        (1, "ZebraLogic Difficulty Sweep (8 Grids)", "DEV", ["scripts/run_zebra_logic_sweep.py", "--samples-per-tier", "5"], 1500.0),
        (1, "AIME 2024 CAS Diagnostic (N=10)", "DEV", ["scripts/run_aime_sympy_diagnostic.py", "--limit", "10", "--model-tag", f"{tier_tag}_REBENCH"], 2000.0),
        (1, "MuSR Compound Soft Reasoning (N=30)", "DEV", ["scripts/run_musr_compound_benchmark.py", "--limit", "10", "--model-tag", f"{tier_tag}_REBENCH"], 2400.0),

        # Phase 2: Frontier Tool & Language
        (2, "BFCL v3 Function Calling (N=20)", "DEV", ["scripts/run_bfcl_benchmark.py", "--limit", "10", "--model-tag", f"{tier_tag}_REBENCH"], 400.0),
        (2, "GPQA Diamond Stratified (N=15)", "DEV", ["scripts/run_gpqa_diamond_benchmark.py", "--limit", "15"], 1200.0),
        (2, "OpenAI SimpleQA Factual Precision (N=20)", "DEV", ["scripts/run_simpleqa_eval.py", "--limit", "20"], 400.0),

        # Phase 3: Mathematical Formalization & Algorithmic Logic
        (3, "MATH-500 Held-Out (N=30)", "DEV", ["scripts/run_modern_2024_benchmarks.py", "--benchmark", "math500", "--samples", "30", "--feedback"], 600.0),
        (3, "GSM-Symbolic Parametric (N=30)", "DEV", ["scripts/run_modern_2024_benchmarks.py", "--benchmark", "gsm-symbolic", "--samples", "30", "--feedback"], 400.0),
        (3, "GSM8K in PAL Mode (N=30)", "DEV", ["scripts/run_standard_academic_benchmarks.py", "--benchmark", "gsm8k", "--samples", "30"], 400.0),
        (3, "CRUXEval-I Code Execution Reasoning (N=50)", "DEV", ["scripts/run_cruxeval_input.py", "--split", "dev"], 400.0),
        (3, "Big-Bench Hard Algorithmic Subsets (N=30)", "DEV", ["scripts/run_standard_academic_benchmarks.py", "--benchmark", "bbh", "--samples", "30"], 1200.0),

        # Phase 4: Code & Algorithmic Synthesis
        (4, "HumanEval Canonical Assisted CEGIS (N=30)", "DEV", ["scripts/run_standard_academic_benchmarks.py", "--benchmark", "humaneval", "--samples", "30"], 400.0),
        (4, "HumanEvalPlus Edge Testing (N=25)", "DEV", ["scripts/run_modern_2024_benchmarks.py", "--benchmark", "humaneval-plus", "--samples", "25"], 400.0),
        (4, "Graph & Planning Traversal (N=20)", "DEV", ["scripts/run_graph_planning_benchmark.py", "--limit", "20"], 900.0),

        # Phase 5: Cognitive, Memory & Spatial Priors
        (5, "ConceptARC Minimal Grid Transformations (16 Tasks)", "DEV", ["scripts/run_concept_arc.py", "--mode", "minimal"], 1200.0),
        (5, "LongMemEval Multi-Session Pipeline (N=30)", "DEV", ["scripts/run_longmemeval_pipeline_benchmark.py", "--limit", "10", "--model-tag", f"{tier_tag}_REBENCH"], 600.0),

        # Phase 6: Security, System, Voice & Identity Batteries
        (6, "Defensive Injection & Security (20 Vectors)", "DEV", ["scripts/run_defensive_security_benchmark.py"], 120.0),
        (6, "Tool Injection & Sandbox Defense (30 Vectors)", "DEV", ["scripts/run_tool_injection_defense.py"], 180.0),
        (6, "OOD Adversarial Security Trap Benchmark", "DEV", ["scripts/run_ood_adversarial_security_benchmark.py", "--model-tag", f"{tier_tag}_REBENCH"], 180.0),
        (6, "Action Hallucination Supervision Harness", "DEV", ["scripts/run_action_hallucination_eval.py"], 180.0),
        (6, "End-to-End Voice & Tooling Integration", "DEV", ["scripts/run_e2e_voice_tooling_integration.py"], 180.0),
        (6, "Personhood & Self-Identity Contrastive Battery", "DEV", ["scripts/run_contrastive_battery.py"], 400.0),
    ]

    selected_suites = [s for s in suite_definitions if s[0] >= args.start_phase]
    print(f"[+] Total Benchmark Suites to run: {len(selected_suites)} across Phases {args.start_phase}..6\n", flush=True)

    if args.dry_run:
        for phase, name, split_type, cmd_args, timeout in selected_suites:
            print(f"  [Phase {phase} | {split_type}] {name} -> python {' '.join(cmd_args)} (timeout: {timeout:.0f}s)")
        return 0

    results: list[dict] = []
    total_start = time.perf_counter()

    for idx, (phase, name, split_type, cmd_args, timeout) in enumerate(selected_suites, start=1):
        print(f"\n>>> Running [{idx}/{len(selected_suites)}] (Phase {phase} | {split_type}): {name} ...", flush=True)
        ok, elapsed, snip = run_benchmark_command(name, cmd_args, timeout_s=timeout)
        results.append({
            "phase": phase,
            "name": name,
            "split_type": split_type,
            "ok": ok,
            "elapsed_s": round(elapsed, 2),
            "command": " ".join(cmd_args),
            "tail_snippet": snip,
        })

    total_elapsed = time.perf_counter() - total_start
    total_pass = sum(1 for r in results if r["ok"])
    total_suites = len(results)

    report_payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tier": tier_tag,
        "arms": args.arms,
        "repeats": args.repeats,
        "environment": runtime_env,
        "total_suites": total_suites,
        "total_pass": total_pass,
        "pass_rate": round(total_pass / total_suites if total_suites else 0.0, 4),
        "total_elapsed_s": round(total_elapsed, 2),
        "results": results,
    }

    report_file = REPORTS_DIR / f"rebench_{tier_tag}_{int(time.time())}.json"
    report_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    print("\n" + "="*78)
    print(f"MASTER RE-BENCHMARKING COMPLETE (TIER: {tier_tag} | ARMS: {args.arms} | REPEATS: {args.repeats})")
    print(f"Suites Passed: {total_pass} / {total_suites} ({total_pass/total_suites*100:.1f}%) in {total_elapsed/60:.1f} minutes")
    print(f"Saved master report to: {report_file}")
    print("="*78)

    return 0 if total_pass == total_suites else 1


if __name__ == "__main__":
    raise SystemExit(main())
