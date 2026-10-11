"""
Project Lucca — Boundary Topology Parser (Module 11, WO-31)
D-REAS-11, D-AUD-01, D-AUD-13

Validates MicroScheme AST sketches and candidate programs against:
1. Tool contracts (ToolSchema properties, parameter arity, and sandboxing).
2. State predicate topologies and allowed arity/type signatures.
3. Operator boundary topologies (primitives, spatial DSL, logical and arithmetic forms).
4. Unresolved holes and forbidden execution primitives (shell commands, unwhitelisted tools).

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import itertools
import re
import time
from typing import Final, cast

from pydantic import BaseModel, Field
import structlog

from lucca.core.schemas import ToolSchema
from lucca.reasoning.egraph import prune_equivalent_sketches
from lucca.reasoning.scheme.parser import (
    ALLOWED_OPS,
    STATE_PREDICATES,
    Keyword,
    SchemeAtom,
    SchemeNode,
    SchemeValue,
    Symbol,
    parse_expr,
    to_canonical,
)

logger = structlog.get_logger(__name__)

FORBIDDEN_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "bash",
        "sh",
        "cmd",
        "powershell",
        "pwsh",
        "exec",
        "system",
        "rm",
        "del",
        "format",
        "eval",
        "subprocess",
    }
)

ARITY_SPEC: Final[dict[str, tuple[int, int | None]]] = {
    # (min_args, max_args). None means unbounded.
    "say": (1, 1),
    "assert": (1, 1),
    "yield-to-core": (0, 0),
    "interrupt-core": (0, 0),
    "intent=": (1, 1),
    "entity-has?": (1, 2),
    "entity": (1, 1),
    "entity-int": (1, 1),
    "entity-num": (1, 1),
    "entity-str": (1, 1),
    "transcript-has?": (1, 1),
    "transcript-matches-glob?": (1, 1),
    "app-running?": (1, 1),
    "hour-between?": (2, 2),
    "weekday?": (0, 1),
    "last-tool-ok?": (0, 0),
    "last-tool=": (1, 1),
    "session-turns>=": (1, 1),
    "interrupted?": (0, 0),
    "fact-exists?": (1, 1),
    "fact-value": (1, 1),
    "not": (1, 1),
    "and": (1, None),
    "or": (1, None),
    "if": (2, 3),
    "+": (2, None),
    "-": (1, 2),
    "*": (2, None),
    "/": (2, 2),
    "=": (2, 2),
    "<": (2, 2),
    ">": (2, 2),
    "<=": (2, 2),
    ">=": (2, 2),
    "min": (2, None),
    "max": (2, None),
    "len": (1, 1),
    "str-contains?": (2, 2),
    "str-lower": (1, 1),
    "list": (0, None),
    # Spatial DSL primitives (Module 1)
    "point": (2, 2),
    "vec": (2, 2),
    "rect": (4, 4),
    "circle": (3, 3),
    "polygon": (1, None),
    "distance": (2, 2),
    "translate": (2, 2),
    "rotate": (2, 2),
    "scale": (2, 2),
    "bounding-box": (1, 1),
    "contains?": (2, 2),
    "intersects?": (2, 2),
    "intersect": (2, 2),
    "area": (1, 1),
    "perimeter": (1, 1),
    # Discrete 2D Spatial DSL primitives (WO-29 / WO-33)
    "find-objects": (1, 3),
    "count-objects": (1, 3),
    "dominant-object": (1, 1),
    "unique-colors": (1, 1),
    "order-columns-by-height": (1, 3),
    "column-heights": (1, 2),
    "row-widths": (1, 2),
    "sort-objects": (1, 3),
    "complete-symmetry": (1, 3),
    "rot90": (1, 2),
    "flip-h": (1, 1),
    "flip-v": (1, 1),
    "is-enclosed": (2, 3),
    "fill-holes": (1, 3),
    "flood-fill": (4, 5),
    "count-cells": (1, 2),
    "crop": (2, 5),
    "crop-to-content": (1, 2),
    "bbox-of-all": (1, 1),
    "paste": (3, 5),
    "move-until-contact": (3, 4),
    "draw-line": (5, 6),
    "majority-filter": (1, 2),
    "denoise": (1, 2),
}


class BoundaryViolationType(str, Enum):
    """Categorization of boundary contract breaches."""

    TOOL_NOT_FOUND = "tool_not_found"
    ARITY_MISMATCH = "arity_mismatch"
    ARGUMENT_TYPE_MISMATCH = "argument_type_mismatch"
    FORBIDDEN_OPERATOR = "forbidden_operator"
    PREDICATE_SIGNATURE_INVALID = "predicate_signature_invalid"
    SANDBOX_BOUNDARY_BREACH = "sandbox_boundary_breach"
    UNRESOLVED_HOLE = "unresolved_hole"


class BoundaryViolation(BaseModel):
    """Specific topology contract violation."""

    violation_type: BoundaryViolationType
    operator: str
    detail: str
    node_canonical: str


class TopologyValidationResult(BaseModel):
    """Result of validating an AST against boundary topology contracts."""

    is_valid: bool
    violations: list[BoundaryViolation] = Field(default_factory=list)
    hole_names: list[str] = Field(default_factory=list)


def is_hole_node(node: SchemeNode) -> bool:
    """Checks whether an AST node represents an unexpanded symbolic hole."""
    if isinstance(node, Symbol):
        name = node.name
        return (
            name.startswith("?hole")
            or name.startswith("??hole")
            or name.startswith("?var")
            or name.startswith("??var")
            or name.startswith("?h-")
            or name.startswith("?h_")
            or name.startswith("??h-")
            or name.startswith("??h_")
        )
    if isinstance(node, list) and len(node) >= 2:
        head = node[0]
        if isinstance(head, Symbol) and head.name in ("?hole", "hole", "?var", "??hole"):
            return True
    return False


def extract_hole_info(node: SchemeNode) -> tuple[str, str | None] | None:
    """Extracts (hole_name, hole_type) from a hole node."""
    if isinstance(node, Symbol):
        if is_hole_node(node):
            raw = node.name.strip("?")
            parts = re.split(r"[-_]", raw)
            h_type = parts[-1] if len(parts) > 1 and parts[-1] else None
            return node.name, h_type
    if isinstance(node, list) and len(node) >= 2:
        head = node[0]
        if isinstance(head, Symbol) and head.name in ("?hole", "hole", "?var", "??hole"):
            h_name = str(node[1].name if isinstance(node[1], Symbol) else node[1])
            h_type = (
                str(node[2].name if isinstance(node[2], Symbol) else node[2])
                if len(node) >= 3
                else None
            )
            return h_name, h_type
    return None


def extract_holes_from_ast(node: SchemeNode) -> list[tuple[str, str | None]]:
    """Traverses a MicroScheme AST and extracts unique (hole_name, hole_type) tuples."""
    holes: list[tuple[str, str | None]] = []

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


class BoundaryTopologyParser:
    """
    Parses and checks MicroScheme AST topology against registered tools,
    state predicates, typing boundaries, and sandboxing invariants.
    """

    def __init__(
        self,
        registered_tools: list[ToolSchema] | None = None,
        allowed_custom_macros: frozenset[str] | None = None,
    ) -> None:
        self.tool_map: dict[str, ToolSchema] = (
            {t.name: t for t in registered_tools} if registered_tools else {}
        )
        self.allowed_custom_macros: frozenset[str] = allowed_custom_macros or frozenset()

    def extract_holes(self, node: SchemeNode) -> list[tuple[str, str | None]]:
        """Finds all symbolic holes present in an AST."""
        holes: list[tuple[str, str | None]] = []

        def _walk(curr: SchemeNode) -> None:
            if is_hole_node(curr):
                info = extract_hole_info(curr)
                if info:
                    holes.append(info)
                return
            if isinstance(curr, list):
                for child in curr:
                    _walk(child)

        _walk(node)
        return holes

    def validate_ast(
        self,
        node: SchemeNode,
        allow_holes: bool = True,
    ) -> TopologyValidationResult:
        """
        Validates entire AST against tool schemas, predicate rules,
        arity specifications, and sandbox constraints.
        """
        violations: list[BoundaryViolation] = []
        found_holes: list[str] = []

        def _validate_node(curr: SchemeNode) -> None:
            # Check hole
            if is_hole_node(curr):
                info = extract_hole_info(curr)
                if info:
                    found_holes.append(info[0])
                if not allow_holes:
                    violations.append(
                        BoundaryViolation(
                            violation_type=BoundaryViolationType.UNRESOLVED_HOLE,
                            operator=info[0] if info else "?hole",
                            detail=f"Unresolved hole '{info[0] if info else '?hole'}' present in concrete program",
                            node_canonical=to_canonical(curr),
                        )
                    )
                return

            if not isinstance(curr, list) or not curr:
                return

            head = curr[0]
            if not isinstance(head, Symbol):
                # An expression starting without a Symbol operator
                violations.append(
                    BoundaryViolation(
                        violation_type=BoundaryViolationType.FORBIDDEN_OPERATOR,
                        operator=str(head),
                        detail=f"Head of expression must be a symbol, got {type(head).__name__}",
                        node_canonical=to_canonical(curr),
                    )
                )
                return

            op = head.name
            args = curr[1:]

            # 1. Tool Call Verification
            if op == "tool":
                self._validate_tool_call(curr, args, violations)
                for child in args:
                    _validate_node(child)
                return

            # 2. Operator Legality
            if (
                op not in ALLOWED_OPS
                and op not in self.allowed_custom_macros
                and not op.startswith("?")
            ):
                violations.append(
                    BoundaryViolation(
                        violation_type=BoundaryViolationType.FORBIDDEN_OPERATOR,
                        operator=op,
                        detail=f"Disallowed operator or undeclared primitive '{op}'",
                        node_canonical=to_canonical(curr),
                    )
                )

            # 3. Arity Verification
            if op in ARITY_SPEC:
                min_a, max_a = ARITY_SPEC[op]
                arg_count = len(args)
                if arg_count < min_a or (max_a is not None and arg_count > max_a):
                    violations.append(
                        BoundaryViolation(
                            violation_type=BoundaryViolationType.ARITY_MISMATCH,
                            operator=op,
                            detail=f"Operator '{op}' expects {min_a}..{max_a} arguments, got {arg_count}",
                            node_canonical=to_canonical(curr),
                        )
                    )

            # 4. State Predicate Signature
            if op in STATE_PREDICATES:
                self._validate_state_predicate(op, args, curr, violations)

            # 5. Type Consistency for Static Term Literals
            self._validate_literal_types(op, args, curr, violations)

            # Recursively validate children
            for child in args:
                _validate_node(child)

        _validate_node(node)
        return TopologyValidationResult(
            is_valid=len(violations) == 0,
            violations=violations,
            hole_names=found_holes,
        )

    def _validate_tool_call(
        self,
        node: SchemeNode,
        args: list[SchemeNode],
        violations: list[BoundaryViolation],
    ) -> None:
        """Validates (tool <name> ...) form against tool contracts."""
        if not args:
            violations.append(
                BoundaryViolation(
                    violation_type=BoundaryViolationType.ARITY_MISMATCH,
                    operator="tool",
                    detail="Form (tool) requires at least a tool name argument",
                    node_canonical=to_canonical(node),
                )
            )
            return

        tool_name_node = args[0]
        if isinstance(tool_name_node, Symbol):
            t_name = tool_name_node.name
        elif isinstance(tool_name_node, str):
            t_name = tool_name_node
        else:
            violations.append(
                BoundaryViolation(
                    violation_type=BoundaryViolationType.ARGUMENT_TYPE_MISMATCH,
                    operator="tool",
                    detail=f"Tool name must be symbol or string, got {type(tool_name_node).__name__}",
                    node_canonical=to_canonical(node),
                )
            )
            return

        # Check forbidden names
        if t_name.lower() in FORBIDDEN_TOOL_NAMES:
            violations.append(
                BoundaryViolation(
                    violation_type=BoundaryViolationType.SANDBOX_BOUNDARY_BREACH,
                    operator="tool",
                    detail=f"Direct shell/system tool '{t_name}' is strictly forbidden by sandbox boundary policy",
                    node_canonical=to_canonical(node),
                )
            )
            return

        # Check registered tools if any are registered
        if self.tool_map and t_name not in self.tool_map:
            violations.append(
                BoundaryViolation(
                    violation_type=BoundaryViolationType.TOOL_NOT_FOUND,
                    operator="tool",
                    detail=f"Tool '{t_name}' is not registered in the active tool manifest",
                    node_canonical=to_canonical(node),
                )
            )

    def _validate_state_predicate(
        self,
        op: str,
        args: list[SchemeNode],
        node: SchemeNode,
        violations: list[BoundaryViolation],
    ) -> None:
        """Validates state predicate arguments."""
        if op == "hour-between?" and len(args) == 2:
            a1, a2 = args[0], args[1]
            if isinstance(a1, (int, float)) and isinstance(a2, (int, float)):
                if not (0 <= a1 <= 24 and 0 <= a2 <= 24):
                    violations.append(
                        BoundaryViolation(
                            violation_type=BoundaryViolationType.PREDICATE_SIGNATURE_INVALID,
                            operator=op,
                            detail=f"hour-between? arguments must be hours within [0, 24], got {a1}, {a2}",
                            node_canonical=to_canonical(node),
                        )
                    )

    def _validate_literal_types(
        self,
        op: str,
        args: list[SchemeNode],
        node: SchemeNode,
        violations: list[BoundaryViolation],
    ) -> None:
        """Validates argument types for static literals."""
        if op in ("+", "-", "*", "/"):
            for idx, a in enumerate(args):
                if isinstance(a, (str, bool)):
                    violations.append(
                        BoundaryViolation(
                            violation_type=BoundaryViolationType.ARGUMENT_TYPE_MISMATCH,
                            operator=op,
                            detail=f"Arithmetic operator '{op}' received non-numeric literal '{a}' at position {idx}",
                            node_canonical=to_canonical(node),
                        )
                    )
        elif op in ("point", "vec") and len(args) == 2:
            for idx, a in enumerate(args):
                if isinstance(a, (str, bool)):
                    violations.append(
                        BoundaryViolation(
                            violation_type=BoundaryViolationType.ARGUMENT_TYPE_MISMATCH,
                            operator=op,
                            detail=f"Geometric operator '{op}' requires numeric coordinates, got literal '{a}' at position {idx}",
                            node_canonical=to_canonical(node),
                        )
                    )

    def check_safe_to_execute(self, node: SchemeNode) -> bool:
        """
        Fast boolean preflight check: True if AST has zero violations
        and no unresolved holes.
        """
        result = self.validate_ast(node, allow_holes=False)
        return result.is_valid


@dataclass(frozen=True)
class HoleEnumerationResult:
    """Result of enumerating and verifying candidate hole bindings."""

    best_binding: dict[str, SchemeValue] | None
    evaluated_count: int
    pruned_count: int
    coverage_rate: float
    ranked_bindings: list[tuple[dict[str, SchemeValue], float]]
    latency_ms: float


def instantiate_hole_ast(node: SchemeNode, bindings: dict[str, SchemeValue]) -> SchemeNode:
    """Recursively replaces hole symbols with bound Scheme values."""
    if is_hole_node(node):
        info = extract_hole_info(node)
        if info:
            h_name = info[0]
            if h_name in bindings:
                b_val = bindings[h_name]
                if isinstance(b_val, (int, float, bool, str, Keyword, Symbol)):
                    return b_val
                if isinstance(b_val, list):
                    return cast(SchemeNode, b_val)
    if isinstance(node, list):
        return [instantiate_hole_ast(child, bindings) for child in node]
    return node


def enumerate_hole_bindings(
    sketch: SchemeNode | str,
    eval_fn: Callable[[SchemeNode, SchemeValue, dict[str, SchemeValue]], SchemeValue],
    demos: list[tuple[SchemeValue, SchemeValue]],
    candidate_domains: dict[str, list[SchemeValue]] | None = None,
    max_candidates: int = 200,
    use_egraph_pruning: bool = True,
) -> HoleEnumerationResult:
    """
    Given a MicroScheme sketch with typed parameter holes and demonstration pairs,
    enumerates candidate parameter bindings and evaluates them on host CPU.
    Uses E-Graph equivalence to collapse redundant candidate ASTs before evaluation.
    """
    t0 = time.perf_counter()
    if isinstance(sketch, str):
        node = parse_expr(sketch)
    else:
        node = sketch

    holes = extract_holes_from_ast(node)
    if not holes:
        all_passed = True
        passed_demos = 0
        for inp, expected in demos:
            try:
                out = eval_fn(node, inp, {})
                if out == expected:
                    passed_demos += 1
                else:
                    all_passed = False
            except Exception as exc:
                logger.debug("hole_eval_direct_failed", error=str(exc))
                all_passed = False
        cov = (passed_demos / len(demos)) if demos else 1.0
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        best: dict[str, SchemeValue] | None = {} if all_passed else None
        return HoleEnumerationResult(
            best_binding=best,
            evaluated_count=1,
            pruned_count=0,
            coverage_rate=cov if all_passed else 0.0,
            ranked_bindings=[({}, cov)] if all_passed else [],
            latency_ms=elapsed_ms,
        )

    domain_per_hole: list[list[SchemeValue]] = []
    hole_names: list[str] = []
    custom_domains = candidate_domains or {}

    for name, h_type in holes:
        hole_names.append(name)
        if name in custom_domains:
            domain_per_hole.append(custom_domains[name])
            continue
        t = (h_type or "").lower()
        if t in custom_domains:
            domain_per_hole.append(custom_domains[t])
        elif "axis" in t:
            domain_per_hole.append(["both", "auto", "h", "v"])
        elif "mode" in t:
            domain_per_hole.append(["auto", "bbox", "canvas"])
        elif "conn" in t:
            domain_per_hole.append([4, 8])
        elif "bool" in t:
            domain_per_hole.append([True, False])
        elif "color" in t:
            domain_per_hole.append([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        elif "int" in t:
            domain_per_hole.append([0, 1, 2, 3])
        elif "key" in t:
            domain_per_hole.append([Keyword(":height"), Keyword(":width"), Keyword(":area"), Keyword(":min-r"), Keyword(":min-c")])
        else:
            domain_per_hole.append(["h", "v", 4, 8, 0, 1, True, False])

    all_combos = list(itertools.product(*domain_per_hole))
    total_unpruned = len(all_combos)
    if total_unpruned > max_candidates:
        all_combos = all_combos[:max_candidates]

    pruned_count = 0
    candidate_list: list[tuple[dict[str, SchemeValue], SchemeNode]] = []
    for combo in all_combos:
        binding: dict[str, SchemeValue] = dict(zip(hole_names, combo, strict=True))
        inst_node = instantiate_hole_ast(node, binding)
        candidate_list.append((binding, inst_node))

    if use_egraph_pruning and len(candidate_list) > 1:
        ast_nodes = [item[1] for item in candidate_list]
        deduped_asts = prune_equivalent_sketches(ast_nodes)
        deduped_set = {to_canonical(d) for d in deduped_asts}
        pruned_candidates = [
            item for item in candidate_list if to_canonical(item[1]) in deduped_set
        ]
        pruned_count = len(candidate_list) - len(pruned_candidates)
        candidate_list = pruned_candidates

    ranked_results: list[tuple[dict[str, SchemeValue], float]] = []
    evaluated_count = 0
    best_binding: dict[str, SchemeValue] | None = None
    best_coverage = 0.0

    for binding, inst_node in candidate_list:
        evaluated_count += 1
        passed_demos = 0
        all_passed = True
        for inp, expected in demos:
            try:
                out = eval_fn(inst_node, inp, binding)
                if out == expected:
                    passed_demos += 1
                else:
                    all_passed = False
            except Exception as exc:
                logger.debug("hole_eval_candidate_failed", error=str(exc))
                all_passed = False

        coverage = (passed_demos / len(demos)) if demos else 0.0
        if coverage > 0.0:
            ranked_results.append((binding, coverage))

        if all_passed:
            best_binding = binding
            best_coverage = 1.0
            break
        elif coverage > best_coverage:
            best_coverage = coverage
            best_binding = binding

    ranked_results.sort(key=lambda x: -x[1])
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return HoleEnumerationResult(
        best_binding=best_binding if best_coverage == 1.0 else None,
        evaluated_count=evaluated_count,
        pruned_count=pruned_count,
        coverage_rate=best_coverage,
        ranked_bindings=ranked_results,
        latency_ms=elapsed_ms,
    )
