"""
Tests for Project Lucca Spatial Anchors & Coordinate Utilities
==============================================================
Verifies foundational 2D image processing, component labeling, and geometry helpers.
"""

from __future__ import annotations

import numpy as np
import pytest

from lucca.reasoning.spatial_anchors import (
    Component,
    bbox,
    canvas,
    centroid,
    color_counts,
    connected_components,
    crop,
    find_cavities,
    flip_h,
    flip_v,
    flood_fill,
    is_identical_shape,
    paste,
    rot90,
)


def test_bbox_and_centroid() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:5, 3:7] = True  # rows 2,3,4 (h=3), cols 3,4,5,6 (w=4)

    b = bbox(mask)
    assert b == (2, 3, 4, 6, 3, 4)

    c = centroid(mask)
    assert c is not None
    assert c[0] == pytest.approx(3.0)
    assert c[1] == pytest.approx(4.5)

    empty_mask = np.zeros((5, 5), dtype=bool)
    assert bbox(empty_mask) is None
    assert centroid(empty_mask) is None


def test_crop_and_paste() -> None:
    grid = np.array([
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
    ])
    cropped = crop(grid, (1, 1, 2, 2, 2, 2))
    assert np.array_equal(cropped, np.array([[4, 5], [7, 8]]))

    base = canvas(4, 4, fill_val=0)
    patch = np.array([[9, 9], [9, 9]])
    pasted = paste(base, patch, top_r=1, left_c=2)
    expected = np.array([
        [0, 0, 0, 0],
        [0, 0, 9, 9],
        [0, 0, 9, 9],
        [0, 0, 0, 0],
    ])
    assert np.array_equal(pasted, expected)

    # Test paste with transparent value
    patch_trans = np.array([[1, 0], [0, 1]])
    pasted_trans = paste(base, patch_trans, top_r=0, left_c=0, transparent_val=0)
    expected_trans = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ])
    assert np.array_equal(pasted_trans, expected_trans)


def test_connected_components_4_vs_8() -> None:
    # Diagonal 2x2 blocks touching only diagonally
    grid = np.array([
        [1, 0],
        [0, 1],
    ])
    # 4-connectivity: should be 2 components
    comps_4 = connected_components(grid, connectivity=4, background=0)
    assert len(comps_4) == 2

    # 8-connectivity: should be 1 component
    comps_8 = connected_components(grid, connectivity=8, background=0)
    assert len(comps_8) == 1
    assert comps_8[0].area == 2
    assert comps_8[0].color == 1


def test_is_identical_shape() -> None:
    mask_a = np.zeros((8, 8), dtype=bool)
    mask_a[1:3, 1:4] = True  # 2x3 block at (1, 1)

    mask_b = np.zeros((10, 10), dtype=bool)
    mask_b[5:7, 6:9] = True  # 2x3 block at (5, 6)

    mask_c = np.zeros((8, 8), dtype=bool)
    mask_c[1:4, 1:3] = True  # 3x2 block (different aspect ratio)

    assert is_identical_shape(mask_a, mask_b) is True
    assert is_identical_shape(mask_a, mask_c) is False


def test_find_cavities() -> None:
    # 5x5 grid with a hollow square of 1s and an enclosed 0 inside at (2, 2)
    grid = np.array([
        [0, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 1, 0, 1, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 0, 0, 0],
    ])
    cavities = find_cavities(grid, background_val=0)
    expected_cavities = np.zeros((5, 5), dtype=bool)
    expected_cavities[2, 2] = True
    assert np.array_equal(cavities, expected_cavities)


def test_rotations_flips_and_flood_fill() -> None:
    arr = np.array([
        [1, 2],
        [3, 4],
    ])
    assert np.array_equal(rot90(arr, k=1), np.array([[2, 4], [1, 3]]))
    assert np.array_equal(flip_h(arr), np.array([[2, 1], [4, 3]]))
    assert np.array_equal(flip_v(arr), np.array([[3, 4], [1, 2]]))

    # Flood fill
    canvas_arr = np.array([
        [0, 0, 1],
        [0, 0, 1],
        [1, 1, 1],
    ])
    filled = flood_fill(canvas_arr, 0, 0, fill_val=7)
    expected_filled = np.array([
        [7, 7, 1],
        [7, 7, 1],
        [1, 1, 1],
    ])
    assert np.array_equal(filled, expected_filled)

    counts = color_counts(arr)
    assert counts == {1: 1, 2: 1, 3: 1, 4: 1}
