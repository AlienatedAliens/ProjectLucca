"""
Project Lucca — Unit Tests for Spatial DSL & Metamorphic Invariance Module
(Module 16, D-REAS-16, D-AUD-01)
"""

from __future__ import annotations

import numpy as np
import pytest

from lucca.reasoning.spatial_dsl import (
    PrimitiveDomain,
    SpatialObject,
    SymbolicInvariants,
    analyze_symbolic_invariants,
    bbox_of_all,
    build_scene_graph,
    check_metamorphic_invariance,
    column_heights,
    complete_symmetry,
    count_cells,
    count_objects,
    crop,
    crop_to_content,
    denoise,
    dominant_object,
    draw_line,
    fill_holes,
    find_objects,
    flip_h,
    flip_v,
    flood_fill,
    format_scene_graph_prompt,
    generate_relational_diff,
    is_enclosed,
    majority_filter,
    move_until_contact,
    normalize_grid,
    order_columns_by_height,
    paste,
    register_macro_primitive,
    resolve_scoped_primitives,
    rot90,
    row_widths,
    sort_objects,
    summarize_grid_objects,
    unique_colors,
)


def test_find_objects_and_counts() -> None:
    grid = [
        [0, 1, 1, 0],
        [0, 1, 1, 0],
        [0, 0, 0, 0],
        [2, 0, 0, 2],
    ]
    objs = find_objects(grid)
    assert len(objs) == 3
    assert count_objects(grid) == 3
    assert count_objects(grid, color=1) == 1
    assert count_objects(grid, color=2) == 2

    # Verify object properties
    obj1 = objs[0]
    assert obj1.color == 1
    assert obj1.area == 4
    assert obj1.height == 2
    assert obj1.width == 2
    assert obj1.dimensions == (2, 2)
    assert obj1.bbox == (0, 1, 1, 2)
    assert not obj1.is_hollow


def test_hollow_object_detection() -> None:
    grid = [
        [3, 3, 3],
        [3, 0, 3],
        [3, 3, 3],
    ]
    objs = find_objects(grid)
    assert len(objs) == 1
    assert objs[0].is_hollow is True

    # Test hole filling
    filled = fill_holes(grid)
    assert filled[1][1] == 3


def test_dominant_object() -> None:
    grid = [
        [1, 0, 0],
        [0, 2, 2],
        [0, 2, 2],
    ]
    dom = dominant_object(grid)
    assert dom is not None
    assert dom.color == 2
    assert dom.area == 4


def test_unique_colors() -> None:
    grid = [
        [0, 5, 2],
        [1, 0, 2],
    ]
    colors = unique_colors(grid)
    assert colors == [1, 2, 5]


def test_enclosure() -> None:
    inner = SpatialObject(
        obj_id=1, color=4, min_r=2, min_c=2, max_r=3, max_c=3,
        height=2, width=2, area=4, is_hollow=False, coords=[(2, 2)],
    )
    outer = SpatialObject(
        obj_id=2, color=1, min_r=0, min_c=0, max_r=5, max_c=5,
        height=6, width=6, area=20, is_hollow=True, coords=[(0, 0)],
    )
    assert is_enclosed(inner, outer) is True
    assert is_enclosed(outer, inner) is False


def test_transformations() -> None:
    grid = [
        [1, 2],
        [3, 4],
    ]
    assert rot90(grid, 1) == [[3, 1], [4, 2]]
    assert flip_h(grid) == [[2, 1], [4, 3]]
    assert flip_v(grid) == [[3, 4], [1, 2]]
    assert crop(grid, 0, 0, 0, 1) == [[1, 2]]

    dst = [[0, 0], [0, 0]]
    src = [[7]]
    assert paste(dst, src, 1, 1) == [[0, 0], [0, 7]]


