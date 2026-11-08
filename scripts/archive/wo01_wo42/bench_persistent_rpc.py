"""
Project Lucca — Formal Silicon Latency Benchmark (N=50)
Spec 09 §1, §2, §4, §5

Executes N=50 real tool calls through Orchestrator._handle_tool_call
using the persistent stdio bridge (lucca-toolsrv --loop) inside the WSL2 Docker sandbox.
Measures and reports Min, P50, P90, P95, P99, Max turnaround on physical workstation silicon.
"""

import json
import statistics
import sys
import time
from pathlib import Path

from lucca.core.orchestrator import Orchestrator
from lucca.core.trace import TurnTrace, now_ns
from lucca.sandbox.rpc import DockerRPCTransport
from lucca.sandbox.service import SandboxService


class DummyTTS:
    def synthesize(self, chunk_id: int, text: str, is_first: bool = False) -> bool:
        return True


class DummyASR:
    pass


class DummyLLM:
    pass


def run_benchmark(n_trials: int = 50) -> None:
    print("=" * 70)
    print(f"Project Lucca: WSL2 Persistent RPC Bridge Latency Benchmark (N={n_trials})")
    print("=" * 70)

    # 1. Verify container liveness
    probe_rpc = DockerRPCTransport(container_name="lucca-file-sandbox")
    if not probe_rpc.is_docker_available():
        print("ERROR: Docker / WSL2 is not available on this system.")
        sys.exit(1)
    if not probe_rpc.is_container_running():
        print("Launching lucca-file-sandbox container in WSL2...")
        if not probe_rpc.ensure_container_running():
            print("ERROR: Could not start container.")
            sys.exit(1)
    probe_rpc.close()
    print("Container lucca-file-sandbox is running and ready.\n")

    # 2. Baseline: Measure Single-Shot (Legacy docker exec per call)
    print("--> Measuring baseline: Single-Shot `docker exec` (N=10)...")
    single_shot_transport = DockerRPCTransport(
        container_name="lucca-file-sandbox",
        use_persistent_worker=False,
    )
    single_shot_latencies: list[float] = []
    for i in range(10):
        res = single_shot_transport.execute(
            call_id=f"base-{i}",
            tool="list_dir",
            args={"path": "."},
        )
        assert res.ok, f"Single-shot call failed: {res.stderr}"
        single_shot_latencies.append(res.elapsed_ms)
    single_shot_transport.close()

    base_p50 = statistics.median(single_shot_latencies)
    print(f"    Single-shot P50: {base_p50:.2f} ms (Min: {min(single_shot_latencies):.2f} ms, Max: {max(single_shot_latencies):.2f} ms)\n")

    # 3. Benchmark Persistent Bridge through Orchestrator._handle_tool_call
    print(f"--> Initializing Orchestrator with Persistent Bridge...")
    sandbox = SandboxService()
    orch = Orchestrator(
        llm=DummyLLM(),  # type: ignore[arg-type]
        tts=DummyTTS(),  # type: ignore[arg-type]
        asr=DummyASR(),  # type: ignore[arg-type]
        sandbox=sandbox,
    )
    # Simulate immediate confirmation for WRITE/EXEC tools during benchmark
    orch._request_confirmation = lambda trace, name, args, timeout_s=15.0: True

    trace = TurnTrace(
        trace_id="bench-trace-01",
        session_id="bench-session-01",
        origin="text",
        mode="transcript",
        t_key_press=now_ns(),
        t_key_release=now_ns(),
        t_vad_done=now_ns(),
    )

    # Pre-warm worker
    print("    Pre-warming persistent worker...")
    warm_res = orch._handle_tool_call(trace, "list_dir", {"path": "."}, speak=False)
    assert warm_res and warm_res.ok, "Warmup call failed"
    print(f"    Warmup complete. First call turnaround (including spawn): {warm_res.elapsed_ms:.2f} ms\n")

    # Benchmark workload: Mix of realistic tools (list_dir, write_file, read_file with SHA256 audit, run_python)
    tools_workload = [
        ("list_dir", {"path": "."}),
        ("write_file", {"path": "bench_payload.txt", "content": "Lucca Persistent Bridge Benchmark Payload", "mode": "overwrite"}),
        ("read_file", {"path": "bench_payload.txt"}),
        ("run_python", {"code": "import math; print(math.sqrt(1764))"}),
    ]

    print(f"--> Executing {n_trials} tool calls through Orchestrator._handle_tool_call...")
    latencies: list[float] = []
    wall_start = time.perf_counter()

    for trial_idx in range(n_trials):
        tool_name, tool_args = tools_workload[trial_idx % len(tools_workload)]
        t0 = time.perf_counter()
        res = orch._handle_tool_call(trace, tool_name, tool_args, speak=False)
        t1 = time.perf_counter()

        elapsed_ms = (t1 - t0) * 1000.0
        assert res is not None and res.ok, f"Trial {trial_idx} failed: {getattr(res, 'stderr', 'unknown')}"
        latencies.append(elapsed_ms)

    total_wall_s = time.perf_counter() - wall_start
    orch.sandbox.close()

    # 4. Statistical Analysis
    fs_lats = [latencies[i] for i in range(n_trials) if tools_workload[i % len(tools_workload)][0] != "run_python"]
    py_lats = [latencies[i] for i in range(n_trials) if tools_workload[i % len(tools_workload)][0] == "run_python"]

    def calc_stats(data: list[float]) -> dict[str, float]:
        s = sorted(data)
        n = len(s)
        return {
            "n": float(n),
            "min": s[0],
            "p50": statistics.median(s),
            "mean": statistics.mean(s),
            "p90": s[int(n * 0.90)],
            "p95": s[int(n * 0.95)],
            "p99": s[min(n - 1, int(n * 0.99))],
            "max": s[-1],
            "stdev": statistics.stdev(s) if n > 1 else 0.0,
        }

    agg_stats = calc_stats(latencies)
    fs_stats = calc_stats(fs_lats)
    py_stats = calc_stats(py_lats)

    speedup_fs = base_p50 / fs_stats["p50"] if fs_stats["p50"] > 0 else 0.0

    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS (N=50 Workstation Silicon Trials)")
    print("=" * 70)
    print(f"  Total Trials Executed : {n_trials} / {n_trials} PASSED (100% success)")
    print(f"  Workload Breakdown    : {int(fs_stats['n'])} Filesystem I/O ({int(fs_stats['n'])*100//n_trials}%) + {int(py_stats['n'])} Ephemeral Python ({int(py_stats['n'])*100//n_trials}%)")
    print(f"  Total Wall Clock      : {total_wall_s * 1000.0:.2f} ms ({total_wall_s:.3f} s)")
    print(f"  Baseline Single-Shot  : P50 = {base_p50:.2f} ms (Min: {min(single_shot_latencies):.2f} ms)")
    print("-" * 70)
    print("  PRIMARY: Filesystem Operations (list_dir, write_file, read_file)")
    print(f"    Sample Size (N)     : N = {int(fs_stats['n'])}")
    print(f"    Turnaround (P50)    : {fs_stats['p50']:6.2f} ms (-{100.0 * (1.0 - (fs_stats['p50'] / base_p50)):.1f}%, {speedup_fs:.1f}x speedup)")
    print(f"    Min                 : {fs_stats['min']:6.2f} ms")
    print(f"    Mean                : {fs_stats['mean']:6.2f} ms (stdev: {fs_stats['stdev']:.2f} ms)")
    print(f"    P90                 : {fs_stats['p90']:6.2f} ms")
    print(f"    P95                 : {fs_stats['p95']:6.2f} ms")
    print(f"    P99 / Max           : {fs_stats['max']:6.2f} ms")
    print("-" * 70)
    print("  PRIMARY: Sub-Isolated Compute (run_python child process with rlimits)")
    print(f"    Sample Size (N)     : N = {int(py_stats['n'])}")
    print(f"    Turnaround (P50)    : {py_stats['p50']:6.2f} ms")
    print(f"    Min                 : {py_stats['min']:6.2f} ms")
    print(f"    Mean                : {py_stats['mean']:6.2f} ms (stdev: {py_stats['stdev']:.2f} ms)")
    print(f"    P90                 : {py_stats['p90']:6.2f} ms")
    print(f"    P95                 : {py_stats['p95']:6.2f} ms")
    print(f"    P99 / Max           : {py_stats['max']:6.2f} ms")
    print("-" * 70)
    print("  FOOTNOTE: Mixed Bimodal Aggregate (76% Filesystem + 24% Python)")
    print(f"    P50: {agg_stats['p50']:5.2f} ms | Mean: {agg_stats['mean']:5.2f} ms | P90: {agg_stats['p90']:5.2f} ms | P95: {agg_stats['p95']:5.2f} ms | P99: {agg_stats['p99']:5.2f} ms")
    print("=" * 70)

    # Save benchmark JSON report
    report_path = Path("logs/benchmark_persistent_rpc.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_trials": n_trials,
        "workload_ratio": {"filesystem_n": int(fs_stats["n"]), "python_n": int(py_stats["n"])},
        "baseline_single_shot_p50_ms": round(base_p50, 2),
        "filesystem_io": {k: round(v, 2) for k, v in fs_stats.items()},
        "isolated_python": {k: round(v, 2) for k, v in py_stats.items()},
        "mixed_aggregate": {k: round(v, 2) for k, v in agg_stats.items()},
        "speedup_filesystem_ratio": round(speedup_fs, 1),
        "total_wall_s": round(total_wall_s, 3),
    }
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"Report saved to {report_path.resolve()}\n")


if __name__ == "__main__":
    run_benchmark(50)
