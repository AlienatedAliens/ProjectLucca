"""
Project Lucca — Discrete 2D Spatial DSL & Metamorphic Invariance Verification
(D-REAS-16, D-AUD-01)

Provides canonical 2D spatial primitives, connected component analysis,
topological relations, structured object extraction, and metamorphic
invariance checking.

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import itertools
from typing import cast

import numpy as np
import scipy.ndimage
import scipy.stats
import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SpatialObject:
    """Structured representation of a discrete 2D connected component."""

    obj_id: int
    color: int
    min_r: int
    min_c: int
    max_r: int
    max_c: int
    height: int
    width: int
    area: int
    is_hollow: bool
    coords: list[tuple[int, int]]

    @property
    def dimensions(self) -> tuple[int, int]:
        """Returns (height, width) dimensions of the bounding box."""
        return (self.height, self.width)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Returns (min_r, min_c, max_r, max_c) bounding box."""
        return (self.min_r, self.min_c, self.max_r, self.max_c)

    def to_dict(self) -> dict[str, int | bool | list[tuple[int, int]]]:
        """Serializes object to pure primitive dictionary."""
        return {
            "obj_id": self.obj_id,
            "color": self.color,
            "min_r": self.min_r,
            "min_c": self.min_c,
            "max_r": self.max_r,
            "max_c": self.max_c,
            "height": self.height,
            "width": self.width,
            "area": self.area,
            "is_hollow": self.is_hollow,
            "coords": self.coords,
        }


def normalize_grid(val: list[list[int]] | object) -> list[list[int]]:
    """Coerces NumPy arrays or nested lists into canonical list[list[int]]."""
    if hasattr(val, "tolist"):
        val = val.tolist()
    if isinstance(val, (list, tuple)):
        return [
            [int(c) for c in row] if isinstance(row, (list, tuple)) else [int(row)]
            for row in val
        ]
    raise TypeError(f"Cannot normalize type {type(val).__name__} to 2D grid")


def find_objects(
    grid: list[list[int]],
    background: int = 0,
    connectivity: int = 8,
) -> list[SpatialObject]:
    """
    Extracts connected components grouped by color (excluding background color, default 0).
    Computes bounding box, dimensions, area, and topological hollowness.
    connectivity: 4 (orthogonal) or 8 (orthogonal + diagonal). Defaults to 8.
    """
    arr = np.array(grid, dtype=int)
    objects: list[SpatialObject] = []
    obj_counter = 1

    structure = scipy.ndimage.generate_binary_structure(2, 2 if connectivity == 8 else 1)

    for color in np.unique(arr):
        if color == background:
            continue
        mask = arr == color
        labeled, num_features = scipy.ndimage.label(mask, structure=structure)
        for f in range(1, num_features + 1):
            comp_mask = labeled == f
            coords = np.argwhere(comp_mask)
            min_r, min_c = coords.min(axis=0)
            max_r, max_c = coords.max(axis=0)
            h = int(max_r - min_r + 1)
            w = int(max_c - min_c + 1)
            area = int(len(coords))

            # Subgrid check for interior holes
            sub = comp_mask[min_r : max_r + 1, min_c : max_c + 1]
            filled_sub = scipy.ndimage.binary_fill_holes(sub)
            is_hollow = bool(np.any(filled_sub & ~sub))

            objects.append(
                SpatialObject(
                    obj_id=obj_counter,
                    color=int(color),
                    min_r=int(min_r),
                    min_c=int(min_c),
                    max_r=int(max_r),
                    max_c=int(max_c),
                    height=h,
                    width=w,
                    area=area,
                    is_hollow=is_hollow,
                    coords=[(int(r), int(c)) for r, c in coords],
                )
            )
            obj_counter += 1

    return objects


def count_objects(
    grid: list[list[int]],
    color: int | None = None,
    connectivity: int = 8,
) -> int:
    """Counts connected components of a specific color, or all non-zero components."""
    arr = np.array(grid, dtype=int)
    if color is not None:
        mask = arr == color
    else:
        mask = arr != 0
    if not np.any(mask):
        return 0
    structure = scipy.ndimage.generate_binary_structure(2, 2 if connectivity == 8 else 1)
    _, num_features = scipy.ndimage.label(mask, structure=structure)
    return int(num_features)


def count_cells(grid: list[list[int]], color: int | None = None) -> int:
    """Counts total number of individual cells with given color (or all non-zero cells if color=None)."""
    arr = np.array(grid, dtype=int)
    if color is not None:
        return int(np.sum(arr == color))
    return int(np.sum(arr != 0))


def dominant_object(grid: list[list[int]]) -> SpatialObject | None:
    """Finds the largest non-zero connected component by pixel count."""
    objs = find_objects(grid)
    if not objs:
        return None
    return max(objs, key=lambda o: o.area)


def unique_colors(grid: list[list[int]], exclude_zero: bool = True) -> list[int]:
    """Returns sorted unique colors present in the grid."""
    arr = np.array(grid, dtype=int)
    colors = np.unique(arr)
    if exclude_zero:
        colors = colors[colors != 0]
    return [int(c) for c in colors]


def fill_holes(grid: list[list[int]], fill_color: int | None = None) -> list[list[int]]:
    """Fills enclosed topological holes in non-zero regions."""
    arr = np.array(grid, dtype=int)
    mask = arr != 0
    filled_mask = scipy.ndimage.binary_fill_holes(mask)
    holes = filled_mask & ~mask
    res = arr.copy()
    if np.any(holes):
        if fill_color is not None:
            res[holes] = fill_color
        else:
            non_zeros = arr[mask]
            if len(non_zeros) > 0:
                vals, counts = np.unique(non_zeros, return_counts=True)
                dominant = int(vals[np.argmax(counts)])
                res[holes] = dominant
    return res.tolist()


def is_enclosed(inner: SpatialObject, outer: SpatialObject) -> bool:
    """Checks whether inner object is geometrically enclosed within outer object."""
    if (
        inner.min_r > outer.min_r
        and inner.max_r < outer.max_r
        and inner.min_c > outer.min_c
        and inner.max_c < outer.max_c
    ):
        return True
    return False


