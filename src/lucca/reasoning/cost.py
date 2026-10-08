"""
Project Lucca — Idiomaticity Cost Extractor (Module 7, WO-30)
Evaluates MicroScheme AST structural complexity and Minimum Description Length (MDL).

Formula:
    Cost(T) = sum_{n in T} w(op_n) + alpha * depth(T)

Operator weights:
    w(primitive) = 1.0
    w(branch)    = 2.0 (if, cond, case, when, unless)
    w(macro_app) = 1.0
    alpha        = 0.5 (depth penalty)
"""

from __future__ import annotations

from typing import Final

from lucca.reasoning.scheme.macros import MacroDefinition
from lucca.reasoning.scheme.parser import (
    Keyword,
    SchemeAtom,
    SchemeNode,
    Symbol,
)

DEFAULT_ALPHA: Final[float] = 0.5
DEFAULT_PRIMITIVE_WEIGHT: Final[float] = 1.0
DEFAULT_BRANCH_WEIGHT: Final[float] = 2.0

BRANCHING_OPERATORS: Final[frozenset[str]] = frozenset({
    "if",
    "cond",
    "case",
    "when",
    "unless",
})


def ast_depth(node: SchemeNode) -> int:
    """
    Computes the maximum tree depth of a MicroScheme AST.
    Leaf atoms have depth 1. Nested expressions increment depth by 1.
    """
    if isinstance(node, list):
        if not node:
            return 1
        return 1 + max(ast_depth(child) for child in node)
    return 1


def ast_node_count(node: SchemeNode) -> int:
    """Computes total number of nodes (inner nodes and leaves) in an AST."""
    if isinstance(node, list):
        return 1 + sum(ast_node_count(child) for child in node)
    return 1


def get_operator_weight(
    op_name: str,
    custom_weights: dict[str, float] | None = None,
) -> float:
    """Resolves weight for an operator symbol."""
    if custom_weights is not None and op_name in custom_weights:
        return custom_weights[op_name]
    if op_name in BRANCHING_OPERATORS:
        return DEFAULT_BRANCH_WEIGHT
    return DEFAULT_PRIMITIVE_WEIGHT


def ast_cost(
    node: SchemeNode,
    alpha: float = DEFAULT_ALPHA,
    operator_weights: dict[str, float] | None = None,
) -> float:
    """
    Computes idiomaticity structural cost for a MicroScheme AST:
        Cost(T) = sum_{n in T} w(op_n) + alpha * depth(T)

    Favors shallow, concise, modular expressions over deeply nested
    or redundant expansions.
    """
    total_node_weight = 0.0

    def _accumulate_weights(curr: SchemeNode) -> None:
        nonlocal total_node_weight
        if isinstance(curr, list):
            if not curr:
                total_node_weight += DEFAULT_PRIMITIVE_WEIGHT
                return
            head = curr[0]
            if isinstance(head, Symbol):
                total_node_weight += get_operator_weight(head.name, operator_weights)
            elif isinstance(head, str):
                total_node_weight += get_operator_weight(head, operator_weights)
            else:
                total_node_weight += DEFAULT_PRIMITIVE_WEIGHT

            for child in curr[1:]:
                _accumulate_weights(child)
        elif isinstance(curr, (Symbol, Keyword, str, int, float, bool)):
            total_node_weight += DEFAULT_PRIMITIVE_WEIGHT

    _accumulate_weights(node)
    depth = ast_depth(node)
    return total_node_weight + (alpha * float(depth))


def compute_description_length(
    nodes: list[SchemeNode],
    alpha: float = DEFAULT_ALPHA,
) -> float:
    """Computes total description length for a sequence of expressions."""
    return sum(ast_cost(node, alpha=alpha) for node in nodes)


def compute_compression_savings(
    original_nodes: list[SchemeNode],
    macro_def: MacroDefinition,
    compressed_nodes: list[SchemeNode],
    alpha: float = DEFAULT_ALPHA,
) -> float:
    """
    Calculates Minimum Description Length (MDL) compression savings:
        OriginalCost = sum Cost(T_original)
        MacroDefCost = Cost(macro_body) + 1.0 (defmacro overhead) + 0.5 * num_params
        CompressedCost = MacroDefCost + sum Cost(T_compressed)
        Savings = OriginalCost - CompressedCost
    """
    original_cost = compute_description_length(original_nodes, alpha=alpha)
    macro_body_cost = ast_cost(macro_def.body, alpha=alpha)
    macro_overhead = 1.0 + (0.5 * len(macro_def.params))
    macro_def_cost = macro_body_cost + macro_overhead
    compressed_cost = macro_def_cost + compute_description_length(compressed_nodes, alpha=alpha)

    return original_cost - compressed_cost
