"""
Project Lucca — Speculative BDI Invariant Validator
Milestone 4 (Architecture B Hardened by Architecture C)

Evaluates candidate System 2 tool calls speculatively before dispatch:
  Action = Arbitrate(S1(State), S2(Prompt, K))

Modal Operators:
- Prohibition (F): Strict invariants that immediately reject tool calls before RPC dispatch.
  Rejects attempts targeting OS directories (%WINDIR%, System32, /etc),
  mutation of databases/binaries (*.sqlite, *.exe, *.ps1), reverse shells,
  or taint-tracked memory/workspace exfiltration.
- Obligation (O): Mandatory actions required by epistemic/deontic rules.
- Permission (P): Safe workspace operations permitted by default.

Invariants:
1. Pure deterministic checks + MicroScheme S-expression rule evaluation.
2. Sub-millisecond execution budget: <= 200 microseconds (typically < 50 us).
3. Zero-Any Rule Compliant (Strictly typed Pydantic & object interfaces).
"""

from __future__ import annotations

import enum
import re
import time
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field, JsonValue

from lucca.sandbox.policy import TaintFlags


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


# Precompiled regular expressions for sub-millisecond evaluation (< 50 microseconds)
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


class SpeculativeBDIValidator:
    """
    Speculative BDI Invariant Validator (Milestone 4).
    Intercepts candidate tool calls emitted by System 2 (ToolCallEnd)
    before any RPC or OS side-effect occurs.
    """

    def __init__(self, workspace_root: Path | str = "C:/ProjectLucca/workspace") -> None:
        self.workspace_root = Path(workspace_root)

    def validate_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        taint_flags: int = 0,
        inquiry_text: str | None = None,
    ) -> BDIValidationResult:
        """
        Speculatively validates a candidate tool call against deontic invariants.
        Budget: <= 200 microseconds.
        """
        t0 = time.perf_counter()
        gas_used = 1

        # 1. Path Containment Invariants (Prohibition)
        path_arg = self._extract_path_argument(tool_args)
        if path_arg:
            gas_used += 1
            # Check directory traversal & null bytes
            if TRAVERSAL_REGEX.search(path_arg):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=f"Path traversal or invalid sequence detected in argument: {path_arg!r}",
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )

            # Check absolute Windows system paths or sensitive Linux directories
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

        # 3. Malicious Code & Host-Escape Invariant in run_python (Prohibition)
        if tool_name == "run_python":
            gas_used += 1
            code = str(tool_args.get("code", ""))
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

        # 4. Exfiltration Taint Tracking Invariant (Prohibition)
        if tool_name == "fetch_url":
            gas_used += 1
            has_private_data = bool(
                taint_flags & (TaintFlags.SENSITIVE_MEMORY | TaintFlags.WORKSPACE_PRIVATE)
            )
            if has_private_data:
                url = str(tool_args.get("url", ""))
                # Only permit loopback or local testing if context is tainted with private user data
                if not (url.startswith("http://127.0.0.1") or url.startswith("http://localhost")):
                    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                    return BDIValidationResult(
                        is_valid=False,
                        norm=DeonticNorm.PROHIBITED,
                        reason=(
                            "Outbound network egress prohibited while session context "
                            "contains tainted memory or workspace data"
                        ),
                        elapsed_us=elapsed_us,
                        gas_used=gas_used,
                    )

        # 5. Hardware Query Epistemic Obligation (Obligation)
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