def flood_fill(grid: list[list[int]], r: int, c: int, fill_color: int) -> list[list[int]]:
    """Fills contiguous region of matching color starting from (r, c)."""
    arr = np.array(grid, dtype=int)
    h, w = arr.shape
    if not (0 <= r < h and 0 <= c < w):
        return arr.tolist()
    orig = arr[r, c]
    if orig == fill_color:
        return arr.tolist()
    q = deque([(r, c)])
    visited = {(r, c)}
    while q:
        cr, cc = q.popleft()
        arr[cr, cc] = fill_color
        for nr, nc in ((cr + 1, cc), (cr - 1, cc), (cr, cc + 1), (cr, cc - 1)):
            if 0 <= nr < h and 0 <= nc < w and (nr, nc) not in visited and arr[nr, nc] == orig:
                visited.add((nr, nc))
                q.append((nr, nc))
    return arr.tolist()


def rot90(grid: list[list[int]], k: int = 1) -> list[list[int]]:
    """Rotates grid 90 degrees clockwise k times."""
    return np.rot90(np.array(grid, dtype=int), k=-k).tolist()


def flip_h(grid: list[list[int]]) -> list[list[int]]:
    """Flips grid horizontally (left-to-right mirror)."""
    return np.fliplr(np.array(grid, dtype=int)).tolist()


def flip_v(grid: list[list[int]]) -> list[list[int]]:
    """Flips grid vertically (top-to-bottom mirror)."""
    return np.flipud(np.array(grid, dtype=int)).tolist()


def crop(grid: list[list[int]], r1: int, c1: int, r2: int, c2: int) -> list[list[int]]:
    """Crops subgrid from (r1, c1) to (r2, c2) inclusive."""
    arr = np.array(grid, dtype=int)
    return arr[r1 : r2 + 1, c1 : c2 + 1].tolist()


def bbox_of_all(grid: list[list[int]], background: int = 0) -> tuple[int, int, int, int] | None:
    """Finds the bounding box (min_r, min_c, max_r, max_c) of all non-background cells."""
    arr = np.array(grid, dtype=int)
    nonzero = np.argwhere(arr != background)
    if nonzero.size == 0:
        return None
    min_r, min_c = nonzero.min(axis=0)
    max_r, max_c = nonzero.max(axis=0)
    return (int(min_r), int(min_c), int(max_r), int(max_c))


def crop_to_content(grid: list[list[int]], background: int = 0) -> list[list[int]]:
    """Crops the grid to the minimal bounding box enclosing all non-background cells."""
    b = bbox_of_all(grid, background)
    if b is None:
        return [[]]
    arr = np.array(grid, dtype=int)
    return arr[b[0] : b[2] + 1, b[1] : b[3] + 1].tolist()


def paste(
    dst: list[list[int]],
    src: list[list[int]],
    r: int,
    c: int,
    ignore_zero: bool = False,
) -> list[list[int]]:
    """Pastes src grid onto dst at offset (r, c)."""
    d_arr = np.array(dst, dtype=int)
    s_arr = np.array(src, dtype=int)
    sh, sw = s_arr.shape
    dh, dw = d_arr.shape
    for i in range(sh):
        for j in range(sw):
            if 0 <= r + i < dh and 0 <= c + j < dw:
                if not ignore_zero or s_arr[i, j] != 0:
                    d_arr[r + i, c + j] = s_arr[i, j]
    return d_arr.tolist()


def sort_objects(
    objects: list[SpatialObject],
    key: str = "height",
    reverse: bool = False,
) -> list[SpatialObject]:
    """Sorts SpatialObjects by attribute: 'height', 'width', 'area', 'min_r', 'min_c', 'color'."""
    valid_keys = {"height", "width", "area", "min_r", "min_c", "max_r", "max_c", "color"}
    if key not in valid_keys:
        raise ValueError(f"Invalid sort key '{key}'. Must be one of {valid_keys}")
    return sorted(objects, key=lambda obj: getattr(obj, key), reverse=reverse)


def column_heights(grid: list[list[int]], background: int = 0) -> list[int]:
    """Returns count of non-background cells per column."""
    arr = np.array(grid, dtype=int)
    if arr.size == 0:
        return []
    return np.sum(arr != background, axis=0).tolist()


def order_columns_by_height(
    grid: list[list[int]],
    reverse: bool = False,
    background: int = 0,
) -> list[list[int]]:
    """
    Sorts vertical columns by non-background cell count (height) and packs
    non-empty columns starting from the left. Empty columns remain at the right.
    """
    arr = np.array(grid, dtype=int)
    if arr.size == 0:
        return grid
    h, w = arr.shape
    columns = []
    for c in range(w):
        col_vals = arr[:, c].tolist()
        height = sum(1 for val in col_vals if val != background)
        columns.append((height, col_vals))

    non_empty = [col for h_val, col in columns if h_val > 0]
    empty = [col for h_val, col in columns if h_val == 0]

    non_empty.sort(
        key=lambda col: sum(1 for val in col if val != background),
        reverse=reverse,
    )
    final_cols = non_empty + empty
    res = np.zeros((h, w), dtype=int)
    for c, col_vals in enumerate(final_cols):
        res[:, c] = col_vals
    return res.tolist()


def row_widths(grid: list[list[int]], background: int = 0) -> list[int]:
    """Returns count of non-background cells per row."""
    arr = np.array(grid, dtype=int)
    if arr.size == 0:
        return []
    return np.sum(arr != background, axis=1).tolist()


def denoise(grid: list[list[int]], min_size: int = 2, background: int = 0) -> list[list[int]]:
    """Removes small isolated noise objects with area < min_size, replacing them with background."""
    objs = find_objects(grid, background=background)
    res = [row[:] for row in grid]
    for obj in objs:
        if obj.area < min_size:
            for r, c in obj.coords:
                res[r][c] = background
    return res


def majority_filter(grid: list[list[int]], radius: int = 1) -> list[list[int]]:
    """Applies a local 2D modal majority filter to smooth salt-and-pepper noise."""
    arr = np.array(grid, dtype=int)
    h, w = arr.shape
    res = np.copy(arr)
    for r in range(h):
        for c in range(w):
            r_min = max(0, r - radius)
            r_max = min(h, r + radius + 1)
            c_min = max(0, c - radius)
            c_max = min(w, c + radius + 1)
            neighborhood = arr[r_min:r_max, c_min:c_max].flatten()
            vals, counts = np.unique(neighborhood, return_counts=True)
            max_idx = int(np.argmax(counts))
            if counts[max_idx] > len(neighborhood) // 2:
                res[r, c] = vals[max_idx]
    return res.tolist()


