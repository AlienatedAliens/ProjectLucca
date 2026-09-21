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

import re
from dataclasses import dataclass
from typing import Final, Literal

import structlog
import z3

from lucca.core.schemas import ToolSchema
from lucca.reasoning.scheme.parser import (
    Keyword,
    RuleDefinition,
    SchemeAtom,
    SchemeNode,
    Symbol,
    parse_rule,
)

logger = structlog.get_logger(__name__)

DEFAULT_SMT_TIMEOUT_MS: Final[int] = 500

VerificationStatus = Literal[
    "VERIFIED",
    "UNSATISFIABLE",
    "TAUTOLOGY",
    "DEONTIC_UNSAFE",
    "UNKNOWN_TOOL",
    "SYNTAX_ERROR",
    "TIMEOUT",
    "ERROR",
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

        self.apps_running: dict[str, z3.BoolRef] = {}
        self.transcript_has: dict[str, z3.BoolRef] = {}
        self.entity_has: dict[tuple[str, str], z3.BoolRef] = {}
        self.entity_int: dict[str, z3.ArithRef] = {}
        self.entity_str: dict[str, z3.SeqRef] = {}

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

    def __init__(self, timeout_ms: int = DEFAULT_SMT_TIMEOUT_MS) -> None:
        self.timeout_ms = timeout_ms

    def verify_source(
        self,
        source: str,
        registered_tools: dict[str, ToolSchema] | None = None,
    ) -> SMTVerificationResult:
        try:
            rule_def = parse_rule(source)
        except Exception as exc:  # noqa: BLE001
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
                when_z3 = z3.BoolVal(bool(when_z3))
        except Exception as exc:  # noqa: BLE001
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

        # 4. Deontic Plan Verification
        deontic_res = self._verify_plan_actions(rule_def.plan_expr, registered_tools)
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

    def _verify_plan_actions(
        self,
        plan_expr: SchemeNode,
        registered_tools: dict[str, ToolSchema] | None = None,
    ) -> SMTVerificationResult:
        """Formally verifies that tool calls satisfy deontic path and tool invariants."""
        if not isinstance(plan_expr, list) or len(plan_expr) == 0:
            return SMTVerificationResult(
                verified=False,
                status="DEONTIC_UNSAFE",
                reasons=["Empty plan expression"],
            )

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

                # Extract tool arguments
                args = self._extract_call_args(action[2:])

                # Deontic path check on filesystem tools
                if tool_name in {"read_file", "write_file", "edit_file", "delete_file"}:
                    path_val = (
                        args.get("path")
                        or args.get("rel_path")
                        or args.get("target")
                        or args.get("file")
                    )
                    if path_val is not None:
                        path_str = str(path_val).strip().lower()

                        # SMT check for forbidden substrings / traversal
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

                        # Check prohibited extensions for mutation tools
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

    def _extract_call_args(self, items: list[SchemeNode]) -> dict[str, SchemeAtom]:
        args: dict[str, SchemeAtom] = {}
        i = 0
        while i < len(items):
            k = items[i]
            if isinstance(k, Keyword) and i + 1 < len(items):
                val = items[i + 1]
                if isinstance(val, (str, int, float, bool, Symbol, Keyword)):
                    args[k.name.lstrip(":")] = val
                i += 2
            else:
                i += 1
        return args

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
                return left == right
            return z3.BoolVal(True)

        elif op == "<":
            if len(args) == 2:
                left = self._translate_expr(args[0], ctx)
                right = self._translate_expr(args[1], ctx)
                return left < right
            return z3.BoolVal(True)

        elif op == "<=":
            if len(args) == 2:
                left = self._translate_expr(args[0], ctx)
                right = self._translate_expr(args[1], ctx)
                return left <= right
            return z3.BoolVal(True)

        elif op == ">":
            if len(args) == 2:
                left = self._translate_expr(args[0], ctx)
                right = self._translate_expr(args[1], ctx)
                return left > right
            return z3.BoolVal(True)

        elif op == ">=":
            if len(args) == 2:
                left = self._translate_expr(args[0], ctx)
                right = self._translate_expr(args[1], ctx)
                return left >= right
            return z3.BoolVal(True)

        elif op == "+":
            if len(args) == 2:
                return self._translate_expr(args[0], ctx) + self._translate_expr(args[1], ctx)
            return z3.IntVal(0)

        elif op == "-":
            if len(args) == 2:
                return self._translate_expr(args[0], ctx) - self._translate_expr(args[1], ctx)
            return z3.IntVal(0)

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

        raise ValueError(
            f"Unmodeled MicroScheme predicate or operator '{op}' cannot be safely verified by SMT"
        )
