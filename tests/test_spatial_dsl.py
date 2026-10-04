"""
Unit tests for WO-29 Module 1: Functional Scheme Spatial DSL.
Tests geometric primitives, spatial transformations, bounding boxes,
containment checks, areas, perimeters, and Scheme macro integration.
"""

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