def restore_periodic_pattern(
    grid: list[list[int]],
    period_r: int | None = None,
    period_c: int | None = None,
    background: int = 0,
) -> list[list[int]]:
    """
    Restores an underlying periodic or repeating pattern by filtering noise.
    Computes consensus modal colors for modulo coordinates (r % period_r, c % period_c).
    If period_r or period_c are not specified, infers the consensus period (1..min(8, dim))
    that maximizes modulo cell agreement.
    """
    arr = np.array(grid, dtype=int)
    if arr.size == 0:
        return grid
    h, w = arr.shape
    if h <= 1 and w <= 1:
        return grid

    best_pr = period_r
    best_pc = period_c

    if best_pr is None or best_pc is None:
        best_score = -1.0
        candidate_prs = [period_r] if period_r is not None else list(range(1, min(9, h + 1)))
        candidate_pcs = [period_c] if period_c is not None else list(range(1, min(9, w + 1)))

        for pr in candidate_prs:
            for pc in candidate_pcs:
                if pr == h and pc == w and (h > 1 or w > 1):
                    continue
                match_count = 0
                total_count = h * w
                for r_mod in range(pr):
                    for c_mod in range(pc):
                        cells = arr[r_mod::pr, c_mod::pc].flatten()
                        if cells.size == 0:
                            continue
                        _vals, counts = np.unique(cells, return_counts=True)
                        match_count += int(np.max(counts))

                score = match_count / float(total_count)
                dl_penalty = (pr * pc) / float(total_count * 4)
                penalized_score = score - dl_penalty
                if penalized_score > best_score:
                    best_score = penalized_score
                    best_pr = pr
                    best_pc = pc

    pr = max(1, best_pr if best_pr is not None else 1)
    pc = max(1, best_pc if best_pc is not None else 1)

    res = np.copy(arr)
    for r_mod in range(pr):
        for c_mod in range(pc):
            cells = arr[r_mod::pr, c_mod::pc].flatten()
            if cells.size == 0:
                continue
            vals, counts = np.unique(cells, return_counts=True)
            mode_color = int(vals[np.argmax(counts)])
            res[r_mod::pr, c_mod::pc] = mode_color

    return res.tolist()


def complete_symmetry(
    grid: list[list[int]],
    axis: str = "vertical",
    mode: str = "canvas",
    background: int = 0,
) -> list[list[int]]:
    """
    Completes reflection symmetry by mirroring non-background cells across
    vertical, horizontal, or both axes.
    mode='canvas' mirrors across the full canvas dimensions.
    mode='bbox' mirrors across the bounding box of non-background content.
    mode='auto' automatically infers the consensus reflection axis that maximizes
                reflected cell agreement, robust to damaged vertices or asymmetric borders.
    """
    arr = np.array(grid, dtype=int)
    if arr.size == 0:
        return grid
    h, w = arr.shape
    res = np.copy(arr)

    valid_axes = {"vertical", "horizontal", "both"}
    if axis not in valid_axes:
        raise ValueError(f"Axis must be one of {valid_axes}, got '{axis}'")
    valid_modes = {"canvas", "bbox", "auto"}
    if mode not in valid_modes:
        raise ValueError(f"Mode must be one of {valid_modes}, got '{mode}'")

    axes_to_run = ["vertical", "horizontal"] if axis == "both" else [axis]

    if mode == "auto":
        for ax in axes_to_run:
            if ax == "vertical":
                best_c: float | None = None
                best_score = -1000000
                for c_half in range(2 * w - 1):
                    c0 = c_half / 2.0
                    matches = 0
                    mismatches = 0
                    for r in range(h):
                        for c in range(w):
                            if res[r, c] != background:
                                opp_c = int(round(2 * c0 - c))
                                if 0 <= opp_c < w:
                                    if res[r, opp_c] == res[r, c]:
                                        matches += 1
                                    elif res[r, opp_c] != background:
                                        mismatches += 1
                    score = matches - 5 * mismatches
                    if score > best_score:
                        best_score = score
                        best_c = c0
                if best_c is not None and best_score > 0:
                    for r in range(h):
                        for c in range(w):
                            if res[r, c] != background:
                                opp_c = int(round(2 * best_c - c))
                                if 0 <= opp_c < w and res[r, opp_c] == background:
                                    res[r, opp_c] = res[r, c]
            elif ax == "horizontal":
                best_r: float | None = None
                best_score = -1000000
                for r_half in range(2 * h - 1):
                    r0 = r_half / 2.0
                    matches = 0
                    mismatches = 0
                    for r in range(h):
                        for c in range(w):
                            if res[r, c] != background:
                                opp_r = int(round(2 * r0 - r))
                                if 0 <= opp_r < h:
                                    if res[opp_r, c] == res[r, c]:
                                        matches += 1
                                    elif res[opp_r, c] != background:
                                        mismatches += 1
                    score = matches - 5 * mismatches
                    if score > best_score:
                        best_score = score
                        best_r = r0
                if best_r is not None and best_score > 0:
                    for r in range(h):
                        for c in range(w):
                            if res[r, c] != background:
                                opp_r = int(round(2 * best_r - r))
                                if 0 <= opp_r < h and res[opp_r, c] == background:
                                    res[opp_r, c] = res[r, c]
        return res.tolist()

    if mode == "bbox":
        non_zeros = np.argwhere(arr != background)
        if non_zeros.size == 0:
            return grid
        min_r, min_c = non_zeros.min(axis=0)
        max_r, max_c = non_zeros.max(axis=0)
        r_range = range(min_r, max_r + 1)
        c_range = range(min_c, max_c + 1)
    else:
        min_r, min_c = 0, 0
        max_r, max_c = h - 1, w - 1
        r_range = range(h)
        c_range = range(w)

    for ax in axes_to_run:
        if ax == "vertical":
            for r in r_range:
                for c in c_range:
                    opp_c = max_c - (c - min_c)
                    if res[r, c] != background and res[r, opp_c] == background:
                        res[r, opp_c] = res[r, c]
                    elif res[r, opp_c] != background and res[r, c] == background:
                        res[r, c] = res[r, opp_c]
        elif ax == "horizontal":
            for r in r_range:
                opp_r = max_r - (r - min_r)
                for c in c_range:
                    if res[r, c] != background and res[opp_r, c] == background:
                        res[opp_r, c] = res[r, c]
                    elif res[opp_r, c] != background and res[r, c] == background:
                        res[r, c] = res[opp_r, c]

    return res.tolist()



