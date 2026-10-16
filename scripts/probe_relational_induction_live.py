"""
Project Lucca — Live Relational Induction Probe
===============================================
Rigorous live-model probe of Organ A relational induction on resident Tier 0 LLM.
Strictly evaluates Model 4's Two-Fixture Specification:
1. Closed Ring + Enclosed Blob -> Target Output: [[1]]
2. Open U-shape + Concavity Blob -> Target Output: [[0]] (Mandatory Disagreement Invariant)

Evaluates 3 runs per fixture across varying temperatures [0.1, 0.2, 0.35].
Scores the emitted source code:
- Did it call `in_cavity(...)`?
- Did it fall back to AABB `bbox` / `during`?
- Did it write raw nested `grid[i][j]` loops?
- Did it execute and produce the correct output?

Zero benchmark dataset strings per anti-benchmax contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.reasoning.cegis_unshackled import (
    UnshackledCEGISEngine,
    execute_unshackled_python,
)
from lucca.reasoning.relational import above, below, externally_connected, in_cavity, left_of, part_of, right_of
from lucca.reasoning.spatial_anchors import connected_components

OUTPUT_FILE: Final[Path] = REPO_ROOT / "logs" / "test_reports" / "probe_relational_induction_live.json"

# ==============================================================================
# Fixture 1: Closed Ring Enclosing a Blob
# ==============================================================================
RING_FIXTURE: Final[dict[str, Any]] = {
    "name": "closed_ring_enclosure",
    "train": [
        {
            # 5x5 blue ring (1) with green blob (2) at (2,2)
            "input": [
                [1, 1, 1, 1, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 2, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 1, 1, 1, 1],
            ],
            "output": [[1]],
        },
        {
            # 7x7 red ring (2) with yellow blob (4) at (3,3)
            "input": [
                [2, 2, 2, 2, 2, 2, 2],
                [2, 0, 0, 0, 0, 0, 2],
                [2, 0, 0, 0, 0, 0, 2],
                [2, 0, 0, 4, 0, 0, 2],
                [2, 0, 0, 0, 0, 0, 2],
                [2, 0, 0, 0, 0, 0, 2],
                [2, 2, 2, 2, 2, 2, 2],
            ],
            "output": [[1]],
        },
    ],
    "test": [
        {
            # 6x6 magenta ring (6) with cyan blob (8) at (2,2)
            "input": [
                [6, 6, 6, 6, 6, 6],
                [6, 0, 0, 0, 0, 6],
                [6, 0, 8, 0, 0, 6],
                [6, 0, 0, 0, 0, 6],
                [6, 0, 0, 0, 0, 6],
                [6, 6, 6, 6, 6, 6],
            ],
            "output": [[1]],
        }
    ],
}

# ==============================================================================
# Fixture 2: Open U-Shape with Blob in Concavity (MANDATORY DISAGREEMENT)
# ==============================================================================
U_SHAPE_FIXTURE: Final[dict[str, Any]] = {
    "name": "u_shape_concavity_open",
    "train": [
        {
            # 5x5 blue U-shape (1, open to top) with green blob (2) in concavity
            "input": [
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 2, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 1, 1, 1, 1],
            ],
            "output": [[0]],
        },
        {
            # 5x5 red C-shape (2, open to right) with yellow blob (4) in concavity
            "input": [
                [2, 2, 2, 2, 2],
                [2, 0, 0, 0, 0],
                [2, 0, 4, 0, 0],
                [2, 0, 0, 0, 0],
                [2, 2, 2, 2, 2],
            ],
            "output": [[0]],
        },
    ],
    "test": [
        {
            # 6x6 yellow U-shape (4, open to bottom) with cyan blob (8) in concavity
            "input": [
                [4, 4, 4, 4, 4, 4],
                [4, 0, 0, 0, 0, 4],
                [4, 0, 8, 0, 0, 4],
                [4, 0, 0, 0, 0, 4],
                [4, 0, 0, 0, 0, 4],
                [4, 0, 0, 0, 0, 4],  # bottom open
            ],
            "output": [[0]],
        }
    ],
}

# ==============================================================================
# Fixture 3 (Ugly 1): Rotated U-Shapes (90° / 180° / 270°) Concavity Open
# ==============================================================================
U_SHAPE_ROTATED_FIXTURE: Final[dict[str, Any]] = {
    "name": "u_shape_rotated_concavity",
    "train": [
        {
            # 5x5 blue C-shape (1, open to left, 270°) with green blob (2) in concavity
            "input": [
                [1, 1, 1, 1, 1],
                [0, 0, 0, 0, 1],
                [0, 2, 0, 0, 1],
                [0, 0, 0, 0, 1],
                [1, 1, 1, 1, 1],
            ],
            "output": [[0]],
        },
        {
            # 6x6 red inverted U (2, open to bottom, 180°) with yellow blob (4) in concavity
            "input": [
                [2, 2, 2, 2, 2, 2],
                [2, 0, 0, 0, 0, 2],
                [2, 0, 4, 0, 0, 2],
                [2, 0, 0, 0, 0, 2],
                [2, 0, 0, 0, 0, 2],
                [0, 0, 0, 0, 0, 0],
            ],
            "output": [[0]],
        },
    ],
    "test": [
        {
            # 7x7 yellow shape open to right (4, 90°) with cyan blob (8) in concavity
            "input": [
                [4, 4, 4, 4, 4, 4, 4],
                [4, 0, 0, 0, 0, 0, 0],
                [4, 0, 0, 0, 0, 0, 0],
                [4, 0, 8, 0, 0, 0, 0],
                [4, 0, 0, 0, 0, 0, 0],
                [4, 0, 0, 0, 0, 0, 0],
                [4, 4, 4, 4, 4, 4, 4],
            ],
            "output": [[0]],
        }
    ],
}

# ==============================================================================
# Fixture 4 (Ugly 2): Blob on Arm of U (Touching Boundary Externally, Not in Dent)
# ==============================================================================
BLOB_ON_ARM_FIXTURE: Final[dict[str, Any]] = {
    "name": "u_shape_blob_on_outer_arm",
    "train": [
        {
            # 7x7 blue U-shape (1, open to top) with green blob (2) touching outer left arm
            "input": [
                [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 1, 0, 0, 1, 0],
                [0, 0, 1, 0, 0, 1, 0],
                [0, 2, 1, 0, 0, 1, 0],
                [0, 0, 1, 0, 0, 1, 0],
                [0, 0, 1, 1, 1, 1, 0],
                [0, 0, 0, 0, 0, 0, 0],
            ],
            "output": [[0]],
        },
        {
            # 7x7 red U-shape (2, open to bottom) with yellow blob (4) touching outer top wall
            "input": [
                [0, 0, 0, 4, 0, 0, 0],
                [0, 2, 2, 2, 2, 2, 0],
                [0, 2, 0, 0, 0, 2, 0],
                [0, 2, 0, 0, 0, 2, 0],
                [0, 2, 0, 0, 0, 2, 0],
                [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0],
            ],
            "output": [[0]],
        },
    ],
    "test": [
        {
            # 8x8 yellow U-shape (4, open to right) with cyan blob (8) touching outer bottom arm
            "input": [
                [0, 0, 0, 0, 0, 0, 0, 0],
                [0, 4, 4, 4, 4, 4, 4, 0],
                [0, 4, 0, 0, 0, 0, 0, 0],
                [0, 4, 0, 0, 0, 0, 0, 0],
                [0, 4, 0, 0, 0, 0, 0, 0],
                [0, 4, 4, 4, 4, 4, 4, 0],
                [0, 0, 0, 8, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0],
            ],
            "output": [[0]],
        }
    ],
}

# ==============================================================================
# Fixture 5 (Ugly 3): Compound Grid (Two Components, Only One Enclosed)
# ==============================================================================
COMPOUND_FIXTURE: Final[dict[str, Any]] = {
    "name": "compound_ring_and_u_shape",
    "train": [
        {
            # 6x10: Closed blue ring (1) enclosing green blob (2) at (2,2)
            # PLUS open red U-shape (3) with yellow blob (4) in concavity at (3,8)
            "input": [
                [1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
                [1, 0, 0, 0, 1, 0, 3, 0, 0, 3],
                [1, 0, 2, 0, 1, 0, 3, 0, 0, 3],
                [1, 0, 0, 0, 1, 0, 3, 0, 4, 3],
                [1, 1, 1, 1, 1, 0, 3, 3, 3, 3],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ],
            "output": [[2]],
        },
        {
            # 6x10: Two open U-shapes, NO closed ring!
            # Magenta U-shape (6) with cyan blob (8) in concavity at (2,2)
            # PLUS gray U-shape (5) with orange blob (7) in concavity at (3,8)
            "input": [
                [6, 0, 0, 0, 6, 0, 0, 0, 0, 0],
                [6, 0, 0, 0, 6, 0, 5, 0, 0, 5],
                [6, 0, 8, 0, 6, 0, 5, 0, 0, 5],
                [6, 0, 0, 0, 6, 0, 5, 0, 7, 5],
                [6, 6, 6, 6, 6, 0, 5, 5, 5, 5],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ],
            "output": [[0]],
        },
    ],
    "test": [
        {
            # 6x10: Open yellow U-shape (4) with red blob (2) at (3,2)
            # PLUS closed cyan ring (8) enclosing magenta blob (6) at (2,8)
            "input": [
                [4, 0, 0, 0, 4, 0, 8, 8, 8, 8],
                [4, 0, 0, 0, 4, 0, 8, 0, 0, 8],
                [4, 0, 0, 0, 4, 0, 8, 0, 6, 8],
                [4, 0, 2, 0, 4, 0, 8, 0, 0, 8],
                [4, 4, 4, 4, 4, 0, 8, 8, 8, 8],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ],
            "output": [[6]],
        }
    ],
}


@dataclass
class ProbeRunResult:
    fixture_name: str
    run_idx: int
    temperature: float
    emitted_code: str
    emitted_hypothesis: str | None
    uses_in_cavity: bool
    uses_relational_primitives: bool
    uses_bbox_fallback: bool
    uses_raw_index_loops: bool
    execution_success: bool
    test_passed: bool
    predicted_output: list[list[int]] | None
    execution_error: str | None
    elapsed_ms: float


def analyze_source_code(code: str) -> tuple[bool, bool, bool, bool]:
    """Analyzes emitted Python code for relational primitives vs regressions."""
    uses_in_cavity = bool(re.search(r"\bin_cavity\s*\(", code))

    relational_tokens = ["above", "below", "left_of", "right_of", "part_of", "externally_connected"]
    uses_relational = uses_in_cavity or any(bool(re.search(rf"\b{t}\s*\(", code)) for t in relational_tokens)

    # Check for AABB / bbox fallback
    uses_bbox = bool(re.search(r"\b(?:bbox|min_r|max_r|min_c|max_c)\b", code)) and not uses_in_cavity

    # Check for raw nested grid[i][j] index loops (excluding component iterations)
    uses_raw_loops = bool(re.search(r"grid\[\w+\]\[\w+\]", code)) or bool(
        re.search(r"range\s*\(\s*(?:len\s*\(\s*grid|h|w|height|width|rows|cols)\b", code, re.IGNORECASE)
    )

    return uses_in_cavity, uses_relational, uses_bbox, uses_raw_loops


def run_single_probe(
    engine: UnshackledCEGISEngine,
    fixture: dict[str, Any],
    run_idx: int,
    temperature: float,
) -> ProbeRunResult:
    t0 = time.perf_counter()
    code, hypothesis, _ = engine.synthesize_turn_1(
        task_data=fixture,
        temperature=temperature,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    uses_in_cavity, uses_relational, uses_bbox, uses_raw_loops = analyze_source_code(code)

    # Execute on test case
    test_input = fixture["test"][0]["input"]
    expected_output = fixture["test"][0]["output"]

    exec_outcome = execute_unshackled_python(code, test_input)
    test_passed = exec_outcome.success and (exec_outcome.output_grid == expected_output)

    return ProbeRunResult(
        fixture_name=fixture["name"],
        run_idx=run_idx,
        temperature=temperature,
        emitted_code=code,
        emitted_hypothesis=hypothesis,
        uses_in_cavity=uses_in_cavity,
        uses_relational_primitives=uses_relational,
        uses_bbox_fallback=uses_bbox,
        uses_raw_index_loops=uses_raw_loops,
        execution_success=exec_outcome.success,
        test_passed=test_passed,
        predicted_output=exec_outcome.output_grid,
        execution_error=exec_outcome.error_message,
        elapsed_ms=elapsed_ms,
    )


def main() -> None:
    print("\n" + "=" * 80)
    print("   PROJECT LUCCA — LIVE RELATIONAL INDUCTION PROBE (TIER 0)")
    print("   Evaluating Organ A Live Emission & Model 4 Disagreement Invariant")
    print("=" * 80 + "\n")

    fixtures_to_run: list[dict[str, Any]]
    if "--ugly-only" in sys.argv:
        fixtures_to_run = [U_SHAPE_ROTATED_FIXTURE, BLOB_ON_ARM_FIXTURE, COMPOUND_FIXTURE]
        print("--> Mode: Running 3 UGLY FIXTURES ONLY")
    elif "--baseline-only" in sys.argv:
        fixtures_to_run = [RING_FIXTURE, U_SHAPE_FIXTURE]
        print("--> Mode: Running 2 BASELINE FIXTURES ONLY")
    else:
        fixtures_to_run = [
            RING_FIXTURE,
            U_SHAPE_FIXTURE,
            U_SHAPE_ROTATED_FIXTURE,
            BLOB_ON_ARM_FIXTURE,
            COMPOUND_FIXTURE,
        ]
        print(f"--> Mode: Running FULL BATTERY ({len(fixtures_to_run)} fixtures)")

    engine = UnshackledCEGISEngine(timeout_seconds=300.0)
    temperatures = [0.1, 0.2, 0.35]
    results: list[ProbeRunResult] = []

    for fixture in fixtures_to_run:
        print(f"\n[{fixture['name'].upper()}] Running 3 Live Synthesis Passes...")
        for run_idx, temp in enumerate(temperatures, start=1):
            print(f"  --> Run {run_idx}/3 (temp={temp}) ... ", end="", flush=True)
            res = run_single_probe(engine, fixture, run_idx, temp)
            results.append(res)

            status = "PASS" if res.test_passed else "FAIL"
            cavity_str = "in_cavity: YES" if res.uses_in_cavity else "in_cavity: NO"
            loop_str = "raw_loops: YES" if res.uses_raw_index_loops else "raw_loops: NO"
            bbox_str = "bbox_fallback: YES" if res.uses_bbox_fallback else "bbox_fallback: NO"

            print(f"[{status}] | {cavity_str} | {bbox_str} | {loop_str} ({res.elapsed_ms:.0f}ms)")
            print(f"      Predicted: {res.predicted_output} | Expected: {fixture['test'][0]['output']}")

    # Save to disk
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "results": [asdict(r) for r in results],
            },
            f,
            indent=2,
        )

    print("\n" + "=" * 80)
    print("PROBE RESULTS SUMMARY:")
    print("=" * 80)
    passed_count = sum(1 for r in results if r.test_passed)
    total_count = len(results)
    cavity_count = sum(1 for r in results if r.uses_in_cavity)
    bbox_count = sum(1 for r in results if r.uses_bbox_fallback)
    print(f"Overall Pass Rate: {passed_count}/{total_count} ({passed_count/total_count*100:.1f}%)")
    print(f"Synthesized in_cavity: {cavity_count}/{total_count} ({cavity_count/total_count*100:.1f}%)")
    print(f"AABB Bounding Box Fallback: {bbox_count}/{total_count} ({bbox_count/total_count*100:.1f}%)")

    for r in results:
        print(f"\n--- {r.fixture_name} (Run {r.run_idx}, temp={r.temperature}) ---")
        print(f"Output: {r.predicted_output} (Test Passed: {r.test_passed})")
        print(f"Emitted Code:\n{r.emitted_code}\n")


if __name__ == "__main__":
    main()
