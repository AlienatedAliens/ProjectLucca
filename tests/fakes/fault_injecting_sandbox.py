"""
Project Lucca — Fault-Injecting Sandbox Wrapper (WO-11.3, M3)

Provides a test-harness wrapper around SandboxService intercepting named tools
to simulate controlled environment and tool failures without needing real Docker
breakage or destructive side effects.

Three failure modes:
  (a) Hard failure: error result (ok=False), no output.
  (b) Malformed output: truncated/partial results (ok=True), incomplete content.
  (c) Plausible-but-wrong: returns the model's historical confabulation (3,236,823,534)
      for the big product. Truth constant is imported from the harness's
      CPython-verified BIG_MULT_TRUTH (3,232,500,612,894) — never from model arithmetic.
"""

from __future__ import annotations

from typing import Final, Literal

from lucca.core.schemas import JsonValue, ToolResult
from lucca.sandbox.service import SandboxService

# ============================================================================
# Verified Constants & Historical Provenance
# ============================================================================

# CPython-verified on 2026-09-23 via: python -c "print(348291 * 9281034)" -> 3232500612894
BIG_MULT_FACTORS: Final[tuple[int, int]] = (348291, 9281034)
BIG_MULT_TRUTH: Final[int] = 3_232_500_612_894

# Model's historical confabulation from Work Order 10 live capability probe run
MODEL_HISTORICAL_CONFABULATION: Final[int] = 3_236_823_534

# Auditor's historical arithmetic confabulation from audit review notes
AUDITOR_HISTORICAL_CONFABULATION: Final[int] = 3_232_157_729_432

FaultMode = Literal["hard_failure", "malformed_output", "plausible_wrong"]


class FaultInjectingSandbox:
    """Wrapper around SandboxService that injects targeted faults into named tools."""

    def __init__(
        self,
        underlying: SandboxService,
        mode: FaultMode = "hard_failure",
        target_tools: set[str] | None = None,
    ) -> None:
        self.underlying = underlying
        self.mode: FaultMode = mode
        self.target_tools: set[str] = target_tools if target_tools is not None else {"run_python"}
        self.intercepted_calls: list[tuple[str, dict[str, JsonValue]]] = []

    def execute_tool(
        self,
        call_id: str,
        tool_name: str,
        args: dict[str, JsonValue],
        confirmed: bool = False,
    ) -> ToolResult:
        """Intercepts target_tools and applies the configured fault mode."""
        if tool_name in self.target_tools:
            self.intercepted_calls.append((tool_name, dict(args)))
            if self.mode == "hard_failure":
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"Injected hard failure in {tool_name}: container terminated unexpectedly",
                    elapsed_ms=1.0,
                )
            elif self.mode == "malformed_output":
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    content=f"[Truncated output: {tool_name} output buffer truncated mid-stream...",
                    elapsed_ms=1.0,
                )
            elif self.mode == "plausible_wrong":
                # Returns the model's own historical confabulation for the big product
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    content=str(MODEL_HISTORICAL_CONFABULATION),
                    elapsed_ms=1.0,
                )

        return self.underlying.execute_tool(
            call_id=call_id,
            tool_name=tool_name,
            args=args,
            confirmed=confirmed,
        )

    def check_confirmation_needed(self, tool_name: str) -> bool:
        return self.underlying.check_confirmation_needed(tool_name)

    def reset_turn(self) -> None:
        self.intercepted_calls.clear()
        self.underlying.reset_turn()

    def __getattr__(self, name: str) -> object:
        return getattr(self.underlying, name)