def draw_line(
    grid: list[list[int]],
    r1: int,
    c1: int,
    r2: int,
    c2: int,
    color: int,
) -> list[list[int]]:
    """Draws a straight line from (r1, c1) to (r2, c2) with the given color."""
    res = [row[:] for row in grid]
    dr = abs(r2 - r1)
    dc = abs(c2 - c1)
    sr = 1 if r1 < r2 else -1
    sc = 1 if c1 < c2 else -1
    err = dr - dc
    r, c = r1, c1
    h = len(res)
    w = len(res[0]) if h > 0 else 0
    while True:
        if 0 <= r < h and 0 <= c < w:
            res[r][c] = color
        if r == r2 and c == c2:
            break
        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            r += sr
        if e2 < dr:
            err += dr
            c += sc
    return res


def move_until_contact(
    grid: list[list[int]],
    obj: SpatialObject,
    dr: int,
    dc: int,
    background: int = 0,
) -> list[list[int]]:
    """Moves a SpatialObject in direction (dr, dc) step by step until touching a grid boundary or non-background obstacle."""
    if dr == 0 and dc == 0:
        return [row[:] for row in grid]
    arr = np.array(grid, dtype=int)
    h, w = arr.shape
    base_arr = np.copy(arr)
    for r, c in obj.coords:
        base_arr[r, c] = background

    curr_coords = list(obj.coords)
    while True:
        next_coords = [(r + dr, c + dc) for r, c in curr_coords]
        if any(r < 0 or r >= h or c < 0 or c >= w for r, c in next_coords):
            break
        if any(base_arr[r, c] != background for r, c in next_coords):
            break
        curr_coords = next_coords

    for r, c in curr_coords:
        base_arr[r, c] = obj.color
    return base_arr.tolist()


def summarize_grid_objects(grid: list[list[int]]) -> str:
    """
    Perceptual Bridge: Constructs a concise, human/LLM-readable summary
    of discrete objects in the grid to bridge the 2D positional attention gap.
    """
    objs = find_objects(grid)
    if not objs:
        h = len(grid)
        w = len(grid[0]) if grid else 0
        return f"Empty grid ({h}x{w}, all background 0)."

    parts: list[str] = []
    for o in objs:
        topo = "hollow frame" if o.is_hollow else "solid block"
        parts.append(
            f"Obj {o.obj_id}: color {o.color}, size {o.height}x{o.width} ({topo}), "
            f"bbox ({o.min_r},{o.min_c})-({o.max_r},{o.max_c}), {o.area} cells"
        )
    return "; ".join(parts)


def check_metamorphic_invariance(
    transform_fn: Callable[[list[list[int]]], list[list[int]]],
    train_pairs: list[dict[str, list[list[int]]]],
) -> tuple[bool, str | None]:
    """
    Metamorphic Invariance Verification:
    Tests whether the synthesized transformation function preserves
    spatial rotational and reflection equivariance on the training pairs:
        transform(rot90(x)) == rot90(transform(x))
        transform(flip_h(x)) == flip_h(transform(x))
        transform(flip_v(x)) == flip_v(transform(x))

    Returns (is_invariant, violation_detail).
    """
    for idx, pair in enumerate(train_pairs):
        inp = pair["input"]
        out = pair["output"]

        # Check rotational equivariance (90 deg)
        try:
            rot_inp = rot90(inp, 1)
            rot_pred = transform_fn(rot_inp)
            expected_rot = rot90(out, 1)
            if rot_pred != expected_rot:
                return (
                    False,
                    f"Example {idx+1} failed 90° rotational equivariance: "
                    "transform(rot90(X)) != rot90(Y). Indicates directional coordinate hardcoding.",
                )
        except Exception as e:
            logger.warning("metamorphic_rotation_error", example=idx + 1, error=str(e))
            return False, f"Example {idx+1} raised {type(e).__name__} on 90° rotation: {e}"

        # Check horizontal reflection equivariance
        try:
            fliph_inp = flip_h(inp)
            fliph_pred = transform_fn(fliph_inp)
            expected_fliph = flip_h(out)
            if fliph_pred != expected_fliph:
                return (
                    False,
                    f"Example {idx+1} failed horizontal flip equivariance: "
                    "transform(flip_h(X)) != flip_h(Y). Indicates left/right axis bias.",
                )
        except Exception as e:
            logger.warning("metamorphic_flip_error", example=idx + 1, error=str(e))
            return False, f"Example {idx+1} raised {type(e).__name__} on horizontal flip: {e}"

        # Check vertical reflection equivariance
        try:
            flipv_inp = flip_v(inp)
            flipv_pred = transform_fn(flipv_inp)
            expected_flipv = flip_v(out)
            if flipv_pred != expected_flipv:
                return (
                    False,
                    f"Example {idx+1} failed vertical flip equivariance: "
                    "transform(flip_v(X)) != flip_v(Y). Indicates top/bottom axis bias.",
                )
        except Exception as e:
            logger.warning("metamorphic_flipv_error", example=idx + 1, error=str(e))
            return False, f"Example {idx+1} raised {type(e).__name__} on vertical flip: {e}"

    return True, None


class PrimitiveDomain(str, Enum):
    CORE = "CORE"
    ORDERING = "ORDERING"
    SYMMETRY = "SYMMETRY"
    TOPOLOGY = "TOPOLOGY"
    EXTRACTION = "EXTRACTION"
    MOTION = "MOTION"
    MORPHOLOGY = "MORPHOLOGY"
    TALLY = "TALLY"


@dataclass(frozen=True)
class SymbolicInvariants:
    is_shape_preserving: bool
    is_1d_tally_output: bool
    tally_orientation: str | None
    is_pixel_count_conserved: bool
    is_pixels_only_added: bool
    has_hollow_objects: bool
    has_high_symmetry: bool
    color_set_preserved: bool
    input_shapes: list[tuple[int, int]]
    output_shapes: list[tuple[int, int]]


