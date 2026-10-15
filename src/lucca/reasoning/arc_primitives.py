"""
Project Lucca — ARC Spatial Primitives Library
Spec 12, Spec 32, Priority 2A
Provides canonical, robust, self-contained 2D spatial primitives for ARC-AGI program synthesis.
All operations return new grids or structured objects without mutating inputs.
"""

from __future__ import annotations

from collections import deque
from typing import Mapping


def clone_grid(grid: list[list[int]]) -> list[list[int]]:
    """Deep clones a 2D integer grid."""
    return [list(row) for row in grid]


def flood_fill(grid: list[list[int]], r: int, c: int, new_color: int) -> list[list[int]]:
    """
    4-way flood fill starting at (r, c). Replaces all contiguous cells
    matching the original color at (r, c) with new_color.
    """
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0
    if not (0 <= r < h and 0 <= c < w):
        return clone_grid(grid)

    target_color = grid[r][c]
    if target_color == new_color:
        return clone_grid(grid)

    out = clone_grid(grid)
    q: deque[tuple[int, int]] = deque([(r, c)])
    visited: set[tuple[int, int]] = {(r, c)}
    out[r][c] = new_color

    while q:
        cr, cc = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = cr + dr, cc + dc
            if 0 <= nr < h and 0 <= nc < w and (nr, nc) not in visited:
                if out[nr][nc] == target_color:
                    visited.add((nr, nc))
                    out[nr][nc] = new_color
                    q.append((nr, nc))
    return out


def replace_color(grid: list[list[int]], old_color: int, new_color: int) -> list[list[int]]:
    """Replaces all occurrences of old_color in grid with new_color."""
    return [[new_color if cell == old_color else cell for cell in row] for row in grid]


def rotate_90(grid: list[list[int]], clockwise: bool = True, times: int = 1) -> list[list[int]]:
    """Rotates grid by 90 degrees times times (clockwise if True, else counter-clockwise)."""
    k = (times % 4 + 4) % 4
    if not clockwise:
        k = (4 - k) % 4

    out = clone_grid(grid)
    for _ in range(k):
        out = [list(col) for col in zip(*out[::-1])]
    return out


def flip_h(grid: list[list[int]]) -> list[list[int]]:
    """Horizontal mirror reflection (left-to-right)."""
    return [row[::-1] for row in grid]


def flip_v(grid: list[list[int]]) -> list[list[int]]:
    """Vertical mirror reflection (top-to-bottom)."""
    return grid[::-1]


def bounding_box(grid: list[list[int]], color: int | None = None) -> tuple[int, int, int, int]:
    """
    Returns (min_r, min_c, max_r, max_c) enclosing all cells with the given color
    (or all non-zero cells if color is None).
    Returns (0, 0, 0, 0) if no matching cells exist.
    """
    coords: list[tuple[int, int]] = []
    for r, row in enumerate(grid):
        for c, val in enumerate(row):
            if (color is None and val != 0) or (color is not None and val == color):
                coords.append((r, c))

    if not coords:
        return (0, 0, 0, 0)

    min_r = min(r for r, _ in coords)
    max_r = max(r for r, _ in coords)
    min_c = min(c for _, c in coords)
    max_c = max(c for _, c in coords)
    return (min_r, min_c, max_r, max_c)


def crop(grid: list[list[int]], min_r: int, min_c: int, max_r: int, max_c: int) -> list[list[int]]:
    """Extracts subgrid rectangle [min_r:max_r+1, min_c:max_c+1] with bounds clamping."""
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0
    r0 = max(0, min_r)
    r1 = min(h - 1, max_r)
    c0 = max(0, min_c)
    c1 = min(w - 1, max_c)
    if r0 > r1 or c0 > c1:
        return [[]]
    return [row[c0 : c1 + 1] for row in grid[r0 : r1 + 1]]


def paste(
    dest: list[list[int]],
    src: list[list[int]],
    r: int,
    c: int,
    transparent_color: int | None = 0,
) -> list[list[int]]:
    """Pastes src grid into a copy of dest starting at top-left (r, c)."""
    out = clone_grid(dest)
    h_d, w_d = len(out), len(out[0]) if out else 0
    h_s, w_s = len(src), len(src[0]) if src else 0

    for i in range(h_s):
        for j in range(w_s):
            val = src[i][j]
            if transparent_color is not None and val == transparent_color:
                continue
            dr, dc = r + i, c + j
            if 0 <= dr < h_d and 0 <= dc < w_d:
                out[dr][dc] = val
    return out


