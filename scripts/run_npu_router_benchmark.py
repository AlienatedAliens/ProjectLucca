"""
Project Lucca — NPU vs CPU Fast Intent & Dynamic Tiered Router Benchmark
Validates sub-10ms semantic intent classification and deterministic neurosymbolic dispatch
across the 6 compound reasoning modalities.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
import numpy as np

from lucca.router.heuristic import HeuristicRouter
from lucca.senses.embed import EmbedWorker


@dataclass
class BenchmarkItem:
    query: str
    expected_domain: str | None
    expected_intent: str
    expected_solver: str | None
    expected_thinking: str


BENCHMARK_ITEMS: list[BenchmarkItem] = [
    # 1. Code Repair (SWE-bench Lite)
    BenchmarkItem(
        query="Diagnose and fix the bug in this python module where pytest is failing with an AttributeError.",
        expected_domain="code_repair",
        expected_intent="code_repair",
        expected_solver="apply_patch",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Apply a patch to fix the regression in the requests library tests.",
        expected_domain="code_repair",
        expected_intent="code_repair",
        expected_solver="apply_patch",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Grep the tree for the traceback and run pytest to verify the issue is resolved.",
        expected_domain="code_repair",
        expected_intent="code_repair",
        expected_solver="apply_patch",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Inspect lines of marshmallow schema to fix the failing test suite.",
        expected_domain="code_repair",
        expected_intent="code_repair",
        expected_solver="apply_patch",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Investigate the failing unit test in the flask routing engine.",
        expected_domain="code_repair",
        expected_intent="code_repair",
        expected_solver="apply_patch",
        expected_thinking="thinking",
    ),

    # 2. Spatial Grid (ConceptARC / ARC-AGI)
    BenchmarkItem(
        query="Transform this concept arc visual reasoning task by flood filling the enclosed shape.",
        expected_domain="spatial_grid",
        expected_intent="spatial_grid",
        expected_solver="arc_primitives",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Rotate the 2D grid matrix 90 degrees counter-clockwise.",
        expected_domain="spatial_grid",
        expected_intent="spatial_grid",
        expected_solver="arc_primitives",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Apply gravity drop to the falling objects in the demonstration grids.",
        expected_domain="spatial_grid",
        expected_intent="spatial_grid",
        expected_solver="arc_primitives",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Extract the connected components and sort them by size in the 2d array.",
        expected_domain="spatial_grid",
        expected_intent="spatial_grid",
        expected_solver="arc_primitives",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Solve this ARC-AGI pattern given the input grid and output grid examples.",
        expected_domain="spatial_grid",
        expected_intent="spatial_grid",
        expected_solver="arc_primitives",
        expected_thinking="thinking",
    ),

    # 3. Web Search (SearXNG / Epistemic Retrieval)
    BenchmarkItem(
        query="Search the web for the latest financial reports of Nvidia for fiscal 2026.",
        expected_domain="web_search",
        expected_intent="web_fetch",
        expected_solver="search_web",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Look up online what the current population and GDP of Tokyo are.",
        expected_domain="web_search",
        expected_intent="web_fetch",
        expected_solver="search_web",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Perform a web search using searxng to find recent clinical trials on mRNA vaccines.",
        expected_domain="web_search",
        expected_intent="web_fetch",
        expected_solver="search_web",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Check other websites and sources online for details on the Artemis mission.",
        expected_domain="web_search",
        expected_intent="web_fetch",
        expected_solver="search_web",
        expected_thinking="thinking",
    ),
    BenchmarkItem(
        query="Find more information on the web about the James Webb telescope discovery.",
        expected_domain="web_search",
        expected_intent="web_fetch",
        expected_solver="search_web",
        expected_thinking="thinking",
    ),

    # 4. Combinatorial SMT (Z3 / Logic Puzzles)
    BenchmarkItem(
        query="Solve the zebra puzzle with five houses of different colors and nationalities.",
        expected_domain="combinatorial_smt",
        expected_intent="logic_constraints",
        expected_solver="z3_smt",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="Einstein's puzzle: who owns the fish given these constraints?",
        expected_domain="combinatorial_smt",
        expected_intent="logic_constraints",
        expected_solver="z3_smt",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="Find an assignment that can satisfy the following constraints using z3 smt solver.",
        expected_domain="combinatorial_smt",
        expected_intent="logic_constraints",
        expected_solver="z3_smt",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="On an island of knights and knaves, A says B is a knave and B says A is a liar.",
        expected_domain="combinatorial_smt",
        expected_intent="logic_constraints",
        expected_solver="z3_smt",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="Determine which house the green house is next to in this logic grid puzzle.",
        expected_domain="combinatorial_smt",
        expected_intent="logic_constraints",
        expected_solver="z3_smt",
        expected_thinking="direct",
    ),

    # 5. Mathematics & Symbolic Algebra (SymPy)
    BenchmarkItem(
        query="Solve the system of equations 2*x + 3*y = 12 and x - y = 1.",
        expected_domain="mathematics",
        expected_intent="math_computation",
        expected_solver="sympy_sandbox",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="Calculate the eigenvalues and determinant of the 3x3 matrix using sympy.",
        expected_domain="mathematics",
        expected_intent="math_computation",
        expected_solver="sympy_sandbox",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="Compute the prime factors and gcd of 1024 and 768.",
        expected_domain="mathematics",
        expected_intent="math_computation",
        expected_solver="sympy_sandbox",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="Find the sum of the squares of all the items in the list given sum is 30.",
        expected_domain="mathematics",
        expected_intent="math_computation",
        expected_solver="sympy_sandbox",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="Evaluate the expression \\log_2(x / (y*z)) given the polynomial roots.",
        expected_domain="mathematics",
        expected_intent="math_computation",
        expected_solver="sympy_sandbox",
        expected_thinking="direct",
    ),

    # 6. Conversational / Direct Reflex / Multi-Hop Relocation
    BenchmarkItem(
        query="Hello Lucca, how are you doing today?",
        expected_domain=None,
        expected_intent="chit_chat",
        expected_solver=None,
        expected_thinking="adaptive",
    ),
    BenchmarkItem(
        query="Good morning! Thanks so much for your help.",
        expected_domain=None,
        expected_intent="chit_chat",
        expected_solver=None,
        expected_thinking="adaptive",
    ),
    BenchmarkItem(
        query="Lucca stop right now!",
        expected_domain=None,
        expected_intent="dangerous",  # or reflex
        expected_solver=None,
        expected_thinking="adaptive",
    ),
    BenchmarkItem(
        query="Where would Danny look to find the earphones given the story?",
        expected_domain="spatial_relocation",
        expected_intent="unknown",  # or contextual
        expected_solver="container_world",
        expected_thinking="direct",
    ),
    BenchmarkItem(
        query="Who moved the keys from the kitchen to the desk while Alice was away?",
        expected_domain="spatial_relocation",
        expected_intent="unknown",
        expected_solver="container_world",
        expected_thinking="direct",
    ),
]


def benchmark_device(device_name: str, runs_per_query: int = 5) -> dict[str, object]:
    print(f"\n{'='*70}\nBenchmarking Device: {device_name}\n{'='*70}")
    worker = EmbedWorker(device=device_name)
    router = HeuristicRouter(embed_worker=worker)

    # Warmup
    router.route("Warmup query for the embedding pipeline and cache initialization")

    results: list[dict[str, object]] = []
    latencies: list[float] = []
    dot_latencies: list[float] = []
    correct_domains = 0
    correct_solvers = 0

    for idx, item in enumerate(BENCHMARK_ITEMS, 1):
        item_latencies: list[float] = []
        for _ in range(runs_per_query):
            t0 = time.perf_counter()
            dec = router.route(item.query)
            t1 = time.perf_counter()
            item_latencies.append((t1 - t0) * 1000.0)

        p50 = float(np.percentile(item_latencies, 50))
        latencies.extend(item_latencies)

        # Measure isolated anchor dot product time (matrix @ qv)
        qv_res, _, _ = worker.embed_text([item.query])
        qv = np.array(qv_res[0], dtype=np.float32)
        dot_t0 = time.perf_counter()
        _ = np.dot(router._anchor_matrix, qv)
        dot_ms = (time.perf_counter() - dot_t0) * 1000.0
        dot_latencies.append(dot_ms)

        # Domain accuracy check
        domain_ok = (dec.reasoning_domain == item.expected_domain)
        solver_ok = (dec.solver_tool == item.expected_solver)
        if domain_ok:
            correct_domains += 1
        if solver_ok:
            correct_solvers += 1

        status_str = "PASS" if domain_ok and solver_ok else "DIFF"
        print(
            f"[{idx:02d}/30] [{status_str}] Domain: {dec.reasoning_domain or 'None':<18} "
            f"| Solver: {dec.solver_tool or 'None':<15} | p50: {p50:5.2f}ms | {item.query[:45]}..."
        )

        results.append({
            "query": item.query,
            "expected_domain": item.expected_domain,
            "actual_domain": dec.reasoning_domain,
            "expected_solver": item.expected_solver,
            "actual_solver": dec.solver_tool,
            "actual_thinking": dec.thinking_mode,
            "deliberation_lane": dec.deliberation_lane,
            "exposed_libraries": dec.exposed_libraries,
            "p50_latency_ms": p50,
            "all_latencies_ms": item_latencies,
            "domain_match": domain_ok,
            "solver_match": solver_ok,
        })

    p50_overall = float(np.percentile(latencies, 50))
    p95_overall = float(np.percentile(latencies, 95))
    avg_dot_us = float(np.mean(dot_latencies)) * 1000.0

    domain_acc = (correct_domains / len(BENCHMARK_ITEMS)) * 100.0
    solver_acc = (correct_solvers / len(BENCHMARK_ITEMS)) * 100.0

    print(f"\n--- Summary for {device_name} ---")
    print(f"Domain Accuracy: {domain_acc:.1f}% ({correct_domains}/{len(BENCHMARK_ITEMS)})")
    print(f"Solver Accuracy: {solver_acc:.1f}% ({correct_solvers}/{len(BENCHMARK_ITEMS)})")
    print(f"End-to-End Latency: p50 = {p50_overall:.2f} ms | p95 = {p95_overall:.2f} ms")
    print(f"Isolated Vector Dot-Product: ~{avg_dot_us:.1f} microseconds")

    return {
        "device": device_name,
        "domain_accuracy_pct": domain_acc,
        "solver_accuracy_pct": solver_acc,
        "latency_p50_ms": p50_overall,
        "latency_p95_ms": p95_overall,
        "vector_dot_us": avg_dot_us,
        "items": results,
    }


def main() -> None:
    print("Project Lucca — Fast NPU/CPU Intent & Neurosymbolic Routing Benchmark")
    report: dict[str, object] = {
        "timestamp": time.time(),
        "total_queries": len(BENCHMARK_ITEMS),
    }

    npu_res = benchmark_device("NPU")
    cpu_res = benchmark_device("CPU")

    report["npu"] = npu_res
    report["cpu"] = cpu_res

    log_dir = Path(r"C:\Projects\ProjectLucca\logs\test_reports")
    log_dir.mkdir(parents=True, exist_ok=True)
    report_file = log_dir / f"npu_router_benchmark_{int(time.time())}.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[REPORT SEALED]: {report_file}")


if __name__ == "__main__":
    main()
