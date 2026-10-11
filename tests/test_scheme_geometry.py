"""
Unit tests for WO-29 Module 1: Functional Scheme Spatial DSL.
Tests geometric primitives, spatial transformations, bounding boxes,
containment checks, areas, perimeters, and Scheme macro integration.
"""

from __future__ import annotations

import math
import pytest

from lucca.reasoning.scheme.eval import evaluate_expr
from lucca.reasoning.scheme.macros import MacroExpander, load_spatial_macros
from lucca.reasoning.scheme.parser import parse_expr


def test_spatial_constructors():
    # Point
    pt2 = evaluate_expr(parse_expr("(point 10 20)"))
    assert pt2 == ["point", 10, 20]

    pt3 = evaluate_expr(parse_expr("(point 1 2 3)"))
    assert pt3 == ["point", 1, 2, 3]

    # Vector
    vec = evaluate_expr(parse_expr("(vec 3 4)"))
    assert vec == ["vec", 3, 4]

    # Rect
    rect = evaluate_expr(parse_expr("(rect 0 0 100 50)"))
    assert rect == ["rect", 0, 0, 100, 50]

    # Circle
    circle = evaluate_expr(parse_expr("(circle 5 5 10)"))
    assert circle == ["circle", 5, 5, 10]


def test_spatial_distance():
    # Distance between points
    dist = evaluate_expr(parse_expr("(distance (point 0 0) (point 3 4))"))
    assert pytest.approx(dist) == 5.0

    # Distance with direct coordinates
    dist2 = evaluate_expr(parse_expr("(distance 1 1 4 5)"))
    assert pytest.approx(dist2) == 5.0


def test_spatial_transformations():
    # Translate point
    t_pt = evaluate_expr(parse_expr("(translate (point 10 20) 5 -5)"))
    assert t_pt == ["point", 15.0, 15.0]

    # Translate rect
    t_rect = evaluate_expr(parse_expr("(translate (rect 10 10 40 20) 5 5)"))
    assert t_rect == ["rect", 15.0, 15.0, 40, 20]

    # Scale rect
    s_rect = evaluate_expr(parse_expr("(scale (rect 0 0 10 10) 2)"))
    assert s_rect == ["rect", 0.0, 0.0, 20.0, 20.0]

    # Rotate point 90 degrees (pi / 2)
    r_pt = evaluate_expr(parse_expr(f"(rotate (point 1 0) {math.pi / 2})"))
    assert pytest.approx(r_pt[1], abs=1e-5) == 0.0
    assert pytest.approx(r_pt[2], abs=1e-5) == 1.0


def test_spatial_bounding_box_and_containment():
    # Bounding box of circle
    bbox = evaluate_expr(parse_expr("(bounding-box (circle 10 10 5))"))
    assert bbox == ["rect", 5.0, 5.0, 10.0, 10.0]

    # Contains in rect
    assert evaluate_expr(parse_expr("(contains? (rect 0 0 10 10) (point 5 5))")) is True
    assert evaluate_expr(parse_expr("(contains? (rect 0 0 10 10) (point 15 5))")) is False

    # Contains in circle
    assert evaluate_expr(parse_expr("(contains? (circle 0 0 5) (point 3 4))")) is True
    assert evaluate_expr(parse_expr("(contains? (circle 0 0 5) (point 4 4))")) is False


def test_spatial_area_and_perimeter():
    # Rect area and perimeter
    area_rect = evaluate_expr(parse_expr("(area (rect 0 0 10 20))"))
    assert pytest.approx(area_rect) == 200.0

    perim_rect = evaluate_expr(parse_expr("(perimeter (rect 0 0 10 20))"))
    assert pytest.approx(perim_rect) == 60.0

    # Circle area and perimeter
    area_circ = evaluate_expr(parse_expr("(area (circle 0 0 10))"))
    assert pytest.approx(area_circ) == math.pi * 100.0

    perim_circ = evaluate_expr(parse_expr("(perimeter (circle 0 0 10))"))
    assert pytest.approx(perim_circ) == 2.0 * math.pi * 10.0


