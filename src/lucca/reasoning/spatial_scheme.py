"""
Project Lucca — MicroScheme Discrete Spatial Environment (WO-29 / WO-33)
D-REAS-11, D-AUD-01

Binds discrete 2D spatial primitives to MicroScheme AST evaluation.
Provides pure, gas-metered execution for spatial transformations,
connected component filtering, symmetry completion, and topology.

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from collections.abc import Callable
import itertools
from typing import Final, cast

import structlog

from lucca.reasoning.scheme.eval import SchemeEvaluator
from lucca.reasoning.scheme.macros import MacroExpander, MacroRegistry
from lucca.reasoning.scheme.parser import (
    Keyword,
    SchemeAtom,
    SchemeNode,
    SchemeValue,
    Symbol,
    parse_expr,
)
from lucca.reasoning.scheme.prims import PURE_PRIMITIVES
from lucca.reasoning.spatial_dsl import (
    SpatialObject,
    bbox_of_all,
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
    is_enclosed,
    majority_filter,
    move_until_contact,
    order_columns_by_height,
    paste,
    restore_periodic_pattern,
    rot90,
    row_widths,
    sort_objects,
    unique_colors,
)

logger = structlog.get_logger(__name__)

GLOBAL_MACRO_REGISTRY: Final[MacroRegistry] = MacroRegistry()


def load_persisted_macros(registry: MacroRegistry) -> None:
    """Loads admitted mined macros from the canonical test report/persisted artifact."""
    import json
    from pathlib import Path
    from lucca.reasoning.scheme.macros import MacroDefinition

    path = Path("logs/test_reports/reasoning_core_m3_mined_macros.json")
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for m in data.get("admitted_macros", []):
                name = m.get("name")
                params = m.get("params", [])
                body_str = m.get("body")
                doc = f"Mined primitive (savings={m.get('compression_savings', 0.0):.2f}): {body_str}"
                if name and body_str and not registry.has(name):
                    m_def = MacroDefinition(
                        name=name,
                        params=params,
                        body=parse_expr(body_str),
                        doc=doc,
                    )
                    registry.register(m_def)
                    from lucca.reasoning.spatial_dsl import register_macro_primitive
                    register_macro_primitive(name=name, params=params, doc=doc)
        except Exception as e:
            logger.debug("persisted_macros_load_failed", error=str(e))


load_persisted_macros(GLOBAL_MACRO_REGISTRY)


def _to_kw_str(val: SchemeValue) -> str:
    """Converts a Scheme atom to a string identifier, stripping leading colons."""
    if isinstance(val, Keyword):
        return val.name.lstrip(":")
    if isinstance(val, Symbol):
        return val.name.lstrip(":")
    if isinstance(val, str):
        return val.lstrip(":")
    return str(val)


def _to_int(val: SchemeValue, default: int = 0) -> int:
    """Safely coerces a Scheme value to integer."""
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return default


def _coerce_grid(val: SchemeValue) -> list[list[int]]:
    """Validates and coerces a Scheme value to a discrete 2D grid matrix."""
    if isinstance(val, list) and val and isinstance(val[0], list):
        grid: list[list[int]] = []
        for row in val:
            if isinstance(row, list):
                row_ints: list[int] = [_to_int(cell, 0) for cell in row]
                grid.append(row_ints)
            else:
                grid.append([_to_int(row, 0)])
        return grid
    return []


def _to_scheme_grid(grid: list[list[int]]) -> list[SchemeValue]:
    """Converts a Python integer grid to a typed SchemeValue list structure."""
    result: list[SchemeValue] = []
    for row in grid:
        row_cells: list[SchemeValue] = [cell for cell in row]
        result.append(row_cells)
    return result


# =============================================================================
# Discrete Spatial MicroScheme Primitives
# =============================================================================


def prim_complete_symmetry(args: list[SchemeValue]) -> SchemeValue:
    """(complete-symmetry grid [:axis :h|:v|:auto] [:mode :consensus|:auto|:canvas])"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    axis: str = "both"
    mode: str = "canvas"

    i = 1
    while i < len(args):
        kw = _to_kw_str(args[i])
        if kw == "axis" and i + 1 < len(args):
            raw_axis = _to_kw_str(args[i + 1]).lower()
            if raw_axis in ("h", "horizontal"):
                axis = "horizontal"
            elif raw_axis in ("v", "vertical"):
                axis = "vertical"
            elif raw_axis in ("both",):
                axis = "both"
            else:
                axis = "both"
            i += 2
        elif kw == "mode" and i + 1 < len(args):
            raw_mode = _to_kw_str(args[i + 1]).lower()
            if raw_mode in ("auto", "bbox", "canvas"):
                mode = raw_mode
            else:
                mode = "canvas"
            i += 2
        else:
            i += 1

    return _to_scheme_grid(complete_symmetry(grid, axis=axis, mode=mode))


