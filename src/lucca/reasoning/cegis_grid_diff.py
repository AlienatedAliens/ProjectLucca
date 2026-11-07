"""
Project Lucca — CEGIS 2D Grid Diffing & ANSI/ASCII Rendering (WO-43 Phase 3.4)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §4
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from lucca.reasoning import relational, spatial_anchors

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
    topological_diagnostics: tuple[str, ...] = ()

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

        if self.topological_diagnostics:
            lines.append("- Organ A Topological & Spatial Diagnostics:")
            for diag in self.topological_diagnostics:
                lines.append(f"  * {diag}")

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

    # Organ A Mereotopological Object-Level Diagnostics (Milestone 36.5 Deliverable 3)
    topo_diags: list[str] = []
    if mismatches:
        from lucca.reasoning.relational.realize_grid import extract_connected_components
        from lucca.reasoning.relational.sorts import Network, Object

        mismatch_pts = frozenset((m.row, m.col) for m in mismatches)
        err_comps = extract_connected_components(mismatch_pts, four_connected=True)
        comp_objects: dict[str, Object] = {}
        for i, comp in enumerate(err_comps):
            comp_objects[f"err_{i}"] = Object(
                id=f"err_{i}",
                attributes={"area": len(comp.points)},
                region=comp,
            )
        _err_net = Network(objects=comp_objects)

        if expected and actual and len(expected) > 0 and len(expected[0]) > 0:
            exp_arr = np.array(expected, dtype=int)
            act_arr = np.array(actual, dtype=int)
            exp_comps = spatial_anchors.connected_components(exp_arr)
            act_comps = spatial_anchors.connected_components(act_arr)

            # 1. Connected-component count discrepancy
            if len(exp_comps) != len(act_comps):
                topo_diags.append(
                    f"Component Count Discrepancy: expected {len(exp_comps)} connected object(s), "
                    f"predicted {len(act_comps)} object(s) ({len(err_comps)} contiguous error region(s))."
                )

            # 2. Translation offset (dr, dc) detection across matching shapes
            used_act: set[int] = set()
            for e_idx, ec in enumerate(exp_comps):
                e_crop = ec.cropped_mask()
                for a_idx, ac in enumerate(act_comps):
                    if a_idx in used_act:
                        continue
                    if ec.area == ac.area and spatial_anchors.is_identical_shape(e_crop, ac.cropped_mask()):
                        dr = int(round(ac.centroid[0] - ec.centroid[0]))
                        dc = int(round(ac.centroid[1] - ec.centroid[1]))
                        if dr != 0 or dc != 0:
                            topo_diags.append(
                                f"Translation Offset on object #{e_idx + 1} (color {ec.color}, area {ec.area}): "
                                f"shifted by (dr={dr:+d}, dc={dc:+d}) relative to expected position."
                            )
                            used_act.add(a_idx)
                            break

            # 3. Cavity / hollow interior mismatch detection via Organ A relational primitives
            exp_fg = frozenset(
                (r, c) for r in range(h_exp) for c in range(w_exp) if expected[r][c] != 0
            )
            act_fg = frozenset(
                (r, c) for r in range(h_act) for c in range(w_act) if actual[r][c] != 0
            )
            exp_cavs = relational.extract_cavities(exp_fg)
            act_cavs = relational.extract_cavities(act_fg)
            if len(exp_cavs) != len(act_cavs):
                topo_diags.append(
                    f"Cavity Enclosure Mismatch: expected {len(exp_cavs)} enclosed cavity cell(s), "
                    f"predicted {len(act_cavs)} cavity cell(s)."
                )
            else:
                cav_diff = [
                    m for m in mismatches if (m.row, m.col) in exp_cavs or (m.row, m.col) in act_cavs
                ]
                if cav_diff:
                    topo_diags.append(
                        f"Cavity Fill Discrepancy: {len(cav_diff)} mismatched cell(s) lie inside or on enclosed cavity regions."
                    )

    summary = (
        "Exact match"
        if is_match
        else f"{mismatch_count}/{total_cells} cells mismatch ({mismatch_ratio * 100:.1f}%)"
        + (f" | {'; '.join(topo_diags)}" if topo_diags else "")
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
        topological_diagnostics=tuple(topo_diags),
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
