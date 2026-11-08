"""
Project Lucca — Restricted CEGIS Sandbox Execution & Compatibility Engine (WO-43 Phase 3.4)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §4
"""

from __future__ import annotations

import ast
import collections
import copy
import functools
import io
import itertools
import json
import math
import re
import threading
import time
import tokenize
import traceback
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, cast

import httpx
import numpy as np
import scipy.ndimage
import structlog

from lucca.reasoning import (
    arc_primitives,
    relational,
    spatial_anchors,
    spatial_dsl,
    spatial_scheme,
)
from lucca.reasoning.relational import mereo, realize_real
from lucca.sandbox.ast_sanitizer import sanitize_and_repair_python_code, sanitize_python_code
from lucca.sandbox.preflight import extract_python_code
from lucca.sandbox.rpc import DockerRPCTransport

if TYPE_CHECKING:
    from lucca.core.cognitive_sink import CognitiveOutcomeSink

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ExecutionOutcome:
    """Outcome of running synthesized Python code against an input grid."""

    success: bool
    output_grid: list[list[int]] | None
    error_type: str | None
    error_message: str | None
    traceback_str: str | None
    elapsed_ms: float


def normalize_to_int_grid(raw_val: object) -> list[list[int]]:
    """Converts numpy array or nested lists into canonical list[list[int]]."""
    if isinstance(raw_val, np.ndarray):
        raw_val = raw_val.tolist()

    if not isinstance(raw_val, list):
        raise TypeError(f"Expected 2D list, got {type(raw_val).__name__}")

    if not raw_val:
        return []

    if not isinstance(raw_val[0], list):
        # 1D list, coerce to 1xW
        return [[int(c) for c in raw_val]]

    return [[int(c) for c in row] for row in raw_val]


def strip_comments_and_docstrings(source: str) -> str:
    """Strips comments and docstrings from Python source, preventing monologue runaway."""
    if not source or not source.strip():
        return ""
    # Strip any from __main__ import statements
    source = re.sub(r"^\s*from\s+__main__\s+import\s+.*$", "", source, flags=re.MULTILINE)
    try:
        out: list[tuple[int, str]] = []
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        prev_toktype = tokenize.INDENT
        for tok in tokens:
            token_type = tok[0]
            token_string = tok[1]
            if token_type == tokenize.COMMENT:
                continue
            if token_type == tokenize.STRING and prev_toktype in (tokenize.INDENT, tokenize.NEWLINE,
                tokenize.NL):
                continue
            out.append((token_type, token_string))
            if token_type not in (tokenize.NL, tokenize.COMMENT):
                prev_toktype = token_type
        return tokenize.untokenize(out).strip()
    except Exception as exc:
        logger.debug("tokenize_strip_comments_fallback", error=str(exc))
        # Fallback line regex if tokenize encounters truncated string
        lines: list[str] = []
        for line in source.splitlines():
            line_no_comment = re.sub(r"#.*$", "", line).rstrip()
            if line_no_comment:
                lines.append(line_no_comment)
        return "\n".join(lines).strip()


_DOCKER_TRANSPORT_HOLDER: dict[str, object | None] = {"instance": None}
_DOCKER_TRANSPORT_LOCK = threading.Lock()

_ALLOWED_CEGIS_IMPORT_MODULES: Final[frozenset[str]] = frozenset(
    {
        "numpy",
        "scipy",
        "scipy.ndimage",
        "itertools",
        "collections",
        "math",
        "copy",
        "functools",
        "fractions",
        "typing",
        "lucca.reasoning",
        "lucca.reasoning.arc_primitives",
        "lucca.reasoning.spatial_anchors",
        "lucca.reasoning.spatial_dsl",
        "lucca.reasoning.spatial_scheme",
        "lucca.reasoning.relational",
        "lucca.reasoning.relational.mereo",
        "lucca.reasoning.relational.realize_real",
    }
)


_FORBIDDEN_CEGIS_CALLS: Final[frozenset[str]] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
        "exit",
        "quit",
    }
)

_FORBIDDEN_CEGIS_ATTRS: Final[frozenset[str]] = frozenset(
    {
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__globals__",
        "__builtins__",
        "__code__",
        "__closure__",
        "__dict__",
        "__class__",
        "system",
        "popen",
        "spawn",
    }
)


