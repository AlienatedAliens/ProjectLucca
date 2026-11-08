"""
Project Lucca — Speculative BDI Invariant Validator
Milestone 4 (Architecture B Hardened by Architecture C) & WO-39 Milestone 2.4

Evaluates candidate System 2 tool calls speculatively before dispatch:
  Action = Arbitrate(S1(State), S2(Prompt, K))

Modal Operators:
- Prohibition (F): Strict invariants that immediately reject tool calls before RPC dispatch.
  Rejects attempts targeting OS directories (%WINDIR%, System32, /etc),
  mutation of databases/binaries (*.sqlite, *.exe, *.ps1), reverse shells,
  taint-tracked memory/workspace exfiltration, or violated Z3 resource/deontic bounds.
- Obligation (O): Mandatory actions required by epistemic/deontic rules.
- Permission (P): Safe workspace operations permitted by default.

Invariants:
1. Deterministic AST, MicroScheme S-expression precondition, and Z3 SMT constraint evaluation.
2. Sub-millisecond execution budget for fast-path checks; genuine AST/S-expr/Z3 step gas metering.
3. Zero-Any Rule Compliant (Strictly typed Pydantic & object interfaces).
"""

from __future__ import annotations

import ast
import enum
import re
import time
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field, JsonValue

from lucca.sandbox.policy import TaintFlags

try:
    import z3
    _HAS_Z3 = True
except ImportError:  # pragma: no cover
    z3 = None
    _HAS_Z3 = False


class DeonticNorm(enum.StrEnum):
    PERMITTED = "permitted"
    PROHIBITED = "prohibited"
    OBLIGATORY = "obligatory"


class BDIValidationResult(BaseModel):
    is_valid: bool = Field(description="Whether the candidate tool call is permitted to execute.")
    norm: DeonticNorm = Field(
        description="Deontic classification: PERMITTED, PROHIBITED, or OBLIGATORY."
    )
    reason: str | None = Field(
        default=None, description="Diagnostic justification or rule violation description."
    )
    elapsed_us: float = Field(default=0.0, description="Validation latency in microseconds.")
    gas_used: int = Field(default=0, description="Gas consumed during evaluation.")


FORBIDDEN_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".sqlite", ".db", ".exe", ".dll", ".bat", ".ps1", ".vbs", ".cmd", ".sh", ".sys", ".ini"}
)

SYSTEM_PATH_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"^[A-Za-z]:[/\\](?:windows|system32|program\s*files|programdata|appdata[/\\]local[/\\]microsoft)|"
    r"^/(?:etc|sys|proc|root|bin|sbin|usr[/\\]bin)|"
    r"(?:^|[/\\])(?:windows|system32|winnt)(?:[/\\]|$)"
    r")",
    re.IGNORECASE,
)

TRAVERSAL_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?:\.\.[/\\]|[/\\]\.\.|^\.\.$|\x00|%2e%2e|%2f|%5c)",
    re.IGNORECASE,
)

MALICIOUS_PYTHON_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"System\.Net\.Sockets\.TCPClient|"
    r"socket\.socket\s*\(|"
    r"pty\.spawn|"
    r"/bin/sh\s+-i|"
    r"subprocess\.(?:run|Popen|call)\s*\(\s*\[?['\"](?:powershell|cmd|bash|sh)\b|"
    r"os\.system\s*\(\s*['\"](?:powershell|cmd|bash|sh|rm\s+-rf|del\s+/[fFqQ]|format)\b|"
    r"ctypes\.windll|"
    r"winreg\.|"
    r"shutil\.rmtree\s*\(\s*r?['\"][A-Za-z]:[/\\]windows"
    r")",
    re.IGNORECASE,
)

# Default MicroScheme S-expression deontic preconditions evaluated per tool call
DEFAULT_DEONTIC_SEXPRS: Final[tuple[str, ...]] = (
    '(not (and (tool= "fetch_url") (tainted? "private") (external-url?)))',
    '(not (and (or (tool= "write_file") (tool= "delete_file")) (forbidden-ext?)))',
)

# Resource bound specifications verified via Z3 SMT solver when numeric args are present
NUMERIC_ARG_BOUNDS: Final[dict[str, tuple[float, float]]] = {
    "timeout": (0.01, 300.0),
    "timeout_s": (0.01, 300.0),
    "max_results": (1.0, 100.0),
    "limit": (1.0, 10000.0),
    "port": (1.0, 65535.0),
    "depth": (0.0, 64.0),
    "max_depth": (1.0, 64.0),
    "memory_mb": (1.0, 16384.0),
}

