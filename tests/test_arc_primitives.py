"""
Project Lucca — Unit Tests for ARC Spatial Primitives Library
Tests all 10 canonical operations per Priority 2A.
"""

import pytest

from lucca.reasoning.arc_primitives import (
    align_objects,
    bounding_box,
    crop,
    flip_h,
    flip_v,
    flood_fill,
    get_connected_components,
    get_objects,
    gravity_drop,
    paste,
    replace_color,
    rotate_90,
)
from lucca.reasoning.spatial_dsl import (
    boolean_combine,
    extract_quadrant_macrogrid,
    extrapolate_ray,
    fill_framed_enclosures,
    find_separator_lines,
    kronecker_fractal_tiling,
    palette_swap_by_legend,
    quadrant_tile,
    split_by_separators,
    tile_and_reflect,
)



def test_flood_fill():
    grid = [
        [1, 1, 0],
        [1, 0, 0],
        [0, 0, 2],
    ]
    res = flood_fill(grid, 0, 0, 3)
    assert res == [
        [3, 3, 0],
        [3, 0, 0],
        [0, 0, 2],
    ]
    # Verify input unchanged
    assert grid[0][0] == 1


def test_replace_color():
    grid = [[1, 2], [2, 1]]
    res = replace_color(grid, 2, 5)
    assert res == [[1, 5], [5, 1]]


def test_rotate_90():
    grid = [
        [1, 2],
        [3, 4],
    ]
    # Clockwise
    cw = rotate_90(grid, clockwise=True)
    assert cw == [
        [3, 1],
        [4, 2],
    ]
    # Counter-clockwise
    ccw = rotate_90(grid, clockwise=False)
    assert ccw == [
        [2, 4],
        [1, 3],
    ]


def test_flip_h_and_v():
    grid = [
        [1, 2, 3],
        [4, 5, 6],
    ]
    assert flip_h(grid) == [
        [3, 2, 1],
        [6, 5, 4],
    ]
    assert flip_v(grid) == [
        [4, 5, 6],
        [1, 2, 3],
    ]


def test_bounding_box():
    grid = [
        [0, 0, 0, 0],
        [0, 2, 2, 0],
        [0, 2, 0, 0],
        [0, 0, 0, 0],
    ]
    assert bounding_box(grid, color=2) == (1, 1, 2, 2)
    assert bounding_box(grid) == (1, 1, 2, 2)
    assert bounding_box(grid, color=5) == (0, 0, 0, 0)


def test_crop_and_paste():
    grid = [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
    ]
    sub = crop(grid, 0, 1, 1, 2)
    assert sub == [
        [1, 2],
        [4, 5],
    ]
    dest = [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
    ]
    pasted = paste(dest, sub, 1, 1)
    assert pasted == [
        [0, 0, 0],
        [0, 1, 2],
        [0, 4, 5],
    ]


def test_get_connected_components_and_objects():
    grid = [
        [1, 1, 0, 2],
        [1, 0, 0, 2],
        [0, 0, 0, 0],
    ]
    objs = get_objects(grid, connectivity=4)
    assert len(objs) == 2
    colors = {o["color"] for o in objs}
    assert colors == {1, 2}

    obj1 = next(o for o in objs if o["color"] == 1)
    assert obj1["area"] == 3
    assert obj1["bbox"] == (0, 0, 1, 1)


def test_gravity_drop():
    grid = [
        [1, 0, 2],
        [0, 0, 0],
        [0, 0, 0],
    ]
    dropped = gravity_drop(grid, direction="down")
    assert dropped == [
        [0, 0, 0],
        [0, 0, 0],
        [1, 0, 2],
    ]

    grid_h = [
        [1, 0, 0],
        [0, 2, 0],
    ]
    dropped_right = gravity_drop(grid_h, direction="right")
    assert dropped_right == [
        [0, 0, 1],
        [0, 0, 2],
    ]


def test_align_objects():
    obj_a = {"coords": [(0, 0), (0, 1)]}
    obj_b = {"coords": [(2, 3), (2, 4)]}
    dr, dc = align_objects(obj_a, obj_b, anchor="top-left")
    assert (dr, dc) == (2, 3)


def test_find_and_split_separators():
    grid = [
        [1, 2, 0],
        [7, 7, 7],
        [3, 4, 0],
    ]
    sep_r, sep_c = find_separator_lines(grid)
    assert sep_r == [1]
    assert sep_c == []
    sub = split_by_separators(grid, sep_r, sep_c)
    assert len(sub) == 2
    assert sub[0][0] == [[1, 2, 0]]
    assert sub[1][0] == [[3, 4, 0]]


def test_boolean_combine():
    sg1 = [[0, 1], [0, 0]]
    sg2 = [[0, 0], [2, 0]]
    comb = boolean_combine([sg1, sg2], op="nor", output_color=8)
    assert comb == [[8, 0], [0, 8]]


def test_tile_and_reflect():
    grid = [[1, 2]]
    tiled = tile_and_reflect(grid, repeat_r=2, repeat_c=2, alternate_flip_h=True)
    assert tiled == [
        [1, 2, 1, 2],
        [2, 1, 2, 1],
    ]


def test_quadrant_tile():
    grid = [[1, 2], [3, 4]]
    res = quadrant_tile(grid)
    # top-left is 180 deg rot, bottom-right is original
    assert len(res) == 4
    assert len(res[0]) == 4
    assert res[2][2:] == [1, 2]
    assert res[3][2:] == [3, 4]


def test_extract_quadrant_macrogrid():
    grid = [
        [0, 1, 2, 0, 3],
        [2, 2, 2, 2, 2],
        [0, 4, 2, 0, 5],
    ]
    macro = extract_quadrant_macrogrid(grid)
    assert len(macro) == 2
    assert len(macro[0]) == 2
    assert macro == [[1, 3], [4, 5]]


def test_fill_framed_enclosures():
    grid = [
        [2, 2, 2, 2, 2],
        [2, 0, 0, 0, 2],
        [2, 0, 0, 0, 2],
        [2, 0, 0, 0, 2],
        [2, 2, 2, 2, 2],
    ]
    res = fill_framed_enclosures(grid, frame_color=2, size_to_color={5: 8})
    assert res[1][1] == 8
    assert res[2][2] == 8


def test_kronecker_fractal_tiling():
    grid = [[1, 0], [0, 1]]
    res = kronecker_fractal_tiling(grid, block_mode="complement")
    assert len(res) == 4
    assert len(res[0]) == 4


def test_palette_swap_by_legend():
    grid = [
        [1, 2, 0],
        [3, 4, 0],
        [0, 1, 3],
    ]
    res = palette_swap_by_legend(grid, legend_h=2, legend_w=2)
    assert res[2] == [0, 2, 4]


def test_extrapolate_ray():
    grid = [
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    res = extrapolate_ray(grid, output_color=3)
    assert res[2][2] == 3
    assert res[3][3] == 3