def test_flood_fill() -> None:
    grid = [
        [1, 1, 0],
        [1, 0, 0],
        [0, 0, 0],
    ]
    filled = flood_fill(grid, 0, 0, 9)
    assert filled[0][0] == 9
    assert filled[0][1] == 9
    assert filled[1][0] == 9
    assert filled[0][2] == 0


def test_normalize_grid() -> None:
    arr = np.array([[1, 2], [3, 4]])
    norm = normalize_grid(arr)
    assert norm == [[1, 2], [3, 4]]


def test_summarize_grid_objects() -> None:
    grid = [
        [0, 3, 3],
        [0, 3, 3],
    ]
    summary = summarize_grid_objects(grid)
    assert "Obj 1: color 3" in summary
    assert "2x2" in summary


def test_metamorphic_invariance() -> None:
    # A symmetric rule: invert colors or flip
    def symmetric_transform(g: list[list[int]]) -> list[list[int]]:
        return rot90(rot90(g, 1), -1)  # identity

    train_pairs = [
        {"input": [[1, 0], [0, 1]], "output": [[1, 0], [0, 1]]},
    ]
    is_inv, detail = check_metamorphic_invariance(symmetric_transform, train_pairs)
    assert is_inv is True
    assert detail is None

    # An asymmetric rule: hardcodes right shift
    def broken_transform(g: list[list[int]]) -> list[list[int]]:
        res = [row[:] for row in g]
        res[0][1] = 9
        return res

    is_inv_bad, detail_bad = check_metamorphic_invariance(broken_transform, train_pairs)
    assert is_inv_bad is False
    assert detail_bad is not None

    # An asymmetric rule: breaks on 3rd transform (vertical flip)
    call_count = 0

    def broken_v_transform(g: list[list[int]]) -> list[list[int]]:
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            return [[9, 9], [9, 9]]
        return g

    is_inv_v, detail_v = check_metamorphic_invariance(broken_v_transform, train_pairs)
    assert is_inv_v is False
    assert detail_v is not None
    assert "vertical flip" in detail_v


def test_load_spatial_macros() -> None:
    from lucca.reasoning.scheme.macros import load_spatial_macros

    reg = load_spatial_macros()
    assert reg is not None


def test_python_ast_cost() -> None:
    from lucca.reasoning.cost import python_ast_cost

    clean_code = "def transform(g):\n    return g\n"
    overfit_code = "def transform(g):\n    return 4 if g[0][0] == 2 else 5\n"

    cost_clean = python_ast_cost(clean_code)
    cost_overfit = python_ast_cost(overfit_code)

    assert cost_clean < cost_overfit
    assert cost_overfit > 50.0  # Literal penalty applied


def test_bbox_of_all_and_crop_to_content() -> None:
    grid = [
        [0, 0, 0, 0],
        [0, 3, 3, 0],
        [0, 3, 0, 0],
        [0, 0, 0, 0],
    ]
    bbox = bbox_of_all(grid)
    assert bbox == (1, 1, 2, 2)
    cropped = crop_to_content(grid)
    assert cropped == [[3, 3], [3, 0]]

    empty_grid = [[0, 0], [0, 0]]
    assert bbox_of_all(empty_grid) is None
    assert crop_to_content(empty_grid) == [[]]


def test_sort_objects() -> None:
    grid = [
        [1, 0, 0, 0],
        [1, 0, 2, 0],
        [1, 0, 2, 0],
        [0, 0, 2, 0],
    ]
    objs = find_objects(grid)
    # obj for color 1 has height 3, width 1, area 3
    # obj for color 2 has height 3, width 1, area 3
    # Let's test with distinct heights
    grid2 = [
        [1, 0, 0],
        [1, 0, 2],
        [1, 0, 0],
    ]
    objs2 = find_objects(grid2)
    sorted_by_height = sort_objects(objs2, key="height")
    assert sorted_by_height[0].color == 2  # height 1
    assert sorted_by_height[1].color == 1  # height 3

    sorted_rev = sort_objects(objs2, key="height", reverse=True)
    assert sorted_rev[0].color == 1