def prim_rot90(args: list[SchemeValue]) -> SchemeValue:
    """(rot90 grid [k=1])"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    k = _to_int(args[1], 1) if len(args) > 1 else 1
    return _to_scheme_grid(rot90(grid, k=k))


def prim_flip_h(args: list[SchemeValue]) -> SchemeValue:
    """(flip-h grid)"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    return _to_scheme_grid(flip_h(grid))


def prim_flip_v(args: list[SchemeValue]) -> SchemeValue:
    """(flip-v grid)"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    return _to_scheme_grid(flip_v(grid))


def prim_crop(args: list[SchemeValue]) -> SchemeValue:
    """(crop grid min-r min-c max-r max-c)"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    if len(args) >= 5:
        min_r = _to_int(args[1])
        min_c = _to_int(args[2])
        max_r = _to_int(args[3])
        max_c = _to_int(args[4])
        return _to_scheme_grid(crop(grid, min_r, min_c, max_r, max_c))
    return _to_scheme_grid(crop_to_content(grid))


def prim_crop_to_content(args: list[SchemeValue]) -> SchemeValue:
    """(crop-to-content grid [bg=0])"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    bg = _to_int(args[1], 0) if len(args) > 1 else 0
    return _to_scheme_grid(crop_to_content(grid, background=bg))


def prim_paste(args: list[SchemeValue]) -> SchemeValue:
    """(paste dest-grid src-grid r c [ignore-zero=#f])"""
    if len(args) < 4:
        return args[0] if args else []
    dest = _coerce_grid(args[0])
    src = _coerce_grid(args[1])
    r = _to_int(args[2], 0)
    c = _to_int(args[3], 0)
    ignore_zero = bool(len(args) > 4 and (args[4] is True or str(args[4]).lower() in ("#t", "true")))
    return _to_scheme_grid(paste(dest, src, r=r, c=c, ignore_zero=ignore_zero))


def prim_fill_holes(args: list[SchemeValue]) -> SchemeValue:
    """(fill-holes grid [:fill color])"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    fill_c: int | None = None

    i = 1
    while i < len(args):
        kw = _to_kw_str(args[i])
        if kw in ("fill", "color") and i + 1 < len(args):
            fill_c = _to_int(args[i + 1])
            i += 2
        elif isinstance(args[i], int):
            fill_c = _to_int(args[i])
            i += 1
        else:
            i += 1

    return _to_scheme_grid(fill_holes(grid, fill_color=fill_c))


def prim_flood_fill(args: list[SchemeValue]) -> SchemeValue:
    """(flood-fill grid r c fill-color)"""
    if len(args) < 4:
        return args[0] if args else []
    grid = _coerce_grid(args[0])
    r = _to_int(args[1], 0)
    c = _to_int(args[2], 0)
    fill_c = _to_int(args[3], 0)
    return _to_scheme_grid(flood_fill(grid, r, c, fill_color=fill_c))


def prim_order_columns_by_height(args: list[SchemeValue]) -> SchemeValue:
    """(order-columns-by-height grid [:reverse #t|#f] [:bg color])"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    reverse = False
    bg = 0

    i = 1
    while i < len(args):
        kw = _to_kw_str(args[i])
        if kw in ("reverse", "descending") and i + 1 < len(args):
            reverse = bool(args[i + 1] is True or str(args[i + 1]).lower() in ("#t", "true"))
            i += 2
        elif kw == "bg" and i + 1 < len(args):
            bg = _to_int(args[i + 1])
            i += 2
        else:
            i += 1

    return _to_scheme_grid(order_columns_by_height(grid, reverse=reverse, background=bg))


def prim_unique_colors(args: list[SchemeValue]) -> SchemeValue:
    """(unique-colors grid) -> list of colors"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    colors = unique_colors(grid)
    return [c for c in colors]


def prim_count_cells(args: list[SchemeValue]) -> SchemeValue:
    """(count-cells grid [color=None]) -> int"""
    if not args:
        return 0
    grid = _coerce_grid(args[0])
    color = _to_int(args[1]) if len(args) > 1 else None
    return count_cells(grid, color=color)


def prim_count_objects(args: list[SchemeValue]) -> SchemeValue:
    """(count-objects grid [:color color] [:conn 4|8]) -> int"""
    if not args:
        return 0
    grid = _coerce_grid(args[0])
    color: int | None = None
    conn: int = 8

    i = 1
    while i < len(args):
        kw = _to_kw_str(args[i])
        if kw == "color" and i + 1 < len(args):
            color = _to_int(args[i + 1])
            i += 2
        elif kw in ("conn", "connectivity") and i + 1 < len(args):
            conn = _to_int(args[i + 1], 8)
            i += 2
        else:
            i += 1

    return count_objects(grid, color=color, connectivity=conn)


def prim_majority_filter(args: list[SchemeValue]) -> SchemeValue:
    """(majority-filter grid [radius=1])"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    radius = _to_int(args[1], 1) if len(args) > 1 else 1
    return _to_scheme_grid(majority_filter(grid, radius=radius))


def prim_denoise(args: list[SchemeValue]) -> SchemeValue:
    """(denoise grid [min-size=2] [bg=0])"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    min_size = _to_int(args[1], 2) if len(args) > 1 else 2
    bg = _to_int(args[2], 0) if len(args) > 2 else 0
    return _to_scheme_grid(denoise(grid, min_size=min_size, background=bg))


def prim_restore_periodic_pattern(args: list[SchemeValue]) -> SchemeValue:
    """(restore-periodic-pattern grid [period-r=None] [period-c=None])"""
    if not args:
        return []
    grid = _coerce_grid(args[0])
    pr: int | None = None
    pc: int | None = None
    if len(args) > 1 and isinstance(args[1], (int, float)):
        pr = _to_int(args[1])
    if len(args) > 2 and isinstance(args[2], (int, float)):
        pc = _to_int(args[2])
    return _to_scheme_grid(restore_periodic_pattern(grid, period_r=pr, period_c=pc))


SPATIAL_SCHEME_PRIMITIVES: Final[
    dict[str, Callable[[list[SchemeValue]], SchemeValue]]
] = {
    "complete-symmetry": prim_complete_symmetry,
    "rot90": prim_rot90,
    "flip-h": prim_flip_h,
    "flip-v": prim_flip_v,
    "crop": prim_crop,
    "crop-to-content": prim_crop_to_content,
    "paste": prim_paste,
    "fill-holes": prim_fill_holes,
    "flood-fill": prim_flood_fill,
    "order-columns-by-height": prim_order_columns_by_height,
    "unique-colors": prim_unique_colors,
    "count-cells": prim_count_cells,
    "count-objects": prim_count_objects,
    "majority-filter": prim_majority_filter,
    "denoise": prim_denoise,
    "restore-periodic-pattern": prim_restore_periodic_pattern,
    "periodic-restore": prim_restore_periodic_pattern,
}


def _make_constant_getter(val: SchemeValue) -> Callable[[list[SchemeValue]], SchemeValue]:
    """Helper factory returning a strictly typed Scheme constant accessor."""
    def _getter(_args: list[SchemeValue]) -> SchemeValue:
        return val

    return _getter


def make_spatial_scheme_env(
    input_grid: list[list[int]] | None = None,
    extra_bindings: dict[str, SchemeValue] | None = None,
) -> dict[str, Callable[[list[SchemeValue]], SchemeValue]]:
    """
    Constructs a complete MicroScheme environment with pure primitives,
    discrete spatial operations, and bound input matrices.
    """
    env: dict[str, Callable[[list[SchemeValue]], SchemeValue]] = {}
    env.update(PURE_PRIMITIVES)
    env.update(SPATIAL_SCHEME_PRIMITIVES)

    if input_grid is not None:
        scheme_grid = _to_scheme_grid(input_grid)
        env["input"] = _make_constant_getter(scheme_grid)
        env["grid"] = _make_constant_getter(scheme_grid)

    if extra_bindings:
        for k, v in extra_bindings.items():
            env[k] = _make_constant_getter(v)

    return env


def evaluate_spatial_sketch(
    sketch: SchemeNode | str,
    input_grid: list[list[int]],
    gas_limit: int = 1000,
    timeout_ms: float = 50.0,
    hole_bindings: dict[str, SchemeValue] | None = None,
    macro_registry: MacroRegistry | None = None,
) -> list[list[int]]:
    """
    Evaluates a MicroScheme spatial sketch against an input grid,
    substituting hole bindings and expanding any registered macros before evaluation.
    """
    effective_macros = macro_registry or GLOBAL_MACRO_REGISTRY
    if isinstance(sketch, str):
        node = parse_expr(sketch, macro_registry=effective_macros)
    else:
        node = sketch

    if effective_macros._macros:
        expander = MacroExpander(effective_macros)
        node = expander.expand(node)

    env = make_spatial_scheme_env(input_grid=input_grid, extra_bindings=hole_bindings)
    evaluator = SchemeEvaluator(gas_limit=gas_limit, timeout_ms=timeout_ms)
    res = evaluator.eval(node, env)
    return _coerce_grid(res)


def extract_holes_from_ast(node: SchemeNode) -> list[tuple[str, str | None]]:
    """Traverses a MicroScheme AST and extracts unique (hole_name, hole_type) tuples."""
    holes: list[tuple[str, str | None]] = []
    from lucca.reasoning.topology import extract_hole_info, is_hole_node

    def _walk(n: SchemeNode) -> None:
        if is_hole_node(n):
            info = extract_hole_info(n)
            if info is not None:
                holes.append(info)
        elif isinstance(n, list):
            for child in n:
                _walk(child)

    _walk(node)
    seen: set[str] = set()
    unique_holes: list[tuple[str, str | None]] = []
    for name, h_type in holes:
        if name not in seen:
            seen.add(name)
            unique_holes.append((name, h_type))
    return unique_holes


def enumerate_sketch_bindings(
    sketch: SchemeNode | str,
    train_pairs: list[dict[str, list[list[int]]]],
    max_candidates: int = 200,
    macro_registry: MacroRegistry | None = None,
) -> tuple[dict[str, SchemeValue] | None, int]:
    """
    Given a MicroScheme sketch with typed parameter holes and training demonstrations,
    enumerates candidate parameter bindings using E-Graph equivalence pruning and
    evaluates them on host CPU. Expands macros before parameter enumeration.
    Returns (best_binding, total_candidates_evaluated).
    """
    from lucca.reasoning.topology import enumerate_hole_bindings

    effective_macros = macro_registry or GLOBAL_MACRO_REGISTRY
    if isinstance(sketch, str):
        node = parse_expr(sketch, macro_registry=effective_macros)
    else:
        node = sketch

    if effective_macros._macros:
        expander = MacroExpander(effective_macros)
        node = expander.expand(node)

    colors_set: set[int] = set()
    for pair in train_pairs:
        for row in pair["input"]:
            colors_set.update(row)
        for row in pair["output"]:
            colors_set.update(row)
    colors_list: list[SchemeValue] = [c for c in sorted(colors_set)]
    if not colors_list:
        colors_list = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    candidate_domains: dict[str, list[SchemeValue]] = {
        "color": colors_list,
    }

    demos: list[tuple[SchemeValue, SchemeValue]] = [
        (cast(SchemeValue, pair["input"]), cast(SchemeValue, pair["output"])) for pair in train_pairs
    ]

    def _eval(eval_node: SchemeNode, inp: SchemeValue, binding: dict[str, SchemeValue]) -> SchemeValue:
        grid = _coerce_grid(inp)
        return cast(SchemeValue, evaluate_spatial_sketch(eval_node, grid, hole_bindings=binding, macro_registry=effective_macros))

    res = enumerate_hole_bindings(
        sketch=node,
        eval_fn=_eval,
        demos=demos,
        candidate_domains=candidate_domains,
        max_candidates=max_candidates,
        use_egraph_pruning=True,
    )

    if res.best_binding is not None:
        from lucca.reasoning.spatial_dsl import check_metamorphic_invariance

        def _candidate_fn(g: list[list[int]], cur_b: dict[str, SchemeValue] = res.best_binding) -> list[list[int]]:
            return evaluate_spatial_sketch(node, g, hole_bindings=cur_b, macro_registry=effective_macros)

        is_inv, _ = check_metamorphic_invariance(_candidate_fn, train_pairs)
        return (res.best_binding, res.evaluated_count)

    return (None, res.evaluated_count)


def compile_dynamic_sketch_grammar(
    active_primitives: list[str] | None = None,
    active_colors: list[int] | None = None,
    macro_registry: MacroRegistry | None = None,
) -> str:
    """
    Dynamically compiles a GBNF sketch grammar incorporating active primitives,
    admitted mined macros, and state-dependent semantic color masking (Milestone 3.1 & 4.1).
    """
    base_prims = [
        "complete-symmetry",
        "fill-holes",
        "crop-to-content",
        "rot90",
        "flip-h",
        "flip-v",
        "order-columns-by-height",
        "restore-periodic-pattern",
        "periodic-restore",
    ]
    if active_primitives:
        for p in active_primitives:
            if p not in base_prims:
                base_prims.append(p)

    effective_macros = macro_registry or GLOBAL_MACRO_REGISTRY
    for m_name in effective_macros._macros:
        if m_name not in base_prims:
            base_prims.append(m_name)

    prim_op_alternatives = " | ".join(f'"{p}"' for p in base_prims)

    if active_colors:
        sorted_colors = sorted(set(active_colors))
        color_choices = " | ".join(f'"{c}"' for c in sorted_colors)
        color_rule = f'hole-color ::= "?hole-color" | ({color_choices})'
    else:
        color_rule = 'hole-color ::= "?hole-color" | [0-9]'

    return f"""root ::= ws sketch (newline ws sketch)* ws
expr-list ::= sketch (newline ws sketch)*
sketch ::= "(" ws prim-op (ws-plus arg)* ws ")"
prim-op ::= {prim_op_alternatives} | [a-zA-Z][a-zA-Z0-9_-]*
arg ::= kw-pair | atom | sketch
kw-pair ::= (":axis" ws-plus "?hole-axis") | (":mode" ws-plus "?hole-mode") | (":fill" ws-plus hole-color) | (":conn" ws-plus "?hole-conn") | (":reverse" ws-plus "?hole-bool") | (keyword ws-plus hole)
atom ::= hole | var | int | boolean
var ::= "input" | "grid" | "bg" | "obj"
hole ::= "?hole-axis" | "?hole-mode" | hole-color | "?hole-conn" | "?hole-int" | "?hole-key" | "?hole-bool"
{color_rule}
keyword ::= ":" [a-zA-Z][a-zA-Z0-9_-]*
int ::= "-"? [0-9]+
boolean ::= "#t" | "#f"
ws ::= [ \\t]*
newline ::= [\\n]+
ws-plus ::= [ \\t\\n\\r]+
"""


