"""
Project Lucca — Z3 SMT Formal Rule & Deontic Verifier
Milestone 6: Autonomous Rule Induction & Formal Verification
Spec 05 §7, Proposal E (D-REAS-06)

Formally verifies MicroScheme candidate rules using the Z3 SMT solver:
1. Precondition Satisfiability (SAT): Rejects contradictory or dead-code rules.
2. Precondition Non-Tautology: Rejects unconditional / tautological rules.
3. Deontic Safety Invariants: Proves candidate plan targets cannot intersect
   system paths, traversal sequences, or prohibited file extensions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import structlog
import z3

from lucca.core.schemas import ToolSchema
from lucca.reasoning.scheme.parser import (
    Keyword,
    RuleDefinition,
    SchemeNode,
    Symbol,
    parse_expr,
    parse_rule,
    to_canonical,
)

logger = structlog.get_logger(__name__)

DEFAULT_SMT_TIMEOUT_MS: Final[int] = 500

VerificationStatus = Literal[
    "VERIFIED",
    "UNSATISFIABLE",
    "TAUTOLOGY",
    "DEONTIC_UNSAFE",
    "DOMAIN_UNSAFE",
    "UNKNOWN_TOOL",
    "SYNTAX_ERROR",
    "TIMEOUT",
    "ERROR",
    "UNMODELED_PREDICATE",
]

# Sensitive and system path signatures
FORBIDDEN_PATH_SUBSTRINGS: Final[tuple[str, ...]] = (
    "..",
    "../",
    "..\\",
    "c:\\windows",
    "c:/windows",
    "system32",
    "syswow64",
    "c:\\program files",
    "c:/program files",
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/var",
    "/proc",
    "/sys",
    ".git",
    ".ssh",
    "id_rsa",
    "id_ed25519",
    ".env",
)

PROHIBITED_WRITE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".exe",
        ".dll",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".sh",
        ".sys",
        ".msi",
        ".com",
        ".scr",
    }
)


@dataclass(frozen=True)
class SMTVerificationResult:
    verified: bool
    status: VerificationStatus
    reasons: list[str]
    model_sample: dict[str, str | int | float | bool] | None = None


class StateContext:
    """Encapsulates Z3 variables and foundational domain axioms for RuleState."""

    def __init__(self) -> None:
        self.intent = z3.String("intent")
        self.hour_local = z3.Int("hour_local")
        self.weekday = z3.Int("weekday")
        self.session_turns = z3.Int("session_turns")
        self.intent_conf = z3.Real("intent_conf")
        self.last_tool = z3.String("last_tool")
        self.last_tool_ok = z3.Bool("last_tool_ok")
        self.interrupted = z3.Bool("interrupted")

        self.apps_running: dict[str, z3.BoolRef] = {}
        self.transcript_has: dict[str, z3.BoolRef] = {}
        self.entity_has: dict[tuple[str, str], z3.BoolRef] = {}
        self.entity_int: dict[str, z3.ArithRef] = {}
        self.entity_str: dict[str, z3.SeqRef] = {}
        self.uninterpreted_funcs: dict[str, z3.FuncDeclRef] = {}

    def get_uninterpreted_func(
        self,
        name: str,
        arg_sorts: tuple[z3.SortRef, ...],
        ret_sort: z3.SortRef,
    ) -> z3.FuncDeclRef:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        key = f"{clean}_{len(arg_sorts)}"
        if key not in self.uninterpreted_funcs:
            self.uninterpreted_funcs[key] = z3.Function(clean, *arg_sorts, ret_sort)
        return self.uninterpreted_funcs[key]

    def get_axioms(self) -> list[z3.BoolRef]:
        """Foundational valid bounds on agent operational state."""
        return [
            self.hour_local >= 0,
            self.hour_local <= 23,
            self.weekday >= 0,
            self.weekday <= 6,
            self.session_turns >= 0,
            self.intent_conf >= 0.0,
            self.intent_conf <= 1.0,
        ]

    def get_app_running(self, app_name: str) -> z3.BoolRef:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", app_name)
        if clean not in self.apps_running:
            self.apps_running[clean] = z3.Bool(f"app_running_{clean}")
        return self.apps_running[clean]

    def get_transcript_has(self, term: str) -> z3.BoolRef:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", term)
        if clean not in self.transcript_has:
            self.transcript_has[clean] = z3.Bool(f"transcript_has_{clean}")
        return self.transcript_has[clean]

    def get_entity_has(self, key: str, val: str) -> z3.BoolRef:
        pair = (key, val)
        if pair not in self.entity_has:
            clean_k = re.sub(r"[^a-zA-Z0-9_]", "_", key)
            clean_v = re.sub(r"[^a-zA-Z0-9_]", "_", val)
            self.entity_has[pair] = z3.Bool(f"entity_has_{clean_k}_{clean_v}")
        return self.entity_has[pair]

    def get_entity_int(self, key: str) -> z3.ArithRef:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", key)
        if clean not in self.entity_int:
            self.entity_int[clean] = z3.Int(f"entity_int_{clean}")
        return self.entity_int[clean]

    def get_entity_str(self, key: str) -> z3.SeqRef:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", key)
        if clean not in self.entity_str:
            self.entity_str[clean] = z3.String(f"entity_str_{clean}")
        return self.entity_str[clean]


class SMTVerifier:
    """
    Formal safety and satisfiability verifier for MicroScheme rules.
    Invokes Z3 solver with bounded timeout to enforce deterministic invariants.
    """

    def __init__(
        self,
        timeout_ms: int | float = DEFAULT_SMT_TIMEOUT_MS,
        allow_pure_reasoning: bool = False,
    ) -> None:
        self.timeout_ms: int = max(1, int(timeout_ms))
        self.allow_pure_reasoning: bool = allow_pure_reasoning

    def verify_source(
        self,
        source: str,
        registered_tools: dict[str, ToolSchema] | None = None,
    ) -> SMTVerificationResult:
        try:
            rule_def = parse_rule(source)
        except Exception as exc:  # noqa: BLE001
            logger.debug("smt_parse_rule_failed", error=str(exc))
            return SMTVerificationResult(
                verified=False,
                status="SYNTAX_ERROR",
                reasons=[f"Syntax error during rule parsing: {exc}"],
            )
        return self.verify_rule(rule_def, registered_tools=registered_tools)

    def verify_rule(
        self,
        rule_def: RuleDefinition,
        registered_tools: dict[str, ToolSchema] | None = None,
    ) -> SMTVerificationResult:
        """
        Runs comprehensive formal SMT verification on a MicroScheme rule:
        1. Precondition SAT & Non-Tautology check.
        2. Plan action deontic safety & path jail verification.
        """
        reasons: list[str] = []
        ctx = StateContext()

        # 1. Translate when_expr to Z3
        try:
            when_z3 = self._translate_expr(rule_def.when_expr, ctx)
            if not isinstance(when_z3, z3.BoolRef):
                if isinstance(when_z3, (z3.ArithRef, z3.BitVecRef)):
                    when_z3 = when_z3 != 0
                elif isinstance(when_z3, z3.SeqRef):
                    when_z3 = z3.Length(when_z3) > 0
                elif isinstance(when_z3, z3.ExprRef):
                    when_z3 = z3.BoolVal(True)
                else:
                    when_z3 = z3.BoolVal(bool(when_z3))
        except Exception as exc:  # noqa: BLE001
            logger.debug("smt_translate_expr_failed", error=str(exc))
            return SMTVerificationResult(
                verified=False,
                status="UNMODELED_PREDICATE",
                reasons=[
                    f"Translation of :when expression to Z3 failed (unmodeled predicate): {exc}"
                ],
            )

        # 2. Check Precondition Satisfiability (SAT)
        sat_solver = z3.Solver()
        sat_solver.set("timeout", self.timeout_ms)
        for axiom in ctx.get_axioms():
            sat_solver.add(axiom)
        sat_solver.add(when_z3)

        sat_check = sat_solver.check()
        if sat_check == z3.unsat:
            msg = (
                f"Rule '{rule_def.rule_id}' precondition is UNSATISFIABLE under "
                "state axioms (dead code / logical contradiction)."
            )
            reasons.append(msg)
            return SMTVerificationResult(
                verified=False,
                status="UNSATISFIABLE",
                reasons=reasons,
            )
        elif sat_check == z3.unknown:
            return SMTVerificationResult(
                verified=False,
                status="TIMEOUT",
                reasons=[
                    f"SMT solver timed out ({self.timeout_ms}ms) during satisfiability check."
                ],
            )

        # Extract sample model
        sample_model: dict[str, str | int | float | bool] = {}
        try:
            model = sat_solver.model()
            if model[ctx.intent] is not None:
                sample_model["intent"] = str(model[ctx.intent]).strip('"')
            if model[ctx.hour_local] is not None:
                val = model[ctx.hour_local].as_long()
                sample_model["hour_local"] = val
            if model[ctx.weekday] is not None:
                val = model[ctx.weekday].as_long()
                sample_model["weekday"] = val
        except Exception as exc:  # noqa: BLE001
            logger.debug("smt_model_extraction_ignored", error=str(exc))

        # 3. Check Precondition Tautology (must not be universally true)
        taut_solver = z3.Solver()
        taut_solver.set("timeout", self.timeout_ms)
        for axiom in ctx.get_axioms():
            taut_solver.add(axiom)
        taut_solver.add(z3.Not(when_z3))

        taut_check = taut_solver.check()
        if taut_check == z3.unsat:
            # Not(when) is unsat => when is always true for all valid states
            msg = (
                f"Rule '{rule_def.rule_id}' precondition is a TAUTOLOGY "
                "(fires unconditionally across all states)."
            )
            reasons.append(msg)
            return SMTVerificationResult(
                verified=False,
                status="TAUTOLOGY",
                reasons=reasons,
                model_sample=sample_model,
            )

        # 3b. Check Arithmetic Domain Safety (division by zero in when_expr)
        div_res = self._check_division_safety(rule_def.when_expr, ctx, precondition=when_z3)
        if not div_res.verified:
            return div_res

        # 4. Deontic Plan Verification (including symbolic Z3 path constraints)
        deontic_res = self._verify_plan_actions(
            rule_def.plan_expr,
            registered_tools=registered_tools,
            ctx=ctx,
            when_z3=when_z3,
        )
        if not deontic_res.verified:
            return deontic_res

        verified_msg = (
            f"Rule '{rule_def.rule_id}' formally verified (SAT, contingent, deontically safe)."
        )
        return SMTVerificationResult(
            verified=True,
            status="VERIFIED",
            reasons=[verified_msg],
            model_sample=sample_model,
        )

    def verify_expression(self, expr: SchemeNode | str) -> SMTVerificationResult:
        """
        Formally verifies an arbitrary MicroScheme expression for domain safety
        (e.g., proving absence of division-by-zero across symbolic inputs).
        """
        try:
            node = parse_expr(expr) if isinstance(expr, str) else expr
        except Exception as exc:  # noqa: BLE001
            logger.debug("smt_verify_expression_syntax_error", error=str(exc))
            return SMTVerificationResult(
                verified=False,
                status="SYNTAX_ERROR",
                reasons=[f"Syntax error parsing expression: {exc}"],
            )
        ctx = StateContext()
        div_res = self._check_division_safety(node, ctx, precondition=None)
        if not div_res.verified:
            return div_res
        return SMTVerificationResult(
            verified=True,
            status="VERIFIED",
            reasons=["Expression verified domain-safe by Z3"],
        )

    def _collect_divisions(self, node: SchemeNode) -> list[SchemeNode]:
        """Collects all denominator AST nodes from (/ num denom) subexpressions."""
        denoms: list[SchemeNode] = []
        if isinstance(node, list) and len(node) > 0:
            head = node[0]
            if isinstance(head, Symbol) and head.name == "/" and len(node) >= 3:
                denoms.append(node[2])
            for child in node:
                denoms.extend(self._collect_divisions(child))
        return denoms

    def _check_division_safety(
        self,
        node: SchemeNode,
        ctx: StateContext,
        precondition: z3.BoolRef | None = None,
    ) -> SMTVerificationResult:
        """Checks via Z3 whether any division denominator can evaluate to 0."""
        denoms = self._collect_divisions(node)
        for denom in denoms:
            try:
                denom_z3 = self._translate_arith_expr(denom, ctx)
            except Exception as exc:  # noqa: BLE001
                logger.debug("smt_division_denom_translate_error", error=str(exc))
                return SMTVerificationResult(
                    verified=False,
                    status="DOMAIN_UNSAFE",
                    reasons=[f"Unverifiable division denominator '{to_canonical(denom)}': {exc}"],
                )
            solver = z3.Solver()
            solver.set("timeout", self.timeout_ms)
            for axiom in ctx.get_axioms():
                solver.add(axiom)
            if precondition is not None:
                solver.add(precondition)
            solver.add(denom_z3 == 0)
            if solver.check() != z3.unsat:
                return SMTVerificationResult(
                    verified=False,
                    status="DOMAIN_UNSAFE",
                    reasons=[
                        f"Division by zero is satisfiable for denominator '{to_canonical(denom)}'"
                    ],
                )
        return SMTVerificationResult(
            verified=True,
            status="VERIFIED",
            reasons=["No division by zero reachable"],
        )

    def _collect_plan_actions(self, node: SchemeNode) -> list[list[SchemeNode]]:
        """Collects all action nodes recursively from plan expression (unpacking list and if)."""
        actions: list[list[SchemeNode]] = []
        if not isinstance(node, list) or len(node) == 0:
            return actions
        head = node[0]
        if isinstance(head, Symbol):
            if head.name == "if":
                for branch in node[2:]:
                    actions.extend(self._collect_plan_actions(branch))
            elif head.name == "list":
                for item in node[1:]:
                    actions.extend(self._collect_plan_actions(item))
            else:
                actions.append(node)
        else:
            actions.append(node)
        return actions

    def _translate_string_expr(self, node: SchemeNode, ctx: StateContext) -> z3.SeqRef:
        """
        Translates a path/string AST node (literal or dynamic S-expression) into a Z3 String sort.
        """
        if isinstance(node, str):
            return z3.StringVal(node.strip().lower())
        if isinstance(node, (int, float, bool)):
            return z3.StringVal(str(node).lower())
        if isinstance(node, (Symbol, Keyword)):
            return ctx.get_entity_str(node.name)
        if isinstance(node, list) and len(node) > 0 and isinstance(node[0], Symbol):
            op = node[0].name
            args = node[1:]
            if op == "entity-str" and len(args) >= 1:
                return ctx.get_entity_str(str(args[0]))
            if op in ("string-append", "concat", "path-join"):
                parts = [self._translate_string_expr(a, ctx) for a in args]
                if not parts:
                    return z3.StringVal("")
                if len(parts) == 1:
                    return parts[0]
                return z3.Concat(*parts)
            if op == "if" and len(args) >= 3:
                cond = self._translate_expr(args[0], ctx)
                then_s = self._translate_string_expr(args[1], ctx)
                else_s = self._translate_string_expr(args[2], ctx)
                if isinstance(cond, z3.BoolRef):
                    res = z3.If(cond, then_s, else_s)
                    if isinstance(res, z3.SeqRef):
                        return res
                return then_s
        # Fallback: unconstrained symbolic string variable for any other dynamic list expression
        return ctx.get_entity_str(f"dynamic_expr_{to_canonical(node)}")

    def _verify_plan_actions(
        self,
        plan_expr: SchemeNode,
        registered_tools: dict[str, ToolSchema] | None = None,
        ctx: StateContext | None = None,
        when_z3: z3.BoolRef | None = None,
    ) -> SMTVerificationResult:
        """Formally verifies that tool calls satisfy deontic path and tool invariants."""
        if not isinstance(plan_expr, list) or len(plan_expr) == 0:
            return SMTVerificationResult(
                verified=False,
                status="DEONTIC_UNSAFE",
                reasons=["Empty plan expression"],
            )

        effective_ctx = ctx or StateContext()
        actions = self._collect_plan_actions(plan_expr)

        reasons: list[str] = []
        for action in actions:
            if not isinstance(action, list) or len(action) == 0:
                continue
            act_head = action[0]
            if isinstance(act_head, Symbol) and act_head.name == "tool":
                if len(action) < 2 or not isinstance(action[1], str):
                    reasons.append("Malformed tool call: missing string tool name")
                    continue

                tool_name = action[1]
                if registered_tools is not None and tool_name not in registered_tools:
                    return SMTVerificationResult(
                        verified=False,
                        status="UNKNOWN_TOOL",
                        reasons=[f"Plan references unregistered tool '{tool_name}'"],
                    )

                # Extract tool arguments (including dynamic S-expression list arguments)
                args = self._extract_call_args(action[2:])

                # Deontic path check on filesystem tools
                if tool_name in {"read_file", "write_file", "edit_file", "delete_file"}:
                    path_val: SchemeNode | None = None
                    for path_key in ("path", "rel_path", "target", "file"):
                        if path_key in args:
                            path_val = args[path_key]
                            break

                    if path_val is None:
                        return SMTVerificationResult(
                            verified=False,
                            status="DEONTIC_UNSAFE",
                            reasons=[f"Tool '{tool_name}' missing required path argument"],
                        )

                    # 1. Static check for literal string paths
                    if isinstance(path_val, (str, int, float, bool, Keyword)):
                        path_str = str(path_val).strip().lower()
                        for forbidden in FORBIDDEN_PATH_SUBSTRINGS:
                            if forbidden in path_str:
                                return SMTVerificationResult(
                                    verified=False,
                                    status="DEONTIC_UNSAFE",
                                    reasons=[
                                        f"Tool '{tool_name}' target path '{path_val}' contains "
                                        f"prohibited sequence '{forbidden}'"
                                    ],
                                )
                        if tool_name in {"write_file", "edit_file"}:
                            for ext in PROHIBITED_WRITE_EXTENSIONS:
                                if path_str.endswith(ext):
                                    return SMTVerificationResult(
                                        verified=False,
                                        status="DEONTIC_UNSAFE",
                                        reasons=[
                                            f"Tool '{tool_name}' target path '{path_val}' has "
                                            f"prohibited executable extension '{ext}'"
                                        ],
                                    )

                    # 2. Formal Z3 String Constraint Check (handles both literal and dynamic
                    # S-expression paths)
                    z3_path = self._translate_string_expr(path_val, effective_ctx)
                    path_solver = z3.Solver()
                    path_solver.set("timeout", self.timeout_ms)
                    for axiom in effective_ctx.get_axioms():
                        path_solver.add(axiom)
                    if when_z3 is not None:
                        path_solver.add(when_z3)

                    hazard_clauses: list[z3.BoolRef] = [
                        z3.Contains(z3_path, z3.StringVal(forbidden))
                        for forbidden in FORBIDDEN_PATH_SUBSTRINGS
                    ]
                    if tool_name in {"write_file", "edit_file"}:
                        hazard_clauses.extend(
                            z3.SuffixOf(z3.StringVal(ext), z3_path)
                            for ext in PROHIBITED_WRITE_EXTENSIONS
                        )

                    path_solver.add(z3.Or(*hazard_clauses))
                    if path_solver.check() != z3.unsat:
                        path_repr = path_val if isinstance(path_val,
                            str) else to_canonical(path_val)
                        return SMTVerificationResult(
                            verified=False,
                            status="DEONTIC_UNSAFE",
                            reasons=[
                                f"Tool '{tool_name}' dynamic/target path '{path_repr}' can violate "
                                "deontic path safety invariants in Z3 model"
                            ],
                        )

        if reasons:
            return SMTVerificationResult(
                verified=False,
                status="DEONTIC_UNSAFE",
                reasons=reasons,
            )

        return SMTVerificationResult(
            verified=True,
            status="VERIFIED",
            reasons=["Plan actions verified safe"],
        )

    def _extract_call_args(self, items: list[SchemeNode]) -> dict[str, SchemeNode]:
        args: dict[str, SchemeNode] = {}
        i = 0
        while i < len(items):
            k = items[i]
            if isinstance(k, Keyword) and i + 1 < len(items):
                val = items[i + 1]
                args[k.name.lstrip(":")] = val
                i += 2
            else:
                i += 1
        return args

    def _translate_arith_expr(
        self,
        node: SchemeNode,
        ctx: StateContext,
    ) -> z3.ArithRef:
        """
        Translates an arithmetic operand into a Z3 ArithRef (mapping Symbol variables to Z3 Ints).
        """
        if isinstance(node, bool):
            return z3.IntVal(1 if node else 0)
        if isinstance(node, int):
            return z3.IntVal(node)
        if isinstance(node, float):
            return z3.RealVal(node)
        if isinstance(node, Symbol):
            return ctx.get_entity_int(node.name)
        expr = self._translate_expr(node, ctx)
        if isinstance(expr, z3.ArithRef):
            return expr
        raise ValueError(f"Expected arithmetic expression, got '{to_canonical(node)}'")

    def _translate_expr(
        self,
        node: SchemeNode,
        ctx: StateContext,
    ) -> z3.ExprRef:
        """Translates MicroScheme AST node into corresponding Z3 expression."""
        if isinstance(node, bool):
            return z3.BoolVal(node)
        if isinstance(node, int):
            return z3.IntVal(node)
        if isinstance(node, float):
            return z3.RealVal(node)
        if isinstance(node, str):
            return z3.StringVal(node)
        if isinstance(node, Symbol):
            if node.name in ("#t", "true"):
                return z3.BoolVal(True)
            if node.name in ("#f", "false"):
                return z3.BoolVal(False)
            return z3.StringVal(node.name)
        if isinstance(node, Keyword):
            return z3.StringVal(node.name)

        if not isinstance(node, list) or len(node) == 0:
            return z3.BoolVal(True)

        head = node[0]
        if not isinstance(head, Symbol):
            return z3.BoolVal(True)

        op = head.name
        args = node[1:]

        if op == "and":
            child_exprs = [self._translate_expr(c, ctx) for c in args]
            bool_exprs = [c for c in child_exprs if isinstance(c, z3.BoolRef)]
            return z3.And(*bool_exprs) if bool_exprs else z3.BoolVal(True)

        elif op == "or":
            child_exprs = [self._translate_expr(c, ctx) for c in args]
            bool_exprs = [c for c in child_exprs if isinstance(c, z3.BoolRef)]
            return z3.Or(*bool_exprs) if bool_exprs else z3.BoolVal(False)

        elif op == "not":
            if not args:
                return z3.BoolVal(False)
            child = self._translate_expr(args[0], ctx)
            if isinstance(child, z3.BoolRef):
                return z3.Not(child)
            return z3.BoolVal(False)

        elif op == "if":
            if len(args) < 3:
                return z3.BoolVal(True)
            cond = self._translate_expr(args[0], ctx)
            then_b = self._translate_expr(args[1], ctx)
            else_b = self._translate_expr(args[2], ctx)
            if isinstance(cond, z3.BoolRef):
                return z3.If(cond, then_b, else_b)
            return then_b

        elif op == "=":
            if len(args) == 2:
                left = self._translate_expr(args[0], ctx)
                right = self._translate_expr(args[1], ctx)
                if isinstance(left, z3.ArithRef) or isinstance(right, z3.ArithRef):
                    return self._translate_arith_expr(args[0],
                        ctx) == self._translate_arith_expr(args[1], ctx)
                return left == right
            return z3.BoolVal(True)

        elif op == "<":
            if len(args) == 2:
                left = self._translate_arith_expr(args[0], ctx)
                right = self._translate_arith_expr(args[1], ctx)
                return left < right
            return z3.BoolVal(True)

        elif op == "<=":
            if len(args) == 2:
                left = self._translate_arith_expr(args[0], ctx)
                right = self._translate_arith_expr(args[1], ctx)
                return left <= right
            return z3.BoolVal(True)

        elif op == ">":
            if len(args) == 2:
                left = self._translate_arith_expr(args[0], ctx)
                right = self._translate_arith_expr(args[1], ctx)
                return left > right
            return z3.BoolVal(True)

        elif op == ">=":
            if len(args) == 2:
                left = self._translate_arith_expr(args[0], ctx)
                right = self._translate_arith_expr(args[1], ctx)
                return left >= right
            return z3.BoolVal(True)

        elif op == "+":
            if len(args) == 2:
                return self._translate_arith_expr(args[0],
                    ctx) + self._translate_arith_expr(args[1], ctx)
            return z3.IntVal(0)

        elif op == "-":
            if len(args) == 2:
                return self._translate_arith_expr(args[0],
                    ctx) - self._translate_arith_expr(args[1], ctx)
            return z3.IntVal(0)

        elif op == "*":
            if len(args) == 2:
                return self._translate_arith_expr(args[0],
                    ctx) * self._translate_arith_expr(args[1], ctx)
            return z3.IntVal(0)

        elif op == "/":
            if len(args) == 2:
                return self._translate_arith_expr(args[0],
                    ctx) / self._translate_arith_expr(args[1], ctx)
            return z3.IntVal(0)

        elif op in ("string-append", "concat", "path-join"):
            return self._translate_string_expr(node, ctx)

        # MicroScheme State Predicates
        elif op == "intent=":
            if len(args) >= 1:
                val = str(args[0]) if not isinstance(args[0], (Symbol, Keyword)) else args[0].name
                return ctx.intent == z3.StringVal(val)
            return z3.BoolVal(False)

        elif op == "hour-between?":
            if len(args) >= 2:
                try:
                    start = int(args[0])  # type: ignore[arg-type]
                    end = int(args[1])  # type: ignore[arg-type]
                    return z3.And(ctx.hour_local >= start, ctx.hour_local <= end)
                except (ValueError, TypeError):
                    return z3.BoolVal(False)
            return z3.BoolVal(False)

        elif op == "weekday?":
            if len(args) >= 1:
                try:
                    day = int(args[0])  # type: ignore[arg-type]
                    return ctx.weekday == day
                except (ValueError, TypeError):
                    return z3.BoolVal(False)
            return z3.BoolVal(False)

        elif op == "session-turns>=":
            if len(args) >= 1:
                try:
                    turns = int(args[0])  # type: ignore[arg-type]
                    return ctx.session_turns >= turns
                except (ValueError, TypeError):
                    return z3.BoolVal(False)
            return z3.BoolVal(False)

        elif op == "last-tool=":
            if len(args) >= 1:
                tool = str(args[0])
                return ctx.last_tool == z3.StringVal(tool)
            return z3.BoolVal(False)

        elif op == "last-tool-ok?":
            return ctx.last_tool_ok == True  # noqa: E712

        elif op == "interrupted?":
            return ctx.interrupted == True  # noqa: E712

        elif op == "app-running?":
            if len(args) >= 1:
                app_name = str(args[0])
                return ctx.get_app_running(app_name)
            return z3.BoolVal(False)

        elif op == "transcript-has?":
            if len(args) >= 1:
                term = str(args[0])
                return ctx.get_transcript_has(term)
            return z3.BoolVal(False)

        elif op == "entity-has?":
            if len(args) >= 2:
                key = str(args[0])
                val = str(args[1])
                return ctx.get_entity_has(key, val)
            return z3.BoolVal(False)

        elif op == "entity-int":
            if len(args) >= 1:
                key = str(args[0])
                return ctx.get_entity_int(key)
            return z3.IntVal(0)

        elif op == "entity-str":
            if len(args) >= 1:
                key = str(args[0])
                return ctx.get_entity_str(key)
            return z3.StringVal("")

        if self.allow_pure_reasoning:
            clean_op = re.sub(r"[^a-zA-Z0-9_]", "_", op)
            child_z3: list[z3.ExprRef] = []
            arg_sorts: list[z3.SortRef] = []
            for c in args:
                tz = self._translate_expr(c, ctx)
                child_z3.append(tz)
                arg_sorts.append(tz.sort())
            fn_decl = ctx.get_uninterpreted_func(clean_op, tuple(arg_sorts), z3.BoolSort())
            return fn_decl(*child_z3)

        raise ValueError(
            f"Unmodeled MicroScheme predicate or operator '{op}' cannot be safely verified by SMT"
        )


ZEBRA_GRAMMAR_PATH: Final[Path] = Path("config/grammars/zebra_constraints.gbnf")


def load_zebra_constraints_grammar(grammar_path: Path | None = None) -> str:
    """
    Loads the GBNF grammar for structured ZebraLogic constraint emission on E2B/E4B edge models.
    """
    path = grammar_path or ZEBRA_GRAMMAR_PATH
    return path.read_text(encoding="utf-8")


def _parse_zebra_spec(spec: str | dict[str, object]) -> dict[str, object]:
    if isinstance(spec, dict):
        return spec
    clean = spec.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL)
    if m:
        clean = m.group(1).strip()
    parsed = json.loads(clean)
    if not isinstance(parsed, dict):
        raise ValueError("Zebra constraint specification must be a JSON object")
    return parsed


def compile_zebra_json_to_z3_python(spec: str | dict[str, object]) -> str:
    """
    Deterministic Python Z3 compiler for edge tiers (E2B / E4B) per Milestone 36.5 Deliverable 2.
    Translates structured JSON relational constraints (same_house, left_of, adjacent, at_pos, etc.)
    into a self-contained, executable Python Z3 script without LLM syntax errors.
    """
    data = _parse_zebra_spec(spec)
    num_houses = int(str(data.get("num_houses", 5)))
    raw_cats = data.get("categories", [])
    categories: list[list[str]] = []
    if isinstance(raw_cats, list):
        for cat in raw_cats:
            if isinstance(cat, list):
                categories.append([str(item).strip() for item in cat if str(item).strip()])

    raw_constraints = data.get("constraints", [])
    constraints: list[dict[str, object]] = []
    if isinstance(raw_constraints, list):
        for c in raw_constraints:
            if isinstance(c, dict):
                constraints.append(c)

    query_entity = str(data.get("query_entity") or "").strip()
    raw_q_cat = data.get("query_category", [])
    query_category: list[str] = (
        [str(x).strip() for x in raw_q_cat if str(x).strip()]
        if isinstance(raw_q_cat, list)
        else []
    )

    lines: list[str] = [
        "import z3",
        "s = z3.Solver()",
        "v = {}",
    ]

    all_entities: list[str] = []
    for cat in categories:
        for ent in cat:
            if ent not in all_entities:
                all_entities.append(ent)
    for c in constraints:
        for k in ("a", "b", "c"):
            val = c.get(k)
            if isinstance(val, str) and val.strip() and val.strip() not in all_entities:
                all_entities.append(val.strip())

    for ent in all_entities:
        lines.append(f"v[{ent!r}] = z3.Int({ent!r})")
        lines.append(f"s.add(v[{ent!r}] >= 1, v[{ent!r}] <= {num_houses})")

    for cat in categories:
        if len(cat) >= 2:
            cat_vars = ", ".join(f"v[{ent!r}]" for ent in cat)
            lines.append(f"s.add(z3.Distinct({cat_vars}))")

    for c in constraints:
        rel = str(c.get("rel") or "").strip().lower()
        a = str(c.get("a") or "").strip()
        b = str(c.get("b") or "").strip()
        c_ent = str(c.get("c") or "").strip()
        pos_raw = c.get("pos")

        if rel in ("same_house", "same", "equals", "eq") and a and b:
            lines.append(f"s.add(v[{a!r}] == v[{b!r}])")
        elif rel in ("different_house", "diff", "not_equal", "neq") and a and b:
            lines.append(f"s.add(v[{a!r}] != v[{b!r}])")
        elif rel == "left_of" and a and b:
            lines.append(f"s.add(v[{a!r}] < v[{b!r}])")
        elif rel == "right_of" and a and b:
            lines.append(f"s.add(v[{a!r}] > v[{b!r}])")
        elif rel in ("immediately_left_of", "direct_left_of", "next_left") and a and b:
            lines.append(f"s.add(v[{a!r}] + 1 == v[{b!r}])")
        elif rel in ("immediately_right_of", "direct_right_of", "next_right") and a and b:
            lines.append(f"s.add(v[{a!r}] - 1 == v[{b!r}])")
        elif rel in ("adjacent", "next_to", "neighbor") and a and b:
            lines.append(f"s.add(z3.Or(v[{a!r}] - v[{b!r}] == 1, v[{b!r}] - v[{a!r}] == 1))")
        elif rel == "at_pos" and a and pos_raw is not None:
            pos_int = int(str(pos_raw))
            lines.append(f"s.add(v[{a!r}] == {pos_int})")
        elif rel == "not_at_pos" and a and pos_raw is not None:
            pos_int = int(str(pos_raw))
            lines.append(f"s.add(v[{a!r}] != {pos_int})")
        elif rel == "between" and a and b and c_ent:
            lines.append(
                f"s.add(z3.Or(z3.And(v[{b!r}] < v[{a!r}], v[{a!r}] < v[{c_ent!r}]), "
                f"z3.And(v[{c_ent!r}] < v[{a!r}], v[{a!r}] < v[{b!r}])))"
            )

    lines.append("if s.check() == z3.sat:")
    lines.append("    m = s.model()")
    if query_entity and query_category:
        lines.append(f"    target_pos = m[v[{query_entity!r}]].as_long()")
        lines.append(f"    for cand in {query_category!r}:")
        lines.append("        if m[v[cand]].as_long() == target_pos:")
        lines.append("            print(cand)")
        lines.append("            break")
    elif query_entity:
        lines.append(f"    print(m[v[{query_entity!r}]].as_long())")
    else:
        lines.append("    out = {k: m[var].as_long() for k, var in v.items() if m[var] "
            "is not None}")
        lines.append("    print(out)")
    lines.append("else:")
    lines.append("    print('UNSAT')")
    return "\n".join(lines)


def solve_zebra_constraints(
    spec: str | dict[str, object],
    timeout_ms: int = 2000,
) -> dict[str, object]:
    """
    Solves a structured ZebraLogic constraint specification directly via Z3 in-process.
    Returns dict with keys: sat (bool), assignments (dict[str, int]), answer (str | int | None),
    code (str).
    """
    data = _parse_zebra_spec(spec)
    code = compile_zebra_json_to_z3_python(data)
    num_houses = int(str(data.get("num_houses", 5)))

    raw_cats = data.get("categories", [])
    categories: list[list[str]] = []
    if isinstance(raw_cats, list):
        for cat in raw_cats:
            if isinstance(cat, list):
                categories.append([str(item).strip() for item in cat if str(item).strip()])

    raw_constraints = data.get("constraints", [])
    constraints: list[dict[str, object]] = []
    if isinstance(raw_constraints, list):
        for c in raw_constraints:
            if isinstance(c, dict):
                constraints.append(c)

    solver = z3.Solver()
    solver.set("timeout", max(1, int(timeout_ms)))
    v: dict[str, z3.ArithRef] = {}

    def _get_var(name: str) -> z3.ArithRef:
        if name not in v:
            v[name] = z3.Int(name)
            solver.add(v[name] >= 1, v[name] <= num_houses)
        return v[name]

    for cat in categories:
        cat_vars = [_get_var(ent) for ent in cat]
        if len(cat_vars) >= 2:
            solver.add(z3.Distinct(*cat_vars))

    for c in constraints:
        rel = str(c.get("rel") or "").strip().lower()
        a = str(c.get("a") or "").strip()
        b = str(c.get("b") or "").strip()
        c_ent = str(c.get("c") or "").strip()
        pos_raw = c.get("pos")

        if rel in ("same_house", "same", "equals", "eq") and a and b:
            solver.add(_get_var(a) == _get_var(b))
        elif rel in ("different_house", "diff", "not_equal", "neq") and a and b:
            solver.add(_get_var(a) != _get_var(b))
        elif rel == "left_of" and a and b:
            solver.add(_get_var(a) < _get_var(b))
        elif rel == "right_of" and a and b:
            solver.add(_get_var(a) > _get_var(b))
        elif rel in ("immediately_left_of", "direct_left_of", "next_left") and a and b:
            solver.add(_get_var(a) + 1 == _get_var(b))
        elif rel in ("immediately_right_of", "direct_right_of", "next_right") and a and b:
            solver.add(_get_var(a) - 1 == _get_var(b))
        elif rel in ("adjacent", "next_to", "neighbor") and a and b:
            va, vb = _get_var(a), _get_var(b)
            solver.add(z3.Or(va - vb == 1, vb - va == 1))
        elif rel == "at_pos" and a and pos_raw is not None:
            solver.add(_get_var(a) == int(str(pos_raw)))
        elif rel == "not_at_pos" and a and pos_raw is not None:
            solver.add(_get_var(a) != int(str(pos_raw)))
        elif rel == "between" and a and b and c_ent:
            va, vb, vc = _get_var(a), _get_var(b), _get_var(c_ent)
            solver.add(z3.Or(z3.And(vb < va, va < vc), z3.And(vc < va, va < vb)))

    if solver.check() != z3.sat:
        return {"sat": False, "assignments": {}, "answer": None, "code": code}

    model = solver.model()
    assignments: dict[str, int] = {}
    for ent, var in v.items():
        val = model[var]
        if val is not None and hasattr(val, "as_long"):
            assignments[ent] = int(val.as_long())

    query_entity = str(data.get("query_entity") or "").strip()
    raw_q_cat = data.get("query_category", [])
    query_category: list[str] = (
        [str(x).strip() for x in raw_q_cat if str(x).strip()]
        if isinstance(raw_q_cat, list)
        else []
    )

    answer: str | int | None = None
    if query_entity and query_entity in assignments:
        target_pos = assignments[query_entity]
        if query_category:
            for cand in query_category:
                if assignments.get(cand) == target_pos:
                    answer = cand
                    break
        else:
            answer = target_pos

    return {
        "sat": True,
        "assignments": assignments,
        "answer": answer,
        "code": code,
    }