def test_column_heights_and_row_widths() -> None:
    grid = [
        [0, 1, 0],
        [2, 1, 0],
        [2, 1, 3],
    ]
    assert column_heights(grid) == [2, 3, 1]
    assert row_widths(grid) == [1, 2, 3]


def test_denoise_and_majority_filter() -> None:
    # Grid with a dominant 3x3 block of color 7, plus isolated single-pixel noise of color 8
    grid = [
        [8, 0, 0, 0],
        [0, 7, 7, 7],
        [0, 7, 8, 7],
        [0, 7, 7, 7],
    ]
    # Denoise with min_size=2 should erase the isolated [0, 0] pixel
    denoised = denoise(grid, min_size=2)
    assert denoised[0][0] == 0
    # Inside the 3x3 block, the single pixel at [2, 2] is area 1
    assert denoised[2][2] == 0

    # Majority filter should replace the noisy 8 inside the 7s with 7
    filtered = majority_filter(grid, radius=1)
    assert filtered[2][2] == 7


def test_complete_symmetry() -> None:
    # Half-diamond / half-shape
    grid = [
        [1, 0, 0],
        [0, 1, 0],
        [1, 0, 0],
    ]
    sym = complete_symmetry(grid, axis="vertical")
    assert sym == [
        [1, 0, 1],
        [0, 1, 0],
        [1, 0, 1],
    ]

    # Bbox mode test with off-center shape
    off_center = [
        [0, 0, 0, 0],
        [0, 2, 0, 0],
        [0, 2, 2, 0],
        [0, 0, 0, 0],
    ]
    sym_bbox = complete_symmetry(off_center, axis="both", mode="bbox")
    assert sym_bbox == [
        [0, 0, 0, 0],
        [0, 2, 2, 0],
        [0, 2, 2, 0],
        [0, 0, 0, 0],
    ]


def test_order_columns_by_height() -> None:
    grid = [
        [0, 0, 0, 4],
        [4, 0, 0, 4],
        [4, 4, 0, 4],
    ]
    # col 0: 2, col 1: 1, col 2: 0, col 3: 3
    # Sorted ascending non-empty: col 1 (1), col 0 (2), col 3 (3), col 2 (0)
    ordered = order_columns_by_height(grid)
    assert ordered == [
        [0, 0, 4, 0],
        [0, 4, 4, 0],
        [4, 4, 4, 0],
    ]


def test_draw_line() -> None:
    grid = [[0] * 4 for _ in range(4)]
    line_grid = draw_line(grid, 0, 0, 3, 3, color=5)
    for i in range(4):
        assert line_grid[i][i] == 5


def test_move_until_contact() -> None:
    # Object of color 2 at row 0, obstacle of color 1 at row 3
    grid = [
        [0, 2, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 1, 0],
    ]
    objs = find_objects(grid)
    obj2 = [o for o in objs if o.color == 2][0]
    moved = move_until_contact(grid, obj2, dr=1, dc=0)
    # Should stop at row 2, right above obstacle at row 3
    assert moved[0][1] == 0
    assert moved[2][1] == 2
    assert moved[3][1] == 1


def test_count_cells() -> None:
    grid = [
        [0, 2, 2],
        [0, 0, 2],
        [3, 0, 0],
    ]
    assert count_cells(grid) == 4
    assert count_cells(grid, color=2) == 3
    assert count_cells(grid, color=3) == 1
    assert count_cells(grid, color=9) == 0


def test_connectivity_diamond_hollow() -> None:
    diamond = [
        [0, 1, 0],
        [1, 0, 1],
        [0, 1, 0],
    ]
    # Under 8-connectivity, diamond is 1 hollow component
    objs8 = find_objects(diamond, connectivity=8)
    assert len(objs8) == 1
    assert objs8[0].is_hollow is True
    assert objs8[0].area == 4

    # Under 4-connectivity, diamond is 4 separate non-hollow components
    objs4 = find_objects(diamond, connectivity=4)
    assert len(objs4) == 4
    assert not any(o.is_hollow for o in objs4)


