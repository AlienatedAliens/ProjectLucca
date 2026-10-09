"""
Project Lucca — Backward Abduction Solver (Module 15, WO-31)
D-REAS-11, D-AUD-01

Deduces candidate hole fillings and required preconditions by working backwards
from target postconditions and goal invariant assertions.

Capabilities:
1. Goal postcondition inversion (arithmetic, relational, spatial, and predicate assertions).
2. Algebraic inverse operators (+ <-> -, * <-> /) for parameter deduction.
3. Precondition derivation for rule and tool invocations.
4. Generates ranked AbductiveHypothesis proposals to guide MCTS expansion.

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, Field
import structlog

from lucca.reasoning.cost import ast_cost
from lucca.reasoning.scheme.eval import SchemeEvaluator
from lucca.reasoning.scheme.parser import (
    ALLOWED_OPS,
    Keyword,
    SchemeAtom,
    SchemeNode,
    Symbol,
    parse_expr,
    to_canonical,
)
from lucca.reasoning.scheme.prims import PURE_PRIMITIVES
from lucca.reasoning.topology import extract_hole_info, is_hole_node

logger = structlog.get_logger(__name__)


class AbductiveHypothesis(BaseModel):
    """A proposed candidate filling for an open hole derived via backward abduction."""

    hole_name: str
    candidate_expr: str
    preconditions: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    heuristic_rank: int = 0
    derivation_rationale: str = ""


def _eval_pure_safe(node: SchemeNode) -> SchemeAtom | None:
    """Safely evaluates a pure MicroScheme node, returning None on failure."""
    evaluator = SchemeEvaluator(gas_limit=500, timeout_ms=50.0)
    try:
        val = evaluator.eval(node, PURE_PRIMITIVES)
        if isinstance(val, (int, float, bool, str, Keyword)):
            return val
        return None
    except Exception as exc:
        logger.debug("eval_pure_safe_failed", error=str(exc))
        return None


def _find_hole_in_ast(node: SchemeNode, target_hole: str) -> bool:
    """Checks if target_hole is present anywhere in node."""
    if is_hole_node(node):
        info = extract_hole_info(node)
        return bool(info and info[0] == target_hole)
    if isinstance(node, list):
        return any(_find_hole_in_ast(child, target_hole) for child in node)
    return False


def _substitute_hole(
    node: SchemeNode,
    hole_name: str,
    replacement: SchemeNode,
) -> SchemeNode:
    """Substitutes all occurrences of hole_name with replacement node."""
    if is_hole_node(node):
        info = extract_hole_info(node)
        if info and info[0] == hole_name:
            return copy.deepcopy(replacement)
        return node
    if isinstance(node, list):
        return [_substitute_hole(child, hole_name, replacement) for child in node]
    return node


class BackwardAbductionSolver:
    """
    Solves backward abductive inferences from target goals to candidate hole fillings.
    """

    def __init__(self, max_hypotheses_per_hole: int = 16) -> None:
        self.max_hypotheses_per_hole = max_hypotheses_per_hole

    def derive_preconditions(self, target_postcondition: SchemeNode) -> list[SchemeNode]:
        """
        Derives required preconditions from a target postcondition.
        For example:
        (assert (user location "Tokyo")) -> [(fact-exists? ("user" "location" "Tokyo"))]
        (say ...) -> [(intent= ...)]
        """
        preconds: list[SchemeNode] = []
        if isinstance(target_postcondition, list) and target_postcondition:
            head = target_postcondition[0]
            if isinstance(head, Symbol):
                op = head.name
                if op == "assert" and len(target_postcondition) > 1:
                    fact_pattern = target_postcondition[1]
                    preconds.append([Symbol("fact-exists?"), fact_pattern])
                elif op == "say" and len(target_postcondition) > 1:
                    preconds.append([Symbol("intent="), "conversation"])
                elif op == "tool" and len(target_postcondition) > 1:
                    t_name = target_postcondition[1]
                    preconds.append([Symbol("intent="), t_name])
        return preconds

    def invert_algebraic_step(
        self,
        op: str,
        target_val: int | float,
        known_arg: int | float,
        hole_is_first: bool,
    ) -> int | float | None:
        """
        Inverts a 2-argument arithmetic operator:
        op == "+": a + b = T => unknown = T - known
        op == "*": a * b = T => unknown = T / known (if known != 0)
        op == "-":
          hole - known = T => hole = T + known (hole_is_first == True)
          known - hole = T => hole = known - T (hole_is_first == False)
        op == "/":
          hole / known = T => hole = T * known (hole_is_first == True, known != 0)
          known / hole = T => hole = known / T (hole_is_first == False, T != 0)
        """
        try:
            if op == "+":
                return target_val - known_arg
            elif op == "*":
                if known_arg != 0:
                    res = target_val / known_arg
                    return int(res) if res.is_integer() else res
            elif op == "-":
                if hole_is_first:
                    return target_val + known_arg
                else:
                    return known_arg - target_val
            elif op == "/":
                if hole_is_first:
                    res = target_val * known_arg
                    return int(res) if isinstance(res, float) and res.is_integer() else res
                else:
                    if target_val != 0:
                        res = known_arg / target_val
                        return int(res) if res.is_integer() else res
        except (ZeroDivisionError, OverflowError):
            return None
        return None

    def invert_goal_for_sketch(
        self,
        sketch: SchemeNode,
        target_val: int | float | str | bool,
        hole_name: str,
    ) -> list[AbductiveHypothesis]:
        """
        Attempts to invert an AST sketch containing a single open hole `hole_name`
        such that eval(sketch[hole -> candidate]) == target_val.
        """
        hypotheses: list[AbductiveHypothesis] = []

        # Case 0: The sketch IS the hole itself: (?hole h) -> target_val
        if is_hole_node(sketch):
            info = extract_hole_info(sketch)
            if info and info[0] == hole_name:
                cand_str = (
                    f'"{target_val}"'
                    if isinstance(target_val, str)
                    else ("#t" if target_val is True else ("#f" if target_val is False else str(target_val)))
                )
                hypotheses.append(
                    AbductiveHypothesis(
                        hole_name=hole_name,
                        candidate_expr=cand_str,
                        confidence=1.0,
                        heuristic_rank=1,
                        derivation_rationale=f"Direct goal equivalence: {hole_name} = {target_val}",
                    )
                )
                return hypotheses

        # Case 1: Binary / N-ary operation with one hole and known other args
        if isinstance(sketch, list) and len(sketch) >= 3:
            head = sketch[0]
            if isinstance(head, Symbol) and head.name in ("+", "-", "*", "/"):
                op = head.name
                # Check for 2-argument operation
                if len(sketch) == 3 and isinstance(target_val, (int, float)):
                    arg1, arg2 = sketch[1], sketch[2]
                    h1_has = _find_hole_in_ast(arg1, hole_name)
                    h2_has = _find_hole_in_ast(arg2, hole_name)

                    if h1_has and not h2_has:
                        val2 = _eval_pure_safe(arg2)
                        if isinstance(val2, (int, float)):
                            solved = self.invert_algebraic_step(
                                op, target_val, val2, hole_is_first=True
                            )
                            if solved is not None:
                                # Recursively invert sub-expression if arg1 is not directly the hole
                                if is_hole_node(arg1):
                                    hypotheses.append(
                                        AbductiveHypothesis(
                                            hole_name=hole_name,
                                            candidate_expr=str(solved),
                                            confidence=0.95,
                                            heuristic_rank=1,
                                            derivation_rationale=f"Inverted {op} with {val2}: {solved}",
                                        )
                                    )
                                else:
                                    sub_hyps = self.invert_goal_for_sketch(
                                        arg1, solved, hole_name
                                    )
                                    hypotheses.extend(sub_hyps)

                    elif h2_has and not h1_has:
                        val1 = _eval_pure_safe(arg1)
                        if isinstance(val1, (int, float)):
                            solved = self.invert_algebraic_step(
                                op, target_val, val1, hole_is_first=False
                            )
                            if solved is not None:
                                if is_hole_node(arg2):
                                    hypotheses.append(
                                        AbductiveHypothesis(
                                            hole_name=hole_name,
                                            candidate_expr=str(solved),
                                            confidence=0.95,
                                            heuristic_rank=1,
                                            derivation_rationale=f"Inverted {op} with {val1}: {solved}",
                                        )
                                    )
                                else:
                                    sub_hyps = self.invert_goal_for_sketch(
                                        arg2, solved, hole_name
                                    )
                                    hypotheses.extend(sub_hyps)

        # Case 2: Fact assertion / Intent inversion
        if isinstance(sketch, list) and sketch:
            head = sketch[0]
            if isinstance(head, Symbol) and head.name == "assert":
                # (assert (?hole h)) -> target is a fact triple
                if len(sketch) == 2 and is_hole_node(sketch[1]):
                    info = extract_hole_info(sketch[1])
                    if info and info[0] == hole_name and isinstance(target_val, str):
                        hypotheses.append(
                            AbductiveHypothesis(
                                hole_name=hole_name,
                                candidate_expr=target_val,
                                confidence=0.9,
                                heuristic_rank=1,
                                derivation_rationale="Asserted fact triple goal inversion",
                            )
                        )

        # Always add direct literal target as baseline hypothesis if suitable
        if isinstance(target_val, (int, float, str, bool)):
            direct_cand = (
                f'"{target_val}"'
                if isinstance(target_val, str)
                else ("#t" if target_val is True else ("#f" if target_val is False else str(target_val)))
            )
            if not any(h.candidate_expr == direct_cand for h in hypotheses):
                hypotheses.append(
                    AbductiveHypothesis(
                        hole_name=hole_name,
                        candidate_expr=direct_cand,
                        confidence=0.7,
                        heuristic_rank=len(hypotheses) + 1,
                        derivation_rationale=f"Fallback direct target: {direct_cand}",
                    )
                )

        return hypotheses[: self.max_hypotheses_per_hole]

    def propose_candidates_for_all_holes(
        self,
        sketch: SchemeNode,
        target_val: int | float | str | bool,
        holes: list[tuple[str, str | None]],
    ) -> dict[str, list[AbductiveHypothesis]]:
        """Proposes hypotheses for each open hole present in the sketch."""
        results: dict[str, list[AbductiveHypothesis]] = {}
        for h_name, _ in holes:
            hyps = self.invert_goal_for_sketch(sketch, target_val, h_name)
            results[h_name] = hyps
        return results
