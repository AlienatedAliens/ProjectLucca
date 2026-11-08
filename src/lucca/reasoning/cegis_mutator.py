"""
Project Lucca — Domain-Agnostic CEGIS AST Mutator (WO-43 Phase 3.4)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §4
"""

from __future__ import annotations

import ast
import copy

import structlog

logger = structlog.get_logger(__name__)


def generate_ast_mutants(source_code: str, max_mutants: int = 30) -> list[str]:
    """
    Domain-agnostic CEGIS syntax mutator for program repair.
    Generates single-point AST mutations:
    1. Condition polarity: `if cond:` <-> `if not (cond):`
    2. Mask / bitwise inversion: `arr[mask]` <-> `arr[~mask]` and `a & b` <-> `a & ~b`
    3. Binary call argument order: `f(a, b)` <-> `f(b, a)`
    """
    try:
        base_tree = ast.parse(source_code)
    except Exception as exc:
        logger.debug("generate_ast_mutants_parse_failed", error=str(exc))
        return []

    mutants: list[str] = []
    seen: set[str] = {source_code.strip()}

    def add_tree(t: ast.AST) -> None:
        if len(mutants) >= max_mutants:
            return
        try:
            ast.fix_missing_locations(t)
            mut_code = ast.unparse(t).strip()
            if mut_code and mut_code not in seen:
                seen.add(mut_code)
                mutants.append(mut_code)
        except Exception as exc:
            logger.debug("ast_mutant_unparse_failed", error=str(exc))

    # 1. Mutate conditionals: if cond -> if not cond
    for node in ast.walk(base_tree):
        if isinstance(node, ast.If):
            t_copy = copy.deepcopy(base_tree)
            for target in ast.walk(t_copy):
                if isinstance(target, ast.If) and getattr(target, "lineno", None) == getattr(node,
                    "lineno", None) and getattr(target, "col_offset", None) == getattr(node,
                        "col_offset", None):
                    if isinstance(target.test, ast.UnaryOp) and isinstance(target.test.op, ast.Not):
                        target.test = target.test.operand
                    else:
                        target.test = ast.UnaryOp(op=ast.Not(), operand=target.test)
                    add_tree(t_copy)
                    break

    # 2. Mutate mask/slice inversion: arr[mask] -> arr[~mask] and binary bitwise op inversion
    for node in ast.walk(base_tree):
        if isinstance(node, ast.Subscript):
            t_copy = copy.deepcopy(base_tree)
            for target in ast.walk(t_copy):
                if isinstance(target, ast.Subscript) and getattr(target, "lineno",
                    None) == getattr(node, "lineno", None) and getattr(target, "col_offset",
                        None) == getattr(node, "col_offset", None):
                    sl = target.slice
                    if isinstance(sl, ast.UnaryOp) and isinstance(sl.op, ast.Invert):
                        target.slice = sl.operand
                        add_tree(t_copy)
                    elif isinstance(sl, (ast.Name, ast.Attribute, ast.Call)):
                        target.slice = ast.UnaryOp(op=ast.Invert(), operand=copy.deepcopy(sl))
                        add_tree(t_copy)
                    break
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            for side in ("left", "right"):
                t_copy = copy.deepcopy(base_tree)
                for target in ast.walk(t_copy):
                    if isinstance(target, ast.BinOp) and getattr(target, "lineno",
                        None) == getattr(node, "lineno", None) and getattr(target, "col_offset",
                            None) == getattr(node, "col_offset", None):
                        target_child = getattr(target, side)
                        if isinstance(target_child, ast.UnaryOp) and isinstance(target_child.op,
                            ast.Invert):
                            setattr(target, side, target_child.operand)
                        else:
                            setattr(target, side, ast.UnaryOp(op=ast.Invert(),
                                operand=copy.deepcopy(target_child)))
                        add_tree(t_copy)
                        break

    # 3. Mutate binary call argument order: f(a, b) -> f(b, a)
    for node in ast.walk(base_tree):
        if isinstance(node, ast.Call) and len(node.args) == 2:
            t_copy = copy.deepcopy(base_tree)
            for target in ast.walk(t_copy):
                if isinstance(target, ast.Call) and getattr(target, "lineno", None) == getattr(node,
                    "lineno", None) and getattr(target, "col_offset", None) == getattr(node,
                        "col_offset", None) and len(target.args) == 2:
                    target.args = [target.args[1], target.args[0]]
                    add_tree(t_copy)
                    break

    # 4. Mutate spatial offsets (+1 <-> -1)
    for node in ast.walk(base_tree):
        if isinstance(node, ast.BinOp) and isinstance(node.right,
            ast.Constant) and node.right.value == 1:
            t_copy = copy.deepcopy(base_tree)
            for target in ast.walk(t_copy):
                if isinstance(target, ast.BinOp) and getattr(target, "lineno",
                    None) == getattr(node, "lineno", None) and getattr(target, "col_offset",
                        None) == getattr(node, "col_offset", None):
                    if isinstance(target.op, ast.Add):
                        target.op = ast.Sub()
                        add_tree(t_copy)
                    elif isinstance(target.op, ast.Sub):
                        target.op = ast.Add()
                        add_tree(t_copy)
                    break

    # 5. Mutate connectivity (4 <-> 8), component sort keys (area <-> bbox, reverse), and spatial
    # directional calls
    _DIRECTIONAL_SWAPS: dict[str, str] = {
        "above": "below",
        "below": "above",
        "left_of": "right_of",
        "right_of": "left_of",
        "flip_h": "flip_v",
        "flip_v": "flip_h",
    }
    for node in ast.walk(base_tree):
        if isinstance(node, ast.Call):
            # Directional function name swap (above <-> below, left_of <-> right_of, flip_h <->
            # flip_v)
            if isinstance(node.func, ast.Name) and node.func.id in _DIRECTIONAL_SWAPS:
                t_copy = copy.deepcopy(base_tree)
                for target in ast.walk(t_copy):
                    if (
                        isinstance(target, ast.Call)
                        and isinstance(target.func, ast.Name)
                        and getattr(target, "lineno", None) == getattr(node, "lineno", None)
                        and getattr(target, "col_offset", None) == getattr(node, "col_offset", None)
                    ):
                        target.func.id = _DIRECTIONAL_SWAPS[node.func.id]
                        add_tree(t_copy)
                        break

            # Positional connectivity in connected_components(arr, 4) <-> connected_components(arr,
            # 8)
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "connected_components"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in (4, 8)
            ):
                t_copy = copy.deepcopy(base_tree)
                for target in ast.walk(t_copy):
                    if (
                        isinstance(target, ast.Call)
                        and getattr(target, "lineno", None) == getattr(node, "lineno", None)
                        and getattr(target, "col_offset", None) == getattr(node, "col_offset", None)
                        and len(target.args) >= 2
                        and isinstance(target.args[1], ast.Constant)
                    ):
                        target.args[1].value = 8 if target.args[1].value == 4 else 4
                        add_tree(t_copy)
                        break

            for kw in node.keywords:
                if kw.arg == "connectivity" and isinstance(kw.value, ast.Constant):
                    t_copy = copy.deepcopy(base_tree)
                    for target in ast.walk(t_copy):
                        if isinstance(target, ast.Call) and getattr(target, "lineno",
                            None) == getattr(node, "lineno", None):
                            for tkw in target.keywords:
                                if tkw.arg == "connectivity" and isinstance(tkw.value,
                                    ast.Constant):
                                    tkw.value.value = 8 if tkw.value.value == 4 else 4
                                    add_tree(t_copy)
                                    break
                elif kw.arg == "reverse" and isinstance(kw.value,
                    ast.Constant) and isinstance(kw.value.value, bool):
                    t_copy = copy.deepcopy(base_tree)
                    for target in ast.walk(t_copy):
                        if isinstance(target, ast.Call) and getattr(target, "lineno",
                            None) == getattr(node, "lineno", None):
                            for tkw in target.keywords:
                                if tkw.arg == "reverse" and isinstance(tkw.value, ast.Constant):
                                    tkw.value.value = not bool(tkw.value.value)
                                    add_tree(t_copy)
                                    break
                elif kw.arg == "key" and isinstance(kw.value, (ast.Attribute, ast.Lambda)):
                    t_copy = copy.deepcopy(base_tree)
                    for target in ast.walk(t_copy):
                        if isinstance(target, ast.Call) and getattr(target, "lineno",
                            None) == getattr(node, "lineno", None):
                            for tkw in target.keywords:
                                if tkw.arg == "key":
                                    for sub in ast.walk(tkw.value):
                                        if isinstance(sub, ast.Attribute):
                                            if sub.attr == "area":
                                                sub.attr = "bbox"
                                                add_tree(t_copy)
                                            elif sub.attr == "bbox":
                                                sub.attr = "area"
                                                add_tree(t_copy)
                                            break

    return mutants
