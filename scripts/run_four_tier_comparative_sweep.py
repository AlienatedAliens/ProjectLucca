"""
Project Lucca — Four-Tier Comparative Benchmark Sweep (v1.45.0)
==============================================================
Empirical evaluation of the v1.45.0 Abductive Engine:
- Pillar 1: Hypothesis-First Abduction
- Pillar 2: Clean-Slate Backtracking & Branch Pruning
- Pillar 3: General Visual Coordinate Utilities (Spatial Anchors)

Across all 4 Model Tiers on RTX 5080 Laptop GPU:
- Tier 0: Gemma 4 26B-A4B Flagship MoE (18 layers GPU offloaded)
- Tier 1: Gemma 4 12B Dense Companion (99 layers GPU offloaded)
- Tier 2: Gemma 4 E4B Edge Dense (99 layers GPU offloaded)
- Tier 3: Gemma 4 E2B Ultra-Compact Edge (99 layers GPU offloaded)

Standardized Battery (44 tasks total per model tier = 176 task evaluations):
1. Spatial: ConceptARC 16 Tasks (1 per concept, fresh synthesis, cache disabled)
2. Code:    CRUXEval-Input Smoke (10 problems, Arm A direct vs Arm B CEGIS repair)
3. Logic:   ZebraLogic 8 Puzzles (2 per search-space tier: 2x2, 3x3, 4x4, 5x5)
4. Math:    MATH-500 MathCAS (10 problems, Arm A control vs Arm B sketch + CAS)

Zero-Any typing invariant strictly enforced per D-AUD-01.
Zero Docker dependency (in-process watchdog sandbox + native subprocesses).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Final

import httpx
import psutil

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

logger = logging.getLogger("four_tier_sweep")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUTPUT_DIR: Final[Path] = REPO_ROOT / "logs" / "test_reports" / "comparative_four_tier"
PYTHON_EXE: Final[str] = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
LLAMA_EXE: Final[Path] = Path(r"C:\ProjectLucca\app\llama-server\llama-server.exe")

@dataclass(frozen=True)
class ModelTierConfig:
    key: str
    display_name: str
    model_path: str
    ngl: int
    ctx_size: int
    spec_type: str


TIER_CONFIGS: Final[dict[str, ModelTierConfig]] = {
    "tier0": ModelTierConfig(
        key="tier0",
        display_name="Tier 0 (Flagship 26B-A4B)",
        model_path=r"C:\ProjectLucca\models\llm\gemma-4-26B-A4B-it-heretic.Q6_K.gguf",
        ngl=18,
        ctx_size=131072,
        spec_type="ngram-mod",
    ),
    "tier1": ModelTierConfig(
        key="tier1",
        display_name="Tier 1 (Companion 12B)",
        model_path=r"C:\ProjectLucca\models\llm\gemma-4-12b-heretic-Q6_K.gguf",
        ngl=99,
        ctx_size=32768,
        spec_type="none",
    ),
    "tier2": ModelTierConfig(
        key="tier2",
        display_name="Tier 2 (Edge E4B)",
        model_path=r"C:\ProjectLucca\models\llm\gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf",
        ngl=99,
        ctx_size=32768,
        spec_type="none",
    ),
    "tier3": ModelTierConfig(
        key="tier3",
        display_name="Tier 3 (Edge E2B)",
        model_path=r"C:\ProjectLucca\models\llm\Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf",
        ngl=99,
        ctx_size=32768,
        spec_type="none",
    ),
}


def stop_running_server() -> None:
    """Terminates any active llama-server process cleanly."""
    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = str(p.info.get("name") or "").lower()
            if "llama-server" in name:
                p.terminate()
                try:
                    p.wait(timeout=3.0)
                except psutil.TimeoutExpired:
                    p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(2.0)


def get_active_model_path() -> str | None:
    """Queries /v1/models on local llama-server to find currently loaded model."""
    try:
        resp = httpx.get("http://127.0.0.1:8080/v1/models", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            if items and "id" in items[0]:
                return str(items[0]["id"])
    except Exception:
        pass
    return None


def ensure_server_for_tier(cfg: ModelTierConfig) -> None:
    """Ensures that the required model is loaded and ready on port 8080."""
    active_model = get_active_model_path()
    if active_model and Path(active_model).resolve() == Path(cfg.model_path).resolve():
        print(f"[REUSE] {cfg.display_name} is already active on port 8080.")
        return

    print(f"[SWITCH] Stopping existing server and starting {cfg.display_name}...")
    stop_running_server()

    cmd: list[str] = [
        str(LLAMA_EXE),
        "--model", cfg.model_path,
        "--n-gpu-layers", str(cfg.ngl),
        "--ctx-size", str(cfg.ctx_size),
        "--cache-type-k", "q8_0",
        "--cache-type-v", "q8_0",
        "--cache-ram", "4096",
        "--parallel", "1",
        "--flash-attn", "on",
        "--host", "127.0.0.1",
        "--port", "8080",
        "--no-webui",
        "--jinja",
    ]
    if cfg.spec_type != "none":
        cmd.extend(["--spec-type", cfg.spec_type])

    log_file = REPO_ROOT / "logs" / "llama-server.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fp = open(log_file, "ab")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    subprocess.Popen(cmd, stdout=fp, stderr=subprocess.STDOUT, creationflags=creationflags)

    # Poll /health until online
    deadline = time.time() + 90.0
    while time.time() < deadline:
        try:
            r = httpx.get("http://127.0.0.1:8080/health", timeout=1.5)
            if r.status_code == 200 and r.json().get("status") == "ok":
                print(f"[ONLINE] {cfg.display_name} is healthy and responsive.")
                return
        except Exception:
            pass
        time.sleep(1.5)

    raise TimeoutError(f"Failed to start llama-server for {cfg.display_name} within 90 seconds.")


@dataclass
class TierBenchmarkResults:
    tier_key: str
    display_name: str
    concept_arc_train_pct: float
    concept_arc_test_pct: float
    concept_arc_train_solved: int
    concept_arc_test_solved: int
    concept_arc_total: int
    cruxeval_direct_pct: float
    cruxeval_cegis_pct: float
    cruxeval_cegis_lift_pp: float
    cruxeval_total: int
    zebra_logic_direct_pct: float
    zebra_logic_think_pct: float
    zebra_logic_z3_pct: float
    zebra_logic_total: int
    math500_direct_pct: float
    math500_cas_pct: float
    math500_lift_pp: float
    math500_total: int
    total_elapsed_s: float


def run_benchmark_for_tier(tier_key: str) -> TierBenchmarkResults:
    cfg = TIER_CONFIGS[tier_key]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_server_for_tier(cfg)

    t0_tier = time.perf_counter()
    print("\n" + "=" * 80)
    print(f"RUNNING STANDARDIZED BENCHMARK BATTERY FOR {cfg.display_name.upper()}")
    print("=" * 80)

    # 1. ConceptARC 16 Concepts (1 task each, pure synthesis, no cache)
    ca_report_path = OUTPUT_DIR / f"concept_arc_{tier_key}.json"
    print(f"\n[1/4] Running ConceptARC 16-Concept Sweep on {cfg.display_name}...")
    ca_cmd = [
        PYTHON_EXE,
        "scripts/run_concept_arc_full.py",
        "--limit-per-concept", "1",
        "--no-resume",
        "--disable-cache",
        "--output", str(ca_report_path),
    ]
    subprocess.run(ca_cmd, cwd=str(REPO_ROOT), check=True)
    ca_data = json.loads(ca_report_path.read_text(encoding="utf-8"))
    ca_train_solved = int(ca_data.get("train_solved", 0))
    ca_test_solved = int(ca_data.get("test_solved", 0))
    ca_total = int(ca_data.get("total_tasks", 16))
    ca_train_pct = float(ca_data.get("train_accuracy", 0.0)) * 100.0
    ca_test_pct = float(ca_data.get("test_accuracy", 0.0)) * 100.0

    # 2. CRUXEval-Input Smoke (10 items)
    crux_report_path = OUTPUT_DIR / f"cruxeval_smoke_{tier_key}.json"
    print(f"\n[2/4] Running CRUXEval-Input Smoke on {cfg.display_name}...")
    crux_cmd = [
        PYTHON_EXE,
        "scripts/run_cruxeval_input.py",
        "--split", "smoke",
        "--output-json", str(crux_report_path),
    ]
    subprocess.run(crux_cmd, cwd=str(REPO_ROOT), check=True)
    crux_data = json.loads(crux_report_path.read_text(encoding="utf-8"))
    crux_summary = crux_data.get("summary", {})
    crux_direct_pct = float(crux_summary.get("arm_a_rate", 0.0)) * 100.0
    crux_cegis_pct = float(crux_summary.get("arm_b_rate", 0.0)) * 100.0
    crux_lift = float(crux_summary.get("net_lift_pp", 0.0))
    crux_total = int(crux_data.get("total_problems", 10))

    # 3. ZebraLogic Sweep (2 per tier = 8 items)
    zebra_report_path = OUTPUT_DIR / f"zebra_logic_{tier_key}.json"
    print(f"\n[3/4] Running ZebraLogic Sweep on {cfg.display_name}...")
    zebra_cmd = [
        PYTHON_EXE,
        "scripts/run_zebra_logic_sweep.py",
        "--samples-per-tier", "2",
        "--output", str(zebra_report_path),
    ]
    subprocess.run(zebra_cmd, cwd=str(REPO_ROOT), check=True)
    zebra_data = json.loads(zebra_report_path.read_text(encoding="utf-8"))
    z_probs = zebra_data.get("problems", [])
    z_total = len(z_probs)
    z_direct_ok = sum(1 for p in z_probs if p.get("direct_ok"))
    z_think_ok = sum(1 for p in z_probs if p.get("thinking_ok"))
    z_llm_z3_ok = sum(1 for p in z_probs if p.get("llm_z3_ok"))
    z_direct_pct = (z_direct_ok / z_total * 100.0) if z_total > 0 else 0.0
    z_think_pct = (z_think_ok / z_total * 100.0) if z_total > 0 else 0.0
    z_z3_pct = (z_llm_z3_ok / z_total * 100.0) if z_total > 0 else 0.0

    # 4. MATH-500 MathCAS (10 items)
    math_report_path = OUTPUT_DIR / f"math500_{tier_key}.json"
    print(f"\n[4/4] Running MATH-500 MathCAS on {cfg.display_name}...")
    math_cmd = [
        PYTHON_EXE,
        "scripts/run_math500_sketch.py",
        "--samples", "10",
        "--output", str(math_report_path),
    ]
    subprocess.run(math_cmd, cwd=str(REPO_ROOT), check=True)
    math_data = json.loads(math_report_path.read_text(encoding="utf-8"))
    m_arm_a = math_data.get("arm_a_control", {})
    m_arm_b = math_data.get("arm_b_augmented", {})
    m_total = int(math_data.get("total_problems", 10))
    m_direct_pct = float(m_arm_a.get("pass_rate", 0.0)) * 100.0
    m_cas_pct = float(m_arm_b.get("pass_rate", 0.0)) * 100.0
    m_lift = m_cas_pct - m_direct_pct

    elapsed = time.perf_counter() - t0_tier
    print(f"\nCompleted {cfg.display_name} in {elapsed:.1f}s.")

    return TierBenchmarkResults(
        tier_key=tier_key,
        display_name=cfg.display_name,
        concept_arc_train_pct=ca_train_pct,
        concept_arc_test_pct=ca_test_pct,
        concept_arc_train_solved=ca_train_solved,
        concept_arc_test_solved=ca_test_solved,
        concept_arc_total=ca_total,
        cruxeval_direct_pct=crux_direct_pct,
        cruxeval_cegis_pct=crux_cegis_pct,
        cruxeval_cegis_lift_pp=crux_lift,
        cruxeval_total=crux_total,
        zebra_logic_direct_pct=z_direct_pct,
        zebra_logic_think_pct=z_think_pct,
        zebra_logic_z3_pct=z_z3_pct,
        zebra_logic_total=z_total,
        math500_direct_pct=m_direct_pct,
        math500_cas_pct=m_cas_pct,
        math500_lift_pp=m_lift,
        math500_total=m_total,
        total_elapsed_s=elapsed,
    )


def print_comparison_matrix(results: list[TierBenchmarkResults]) -> None:
    print("\n" + "=" * 105)
    print("        PROJECT LUCCA — FOUR-TIER EMPIRICAL REASONING MATRIX (v1.45.0 ABDUCTIVE ENGINE)")
    print("=" * 105)
    print(
        f"{'Model Tier':<26} | {'ConceptARC (Test)':<18} | {'CRUXEval (CEGIS)':<17} | "
        f"{'ZebraLogic (Z3)':<17} | {'MATH-500 (CAS)':<17}"
    )
    print("-" * 105)

    for r in results:
        ca_str = f"{r.concept_arc_test_solved}/{r.concept_arc_total} ({r.concept_arc_test_pct:.1f}%)"
        crux_str = f"{r.cruxeval_cegis_pct:.1f}% (+{r.cruxeval_cegis_lift_pp:+.0f}pp)"
        z_str = f"{r.zebra_logic_z3_pct:.1f}% (Dir:{r.zebra_logic_direct_pct:.0f}%)"
        m_str = f"{r.math500_cas_pct:.1f}% (+{r.math500_lift_pp:+.0f}pp)"
        print(f"{r.display_name:<26} | {ca_str:<18} | {crux_str:<17} | {z_str:<17} | {m_str:<17}")

    print("=" * 105 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Four-Tier Comparative Benchmark Sweep Runner")
    parser.add_argument(
        "--tier",
        choices=["all", "tier0", "tier1", "tier2", "tier3"],
        default="all",
        help="Model tier to evaluate (default: all)",
    )
    parser.add_argument(
        "--no-restore-tier0",
        action="store_true",
        help="Do not restore Tier 0 flagship server upon completion",
    )
    args = parser.parse_args()

    selected_tiers = (
        ["tier0", "tier1", "tier2", "tier3"] if args.tier == "all" else [args.tier]
    )

    all_results: list[TierBenchmarkResults] = []
    matrix_file = OUTPUT_DIR / f"master_four_tier_matrix_{int(time.time())}.json"

    try:
        for t_key in selected_tiers:
            res = run_benchmark_for_tier(t_key)
            all_results.append(res)
    finally:
        # Restore Tier 0 flagship server if we evaluated other models and wasn't disabled
        if not args.no_restore_tier0 and ("tier1" in selected_tiers or "tier2" in selected_tiers or "tier3" in selected_tiers):
            print("\n[RESTORATION] Restoring resident Tier 0 (Flagship 26B-A4B) server...")
            try:
                ensure_server_for_tier(TIER_CONFIGS["tier0"])
                print("[RESTORATION OK] Tier 0 resident daemon restored on port 8080.")
            except Exception as exc:
                print(f"[RESTORATION WARNING] Could not restore Tier 0 server: {exc}")

    # Output master matrix
    print_comparison_matrix(all_results)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    matrix_data = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "evaluated_tiers": [asdict(r) for r in all_results],
    }
    matrix_file.write_text(json.dumps(matrix_data, indent=2), encoding="utf-8")
    print(f"[AUDIT SEALED] Master comparative matrix written to: {matrix_file}")


if __name__ == "__main__":
    main()