@dataclass(frozen=True)
class PrimitiveModule:
    domain: PrimitiveDomain
    helpers_doc: str
    guidance_rules: list[str]
    function_names: list[str]


PRIMITIVE_REGISTRY: dict[PrimitiveDomain, PrimitiveModule] = {
    PrimitiveDomain.CORE: PrimitiveModule(
        domain=PrimitiveDomain.CORE,
        helpers_doc=(
            "- Core Object Primitives:\n"
            "  * `find_objects(grid, background=0, connectivity=8)`: Extracts connected components. Each object has "
            ".color, .dimensions (height, width), .bbox (min_r, min_c, max_r, max_c), .area (cell count), "
            ".is_hollow (bool), .coords (list of (r, c) tuples).\n"
            "  * `count_objects(grid, color=None, connectivity=8)`: Number of connected components.\n"
            "  * `dominant_object(grid)`: Largest non-zero connected component by pixel area.\n"
            "  * `unique_colors(grid)`: Sorted list of unique non-background colors."
        ),
        guidance_rules=[
            "- Color integers are arbitrary symbolic tokens. Never hardcode numeric color literals from training examples into output! Always preserve existing cell colors or extract them dynamically.",
        ],
        function_names=["find_objects", "count_objects", "dominant_object", "unique_colors"],
    ),
    PrimitiveDomain.ORDERING: PrimitiveModule(
        domain=PrimitiveDomain.ORDERING,
        helpers_doc=(
            "- Ordering Primitives:\n"
            "  * `order_columns_by_height(grid, reverse=False)`: Sorts vertical columns by height and packs them starting from the left.\n"
            "  * `column_heights(grid)`: Returns list of heights (count of non-zero cells per column).\n"
            "  * `row_widths(grid)`: Returns list of widths (count of non-zero cells per row).\n"
            "  * `sort_objects(objects, key='height'|'width'|'area'|'min_r'|'min_c', reverse=False)`: Sorts objects by property."
        ),
        guidance_rules=[
            "- For column/bar ordering, use `order_columns_by_height(grid)` directly (preserves colors and packs non-empty columns from the left).",
        ],
        function_names=["order_columns_by_height", "column_heights", "row_widths", "sort_objects"],
    ),
    PrimitiveDomain.SYMMETRY: PrimitiveModule(
        domain=PrimitiveDomain.SYMMETRY,
        helpers_doc=(
            "- Symmetry & Reflection Primitives:\n"
            "  * `complete_symmetry(grid, axis='both'|'vertical'|'horizontal', mode='auto')`: Completes symmetric reflection by mirroring non-background cells across the optimal consensus axis.\n"
            "  * `rot90(grid, k=1)`: Rotates grid 90 degrees counter-clockwise k times.\n"
            "  * `flip_h(grid)`: Flips grid horizontally (left-right reflection).\n"
            "  * `flip_v(grid)`: Flips grid vertically (top-bottom reflection)."
        ),
        guidance_rules=[
            "- For shape completion, use `complete_symmetry(grid, axis='both', mode='auto')` directly.",
        ],
        function_names=["complete_symmetry", "rot90", "flip_h", "flip_v"],
    ),
    PrimitiveDomain.TOPOLOGY: PrimitiveModule(
        domain=PrimitiveDomain.TOPOLOGY,
        helpers_doc=(
            "- Topology & Enclosure Primitives:\n"
            "  * `is_enclosed(inner_obj, outer_obj)`: Checks if inner object's bbox is inside outer object's bbox.\n"
            "  * `fill_holes(grid, color)`: Fills enclosed interior background regions.\n"
            "  * `flood_fill(grid, r, c, color)`: Replaces connected region starting at (r, c) with color.\n"
            "  * `restore_periodic_pattern(grid, period_r=None, period_c=None)`: Restores underlying periodic pattern by filtering noise.\n"
            "  * `count_cells(grid, color=None)`: Returns total number of individual cells with given color."
        ),
        guidance_rules=[
            "- To detect enclosed regions, check hollow frames with `o.is_hollow` or compare coordinates with `is_enclosed(inner, outer)`.",
            "- CRITICAL: Note that `obj.area` is the number of cells in the object. If dots may be diagonally adjacent, count cells using `sum(o.area for o in selected_objects)` or `len(o.coords)` rather than component count.",
        ],
        function_names=["is_enclosed", "fill_holes", "flood_fill", "count_cells", "restore_periodic_pattern"],
    ),
    PrimitiveDomain.EXTRACTION: PrimitiveModule(
        domain=PrimitiveDomain.EXTRACTION,
        helpers_doc=(
            "- Extraction & Subgrid Primitives:\n"
            "  * `crop(grid, min_r, min_c, max_r, max_c)`: Extracts subgrid rectangle.\n"
            "  * `crop_to_content(grid)`: Crops grid to bounding box of all non-background cells.\n"
            "  * `bbox_of_all(grid)`: Returns (min_r, min_c, max_r, max_c) enclosing all non-background cells.\n"
            "  * `paste(dest, src, r, c)`: Pastes src subgrid into dest grid at (r, c)."
        ),
        guidance_rules=[
            "- To extract a selected object, use `crop(grid, obj.min_r, obj.min_c, obj.max_r, obj.max_c)` or `crop_to_content(grid)`.",
        ],
        function_names=["crop", "crop_to_content", "bbox_of_all", "paste"],
    ),
    PrimitiveDomain.MOTION: PrimitiveModule(
        domain=PrimitiveDomain.MOTION,
        helpers_doc=(
            "- Motion & Line Primitives:\n"
            "  * `move_until_contact(grid, obj, dr, dc)`: Translates object in direction (dr, dc) until contacting an obstacle or boundary.\n"
            "  * `draw_line(grid, r1, c1, r2, c2, color)`: Draws straight discrete line from (r1, c1) to (r2, c2)."
        ),
        guidance_rules=[
            "- For sliding motion, use `move_until_contact(grid, obj, dr, dc)`.",
        ],
        function_names=["move_until_contact", "draw_line"],
    ),
    PrimitiveDomain.MORPHOLOGY: PrimitiveModule(
        domain=PrimitiveDomain.MORPHOLOGY,
        helpers_doc=(
            "- Morphology Primitives:\n"
            "  * `denoise(grid, min_size=2)`: Removes isolated noise objects with area < min_size.\n"
            "  * `majority_filter(grid, radius=1)`: Applies local modal majority filter."
        ),
        guidance_rules=[
            "- To remove isolated noise specks, use `denoise(grid, min_size=2)`.",
        ],
        function_names=["denoise", "majority_filter"],
    ),
    PrimitiveDomain.TALLY: PrimitiveModule(
        domain=PrimitiveDomain.TALLY,
        helpers_doc=(
            "- Counting & Tally Primitives:\n"
            "  * `count_cells(grid, color=None)`: Returns total number of individual cells with given color.\n"
            "  * `count_objects(grid, color=None, connectivity=8)`: Returns number of connected components."
        ),
        guidance_rules=[
            "- If output is a fixed-width tally vector of length W: initialize row with background zeros and fill the first count cells with the tally color (e.g. `res = [0] * W; for i in range(min(count, W)): res[i] = tally_color; return [res]`).",
            "- If output is a 1xW horizontal tally vector of zeros: `return [[0] * count]`.\n"
            "- If output is an Hx1 vertical tally vector of zeros: `return [[0] for _ in range(count)]`.",
            "- When computing a tally count of dots or regions: use total cell count `sum(o.area for o in items)` (or `sum(len(o.coords) for o in items)`) rather than component count `len(items)`, because adjacent dots merge into single components under connectivity.",
        ],
        function_names=["count_cells", "count_objects"],
    ),
}


