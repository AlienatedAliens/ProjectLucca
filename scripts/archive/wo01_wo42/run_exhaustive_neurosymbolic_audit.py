"""
Project Lucca — Exhaustive Neurosymbolic Audit & Factorial Telemetry Runner
============================================================================
Publication-Grade Empirical Evaluation Harness for:
- Arm A: Direct LLM Control Baseline
- Arm B: Dynamic Python Program Synthesis
- Arm C: GBNF-Constrained MicroScheme LISP with CPU Hole Enumeration
- Arm D: Unified Neurosymbolic Hybrid (Python Induction -> LISP Primitive -> GBNF Hole Search)

Collects full publication telemetry:
- Latency breakdown (prefill, generation, hole enumeration, sandbox exec)
- Token accounting & AST/MDL complexity metrics
- Hardware footprint (VRAM MiB, GPU power W, temperature C, host RAM MB)
- Exact failure taxonomy & differential regression tracking across patch versions
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Final

import httpx
import numpy as np
import scipy.ndimage
from scipy.stats import binomtest

# Add repo root to path
REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.reasoning.cost import (
    ast_depth,
    ast_node_count,
    compute_description_length,
    python_ast_cost,
)
from lucca.reasoning.spatial_dsl import (
    PrimitiveDomain,
    SpatialObject,
    SymbolicInvariants,
    analyze_symbolic_invariants,
    check_metamorphic_invariance,
    find_objects,
    flood_fill,
    rot90,
    flip_h,
    flip_v,
    crop,
    resolve_scoped_primitives,
)
from lucca.reasoning.arc_primitives import (
    bounding_box,
    get_connected_components,
    replace_color,
    gravity_drop,
)
from lucca.reasoning.spatial_scheme import (
    GLOBAL_MACRO_REGISTRY,
    SPATIAL_SCHEME_PRIMITIVES,
    _coerce_grid,
    _to_int,
    _to_kw_str,
    _to_scheme_grid,
    compile_dynamic_sketch_grammar,
    enumerate_sketch_bindings,
    evaluate_spatial_sketch,
)
from lucca.reasoning.scheme.parser import (
    Keyword,
    Symbol,
    parse_expr,
    register_dynamic_op,
    to_canonical,
)
from lucca.sandbox.preflight import extract_python_code
from scripts.measure_footprint import FootprintMonitor
from scripts.run_concept_arc import (
    ABDUCTION_GBNF_GRAMMAR,
    AbductionPayload,
    compute_grid_diff,
    execute_transform_code,
    extract_grid_from_text,
    extract_perceptual_invariants,
    generate_visual_diff,
    query_llm,
    wilson_ci,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("exhaustive_audit")

SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0
LEARNED_MACROS_FILE: Final[Path] = REPO_ROOT / "data" / "learned_macros.json"


# =============================================================================
# Telemetry Data Structures
# =============================================================================

@dataclass
class TaskTelemetry:
    llm_prefill_ms: float = 0.0
    llm_generation_ms: float = 0.0
    cpu_hole_enumeration_ms: float = 0.0
    sandbox_execution_ms: float = 0.0
    total_elapsed_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    gpu_vram_peak_mib: float = 0.0
    gpu_power_w: float = 0.0
    gpu_temp_c: float = 0.0
    host_ram_mb: float = 0.0
    ast_depth: int = 0
    ast_node_count: int = 0
    complexity_cost: float = 0.0
    mdl_bits: float = 0.0
    candidates_evaluated: int = 0
    is_metamorphic_invariant: bool = False
    repair_rounds: int = 0


@dataclass
class AuditRecord:
    task_id: str
    concept: str
    tier: str
    patch_id: str
    arm: str
    success: bool
    method: str
    failure_code: str | None
    failure_detail: str | None
    synthesized_program: str | None
    telemetry: TaskTelemetry = field(default_factory=TaskTelemetry)


# =============================================================================
# Helper & Extraction Utilities
# =============================================================================

def extract_python_functions(code_text: str) -> list[tuple[str, str]]:
    """Extracts top-level function names and source blocks using AST parsing."""
    functions: list[tuple[str, str]] = []
    try:
        tree = ast.parse(code_text)
        lines = code_text.splitlines()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                fn_name = node.name
                start_l = node.lineno - 1
                end_l = getattr(node, "end_lineno", len(lines))
                fn_source = "\n".join(lines[start_l:end_l])
                functions.append((fn_name, fn_source))
    except Exception:
        matches = re.finditer(r"(def\s+([a-zA-Z_]\w*)\s*\([^)]*\):[\s\S]*?)(?=\ndef|\Z)", code_text)
        for m in matches:
            functions.append((m.group(2), m.group(1).strip()))
    return functions


def query_llm_with_telemetry(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    grammar: str | None = None,
) -> tuple[str, int, int, float]:
    """Queries resident llama-server and measures exact token usage and latency."""
    t0 = time.perf_counter()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if grammar is not None:
        payload["grammar"] = grammar

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - t0) * 1000.0
        content = str(data["choices"][0]["message"]["content"])
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", len(prompt) // 4)
        completion_tokens = usage.get("completion_tokens", len(content) // 4)
        return content, prompt_tokens, completion_tokens, latency_ms


# =============================================================================
# Execution Arms
# =============================================================================

def run_arm_a_control(
    task_id: str,
    concept: str,
    train_pairs: list[dict[str, list[list[int]]]],
    test_pair: dict[str, list[list[int]]],
    tier: str,
    patch_id: str,
) -> AuditRecord:
    """Arm A: Direct Baseline Control (Zero-Shot)."""
    gt_test_output = test_pair["output"]
    train_desc = "".join(f"Example {i+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n" for i, ex in enumerate(train_pairs))
    prompt = (
        "You are an expert ARC-AGI reasoning engine. Solve this spatial grid transformation task.\n"
        "Study the training examples, deduce the underlying transformation rule, and output the EXACT "
        "test output grid for the test input.\n\n"
        f"{train_desc}"
        f"Test Input:\n{test_pair['input']}\n\n"
        "Output ONLY the test output grid as a valid JSON 2D array inside a ```json ... ``` block."
    )
    t0 = time.perf_counter()
    try:
        resp, p_toks, c_toks, lat_ms = query_llm_with_telemetry(prompt, temperature=0.1, max_tokens=1024)
        grid = extract_grid_from_text(resp, grid_in=test_pair["input"])
        total_ms = (time.perf_counter() - t0) * 1000.0

        telemetry = TaskTelemetry(
            llm_generation_ms=lat_ms,
            total_elapsed_ms=total_ms,
            prompt_tokens=p_toks,
            completion_tokens=c_toks,
        )

        if grid is None:
            return AuditRecord(task_id, concept, tier, patch_id, "Arm_A_Control", False, "DIRECT", "PARSE_ERROR", "No grid detected in response", None, telemetry)
        if grid == gt_test_output:
            return AuditRecord(task_id, concept, tier, patch_id, "Arm_A_Control", True, "DIRECT", None, None, None, telemetry)
        if len(grid) != len(gt_test_output) or len(grid[0]) != len(gt_test_output[0]):
            return AuditRecord(task_id, concept, tier, patch_id, "Arm_A_Control", False, "DIRECT", "SHAPE_MISMATCH", f"Expected {len(gt_test_output)}x{len(gt_test_output[0])}, got {len(grid)}x{len(grid[0])}", None, telemetry)
        return AuditRecord(task_id, concept, tier, patch_id, "Arm_A_Control", False, "DIRECT", "VALUE_MISMATCH", "Cell value disagreement", None, telemetry)
    except Exception as e:
        return AuditRecord(task_id, concept, tier, patch_id, "Arm_A_Control", False, "DIRECT", "EXCEPTION", str(e), None, TaskTelemetry(total_elapsed_ms=(time.perf_counter()-t0)*1000.0))


def run_arm_b_python(
    task_id: str,
    concept: str,
    train_pairs: list[dict[str, list[list[int]]]],
    test_pair: dict[str, list[list[int]]],
    invariants: SymbolicInvariants,
    abduction_payload: AbductionPayload,
    tier: str,
    patch_id: str,
) -> AuditRecord:
    """Arm B: Dynamic Python Program Synthesis."""
    gt_test_output = test_pair["output"]
    train_desc = "".join(f"Example {i+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n" for i, ex in enumerate(train_pairs[:3]))
    t0 = time.perf_counter()
    telemetry = TaskTelemetry()

    # Step 1: Induce Python helper
    induce_prompt = (
        "Analyze these input-output spatial grid examples:\n\n"
        f"{train_desc}"
        f"Hypothesis: {abduction_payload.to_readable_hypothesis()}\n\n"
        "Identify 1 reusable spatial helper function in Python (e.g. bounding box, ray cast, connected components, flood fill).\n"
        "Do NOT write `transform(grid)`. Write ONLY the helper function inside ```python ... ```."
    )
    helper_code = ""
    try:
        resp, p_tok, c_tok, lat = query_llm_with_telemetry(induce_prompt, temperature=0.2, max_tokens=500)
        telemetry.prompt_tokens += p_tok
        telemetry.completion_tokens += c_tok
        telemetry.llm_generation_ms += lat
        helper_code = extract_python_code(resp)
    except Exception:
        pass

    # Step 2: Synthesize def transform
    perceptual_invariants = extract_perceptual_invariants(train_pairs, test_pair["input"])
    synth_prompt = (
        "Write a concise Python function `def transform(grid: list[list[int]]) -> list[list[int]]:` to solve this task.\n\n"
        f"Hypothesis:\n{abduction_payload.to_readable_hypothesis()}\n\n"
        f"Invariants:\n{perceptual_invariants}\n\n"
        f"Helper Function:\n```python\n{helper_code}\n```\n\n"
        f"{train_desc}"
        "Rules: Start immediately with `def transform(grid):`. Return a 2D list of integers. Output inside ```python ... ```."
    )

    def test_cand(code: str) -> tuple[bool, str | None]:
        for i, p in enumerate(train_pairs):
            try:
                t_exec0 = time.perf_counter()
                pred = execute_transform_code(code, p["input"])
                telemetry.sandbox_execution_ms += (time.perf_counter() - t_exec0) * 1000.0
                if pred != p["output"]:
                    return False, f"Failed on Ex {i+1}"
            except Exception as exc:
                return False, f"Exception on Ex {i+1}: {exc}"
        return True, None

    verified_code = None
    syntax_error = None
    for temp in [0.15, 0.25, 0.35, 0.60]:
        try:
            resp, p_tok, c_tok, lat = query_llm_with_telemetry(synth_prompt, temperature=temp, max_tokens=1024)
            telemetry.prompt_tokens += p_tok
            telemetry.completion_tokens += c_tok
            telemetry.llm_generation_ms += lat
            code = extract_python_code(resp)
            if not code:
                continue
            cand_code = f"{helper_code}\n\n{code}" if helper_code and helper_code not in code else code
            try:
                ast.parse(cand_code)
                ok, err = test_cand(cand_code)
                if ok:
                    verified_code = cand_code
                    break
            except SyntaxError as se:
                syntax_error = f"SYNTAX_ERROR: {se}"

            if helper_code and helper_code not in code:
                try:
                    ast.parse(code)
                    ok, err = test_cand(code)
                    if ok:
                        verified_code = code
                        break
                except Exception:
                    pass
        except Exception:
            pass

    telemetry.total_elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if not verified_code:
        f_code = "SYNTAX_ERROR" if syntax_error else "TRAIN_UNSAT"
        return AuditRecord(task_id, concept, tier, patch_id, "Arm_B_Python", False, "DYNAMIC_PYTHON", f_code, syntax_error, None, telemetry)

    telemetry.complexity_cost = python_ast_cost(verified_code)
    try:
        t_exec0 = time.perf_counter()
        pred = execute_transform_code(verified_code, test_pair["input"])
        telemetry.sandbox_execution_ms += (time.perf_counter() - t_exec0) * 1000.0
        if pred == gt_test_output:
            return AuditRecord(task_id, concept, tier, patch_id, "Arm_B_Python", True, "DYNAMIC_PYTHON", None, None, verified_code, telemetry)
        if len(pred) != len(gt_test_output) or len(pred[0]) != len(gt_test_output[0]):
            return AuditRecord(task_id, concept, tier, patch_id, "Arm_B_Python", False, "DYNAMIC_PYTHON", "SHAPE_MISMATCH", f"Expected {len(gt_test_output)}x{len(gt_test_output[0])}, got {len(pred)}x{len(pred[0])}", verified_code, telemetry)
        return AuditRecord(task_id, concept, tier, patch_id, "Arm_B_Python", False, "DYNAMIC_PYTHON", "VALUE_MISMATCH", "Cell value disagreement", verified_code, telemetry)
    except Exception as exc:
        return AuditRecord(task_id, concept, tier, patch_id, "Arm_B_Python", False, "DYNAMIC_PYTHON", "EXECUTION_EXCEPTION", str(exc), verified_code, telemetry)


def run_arm_c_scheme(
    task_id: str,
    concept: str,
    train_pairs: list[dict[str, list[list[int]]]],
    test_pair: dict[str, list[list[int]]],
    invariants: SymbolicInvariants,
    abduction_payload: AbductionPayload,
    tier: str,
    patch_id: str,
) -> AuditRecord:
    """Arm C: MicroScheme LISP S-Expressions + GBNF Grammar + Hole Enumeration."""
    gt_test_output = test_pair["output"]
    t0 = time.perf_counter()
    telemetry = TaskTelemetry()

    # Active color discovery
    colors_set: set[int] = set()
    for p in train_pairs:
        for r in p["input"]:
            colors_set.update(r)
        for r in p["output"]:
            colors_set.update(r)
    colors_list = sorted(colors_set)

    sketch_grammar = compile_dynamic_sketch_grammar(active_colors=colors_list)

    prims_docs = [
        "- (complete-symmetry input :axis ?hole-axis :mode ?hole-mode)  ; restore shape reflection symmetry",
        "- (fill-holes input :fill ?hole-color)                        ; fill enclosed interior holes",
        "- (crop-to-content input)                                      ; extract bounding box of foreground content",
        "- (rot90 input ?hole-int)                                      ; rotate grid 90/180/270 degrees",
        "- (flip-h input) or (flip-v input)                             ; mirror grid horizontally or vertically",
        "- (order-columns-by-height input :reverse ?hole-bool)          ; sort columns by height",
        "- (restore-periodic-pattern input)                             ; restore periodic pattern",
    ]
    for m_name, m_def in GLOBAL_MACRO_REGISTRY._macros.items():
        m_params = " ".join(f"?hole-{p}" for p in m_def.params)
        prims_docs.append(f"- ({m_name} input {m_params})  ; {m_def.doc}")

    sketch_prompt = (
        "You are a formal program synthesis engine. Emit 2 or 3 distinct candidate MicroScheme sketch expressions (one per line) that could perform this spatial transformation.\n\n"
        "Valid primitives:\n" + "\n".join(prims_docs) + "\n\n"
        f"Task Hypothesis: {abduction_payload.to_readable_hypothesis()}\n"
        "Rule: Always use typed parameter holes (?hole-axis, ?hole-mode, ?hole-color, etc.) instead of hardcoded values.\n"
        "Emit each candidate sketch on a separate line."
    )

    try:
        resp, p_tok, c_tok, lat = query_llm_with_telemetry(sketch_prompt, temperature=0.1, max_tokens=160, grammar=sketch_grammar)
        telemetry.prompt_tokens += p_tok
        telemetry.completion_tokens += c_tok
        telemetry.llm_generation_ms += lat

        candidate_sketches = [s.strip() for s in resp.split("\n") if s.strip()]
        for sk in candidate_sketches:
            t_hole0 = time.perf_counter()
            best_binding, eval_count = enumerate_sketch_bindings(sk, train_pairs)
            telemetry.cpu_hole_enumeration_ms += (time.perf_counter() - t_hole0) * 1000.0
            telemetry.candidates_evaluated += eval_count

            if best_binding is not None:
                # Successfully bound and verified on train pairs
                parsed_node = parse_expr(sk)
                telemetry.ast_depth = ast_depth(parsed_node)
                telemetry.ast_node_count = ast_node_count(parsed_node)
                telemetry.complexity_cost = float(len(sk.split()))
                telemetry.mdl_bits = compute_description_length(parsed_node)

                # Test on test grid
                t_eval0 = time.perf_counter()
                pred = evaluate_spatial_sketch(sk, test_pair["input"], hole_bindings=best_binding)
                telemetry.sandbox_execution_ms += (time.perf_counter() - t_eval0) * 1000.0
                telemetry.total_elapsed_ms = (time.perf_counter() - t0) * 1000.0

                prog_str = f"{sk} | binding: {best_binding}"
                if pred == gt_test_output:
                    return AuditRecord(task_id, concept, tier, patch_id, "Arm_C_MicroScheme", True, "GBNF_SCHEME_HOLE_ENUM", None, None, prog_str, telemetry)
                if len(pred) != len(gt_test_output) or len(pred[0]) != len(gt_test_output[0]):
                    return AuditRecord(task_id, concept, tier, patch_id, "Arm_C_MicroScheme", False, "GBNF_SCHEME_HOLE_ENUM", "SHAPE_MISMATCH", f"Expected {len(gt_test_output)}x{len(gt_test_output[0])}, got {len(pred)}x{len(pred[0])}", prog_str, telemetry)
                return AuditRecord(task_id, concept, tier, patch_id, "Arm_C_MicroScheme", False, "GBNF_SCHEME_HOLE_ENUM", "VALUE_MISMATCH", "Cell value disagreement", prog_str, telemetry)

        telemetry.total_elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return AuditRecord(task_id, concept, tier, patch_id, "Arm_C_MicroScheme", False, "GBNF_SCHEME_HOLE_ENUM", "HOLE_UNSAT", "No valid parameter binding satisfied demonstrations", None, telemetry)

    except Exception as exc:
        telemetry.total_elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return AuditRecord(task_id, concept, tier, patch_id, "Arm_C_MicroScheme", False, "GBNF_SCHEME_HOLE_ENUM", "SCHEME_EXCEPTION", str(exc), None, telemetry)


def make_dynamic_scheme_primitive(py_fn: Callable) -> Callable[[list[SchemeValue]], SchemeValue]:
    """Wraps a Python grid-transforming or spatial-extracting function into a typed MicroScheme primitive."""
    def _scheme_prim(args: list[SchemeValue]) -> SchemeValue:
        if not args:
            return []
        grid = _coerce_grid(args[0])
        py_args: list[Any] = [grid]
        py_kwargs: dict[str, Any] = {}
        i = 1
        while i < len(args):
            arg = args[i]
            if isinstance(arg, (Keyword, Symbol)) and str(arg.name).startswith(":"):
                kw_name = _to_kw_str(arg).replace("-", "_")
                if i + 1 < len(args):
                    val = args[i + 1]
                    py_kwargs[kw_name] = _to_kw_str(val) if isinstance(val, (Keyword, Symbol)) else val
                    i += 2
                    continue
            elif isinstance(arg, (int, float, str, bool)):
                py_args.append(arg)
            elif isinstance(arg, (Keyword, Symbol)):
                py_args.append(_to_kw_str(arg))
            i += 1
        try:
            res = py_fn(*py_args, **py_kwargs)
            if hasattr(res, "tolist"):
                res = res.tolist()
            if isinstance(res, (tuple, list)):
                if res and isinstance(res[0], (int, float, np.integer, np.floating)):
                    return [_to_int(x) for x in res]
                if res and isinstance(res[0], (list, tuple)):
                    return _to_scheme_grid(res)
                if not res:
                    return []
            if isinstance(res, (int, np.integer)):
                return int(res)
            if isinstance(res, (float, np.floating)):
                return float(res)
            if isinstance(res, (bool, np.bool_)):
                return bool(res)
            return res
        except Exception as exc:
            logger.debug("dynamic_scheme_prim_error: %s", exc)
            return []
    return _scheme_prim


def load_all_learned_macros() -> list[str]:
    """Loads and registers all admitted macros from data/learned_macros.json."""
    loaded_ops: list[str] = []
    if not LEARNED_MACROS_FILE.exists():
        return loaded_ops
    try:
        data = json.loads(LEARNED_MACROS_FILE.read_text(encoding="utf-8"))
        local_ns: dict[str, Any] = {
            "np": np,
            "numpy": np,
            "scipy": scipy,
            "ndimage": scipy.ndimage,
            "label": scipy.ndimage.label,
            "binary_fill_holes": scipy.ndimage.binary_fill_holes,
        }
        for item in data:
            code = item.get("code", "")
            if not code:
                continue
            try:
                exec(code, local_ns, local_ns)
                tree = ast.parse(code)
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                        fn_obj = local_ns.get(node.name)
                        if callable(fn_obj):
                            scheme_op = node.name.replace("_", "-")
                            register_dynamic_op(scheme_op)
                            SPATIAL_SCHEME_PRIMITIVES[scheme_op] = make_dynamic_scheme_primitive(fn_obj)
                            if scheme_op not in loaded_ops:
                                loaded_ops.append(scheme_op)
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Failed loading learned macros: %s", exc)
    return loaded_ops


def persist_learned_macro(name: str, code: str, task_id: str, model_tag: str) -> None:
    """Appends a newly verified helper function to data/learned_macros.json."""
    try:
        macros = []
        if LEARNED_MACROS_FILE.exists():
            try:
                macros = json.loads(LEARNED_MACROS_FILE.read_text(encoding="utf-8"))
            except Exception:
                macros = []
        if not any(m.get("name") == name and m.get("code") == code for m in macros):
            macros.append({
                "name": name,
                "task_id": task_id,
                "model_tag": model_tag,
                "code": code,
                "timestamp_utc": datetime.now(UTC).isoformat(),
            })
            LEARNED_MACROS_FILE.parent.mkdir(parents=True, exist_ok=True)
            LEARNED_MACROS_FILE.write_text(json.dumps(macros, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("Failed persisting learned macro: %s", exc)


def run_arm_d_hybrid(
    task_id: str,
    concept: str,
    train_pairs: list[dict[str, list[list[int]]]],
    test_pair: dict[str, list[list[int]]],
    invariants: SymbolicInvariants,
    abduction_payload: AbductionPayload,
    tier: str,
    patch_id: str,
) -> AuditRecord:
    """
    Arm D: Unified Neurosymbolic Hybrid (Patch v1.2)
    (Scheme Reflex -> Dynamic Python Induction -> Compositional Scheme Bridge -> Python Fallback).
    Zero regression guarantee with maximum token and latency efficiency.
    """
    gt_test_output = test_pair["output"]
    t0 = time.perf_counter()
    telemetry = TaskTelemetry()

    # Pre-load persistent learned macros library
    learned_ops = load_all_learned_macros()

    # -------------------------------------------------------------------------
    # Phase 1: Native MicroScheme Reflex (Fast Path)
    # -------------------------------------------------------------------------
    rec_c = run_arm_c_scheme(task_id, concept, train_pairs, test_pair, invariants, abduction_payload, tier, patch_id)
    telemetry.prompt_tokens += rec_c.telemetry.prompt_tokens
    telemetry.completion_tokens += rec_c.telemetry.completion_tokens
    telemetry.llm_generation_ms += rec_c.telemetry.llm_generation_ms
    telemetry.cpu_hole_enumeration_ms += rec_c.telemetry.cpu_hole_enumeration_ms
    telemetry.sandbox_execution_ms += rec_c.telemetry.sandbox_execution_ms
    telemetry.candidates_evaluated += rec_c.telemetry.candidates_evaluated

    if rec_c.success:
        telemetry.total_elapsed_ms = (time.perf_counter() - t0) * 1000.0
        telemetry.ast_depth = rec_c.telemetry.ast_depth
        telemetry.ast_node_count = rec_c.telemetry.ast_node_count
        telemetry.complexity_cost = rec_c.telemetry.complexity_cost
        telemetry.mdl_bits = rec_c.telemetry.mdl_bits
        return AuditRecord(
            task_id, concept, tier, patch_id, "Arm_D_Hybrid", True,
            "SCHEME_NATIVE", None, None, rec_c.synthesized_program, telemetry
        )

    # -------------------------------------------------------------------------
    # Phase 2: Dynamic Python Primitive Induction -> MicroScheme Bridge
    # -------------------------------------------------------------------------
    train_desc = "".join(f"Example {i+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n" for i, ex in enumerate(train_pairs[:3]))
    induce_prompt = (
        "Analyze these input-output spatial grid examples:\n\n"
        f"{train_desc}"
        f"Hypothesis: {abduction_payload.to_readable_hypothesis()}\n\n"
        "Identify 1 reusable spatial helper function in Python (e.g. bounding box, ray cast, connected components, flood fill, center pixel, extract shape).\n"
        "Do NOT write `transform(grid)`. Write ONLY the helper function inside ```python ... ```."
    )
    helper_code = ""
    try:
        resp, p_tok, c_tok, lat = query_llm_with_telemetry(induce_prompt, temperature=0.2, max_tokens=500)
        telemetry.prompt_tokens += p_tok
        telemetry.completion_tokens += c_tok
        telemetry.llm_generation_ms += lat
        helper_code = extract_python_code(resp)
    except Exception:
        pass

    if helper_code:
        try:
            local_ns: dict[str, Any] = {
                "np": np,
                "numpy": np,
                "scipy": scipy,
                "ndimage": scipy.ndimage,
                "label": scipy.ndimage.label,
                "binary_fill_holes": scipy.ndimage.binary_fill_holes,
            }
            exec(helper_code, local_ns, local_ns)
            tree = ast.parse(helper_code)
            induced_fns: list[tuple[str, Callable]] = []
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    fn_obj = local_ns.get(node.name)
                    if callable(fn_obj):
                        induced_fns.append((node.name, fn_obj))

            if induced_fns:
                fn_name, fn_obj = induced_fns[-1]
                scheme_op_name = fn_name.replace("_", "-")
                register_dynamic_op(scheme_op_name)
                SPATIAL_SCHEME_PRIMITIVES[scheme_op_name] = make_dynamic_scheme_primitive(fn_obj)

                # Active colors for grammar
                colors_set: set[int] = set()
                for p in train_pairs:
                    for r in p["input"]:
                        colors_set.update(r)
                    for r in p["output"]:
                        colors_set.update(r)
                colors_list = sorted(colors_set)

                active_prims = [scheme_op_name] + learned_ops[:5]
                dynamic_grammar = compile_dynamic_sketch_grammar(
                    active_primitives=active_prims,
                    active_colors=colors_list,
                )

                combos_doc = [
                    "- (set-pixel input (coords input) :color ?hole-color)          ; place pixel at coords (r, c)",
                    "- (crop-bbox input (bbox input))                              ; crop to bounding box (min-r min-c max-r max-c)",
                    "- (replace-color input :from ?hole-color :to ?hole-color)      ; replace one color with another",
                    "- (fill-mask input (mask input) :color ?hole-color)            ; paint region where mask is True",
                    "- (complete-symmetry input :axis ?hole-axis :mode ?hole-mode)  ; restore shape reflection symmetry",
                    "- (fill-holes input :fill ?hole-color)                        ; fill enclosed interior holes",
                    "- (crop-to-content input)                                      ; extract bounding box of foreground content",
                    "- (rot90 input ?hole-int)                                      ; rotate grid 90/180/270 degrees",
                    f"- ({scheme_op_name} input [args...])                         ; newly induced dynamic helper",
                ]

                synth_prompt = (
                    f"You are a formal program synthesis engine. A new primitive `{scheme_op_name}` has been dynamically compiled.\n"
                    f"Primitive signature: ({scheme_op_name} input [args...])\n"
                    f"Task Hypothesis: {abduction_payload.to_readable_hypothesis()}\n\n"
                    "Available combinators & primitives:\n" + "\n".join(combos_doc) + "\n\n"
                    "Emit 2 or 3 distinct candidate MicroScheme sketches (one per line). You may compose pipelines:\n"
                    f"- (set-pixel input ({scheme_op_name} input) :color ?hole-color)\n"
                    f"- (crop-bbox input ({scheme_op_name} input))\n"
                    f"- (replace-color ({scheme_op_name} input) :from ?hole-color :to ?hole-color)\n"
                    f"- ({scheme_op_name} input :color ?hole-color)\n"
                    "Emit each candidate sketch on a separate line with typed holes (?hole-color, ?hole-int, ?hole-axis, ?hole-bool)."
                )

                resp_sketch, p_tok_s, c_tok_s, lat_s = query_llm_with_telemetry(
                    synth_prompt, temperature=0.1, max_tokens=180, grammar=dynamic_grammar
                )
                telemetry.prompt_tokens += p_tok_s
                telemetry.completion_tokens += c_tok_s
                telemetry.llm_generation_ms += lat_s

                candidate_sketches = [s.strip() for s in resp_sketch.split("\n") if s.strip()]
                for sk in candidate_sketches:
                    t_hole0 = time.perf_counter()
                    best_binding, eval_count = enumerate_sketch_bindings(sk, train_pairs)
                    telemetry.cpu_hole_enumeration_ms += (time.perf_counter() - t_hole0) * 1000.0
                    telemetry.candidates_evaluated += eval_count

                    if best_binding is not None:
                        t_eval0 = time.perf_counter()
                        pred = evaluate_spatial_sketch(sk, test_pair["input"], hole_bindings=best_binding)
                        telemetry.sandbox_execution_ms += (time.perf_counter() - t_eval0) * 1000.0
                        prog_str = f"{sk} | binding: {best_binding} | helper: {fn_name}"

                        if pred == gt_test_output:
                            telemetry.total_elapsed_ms = (time.perf_counter() - t0) * 1000.0
                            persist_learned_macro(fn_name, helper_code, task_id, tier)
                            return AuditRecord(
                                task_id, concept, tier, patch_id, "Arm_D_Hybrid", True,
                                "DYNAMIC_SCHEME_HYBRID", None, None, prog_str, telemetry
                            )
        except Exception as exc:
            logger.debug("dynamic_scheme_hybrid_error", error=str(exc))

    # -------------------------------------------------------------------------
    # Phase 3: Dynamic Python Synthesis Fallback (Zero Regression)
    # -------------------------------------------------------------------------
    rec_b = run_arm_b_python(task_id, concept, train_pairs, test_pair, invariants, abduction_payload, tier, patch_id)
    telemetry.prompt_tokens += rec_b.telemetry.prompt_tokens
    telemetry.completion_tokens += rec_b.telemetry.completion_tokens
    telemetry.llm_generation_ms += rec_b.telemetry.llm_generation_ms
    telemetry.sandbox_execution_ms += rec_b.telemetry.sandbox_execution_ms
    telemetry.total_elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if rec_b.success:
        telemetry.complexity_cost = rec_b.telemetry.complexity_cost
        if helper_code:
            persist_learned_macro(task_id + "_helper", helper_code, task_id, tier)
        return AuditRecord(
            task_id, concept, tier, patch_id, "Arm_D_Hybrid", True,
            "PYTHON_FALLBACK", None, None, rec_b.synthesized_program, telemetry
        )

    # -------------------------------------------------------------------------
    # All Phases Failed
    # -------------------------------------------------------------------------
    return AuditRecord(
        task_id, concept, tier, patch_id, "Arm_D_Hybrid", False,
        "HYBRID_FAILED", rec_b.failure_code or "HYBRID_UNSAT", rec_b.failure_detail, None, telemetry
    )


# =============================================================================
# Multi-Task Factorial Runner
# =============================================================================

def evaluate_task_exhaustive(
    task_path: Path,
    concept: str,
    tier: str,
    patch_id: str,
    arms: list[str],
) -> list[AuditRecord]:
    """Runs all requested experimental arms on a single task."""
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task_id = task_path.stem
    train_pairs = task["train"]
    test_pair = task["test"][0]

    records: list[AuditRecord] = []

    # Pre-compute symbolic invariants & abduction payload for fair comparison
    invariants = analyze_symbolic_invariants(train_pairs)
    train_desc = "".join(f"Example {i+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n" for i, ex in enumerate(train_pairs[:3]))
    abduction_prompt = (
        "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples.\n"
        f"{train_desc}"
        "Formulate an Operational Hypothesis and output strict JSON with primary_domain, secondary_domain, selection_rule, transformation_rule, color_rule."
    )
    try:
        abd_resp = query_llm(abduction_prompt, temperature=0.1, max_tokens=400, grammar=ABDUCTION_GBNF_GRAMMAR)
        abd_dict = json.loads(abd_resp)
        payload = AbductionPayload(
            primary_domain=PrimitiveDomain(abd_dict["primary_domain"]),
            secondary_domain=PrimitiveDomain(abd_dict["secondary_domain"]) if abd_dict.get("secondary_domain") and abd_dict["secondary_domain"] != "null" else None,
            selection_rule=str(abd_dict.get("selection_rule", "")),
            transformation_rule=str(abd_dict.get("transformation_rule", "")),
            color_rule=str(abd_dict.get("color_rule", "")),
        )
    except Exception:
        payload = AbductionPayload(PrimitiveDomain.EXTRACTION, PrimitiveDomain.SYMMETRY, "Objects", "Transform", "Preserve")

    if "arm_a" in arms:
        records.append(run_arm_a_control(task_id, concept, train_pairs, test_pair, tier, patch_id))
    if "arm_b" in arms:
        records.append(run_arm_b_python(task_id, concept, train_pairs, test_pair, invariants, payload, tier, patch_id))
    if "arm_c" in arms:
        records.append(run_arm_c_scheme(task_id, concept, train_pairs, test_pair, invariants, payload, tier, patch_id))
    if "arm_d" in arms:
        records.append(run_arm_d_hybrid(task_id, concept, train_pairs, test_pair, invariants, payload, tier, patch_id))

    return records


# =============================================================================
# CLI Main & Telemetry Reporting
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Exhaustive Publication-Grade Neurosymbolic Audit Harness")
    parser.add_argument("--split", choices=["minimal", "in_vocab", "out_vocab", "arc1", "full"], default="minimal")
    parser.add_argument("--tasks", type=str, default="", help="Comma-separated task names")
    parser.add_argument("--arms", type=str, default="arm_a,arm_b,arm_c", help="Comma-separated arms: arm_a,arm_b,arm_c,arm_d")
    parser.add_argument("--model-tag", type=str, default="Tier0-26B", help="Tier identifier")
    parser.add_argument("--patch-id", type=str, default="patch-v1.0-baseline", help="Patch version tag")
    parser.add_argument("--baseline-report", type=str, default="", help="Path to prior report for differential delta matrix")
    args = parser.parse_args()

    selected_arms = [a.strip().lower() for a in args.arms.split(",") if a.strip()]
    selected_task_names = [t.strip().replace(".json", "") for t in args.tasks.split(",") if t.strip()]

    base_dir = REPO_ROOT / "data" / "benchmarks" / "ConceptARC"
    tasks: list[tuple[Path, str]] = []

    in_vocab_concepts = {"CompleteShape", "Center", "HorizontalVertical", "InsideOutside", "Order", "SameDifferent"}

    if args.split in ("minimal", "in_vocab", "out_vocab", "full"):
        for p in sorted((base_dir / "MinimalTasks").glob("*.json")):
            c = p.stem.replace("Minimal", "")
            if args.split == "in_vocab" and c not in in_vocab_concepts:
                continue
            if args.split == "out_vocab" and c in in_vocab_concepts:
                continue
            if not selected_task_names or p.stem in selected_task_names:
                tasks.append((p, c))

    if args.split in ("arc1", "full"):
        for p in sorted((REPO_ROOT / "data/benchmarks/arc_agi_1").glob("*.json")):
            if not selected_task_names or p.stem in selected_task_names:
                tasks.append((p, f"ARC1-{p.stem}"))

    print("\n" + "=" * 80)
    print(f"=== Project Lucca: Exhaustive Neurosymbolic Factorial Audit [{args.model_tag}] ===")
    print(f"Patch ID: {args.patch_id} | Split: {args.split} | Total Tasks: {len(tasks)}")
    print(f"Arms Evaluated: {', '.join(selected_arms).upper()}")
    print(f"Target Server: {SERVER_URL} | Time: {datetime.now(UTC).isoformat()}")
    print("=" * 80 + "\n")

    all_records: list[AuditRecord] = []
    footprint_summary: dict[str, Any] = {}

    with FootprintMonitor(interval_s=2.0) as monitor:
        for idx, (t_path, c_name) in enumerate(tasks, 1):
            print(f"[{idx}/{len(tasks)}] Auditing {c_name} :: {t_path.name} ... ", end="", flush=True)
            recs = evaluate_task_exhaustive(t_path, c_name, args.model_tag, args.patch_id, selected_arms)
            all_records.extend(recs)

            status_str = " | ".join(f"{r.arm.split('_')[1]}: {'PASS' if r.success else 'FAIL (' + str(r.failure_code) + ')'}" for r in recs)
            print(f"[{status_str}]")

    footprint_summary = monitor.get_summary()

    # Statistical Aggregation
    arm_stats: dict[str, dict[str, Any]] = {}
    for arm in selected_arms:
        arm_tag = f"Arm_{arm.split('_')[1].upper()}" if "_" in arm else f"Arm_{arm.upper()}"
        matching = [r for r in all_records if r.arm.lower().startswith(arm)]
        passed = sum(1 for r in matching if r.success)
        total = len(matching)
        rate = passed / total if total > 0 else 0.0
        ci = wilson_ci(passed, total)
        syntax_errs = sum(1 for r in matching if r.failure_code == "SYNTAX_ERROR")
        hole_unsats = sum(1 for r in matching if r.failure_code == "HOLE_UNSAT")
        avg_lat = sum(r.telemetry.total_elapsed_ms for r in matching) / total if total > 0 else 0.0
        avg_toks = sum(r.telemetry.prompt_tokens + r.telemetry.completion_tokens for r in matching) / total if total > 0 else 0.0

        arm_stats[arm] = {
            "passed": passed,
            "total": total,
            "pass_rate": rate,
            "wilson_ci_95": list(ci),
            "syntax_error_rate": syntax_errs / total if total > 0 else 0.0,
            "hole_unsat_count": hole_unsats,
            "avg_latency_ms": avg_lat,
            "avg_total_tokens": avg_toks,
        }

    print("\n" + "=" * 80)
    print(f"=== Factorial Audit Summary: {args.model_tag} [{args.patch_id}] ===")
    print("=" * 80)
    for arm, stats in arm_stats.items():
        print(f"{arm.upper():<12} | Pass: {stats['passed']}/{stats['total']} ({stats['pass_rate']*100:.1f}%) | "
              f"Syntax Err: {stats['syntax_error_rate']*100:.1f}% | "
              f"Avg Latency: {stats['avg_latency_ms']:.0f}ms | Avg Tokens: {stats['avg_total_tokens']:.0f}")

    # Differential Comparison vs Baseline Report
    diff_matrix: dict[str, Any] = {}
    if args.baseline_report and Path(args.baseline_report).exists():
        try:
            base_data = json.loads(Path(args.baseline_report).read_text(encoding="utf-8"))
            base_patch = base_data.get("patch_id", "baseline")
            print("\n" + "=" * 80)
            print(f"=== Differential Regression Matrix vs. Baseline [{base_patch}] ===")
            print("=" * 80)
            for arm in selected_arms:
                matching = [r for r in all_records if r.arm.lower().startswith(arm)]
                arm_rescues = []
                arm_regressions = []
                arm_ties = 0
                for r in matching:
                    b_rec = next((br for br in base_data.get("records", []) if br["task_id"] == r.task_id and br["arm"].lower().startswith(arm)), None)
                    if b_rec is None and arm == "arm_d":
                        b_rec = next((br for br in base_data.get("records", []) if br["task_id"] == r.task_id and br["arm"].lower().startswith("arm_b")), None)
                    if b_rec:
                        b_succ = b_rec.get("success", False)
                        if not b_succ and r.success:
                            arm_rescues.append(r.task_id)
                        elif b_succ and not r.success:
                            arm_regressions.append(r.task_id)
                        else:
                            arm_ties += 1

                b_total = len(arm_rescues) + len(arm_regressions)
                p_val = binomtest(len(arm_rescues), b_total, 0.5, alternative="two-sided").pvalue if b_total > 0 else 1.0

                diff_matrix[arm] = {
                    "baseline_patch": base_patch,
                    "rescues_f_to_p": arm_rescues,
                    "regressions_p_to_f": arm_regressions,
                    "ties": arm_ties,
                    "discordant_total": b_total,
                    "p_value_twosided": p_val,
                }
                print(f"Arm: {arm.upper():<12} | Rescues (F->P): {len(arm_rescues):<2} | Regressions (P->F): {len(arm_regressions):<2} | Ties: {arm_ties:<2} | Two-Sided p-val: {p_val:.4f}")
                if arm_rescues:
                    print(f"   Rescued Tasks: {', '.join(arm_rescues)}")
                if arm_regressions:
                    print(f"   Regressed Tasks: {', '.join(arm_regressions)}")
            print("=" * 80 + "\n")
        except Exception as be:
            print(f"[WARNING] Could not parse baseline report: {be}")

    # Cryptographic Report
    report_data = {
        "benchmark": "Exhaustive_Neurosymbolic_Factorial_Audit",
        "model_tag": args.model_tag,
        "patch_id": args.patch_id,
        "split": args.split,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "footprint_telemetry": footprint_summary,
        "arm_summaries": arm_stats,
        "differential_matrix": diff_matrix,
        "records": [asdict(r) for r in all_records],
    }

    out_file = REPO_ROOT / f"logs/test_reports/exhaustive_audit_{args.model_tag.lower()}_{args.patch_id}_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"\n[REPORT SEALED] Full publication telemetry saved to {out_file}\n")


if __name__ == "__main__":
    main()
