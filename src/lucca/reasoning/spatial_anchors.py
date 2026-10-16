"""
Project Lucca — General Spatial Anchors & Coordinate Utilities
==============================================================
Provides foundational 2D image processing, geometry, and coordinate anchor
primitives for neurosymbolic program synthesis and CEGIS self-repair.

Zero Handcoded Benchmark Primitives:
- These are standard computational vision utilities (equivalent to skimage/scipy/cv2),
  not task-specific domain heuristics.
- Fully typed with zero `Any` annotations per D-AUD-01.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence, cast

import numpy as np
import numpy.typing as npt
import scipy.ndimage


@dataclass(frozen=True)
class Component:
    """A single connected object in a 2D grid."""

    color: int
    mask: npt.NDArray[np.bool_]  # Boolean 2D array of same shape as original grid
    min_r: int
    min_c: int
    max_r: int
    max_c: int
    height: int
    width: int
    area: int
    centroid: tuple[float, float]

    @property
    def bbox(self) -> tuple[int, int, int, int, int, int]:
        """Returns (min_r, min_c, max_r, max_c, height, width)."""
        return (self.min_r, self.min_c, self.max_r, self.max_c, self.height, self.width)

    def cropped_mask(self) -> npt.NDArray[np.bool_]:
        """Returns the binary mask cropped tightly to its bounding box."""
        return self.mask[self.min_r : self.max_r + 1, self.min_c : self.max_c + 1]


def bbox(mask: npt.NDArray[np.generic]) -> tuple[int, int, int, int, int, int] | None:
    """
    Computes tight bounding box of all non-zero/True pixels in a 2D mask.
    Returns: (min_r, min_c, max_r, max_c, height, width) or None if mask is empty.
    """
    rows, cols = np.where(mask)
    if len(rows) == 0:
        return None
    min_r: int = int(np.min(rows))
    max_r: int = int(np.max(rows))
    min_c: int = int(np.min(cols))
    max_c: int = int(np.max(cols))
    height: int = max_r - min_r + 1
    width: int = max_c - min_c + 1
    return (min_r, min_c, max_r, max_c, height, width)


def centroid(mask: npt.NDArray[np.generic]) -> tuple[float, float] | None:
    """
    Computes center of mass (mean_row, mean_col) of non-zero pixels.
    Returns None if mask is empty.
    """
    rows, cols = np.where(mask)
    if len(rows) == 0:
        return None
    return (float(np.mean(rows)), float(np.mean(cols)))


def crop(
    arr: npt.NDArray[np.generic],
    bounds: tuple[int, int, int, int, int, int] | tuple[int, int, int, int],
) -> npt.NDArray[np.generic]:
    """
    Crops a sub-grid using bounding box coordinates.
    Accepts (min_r, min_c, max_r, max_c) or (min_r, min_c, max_r, max_c, height, width).
    """
    min_r, min_c, max_r, max_c = bounds[0], bounds[1], bounds[2], bounds[3]
    return np.copy(arr[min_r : max_r + 1, min_c : max_c + 1])


def connected_components(
    arr: npt.NDArray[np.generic] | Sequence[Sequence[int]],
    connectivity: int = 8,
    background: int = 0,
) -> list[Component]:
    """
    Identifies all connected components for non-background colors in a 2D integer grid.

    Args:
        arr: 2D integer array or list of lists (H, W).
        connectivity: 4 (orthogonal) or 8 (orthogonal + diagonal).
        background: Value considered background to ignore (default 0).
    """
    grid_arr = np.asarray(arr)
    if connectivity == 8:
        struct: npt.NDArray[np.bool_] = np.ones((3, 3), dtype=bool)
    else:
        struct = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)

    unique_colors = [int(c) for c in np.unique(grid_arr) if c != background]
    components: list[Component] = []

    for color in unique_colors:
        color_mask = (grid_arr == color)
        labeled_arr, num_features = scipy.ndimage.label(color_mask, structure=struct)
        for feat_id in range(1, num_features + 1):
            comp_mask = (labeled_arr == feat_id)
            b = bbox(comp_mask)
            if b is None:
                continue
            min_r, min_c, max_r, max_c, h, w = b
            c_pos = centroid(comp_mask) or (float(min_r), float(min_c))
            components.append(
                Component(
                    color=color,
                    mask=comp_mask,
                    min_r=min_r,
                    min_c=min_c,
                    max_r=max_r,
                    max_c=max_c,
                    height=h,
                    width=w,
                    area=int(np.sum(comp_mask)),
                    centroid=c_pos,
                )
            )

    return components


def is_identical_shape(mask_a: npt.NDArray[np.generic], mask_b: npt.NDArray[np.generic]) -> bool:
    """
    Tests whether two binary masks have the exact same shape template under translation.
    Crops both to their bounding boxes and tests array equality.
    """
    b_a = bbox(mask_a)
    b_b = bbox(mask_b)
    if b_a is None or b_b is None:
        return b_a == b_b
    if b_a[4] != b_b[4] or b_a[5] != b_b[5]:
        return False
    cropped_a = mask_a[b_a[0] : b_a[2] + 1, b_a[1] : b_a[3] + 1]
    cropped_b = mask_b[b_b[0] : b_b[2] + 1, b_b[1] : b_b[3] + 1]
    return bool(np.array_equal(cropped_a, cropped_b))


def rot90(arr: npt.NDArray[np.generic], k: int = 1) -> npt.NDArray[np.generic]:
    """Rotates grid 90 degrees counter-clockwise k times."""
    return np.ascontiguousarray(np.rot90(arr, k=k))


def flip_h(arr: npt.NDArray[np.generic]) -> npt.NDArray[np.generic]:
    """Flips grid horizontally (left-to-right mirror)."""
    return np.ascontiguousarray(np.fliplr(arr))


def flip_v(arr: npt.NDArray[np.generic]) -> npt.NDArray[np.generic]:
    """Flips grid vertically (upside-down mirror)."""
    return np.ascontiguousarray(np.flipud(arr))


def flood_fill(
    arr: npt.NDArray[np.generic],
    start_r: int,
    start_c: int,
    fill_val: int,
) -> npt.NDArray[np.generic]:
    """
    Standard 4-way flood fill starting from (start_r, start_c).
    Fills all connected pixels matching the starting pixel's color with fill_val.
    """
    out = np.copy(arr)
    h, w = out.shape
    if not (0 <= start_r < h and 0 <= start_c < w):
        return out
    target_val = int(out[start_r, start_c])
    if target_val == fill_val:
        return out

    queue: list[tuple[int, int]] = [(start_r, start_c)]
    visited = np.zeros((h, w), dtype=bool)
    visited[start_r, start_c] = True

    while queue:
        r, c = queue.pop(0)
        out[r, c] = fill_val
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc]:
                if out[nr, nc] == target_val:
                    visited[nr, nc] = True
                    queue.append((nr, nc))

    return out


def find_cavities(arr: npt.NDArray[np.generic], background_val: int = 0) -> npt.NDArray[np.bool_]:
    """
    Identifies enclosed interior cavities (voids) in a grid.
    Returns a boolean mask of pixels that match background_val but cannot
    reach the grid boundary via 4-connectivity.
    """
    h, w = arr.shape
    bg_mask = (arr == background_val)

    # Flood fill from all boundary background pixels
    reachable_from_boundary = np.zeros((h, w), dtype=bool)
    boundary_pixels: list[tuple[int, int]] = []

    for r in range(h):
        if bg_mask[r, 0]:
            boundary_pixels.append((r, 0))
        if bg_mask[r, w - 1]:
            boundary_pixels.append((r, w - 1))
    for c in range(w):
        if bg_mask[0, c]:
            boundary_pixels.append((0, c))
        if bg_mask[h - 1, c]:
            boundary_pixels.append((h - 1, c))

    for r, c in boundary_pixels:
        reachable_from_boundary[r, c] = True

    queue = list(boundary_pixels)
    while queue:
        r, c = queue.pop(0)
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                if bg_mask[nr, nc] and not reachable_from_boundary[nr, nc]:
                    reachable_from_boundary[nr, nc] = True
                    queue.append((nr, nc))

    # Cavities are background pixels that cannot reach the boundary
    return cast(npt.NDArray[np.bool_], np.logical_and(bg_mask, ~reachable_from_boundary))


def color_counts(arr: npt.NDArray[np.generic]) -> dict[int, int]:
    """Returns frequency count of each discrete color in the grid."""
    unique, counts = np.unique(arr, return_counts=True)
    return {int(u): int(c) for u, c in zip(unique, counts)}


def canvas(height: int, width: int, fill_val: int = 0) -> npt.NDArray[np.int_]:
    """Constructs a fresh 2D numpy canvas of specified dimensions filled with fill_val."""
    return np.full((height, width), fill_val, dtype=int)


def paste(
    base: npt.NDArray[np.generic],
    patch: npt.NDArray[np.generic],
    top_r: int,
    left_c: int,
    transparent_val: int | None = None,
) -> npt.NDArray[np.generic]:
    """
    Pastes patch onto base grid starting at (top_r, left_c), clipping to base boundaries.
    If transparent_val is given, pixels matching transparent_val in patch are not pasted.
    """
    out = np.copy(base)
    h_b, w_b = out.shape
    h_p, w_p = patch.shape

    # Determine overlapping bounds
    r_start = max(0, top_r)
    r_end = min(h_b, top_r + h_p)
    c_start = max(0, left_c)
    c_end = min(w_b, left_c + w_p)

    if r_start >= r_end or c_start >= c_end:
        return out

    p_r_start = r_start - top_r
    p_r_end = p_r_start + (r_end - r_start)
    p_c_start = c_start - left_c
    p_c_end = p_c_start + (c_end - c_start)

    sub_patch = patch[p_r_start:p_r_end, p_c_start:p_c_end]
    if transparent_val is None:
        out[r_start:r_end, c_start:c_end] = sub_patch
    else:
        mask = (sub_patch != transparent_val)
        target_slice = out[r_start:r_end, c_start:c_end]
        target_slice[mask] = sub_patch[mask]
        out[r_start:r_end, c_start:c_end] = target_slice

    return out