def test_spatial_intersection():
    # Overlapping rects
    assert evaluate_expr(parse_expr("(intersects? (rect 0 0 10 10) (rect 5 5 10 10))")) is True
    # Disjoint rects
    assert evaluate_expr(parse_expr("(intersects? (rect 0 0 10 10) (rect 20 20 10 10))")) is False


def test_spatial_macros_loaded():
    reg = load_spatial_macros()
    assert reg.has("square")
    assert reg.has("unit-circle")
    assert reg.has("unit-square")
    assert reg.has("origin-2d")

    # Expand (square 0 0 10) -> (rect 0 0 10 10)
    expander = MacroExpander(reg)
    ast = parse_expr("(square 0 0 10)", macro_registry=reg)
    expanded = expander.expand(ast)
    result = evaluate_expr(expanded)
    assert result == ["rect", 0, 0, 10, 10]


def test_discrete_spatial_scheme_eval():
    from lucca.reasoning.spatial_scheme import evaluate_spatial_sketch

    # Symmetry completion
    grid = [[1, 0], [0, 0]]
    res_h = evaluate_spatial_sketch("(complete-symmetry input :axis :h)", grid)
    assert res_h == [[1, 0], [1, 0]]

    # Content crop
    grid_crop = [[0, 0, 0], [0, 2, 0], [0, 0, 0]]
    res_crop = evaluate_spatial_sketch("(crop-to-content input)", grid_crop)
    assert res_crop == [[2]]

    # Fill holes
    grid_holes = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
    res_fill = evaluate_spatial_sketch("(fill-holes input :fill 3)", grid_holes)
    assert res_fill == [[1, 1, 1], [1, 3, 1], [1, 1, 1]]

    # Rot90
    res_rot = evaluate_spatial_sketch("(rot90 input 1)", [[1, 2], [3, 4]])
    assert res_rot == [[3, 1], [4, 2]]


def test_scheme_sketch_hole_extraction():
    from lucca.reasoning.scheme.parser import parse_expr
    from lucca.reasoning.topology import extract_hole_info, is_hole_node
    from lucca.reasoning.spatial_scheme import evaluate_spatial_sketch

    ast = parse_expr("(complete-symmetry input :axis ?hole-axis)")
    assert isinstance(ast, list)
    hole_nodes = [node for node in ast if is_hole_node(node)]
    assert len(hole_nodes) == 1
    info = extract_hole_info(hole_nodes[0])
    assert info == ("?hole-axis", "axis")

    # Evaluate with hole binding
    grid = [[1, 0], [0, 0]]
    res = evaluate_spatial_sketch(
        "(complete-symmetry input :axis ?hole-axis)",
        grid,
        hole_bindings={"?hole-axis": "h"},
    )
    assert res == [[1, 0], [1, 0]]


def test_gbnf_scheme_sketch_grammar_file():
    from pathlib import Path

    grammar_path = Path("config/grammars/scheme_sketch.gbnf")
    assert grammar_path.exists()
    content = grammar_path.read_text(encoding="utf-8")
    assert "root ::= ws sketch" in content
    assert "?hole-conn" in content
    assert "?hole-axis" in content
    assert "?hole-color" in content
    assert "kw-pair ::=" in content


def test_egraph_discrete_spatial_pruning():
    from lucca.reasoning.egraph import prune_equivalent_sketches
    from lucca.reasoning.scheme.parser import parse_expr, to_canonical

    cands = [
        parse_expr("(flip-h (flip-h input))"),
        parse_expr("input"),
        parse_expr("(rot90 input 0)"),
        parse_expr("(crop-to-content (crop-to-content input))"),
        parse_expr("(crop-to-content input)"),
    ]
    pruned = prune_equivalent_sketches(cands)
    pruned_canon = {to_canonical(p) for p in pruned}
    assert len(pruned) == 2
    assert "input" in pruned_canon
    assert "(crop-to-content input)" in pruned_canon