def validate_cegis_ast_safety(code: str) -> tuple[bool, str | None]:
    """
    Validates candidate Python code via AST inspection before execution (Milestone 1.3).
    Rejects dangerous imports, dynamic code execution builtins, and dunder introspection.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in _ALLOWED_CEGIS_IMPORT_MODULES:
                    return False, f"SecurityError: Import of module '{
                        alias.name}' is forbidden in CEGIS sandbox"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod not in _ALLOWED_CEGIS_IMPORT_MODULES:
                return False, f"SecurityError: Import from module '{
                    mod}' is forbidden in CEGIS sandbox"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CEGIS_CALLS:
                return False, f"SecurityError: Call to builtin '{
                    node.func.id}' is forbidden in CEGIS sandbox"
        elif isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_CEGIS_ATTRS or (
                node.attr.startswith("__") and node.attr.endswith("__")):
                return False, f"SecurityError: Access to attribute '{
                    node.attr}' is forbidden in CEGIS sandbox"
        elif isinstance(node, ast.Name):
            if node.id in {"__builtins__", "__loader__", "__spec__"}:
                return False, f"SecurityError: Reference to '{
                    node.id}' is forbidden in CEGIS sandbox"

    return True, None


def _build_restricted_cegis_globals(
    exposed_libraries: Sequence[str] | None = None,
) -> dict[str, object]:
    """Builds an isolated execution namespace with safe builtins and spatial primitives."""
    _ = exposed_libraries


    def _safe_import(
        name: str,
        globals_dict: dict[str, object] | None = None,
        locals_dict: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name not in _ALLOWED_CEGIS_IMPORT_MODULES:
            raise ImportError(f"Import of '{name}' is forbidden in restricted CEGIS sandbox")
        return __import__(name, globals_dict, locals_dict, fromlist, level)

    safe_builtins: dict[str, object] = {
        "__import__": _safe_import,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "divmod": divmod,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "frozenset": frozenset,
        "int": int,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "iter": iter,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "pow": pow,
        "range": range,
        "reversed": reversed,
        "round": round,
        "set": set,
        "slice": slice,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
        "True": True,
        "False": False,
        "None": None,
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
        "IndexError": IndexError,
        "ZeroDivisionError": ZeroDivisionError,
        "RuntimeError": RuntimeError,
    }
    return {
        "__builtins__": safe_builtins,
        "np": np,
        "numpy": np,
        "scipy": scipy,
        "ndimage": scipy.ndimage,
        "itertools": itertools,
        "collections": collections,
        "math": math,
        "copy": copy,
        "functools": functools,
        "spatial_anchors": spatial_anchors,
        "relational": relational,
        "bbox": spatial_anchors.bbox,
        "crop": spatial_anchors.crop,
        "centroid": spatial_anchors.centroid,
        "connected_components": spatial_anchors.connected_components,
        "is_identical_shape": spatial_anchors.is_identical_shape,
        "rot90": spatial_anchors.rot90,
        "flip_h": spatial_anchors.flip_h,
        "flip_v": spatial_anchors.flip_v,
        "flood_fill": spatial_anchors.flood_fill,
        "find_cavities": spatial_anchors.find_cavities,
        "color_counts": spatial_anchors.color_counts,
        "canvas": spatial_anchors.canvas,
        "paste": spatial_anchors.paste,
        "Component": spatial_anchors.Component,
        "in_cavity": relational.in_cavity,
        "part_of": relational.part_of,
        "externally_connected": relational.externally_connected,
        "partially_overlaps": relational.partially_overlaps,
        "above": relational.above,
        "below": relational.below,
        "left_of": relational.left_of,
        "right_of": relational.right_of,
        "extract_cavities": relational.extract_cavities,
        "extract_cavity_mask": relational.extract_cavity_mask,
        "extract_exterior_mask": relational.extract_exterior_mask,
        "is_between": relational.is_between,
        "y_projection": relational.y_projection,
        "x_projection": relational.x_projection,
        "GridRegion": relational.GridRegion,
        # WO-43 Phase 3.5: ARC primitives, Spatial DSL, Spatial Scheme, Mereo, and RealizeReal
        "arc_primitives": arc_primitives,
        "spatial_dsl": spatial_dsl,
        "spatial_scheme": spatial_scheme,
        "mereo": mereo,
        "realize_real": realize_real,
        "clone_grid": arc_primitives.clone_grid,
        "replace_color": arc_primitives.replace_color,
        "rotate_90": arc_primitives.rotate_90,
        "bounding_box": arc_primitives.bounding_box,
        "get_connected_components": arc_primitives.get_connected_components,
        "get_objects": arc_primitives.get_objects,
        "gravity_drop": arc_primitives.gravity_drop,
        "align_objects": arc_primitives.align_objects,
        "SpatialObject": spatial_dsl.SpatialObject,
        "normalize_grid": spatial_dsl.normalize_grid,
        "find_objects": spatial_dsl.find_objects,
        "count_objects": spatial_dsl.count_objects,
        "count_cells": spatial_dsl.count_cells,
        "dominant_object": spatial_dsl.dominant_object,
        "unique_colors": spatial_dsl.unique_colors,
        "fill_holes": spatial_dsl.fill_holes,
        "is_enclosed": spatial_dsl.is_enclosed,
        "bbox_of_all": spatial_dsl.bbox_of_all,
        "crop_to_content": spatial_dsl.crop_to_content,
        "sort_objects": spatial_dsl.sort_objects,
        "column_heights": spatial_dsl.column_heights,
        "order_columns_by_height": spatial_dsl.order_columns_by_height,
        "row_widths": spatial_dsl.row_widths,
        "denoise": spatial_dsl.denoise,
        "majority_filter": spatial_dsl.majority_filter,
        "restore_periodic_pattern": spatial_dsl.restore_periodic_pattern,
        "complete_symmetry": spatial_dsl.complete_symmetry,
        "draw_line": spatial_dsl.draw_line,
        "move_until_contact": spatial_dsl.move_until_contact,
        "rotate_grid": spatial_dsl.rotate_grid,
        "reflect_grid": spatial_dsl.reflect_grid,
        "translate_grid": spatial_dsl.translate_grid,
        "crop_grid": spatial_dsl.crop_grid,
        "overlay_grid": spatial_dsl.overlay_grid,
        "analyze_symbolic_invariants": spatial_dsl.analyze_symbolic_invariants,
        "evaluate_spatial_sketch": spatial_scheme.evaluate_spatial_sketch,
        "during_real": realize_real.during_real,
        "point_in_interval": realize_real.point_in_interval,
    }



def _execute_in_restricted_sandbox(
    clean_code: str,
    grid_in: list[list[int]],
    timeout_s: float,
) -> ExecutionOutcome:
    """Executes AST-validated candidate code in a restricted-builtins, timeout-bounded sandbox."""

    t0 = time.perf_counter()
    box: dict[str, object] = {}

    def _target() -> None:
        try:
            env = _build_restricted_cegis_globals()
            compiled = compile(clean_code, "<cegis_sandbox>", "exec")
            eval(compiled, env, env)  # noqa: S307
            transform_fn = env.get("transform")
            if not callable(transform_fn):
                raise ValueError("Synthesized code does not define a callable "
                    "`transform(grid)` function.")
            raw_res = transform_fn(copy.deepcopy(grid_in))
            box["result"] = normalize_to_int_grid(raw_res)
        except Exception as exc:  # noqa: BLE001
            logger.debug("cegis_unshackled_target_error", error=str(exc))
            box["error_type"] = type(exc).__name__
            box["error_message"] = str(exc)
            box["traceback"] = traceback.format_exc()

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=max(0.05, timeout_s))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if worker.is_alive():
        return ExecutionOutcome(
            success=False,
            output_grid=None,
            error_type="TimeoutError",
            error_message=f"Execution timed out after {timeout_s:.2f}s",
            traceback_str=None,
            elapsed_ms=elapsed_ms,
        )

    if "error_type" in box:
        return ExecutionOutcome(
            success=False,
            output_grid=None,
            error_type=str(box["error_type"]),
            error_message=str(box.get("error_message", "")),
            traceback_str=str(box.get("traceback", "")),
            elapsed_ms=elapsed_ms,
        )

    return ExecutionOutcome(
        success=True,
        output_grid=cast(list[list[int]], box.get("result")),
        error_type=None,
        error_message=None,
        traceback_str=None,
        elapsed_ms=elapsed_ms,
    )


def get_cegis_docker_transport() -> DockerRPCTransport | None:
    """Returns singleton DockerRPCTransport instance for isolated container execution (D-AUD-13)."""
    with _DOCKER_TRANSPORT_LOCK:
        if _DOCKER_TRANSPORT_HOLDER["instance"] is None:
            try:
                t = DockerRPCTransport(
                    container_name="lucca-file-sandbox", use_direct_fallback=False
                )
                if t.is_docker_available():
                    _DOCKER_TRANSPORT_HOLDER["instance"] = t
            except Exception as exc:
                logger.debug("docker_transport_init_failed", error=str(exc))
                _DOCKER_TRANSPORT_HOLDER["instance"] = None
        inst = _DOCKER_TRANSPORT_HOLDER["instance"]
        return inst if isinstance(inst, DockerRPCTransport) else None



_DOCKER_RUNNER_PRELUDE: Final[str] = """import sys, json
for _p in ('/workspace', '/tmp/lucca_runtime'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import numpy as np
import scipy, scipy.ndimage as ndimage
import itertools, collections, math, copy
from lucca.reasoning import spatial_anchors, relational
from lucca.reasoning.spatial_anchors import (
    bbox, crop, centroid, connected_components, is_identical_shape,
    rot90, flip_h, flip_v, flood_fill, find_cavities, color_counts,
    canvas, paste, Component
)
from lucca.reasoning.relational import (
    in_cavity, part_of, externally_connected, partially_overlaps,
    above, below, left_of, right_of, extract_cavities, extract_cavity_mask,
    extract_exterior_mask, is_between, y_projection, x_projection, GridRegion
)
from lucca.reasoning import arc_primitives, spatial_dsl, spatial_scheme
from lucca.reasoning.relational import mereo, realize_real
from lucca.reasoning.arc_primitives import (
    clone_grid, replace_color, rotate_90, bounding_box,
    get_connected_components, get_objects, gravity_drop, align_objects
)
from lucca.reasoning.spatial_dsl import (
    SpatialObject, normalize_grid, find_objects, count_objects, count_cells,
    dominant_object, unique_colors, fill_holes, is_enclosed, bbox_of_all,
    crop_to_content, sort_objects, column_heights, order_columns_by_height,
    row_widths, denoise, majority_filter, restore_periodic_pattern,
    complete_symmetry, draw_line, move_until_contact, rotate_grid,
    reflect_grid, translate_grid, crop_grid, overlay_grid,
    analyze_symbolic_invariants
)
from lucca.reasoning.relational.realize_real import during_real, point_in_interval
"""



def _prepare_cegis_code(code: str, t0: float) -> tuple[str | None, ExecutionOutcome | None]:
    """Sanitizes and AST-validates candidate CEGIS Python code."""

    clean_code = strip_comments_and_docstrings(code)
    repaired_code, is_valid_syntax, syntax_err = sanitize_and_repair_python_code(clean_code)
    if is_valid_syntax and repaired_code:
        clean_code = strip_comments_and_docstrings(repaired_code)
    elif not is_valid_syntax:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return None, ExecutionOutcome(
            success=False,
            output_grid=None,
            error_type="SyntaxError",
            error_message=syntax_err or "Invalid Python syntax",
            traceback_str=syntax_err,
            elapsed_ms=elapsed_ms,
        )

    safe_ok, safe_err = validate_cegis_ast_safety(clean_code)
    if not safe_ok:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return None, ExecutionOutcome(
            success=False,
            output_grid=None,
            error_type="SecurityError",
            error_message=safe_err or "AST safety validation failed",
            traceback_str=safe_err,
            elapsed_ms=elapsed_ms,
        )
    return clean_code, None


def execute_unshackled_python(
    code: str,
    grid_in: list[list[int]],
    timeout_s: float = 4.0,
    transport: DockerRPCTransport | None = None,
) -> ExecutionOutcome:
    """Executes Python transform code after AST sanitization and safety validation."""
    t0 = time.perf_counter()
    clean_code, err_outcome = _prepare_cegis_code(code, t0)
    if err_outcome is not None or clean_code is None:
        return err_outcome  # type: ignore[return-value]

    rpc_client = transport if transport is not None else get_cegis_docker_transport()
    if rpc_client is None:
        return _execute_in_restricted_sandbox(clean_code, grid_in, timeout_s)

    runner_script = (
        f"{_DOCKER_RUNNER_PRELUDE}\n{clean_code}\n\n"
        "if 'transform' not in locals() or not callable(locals()['transform']):\n"
        "    raise ValueError('Synthesized code does not define a callable `transform(grid)` "
            "function.')\n"
        f"_res = transform({json.dumps(grid_in)})\n"
        "print('__LUCCA_RESULT_START__')\nprint(json.dumps(_res))\nprint('__LUCCA_RESULT_END__')\n"
    )
    try:
        res = rpc_client.execute(
            call_id=f"cegis-{time.time_ns()}",
            tool="run_python",
            args={"code": runner_script, "timeout": max(int(timeout_s), 2)},
            timeout_s=timeout_s + 4.0,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if not getattr(res, "ok", False):
            err_msg = str(getattr(res, "stderr", "") or getattr(res, "content", "Execution failed"))
            exc_matches = re.findall(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exc"
                r"eption))\b", err_msg, re.MULTILINE)
            err_type = exc_matches[
                -1] if exc_matches else (
                    "TimeoutError" if "timeout" in err_msg.lower() or "timed out"
                        in err_msg.lower() else "ExecutionError")
            return ExecutionOutcome(False, None, err_type, err_msg, getattr(res, "stderr", None),
                elapsed_ms)

        content = str(getattr(res, "content", "") or "")
        m = re.search(r"__LUCCA_RESULT_START__\s*(.*?)\s*__LUCCA_RESULT_END__", content, re.DOTALL)
        if not m:
            return ExecutionOutcome(False, None, "ValueError", "Function completed without "
                "structured output markers.", None, elapsed_ms)
        return ExecutionOutcome(True, normalize_to_int_grid(json.loads(m.group(1).strip())), None,
            None, None, elapsed_ms)
    except Exception as exc:
        logger.debug("execute_unshackled_python_failed", error=str(exc))
        return ExecutionOutcome(False, None, type(exc).__name__, str(exc), None,
            (time.perf_counter() - t0) * 1000.0)


def execute_unshackled_python_batch(
    code: str,
    grids_in: list[list[list[int]]],
    timeout_s: float = 8.0,
    transport: DockerRPCTransport | None = None,
) -> list[ExecutionOutcome]:
    """Evaluates candidate code across multiple demonstration grids in a single roundtrip."""
    t0 = time.perf_counter()
    if not grids_in:
        return []
    clean_code, err_outcome = _prepare_cegis_code(code, t0)
    if err_outcome is not None or clean_code is None:
        return [err_outcome for _ in grids_in]  # type: ignore[misc]

    rpc_client = transport if transport is not None else get_cegis_docker_transport()
    if rpc_client is None:
        per_grid_timeout = max(0.5, timeout_s / max(len(grids_in), 1))
        return [_execute_in_restricted_sandbox(clean_code, g, per_grid_timeout) for g in grids_in]

    runner_script = (
        f"{_DOCKER_RUNNER_PRELUDE}\n{clean_code}\n\n"
        "if 'transform' not in locals() or not callable(locals()['transform']):\n"
        "    raise ValueError('Synthesized code does not define a callable `transform(grid)` "
            "function.')\n"
        f"_inputs = {json.dumps(grids_in)}\n"
        "_outputs = [transform(_g) for _g in _inputs]\n"
        "print('__LUCCA_RESULT_START__')\nprint(json.dumps(_outputs))\nprint('__LUCCA_RESULT_END__')\n"
    )
    try:
        res = rpc_client.execute(
            call_id=f"cegis-batch-{time.time_ns()}",
            tool="run_python",
            args={"code": runner_script, "timeout": max(int(timeout_s), 2)},
            timeout_s=timeout_s + 4.0,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if not getattr(res, "ok", False):
            err_msg = str(getattr(res, "stderr", "") or getattr(res, "content",
                "Batch execution failed"))
            err_type = "TimeoutError" if (
                "timed out" in err_msg.lower() or "timeout"
                in err_msg.lower()) else "ExecutionError"
            return [ExecutionOutcome(False, None, err_type, err_msg, getattr(res, "stderr", None),
                elapsed_ms) for _ in grids_in]

        content = str(getattr(res, "content", "") or "")
        m = re.search(r"__LUCCA_RESULT_START__\s*(.*?)\s*__LUCCA_RESULT_END__", content, re.DOTALL)
        if not m:
            return [ExecutionOutcome(False, None, "ValueError", "Batch completed without "
                "structured markers.", None, elapsed_ms) for _ in grids_in]

        raw_outputs = json.loads(m.group(1).strip())
        outcomes: list[ExecutionOutcome] = []
        per_ms = elapsed_ms / max(len(grids_in), 1)
        for raw in raw_outputs:
            try:
                outcomes.append(ExecutionOutcome(True, normalize_to_int_grid(raw), None, None, None,
                    per_ms))
            except Exception as norm_err:
                logger.debug("batch_grid_normalization_failed", error=str(norm_err))
                outcomes.append(ExecutionOutcome(False, None, "TypeError",
                    f"Output could not be normalized: {norm_err}", None, per_ms))
        return outcomes

    except Exception as exc:
        logger.debug("execute_unshackled_python_batch_failed", error=str(exc))
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return [ExecutionOutcome(False, None, type(exc).__name__, str(exc), None,
            elapsed_ms) for _ in grids_in]


CANONICAL_PRIMITIVES_PROMPT: Final[str] = (
    "======================================================================\n"
    "MANDATORY PRE-IMPORTED SPATIAL & RELATIONAL PRIMITIVES (In Global Scope):\n"
    "======================================================================\n"
    "- `connected_components(arr, connectivity=8, background=0)`: returns list of Component "
        "objects with "
    "`.color`, `.mask`, `.bbox`, `.area`, `.centroid`, `.cropped_mask()`.\n"
    "- `in_cavity(a, b)`: returns True iff region/component `a` is strictly enclosed inside the "
        "hollow cavity of `b` "
    "(4-connected border complement; correctly returns False for open U-shapes).\n"
    "- `extract_cavities(b)`: returns frozenset of (r, c) coordinates of hollow cavities in `b`.\n"
    "- `extract_cavity_mask(b, shape=None)`: returns 2D boolean numpy mask of "
        "cavity/interior of `b`.\n"
    "- `extract_exterior_mask(b, shape)`: returns 2D boolean numpy mask of cells OUTSIDE `b` and "
        "outside `b`'s cavities.\n"
    "- `is_between(p, a, b)`: returns True iff point or component `p` lies strictly within the "
        "bounding span formed by anchors `a` and `b` (1D/2D betweenness).\n"
    "- `part_of(a, b)`: returns True iff every cell of `a` is part of `b` (subset containment).\n"
    "- `externally_connected(a, b, four_connected=True)`: returns True iff `a` and `b` touch at "
        "their boundary without overlapping.\n"
    "- `above(a, b)`, `below(a, b)`, `left_of(a, b)`, `right_of(a, b)`: qualitative spatial "
        "ordering via Allen interval algebra.\n"
    "- `bbox(mask)`: returns (min_r, min_c, max_r, max_c, h, w) or None.\n"
    "- `crop(arr, bbox_tuple)`: crops subgrid corresponding to bbox.\n"
    "- `centroid(mask)`: returns (mean_r, mean_c).\n"
    "- `is_identical_shape(mask_a, mask_b)`: returns True if two binary shapes are identical under "
        "translation.\n"
    "- `rot90(arr, k=1)`, `flip_h(arr)`, `flip_v(arr)`: symmetry transformations.\n"
    "- `canvas(h, w, fill_val=0)`: returns fresh numpy canvas of shape (h, w).\n"
    "- `paste(base, patch, top_r, left_c, transparent_val=None)`: pastes patch onto base grid.\n"
    "\n"
    "MANDATORY REASONING & PROGRAMMING CONTRACT:\n"
    "1. ENCLOSURE / CAVITY / INSIDE QUERIES:\n"
    "   - When the task involves checking if an object or pixel is inside, enclosed by, or "
        "contained in a frame/cavity, "
    "YOU MUST USE `in_cavity(a, b)`, `extract_cavities(b)`, or `extract_cavity_mask(b)`.\n"
    "   - FORBIDDEN HEURISTIC: NEVER use bounding-box coordinate comparisons (`min_r <= r <= max_r "
        "and min_c <= c <= max_c`) "
    "as a test for enclosure. Bounding boxes fail on non-convex or concave containers.\n"
    "   - FORBIDDEN BOILERPLATE: NEVER write manual BFS flood-fill queues or custom crawler loops "
        "from scratch. Call the built-in primitives.\n"
    "   - MULTI-CONTAINER MANDATE: A grid may contain MULTIPLE independent containers (e.g. 2 or 3 "
        "separate frames/boxes). "
    "NEVER assume there is only one largest container using `max(components, key=...)`. Iterate "
        "over ALL candidate containers.\n"
    "2. NON-ENCLOSURE QUERIES (Collinearity, betweenness, counts, color mapping):\n"
    "   - When the problem does NOT involve cavities or enclosed holes, use direct arithmetic or "
        "`is_between(p, a, b)`.\n"
    "3. SYNTAX & CLEAN CODE:\n"
    "   - Return ONLY clean executable Python code inside a single ```python ... ``` block.\n"
    "   - Absolutely NO comments (#), NO docstrings, and NO natural language explanations inside "
        "the code block.\n"
    "======================================================================\n"
)

DEFAULT_CONTAINER: Final[str] = "lucca-file-sandbox"
DEFAULT_TIMEOUT_S: Final[float] = 10.0
DEFAULT_MAX_TURNS: Final[int] = 3


@dataclass(frozen=True)
class CEGISTrace:
    """Audit record for a single synthesis / execution turn."""
    turn: int
    code: str
    ok_exec: bool
    stdout: str
    stderr: str
    error_type: str | None
    error_message: str | None
    elapsed_ms: float


@dataclass(frozen=True)
class CEGISResult:
    """Final outcome of the multi-turn CEGIS synthesis loop."""
    success: bool
    final_code: str | None
    predicted_output: str | None
    turns_taken: int
    method: str
    failure_stage: str | None
    traces: list[CEGISTrace] = field(default_factory=list)
    total_elapsed_ms: float = 0.0

    @property
    def output(self) -> str | None:
        return self.predicted_output


def parse_python_exception(stderr_text: str) -> tuple[str | None, str | None]:
    """Extracts the Python exception type and message from a standard traceback string."""
    if not stderr_text:
        return None, None
    lines = [line.strip() for line in stderr_text.strip().splitlines() if line.strip()]
    if not lines:
        return None, None
    last_line = lines[-1]
    match = re.match(r"^([A-Za-z_]\w*Error|[A-Za-z_]\w*Exception|AssertionErro"
        r"r):\s*(.*)$", last_line)
    if match:
        return match.group(1), match.group(2)
    if "Error" in last_line:
        parts = last_line.split(":", 1)
        return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
    return None, last_line


class PythonCEGISEngine:
    """Counter-Example Guided Inductive Synthesis compatibility engine for general Python tasks."""

    def __init__(
        self,
        container_name: str = DEFAULT_CONTAINER,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_turns: int = DEFAULT_MAX_TURNS,
        server_url: str = "http://127.0.0.1:8080/v1/chat/completions",
        num_candidates: int = 1,
        outcome_sink: CognitiveOutcomeSink | None = None,
    ) -> None:
        self.container_name = container_name
        self.timeout_s = timeout_s
        self.max_turns = max_turns
        self.server_url = server_url
        self.num_candidates = num_candidates
        self.outcome_sink = outcome_sink
        self._rpc: DockerRPCTransport | None = None

    def _notify_outcome_sink(
        self,
        result: CEGISResult,
        task_prompt: str,
        task_id: str | None = None,
        outcome_sink: CognitiveOutcomeSink | None = None,
    ) -> None:
        sink = outcome_sink or self.outcome_sink
        if sink is None:
            return
        try:
            tid = task_id or f"py-cegis-{uuid.uuid4().hex[:8]}"
            turn_1_err = (
                f"{result.traces[0].error_type or 'Error'}: "
                f"{result.traces[0].error_message or result.traces[0].stderr[:120]}"
                if result.traces and not result.traces[0].ok_exec
                else None
            )
            turn_traces: list[dict[str, object]] = [
                {
                    "turn": tr.turn,
                    "name": "initial_synthesis" if tr.turn == 1 else f"repair_turn_{tr.turn}",
                    "summary": f"ok_exec={tr.ok_exec}; out={tr.stdout[:60]}"
                    if tr.ok_exec
                    else f"error={
                        tr.error_type or 'RuntimeError'}: {(tr.error_message or tr.stderr)[:80]}",
                }
                for tr in result.traces
            ]
            sink.record_cegis_outcome(
                task_id=tid,
                problem_summary=task_prompt.strip()[:160],
                engine_name="PythonCEGISEngine",
                success=result.success,
                turns_taken=result.turns_taken,
                final_code=result.final_code,
                turn_1_error=turn_1_err,
                verified_strategy=result.method,
                turn_traces=turn_traces,
                status_label=result.method,
            )
        except Exception as sink_err:  # noqa: BLE001
            logger.debug("python_cegis_outcome_sink_failed", error=str(sink_err))

    @property
    def transport(self) -> DockerRPCTransport:
        return self._get_rpc()

    def warmup(self) -> bool:
        return self._get_rpc().warmup()

    def _get_rpc(self) -> DockerRPCTransport:
        if self._rpc is None:
            self._rpc = DockerRPCTransport(container_name=self.container_name,
                use_direct_fallback=False)
            self._rpc.ensure_container_running()
            try:
                self._rpc.execute(call_id="cegis-warmup", tool="run_python", args={"code": "pass"},
                    timeout_s=15.0)
            except Exception as e:
                logger.warning("cegis_docker_warmup_failed", error=str(e))
        return self._rpc

    def _query_llm(
        self, messages: list[dict[str, str]], temperature: float = 0.1, max_tokens: int = 1024
    ) -> tuple[str, str]:
        payload: dict[str, object] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(self.server_url, json=payload)
            resp.raise_for_status()
            choice = resp.json()["choices"][0]
            return str(
                choice[
                    "message"].get("content") or "").strip(), str(choice.get("finish_reason")
                        or "stop")

    @staticmethod
    def _extract_output_pattern(stdout_val: str, output_pattern: str | None) -> str:
        text = stdout_val.strip()
        if not text or not output_pattern:
            return text
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        target_line = lines[-1] if lines else text
        matches = list(re.finditer(output_pattern, target_line)) or list(re.finditer(output_pattern,
            text))
        if matches:
            m = matches[-1]
            return m.group(1) if m.groups() else m.group(0)
        return text

    def _execute_code(self, code: str) -> tuple[bool, str, str]:
        try:
            res = self._get_rpc().execute(
                call_id=f"cegis-{time.time_ns()}",
                tool="run_python",
                args={"code": code},
                timeout_s=self.timeout_s,
            )
            if res.ok:
                return True, str(res.content or "").strip(), ""
            return False, "", str(res.stderr or res.content or "execution_failed").strip()
        except Exception as e:
            logger.warning("cegis_docker_execution_exception", error=str(e))
            return False, "", f"{type(e).__name__}: {e}"


    def _parse_err(self, stderr_text: str) -> tuple[str | None, str | None]:
        return parse_python_exception(stderr_text)

    def synthesize_checked_formalization(
        self, task_prompt: str, output_pattern: str | None = None
    ) -> CEGISResult:
        t0 = time.perf_counter()
        prompts = [
            ("SYMBOLIC", "Solve using exact symbolic computation (sympy/z3) and print ONLY the "
                "final answer in ```python ... ```.", 0.1),
            ("BRUTE_FORCE", "Solve using direct numerical simulation/enumeration and print ONLY "
                "the final answer in ```python ... ```.", 0.2),
        ]
        traces: list[CEGISTrace] = []
        outputs: list[tuple[str, str, str]] = []
        for idx, (label, sys_p, temp) in enumerate(prompts, start=1):
            t_cand = time.perf_counter()
            content, _ = self._query_llm([{"role": "system", "content": sys_p}, {"role": "user",
                "content": task_prompt}], temperature=temp)
            code = extract_python_code(content) or ""
            ok_exec, stdout_val, stderr_val = False, "", "No code extracted"
            if code:
                sanitized_c, ok_s, _ = sanitize_python_code(code)
                ok_exec, stdout_val, stderr_val = self._execute_code(sanitized_c if ok_s else code)
            elapsed_ms = (time.perf_counter() - t_cand) * 1000.0
            err_t, err_m = (None, None) if ok_exec else self._parse_err(stderr_val)
            traces.append(CEGISTrace(idx, code, ok_exec, stdout_val, stderr_val, err_t, err_m,
                elapsed_ms))
            if ok_exec and stdout_val.strip():
                outputs.append((label, self._extract_output_pattern(stdout_val,
                    output_pattern).strip(), code))

        if len(outputs) == 2 and outputs[0][1] == outputs[1][1] and outputs[0][1] != "":
            total_ms = (time.perf_counter() - t0) * 1000.0
            res_agreed = CEGISResult(True, outputs[0][2], outputs[0][1], 2,
                "CHECKED_FORMALIZATION_AGREED", None, traces, total_ms)
            self._notify_outcome_sink(res_agreed, task_prompt)
            return res_agreed

        if len(outputs) == 2 and outputs[0][1] != outputs[1][1]:
            last_tr = traces[-1]
            traces[-1] = CEGISTrace(
                last_tr.turn, last_tr.code, last_tr.ok_exec, last_tr.stdout, last_tr.stderr,
                "DisagreementError",
                    f"Symbolic ({outputs[0][1]!r}) != Brute-Force ({outputs[1][1]!r})",
                        last_tr.elapsed_ms,
            )

        esc_res = self.synthesize_parallel(task_prompt=task_prompt, output_pattern=output_pattern,
            n_candidates=max(3, self.num_candidates))
        if esc_res.success and esc_res.predicted_output and esc_res.predicted_output.strip():
            return esc_res
        total_ms = (time.perf_counter() - t0) * 1000.0
        res_dis = CEGISResult(
            False, esc_res.final_code or (outputs[0][2] if outputs else None), None,
            len(traces) + esc_res.turns_taken, "CHECKED_FORMALIZATION_DISAGREED",
            "DUAL_FORMULATION_DISAGREEMENT", traces + esc_res.traces, total_ms,
        )
        self._notify_outcome_sink(res_dis, task_prompt)
        return res_dis

    def synthesize_parallel(
        self,
        task_prompt: str,
        system_prompt: str | None = None,
        test_harness: str | None = None,
        output_pattern: str | None = None,
        n_candidates: int | None = None,
    ) -> CEGISResult:
        n = n_candidates if n_candidates is not None else self.num_candidates
        if n <= 1:
            return self.synthesize_and_repair(task_prompt, system_prompt, test_harness,
                output_pattern)
        hints = [
            "Use a direct mathematical / algebraic formula where possible.",
            "Use simulation or step-by-step enumeration to derive the answer.",
            "Use SymPy or built-in Python arithmetic; avoid manual loops if possible.",
            "Use brute-force search with explicit case enumeration.",
            "Translate the problem into a constraint and solve via conditional logic.",
        ]
        for i in range(n):
            hint = hints[i % len(hints)]
            aug_sys = f"{system_prompt}\nStrategy hint: {hint}" if system_prompt else (
                "You are "
                f"an expert Python programmer.\nStrategy hint: {hint}"
            )
            t_cand = time.perf_counter()
            content, _ = self._query_llm([{"role": "system", "content": aug_sys}, {"role": "user",
                "content": task_prompt}], temperature=0.5 + 0.1 * i)
            code = extract_python_code(content)
            ok_exec, stdout_val, stderr_val, full_exec = False, "", "No code extracted", ""
            if code:
                full_exec = (
                    f"{code}\n\n# --- Verification Harness "
                    f"---\n{test_harness}"
                ) if (test_harness and test_harness.strip() not in code) else code
                if "print" not in full_exec and "ans" in full_exec:
                    full_exec = f"{full_exec}\nprint(ans)"
                ok_exec, stdout_val, stderr_val = self._execute_code(full_exec)
            elapsed_cand = (time.perf_counter() - t_cand) * 1000.0
            err_type, err_msg = (None, None) if ok_exec else self._parse_err(stderr_val)
            trace = CEGISTrace(i + 1, full_exec, ok_exec, stdout_val, stderr_val, err_type, err_msg,
                elapsed_cand)
            pred = self._extract_output_pattern(stdout_val, output_pattern) if ok_exec else None
            result = CEGISResult(
                ok_exec, full_exec if code else None, pred, 1, f"PARALLEL_CANDIDATE_{i + 1}",
                None if ok_exec else "CANDIDATE_EXECUTION_FAILED", [trace], elapsed_cand,
            )
            if ok_exec and (bool(stdout_val.strip()) or bool(test_harness)):
                return result
        return self.synthesize_and_repair(task_prompt, system_prompt, test_harness, output_pattern,
            temperature=0.1)

    def synthesize_and_repair(
        self,
        task_prompt: str,
        system_prompt: str | None = None,
        test_harness: str | None = None,
        output_pattern: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1536,
        exemplar_messages: list[dict[str, str]] | None = None,
        prelude: str | None = None,
        max_turns: int | None = None,
        task_id: str | None = None,
        outcome_sink: CognitiveOutcomeSink | None = None,
    ) -> CEGISResult:
        t0 = time.perf_counter()
        traces: list[CEGISTrace] = []
        messages: list[dict[str, str]] = list(exemplar_messages) if exemplar_messages else (
            ([{"role": "system",
                "content": system_prompt}] if system_prompt else []) + [{"role": "user",
                    "content": task_prompt}]
        )
        last_code: str | None = None
        failure_stage: str | None = None
        effective_max_turns = max_turns if max_turns is not None else self.max_turns

        for turn in range(1, effective_max_turns + 1):
            t_turn = time.perf_counter()
            content, finish_reason = self._query_llm(
                messages=messages,
                temperature=temperature if turn == 1 else min(0.4, temperature + 0.15 * (turn - 1)),
                max_tokens=max(max_tokens, 1536) if turn >= 2 else max_tokens,
            )
            code = extract_python_code(content)
            if not code:
                elapsed_ms = (time.perf_counter() - t_turn) * 1000.0
                traces.append(CEGISTrace(turn, "", False, "", "No valid Python code "
                    "found in output", "TranslationError", "No code block extracted", elapsed_ms))
                failure_stage = "TRANSLATION_NO_CODE"
                messages.append({"role": "assistant", "content": content[:400]})
                messages.append({"role": "user", "content": "Error: No complete Python code block "
                    "detected. Output ONLY ```python ... ```."})
                continue

            last_code = code
            full_exec_code = (
                f"{prelude.strip()}\n\n"
                f"{code}"
            ) if (prelude and prelude.strip() and prelude.strip() not in code) else code
            if test_harness and test_harness.strip() not in full_exec_code:
                full_exec_code = f"{
                    full_exec_code}\n\n# --- Verification Harness ---\n{test_harness}"
            sanitized_exec, ok_san, _ = sanitize_python_code(full_exec_code)
            if ok_san:
                full_exec_code = sanitized_exec
            elif "print" not in full_exec_code and "ans" in full_exec_code:
                full_exec_code = f"{full_exec_code}\nprint(ans)"

            ok_exec, stdout_val, stderr_val = self._execute_code(full_exec_code)
            elapsed_ms = (time.perf_counter() - t_turn) * 1000.0
            if ok_exec and not test_harness:
                if not stdout_val.strip() or "<built-in function" in stdout_val:
                    ok_exec, stderr_val = False, "EmptyOutputError: Code printed no output."
                elif output_pattern and not re.search(output_pattern, stdout_val):
                    ok_exec, stderr_val = False, f"OutputFormatError: Stdout did not match {
                        output_pattern!r}."

            err_type, err_msg = parse_python_exception(stderr_val) if not ok_exec else (None, None)
            traces.append(CEGISTrace(turn, full_exec_code, ok_exec, stdout_val, stderr_val,
                err_type, err_msg, elapsed_ms))
            if ok_exec:
                predicted_out = self._extract_output_pattern(stdout_val, output_pattern)
                total_elapsed = (time.perf_counter() - t0) * 1000.0
                method = "VERIFIED_PROGRAM" if turn == 1 else "VERIFIED_REPAIRED_PROGRAM"
                res_ok = CEGISResult(True, full_exec_code, predicted_out, turn, method, None,
                    traces, total_elapsed)
                self._notify_outcome_sink(res_ok, task_prompt, task_id=task_id,
                    outcome_sink=outcome_sink)
                return res_ok

            failure_stage = (
                "SANDBOX_TIMEOUT_OR_RESOUR"
                "CE_LIMIT"
            ) if (
                "TimeoutError" in stderr_val or "timed out" in stderr_val.lower()) else (
                    "EXECUTION_RU"
                    "NTIME_ERROR"
                )
            if turn < effective_max_turns:
                cleaned_lines = [
                    ln for ln in (code or content).splitlines() if not ln.strip().startswith("#")]
                compact_code = "\n".join(cleaned_lines[-40:])
                repair_prompt = (
                    f"Your Python code produced an error:\n[Error Type]: {
                        err_type or 'RuntimeError'}\n"
                    f"[Error Message]: {
                        err_msg or stderr_val.strip()}\n[Traceback]:\n{stderr_val.strip()[-600:]}\n"
                    "Provide the corrected Python script inside ```python ... ```."
                )
                messages.append({"role": "assistant", "content": f"```python\n{compact_code}\n```"})
                messages.append({"role": "user", "content": repair_prompt})

        total_elapsed = (time.perf_counter() - t0) * 1000.0
        res_fail = CEGISResult(False, last_code, None, effective_max_turns, "INTERNAL_FALLBACK",
            failure_stage or "LLM_REASONING_LOGIC", traces, total_elapsed)
        self._notify_outcome_sink(res_fail, task_prompt, task_id=task_id, outcome_sink=outcome_sink)
        return res_fail
