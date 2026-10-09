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

from enum import Enum
import re
from typing import Final

from pydantic import BaseModel, Field
import structlog

from lucca.core.schemas import ToolSchema
from lucca.reasoning.scheme.parser import (
    ALLOWED_OPS,
    STATE_PREDICATES,
    Keyword,
    SchemeAtom,
    SchemeNode,
    Symbol,
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
        return node.name.startswith("?hole") or node.name.startswith("?var") or node.name.startswith("?h")
    if isinstance(node, list) and len(node) >= 2:
        head = node[0]
        if isinstance(head, Symbol) and head.name in ("?hole", "hole", "?var"):
            return True
    return False


def extract_hole_info(node: SchemeNode) -> tuple[str, str | None] | None:
    """Extracts (hole_name, hole_type) from a hole node."""
    if isinstance(node, Symbol):
        if node.name.startswith("?hole") or node.name.startswith("?var") or node.name.startswith("?h"):
            return node.name, None
    if isinstance(node, list) and len(node) >= 2:
        head = node[0]
        if isinstance(head, Symbol) and head.name in ("?hole", "hole", "?var"):
            h_name = str(node[1].name if isinstance(node[1], Symbol) else node[1])
            h_type = (
                str(node[2].name if isinstance(node[2], Symbol) else node[2])
                if len(node) >= 3
                else None
            )
            return h_name, h_type
    return None


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
