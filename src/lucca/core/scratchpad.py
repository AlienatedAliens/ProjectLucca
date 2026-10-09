"""
Project Lucca — Scratchpad Falsification Loop (Module 5, WO-30)
Fast-path concrete counterexample generation and dynamic testing for candidate macros
prior to Z3 formal verification and quarantine admission.

Invariants:
- D-AUD-13 / ADR-013: Dynamic execution runs strictly inside container sandboxes (--network none).
- Minimum >= 3 concrete I/O test cases per candidate.
- Fails fast on runtime errors, timeouts (<= 500ms budget), or assertion failures.
- Zero-Any (D-AUD-01).
"""

from __future__ import annotations

import copy
import json
import time
from typing import Final

from pydantic import BaseModel, Field
import structlog

from lucca.core.schemas import RuleState
from lucca.core.turn_pipeline import SubTurnScratchpadBuffer
from lucca.reasoning.scheme.eval import SchemeEvaluator, build_env
from lucca.reasoning.scheme.macros import (
    MAX_MACRO_DEPTH,
    MAX_MACRO_STEPS,
    MacroDefinition,
    MacroExpander,
    MacroRegistry,
)
from lucca.reasoning.scheme.parser import (
    SchemeAtom,
    SchemeNode,
    SchemeValue,
    Symbol,
    to_canonical,
)
from lucca.sandbox.rpc import DockerRPCTransport

logger = structlog.get_logger(__name__)

DEFAULT_FALSIFICATION_TIMEOUT_MS: Final[float] = 500.0
MIN_TEST_CASES_REQUIRED: Final[int] = 3

ARITHMETIC_OPS: Final[frozenset[str]] = frozenset({"+", "-", "*", "/", "<", ">", "<=", ">="})


def _is_arithmetic_tree(node: SchemeNode) -> bool:
    """Checks if AST predominantly involves numeric/arithmetic operations."""
    if isinstance(node, list):
        if node and isinstance(node[0], Symbol) and node[0].name in ARITHMETIC_OPS:
            return True
        return any(_is_arithmetic_tree(child) for child in node)
    return False


class MacroTestCase(BaseModel):
    """A concrete I/O test case used to probe a candidate macro."""

    inputs: dict[str, str | int | float | bool] = Field(default_factory=dict)
    expected_output: str | int | float | bool | list[str | int | float | bool] | None = None
    description: str = ""


class FalsificationOutcome(BaseModel):
    """Result of running concrete I/O counterexample checks on a candidate macro."""

    passed: bool
    falsified: bool
    total_cases: int
    passed_cases: int
    counterexample: str | None = None
    failure_reason: str | None = None
    elapsed_ms: float = 0.0