SExprNode = str | list["SExprNode"]


def _parse_sexpr(text: str) -> SExprNode:
    """Lightweight deterministic S-expression parser for deontic preconditions."""
    tokens: list[str] = [str(m) for m in re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text.strip())]
    if not tokens:
        return []
    pos = 0

    def _read() -> SExprNode:
        nonlocal pos
        if pos >= len(tokens):
            return []
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            lst: list[SExprNode] = []
            while pos < len(tokens) and tokens[pos] != ")":
                lst.append(_read())
            if pos < len(tokens) and tokens[pos] == ")":
                pos += 1
            return lst
        if tok.startswith('"') and tok.endswith('"') and len(tok) >= 2:
            return tok[1:-1]
        return tok

    return _read()


class SpeculativeBDIValidator:
    """
    Speculative BDI Invariant Validator (Milestone 4 & WO-39 Milestone 2.4).
    Intercepts candidate tool calls emitted by System 2 (ToolCallEnd)
    before any RPC or OS side-effect occurs.
    """

    def __init__(
        self,
        workspace_root: Path | str = "C:/ProjectLucca/workspace",
        deontic_rules: list[str] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.deontic_sexprs: list[str] = (
            list(deontic_rules) if deontic_rules is not None else list(DEFAULT_DEONTIC_SEXPRS)
        )
        self._parsed_rules: list[SExprNode] = [_parse_sexpr(s) for s in self.deontic_sexprs]

    def add_deontic_rule(self, sexpr: str) -> None:
        """Registers an additional S-expression deontic precondition."""
        self.deontic_sexprs.append(sexpr)
        self._parsed_rules.append(_parse_sexpr(sexpr))

    def _eval_sexpr_node(
        self,
        node: SExprNode,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        taint_flags: int,
        path_arg: str | None,
    ) -> tuple[bool | float | str, int]:
        """Evaluates a parsed S-expression AST node and returns (value, ast_steps_consumed)."""
        if isinstance(node, str):
            try:
                return float(node), 1
            except ValueError:
                return node, 1
        if not node:
            return True, 1

        head = str(node[0]).lower()
        steps = 1

        if head == "not" and len(node) >= 2:
            val, s = self._eval_sexpr_node(node[1], tool_name, tool_args, taint_flags, path_arg)
            return (not bool(val)), steps + s

        if head == "and":
            result = True
            for child in node[1:]:
                val, s = self._eval_sexpr_node(child, tool_name, tool_args, taint_flags, path_arg)
                steps += s
                if not bool(val):
                    result = False
                    break
            return result, steps

        if head == "or":
            result = False
            for child in node[1:]:
                val, s = self._eval_sexpr_node(child, tool_name, tool_args, taint_flags, path_arg)
                steps += s
                if bool(val):
                    result = True
                    break
            return result, steps

        if head == "tool=" and len(node) >= 2:
            target_tool, s = self._eval_sexpr_node(
                node[1], tool_name, tool_args, taint_flags, path_arg
            )
            return (tool_name == str(target_tool)), steps + s

        if head == "tainted?" and len(node) >= 2:
            kind, s = self._eval_sexpr_node(node[1], tool_name, tool_args, taint_flags, path_arg)
            steps += s
            if str(kind).lower() == "private":
                return (
                    bool(
                        taint_flags & (TaintFlags.SENSITIVE_MEMORY | TaintFlags.WORKSPACE_PRIVATE)),
                    steps,
                )
            return bool(taint_flags), steps

        if head == "external-url?":
            url = str(tool_args.get("url", ""))
            is_local = url.startswith("http://127.0.0.1") or url.startswith("http://localhost")
            return (bool(url) and not is_local), steps + 1

        if head == "forbidden-ext?":
            if not path_arg:
                return False, steps + 1
            ext = Path(path_arg).suffix.lower()
            return (ext in FORBIDDEN_EXTENSIONS), steps + 1

        if head == "arg-has?" and len(node) >= 2:
            arg_key, s = self._eval_sexpr_node(node[1], tool_name, tool_args, taint_flags, path_arg)
            return (str(arg_key) in tool_args), steps + s

        if head in ("<=", ">=", "<", ">", "=") and len(node) >= 3:
            lhs_Key, s1 = self._eval_sexpr_node(node[1], tool_name, tool_args, taint_flags,
                path_arg)
            rhs_val, s2 = self._eval_sexpr_node(node[2], tool_name, tool_args, taint_flags,
                path_arg)
            steps += s1 + s2
            raw_arg = tool_args.get(str(lhs_Key), lhs_Key)
            try:
                lv = float(raw_arg)  # type: ignore[arg-type]
                rv = float(rhs_val)
            except (TypeError, ValueError):
                return True, steps
            if head == "<=":
                return lv <= rv, steps
            if head == ">=":
                return lv >= rv, steps
            if head == "<":
                return lv < rv, steps
            if head == ">":
                return lv > rv, steps
            return lv == rv, steps

        return True, steps

    def _inspect_python_ast(self, code: str) -> tuple[bool, str | None, int]:
        """Walks the Python AST to detect host-escape calls and meter actual AST node complexity."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return True, None, 2

        node_count = 0
        for node in ast.walk(tree):
            node_count += 1
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    func_name = f"{node.func.value.id}.{node.func.attr}"
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id
                if func_name in ("pty.spawn", "socket.socket", "ctypes.windll"):
                    return (
                        False,
                        f"Host escape or forbidden system call '{func_name}' detected in AST",
                        node_count,
                    )
            elif isinstance(node, ast.While):
                is_const_true = isinstance(node.test,
                    ast.Constant) and bool(node.test.value) is True
                if is_const_true:
                    has_exit = any(
                        isinstance(sub, (ast.Break, ast.Return, ast.Raise))
                        for stmt in node.body
                        for sub in ast.walk(stmt)
                    )
                    if not has_exit:
                        return (
                            False,
                            "Unbounded infinite 'while True' loop without break/return "
                                "detected in AST",
                            node_count,
                        )
        return True, None, max(1, node_count)

    def verify_z3_constraints(
        self,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        taint_flags: int = 0,
    ) -> tuple[bool, str | None, int]:
        """
        Evaluates numeric resource bounds and symbolic deontic constraints via Z3 SMT solver.
        Returns (is_satisfiable, violation_reason, z3_steps_used).
        """
        numeric_Automatic: list[tuple[str, float, float, float]] = []
        for k, (lo, hi) in NUMERIC_ARG_BOUNDS.items():
            if k in tool_args and isinstance(tool_args[k], (int, float)) and not isinstance(
                tool_args[k], bool
            ):
                numeric_Automatic.append((k, float(tool_args[k]), lo, hi))  # type: ignore[arg-type]

        has_private_taint = bool(
            taint_flags & (TaintFlags.SENSITIVE_MEMORY | TaintFlags.WORKSPACE_PRIVATE)
        )
        is_fetch = tool_name == "fetch_url"

        if not numeric_Automatic and not (is_fetch and has_private_taint):
            return True, None, 0

        if not _HAS_Z3 or z3 is None:
            steps = 0
            for k, val, lo, hi in numeric_Automatic:
                steps += 2
                if not (lo <= val <= hi):
                    return (
                        False,
                        f"Resource bound constraint violated for '{
                            k}={val}' (allowed [{lo}, {hi}])",
                        steps,
                    )
            return True, None, steps

        solver = z3.Solver()
        solver.set("timeout", 20)
        z3_steps = 1

        if is_fetch:
            url = str(tool_args.get("url", ""))
            is_ext = bool(url) and not (
                url.startswith("http://127.0.0.1") or url.startswith("http://localhost")
            )
            taint_var = z3.Bool("tainted_private")
            egress_var = z3.Bool("external_egress")
            solver.add(taint_var == z3.BoolVal(has_private_taint))
            solver.add(egress_var == z3.BoolVal(is_ext))
            solver.add(z3.Implies(taint_var, z3.Not(egress_var)))
            z3_steps += 3
            if solver.check() == z3.unsat:
                return (
                    False,
                    "Outbound network egress prohibited while session context contains tainted "
                        "memory or workspace data",
                    z3_steps,
                )

        for k, val, lo, hi in numeric_Automatic:
            var = z3.Real(f"arg_{k}")
            solver.push()
            solver.add(var == z3.RealVal(val))
            solver.add(var >= z3.RealVal(lo))
            solver.add(var <= z3.RealVal(hi))
            z3_steps += 3
            if solver.check() == z3.unsat:
                solver.pop()
                return (
                    False,
                    f"Z3 resource-bound constraint violated: {k}={val} outside [{lo}, {hi}]",
                    z3_steps,
                )
            solver.pop()

        return True, None, z3_steps

    def validate_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        taint_flags: int = 0,
        inquiry_text: str | None = None,
    ) -> BDIValidationResult:
        """
        Speculatively validates a candidate tool call against deontic invariants,
        MicroScheme S-expression preconditions, and Z3 resource-bound constraints.
        """
        t0 = time.perf_counter()
        gas_used = 0

        # 1. Path Containment Invariants (Prohibition)
        path_arg = self._extract_path_argument(tool_args)
        if path_arg:
            gas_used += 1
            if TRAVERSAL_REGEX.search(path_arg):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=f"Path traversal or invalid sequence detected in argument: {path_arg!r}",
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )

            gas_used += 1
            if SYSTEM_PATH_REGEX.search(path_arg):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=f"Access to protected system directory prohibited: {path_arg!r}",
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )

            # 2. Mutation Invariants on Sensitive File Extensions (Prohibition)
            if tool_name in ("write_file", "delete_file"):
                gas_used += 1
                ext = Path(path_arg).suffix.lower()
                if ext in FORBIDDEN_EXTENSIONS:
                    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                    return BDIValidationResult(
                        is_valid=False,
                        norm=DeonticNorm.PROHIBITED,
                        reason=(
                            f"Direct modification of sensitive file format '{ext}' is prohibited"
                        ),
                        elapsed_us=elapsed_us,
                        gas_used=gas_used,
                    )

        # 3. Malicious Code & Host-Escape Invariant in run_python (Regex + AST walk)
        if tool_name == "run_python":
            code = str(tool_args.get("code", ""))
            gas_used += 1
            if code and MALICIOUS_PYTHON_REGEX.search(code):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=(
                        "Host escape, socket reverse-shell, or destructive system call "
                        "detected in python script"
                    ),
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )
            if code:
                ast_ok, ast_reason, ast_steps = self._inspect_python_ast(code)
                gas_used += ast_steps
                if not ast_ok:
                    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                    return BDIValidationResult(
                        is_valid=False,
                        norm=DeonticNorm.PROHIBITED,
                        reason=ast_reason,
                        elapsed_us=elapsed_us,
                        gas_used=gas_used,
                    )

        # 4. MicroScheme S-Expression Deontic Preconditions
        extra_preconds = tool_args.get("_preconditions")
        rules_to_eval = list(self._parsed_rules)
        if isinstance(extra_preconds, str) and extra_preconds.strip():
            rules_to_eval.append(_parse_sexpr(extra_preconds))
        elif isinstance(extra_preconds, list):
            for p_str in extra_preconds:
                if isinstance(p_str, str) and p_str.strip():
                    rules_to_eval.append(_parse_sexpr(p_str))

        for parsed_rule in rules_to_eval:
            ok_val, rule_steps = self._eval_sexpr_node(
                parsed_rule, tool_name, tool_args, taint_flags, path_arg
            )
            gas_used += rule_steps
            if not bool(ok_val):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                if tool_name == "fetch_url":
                    reason_msg = (
                        "Outbound network egress prohibited while session context "
                        "contains tainted memory or workspace data"
                    )
                else:
                    reason_msg = "MicroScheme deontic S-expression precondition violated"
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=reason_msg,
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )

        # 5. Z3 SMT Resource-Bound & Deontic Verification
        z3_ok, z3_reason, z3_steps = self.verify_z3_constraints(
            tool_name, tool_args, taint_flags=taint_flags
        )
        gas_used += z3_steps
        if not z3_ok:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return BDIValidationResult(
                is_valid=False,
                norm=DeonticNorm.PROHIBITED,
                reason=z3_reason,
                elapsed_us=elapsed_us,
                gas_used=gas_used,
            )

        # 6. Hardware Query Epistemic Obligation (Obligation)
        if inquiry_text:
            gas_used += 1
            lower_inquiry = inquiry_text.lower()
            is_hardware_inquiry = any(
                hw in lower_inquiry
                for hw in ("gpu", "vram", "cpu load", "ram amount", "workstation hardware")
            )
            if is_hardware_inquiry and tool_name not in ("query_capabilities", "list_dir"):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=True,
                    norm=DeonticNorm.OBLIGATORY,
                    reason="Hardware state inquiry obligates querying live hardware telemetry",
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )

        gas_used = max(1, gas_used)
        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        return BDIValidationResult(
            is_valid=True,
            norm=DeonticNorm.PERMITTED,
            reason="Tool call satisfies all speculative deontic invariants",
            elapsed_us=elapsed_us,
            gas_used=gas_used,
        )

    def _extract_path_argument(self, tool_args: dict[str, JsonValue]) -> str | None:
        """Extracts the primary path or target argument from tool parameters."""
        for key in ("path", "rel_path", "target", "file", "filename"):
            if key in tool_args and isinstance(tool_args[key], str):
                return str(tool_args[key]).strip()
        return None
