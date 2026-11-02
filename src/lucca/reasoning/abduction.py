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
import math
import threading
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, Field
import structlog
import z3

_Z3_LOCK = threading.Lock()

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

    def _ast_to_z3(
        self,
        node: SchemeNode,
        hole_vars: dict[str, z3.ArithRef],
        input_env: dict[str, int | float],
        solver: z3.Solver,
    ) -> z3.ArithRef | None:
        """Translates a MicroScheme arithmetic AST with holes and input variables into a Z3 term."""
        if is_hole_node(node):
            info = extract_hole_info(node)
            if info and info[0] in hole_vars:
                return hole_vars[info[0]]
            return None
        if isinstance(node, bool):
            return z3.IntVal(1 if node else 0)
        if isinstance(node, int):
            return z3.IntVal(node)
        if isinstance(node, float):
            if node.is_integer():
                return z3.IntVal(int(node))
            return None
        if isinstance(node, Symbol):
            name = node.name
            if name in hole_vars:
                return hole_vars[name]
            if name in input_env:
                v = input_env[name]
                return z3.IntVal(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else None
            return None
        if isinstance(node, str):
            if node in input_env:
                v = input_env[node]
                return z3.IntVal(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else None
            return None
        if isinstance(node, list) and len(node) >= 2:
            head = node[0]
            op = head.name if isinstance(head, Symbol) else (head if isinstance(head, str) else "")
            sub_terms: list[z3.ArithRef] = []
            for child in node[1:]:
                t = self._ast_to_z3(child, hole_vars, input_env, solver)
                if t is None:
                    return None
                sub_terms.append(t)
            if not sub_terms:
                return None
            if op == "+":
                acc = sub_terms[0]
                for st in sub_terms[1:]:
                    acc = acc + st
                return acc
            if op == "-":
                if len(sub_terms) == 1:
                    return -sub_terms[0]
                acc = sub_terms[0]
                for st in sub_terms[1:]:
                    acc = acc - st
                return acc
            if op == "*":
                acc = sub_terms[0]
                for st in sub_terms[1:]:
                    acc = acc * st
                return acc
            if op == "/" and len(sub_terms) == 2:
                solver.add(sub_terms[1] != 0)
                return sub_terms[0] / sub_terms[1]
        return None

    def solve_holes_z3(
        self,
        sketch: SchemeNode,
        holes: list[tuple[str, str | None]],
        target_val: int | float | str | bool = 0,
        test_cases: list[dict[str, object]] | None = None,
    ) -> dict[str, list[AbductiveHypothesis]]:
        """Uses Z3 constraint solving to deduce hole expressions consistent across all test cases."""
        results: dict[str, list[AbductiveHypothesis]] = {h[0]: [] for h in holes}
        if not holes:
            return results

        # 1. Try solving for constant integer hole values that satisfy ALL test_cases (or compound sketch)
        if test_cases:
            with _Z3_LOCK:
                return self._solve_holes_z3_locked(sketch, holes, target_val, test_cases, results)
        return results

    def _solve_holes_z3_locked(
        self,
        sketch: SchemeNode,
        holes: list[tuple[str, str | None]],
        target_val: int | float | str | bool,
        test_cases: list[dict[str, object]],
        results: dict[str, list[AbductiveHypothesis]],
    ) -> dict[str, list[AbductiveHypothesis]]:
        if test_cases:
            solver = z3.Solver()
            solver.set("timeout", 200)
            hole_vars = {h[0]: z3.Int(f"hole_{h[0]}") for h in holes}
            valid_encoding = True
            for tc in test_cases:
                raw_in = tc.get("inputs", tc.get("input", {}))
                in_dict: dict[str, int | float] = {}
                if isinstance(raw_in, dict):
                    for k, v in raw_in.items():
                        if isinstance(v, (int, float)):
                            in_dict[str(k)] = v
                elif isinstance(raw_in, (int, float)):
                    in_dict = {"x": raw_in, "n": raw_in}
                exp_out = tc.get("output", tc.get("expected", tc.get("expected_output")))
                if not isinstance(exp_out, (int, float)) or not float(exp_out).is_integer():
                    valid_encoding = False
                    break
                term = self._ast_to_z3(sketch, hole_vars, in_dict, solver)
                if term is None:
                    valid_encoding = False
                    break
                solver.add(term == int(exp_out))

            # Reject bare-hole constant solution if outputs vary across test cases
            outputs_set = {
                tc.get("output", tc.get("expected", tc.get("expected_output")))
                for tc in test_cases
            }
            if valid_encoding and not (is_hole_node(sketch) and len(outputs_set) >= 1):
                if solver.check() == z3.sat:
                    model = solver.model()
                    for h_name, z_var in hole_vars.items():
                        val = model.eval(z_var, model_completion=True)
                        if val is not None and hasattr(val, "as_long"):
                            c_str = str(val.as_long())
                            results[h_name].append(
                                AbductiveHypothesis(
                                    hole_name=h_name,
                                    candidate_expr=c_str,
                                    confidence=0.98,
                                    heuristic_rank=1,
                                    derivation_rationale=f"Z3 multi-case constant solution: {h_name} = {c_str}",
                                )
                            )

            # 2. Try solving each hole as a linear/quadratic symbolic expression over input vars via Z3
            first_in = test_cases[0].get("inputs", test_cases[0].get("input", {}))
            var_names: list[str] = []
            if isinstance(first_in, dict):
                var_names = [str(k) for k, v in first_in.items() if isinstance(v, (int, float))]
            elif isinstance(first_in, (int, float)):
                var_names = ["x"]

            if var_names and len(holes) == 1:
                h_name = holes[0][0]
                lin_solver = z3.Solver()
                lin_solver.set("timeout", 250)
                c0 = z3.Int("c0")
                coeffs = {vn: z3.Int(f"c_{vn}") for vn in var_names}
                sq_coeffs = {vn: z3.Int(f"sq_{vn}") for vn in var_names}
                lin_solver.add(c0 >= -10, c0 <= 10)
                for vn in var_names:
                    lin_solver.add(coeffs[vn] >= -10, coeffs[vn] <= 10)
                    lin_solver.add(sq_coeffs[vn] >= -5, sq_coeffs[vn] <= 5)

                # Require at least one non-zero variable coefficient so it is not a trivial constant
                non_zero_terms = [coeffs[vn] != 0 for vn in var_names] + [
                    sq_coeffs[vn] != 0 for vn in var_names
                ]
                lin_solver.add(z3.Or(*non_zero_terms))

                ok_lin = True
                for tc in test_cases:
                    raw_in = tc.get("inputs", tc.get("input", {}))
                    in_dict = (
                        {str(k): v for k, v in raw_in.items() if isinstance(v, (int, float))}
                        if isinstance(raw_in, dict)
                        else ({"x": raw_in} if isinstance(raw_in, (int, float)) else {})
                    )
                    exp_out = tc.get("output", tc.get("expected", tc.get("expected_output")))
                    if not isinstance(exp_out, (int, float)) or not float(exp_out).is_integer():
                        ok_lin = False
                        break
                    hole_expr: z3.ArithRef = c0
                    for vn in var_names:
                        xv = int(in_dict.get(vn, 0))
                        hole_expr = hole_expr + coeffs[vn] * xv + sq_coeffs[vn] * (xv * xv)
                    term = self._ast_to_z3(sketch, {h_name: hole_expr}, in_dict, lin_solver)
                    if term is None:
                        ok_lin = False
                        break
                    lin_solver.add(term == int(exp_out))

                if ok_lin and lin_solver.check() == z3.sat:
                    m = lin_solver.model()
                    c0_val = m.eval(c0, model_completion=True).as_long()
                    sum_parts: list[str] = []
                    for vn in var_names:
                        sq_v = m.eval(sq_coeffs[vn], model_completion=True).as_long()
                        if sq_v == 1:
                            sum_parts.append(f"(* {vn} {vn})")
                        elif sq_v == -1:
                            sum_parts.append(f"(- 0 (* {vn} {vn}))")
                        elif sq_v != 0:
                            sum_parts.append(f"(* {sq_v} (* {vn} {vn}))")

                        c_v = m.eval(coeffs[vn], model_completion=True).as_long()
                        if c_v == 1:
                            sum_parts.append(vn)
                        elif c_v == -1:
                            sum_parts.append(f"(- 0 {vn})")
                        elif c_v != 0:
                            sum_parts.append(f"(* {c_v} {vn})")

                    if c0_val != 0 or not sum_parts:
                        sum_parts.append(str(c0_val))

                    if len(sum_parts) == 1:
                        sexpr_str = sum_parts[0]
                    else:
                        sexpr_str = sum_parts[0]
                        for sp in sum_parts[1:]:
                            sexpr_str = f"(+ {sexpr_str} {sp})"

                    results[h_name].append(
                        AbductiveHypothesis(
                            hole_name=h_name,
                            candidate_expr=sexpr_str,
                            confidence=0.99,
                            heuristic_rank=1,
                            derivation_rationale=f"Z3 symbolic polynomial abduction: {sexpr_str}",
                        )
                    )

        return results

    def invert_goal_for_sketch(
        self,
        sketch: SchemeNode,
        target_val: int | float | str | bool,
        hole_name: str,
        test_cases: list[dict[str, object]] | None = None,
    ) -> list[AbductiveHypothesis]:
        """
        Attempts to invert an AST sketch containing an open hole `hole_name`
        via algebraic inversion and Z3 constraint solving without direct target cheating.
        """
        hypotheses: list[AbductiveHypothesis] = []

        if test_cases:
            z3_map = self.solve_holes_z3(
                sketch=sketch,
                holes=[(hole_name, None)],
                target_val=target_val,
                test_cases=test_cases,
            )
            hypotheses.extend(z3_map.get(hole_name, []))

        # Case 1: Binary / N-ary operation with one or two holes
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
                                        arg1, solved, hole_name, test_cases=test_cases
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
                                        arg2, solved, hole_name, test_cases=test_cases
                                    )
                                    hypotheses.extend(sub_hyps)

                    # Multi-hole factorization / decomposition when both arg1 and arg2 are holes
                    if is_hole_node(arg1) and is_hole_node(arg2) and float(target_val).is_integer():
                        t_int = int(target_val)
                        if op == "*" and t_int != 0:
                            abs_t = abs(t_int)
                            limit = int(math.isqrt(abs_t)) + 1
                            for d in range(limit, 1, -1):
                                if abs_t % d == 0:
                                    q = t_int // d
                                    for cand_v in (d, q):
                                        c_s = str(cand_v)
                                        if not any(h.candidate_expr == c_s for h in hypotheses):
                                            hypotheses.append(
                                                AbductiveHypothesis(
                                                    hole_name=hole_name,
                                                    candidate_expr=c_s,
                                                    confidence=0.85,
                                                    heuristic_rank=len(hypotheses) + 1,
                                                    derivation_rationale=f"Multiplicative factor decomposition of {t_int}: {d} * {q}",
                                                )
                                            )
                        elif op == "+":
                            half = t_int // 2
                            for cand_v in (half, t_int - half, 1, t_int - 1):
                                c_s = str(cand_v)
                                if not any(h.candidate_expr == c_s for h in hypotheses):
                                    hypotheses.append(
                                        AbductiveHypothesis(
                                            hole_name=hole_name,
                                            candidate_expr=c_s,
                                            confidence=0.75,
                                            heuristic_rank=len(hypotheses) + 1,
                                            derivation_rationale=f"Additive partition of {t_int}",
                                        )
                                    )

                # N-ary (> 2 args) arithmetic with 1 hole and known other args
                elif len(sketch) > 3 and isinstance(target_val, (int, float)) and op in ("+", "*"):
                    hole_children = [
                        c for c in sketch[1:] if _find_hole_in_ast(c, hole_name)
                    ]
                    other_children = [
                        c for c in sketch[1:] if not _find_hole_in_ast(c, hole_name)
                    ]
                    if len(hole_children) == 1 and len(other_children) == len(sketch) - 2:
                        other_vals = [_eval_pure_safe(c) for c in other_children]
                        if all(isinstance(v, (int, float)) for v in other_vals):
                            if op == "+":
                                partial = sum(float(v) for v in other_vals if isinstance(v, (int, float)))
                                rem = target_val - partial
                                rem_clean: int | float = int(rem) if float(rem).is_integer() else rem
                            else:
                                partial = 1.0
                                for v in other_vals:
                                    if isinstance(v, (int, float)):
                                        partial *= float(v)
                                rem = target_val / partial if partial != 0 else 0.0
                                rem_clean = int(rem) if float(rem).is_integer() else rem
                            if is_hole_node(hole_children[0]):
                                hypotheses.append(
                                    AbductiveHypothesis(
                                        hole_name=hole_name,
                                        candidate_expr=str(rem_clean),
                                        confidence=0.95,
                                        heuristic_rank=1,
                                        derivation_rationale=f"N-ary {op} algebraic inversion: {rem_clean}",
                                    )
                                )
                            else:
                                hypotheses.extend(
                                    self.invert_goal_for_sketch(
                                        hole_children[0], rem_clean, hole_name, test_cases=test_cases
                                    )
                                )

        # Case 2: Fact assertion / Intent inversion
        if isinstance(sketch, list) and sketch:
            head = sketch[0]
            if isinstance(head, Symbol) and head.name == "assert":
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

        return hypotheses[: self.max_hypotheses_per_hole]

    def propose_candidates_for_all_holes(
        self,
        sketch: SchemeNode,
        target_val: int | float | str | bool,
        holes: list[tuple[str, str | None]],
        test_cases: list[dict[str, object]] | None = None,
    ) -> dict[str, list[AbductiveHypothesis]]:
        """Proposes hypotheses for each open hole present in the sketch."""
        results: dict[str, list[AbductiveHypothesis]] = {}
        for h_name, _ in holes:
            hyps = self.invert_goal_for_sketch(
                sketch, target_val, h_name, test_cases=test_cases
            )
            results[h_name] = hyps
        return results