def analyze_symbolic_invariants(
    train_pairs: list[dict[str, list[list[int]]]],
) -> SymbolicInvariants:
    """
    Computes mathematical invariants across training pairs:
    - Shape preserving: True if all train pairs have input_shape == output_shape.
    - 1D tally output: True if all outputs have shape 1xW or Hx1 with different dimensions than input.
    - Pixel count conserved: True if sum of non-zero cells in == out for all pairs.
    - Has hollow objects: True if any input contains a hollow frame/component.
    - Has high symmetry: True if input content reflects onto itself with high consensus score.
    - Color set preserved: True if set of output colors is a subset of input colors.
    """
    if not train_pairs:
        return SymbolicInvariants(
            is_shape_preserving=False,
            is_1d_tally_output=False,
            tally_orientation=None,
            is_pixel_count_conserved=False,
            is_pixels_only_added=False,
            has_hollow_objects=False,
            has_high_symmetry=False,
            color_set_preserved=False,
            input_shapes=[],
            output_shapes=[],
        )

    in_shapes: list[tuple[int, int]] = []
    out_shapes: list[tuple[int, int]] = []
    shape_preserving = True
    all_1d_tally = True
    orientations: list[str] = []
    pixel_conserved = True
    pixels_only_added = True
    any_hollow = False
    high_symmetry = False
    colors_preserved = True

    for pair in train_pairs:
        inp = pair["input"]
        out = pair["output"]
        h_in = len(inp)
        w_in = len(inp[0]) if inp else 0
        h_out = len(out)
        w_out = len(out[0]) if out else 0

        in_shapes.append((h_in, w_in))
        out_shapes.append((h_out, w_out))

        if (h_in, w_in) != (h_out, w_out):
            shape_preserving = False

        if (h_out == 1 and w_out >= 1) or (w_out == 1 and h_out >= 1):
            if h_out == 1 and w_out > 1 and (h_in != 1 or w_in != w_out):
                orientations.append("horizontal")
            elif w_out == 1 and h_out > 1 and (w_in != 1 or h_in != h_out):
                orientations.append("vertical")
            elif h_out == 1 and w_out == 1 and (h_in > 1 or w_in > 1):
                orientations.append("scalar")
            else:
                all_1d_tally = False
        else:
            all_1d_tally = False

        # Non-zero pixel count
        nz_in = sum(1 for row in inp for c in row if c != 0)
        nz_out = sum(1 for row in out for c in row if c != 0)
        if nz_in != nz_out:
            pixel_conserved = False
        if nz_in > nz_out:
            pixels_only_added = False

        # Hollow check
        objs = find_objects(inp, connectivity=8)
        if any(o.is_hollow for o in objs):
            any_hollow = True

        # Symmetry check
        arr_in = np.array(inp, dtype=int)
        if np.any(arr_in != 0):
            sym = complete_symmetry(inp, axis="both", mode="auto")
            arr_sym = np.array(sym, dtype=int)
            if np.sum(arr_in != 0) > 0 and np.sum(arr_in == arr_sym) / arr_in.size > 0.85:
                high_symmetry = True

        # Colors preserved check
        c_in = set(c for row in inp for c in row)
        c_out = set(c for row in out for c in row)
        if not c_out.issubset(c_in):
            colors_preserved = False

    tally_orient = None
    if all_1d_tally and orientations:
        if any(o == "horizontal" for o in orientations):
            tally_orient = "horizontal"
        elif any(o == "vertical" for o in orientations):
            tally_orient = "vertical"
        else:
            tally_orient = "scalar"

    return SymbolicInvariants(
        is_shape_preserving=shape_preserving,
        is_1d_tally_output=all_1d_tally,
        tally_orientation=tally_orient,
        is_pixel_count_conserved=pixel_conserved,
        is_pixels_only_added=pixels_only_added,
        has_hollow_objects=any_hollow,
        has_high_symmetry=high_symmetry,
        color_set_preserved=colors_preserved,
        input_shapes=in_shapes,
        output_shapes=out_shapes,
    )


