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
    sorted_lats = sorted(latencies)
    lat_min = sorted_lats[0]
    lat_max = sorted_lats[-1]
    lat_mean = statistics.mean(sorted_lats)
    lat_p50 = statistics.median(sorted_lats)
    lat_p90 = sorted_lats[int(n_trials * 0.90)]
    lat_p95 = sorted_lats[int(n_trials * 0.95)]
    lat_p99 = sorted_lats[int(n_trials * 0.99)]
    lat_stdev = statistics.stdev(sorted_lats) if len(sorted_lats) > 1 else 0.0

    speedup_ratio = base_p50 / lat_p50 if lat_p50 > 0 else 0.0

    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS (N=50 Trials on Silicon)")
    print("=" * 70)
    print(f"  Trials Executed   : {n_trials} / {n_trials} PASSED (100% success)")
    print(f"  Total Wall Clock  : {total_wall_s * 1000.0:.2f} ms ({total_wall_s:.3f} s)")
    print(f"  Throughput        : {n_trials / total_wall_s:.1f} calls/sec")
    print("-" * 70)
    print(f"  Baseline Single-Shot P50 : {base_p50:.2f} ms")
    print(f"  Persistent Bridge P50    : {lat_p50:.2f} ms")
    print(f"  Latency Collapse (P50)   : -{100.0 * (1.0 - (lat_p50 / base_p50)):.1f}% ({speedup_ratio:.1f}x speedup)")
    print("-" * 70)
    print("  Detailed Latency Distribution (Orchestrator End-to-End):")
    print(f"    Min      : {lat_min:6.2f} ms")
    print(f"    P50 (Med): {lat_p50:6.2f} ms")
    print(f"    Mean     : {lat_mean:6.2f} ms (stdev: {lat_stdev:.2f} ms)")
    print(f"    P90      : {lat_p90:6.2f} ms")
    print(f"    P95      : {lat_p95:6.2f} ms")
    print(f"    P99      : {lat_p99:6.2f} ms")
    print(f"    Max      : {lat_max:6.2f} ms")
    print("=" * 70)

    # Save benchmark JSON report
    report_path = Path("logs/benchmark_persistent_rpc.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_trials": n_trials,
        "baseline_single_shot_p50_ms": round(base_p50, 2),
        "persistent_bridge_min_ms": round(lat_min, 2),
        "persistent_bridge_p50_ms": round(lat_p50, 2),
        "persistent_bridge_mean_ms": round(lat_mean, 2),
        "persistent_bridge_p90_ms": round(lat_p90, 2),
        "persistent_bridge_p95_ms": round(lat_p95, 2),
        "persistent_bridge_p99_ms": round(lat_p99, 2),
        "persistent_bridge_max_ms": round(lat_max, 2),
        "persistent_bridge_stdev_ms": round(lat_stdev, 2),
        "speedup_ratio": round(speedup_ratio, 1),
        "total_wall_s": round(total_wall_s, 3),
    }
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"Report saved to {report_path.resolve()}\n")


if __name__ == "__main__":
    run_benchmark(50)
