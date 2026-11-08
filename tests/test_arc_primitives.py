"""
Project Lucca — Unit Tests for ARC Spatial Primitives Library
Tests all 10 canonical operations per Priority 2A.
"""


from lucca.reasoning.arc_primitives import (
    align_objects,
    bounding_box,
    crop,
    flip_h,
    flip_v,
    flood_fill,
    get_objects,
    gravity_drop,
    paste,
    replace_color,
    rotate_90,
)
from lucca.reasoning.spatial_dsl import (
    connected_components,
    crop_grid,
    find_separator_lines,
    overlay_grid,
    reflect_grid,
    rotate_grid,
    split_by_separators,
    translate_grid,
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


def test_connected_components_dsl():
    grid = [
        [1, 1, 0],
        [0, 0, 2],
    ]
    comps = connected_components(grid, background=0, connectivity=4)
    assert len(comps) == 2
    assert {c.color for c in comps} == {1, 2}


def test_rotate_and_reflect_grid():
    grid = [
        [1, 2],
        [3, 4],
    ]
    assert rotate_grid(grid, k=1) == [
        [3, 1],
        [4, 2],
    ]
    assert reflect_grid(grid, axis="horizontal") == [
        [2, 1],
        [4, 3],
    ]
    assert reflect_grid(grid, axis="vertical") == [
        [3, 4],
        [1, 2],
    ]


def test_translate_crop_and_overlay_grid():
    grid = [
        [1, 2, 0],
        [3, 4, 0],
        [0, 0, 0],
    ]
    translated = translate_grid(grid, dr=1, dc=1, fill_value=0)
    assert translated == [
        [0, 0, 0],
        [0, 1, 2],
        [0, 3, 4],
    ]
    cropped = crop_grid(translated, 1, 1, 2, 2)
    assert cropped == [
        [1, 2],
        [3, 4],
    ]
    overlaid = overlay_grid(grid, [[9, 0], [0, 9]], top_r=0, left_c=0, transparent_color=0)
    assert overlaid == [
        [9, 2, 0],
        [3, 9, 0],
        [0, 0, 0],
    ]