def test_complete_symmetry_auto_mode() -> None:
    # Asymmetric canvas where one vertex is missing on right side
    grid = [
        [0, 0, 0, 0, 0, 2, 0, 0, 0, 0],
        [0, 0, 0, 0, 4, 0, 4, 0, 0, 0],
        [0, 0, 0, 4, 0, 0, 0, 4, 0, 0],
        [0, 0, 4, 0, 0, 0, 0, 0, 4, 0],
        [0, 2, 0, 0, 0, 0, 0, 0, 0, 0],  # missing (4, 8) with color 2
        [0, 0, 4, 0, 0, 0, 0, 0, 4, 0],
        [0, 0, 0, 4, 0, 0, 0, 4, 0, 0],
        [0, 0, 0, 0, 4, 0, 4, 0, 0, 0],
        [0, 0, 0, 0, 0, 2, 0, 0, 0, 0],
    ]
    completed = complete_symmetry(grid, axis="both", mode="auto")
    # Vertex on row 4 col 1 (color 2) must be reflected to row 4 col 9
    assert completed[4][9] == 2


def test_analyze_symbolic_invariants() -> None:
    # 1. Tally task
    tally_pairs = [
        {"input": [[0, 2, 0], [0, 0, 0]], "output": [[0]]},
        {"input": [[0, 2, 2], [0, 0, 0]], "output": [[0, 0]]},
    ]
    inv_tally = analyze_symbolic_invariants(tally_pairs)
    assert inv_tally.is_1d_tally_output is True
    assert inv_tally.tally_orientation in ("horizontal", "scalar")
    assert inv_tally.is_shape_preserving is False

    # 2. Hollow shape task
    hollow_pairs = [
        {"input": [[3, 3, 3], [3, 0, 3], [3, 3, 3]], "output": [[3, 3, 3], [3, 3, 3], [3, 3, 3]]},
    ]
    inv_hollow = analyze_symbolic_invariants(hollow_pairs)
    assert inv_hollow.has_hollow_objects is True
    assert inv_hollow.is_shape_preserving is True

    # 3. Permutation / ordering task (pixel count conserved)
    order_pairs = [
        {"input": [[1, 0], [1, 2]], "output": [[0, 1], [2, 1]]},
    ]
    inv_order = analyze_symbolic_invariants(order_pairs)
    assert inv_order.is_pixel_count_conserved is True


def test_resolve_scoped_primitives() -> None:
    inv = SymbolicInvariants(
        is_shape_preserving=False,
        is_1d_tally_output=True,
        tally_orientation="horizontal",
        is_pixel_count_conserved=False,
        is_pixels_only_added=True,
        has_hollow_objects=True,
        has_high_symmetry=False,
        color_set_preserved=True,
        input_shapes=[(3, 3)],
        output_shapes=[(1, 2)],
    )

    # When primary is TOPOLOGY, but output is 1D tally, TALLY must be automatically included
    doc, rules = resolve_scoped_primitives(inv, PrimitiveDomain.TOPOLOGY)
    assert "count_cells" in doc
    assert "tally vector" in " ".join(rules)

    # When primary is SYMMETRY
    inv_sym = SymbolicInvariants(
        is_shape_preserving=True,
        is_1d_tally_output=False,
        tally_orientation=None,
        is_pixel_count_conserved=False,
        is_pixels_only_added=True,
        has_hollow_objects=False,
        has_high_symmetry=True,
        color_set_preserved=True,
        input_shapes=[(5, 5)],
        output_shapes=[(5, 5)],
    )
    doc_sym, rules_sym = resolve_scoped_primitives(inv_sym, PrimitiveDomain.SYMMETRY, PrimitiveDomain.MORPHOLOGY)
    assert "complete_symmetry" in doc_sym
    assert "mode='auto'" in " ".join(rules_sym)
    # MORPHOLOGY must be pruned because is_pixels_only_added is True
    assert "denoise" not in doc_sym


