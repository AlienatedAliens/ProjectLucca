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
        num_candidates: int = 1,
    ) -> None:
        self.container_name = container_name
        self.timeout_s = timeout_s
        self.max_turns = max_turns
        self.server_url = server_url
        self.num_candidates = num_candidates
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
        max_tokens: int = 1024,
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

    @staticmethod
    def _extract_output_pattern(stdout_val: str, output_pattern: str | None) -> str:
        text = stdout_val.strip()
        if not text or not output_pattern:
            return text
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        target_line = lines[-1] if lines else text
        matches = list(re.finditer(output_pattern, target_line))
        if not matches:
            matches = list(re.finditer(output_pattern, text))
        if matches:
            m = matches[-1]
            return m.group(1) if m.groups() else m.group(0)
        return text

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

    def synthesize_checked_formalization(
        self,
        task_prompt: str,
        output_pattern: str | None = None,
    ) -> "CEGISResult":
        """
        Checked Formalization via Dual-Formulation Agreement (Peer Review Q1.2 & Q3).

        Generates two independent formulations of the problem:
        1. Path A (Symbolic / Algebraic): Extracts givens, unknowns, and relations into
           structured comments, then solves via exact symbolic algebra (SymPy / Z3).
        2. Path B (Brute-Force / Small-Case Verification): Solves or checks via direct
           numerical enumeration / brute-force simulation in Python.

        If both formulations execute cleanly in the Docker sandbox and produce identical
        non-empty answers, the answer is accepted with high confidence
        (method='CHECKED_FORMALIZATION_AGREED').
        If they disagree or either fails execution, escalates to synthesize_parallel(n_candidates=3)
        to resolve via diversified sampling.
        """
        t0 = time.perf_counter()
        prompt_symbolic = (
            "You are a formal mathematical verification engineer.\n"
            "Step 1: In Python comments (# Given: ..., # Unknown: ..., # Relation: ...), "
            "explicitly list the extracted givens, unknowns, and algebraic/logical relations.\n"
            "Step 2: Write a Python script using `sympy` or `z3` (exact symbolic computation) "
            "to solve the problem and print ONLY the final answer.\n"
            "Return ONLY a ```python ... ``` block."
        )
        prompt_bruteforce = (
            "You are an algorithmic verification engineer.\n"
            "Write a self-contained Python script that solves or verifies the problem using "
            "direct numerical simulation, case enumeration, or brute-force search (avoiding "
            "unverified algebraic shortcuts), and prints ONLY the final answer.\n"
            "Return ONLY a ```python ... ``` block."
        )

        traces: list[CEGISTrace] = []
        outputs: list[tuple[str, str, str]] = []  # (label, predicted_out, full_code)

        for idx, (label, sys_p, temp) in enumerate(
            [
                ("SYMBOLIC", prompt_symbolic, 0.1),
                ("BRUTE_FORCE", prompt_bruteforce, 0.2),
            ],
            start=1,
        ):
            t_cand = time.perf_counter()
            msgs = [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": task_prompt},
            ]
            content, _ = self._query_llm(messages=msgs, temperature=temp, max_tokens=1024)
            code = extract_python_code(content) or ""
            ok_exec, stdout_val, stderr_val = False, "", "No code extracted"
            if code:
                if "print" not in code and "ans" in code:
                    code = f"{code}\nprint(ans)"
                ok_exec, stdout_val, stderr_val = self._execute_code(code)

            elapsed_ms = (time.perf_counter() - t_cand) * 1000.0
            err_t, err_m = (None, None) if ok_exec else self._parse_err(stderr_val)
            traces.append(
                CEGISTrace(
                    turn=idx,
                    code=code,
                    ok_exec=ok_exec,
                    stdout=stdout_val,
                    stderr=stderr_val,
                    error_type=err_t,
                    error_message=err_m,
                    elapsed_ms=elapsed_ms,
                )
            )
            if ok_exec and stdout_val.strip():
                pred = self._extract_output_pattern(stdout_val, output_pattern)
                outputs.append((label, pred.strip(), code))

        # Check dual-formulation agreement
        if len(outputs) == 2 and outputs[0][1] == outputs[1][1] and outputs[0][1] != "":
            total_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                "cegis_checked_formalization_agreed",
                agreed_output=outputs[0][1],
                elapsed_ms=total_ms,
            )
            return CEGISResult(
                success=True,
                final_code=outputs[0][2],
                predicted_output=outputs[0][1],
                turns_taken=2,
                method="CHECKED_FORMALIZATION_AGREED",
                failure_stage=None,
                traces=traces,
                total_elapsed_ms=total_ms,
            )

        # Disagreement or execution failure -> escalate to parallel candidate sampling
        logger.info(
            "cegis_checked_formalization_disagreed_escalating",
            outputs=[o[1] for o in outputs],
        )
        esc_res = self.synthesize_parallel(
            task_prompt=task_prompt,
            output_pattern=output_pattern,
            n_candidates=max(3, self.num_candidates),
        )
        if esc_res.success and esc_res.predicted_output and esc_res.predicted_output.strip():
            return esc_res
        if len(outputs) == 1 and outputs[0][1]:
            total_ms = (time.perf_counter() - t0) * 1000.0
            return CEGISResult(
                success=True,
                final_code=outputs[0][2],
                predicted_output=outputs[0][1],
                turns_taken=len(traces) + esc_res.turns_taken,
                method=f"CHECKED_FORMALIZATION_SINGLE_{outputs[0][0]}",
                failure_stage=None,
                traces=traces + esc_res.traces,
                total_elapsed_ms=total_ms,
            )
        return esc_res

    def synthesize_parallel(
        self,
        task_prompt: str,
        system_prompt: str | None = None,
        test_harness: str | None = None,
        output_pattern: str | None = None,
        n_candidates: int | None = None,
    ) -> "CEGISResult":
        """
        Diversified parallel candidate sampling (peer-review directive Q2 / Q5).

        Samples n_candidates (default: self.num_candidates, min 1) independent
        synthesis attempts using diverse strategy-hinting system prompts and
        stochastic temperatures (T=0.6–0.9). Candidates are executed in the Docker
        sandbox and the first verified solution is returned immediately.

        If no candidate executes successfully, falls back to synthesize_and_repair()
        with the greedy T=0.1 baseline to preserve backward compatibility.

        This escapes the greedy top_k=1 trap: if Turn 1's algorithmic strategy
        is wrong, no single repair chain can escape it. N=3 diversified candidates
        each start from a fresh formulation angle.
        """
        n = n_candidates if n_candidates is not None else self.num_candidates
        if n <= 1:
            return self.synthesize_and_repair(
                task_prompt=task_prompt,
                system_prompt=system_prompt,
                test_harness=test_harness,
                output_pattern=output_pattern,
            )

        # Diverse strategy hints — each nudges the LLM toward a different
        # algorithmic approach so candidates aren't just temperature-varied clones.
        STRATEGY_HINTS = [
            "Use a direct mathematical / algebraic formula where possible.",
            "Use simulation or step-by-step enumeration to derive the answer.",
            "Use SymPy or built-in Python arithmetic; avoid manual loops if possible.",
            "Use brute-force search with explicit case enumeration.",
            "Translate the problem into a constraint and solve via conditional logic.",
        ]

        t0 = time.perf_counter()
        candidate_results: list["CEGISResult"] = []

        for i in range(n):
            hint = STRATEGY_HINTS[i % len(STRATEGY_HINTS)]
            if system_prompt:
                aug_system = f"{system_prompt}\nStrategy hint: {hint}"
            else:
                aug_system = (
                    "You are an expert Python programmer solving computational tasks.\n"
                    f"Strategy hint: {hint}"
                )
            # Stochastic temperature schedule: spread T over [0.5, 0.9]
            temp = 0.5 + 0.1 * i

            messages: list[dict[str, str]] = [
                {"role": "system", "content": aug_system},
                {"role": "user", "content": task_prompt},
            ]

            t_cand = time.perf_counter()
            content, _ = self._query_llm(messages=messages, temperature=temp, max_tokens=1024)
            code = None
            try:
                from lucca.sandbox.preflight import extract_python_code
                code = extract_python_code(content)
            except (ImportError, AttributeError) as _extract_err:
                logger.debug("cegis_parallel_extract_failed", candidate=i, error=str(_extract_err))

            ok_exec, stdout_val, stderr_val = False, "", "No code extracted"
            if code:
                full_exec = code
                if test_harness and test_harness.strip() not in code:
                    full_exec = f"{code}\n\n# --- Verification Harness ---\n{test_harness}"
                if "print" not in full_exec and "ans" in full_exec:
                    full_exec = f"{full_exec}\nprint(ans)"
                ok_exec, stdout_val, stderr_val = self._execute_code(full_exec)
            else:
                full_exec = ""

            elapsed_cand = (time.perf_counter() - t_cand) * 1000.0
            err_type, err_msg = (None, None) if ok_exec else (
                (lambda p: (p[0], p[1]))(self._parse_err(stderr_val))
            )

            trace = CEGISTrace(
                turn=i + 1,
                code=full_exec,
                ok_exec=ok_exec,
                stdout=stdout_val,
                stderr=stderr_val,
                error_type=err_type,
                error_message=err_msg,
                elapsed_ms=elapsed_cand,
            )

            predicted_out: str | None = None
            if ok_exec:
                predicted_out = self._extract_output_pattern(stdout_val, output_pattern)

            result = CEGISResult(
                success=ok_exec,
                final_code=full_exec if code else None,
                predicted_output=predicted_out,
                turns_taken=1,
                method=f"PARALLEL_CANDIDATE_{i + 1}",
                failure_stage=None if ok_exec else "CANDIDATE_EXECUTION_FAILED",
                traces=[trace],
                total_elapsed_ms=elapsed_cand,
            )
            candidate_results.append(result)

            if ok_exec and (bool(stdout_val.strip()) or bool(test_harness)):
                logger.info(
                    "cegis_parallel_candidate_success",
                    candidate=i + 1,
                    n_total=n,
                    elapsed_ms=elapsed_cand,
                )
                return result

        # No candidate succeeded — fall back to repair loop on the original prompt
        logger.warning(
            "cegis_parallel_all_failed",
            n_candidates=n,
            total_elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )
        return self.synthesize_and_repair(
            task_prompt=task_prompt,
            system_prompt=system_prompt,
            test_harness=test_harness,
            output_pattern=output_pattern,
            temperature=0.1,
        )

    def _parse_err(self, stderr_text: str) -> tuple[str | None, str | None]:
        """Thin wrapper so synthesize_parallel can reuse exception parsing."""
        return parse_python_exception(stderr_text)

    def synthesize_and_repair(
        self,
        task_prompt: str,
        system_prompt: str | None = None,
        test_harness: str | None = None,
        output_pattern: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        exemplar_messages: list[dict[str, str]] | None = None,
    ) -> CEGISResult:
        """
        Runs the full CEGIS loop:
        1. Turn 1 synthesis from task_prompt or exemplar_messages.
        2. Execution in Docker sandbox.
        3. If failure, iterative repair using error traceback & state diffs.
        """
        t0 = time.perf_counter()
        traces: list[CEGISTrace] = []

        messages: list[dict[str, str]] = []
        if exemplar_messages:
            messages.extend(exemplar_messages)
        else:
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
            if "print" not in full_exec_code and "ans" in full_exec_code:
                full_exec_code = f"{full_exec_code}\nprint(ans)"

            ok_exec, stdout_val, stderr_val = self._execute_code(full_exec_code)
            elapsed_ms = (time.perf_counter() - t_turn) * 1000.0

            if ok_exec and not test_harness:
                if not stdout_val.strip() or "<built-in function" in stdout_val:
                    ok_exec = False
                    stderr_val = "EmptyOutputError: Code executed with exit code 0 but printed no output to stdout. Call print(final_answer) at the end."
                elif output_pattern and not re.search(output_pattern, stdout_val):
                    ok_exec = False
                    stderr_val = f"OutputFormatError: Stdout {stdout_val.strip()[:80]!r} did not match required pattern {output_pattern!r}. Print ONLY the final answer."

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
                predicted_out = self._extract_output_pattern(stdout_val, output_pattern)

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