def get_connected_components(
    grid: list[list[int]],
    color: int | None = None,
    connectivity: int = 8,
) -> list[dict[str, int | list[tuple[int, int]] | tuple[int, int, int, int]]]:
    """
    Extracts connected components from grid.
    If color is specified, only finds components of that color.
    If color is None, finds components of all non-zero colors.
    connectivity: 4 (orthogonal) or 8 (orthogonal + diagonal).
    """
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0
    visited: set[tuple[int, int]] = set()
    components: list[dict[str, int | list[tuple[int, int]] | tuple[int, int, int, int]]] = []

    neighbor_deltas = (
        ((-1, 0), (1, 0), (0, -1), (0, 1))
        if connectivity == 4
        else ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
    )

    for r in range(h):
        for c in range(w):
            val = grid[r][c]
            if (r, c) in visited:
                continue
            if color is not None and val != color:
                continue
            if color is None and val == 0:
                continue

            comp_coords: list[tuple[int, int]] = []
            comp_color = val
            q: deque[tuple[int, int]] = deque([(r, c)])
            visited.add((r, c))

            while q:
                cr, cc = q.popleft()
                comp_coords.append((cr, cc))
                for dr, dc in neighbor_deltas:
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < h and 0 <= nc < w and (nr, nc) not in visited:
                        if grid[nr][nc] == comp_color:
                            visited.add((nr, nc))
                            q.append((nr, nc))

            min_r = min(cr for cr, _ in comp_coords)
            max_r = max(cr for cr, _ in comp_coords)
            min_c = min(cc for _, cc in comp_coords)
            max_c = max(cc for _, cc in comp_coords)

            components.append(
                {
                    "color": comp_color,
                    "coords": comp_coords,
                    "area": len(comp_coords),
                    "bbox": (min_r, min_c, max_r, max_c),
                    "min_r": min_r,
                    "max_r": max_r,
                    "min_c": min_c,
                    "max_c": max_c,
                    "height": max_r - min_r + 1,
                    "width": max_c - min_c + 1,
                }
            )

    return components


def get_objects(
    grid: list[list[int]],
    background: int = 0,
    connectivity: int = 8,
) -> list[dict[str, int | list[tuple[int, int]] | tuple[int, int, int, int]]]:
    """Extracts non-background objects from grid with topological metadata."""
    comps = get_connected_components(grid, color=None, connectivity=connectivity)
    return [c for c in comps if c["color"] != background]


def gravity_drop(
    grid: list[list[int]],
    color: int | None = None,
    direction: str = "down",
) -> list[list[int]]:
    """
    Applies discrete gravity to cells of specified color (or all non-zero cells if color is None)
    in the given direction ("down", "up", "left", "right").
    Cells stack against the boundary and stationary obstacles.
    """
    out = clone_grid(grid)
    h = len(out)
    w = len(out[0]) if h > 0 else 0

    if direction == "down":
        for c in range(w):
            falling: list[int] = []
            for r in range(h):
                val = out[r][c]
                if (color is None and val != 0) or (color is not None and val == color):
                    falling.append(val)
                    out[r][c] = 0
            # Place at bottom
            for idx, val in enumerate(falling):
                out[h - len(falling) + idx][c] = val

    elif direction == "up":
        for c in range(w):
            falling = []
            for r in range(h):
                val = out[r][c]
                if (color is None and val != 0) or (color is not None and val == color):
                    falling.append(val)
                    out[r][c] = 0
            # Place at top
            for idx, val in enumerate(falling):
                out[idx][c] = val

    elif direction == "left":
        for r in range(h):
            falling = []
            for c in range(w):
                val = out[r][c]
                if (color is None and val != 0) or (color is not None and val == color):
                    falling.append(val)
                    out[r][c] = 0
            # Place at left
            for idx, val in enumerate(falling):
                out[r][idx] = val

    elif direction == "right":
        for r in range(h):
            falling = []
            for c in range(w):
                val = out[r][c]
                if (color is None and val != 0) or (color is not None and val == color):
                    falling.append(val)
                    out[r][c] = 0
            # Place at right
            for idx, val in enumerate(falling):
                out[r][w - len(falling) + idx] = val

    return out


def align_objects(
    obj_a: Mapping[str, object] | list[tuple[int, int]],
    obj_b: Mapping[str, object] | list[tuple[int, int]],
    anchor: str = "top-left",
) -> tuple[int, int]:
    """
    Computes translation delta (dr, dc) to align object A with object B
    using the specified anchor: 'top-left', 'center', 'bottom-right'.
    """
    raw_coords_a = obj_a.get("coords") if isinstance(obj_a, Mapping) else obj_a
    raw_coords_b = obj_b.get("coords") if isinstance(obj_b, Mapping) else obj_b
    coords_a: list[tuple[int, int]] = raw_coords_a if isinstance(raw_coords_a, list) else []  # type: ignore
    coords_b: list[tuple[int, int]] = raw_coords_b if isinstance(raw_coords_b, list) else []  # type: ignore
    if not coords_a or not coords_b:
        return (0, 0)

    min_ra, max_ra = min(r for r, _ in coords_a), max(r for r, _ in coords_a)
    min_ca, max_ca = min(c for _, c in coords_a), max(c for _, c in coords_a)
    min_rb, max_rb = min(r for r, _ in coords_b), max(r for r, _ in coords_b)
    min_cb, max_cb = min(c for _, c in coords_b), max(c for _, c in coords_b)

    if anchor == "center":
        ca_r, ca_c = (min_ra + max_ra) / 2.0, (min_ca + max_ca) / 2.0
        cb_r, cb_c = (min_rb + max_rb) / 2.0, (min_cb + max_cb) / 2.0
        return (int(round(cb_r - ca_r)), int(round(cb_c - ca_c)))
    elif anchor == "bottom-right":
        return (max_rb - max_ra, max_cb - max_ca)
    else:  # top-left
        return (min_rb - min_ra, min_cb - min_ca)


__all__ = [
    "align_objects",
    "bounding_box",
    "clone_grid",
    "crop",
    "flip_h",
    "flip_v",
    "flood_fill",
    "get_connected_components",
    "get_objects",
    "gravity_drop",
    "paste",
    "replace_color",
    "rotate_90",
]
