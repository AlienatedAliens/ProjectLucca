"""
Project Lucca — Full Uncurated Cross-Domain Benchmark Batch Runner
=================================================================
Executes the full, uncurated academic benchmark datasets on the active model
under the v1.45.0 Abductive CEGIS Engine with 100% atomic checkpointing:

1. ConceptARC Full Corpus ($N=160$ tasks):
   - All 10 tasks across all 16 cognitive concepts.
   - Pure cold synthesis (episodic cache disabled).
   - Resumable atomic checkpointing per task.

2. MATH-500 Full Corpus ($N=500$ problems):
   - All 500 competition math problems across all 7 subjects and 5 difficulty levels.
   - Direct Arm A Control vs Arm B MicroScheme MathCAS Sketch.
   - Resumable atomic checkpointing per problem.

3. CRUXEval-Input Full Evaluation ($N=400$ problems):
   - Full 400-function input prediction evaluation.
   - Direct Arm A vs Iterative CEGIS Arm B self-debugging ladder.
   - Resumable atomic checkpointing per function.

Zero-Any typing invariant strictly enforced per D-AUD-01.
Zero Docker dependency.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Windows console cp1252 fix
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OUTPUT_DIR: Final[Path] = REPO_ROOT / "logs" / "test_reports" / "full_uncurated"
PYTHON_EXE: Final[str] = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("uncurated_batch")


def verify_active_server() -> str:
    """Verifies that llama-server is online and identifies the active model."""
    try:
        r = httpx.get("http://127.0.0.1:8080/health", timeout=3.0)
        if r.status_code != 200 or r.json().get("status") != "ok":
            raise RuntimeError(f"Server returned non-ok health: {r.text}")
        
        m_resp = httpx.get("http://127.0.0.1:8080/v1/models", timeout=3.0)
        items = m_resp.json().get("data", [])
        model_id = items[0]["id"] if items else "unknown"
        print(f"[SERVER ONLINE] Active Model: {Path(model_id).name}")
        return str(model_id)
    except Exception as exc:
        print(f"[FATAL ERROR] llama-server is offline: {exc}")
        sys.exit(1)


def run_benchmark_step(name: str, cmd: list[str]) -> None:
    print("\n" + "=" * 80)
    print(f"STARTING FULL-SCALE BENCHMARK: {name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print("=" * 80 + "\n", flush=True)

    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    elapsed = time.perf_counter() - t0

    if proc.returncode != 0:
        print(f"\n[WARNING] Benchmark {name} exited with non-zero code {proc.returncode} in {elapsed:.1f}s")
    else:
        print(f"\n[SUCCESS] Benchmark {name} completed successfully in {elapsed:.1f}s ({elapsed/60.0:.1f}m)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Full Uncurated Cross-Domain Benchmark Batch Runner")
    parser.add_argument(
        "--domain",
        choices=["all", "concept_arc", "math500", "cruxeval"],
        default="all",
        help="Benchmark domain to run (default: all)",
    )
    parser.add_argument("--limit-concept-arc", type=int, default=None, help="Optional task limit per concept")
    parser.add_argument("--limit-math", type=int, default=500, help="Math problem limit (default: 500)")
    parser.add_argument("--limit-cruxeval", type=int, default=400, help="CRUXEval problem limit (default: 400)")
    parser.add_argument("--no-resume", action="store_true", help="Do not resume existing checkpoints")
    parser.add_argument("--model-tag", type=str, default="tier0", help="Model tag for reports (default: tier0)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    active_model = verify_active_server()
    model_tag = args.model_tag

    print("\n" + "#" * 80)
    print("   PROJECT LUCCA — FULL UNCURATED CROSS-DOMAIN BENCHMARK CAMPAIGN (v1.45.0)")
    print(f"   Model: {Path(active_model).name} [{model_tag}]")
    print(f"   Domain: {args.domain.upper()} | Output: {OUTPUT_DIR}")
    print("#" * 80 + "\n")

    t_batch_start = time.perf_counter()

    # 1. ConceptARC Full (N=160 tasks)
    if args.domain in ("all", "concept_arc"):
        ca_out = OUTPUT_DIR / f"concept_arc_160_full_{model_tag}.json"
        ca_cmd = [
            PYTHON_EXE,
            "scripts/run_concept_arc_full.py",
            "--disable-cache",
            "--output", str(ca_out),
        ]
        if args.limit_concept_arc is not None:
            ca_cmd.extend(["--limit-per-concept", str(args.limit_concept_arc)])
        if args.no_resume:
            ca_cmd.append("--no-resume")

        run_benchmark_step("ConceptARC Full Corpus ($N=160$)", ca_cmd)

    # 2. MATH-500 Full (N=500 problems)
    if args.domain in ("all", "math500"):
        math_out = OUTPUT_DIR / f"math500_500_full_{model_tag}.json"
        math_cmd = [
            PYTHON_EXE,
            "scripts/run_math500_sketch.py",
            "--samples", str(args.limit_math),
            "--output", str(math_out),
        ]
        if args.no_resume:
            math_cmd.append("--no-resume")

        run_benchmark_step(f"MATH-500 Full Held-Out Corpus ($N={args.limit_math}$)", math_cmd)

    # 3. CRUXEval-Input Full (N=400 problems)
    if args.domain in ("all", "cruxeval"):
        crux_out = OUTPUT_DIR / f"cruxeval_input_{args.limit_cruxeval}_full_{model_tag}.json"
        crux_cmd = [
            PYTHON_EXE,
            "scripts/run_cruxeval_input.py",
            "--split", "full",
            "--limit", str(args.limit_cruxeval),
            "--output-json", str(crux_out),
        ]
        if args.no_resume:
            crux_cmd.append("--no-resume")

        run_benchmark_step(f"CRUXEval-Input Full Corpus ($N={args.limit_cruxeval}$)", crux_cmd)

    total_elapsed = time.perf_counter() - t_batch_start
    print("\n" + "=" * 80)
    print("ALL FULL UNCURATED BENCHMARKS CONCLUDED")
    print(f"Total Batch Runtime: {total_elapsed/3600.0:.2f} hours ({total_elapsed:.1f}s)")
    print(f"Reports Sealed in: {OUTPUT_DIR}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