def resolve_scoped_primitives(
    invariants: SymbolicInvariants,
    primary_domain: PrimitiveDomain,
    secondary_domain: PrimitiveDomain | None = None,
) -> tuple[str, list[str]]:
    """
    Combines Layer 1 Symbolic Invariants with Layer 2 GBNF Abducted Domains
    to resolve the exact scoped primitive prompt and guidance rules.
    """
    selected_domains: list[PrimitiveDomain] = [PrimitiveDomain.CORE]

    # Layer 1 hard invariant overrides:
    if invariants.is_1d_tally_output and PrimitiveDomain.TALLY not in selected_domains:
        selected_domains.append(PrimitiveDomain.TALLY)
    if invariants.has_high_symmetry and PrimitiveDomain.SYMMETRY not in selected_domains:
        selected_domains.append(PrimitiveDomain.SYMMETRY)

    # Layer 2 neural intent:
    if primary_domain not in selected_domains and primary_domain in PRIMITIVE_REGISTRY:
        selected_domains.append(primary_domain)
    if secondary_domain and secondary_domain not in selected_domains and secondary_domain in PRIMITIVE_REGISTRY:
        selected_domains.append(secondary_domain)

    # Prune impossible domains:
    # If pixels are strictly added or conserved, prune MORPHOLOGY (denoising/removal)
    if invariants.is_pixels_only_added and PrimitiveDomain.MORPHOLOGY in selected_domains:
        selected_domains.remove(PrimitiveDomain.MORPHOLOGY)

    # Compile prompt snippets and guidance rules
    docs: list[str] = []
    rules: list[str] = []

    for dom in selected_domains:
        if dom in PRIMITIVE_REGISTRY:
            mod = PRIMITIVE_REGISTRY[dom]
            docs.append(mod.helpers_doc)
            rules.extend(mod.guidance_rules)

    helpers_text = "\n\n".join(docs)
    return helpers_text, rules


def register_macro_primitive(
    name: str,
    params: list[str],
    doc: str,
    rules: list[str] | None = None,
    domain: PrimitiveDomain = PrimitiveDomain.CORE,
) -> None:
    """
    Dynamically registers a newly mined macro into the spatial DSL primitive registry (Milestone 3.1, WO-33).
    Exposes the macro to prompt synthesis and primitive scoping.
    """
    if domain in PRIMITIVE_REGISTRY:
        existing = PRIMITIVE_REGISTRY[domain]
        fn_names = list(existing.function_names)
        if name not in fn_names:
            fn_names.append(name)
        new_doc = existing.helpers_doc + f"\n  * `{name}({', '.join(params)})`: {doc}"
        new_rules = list(existing.guidance_rules)
        if rules:
            new_rules.extend(rules)
        PRIMITIVE_REGISTRY[domain] = PrimitiveModule(
            domain=domain,
            helpers_doc=new_doc,
            guidance_rules=new_rules,
            function_names=fn_names,
        )


def build_scene_graph(
    grid: list[list[int]],
    background: int = 0,
    connectivity: int = 8,
) -> dict[str, object]:
    """
    Constructs a symbolic Scene Graph representation of a discrete 2D grid (Milestone 3.2, WO-33).
    Extracts connected components and computes pairwise topological relationships:
    - contains(obj_A, obj_B): obj_B is enclosed inside hollow obj_A
    - adjacent(obj_A, obj_B, direction): obj_A touches obj_B (min Chebyshev distance <= 1)
    - aligned_col(obj_A, obj_B): obj_A and obj_B share column alignment
    - aligned_row(obj_A, obj_B): obj_A and obj_B share row alignment
    """
    objs = find_objects(grid, background=background, connectivity=connectivity)
    h = len(grid)
    w = len(grid[0]) if grid else 0

    obj_dicts: list[dict[str, object]] = []
    for o in objs:
        mean_r = sum(r for r, _ in o.coords) / len(o.coords) if o.coords else float(o.min_r)
        mean_c = sum(c for _, c in o.coords) / len(o.coords) if o.coords else float(o.min_c)
        obj_dicts.append({
            "id": f"obj_{o.obj_id}",
            "color": o.color,
            "min_r": o.min_r,
            "min_c": o.min_c,
            "max_r": o.max_r,
            "max_c": o.max_c,
            "height": o.height,
            "width": o.width,
            "area": o.area,
            "is_hollow": o.is_hollow,
            "centroid": (round(mean_r, 1), round(mean_c, 1)),
            "coords": o.coords,
        })

    contains_rels: list[str] = []
    adjacent_rels: list[str] = []
    aligned_rels: list[str] = []
    num_objs = len(objs)
    for i in range(num_objs):
        for j in range(num_objs):
            if i == j:
                continue
            o1 = objs[i]
            o2 = objs[j]
            id1 = f"obj_{o1.obj_id}"
            id2 = f"obj_{o2.obj_id}"

            # 1. contains
            if is_enclosed(o2, o1):
                contains_rels.append(f"contains({id1}, {id2})")

            # 2. adjacent (undirected, report once for i < j)
            if i < j:
                coords1 = o1.coords
                coords2 = o2.coords
                # Bounding box proximity check
                if not (
                    o1.max_r < o2.min_r - 1
                    or o2.max_r < o1.min_r - 1
                    or o1.max_c < o2.min_c - 1
                    or o2.max_c < o1.min_c - 1
                ):
                    min_cheb = min(
                        max(abs(r1 - r2), abs(c1 - c2))
                        for r1, c1 in coords1
                        for r2, c2 in coords2
                    )
                    if min_cheb <= 1:
                        c1_r = sum(r for r, _ in coords1) / len(coords1)
                        c1_c = sum(c for _, c in coords1) / len(coords1)
                        c2_r = sum(r for r, _ in coords2) / len(coords2)
                        c2_c = sum(c for _, c in coords2) / len(coords2)
                        dr = c2_r - c1_r
                        dc = c2_c - c1_c
                        if abs(dr) >= abs(dc):
                            direction = "below" if dr > 0 else "above"
                        else:
                            direction = "right" if dc > 0 else "left"
                        adjacent_rels.append(f"adjacent({id1}, {id2}, direction={direction})")

            # 3. aligned (undirected, report once for i < j)
            if i < j:
                c1_c_round = round(sum(c for _, c in o1.coords) / len(o1.coords))
                c2_c_round = round(sum(c for _, c in o2.coords) / len(o2.coords))
                if o1.min_c == o2.min_c or o1.max_c == o2.max_c or c1_c_round == c2_c_round:
                    aligned_rels.append(f"aligned_col({id1}, {id2})")

                c1_r_round = round(sum(r for r, _ in o1.coords) / len(o1.coords))
                c2_r_round = round(sum(r for r, _ in o2.coords) / len(o2.coords))
                if o1.min_r == o2.min_r or o1.max_r == o2.max_r or c1_r_round == c2_r_round:
                    aligned_rels.append(f"aligned_row({id1}, {id2})")

    relations: list[str] = contains_rels + adjacent_rels + aligned_rels[:8]
    if len(relations) > 20:
        relations = relations[:20]

    return {
        "height": h,
        "width": w,
        "background": background,
        "objects": obj_dicts,
        "relations": relations,
    }


