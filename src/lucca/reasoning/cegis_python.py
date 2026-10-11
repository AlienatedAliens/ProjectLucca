"""
Project Lucca — Counter-Example Guided Inductive Synthesis (CEGIS) for General Python
Work Order 35 (WO-35 Milestone 35.1)

Provides an autonomous, multi-turn self-repair synthesis loop:
1. Turn 1: Synthesize initial candidate Python program.
2. Preflight verification & repair via AST sanitizer.
3. Hardened Docker container execution (lucca-file-sandbox) via DockerRPCTransport.
4. Failure extraction: captures exception type, line, traceback, and failed assertions.
5. Turn 2..K: Feeds failure state to LLM with structured CEGIS repair prompt.
6. Returns verified solution or structured failure artifact.

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import time
from typing import Final

import httpx
import structlog

from lucca.sandbox.preflight import extract_python_code
from lucca.sandbox.rpc import DockerRPCTransport

logger = structlog.get_logger(__name__)

DEFAULT_CONTAINER: Final[str] = "lucca-file-sandbox"
DEFAULT_TIMEOUT_S: Final[float] = 10.0
DEFAULT_MAX_TURNS: Final[int] = 3


@dataclass(frozen=True)
class CEGISTrace:
    """Audit record for a single synthesis / execution turn."""

    turn: int
    code: str
    ok_exec: bool
    stdout: str
    stderr: str
    error_type: str | None
    error_message: str | None
    elapsed_ms: float


@dataclass(frozen=True)
class CEGISResult:
    """Final outcome of the multi-turn CEGIS synthesis loop."""

    success: bool
    final_code: str | None
    predicted_output: str | None
    turns_taken: int
    method: str  # "VERIFIED_PROGRAM" | "VERIFIED_REPAIRED_PROGRAM" | "INTERNAL_FALLBACK"
    failure_stage: str | None
    traces: list[CEGISTrace] = field(default_factory=list)
    total_elapsed_ms: float = 0.0


def parse_python_exception(stderr_text: str) -> tuple[str | None, str | None]:
    """Extracts the Python exception type and message from a standard traceback string."""
    if not stderr_text:
        return None, None
    lines = [line.strip() for line in stderr_text.strip().splitlines() if line.strip()]
    if not lines:
        return None, None
    last_line = lines[-1]
    match = re.match(r"^([A-Za-z_]\w*Error|[A-Za-z_]\w*Exception|AssertionError):\s*(.*)$", last_line)
    if match:
        return match.group(1), match.group(2)
    # Generic error line
    if "Error" in last_line:
        parts = last_line.split(":", 1)
        err_type = parts[0].strip()
        err_msg = parts[1].strip() if len(parts) > 1 else ""
        return err_type, err_msg
    return None, last_line


class PythonCEGISEngine:
    """Autonomous Counter-Example Guided Inductive Synthesis engine for Python."""

    def __init__(
        self,
        container_name: str = DEFAULT_CONTAINER,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_turns: int = DEFAULT_MAX_TURNS,
        server_url: str = "http://127.0.0.1:8080/v1/chat/completions",
    ) -> None:
        self.container_name = container_name
        self.timeout_s = timeout_s
        self.max_turns = max_turns
        self.server_url = server_url
        self._rpc: DockerRPCTransport | None = None

    def _get_rpc(self) -> DockerRPCTransport:
        if self._rpc is None:
            self._rpc = DockerRPCTransport(
                container_name=self.container_name, use_direct_fallback=False
            )
            if not self._rpc.is_container_running():
                self._rpc.ensure_container_running()
            # Warm up persistent worker
            try:
                self._rpc.execute(
                    call_id="cegis-warmup",
                    tool="run_python",
                    args={"code": "pass"},
                    timeout_s=15.0,
                )
            except Exception as e:
                logger.warning("cegis_docker_warmup_failed", error=str(e))
        return self._rpc

    def _query_llm(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> tuple[str, str]:
        """Queries LLM server, returning (content, finish_reason)."""
        payload: dict[str, object] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(self.server_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            content = str(choice["message"].get("content") or "").strip()
            finish = str(choice.get("finish_reason") or "stop")
            return content, finish

    def _execute_code(self, code: str) -> tuple[bool, str, str]:
        """Executes Python code in Docker container."""
        try:
            rpc = self._get_rpc()
            call_id = f"cegis-{time.time_ns()}"
            res = rpc.execute(
                call_id=call_id,
                tool="run_python",
                args={"code": code},
                timeout_s=self.timeout_s,
            )
            if res.ok:
                return True, str(res.content or "").strip(), ""
            err = str(res.stderr or res.content or "execution_failed").strip()
            return False, "", err
        except Exception as e:
            logger.warning("cegis_docker_execution_exception", error=str(e))
            return False, "", f"{type(e).__name__}: {e}"

    def synthesize_and_repair(
        self,
        task_prompt: str,
        system_prompt: str | None = None,
        test_harness: str | None = None,
        output_pattern: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> CEGISResult:
        """
        Runs the full CEGIS loop:
        1. Turn 1 synthesis from task_prompt.
        2. Execution in Docker sandbox.
        3. If failure, iterative repair using error traceback & state diffs.
        """
        t0 = time.perf_counter()
        traces: list[CEGISTrace] = []

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": task_prompt})

        last_code: str | None = None
        predicted_out: str | None = None
        failure_stage: str | None = None

        for turn in range(1, self.max_turns + 1):
            t_turn = time.perf_counter()
            content, finish_reason = self._query_llm(
                messages=messages,
                temperature=temperature if turn == 1 else min(0.3, temperature + 0.1),
                max_tokens=max_tokens,
            )

            code = extract_python_code(content)
            if not code:
                # No code extracted from response
                elapsed_ms = (time.perf_counter() - t_turn) * 1000.0
                trace = CEGISTrace(
                    turn=turn,
                    code="",
                    ok_exec=False,
                    stdout="",
                    stderr="No valid Python code found in output",
                    error_type="TranslationError",
                    error_message="No code block extracted",
                    elapsed_ms=elapsed_ms,
                )
                traces.append(trace)
                failure_stage = "TRANSLATION_NO_CODE"

                # Prompt model to format as code block
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        "Error: No Python code block was detected. "
                        "Please write your complete executable solution in a ```python ... ``` block."
                    ),
                })
                continue

            last_code = code

            # Full executable snippet includes test harness if provided
            full_exec_code = code
            if test_harness and test_harness.strip() not in code:
                full_exec_code = f"{code}\n\n# --- Verification Harness ---\n{test_harness}"

            ok_exec, stdout_val, stderr_val = self._execute_code(full_exec_code)
            elapsed_ms = (time.perf_counter() - t_turn) * 1000.0

            err_type, err_msg = parse_python_exception(stderr_val) if not ok_exec else (None, None)

            trace = CEGISTrace(
                turn=turn,
                code=full_exec_code,
                ok_exec=ok_exec,
                stdout=stdout_val,
                stderr=stderr_val,
                error_type=err_type,
                error_message=err_msg,
                elapsed_ms=elapsed_ms,
            )
            traces.append(trace)

            if ok_exec:
                # Execution succeeded!
                if output_pattern:
                    match = re.search(output_pattern, stdout_val)
                    if match:
                        predicted_out = match.group(1) if match.groups() else match.group(0)
                    else:
                        predicted_out = stdout_val
                else:
                    predicted_out = stdout_val

                total_elapsed = (time.perf_counter() - t0) * 1000.0
                method = "VERIFIED_PROGRAM" if turn == 1 else "VERIFIED_REPAIRED_PROGRAM"
                logger.info(
                    "cegis_synthesis_success",
                    turn=turn,
                    method=method,
                    predicted=predicted_out,
                    elapsed_ms=total_elapsed,
                )
                return CEGISResult(
                    success=True,
                    final_code=full_exec_code,
                    predicted_output=predicted_out,
                    turns_taken=turn,
                    method=method,
                    failure_stage=None,
                    traces=traces,
                    total_elapsed_ms=total_elapsed,
                )

            # Execution failed — formulate CEGIS feedback for repair turn
            logger.info(
                "cegis_execution_failure",
                turn=turn,
                error_type=err_type,
                error_message=err_msg,
                stderr_snippet=stderr_val[:120],
            )

            if "TimeoutError" in stderr_val or "timed out" in stderr_val.lower():
                failure_stage = "SANDBOX_TIMEOUT_OR_RESOURCE_LIMIT"
            else:
                failure_stage = "EXECUTION_RUNTIME_ERROR"

            if turn < self.max_turns:
                # Construct autonomous repair prompt
                repair_prompt = (
                    f"Your Python code produced a runtime error when executed in the sandbox:\n\n"
                    f"[Error Type]: {err_type or 'RuntimeError'}\n"
                    f"[Error Message]: {err_msg or stderr_val.strip()}\n"
                    f"[Traceback / Stderr]:\n{stderr_val.strip()[-600:]}\n\n"
                    f"Please analyze the cause of this failure, fix the issue, and provide "
                    f"the complete corrected Python script.\n"
                    f"Output ONLY executable Python inside a ```python ... ``` block."
                )
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": repair_prompt})

        # All repair turns exhausted
        total_elapsed = (time.perf_counter() - t0) * 1000.0
        logger.warning(
            "cegis_synthesis_exhausted",
            max_turns=self.max_turns,
            failure_stage=failure_stage,
            total_elapsed_ms=total_elapsed,
        )
        return CEGISResult(
            success=False,
            final_code=last_code,
            predicted_output=None,
            turns_taken=self.max_turns,
            method="INTERNAL_FALLBACK",
            failure_stage=failure_stage or "LLM_REASONING_LOGIC",
            traces=traces,
            total_elapsed_ms=total_elapsed,
        )