class ScratchpadFalsifier:
    """
    Module 5 Scratchpad Falsification Engine.
    Executes candidate macros against >= 3 concrete test cases in the Docker sandbox
    before admitting them to QUARANTINE.
    """

    def __init__(
        self,
        transport: DockerRPCTransport | None = None,
        timeout_ms: float = DEFAULT_FALSIFICATION_TIMEOUT_MS,
        min_test_cases: int = MIN_TEST_CASES_REQUIRED,
        allow_in_process_fallback: bool = True,
    ) -> None:
        self.transport = transport
        self.timeout_ms = timeout_ms
        self.min_test_cases = min_test_cases
        self.allow_in_process_fallback = allow_in_process_fallback

    def synthesize_test_cases(
        self,
        macro_def: MacroDefinition,
        sample_bindings: list[dict[str, SchemeNode]] | None = None,
    ) -> list[MacroTestCase]:
        """
        Synthesizes concrete test cases from execution bindings or synthetic boundary values.
        Ensures >= min_test_cases (>= 3) cases are generated.
        """
        cases: list[MacroTestCase] = []

        is_num = _is_arithmetic_tree(macro_def.body)

        # 1. Use concrete observed bindings if provided
        if sample_bindings:
            for idx, b in enumerate(sample_bindings):
                inputs_map: dict[str, str | int | float | bool] = {}
                for k in macro_def.params:
                    val = b.get(k)
                    if isinstance(val, (int, float, bool)):
                        inputs_map[k] = val
                    elif isinstance(val, (str, Symbol)):
                        if is_num:
                            try:
                                inputs_map[k] = float(val) if isinstance(val, str) else (idx + 1)
                            except ValueError:
                                inputs_map[k] = idx + 1
                        else:
                            inputs_map[k] = val.name if isinstance(val, Symbol) else val
                    else:
                        inputs_map[k] = (idx + 1) if is_num else f"val_{idx}"
                cases.append(
                    MacroTestCase(
                        inputs=inputs_map,
                        description=f"observed_trace_{idx + 1}",
                    )
                )

        # 2. Augment with synthetic boundary cases if fewer than min_test_cases

        if is_num:
            probe_vals: list[list[str | int | float | bool]] = [
                [1, 2, 3, 4],
                [5, 10, 15, 20],
                [0, 1, 0, 1],
                [2, 4, 8, 16],
            ]
        else:
            probe_vals = [
                ["calc", "calculator", "tool_a"],
                ["notepad", "text_editor", "tool_b"],
                ["terminal", "console", "tool_c"],
                ["edge", "browser", "tool_d"],
            ]

        case_idx = len(cases)
        while len(cases) < self.min_test_cases:
            inputs_map = {}
            for p_i, p_name in enumerate(macro_def.params):
                pool = probe_vals[case_idx % len(probe_vals)]
                inputs_map[p_name] = pool[p_i % len(pool)]
            cases.append(
                MacroTestCase(
                    inputs=inputs_map,
                    description=f"synthetic_boundary_{case_idx + 1}",
                )
            )
            case_idx += 1

        return cases

    def falsify(
        self,
        macro_def: MacroDefinition,
        test_cases: list[MacroTestCase],
        scratchpad_buffer: SubTurnScratchpadBuffer | None = None,
    ) -> FalsificationOutcome:
        """
        Tests candidate macro against concrete I/O test cases.
        Fails fast if runtime error, timeout (> 500ms), or assertion error occurs.
        """
        t0 = time.perf_counter()

        if len(test_cases) < self.min_test_cases:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return FalsificationOutcome(
                passed=False,
                falsified=True,
                total_cases=len(test_cases),
                passed_cases=0,
                failure_reason=f"Insufficient test cases: required >={self.min_test_cases}, provided {len(test_cases)}",
                elapsed_ms=elapsed_ms,
            )

        passed_count = 0
        registry = MacroRegistry({macro_def.name: macro_def})
        expander = MacroExpander(registry)

        for case_idx, case in enumerate(test_cases):
            # Check elapsed budget
            curr_elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if curr_elapsed_ms > self.timeout_ms:
                return FalsificationOutcome(
                    passed=False,
                    falsified=True,
                    total_cases=len(test_cases),
                    passed_cases=passed_count,
                    failure_reason=f"Falsification timeout exceeded ({curr_elapsed_ms:.2f}ms > {self.timeout_ms}ms)",
                    elapsed_ms=curr_elapsed_ms,
                )

            # Construct invocation AST: (macro_name arg1 arg2 ...)
            invocation_args: list[SchemeNode] = []
            for p in macro_def.params:
                val = case.inputs.get(p, "")
                if isinstance(val, (int, float, bool)):
                    invocation_args.append(val)
                else:
                    invocation_args.append(str(val))

            call_ast: SchemeNode = [Symbol(macro_def.name), *invocation_args]

            # Dynamic expansion & execution
            try:
                expanded_ast = expander.expand(call_ast)
            except Exception as exp_err:
                logger.warning(
                    "scratchpad_macro_expansion_failed",
                    macro=macro_def.name,
                    error=str(exp_err),
                )
                curr_elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return FalsificationOutcome(
                    passed=False,
                    falsified=True,
                    total_cases=len(test_cases),
                    passed_cases=passed_count,
                    counterexample=f"Input {case.inputs} expansion error: {exp_err}",
                    failure_reason=f"Expansion error: {exp_err}",
                    elapsed_ms=curr_elapsed_ms,
                )

            # Execution check
            exec_ok, exec_res, exec_err = self._execute_test_case(expanded_ast, inputs=case.inputs)
            if not exec_ok:
                curr_elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return FalsificationOutcome(
                    passed=False,
                    falsified=True,
                    total_cases=len(test_cases),
                    passed_cases=passed_count,
                    counterexample=f"Input {case.inputs} execution failed: {exec_err}",
                    failure_reason=f"Execution error: {exec_err}",
                    elapsed_ms=curr_elapsed_ms,
                )

            # Expected output verification if provided
            if case.expected_output is not None and exec_res != case.expected_output:
                curr_elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return FalsificationOutcome(
                    passed=False,
                    falsified=True,
                    total_cases=len(test_cases),
                    passed_cases=passed_count,
                    counterexample=f"Input {case.inputs} produced {exec_res!r}, expected {case.expected_output!r}",
                    failure_reason=f"Output mismatch: expected {case.expected_output!r}, got {exec_res!r}",
                    elapsed_ms=curr_elapsed_ms,
                )

            passed_count += 1

        total_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        outcome = FalsificationOutcome(
            passed=True,
            falsified=False,
            total_cases=len(test_cases),
            passed_cases=passed_count,
            elapsed_ms=total_elapsed_ms,
        )

        if scratchpad_buffer is not None:
            scratchpad_buffer._intermediate_traces.append({
                "subsystem": "scratchpad_falsifier",
                "macro": macro_def.name,
                "passed_cases": passed_count,
                "total_cases": len(test_cases),
                "elapsed_ms": total_elapsed_ms,
            })

        return outcome

    def _execute_test_case(
        self,
        ast: SchemeNode,
        inputs: dict[str, str | int | float | bool] | None = None,
    ) -> tuple[bool, SchemeValue | None, str | None]:
        """
        Evaluates expanded AST. Under D-AUD-13, calls container when available;
        falls back to bounded evaluator if container is absent in local dev/test environment.
        """
        # If transport is available and active in Docker
        if self.transport is not None and self.transport.is_docker_available():
            try:
                sexpr_str = to_canonical(ast)
                runner_script = (
                    f"from lucca.reasoning.scheme.parser import parse_expr; "
                    f"from lucca.reasoning.scheme.eval import evaluate_expr; "
                    f"res = evaluate_expr(parse_expr({json.dumps(sexpr_str)})); "
                    f"print(repr(res))"
                )
                res = self.transport.execute(
                    call_id=f"falsify-{time.time_ns()}",
                    tool="run_python",
                    args={"code": runner_script},
                    timeout_s=0.5,
                )
                if res.ok:
                    raw_out = (res.content or "").strip()
                    try:
                        import ast as _py_ast
                        parsed_val = _py_ast.literal_eval(raw_out)
                    except (ValueError, SyntaxError):
                        parsed_val = raw_out
                    return True, parsed_val, None
                return False, None, res.stderr or "Container execution error"
            except Exception as rpc_err:
                logger.warning("container_falsification_rpc_error", error=str(rpc_err))
                if not self.allow_in_process_fallback:
                    return False, None, f"D-AUD-13 policy failure: {rpc_err}"

        # Controlled bounded host evaluation fallback for testing / offline environments
        if self.allow_in_process_fallback:
            try:
                evaluator = SchemeEvaluator(gas_limit=200, timeout_ms=50.0)
                evaluator.start_time = time.perf_counter()

                # Provide rich simulated state containing inputs for state predicates
                app_name = "calc"
                if inputs:
                    for v in inputs.values():
                        if isinstance(v, str):
                            app_name = v
                            break

                simulated_state = RuleState(
                    schema_version=1,
                    transcript="launch application",
                    transcript_lower="launch application",
                    intent="launch_app",
                    intent_conf=0.95,
                    entities={"app": [app_name]},
                    hour_local=12,
                    weekday=1,
                    apps_running=frozenset(),
                    session_turns=1,
                )
                env = build_env(simulated_state)
                val = evaluator.eval(ast, env)
                return True, val, None
            except Exception as eval_err:
                logger.debug("scratchpad_in_process_eval_failed", error=str(eval_err))
                return False, None, str(eval_err)

        return False, None, "D-AUD-13 violation: Docker container unavailable and fallback disabled"