def format_scene_graph_prompt(scene_graph: dict[str, object]) -> str:
    """Formats a symbolic scene graph into structured text for model consumption."""
    h = scene_graph.get("height", 0)
    w = scene_graph.get("width", 0)
    bg = scene_graph.get("background", 0)
    raw_objs = scene_graph.get("objects", [])
    objs = raw_objs if isinstance(raw_objs, list) else []
    raw_rels = scene_graph.get("relations", [])
    rels = raw_rels if isinstance(raw_rels, list) else []

    if not objs:
        return f"Scene: {h}x{w} grid, background {bg}, no foreground objects."

    if len(objs) > 12:
        sorted_objs = sorted(
            objs,
            key=lambda o: int(o.get("area", 0)) if isinstance(o, dict) and isinstance(o.get("area"), (int, float)) else 0,
            reverse=True,
        )
        display_objs = sorted_objs[:10]
        omitted = len(objs) - 10
    else:
        display_objs = objs
        omitted = 0

    lines: list[str] = [f"Scene: {h}x{w} (bg={bg}):"]
    lines.append("  Objects:")
    for o in display_objs:
        if isinstance(o, dict):
            oid = o.get("id", "obj")
            color = o.get("color")
            shape = f"{o.get('height')}x{o.get('width')}"
            area = o.get("area")
            topo = "hollow" if o.get("is_hollow") else "solid"
            bbox = f"({o.get('min_r')},{o.get('min_c')})-({o.get('max_r')},{o.get('max_c')})"
            centroid = o.get("centroid")
            lines.append(f"    - {oid}: color={color}, shape={shape}, area={area}, bbox={bbox}, topo={topo}, centroid={centroid}")
    if omitted > 0:
        lines.append(f"    - ... ({omitted} smaller objects omitted)")

    if rels:
        lines.append("  Relations:")
        for r in rels:
            lines.append(f"    - {r}")

    return "\n".join(lines)


def generate_relational_diff(pred: list[list[int]], expected: list[list[int]]) -> str:
    """
    Constructs high-level transformation and object deltas between predicted
    and expected grids for the CEGIS repair loop (Milestone 3.3, WO-33).
    """
    pred_h, pred_w = len(pred), len(pred[0]) if pred else 0
    exp_h, exp_w = len(expected), len(expected[0]) if expected else 0
    if (pred_h, pred_w) != (exp_h, exp_w):
        return f"Shape mismatch: expected dimensions {exp_h}x{exp_w}, but got {pred_h}x{pred_w}."

    sg_pred = build_scene_graph(pred)
    sg_exp = build_scene_graph(expected)

    objs_pred = {str(o["id"]): o for o in cast(list[dict[str, object]], sg_pred.get("objects", []))}
    objs_exp = {str(o["id"]): o for o in cast(list[dict[str, object]], sg_exp.get("objects", []))}

    deltas: list[str] = []

    pred_by_color: dict[int, list[dict[str, object]]] = {}
    for o in objs_pred.values():
        c = int(cast(int, o["color"]))
        pred_by_color.setdefault(c, []).append(o)

    exp_by_color: dict[int, list[dict[str, object]]] = {}
    for o in objs_exp.values():
        c = int(cast(int, o["color"]))
        exp_by_color.setdefault(c, []).append(o)

    all_colors = sorted(set(pred_by_color.keys()) | set(exp_by_color.keys()))

    for c in all_colors:
        p_list = pred_by_color.get(c, [])
        e_list = exp_by_color.get(c, [])

        if not p_list and e_list:
            for eo in e_list:
                deltas.append(
                    f"Missing object [color={c}]: expected {eo['height']}x{eo['width']} component at bbox ({eo['min_r']},{eo['min_c']})-({eo['max_r']},{eo['max_c']})"
                )
        elif p_list and not e_list:
            for po in p_list:
                deltas.append(
                    f"Unexpected extra object [color={c}]: produced {po['height']}x{po['width']} component at bbox ({po['min_r']},{po['min_c']})-({po['max_r']},{po['max_c']})"
                )
        else:
            for po, eo in itertools.zip_longest(p_list, e_list):
                if po is None and eo is not None:
                    deltas.append(f"Missing component [color={c}]: expected at centroid {eo['centroid']}")
                elif eo is None and po is not None:
                    deltas.append(f"Unexpected extra component [color={c}]: produced at centroid {po['centroid']}")
                elif po is not None and eo is not None:
                    p_cent = cast(tuple[float, float], po["centroid"])
                    e_cent = cast(tuple[float, float], eo["centroid"])
                    dr = round(p_cent[0] - e_cent[0], 1)
                    dc = round(p_cent[1] - e_cent[1], 1)
                    if dr != 0.0 or dc != 0.0:
                        deltas.append(
                            f"Object [color={c}] position mismatch: at centroid {p_cent}, expected {e_cent}. Delta: dr={dr:+0.1f}, dc={dc:+0.1f}"
                        )
                    if po["is_hollow"] != eo["is_hollow"]:
                        p_topo = "hollow frame" if po["is_hollow"] else "solid block"
                        e_topo = "hollow frame" if eo["is_hollow"] else "solid block"
                        deltas.append(
                            f"Object [color={c}] topology mismatch: produced {p_topo}, expected {e_topo}"
                        )
                    if po["area"] != eo["area"]:
                        deltas.append(
                            f"Object [color={c}] size mismatch: produced {po['area']} cells ({po['height']}x{po['width']}), expected {eo['area']} cells ({eo['height']}x{eo['width']})"
                        )

    diff_cells = sum(1 for r in range(exp_h) for col in range(exp_w) if pred[r][col] != expected[r][col])
    if deltas:
        delta_str = ";\n  ".join(deltas[:5])
        return f"Relational Diffs ({diff_cells} cells differ):\n  {delta_str}"

    return f"Cell differences: {diff_cells} cells differ between predicted and expected grids."