def test_scene_graph_extraction_and_prompt() -> None:
    # 5x6 grid with:
    # - hollow frame of color 2 at (0, 0)-(4, 4)
    # - single cell of color 3 enclosed at (2, 2)
    # - single cell of color 4 adjacent to outer frame at (2, 5)
    grid = [
        [2, 2, 2, 2, 2, 0],
        [2, 0, 0, 0, 2, 0],
        [2, 0, 3, 0, 2, 4],
        [2, 0, 0, 0, 2, 0],
        [2, 2, 2, 2, 2, 0],
    ]
    sg = build_scene_graph(grid)
    objs = sg["objects"]
    assert len(objs) == 3
    rels = sg["relations"]
    assert any("contains" in r for r in rels)
    assert any("adjacent" in r for r in rels)
    prompt = format_scene_graph_prompt(sg)
    assert "Scene: 5x6" in prompt
    assert "hollow" in prompt
    assert "contains" in prompt


def test_relational_diff_engine() -> None:
    g1 = [
        [1, 1],
        [1, 1],
    ]
    g2_shape = [
        [1, 1, 1],
    ]
    # Shape mismatch
    diff_shape = generate_relational_diff(g1, g2_shape)
    assert "Shape mismatch" in diff_shape

    # Position shift: object moved from (0, 0) to (1, 1)
    exp = [
        [1, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
    ]
    pred_shifted = [
        [0, 0, 0],
        [0, 1, 0],
        [0, 0, 0],
    ]
    diff_shift = generate_relational_diff(pred_shifted, exp)
    assert "position mismatch" in diff_shift
    assert "Delta: dr=+1.0, dc=+1.0" in diff_shift

    # Topology mismatch: expected hollow frame, got solid block
    exp_hollow = [
        [2, 2, 2],
        [2, 0, 2],
        [2, 2, 2],
    ]
    pred_solid = [
        [2, 2, 2],
        [2, 2, 2],
        [2, 2, 2],
    ]
    diff_topo = generate_relational_diff(pred_solid, exp_hollow)
    assert "topology mismatch" in diff_topo


def test_dynamic_sketch_grammar_and_semantic_masking() -> None:
    from lucca.reasoning.spatial_scheme import compile_dynamic_sketch_grammar

    grammar = compile_dynamic_sketch_grammar(
        active_primitives=["my-custom-macro"],
        active_colors=[2, 5],
    )
    assert '"my-custom-macro"' in grammar
    assert '"2" | "5"' in grammar


def test_macro_primitive_registration_and_execution() -> None:
    from lucca.reasoning.scheme.macros import MacroDefinition
    from lucca.reasoning.scheme.parser import parse_expr
    from lucca.reasoning.spatial_scheme import GLOBAL_MACRO_REGISTRY, evaluate_spatial_sketch

    m_def = MacroDefinition(
        name="my-flip-fill",
        params=["input", "fill-col"],
        body=parse_expr("(fill-holes (flip-h input) :fill fill-col)"),
        doc="Flips grid horizontally and fills holes",
    )
    GLOBAL_MACRO_REGISTRY.register(m_def)
    register_macro_primitive(
        name="my-flip-fill",
        params=["input", "fill-col"],
        doc="Flips grid horizontally and fills holes",
    )

    test_grid = [
        [0, 1, 1, 1],
        [0, 1, 0, 1],
        [0, 1, 1, 1],
    ]
    res = evaluate_spatial_sketch("(my-flip-fill input 2)", test_grid)
    expected = [
        [1, 1, 1, 0],
        [1, 2, 1, 0],
        [1, 1, 1, 0],
    ]
    assert res == expected