def test_topology_enumerate_hole_bindings():
    from lucca.reasoning.topology import enumerate_hole_bindings
    from lucca.reasoning.scheme.eval import SchemeEvaluator
    from lucca.reasoning.scheme.prims import PURE_PRIMITIVES

    evaluator = SchemeEvaluator(gas_limit=500, timeout_ms=50.0)

    def _eval(node, inp, binding):
        env = dict(PURE_PRIMITIVES)
        env["input"] = lambda _: inp
        return evaluator.eval(node, env)

    demos = [(10, 12), (5, 7), (0, 2)]
    res = enumerate_hole_bindings(
        sketch="(+ input ?hole-int)",
        eval_fn=_eval,
        demos=demos,
        max_candidates=50,
        use_egraph_pruning=True,
    )
    assert res.best_binding is not None
    assert res.best_binding.get("?hole-int") == 2
    assert res.coverage_rate == 1.0
    assert res.latency_ms < 50.0


def test_spatial_scheme_binding_with_egraph():
    from lucca.reasoning.spatial_scheme import enumerate_sketch_bindings

    train_pairs = [
        {"input": [[1, 0], [0, 0]], "output": [[1, 0], [1, 0]]},
        {"input": [[2, 2], [0, 0]], "output": [[2, 2], [2, 2]]},
    ]
    binding, count = enumerate_sketch_bindings(
        "(complete-symmetry input :axis ?hole-axis :mode ?hole-mode)",
        train_pairs,
    )
    assert binding is not None
    assert binding.get("?hole-axis") in ("h", "horizontal")
    assert count <= 200


def test_restore_periodic_pattern():
    from lucca.reasoning.spatial_dsl import restore_periodic_pattern
    from lucca.reasoning.spatial_scheme import evaluate_spatial_sketch

    # 4x4 alternating column stripes with 1 corrupted noise cell at (2, 1)
    corrupted = [
        [1, 2, 1, 2],
        [1, 2, 1, 2],
        [1, 0, 1, 2],
        [1, 2, 1, 2],
    ]
    restored = restore_periodic_pattern(corrupted)
    expected = [
        [1, 2, 1, 2],
        [1, 2, 1, 2],
        [1, 2, 1, 2],
        [1, 2, 1, 2],
    ]
    assert restored == expected

    # Test pure MicroScheme evaluation
    res_scheme = evaluate_spatial_sketch("(restore-periodic-pattern input)", corrupted)
    assert res_scheme == expected

    res_alias = evaluate_spatial_sketch("(periodic-restore input)", corrupted)
    assert res_alias == expected


def test_mine_new_primitives_anti_unification_and_smt():
    from lucca.reasoning.compression import (
        DreamCoderMacroMiner,
        mine_new_primitives,
        register_mined_primitive,
    )
    from lucca.reasoning.scheme.macros import MacroRegistry
    from lucca.reasoning.smt_verifier import SMTVerifier

    # 3 independent solved traces sharing a recurring spatial synthesis pipeline
    t1 = '(fill-holes (complete-symmetry input :axis "h" :mode "canvas") :fill 1)'
    t2 = '(fill-holes (complete-symmetry input :axis "v" :mode "canvas") :fill 2)'
    t3 = '(fill-holes (complete-symmetry input :axis "both" :mode "canvas") :fill 3)'

    miner = DreamCoderMacroMiner(smt_verifier=SMTVerifier(allow_pure_reasoning=True))
    candidates = mine_new_primitives(
        solved_traces=[t1, t2, t3],
        miner=miner,
        min_traces=2,
        min_cost_savings=2.0,
    )

    assert len(candidates) >= 1
    cand = candidates[0]
    assert cand.smt_verified is True
    assert cand.falsification_passed is True
    assert cand.compression_savings >= 2.0
    assert len(cand.params) >= 1

    registry = MacroRegistry()
    assert register_mined_primitive(cand, macro_registry=registry) is True
    assert registry.has(cand.name)


def test_mine_new_primitives_anti_test_tuning_gate():
    from lucca.reasoning.compression import mine_new_primitives

    # Single trace: must fail admission due to anti-test-tuning gate (requires >= 2 traces)
    t_single = '(fill-holes (complete-symmetry input :axis "h" :mode "canvas") :fill 1)'
    candidates = mine_new_primitives(
        solved_traces=[t_single],
        min_traces=2,
    )
    assert len(candidates) == 0


