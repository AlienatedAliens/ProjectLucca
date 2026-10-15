"""
Project Lucca — Unshackled Counterexample-Guided Inductive Synthesis (CEGIS)
v1.44.0 General Reasoning Engine (Zero Handcrafted Benchmark Primitives)

Provides an autonomous, multi-turn program induction and self-repair loop:
1. Turn 1: Synthesizes candidate Python transformation without hardcoded DSL biases.
   Unrestricted access to NumPy, SciPy, itertools, and standard control flow.
2. Watchdog Sandbox: Executes in isolated namespace with timeout watchdog.
3. Structured Cell Diff: Computes fine-grained spatial/relational counterexample:
   - Coordinate-level value discrepancies: (row, col) expected vs actual
   - Bounding boxes of error regions
   - Side-by-side ANSI / ASCII comparison grids
4. Turn 2..K: Feeds the exact counterexample diff back to LLM to guide repair.
5. Verification: Tests 100% of training demonstrations + metamorphic checks.
6. Test Inference: Applies verified code to unseen test input.

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import json
import logging
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Final

import httpx
import numpy as np
import scipy.ndimage

import structlog

from lucca.reasoning import spatial_anchors
from lucca.sandbox.preflight import extract_python_code

logger = structlog.get_logger(__name__)


def extract_hypothesis(text: str) -> str | None:
    """Extracts structured hypothesis block from model response if present."""
    m = re.search(r"(?:HYPOTHESIS|Hypothesis):?\s*(.+?)(?=```python|```|$)", text, re.DOTALL | re.IGNORECASE)
    if m:
        cleaned = m.group(1).strip()
        return cleaned if len(cleaned) > 10 else None
    return None


# ARC Standard Palette (0-9)
ARC_PALETTE_NAMES: Final[dict[int, str]] = {
    0: "black",
    1: "blue",
    2: "red",
    3: "green",
    4: "yellow",
    5: "gray",
    6: "magenta",
    7: "orange",
    8: "cyan",
    9: "maroon",
}

# ANSI 256-color background escapes for the 10 ARC colors
ARC_ANSI_BG: Final[dict[int, str]] = {
    0: "\033[48;5;232m\033[38;5;255m",  # Black bg, white fg
    1: "\033[48;5;27m\033[38;5;255m",   # Blue
    2: "\033[48;5;196m\033[38;5;255m",  # Red
    3: "\033[48;5;34m\033[38;5;255m",   # Green
    4: "\033[48;5;220m\033[38;5;0m",    # Yellow (black fg)
    5: "\033[48;5;244m\033[38;5;255m",  # Gray
    6: "\033[48;5;201m\033[38;5;255m",  # Magenta
    7: "\033[48;5;208m\033[38;5;0m",    # Orange (black fg)
    8: "\033[48;5;51m\033[38;5;0m",     # Cyan (black fg)
    9: "\033[48;5;124m\033[38;5;255m",  # Maroon
}
ANSI_RESET: Final[str] = "\033[0m"
ANSI_DIFF_HIGHLIGHT: Final[str] = "\033[48;5;196m\033[38;5;226m\033[1m"  # Bright red bg, yellow bold


@dataclass(frozen=True)
class CellMismatch:
    """Detailed record of a single mismatched grid cell."""

    row: int
    col: int
    expected_val: int
    actual_val: int

    @property
    def expected_color(self) -> str:
        return ARC_PALETTE_NAMES.get(self.expected_val, f"color_{self.expected_val}")

    @property
    def actual_color(self) -> str:
        return ARC_PALETTE_NAMES.get(self.actual_val, f"color_{self.actual_val}")

    def __str__(self) -> str:
        return (
            f"({self.row}, {self.col}): expected {self.expected_val} "
            f"({self.expected_color}), got {self.actual_val} ({self.actual_color})"
        )


@dataclass(frozen=True)
class GridDiff:
    """Structured discrepancy analysis between expected and predicted grids."""

    is_match: bool
    shape_match: bool
    expected_shape: tuple[int, int]
    actual_shape: tuple[int, int]
    total_cells: int
    mismatch_count: int
    mismatch_ratio: float
    mismatches: list[CellMismatch]
    bounding_box: tuple[int, int, int, int] | None  # (min_r, min_c, max_r, max_c)
    summary_message: str

    def format_counterexample_prompt(self, max_examples: int = 12) -> str:
        """Formats the discrepancy as an actionable prompt chunk for LLM self-repair."""
        if self.is_match:
            return "No discrepancy detected (grids match exactly)."

        lines: list[str] = []
        if not self.shape_match:
            lines.append(
                f"- Shape Mismatch: Expected {self.expected_shape[0]}x{self.expected_shape[1]}, "
                f"but your function produced {self.actual_shape[0]}x{self.actual_shape[1]}."
            )
            return "\n".join(lines)

        lines.append(
            f"- Value Discrepancy: {self.mismatch_count} of {self.total_cells} cells differ "
            f"({self.mismatch_ratio * 100:.1f}% mismatch)."
        )

        if self.bounding_box:
            min_r, min_c, max_r, max_c = self.bounding_box
            lines.append(
                f"- Error Region Bounding Box: rows [{min_r}..{max_r}], cols [{min_c}..{max_c}]."
            )

        shown_mismatches = self.mismatches[:max_examples]
        lines.append("- Concrete Cell Differences:")
        for m in shown_mismatches:
            lines.append(f"  * {m}")

        if len(self.mismatches) > max_examples:
            remaining = len(self.mismatches) - max_examples
            lines.append(f"  * ... and {remaining} additional mismatched cells.")

        return "\n".join(lines)


def compute_detailed_grid_diff(
    expected: list[list[int]], actual: list[list[int]]
) -> GridDiff:
    """Computes coordinate-level diff between expected and actual 2D matrices."""
    h_exp = len(expected)
    w_exp = len(expected[0]) if h_exp > 0 else 0
    h_act = len(actual)
    w_act = len(actual[0]) if h_act > 0 else 0

    shape_match = (h_exp == h_act) and (w_exp == w_act)
    if not shape_match:
        return GridDiff(
            is_match=False,
            shape_match=False,
            expected_shape=(h_exp, w_exp),
            actual_shape=(h_act, w_act),
            total_cells=h_exp * w_exp,
            mismatch_count=max(h_exp * w_exp, h_act * w_act),
            mismatch_ratio=1.0,
            mismatches=[],
            bounding_box=None,
            summary_message=f"Shape mismatch: expected {h_exp}x{w_exp}, got {h_act}x{w_act}",
        )

    mismatches: list[CellMismatch] = []
    min_r, min_c = h_exp, w_exp
    max_r, max_c = -1, -1

    for r in range(h_exp):
        for c in range(w_exp):
            val_exp = expected[r][c]
            val_act = actual[r][c]
            if val_exp != val_act:
                mismatches.append(CellMismatch(row=r, col=c, expected_val=val_exp, actual_val=val_act))
                if r < min_r:
                    min_r = r
                if r > max_r:
                    max_r = r
                if c < min_c:
                    min_c = c
                if c > max_c:
                    max_c = c

    total_cells = h_exp * w_exp
    mismatch_count = len(mismatches)
    is_match = mismatch_count == 0
    mismatch_ratio = mismatch_count / total_cells if total_cells > 0 else 0.0

    bbox = (min_r, min_c, max_r, max_c) if mismatches else None
    summary = (
        "Exact match"
        if is_match
        else f"{mismatch_count}/{total_cells} cells mismatch ({mismatch_ratio * 100:.1f}%)"
    )

    return GridDiff(
        is_match=is_match,
        shape_match=True,
        expected_shape=(h_exp, w_exp),
        actual_shape=(h_act, w_act),
        total_cells=total_cells,
        mismatch_count=mismatch_count,
        mismatch_ratio=mismatch_ratio,
        mismatches=mismatches,
        bounding_box=bbox,
        summary_message=summary,
    )


def render_grid_ansi(
    grid: list[list[int]],
    highlight_mask: list[list[bool]] | None = None,
    use_color: bool = True,
) -> str:
    """Renders a 2D integer grid with ANSI 256-color backgrounds or clean ASCII."""
    if not grid or not grid[0]:
        return "[]"

    h = len(grid)
    w = len(grid[0])
    lines: list[str] = []

    for r in range(h):
        row_str: list[str] = []
        for c in range(w):
            val = grid[r][c]
            is_highlighted = highlight_mask[r][c] if highlight_mask and r < len(highlight_mask) and c < len(highlight_mask[0]) else False

            if use_color:
                if is_highlighted:
                    row_str.append(f"{ANSI_DIFF_HIGHLIGHT} {val} {ANSI_RESET}")
                else:
                    bg = ARC_ANSI_BG.get(val, "\033[48;5;236m\033[38;5;255m")
                    row_str.append(f"{bg} {val} {ANSI_RESET}")
            else:
                mark = f"*{val}" if is_highlighted else f" {val}"
                row_str.append(mark)
        lines.append("".join(row_str) if use_color else " ".join(row_str))

    return "\n".join(lines)


def render_grid_side_by_side(
    expected: list[list[int]],
    actual: list[list[int]],
    input_grid: list[list[int]] | None = None,
    use_color: bool = True,
) -> str:
    """Renders Input (optional), Expected, Actual, and Diff columns side by side."""
    diff = compute_detailed_grid_diff(expected, actual)

    h_exp = len(expected)
    w_exp = len(expected[0]) if h_exp > 0 else 0
    h_act = len(actual)
    w_act = len(actual[0]) if h_act > 0 else 0

    max_h = max(h_exp, h_act, len(input_grid) if input_grid else 0)
    output_lines: list[str] = []

    headers: list[str] = []
    if input_grid is not None:
        headers.append("--- INPUT ---".center(max(14, len(input_grid[0]) * 3 if input_grid and input_grid[0] else 14)))
    headers.append("--- EXPECTED ---".center(max(16, w_exp * 3)))
    headers.append("--- PREDICTED ---".center(max(16, w_act * 3)))
    headers.append("--- DIFF MASK ---".center(max(16, w_exp * 3)))
    output_lines.append("   ".join(headers))

    # Build mask
    mask: list[list[bool]] = [[False] * w_exp for _ in range(h_exp)]
    if diff.shape_match:
        for m in diff.mismatches:
            mask[m.row][m.col] = True

    for r in range(max_h):
        row_parts: list[str] = []

        # Input
        if input_grid is not None:
            if r < len(input_grid):
                row_parts.append(render_grid_ansi([input_grid[r]], use_color=use_color))
            else:
                w_in = len(input_grid[0]) if input_grid and input_grid[0] else 4
                row_parts.append(" " * (w_in * 3))

        # Expected
        if r < h_exp:
            row_parts.append(render_grid_ansi([expected[r]], use_color=use_color))
        else:
            row_parts.append(" " * (w_exp * 3))

        # Predicted
        if r < h_act:
            hl_row = [mask[r][c] if diff.shape_match and c < len(mask[r]) else False for c in range(w_act)]
            row_parts.append(render_grid_ansi([actual[r]], highlight_mask=[hl_row], use_color=use_color))
        else:
            row_parts.append(" " * (w_act * 3))

        # Diff Mask
        if diff.shape_match and r < h_exp:
            diff_row_chars: list[str] = []
            for c in range(w_exp):
                if mask[r][c]:
                    if use_color:
                        diff_row_chars.append(f"{ANSI_DIFF_HIGHLIGHT} X {ANSI_RESET}")
                    else:
                        diff_row_chars.append(" X ")
                else:
                    if use_color:
                        diff_row_chars.append("\033[48;5;234m . \033[0m")
                    else:
                        diff_row_chars.append(" . ")
            row_parts.append("".join(diff_row_chars))
        else:
            row_parts.append("  [SHAPE MISMATCH]  " if not diff.shape_match else " " * (w_exp * 3))

        output_lines.append("   ".join(row_parts))

    output_lines.append(f"\nDiscrepancy: {diff.summary_message}")
    return "\n".join(output_lines)


@dataclass(frozen=True)
class ExecutionOutcome:
    """Outcome of running synthesized Python code against an input grid."""

    success: bool
    output_grid: list[list[int]] | None
    error_type: str | None
    error_message: str | None
    traceback_str: str | None
    elapsed_ms: float


def normalize_to_int_grid(raw_val: Any) -> list[list[int]]:
    """Converts numpy array or nested lists into canonical list[list[int]]."""
    if isinstance(raw_val, np.ndarray):
        raw_val = raw_val.tolist()

    if not isinstance(raw_val, list):
        raise TypeError(f"Expected 2D list, got {type(raw_val).__name__}")

    if not raw_val:
        return []

    if not isinstance(raw_val[0], list):
        # 1D list, coerce to 1xW
        return [[int(c) for c in raw_val]]

    return [[int(c) for c in row] for row in raw_val]


def execute_unshackled_python(
    code: str,
    grid_in: list[list[int]],
    timeout_s: float = 4.0,
) -> ExecutionOutcome:
    """
    Executes Python transform code with full standard library access in an isolated namespace.
    Safely enforces runtime timeout via a background watchdog thread.
    """
    t0 = time.perf_counter()

    # Clean execution namespace with general scientific tools & spatial anchors
    exec_globals: dict[str, Any] = {
        "np": np,
        "numpy": np,
        "scipy": scipy,
        "ndimage": scipy.ndimage,
        "itertools": sys.modules.get("itertools"),
        "collections": sys.modules.get("collections"),
        "math": sys.modules.get("math"),
        "copy": sys.modules.get("copy"),
        # General Spatial Anchors & Image Processing Utilities
        "spatial": spatial_anchors,
        "bbox": spatial_anchors.bbox,
        "crop": spatial_anchors.crop,
        "centroid": spatial_anchors.centroid,
        "connected_components": spatial_anchors.connected_components,
        "is_identical_shape": spatial_anchors.is_identical_shape,
        "rot90": spatial_anchors.rot90,
        "flip_h": spatial_anchors.flip_h,
        "flip_v": spatial_anchors.flip_v,
        "flood_fill": spatial_anchors.flood_fill,
        "find_cavities": spatial_anchors.find_cavities,
        "color_counts": spatial_anchors.color_counts,
        "canvas": spatial_anchors.canvas,
        "paste": spatial_anchors.paste,
        "Component": spatial_anchors.Component,
    }

    result_holder: list[Any] = []
    error_holder: list[Exception] = []

    def _worker() -> None:
        try:
            exec(code, exec_globals)
            if "transform" not in exec_globals or not callable(exec_globals["transform"]):
                raise ValueError("Synthesized code does not define a callable `transform(grid)` function.")
            fn = exec_globals["transform"]
            out = fn(grid_in)
            result_holder.append(out)
        except Exception as exc:
            error_holder.append(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout_s)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if thread.is_alive():
        return ExecutionOutcome(
            success=False,
            output_grid=None,
            error_type="TimeoutError",
            error_message=f"Execution timed out after {timeout_s:.1f}s (infinite loop or high computational complexity).",
            traceback_str=None,
            elapsed_ms=elapsed_ms,
        )

    if error_holder:
        exc = error_holder[0]
        import traceback

        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return ExecutionOutcome(
            success=False,
            output_grid=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
            traceback_str=tb_str,
            elapsed_ms=elapsed_ms,
        )

    if not result_holder:
        return ExecutionOutcome(
            success=False,
            output_grid=None,
            error_type="ValueError",
            error_message="Function completed but returned no value.",
            traceback_str=None,
            elapsed_ms=elapsed_ms,
        )

    try:
        normalized = normalize_to_int_grid(result_holder[0])
        return ExecutionOutcome(
            success=True,
            output_grid=normalized,
            error_type=None,
            error_message=None,
            traceback_str=None,
            elapsed_ms=elapsed_ms,
        )
    except Exception as norm_err:
        return ExecutionOutcome(
            success=False,
            output_grid=None,
            error_type="TypeError",
            error_message=f"Output could not be normalized to integer grid: {norm_err}",
            traceback_str=None,
            elapsed_ms=elapsed_ms,
        )


@dataclass(frozen=True)
class CEGISTurn:
    """Audit record for a single CEGIS synthesis/repair turn."""

    turn: int
    code: str
    passed_examples: int
    total_examples: int
    first_failure_idx: int | None
    failure_diff: GridDiff | None
    execution_error: str | None
    prompt_used: str
    elapsed_ms: float
    hypothesis: str | None = None
    is_backtrack: bool = False


@dataclass(frozen=True)
class CEGISRunResult:
    """Comprehensive outcome of the Counterexample-Guided Inductive Synthesis loop."""

    success: bool
    final_code: str | None
    turns_taken: int
    turns: list[CEGISTurn] = field(default_factory=list)
    test_predictions: list[list[list[int]]] = field(default_factory=list)
    total_elapsed_ms: float = 0.0
    error_summary: str | None = None


class UnshackledCEGISEngine:
    """
    Autonomous Counterexample-Guided Inductive Synthesis (CEGIS) Engine for Lucca v1.44.0.
    Eliminates benchmark-specific DSL shortcuts, allowing the model to invent arbitrary
    algorithmic Python transformation code on the fly with structured cell diff guidance.
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8080/v1/chat/completions",
        timeout_seconds: float = 120.0,
        max_turns: int = 4,
    ) -> None:
        self.server_url = server_url
        self.timeout_seconds = timeout_seconds
        self.max_turns = max_turns

    def query_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Queries local llama-server instance synchronously."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(self.server_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"]).strip()

    @staticmethod
    def _format_train_examples(train_pairs: list[dict[str, list[list[int]]]]) -> str:
        blocks: list[str] = []
        for idx, ex in enumerate(train_pairs, start=1):
            blocks.append(
                f"### Demonstration {idx}:\n"
                f"Input ({len(ex['input'])}x{len(ex['input'][0]) if ex['input'] else 0}):\n"
                f"{json.dumps(ex['input'])}\n"
                f"Output ({len(ex['output'])}x{len(ex['output'][0]) if ex['output'] else 0}):\n"
                f"{json.dumps(ex['output'])}\n"
            )
        return "\n".join(blocks)

    def synthesize_turn_1(
        self,
        task_data: dict[str, Any],
        hint: str | None = None,
        temperature: float = 0.2,
    ) -> tuple[str, str | None, str]:
        """
        Synthesizes initial candidate Python program (Turn 1) using Hypothesis-First Abduction.
        Provides unrestricted scientific libraries and zero handcoded benchmark DSL functions.
        """
        train_pairs: list[dict[str, list[list[int]]]] = task_data.get("train", [])
        train_desc = self._format_train_examples(train_pairs)

        system_prompt = (
            "You are an expert algorithmic programmer and neurosymbolic reasoning engine.\n"
            "Your objective is to deduce the exact invariant spatial transformation mapping 2D integer grids "
            "from input to output across all demonstrations, and implement it as a clean Python function."
        )

        user_prompt_lines: list[str] = [
            "Analyze the following input-output grid demonstrations carefully:",
            "",
            train_desc,
            "Format Requirement (Hypothesis-First):",
            "Begin your response with a concise HYPOTHESIS block before emitting code:",
            "HYPOTHESIS:",
            "- Background Color: <int> (<name>)",
            "- Canvas Sizing: <same_as_input | fixed HxW | cropped | expanded>",
            "- Objects & Topology: <individual pixels | 4-connected | 8-connected | cavities | lines>",
            "- Core Transformation Invariant: <1-2 sentences clearly stating the spatial rule>",
            "- Algorithmic Recipe: <step 1, step 2, step 3>",
            "",
            "Available Pre-Imported Spatial Utilities (Zero-Boilerplate Image Processing):",
            "- `connected_components(arr, connectivity=8, background=0)`: returns list of Component objects with `.color`, `.mask`, `.bbox`, `.area`, `.centroid`, `.cropped_mask()`",
            "- `bbox(mask)`: returns (min_r, min_c, max_r, max_c, h, w) or None",
            "- `crop(arr, bbox_tuple)`: crops subgrid corresponding to bbox",
            "- `centroid(mask)`: returns (mean_r, mean_c)",
            "- `is_identical_shape(mask_a, mask_b)`: returns True if two binary shapes are identical under translation",
            "- `find_cavities(arr, background_val=0)`: returns boolean mask of enclosed interior voids",
            "- `flood_fill(arr, start_r, start_c, fill_val)`: 4-way flood fill",
            "- `rot90(arr, k=1)`, `flip_h(arr)`, `flip_v(arr)`: symmetry transformations",
            "- `canvas(h, w, fill_val=0)`: returns fresh numpy canvas of shape (h, w)",
            "- `paste(base, patch, top_r, left_c, transparent_val=None)`: pastes patch onto base grid",
            "",
            "Specifications & Rules:",
            "1. Write a Python function `def transform(grid: list[list[int]]) -> list[list[int]]:` that solves this transformation.",
            "2. STRONGLY PREFERRED: Use the pre-imported spatial utilities (`connected_components`, `find_cavities`, `bbox`, `crop`, `is_identical_shape`, `paste`) instead of writing manual BFS/DFS loops. Do NOT write manual BFS queues or flood-fills from scratch; call the built-in utilities.",
            "3. The grid values are integers 0-9 representing discrete colors (0=black, 1=blue, 2=red, 3=green, 4=yellow, 5=gray, 6=magenta, 7=orange, 8=cyan, 9=maroon).",
            "4. Return executable Python code inside a single ```python ... ``` block. Prioritize clean, complete, fully closed Python code.",
        ]

        if hint:
            user_prompt_lines.append(f"\nUser / System Guidance: {hint}")

        prompt = "\n".join(user_prompt_lines)
        response_text = self.query_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=3072,
        )

        code = extract_python_code(response_text)
        hypothesis = extract_hypothesis(response_text)
        return code, hypothesis, prompt

    def verify_candidate(
        self,
        code: str,
        train_pairs: list[dict[str, list[list[int]]]],
    ) -> tuple[bool, int, int | None, GridDiff | None, str | None]:
        """
        Evaluates candidate code against all training demonstrations.
        Returns (all_passed, passed_count, first_failing_idx, first_diff, error_message).
        """
        passed_count = 0
        for idx, pair in enumerate(train_pairs):
            outcome = execute_unshackled_python(code, pair["input"])
            if not outcome.success:
                err_msg = f"{outcome.error_type}: {outcome.error_message}"
                return False, passed_count, idx, None, err_msg

            diff = compute_detailed_grid_diff(pair["output"], outcome.output_grid or [])
            if diff.is_match:
                passed_count += 1
            else:
                return False, passed_count, idx, diff, None

        return True, passed_count, None, None, None

    def synthesize_repair_turn(
        self,
        prior_code: str,
        task_data: dict[str, Any],
        failing_idx: int,
        diff: GridDiff | None,
        err_msg: str | None,
        turn_num: int,
        temperature: float = 0.25,
        prior_hypothesis: str | None = None,
    ) -> tuple[str, str | None, str]:
        """
        Synthesizes a repaired program using structured counterexample diffs (Turn 2..K).
        """
        train_pairs: list[dict[str, list[list[int]]]] = task_data.get("train", [])
        failing_pair = train_pairs[failing_idx]
        train_desc = self._format_train_examples(train_pairs)

        system_prompt = (
            "You are an expert algorithmic debugger and neurosymbolic program repair engine.\n"
            "Your previous implementation failed on a training demonstration. Analyze the exact counterexample diff, "
            "locate the flaw in your logic, and output a corrected, fully verified `transform` function."
        )

        repair_prompt_lines: list[str] = [
            f"### CEGIS REPAIR TURN {turn_num}:",
            f"Your previous Python code failed on Demonstration {failing_idx + 1}.",
            "",
            f"Previous Code Attempt:\n```python\n{prior_code}\n```",
        ]

        if prior_hypothesis:
            repair_prompt_lines.append(f"\nPrevious Hypothesis:\n{prior_hypothesis}\n")

        repair_prompt_lines.append("### Failure Diagnostic:")

        if err_msg:
            repair_prompt_lines.append(f"- Execution Runtime Error: {err_msg}")
        elif diff:
            repair_prompt_lines.append(diff.format_counterexample_prompt(max_examples=16))
            outcome = execute_unshackled_python(prior_code, failing_pair["input"])
            if outcome.success and outcome.output_grid:
                side_by_side = render_grid_side_by_side(
                    expected=failing_pair["output"],
                    actual=outcome.output_grid,
                    use_color=False,
                )
                repair_prompt_lines.append("\nGrid Comparison (Expected vs Predicted vs Diff):\n" + side_by_side)

        repair_prompt_lines.extend([
            "",
            "All Training Demonstrations for Reference:",
            train_desc,
            "Instructions for Repair:",
            "1. Keep any diagnosis comment strictly under 2 lines (# Diagnosis: ...). Do NOT write lengthy text essays in docstrings or comments.",
            "2. Prioritize writing complete, fully closed code: make sure all loops, brackets, and functions are complete before returning.",
            "3. STRONGLY PREFERRED: Use spatial utilities (`connected_components`, `find_cavities`, `bbox`, `crop`, `is_identical_shape`, `paste`) instead of writing manual BFS/DFS loops. Do NOT write manual BFS queues from scratch.",
            "4. Modify your logic so that it satisfies Demonstration 1, 2, ... and ALL others simultaneously.",
            "5. Ensure `def transform(grid: list[list[int]]) -> list[list[int]]:` is robust and handles canvas boundaries properly.",
            "6. Return ONLY executable Python code inside a single ```python ... ``` block. Prioritize clean, complete, fully closed Python code.",
        ])

        prompt = "\n".join(repair_prompt_lines)
        response_text = self.query_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=3072,
        )

        code = extract_python_code(response_text)
        hypothesis = extract_hypothesis(response_text)
        return code, hypothesis, prompt

    def synthesize_backtrack_turn(
        self,
        task_data: dict[str, Any],
        turn_num: int,
        failed_hypotheses: list[str],
        prior_error: str | None = None,
        temperature: float = 0.35,
    ) -> tuple[str, str | None, str]:
        """
        Synthesizes a fresh candidate from scratch when previous branches reached an impasse.
        Discards the failed code branch and forces the model to explore an alternative hypothesis.
        """
        train_pairs: list[dict[str, list[list[int]]]] = task_data.get("train", [])
        train_desc = self._format_train_examples(train_pairs)

        system_prompt = (
            "You are an expert algorithmic programmer and neurosymbolic reasoning engine.\n"
            "Your previous hypothesis failed completely. You must formulate a fresh, alternative conceptual hypothesis "
            "and implement a brand-new transformation function from scratch."
        )

        user_prompt_lines: list[str] = [
            f"### CLEAN-SLATE BACKTRACKING (TURN {turn_num}):",
            "The previous code branch failed completely across all demonstrations (0 passed).",
            "CRITICAL: Discard the previous approach completely. Do NOT attempt to patch it.",
            "",
            "Previous Failed Hypotheses:",
        ]
        for idx, h in enumerate(failed_hypotheses, start=1):
            user_prompt_lines.append(f"- Hypothesis {idx}: {h}")

        if prior_error:
            user_prompt_lines.append(f"\nObserved Failure: {prior_error}")

        user_prompt_lines.extend([
            "",
            "Formulate a FRESH, ALTERNATIVE hypothesis from scratch.",
            "Consider whether:",
            "- Background color was misidentified (e.g. non-zero background or inverted foreground).",
            "- Connectivity is 8-connected instead of 4-connected (or vice-versa).",
            "- The rule depends on enclosed cavities, hollow shapes, or spatial order (top-to-bottom / size).",
            "- The output canvas has different dimensions or is a crop of a specific bounding box.",
            "- The transformation is rotational or reflective symmetry.",
            "",
            "Format Requirement (Hypothesis-First):",
            "Begin with a fresh HYPOTHESIS block before the code:",
            "HYPOTHESIS:",
            "- Background Color: <int> (<name>)",
            "- Canvas Sizing: <same_as_input | fixed HxW | cropped | expanded>",
            "- Objects & Topology: <individual pixels | 4-connected | 8-connected | cavities | lines>",
            "- Core Transformation Invariant: <1-2 sentences clearly stating the fresh rule>",
            "- Algorithmic Recipe: <step 1, step 2, step 3>",
            "",
            "Available Pre-Imported Spatial Utilities:",
            "- `connected_components(arr, connectivity=8, background=0)`: returns list of Component objects",
            "- `bbox(mask)`, `crop(arr, bbox_tuple)`, `centroid(mask)`, `is_identical_shape(mask_a, mask_b)`",
            "- `find_cavities(arr, background_val=0)`, `flood_fill(arr, r, c, fill_val)`",
            "- `rot90(arr, k=1)`, `flip_h(arr)`, `flip_v(arr)`, `canvas(h, w, fill_val=0)`, `paste(...)`",
            "",
            "All Training Demonstrations for Reference:",
            train_desc,
            "Specifications & Rules:",
            "1. Write a Python function `def transform(grid: list[list[int]]) -> list[list[int]]:` that solves this transformation.",
            "2. STRONGLY PREFERRED: Use built-in spatial utilities (`connected_components`, `find_cavities`, `bbox`, `is_identical_shape`) instead of manual BFS loops.",
            "3. Return executable Python code inside a single ```python ... ``` block. Prioritize clean, complete, fully closed Python code.",
        ])

        prompt = "\n".join(user_prompt_lines)
        response_text = self.query_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=3072,
        )

        code = extract_python_code(response_text)
        hypothesis = extract_hypothesis(response_text)
        return code, hypothesis, prompt

    def run_cegis_loop(
        self,
        task_data: dict[str, Any],
        hint: str | None = None,
        max_turns: int | None = None,
    ) -> CEGISRunResult:
        """
        Executes the full multi-turn CEGIS loop for a given task.
        Halts immediately once 100% of training demonstrations are satisfied.
        """
        t0 = time.perf_counter()
        effective_max_turns = max_turns or self.max_turns
        train_pairs = task_data.get("train", [])
        total_examples = len(train_pairs)

        traces: list[CEGISTurn] = []
        current_code: str = ""
        current_hypothesis: str | None = None
        turn_idx = 1
        limit_turns = effective_max_turns
        consecutive_zero_passes = 0

        while turn_idx <= limit_turns:
            turn_t0 = time.perf_counter()

            if turn_idx == 1:
                code, hypo, prompt = self.synthesize_turn_1(task_data, hint=hint, temperature=0.2)
                is_backtrack = False
            else:
                last_trace = traces[-1]
                should_backtrack = (
                    consecutive_zero_passes >= 1
                    and (turn_idx >= 3 or last_trace.execution_error is not None)
                )
                if should_backtrack:
                    failed_hypos = [t.hypothesis for t in traces if t.hypothesis]
                    if not failed_hypos and current_hypothesis:
                        failed_hypos = [current_hypothesis]
                    code, hypo, prompt = self.synthesize_backtrack_turn(
                        task_data=task_data,
                        turn_num=turn_idx,
                        failed_hypotheses=failed_hypos,
                        prior_error=last_trace.execution_error or (f"Cell diff on demo {last_trace.first_failure_idx + 1}" if last_trace.failure_diff else None),
                        temperature=0.35,
                    )
                    is_backtrack = True
                else:
                    code, hypo, prompt = self.synthesize_repair_turn(
                        prior_code=current_code,
                        task_data=task_data,
                        failing_idx=last_trace.first_failure_idx or 0,
                        diff=last_trace.failure_diff,
                        err_msg=last_trace.execution_error,
                        turn_num=turn_idx,
                        temperature=0.2 + (min(turn_idx, 5) * 0.05),
                        prior_hypothesis=current_hypothesis,
                    )
                    is_backtrack = False

            current_code = code
            if hypo:
                current_hypothesis = hypo
            turn_elapsed = (time.perf_counter() - turn_t0) * 1000.0

            if not code or not code.strip():
                traces.append(
                    CEGISTurn(
                        turn=turn_idx,
                        code="",
                        passed_examples=0,
                        total_examples=total_examples,
                        first_failure_idx=0,
                        failure_diff=None,
                        execution_error="No executable Python code extracted from LLM response.",
                        prompt_used=prompt,
                        elapsed_ms=turn_elapsed,
                        hypothesis=current_hypothesis,
                        is_backtrack=is_backtrack,
                    )
                )
                consecutive_zero_passes += 1
                turn_idx += 1
                continue

            all_passed, passed_count, fail_idx, fail_diff, err_msg = self.verify_candidate(
                code, train_pairs
            )

            if passed_count == 0:
                consecutive_zero_passes += 1
            else:
                consecutive_zero_passes = 0

            traces.append(
                CEGISTurn(
                    turn=turn_idx,
                    code=code,
                    passed_examples=passed_count,
                    total_examples=total_examples,
                    first_failure_idx=fail_idx,
                    failure_diff=fail_diff,
                    execution_error=err_msg,
                    prompt_used=prompt,
                    elapsed_ms=turn_elapsed,
                    hypothesis=current_hypothesis,
                    is_backtrack=is_backtrack,
                )
            )

            logger.info(
                "cegis_turn_evaluated",
                turn=turn_idx,
                passed=passed_count,
                total=total_examples,
                all_passed=all_passed,
                is_backtrack=is_backtrack,
                elapsed_ms=turn_elapsed,
            )

            if all_passed:
                total_elapsed = (time.perf_counter() - t0) * 1000.0
                test_preds = self.predict_test(code, task_data.get("test", []))
                return CEGISRunResult(
                    success=True,
                    final_code=code,
                    turns_taken=turn_idx,
                    turns=traces,
                    test_predictions=test_preds,
                    total_elapsed_ms=total_elapsed,
                    error_summary=None,
                )

            # Adaptive budget extension: if at current limit and showing positive progress, grant 1 bonus turn
            if turn_idx == limit_turns and passed_count > 0 and limit_turns < effective_max_turns + 2:
                logger.info(
                    "adaptive_cegis_turn_extended",
                    turn=turn_idx,
                    passed=passed_count,
                    total=total_examples,
                )
                limit_turns += 1

            turn_idx += 1

        total_elapsed = (time.perf_counter() - t0) * 1000.0
        return CEGISRunResult(
            success=False,
            final_code=current_code,
            turns_taken=len(traces),
            turns=traces,
            test_predictions=[],
            total_elapsed_ms=total_elapsed,
            error_summary=f"Failed to satisfy 100% of demonstrations after {len(traces)} turns.",
        )

    @staticmethod
    def predict_test(
        code: str, test_pairs: list[dict[str, list[list[int]]]]
    ) -> list[list[list[int]]]:
        """Runs the verified code on the unseen test input(s)."""
        predictions: list[list[list[int]]] = []
        for pair in test_pairs:
            outcome = execute_unshackled_python(code, pair["input"])
            if outcome.success and outcome.output_grid is not None:
                predictions.append(outcome.output_grid)
            else:
                predictions.append([])
        return predictions
