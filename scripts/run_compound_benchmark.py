"""
Project Lucca — Compound AI Reasoning 100-Problem Benchmark Runner
Spec: docs/specs/COMPOUND_REASONING_100_SPEC.md (SPEC-BENCH-100-v1.0)
WO-25 Phase 3

Runs the complete 100-problem benchmark battery through the live TurnPipeline
and outputs structured JSON reports to logs/test_reports/.

Usage:
  uv run python scripts/run_compound_benchmark.py
  uv run python scripts/run_compound_benchmark.py --category CAT01
  uv run python scripts/run_compound_benchmark.py --auto-start-server
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.brain.server_ctl import (
    check_server_status,
    is_healthy,
    start_server,
    stop_server,
)
from lucca.core.config import get_config
from tests.test_a1_live_hw import _make_hw_orchestrator
from tests.test_compound_reasoning_benchmark import (
    BENCHMARK_100_PROBES,
    BenchmarkProbe,
    run_probe,
)


def ensure_server(cfg, home_dir: Path, auto_start: bool = True):
    """Verifies that llama-server is healthy, or starts it if auto_start is True."""
    print("Checking llama-server health at http://127.0.0.1:8080/health ...")
    status = check_server_status("127.0.0.1", 8080)
    if status == "ready":
        print("  [OK] llama-server is online and responsive.")
        return None

    if not auto_start:
        print(f"  [ERROR] llama-server status is '{status}' and --auto-start-server is False.")
        print("  Please start llama-server or run with --auto-start-server.")
        sys.exit(1)

    print(f"  [INFO] llama-server status: '{status}'. Auto-launching native llama-server...")
    proc = start_server(cfg.llm, home_dir)
    print(f"  [INFO] Process spawned (PID {proc.pid}). Waiting for ready status (up to 45s)...")

    deadline = time.time() + 45.0
    while time.time() < deadline:
        time.sleep(1.5)
        st = check_server_status("127.0.0.1", 8080)
        if st == "ready":
            print(f"  [READY] llama-server initialized successfully (status: {st}).")
            return proc
        print(f"  ... status: {st} ({round(deadline - time.time())}s remaining)")

    print("  [ERROR] Timed out waiting for llama-server to become ready.")
    stop_server("127.0.0.1", 8080, proc)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Project Lucca 100-Problem Benchmark")
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default="all",
        help="Category to run: CAT01 to CAT10, or 'all' (default: all)",
    )
    parser.add_argument(
        "--probe",
        "-p",
        type=str,
        default=None,
        help="Single probe ID to run, e.g. CAT02-01 (overrides --category)",
    )
    parser.add_argument(
        "--auto-start-server",
        action="store_true",
        default=True,
        help="Automatically launch llama-server if offline",
    )
    parser.add_argument(
        "--no-auto-start",
        action="store_false",
        dest="auto_start_server",
        help="Do not auto-launch llama-server",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Custom output JSON report file path",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=True,
        help="Print verbose replies and grading details per probe",
    )
    args = parser.parse_args()

    cfg = get_config()
    server_proc = ensure_server(cfg, cfg.home_dir, auto_start=args.auto_start_server)

    # Filter probes
    if args.probe:
        target_probe = args.probe.strip().upper()
        probes = [p for p in BENCHMARK_100_PROBES if p.id.upper() == target_probe]
        if not probes:
            print(f"[ERROR] Unknown probe ID: {target_probe}")
            sys.exit(1)
        target_cat = probes[0].category
    else:
        target_cat = args.category.strip().upper()
        if target_cat == "ALL":
            probes = list(BENCHMARK_100_PROBES)
        else:
            probes = [p for p in BENCHMARK_100_PROBES if p.category == target_cat]
            if not probes:
                print(f"[ERROR] Unknown category: {target_cat}. Valid: CAT01..CAT10, ALL")
                sys.exit(1)

    print("\n" + "=" * 78)
    print(f"  PROJECT LUCCA — COMPOUND REASONING 100-PROBLEM BENCHMARK")
    print(f"  Selected: {target_cat} ({len(probes)} problems)")
    print("=" * 78 + "\n")

    # Run benchmarks with fresh orchestrator per category
    reports_dir = REPO_ROOT / "logs" / "test_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    all_results: list[dict[str, Any]] = []
    category_map: dict[str, list[dict[str, Any]]] = {}

    current_cat = None
    orch = None
    tmp_dir = None

    try:
        from unittest.mock import MagicMock
        for idx, probe in enumerate(probes, 1):
            if probe.category != current_cat:
                if orch is not None and hasattr(orch, "db"):
                    try:
                        orch.db.close()
                    except Exception:
                        pass
                current_cat = probe.category
                category_map[current_cat] = []
                # Re-instantiate clean orchestrator for isolation
                tmp_dir = tempfile.TemporaryDirectory()
                orch, _, _ = _make_hw_orchestrator(Path(tmp_dir.name), use_docker=True)
                orch.config.llm.temperature = 0.0
                orch.llm.config.llm.temperature = 0.0
                orch.speech_output = MagicMock()
                orch.confirmations = MagicMock()
                orch.confirmations.request_confirmation = MagicMock(return_value=True)
                orch._request_confirmation = MagicMock(return_value=True)
                print(f"\n--- Entering Category: {current_cat} ---")

            # Reset history between turns
            assert orch is not None
            orch.history = []
            orch.turn_pipeline.reset_turn_state()
            if hasattr(orch, "_tts_queue") and hasattr(orch._tts_queue, "queue"):
                orch._tts_queue.queue.clear()

            print(f"\n[{idx:03d}/{len(probes):03d}] {probe.id}: {probe.title}")
            print(f"  Prompt:   {probe.prompt}")
            res = run_probe(orch, probe)
            category_map[current_cat].append(res)
            all_results.append(res)

            status_str = "PASS" if res["passed"] else "FAIL"
            p_ok = "OK" if res.get("path_ok", True) else "FAIL"
            a_ok = "OK" if res.get("answer_ok", res["passed"]) else "FAIL"
            f_ok = "OK" if res.get("faithfulness_ok", True) else "FAIL"
            p_taken = res.get("path_taken", "native")
            t_calls = res.get("tool_calls_count", len(res.get("tools", [])))
            t_fails = res.get("tool_failures_count", 0)
            t_recov = res.get("tool_recovered", False)
            print(f"  Result:   {status_str} ({res['elapsed_s']}s) [Path: {p_ok} ({p_taken}) | Answer: {a_ok} | Faith: {f_ok}]")
            print(f"  Class:    {res.get('outcome_class', 'unique')} | Policy: {res.get('tool_route_policy', 'allowed')}")
            recov_str = " [RECOVERY]" if t_recov else ""
            print(f"  Tools:    calls={t_calls}, fails={t_fails}{recov_str} -> {json.dumps(res.get('tool_calls', []))}")
            if res.get('receipts'):
                for r in res['receipts']:
                    err_info = f" err={repr(r.get('error'))[:80]}" if r.get('error') else ""
                    print(f"  Receipt:  tool={r.get('name')} ok={r.get('ok')}{err_info} out={repr(r.get('output'))[:140]}")
            if res.get('code_assumptions'):
                print(f"  Mined:    {res['code_assumptions']}")
            print(f"  Reply:    {res['reply']}")
            print(f"  Grading:  {res['eval_reason']}")

    finally:
        if orch is not None and hasattr(orch, "db"):
            try:
                orch.db.close()
            except Exception:
                pass
        if server_proc is not None:
            print("\nShutting down spawned llama-server...")
            stop_server("127.0.0.1", 8080, server_proc)

    # Output Summary Table
    print("\n" + "=" * 104)
    print(f"{'Category':<8} | {'Name':<30} | {'Score':<7} | {'Rate':<6} | {'Path':<5} | {'Faith':<5} | {'Tools (calls/fails/recov)':<25} | {'Med Latency':<11}")
    print("-" * 104)

    cat_names = {
        "CAT01": "Situational Telemetry Deduction",
        "CAT02": "Spatial, Kinematic & 3D Vectors",
        "CAT03": "Formal Constraint Logic Grids",
        "CAT04": "Closed-World Interval & Algebra",
        "CAT05": "Web-Augmented Real Research",
        "CAT06": "Defeasible Abductive Inference",
        "CAT07": "Theory of Mind & Game Theory",
        "CAT08": "Autobiographical Memory & Purge",
        "CAT09": "Meta-Cognitive Self-Diagnosis",
        "CAT10": "Means-Ends Practical Planning",
    }

    total_passed = 0
    total_count = 0
    total_path_ok = 0
    total_faith_ok = 0
    total_tool_calls = 0
    total_tool_fails = 0
    total_tool_recov = 0
    all_latencies = []

    for cat_id, cat_results in category_map.items():
        c_passed = sum(1 for r in cat_results if r["passed"])
        c_path = sum(1 for r in cat_results if r.get("path_ok", True))
        c_faith = sum(1 for r in cat_results if r.get("faithfulness_ok", True))
        c_calls = sum(r.get("tool_calls_count", len(r.get("tools", []))) for r in cat_results)
        c_fails = sum(r.get("tool_failures_count", 0) for r in cat_results)
        c_recov = sum(1 for r in cat_results if r.get("tool_recovered", False))
        c_total = len(cat_results)
        total_passed += c_passed
        total_count += c_total
        total_path_ok += c_path
        total_faith_ok += c_faith
        total_tool_calls += c_calls
        total_tool_fails += c_fails
        total_tool_recov += c_recov
        latencies = [r["elapsed_s"] for r in cat_results]
        all_latencies.extend(latencies)
        med_lat = round(statistics.median(latencies), 2) if latencies else 0.0
        rate = round((c_passed / c_total) * 100, 1) if c_total else 0.0
        c_name = cat_names.get(cat_id, cat_id)
        tool_stat_str = f"{c_calls} / {c_fails} / {c_recov}"
        print(f"{cat_id:<8} | {c_name:<30} | {c_passed}/{c_total:<4} | {rate:>5.1f}% | {c_path}/{c_total:<2} | {c_faith}/{c_total:<2} | {tool_stat_str:<25} | {med_lat:>6.2f}s")

    print("-" * 104)
    overall_rate = round((total_passed / total_count) * 100, 1) if total_count else 0.0
    overall_med = round(statistics.median(all_latencies), 2) if all_latencies else 0.0
    all_tool_str = f"{total_tool_calls} / {total_tool_fails} / {total_tool_recov}"
    print(f"{'OVERALL':<8} | {'100-Problem Compound Battery':<30} | {total_passed}/{total_count:<4} | {overall_rate:>5.1f}% | {total_path_ok}/{total_count:<2} | {total_faith_ok}/{total_count:<2} | {all_tool_str:<25} | {overall_med:>6.2f}s")
    print("=" * 104 + "\n")

    # Save JSON Report
    out_path = Path(args.output) if args.output else reports_dir / f"compound_benchmark_{ts}.json"
    report_data = {
        "timestamp": ts,
        "total_problems": total_count,
        "total_passed": total_passed,
        "pass_rate_pct": overall_rate,
        "total_path_ok": total_path_ok,
        "total_faithfulness_ok": total_faith_ok,
        "total_tool_calls": total_tool_calls,
        "total_tool_failures": total_tool_fails,
        "total_tool_recoveries": total_tool_recov,
        "median_latency_s": overall_med,
        "category_summary": {
            cat_id: {
                "name": cat_names.get(cat_id, cat_id),
                "passed": sum(1 for r in res_list if r["passed"]),
                "total": len(res_list),
                "pass_rate_pct": round((sum(1 for r in res_list if r["passed"]) / len(res_list)) * 100, 1),
                "path_ok": sum(1 for r in res_list if r.get("path_ok", True)),
                "faithfulness_ok": sum(1 for r in res_list if r.get("faithfulness_ok", True)),
                "tool_calls": sum(r.get("tool_calls_count", len(r.get("tools", []))) for r in res_list),
                "tool_failures": sum(r.get("tool_failures_count", 0) for r in res_list),
                "tool_recoveries": sum(1 for r in res_list if r.get("tool_recovered", False)),
                "median_latency_s": round(statistics.median([r["elapsed_s"] for r in res_list]), 2) if res_list else 0.0,
            }
            for cat_id, res_list in category_map.items()
        },
        "results": all_results,
    }
    out_path.write_text(json.dumps(report_data, indent=2))
    print(f"Full benchmark JSON report written to: {out_path}\n")


if __name__ == "__main__":
    main()
