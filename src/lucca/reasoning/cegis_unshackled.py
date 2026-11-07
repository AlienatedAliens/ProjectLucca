"""
Project Lucca — Unshackled Counterexample-Guided Inductive Synthesis (CEGIS)
v1.44.0 General Reasoning Engine & WO-43 Phase 3.4 Modularized Facade
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import httpx
import structlog

from lucca.reasoning.cegis_grid_diff import (
    ANSI_DIFF_HIGHLIGHT,
    ANSI_RESET,
    ARC_ANSI_BG,
    ARC_PALETTE_NAMES,
    CellMismatch,
    GridDiff,
    compute_detailed_grid_diff,
    render_grid_ansi,
    render_grid_side_by_side,
)
from lucca.reasoning.cegis_mutator import generate_ast_mutants
from lucca.reasoning.cegis_sandbox import (
    _ALLOWED_CEGIS_IMPORT_MODULES,
    _FORBIDDEN_CEGIS_ATTRS,
    _FORBIDDEN_CEGIS_CALLS,
    CANONICAL_PRIMITIVES_PROMPT,
    DEFAULT_CONTAINER,
    DEFAULT_MAX_TURNS,
    DEFAULT_TIMEOUT_S,
    CEGISResult,
    CEGISTrace,
    ExecutionOutcome,
    PythonCEGISEngine,
    _build_restricted_cegis_globals,
    execute_unshackled_python,
    execute_unshackled_python_batch,
    normalize_to_int_grid,
    parse_python_exception,
    strip_comments_and_docstrings,
    validate_cegis_ast_safety,
)
from lucca.sandbox.preflight import extract_python_code

if TYPE_CHECKING:
    from lucca.core.cognitive_sink import CognitiveOutcomeSink

logger = structlog.get_logger(__name__)


def extract_hypothesis(text: str) -> str | None:
    """Extracts structured hypothesis block from model response if present."""
    m = re.search(r"(?:HYPOTHESIS|Hypothesis):?\s*(.+?)(?=```python|```|$)", text, re.DOTALL | re.IGNORECASE)
    if m:
        cleaned = m.group(1).strip()
        return cleaned if len(cleaned) > 10 else None
    return None



@dataclass(frozen=True)
class CEGISTurn:
    """Audit record for a single CEGIS synthesis/repair turn."""

    turn: int
    code: str
    passed_examples: int
    total_examples: int
    first_failure_idx: int | None
    failure_diff: GridDiff | None
    execution_error: str | None
    prompt_used: str
    elapsed_ms: float
    hypothesis: str | None = None
    is_backtrack: bool = False


@dataclass(frozen=True)
class CEGISRunResult:
    """Comprehensive outcome of the Counterexample-Guided Inductive Synthesis loop."""

    success: bool
    final_code: str | None
    turns_taken: int
    turns: list[CEGISTurn] = field(default_factory=list)
    test_predictions: list[list[list[int]]] = field(default_factory=list)
    total_elapsed_ms: float = 0.0
    error_summary: str | None = None



class UnshackledCEGISEngine:
    """
    Autonomous Counterexample-Guided Inductive Synthesis (CEGIS) Engine for Lucca v1.44.0.
    Eliminates benchmark-specific DSL shortcuts, allowing the model to invent arbitrary
    algorithmic Python transformation code on the fly with structured cell diff guidance.
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8080/v1/chat/completions",
        timeout_seconds: float = 120.0,
        max_turns: int = 4,
        k_samples: int = 4,
        outcome_sink: CognitiveOutcomeSink | None = None,
    ) -> None:
        self.server_url = server_url
        self.timeout_seconds = timeout_seconds
        self.max_turns = max_turns
        self.k_samples = k_samples
        self.outcome_sink = outcome_sink

    def _notify_outcome_sink(
        self,
        result: CEGISRunResult,
        task_data: dict[str, object],
        hint: str | None = None,
        outcome_sink: CognitiveOutcomeSink | None = None,
    ) -> None:
        """Forwards UnshackledCEGISEngine run outcome to CognitiveOutcomeSink (Milestone 36.1)."""
        sink = outcome_sink or self.outcome_sink
        if sink is None:
            return
        try:
            task_id = str(task_data.get("id") or task_data.get("task_id") or f"arc-{uuid.uuid4().hex[:8]}")
            turn_1_err: str | None = None
            verified_strat: str | None = None
            if result.turns:
                t1 = result.turns[0]
                if t1.execution_error:
                    turn_1_err = t1.execution_error
                elif t1.failure_diff:
                    turn_1_err = t1.failure_diff.summary_message
                last_t = result.turns[-1]
                verified_strat = last_t.hypothesis or ("Multi-turn spatial repair" if result.turns_taken >= 2 else "Direct synthesis")
            turn_traces: list[dict[str, object]] = [
                {
                    "turn": tr.turn,
                    "name": "initial_synthesis" if tr.turn == 1 else f"repair_turn_{tr.turn}",
                    "summary": f"passed={tr.passed_examples}/{tr.total_examples}; err={tr.execution_error or (tr.failure_diff.summary_message if tr.failure_diff else 'none')}",
                }
                for tr in result.turns
            ]
            status_label = (
                "VERIFIED_REPAIRED_PROGRAM"
                if (result.success and result.turns_taken >= 2)
                else ("CHECKED_FORMALIZATION_AGREED" if result.success else "INTERNAL_FALLBACK")
            )
            sink.record_cegis_outcome(
                task_id=task_id,
                problem_summary=verified_strat or hint or f"Spatial grid transformation ({task_id})",
                engine_name="UnshackledCEGISEngine",
                success=result.success,
                turns_taken=result.turns_taken,
                final_code=result.final_code,
                turn_1_error=turn_1_err,
                verified_strategy=verified_strat,
                turn_traces=turn_traces,
                status_label=status_label,
            )
        except Exception as sink_err:  # noqa: BLE001
            logger.debug("unshackled_cegis_outcome_sink_failed", error=str(sink_err))

    def query_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        stop: list[str] | None = None,
    ) -> str:
        """Queries local llama-server instance synchronously."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, object] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if stop:
            payload["stop"] = stop
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(self.server_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"]).strip()

    @staticmethod

    def _format_train_examples(train_pairs: list[dict[str, list[list[int]]]]) -> str:
        blocks: list[str] = []
        for idx, ex in enumerate(train_pairs, start=1):
            blocks.append(
                f"### Demonstration {idx}:\n"
                f"Input ({len(ex['input'])}x{len(ex['input'][0]) if ex['input'] else 0}):\n"
                f"{json.dumps(ex['input'])}\n"
                f"Output ({len(ex['output'])}x{len(ex['output'][0]) if ex['output'] else 0}):\n"
                f"{json.dumps(ex['output'])}\n"
            )
        return "\n".join(blocks)

    def verify_candidate(
        self,
        code: str,
        train_pairs: list[dict[str, list[list[int]]]],
    ) -> tuple[bool, int, int | None, GridDiff | None, str | None]:
        """
        Evaluates candidate code against all training demonstrations using batch container execution.
        Returns (all_passed, passed_count, first_failing_idx, first_diff, error_message).
        """
        if not train_pairs:
            return True, 0, None, None, None
        inputs = [p["input"] for p in train_pairs]
        outcomes = execute_unshackled_python_batch(code, inputs)
        passed_count = 0
        for idx, (pair, outcome) in enumerate(zip(train_pairs, outcomes)):
            if not outcome.success or outcome.output_grid is None:
                err_msg = f"{outcome.error_type}: {outcome.error_message}"
                return False, passed_count, idx, None, err_msg
            diff = compute_detailed_grid_diff(pair["output"], outcome.output_grid)
            if diff.is_match:
                passed_count += 1
            else:
                return False, passed_count, idx, diff, None
        return True, passed_count, None, None, None

    def verify_or_mutate_candidate(
        self,
        code: str,
        train_pairs: list[dict[str, list[list[int]]]],
    ) -> tuple[str, bool, int, int | None, GridDiff | None, str | None]:
        """
        Evaluates candidate code against training demonstrations.
        If initial code does not satisfy 100% of demonstrations, generates domain-agnostic
        single-point AST mutations (boolean polarity, mask inversion, argument swap).
        Returns (best_code, all_passed, passed_count, first_failing_idx, first_diff, error_message).
        """
        all_passed, passed_count, fail_idx, fail_diff, err_msg = self.verify_candidate(code, train_pairs)
        if all_passed or not code.strip():
            return code, all_passed, passed_count, fail_idx, fail_diff, err_msg
        mutants = generate_ast_mutants(code)
        best_code = code
        best_passed_count = passed_count
        best_fail_idx = fail_idx
        best_diff = fail_diff
        best_err = err_msg
        for mutant in mutants:
            m_passed, m_count, m_fail_idx, m_diff, m_err = self.verify_candidate(mutant, train_pairs)
            if m_passed:
                logger.info(
                    "cegis_ast_mutant_repaired_100_train",
                    original_passed=passed_count,
                    mutant_passed=m_count,
                    total=len(train_pairs),
                )
                return mutant, True, m_count, None, None, None
            if m_count > best_passed_count:
                best_code = mutant
                best_passed_count = m_count
                best_fail_idx = m_fail_idx
                best_diff = m_diff
                best_err = m_err
        return best_code, False, best_passed_count, best_fail_idx, best_diff, best_err

    def synthesize_turn_1(
        self,
        task_data: dict[str, object],
        hint: str | None = None,
        temperature: float = 0.2,
        k_samples: int | None = None,
    ) -> tuple[str, str | None, str]:
        """
        Synthesizes initial candidate Python program (Turn 1) using Hypothesis-First Abduction.
        Employs Best-of-K sampling across temperature schedule, selecting by training demonstration accuracy.
        """
        raw_train = task_data.get("train", [])
        train_pairs = cast(list[dict[str, list[list[int]]]], raw_train if isinstance(raw_train, list) else [])
        train_desc = self._format_train_examples(train_pairs)
        system_prompt = (
            "You are an expert algorithmic programmer and neurosymbolic reasoning engine.\n"
            "Your objective is to deduce the exact invariant spatial transformation mapping 2D integer grids "
            "from input to output across all demonstrations, and implement it as a clean Python function."
        )
        user_prompt_lines: list[str] = [
            CANONICAL_PRIMITIVES_PROMPT,
            "",
            "Analyze the following input-output grid demonstrations carefully:",
            "",
            train_desc,
            "Format Requirement (Hypothesis-First):",
            "Begin your response with a concise HYPOTHESIS block before emitting code:",
            "HYPOTHESIS:",
            "- Background Color: <int> (<name>)",
            "- Canvas Sizing: <same_as_input | fixed HxW | cropped | expanded>",
            "- Objects & Topology: <individual pixels | 4-connected | 8-connected | cavities | lines>",
            "- Core Transformation Invariant: <1-2 sentences clearly stating the spatial rule>",
            "- Algorithmic Recipe: <step 1, step 2, step 3>",
            "",
            "Specifications & Rules:",
            "1. Write a Python function `def transform(grid: list[list[int]]) -> list[list[int]]:` that solves this transformation.",
            "2. All utilities listed above are ALREADY in global scope. Do NOT import from `__main__` or `spatial_utils`.",
            "3. Return executable Python code inside a single ```python ... ``` block. Absolutely NO comments (#), NO docstrings, and NO markdown explanation outside the block.",
        ]
        if hint:
            user_prompt_lines.append(f"\nUser / System Guidance: {hint}")
        prompt = "\n".join(user_prompt_lines)
        k = k_samples if k_samples is not None else self.k_samples
        temperatures = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5][:k] if k > 1 else [temperature]
        best_candidate: tuple[int, int, str, str | None] | None = None
        for s_idx, t in enumerate(temperatures):
            response_text = self.query_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=t,
                max_tokens=2048,
            )
            cand_code = extract_python_code(response_text)
            cand_code = strip_comments_and_docstrings(cand_code)
            cand_hypo = extract_hypothesis(response_text)
            if not cand_code:
                continue
            cand_code, all_passed, passed_count, _, _, _ = self.verify_or_mutate_candidate(cand_code, train_pairs)
            if all_passed:
                logger.info(
                    "turn1_best_of_k_train_passed",
                    sample=s_idx + 1,
                    total_samples=len(temperatures),
                    temperature=t,
                    passed=passed_count,
                    total=len(train_pairs),
                )
                return cand_code, cand_hypo, prompt
            score = (passed_count, -len(cand_code))
            if best_candidate is None or score > (best_candidate[0], best_candidate[1]):
                best_candidate = (passed_count, -len(cand_code), cand_code, cand_hypo)
        if best_candidate is not None:
            return best_candidate[2], best_candidate[3], prompt
        return "", None, prompt

    def synthesize_repair_turn(
        self,
        prior_code: str,
        task_data: dict[str, object],
        failing_idx: int,
        diff: GridDiff | None,
        err_msg: str | None,
        turn_num: int,
        temperature: float = 0.25,
        prior_hypothesis: str | None = None,
        k_samples: int | None = None,
    ) -> tuple[str, str | None, str]:
        """
        Synthesizes a repaired program using structured counterexample diffs (Turn 2..K).
        Samples multiple candidates and selects by demonstration pass accuracy.
        """
        raw_train = task_data.get("train", [])
        train_pairs = cast(list[dict[str, list[list[int]]]], raw_train if isinstance(raw_train, list) else [])
        failing_pair = train_pairs[failing_idx]
        train_desc = self._format_train_examples(train_pairs)
        system_prompt = (
            "You are an expert algorithmic debugger and neurosymbolic program repair engine.\n"
            "Your previous implementation failed on a training demonstration. Analyze the exact counterexample diff, "
            "locate the flaw in your logic, and output a corrected, fully verified `transform` function."
        )
        repair_prompt_lines: list[str] = [
            f"### CEGIS REPAIR TURN {turn_num}:",
            f"Your previous Python code failed on Demonstration {failing_idx + 1}.",
            "",
            CANONICAL_PRIMITIVES_PROMPT,
            "",
            f"Previous Code Attempt:\n```python\n{prior_code}\n```",
        ]
        if prior_hypothesis:
            repair_prompt_lines.append(f"\nPrevious Hypothesis:\n{prior_hypothesis}\n")
        repair_prompt_lines.append("### Failure Diagnostic:")
        if err_msg:
            repair_prompt_lines.append(f"- Execution Runtime Error: {err_msg}")
        elif diff:
            repair_prompt_lines.append(diff.format_counterexample_prompt(max_examples=16))
            outcome = execute_unshackled_python(prior_code, failing_pair["input"])
            if outcome.success and outcome.output_grid:
                side_by_side = render_grid_side_by_side(
                    expected=failing_pair["output"],
                    actual=outcome.output_grid,
                    use_color=False,
                )
                repair_prompt_lines.append("\nGrid Comparison (Expected vs Predicted vs Diff):\n" + side_by_side)
        repair_prompt_lines.extend([
            "",
            "All Training Demonstrations for Reference:",
            train_desc,
            "Instructions for Repair:",
            "1. Analyze why the previous code failed the counterexample demonstration.",
            "2. For enclosure/containment queries, you MUST use `in_cavity`, `extract_cavities`, or `extract_cavity_mask`.",
            "3. Bounding box `min/max` coordinate check is STRICTLY FORBIDDEN for enclosure checks.",
            "4. Do NOT assume single containers; iterate over all candidate containers.",
            "5. Modify your logic so that it satisfies Demonstration 1, 2, ... and ALL others simultaneously.",
            "6. Return ONLY executable Python code inside a single ```python ... ``` block. Absolutely NO comments or docstrings.",
        ])
        prompt = "\n".join(repair_prompt_lines)
        k = k_samples if k_samples is not None else self.k_samples
        temperatures = [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5][:k] if k > 1 else [temperature]
        best_candidate: tuple[int, int, str, str | None] | None = None
        for s_idx, t in enumerate(temperatures):
            response_text = self.query_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=t,
                max_tokens=2048,
            )
            cand_code = extract_python_code(response_text)
            cand_code = strip_comments_and_docstrings(cand_code)
            cand_hypo = extract_hypothesis(response_text)
            if not cand_code:
                continue
            cand_code, all_passed, passed_count, _, _, _ = self.verify_or_mutate_candidate(cand_code, train_pairs)
            if all_passed:
                logger.info(
                    "repair_best_of_k_train_passed",
                    turn=turn_num,
                    sample=s_idx + 1,
                    total_samples=len(temperatures),
                    temperature=t,
                    passed=passed_count,
                    total=len(train_pairs),
                )
                return cand_code, cand_hypo, prompt
            score = (passed_count, -len(cand_code))
            if best_candidate is None or score > (best_candidate[0], best_candidate[1]):
                best_candidate = (passed_count, -len(cand_code), cand_code, cand_hypo)
        if best_candidate is not None:
            return best_candidate[2], best_candidate[3], prompt
        return "", None, prompt

    def synthesize_backtrack_turn(
        self,
        task_data: dict[str, object],
        turn_num: int,
        failed_hypotheses: list[str],
        prior_error: str | None = None,
        temperature: float = 0.35,
        k_samples: int | None = None,
    ) -> tuple[str, str | None, str]:
        """
        Synthesizes a fresh candidate from scratch when previous branches reached an impasse.
        Discards the failed code branch and forces the model to explore an alternative hypothesis.
        """
        raw_train = task_data.get("train", [])
        train_pairs = cast(list[dict[str, list[list[int]]]], raw_train if isinstance(raw_train, list) else [])
        train_desc = self._format_train_examples(train_pairs)
        system_prompt = (
            "You are an expert algorithmic programmer and neurosymbolic reasoning engine.\n"
            "Your previous hypothesis failed completely. You must formulate a fresh, alternative conceptual hypothesis "
            "and implement a brand-new transformation function from scratch."
        )
        user_prompt_lines: list[str] = [
            f"### CLEAN-SLATE BACKTRACKING (TURN {turn_num}):",
            "The previous code branch failed completely across all demonstrations (0 passed).",
            "CRITICAL: Discard the previous approach completely. Do NOT attempt to patch it.",
            "",
            CANONICAL_PRIMITIVES_PROMPT,
            "",
            "Previous Failed Hypotheses:",
        ]
        for idx, h in enumerate(failed_hypotheses, start=1):
            user_prompt_lines.append(f"- Hypothesis {idx}: {h}")
        if prior_error:
            user_prompt_lines.append(f"\nObserved Failure: {prior_error}")
        user_prompt_lines.extend([
            "",
            "Formulate a FRESH, ALTERNATIVE hypothesis from scratch.",
            "Consider whether:",
            "- Background color was misidentified (e.g. non-zero background or inverted foreground).",
            "- Connectivity is 8-connected instead of 4-connected (or vice-versa).",
            "- The rule depends on enclosed cavities, hollow shapes, or spatial order (top-to-bottom / size).",
            "- The output canvas has different dimensions or is a crop of a specific bounding box.",
            "- The transformation is rotational or reflective symmetry.",
            "",
            "Format Requirement (Hypothesis-First):",
            "Begin with a fresh HYPOTHESIS block before the code:",
            "HYPOTHESIS:",
            "- Background Color: <int> (<name>)",
            "- Canvas Sizing: <same_as_input | fixed HxW | cropped | expanded>",
            "- Objects & Topology: <individual pixels | 4-connected | 8-connected | cavities | lines>",
            "- Core Transformation Invariant: <1-2 sentences clearly stating the fresh rule>",
            "- Algorithmic Recipe: <step 1, step 2, step 3>",
            "",
            "All Training Demonstrations for Reference:",
            train_desc,
            "Specifications & Rules:",
            "1. Write a Python function `def transform(grid: list[list[int]]) -> list[list[int]]:` that solves this transformation.",
            "2. For enclosure/containment queries, you MUST use `in_cavity`, `extract_cavities`, or `extract_cavity_mask`.",
            "3. Bounding box `min/max` is STRICTLY FORBIDDEN for enclosure checks.",
            "4. Do NOT assume single containers; iterate over all candidate containers.",
            "5. Return executable Python code inside a single ```python ... ``` block. Prioritize clean, complete, fully closed Python code.",
        ])
        prompt = "\n".join(user_prompt_lines)
        k = k_samples if k_samples is not None else self.k_samples
        temperatures = [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55][:k] if k > 1 else [temperature]
        best_candidate: tuple[int, int, str, str | None] | None = None
        for s_idx, t in enumerate(temperatures):
            response_text = self.query_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=t,
                max_tokens=2048,
            )
            cand_code = extract_python_code(response_text)
            cand_code = strip_comments_and_docstrings(cand_code)
            cand_hypo = extract_hypothesis(response_text)
            if not cand_code:
                continue
            cand_code, all_passed, passed_count, _, _, _ = self.verify_or_mutate_candidate(cand_code, train_pairs)
            if all_passed:
                logger.info(
                    "backtrack_best_of_k_train_passed",
                    turn=turn_num,
                    sample=s_idx + 1,
                    total_samples=len(temperatures),
                    temperature=t,
                    passed=passed_count,
                    total=len(train_pairs),
                )
                return cand_code, cand_hypo, prompt
            score = (passed_count, -len(cand_code))
            if best_candidate is None or score > (best_candidate[0], best_candidate[1]):
                best_candidate = (passed_count, -len(cand_code), cand_code, cand_hypo)
        if best_candidate is not None:
            return best_candidate[2], best_candidate[3], prompt
        return "", None, prompt

    def run_cegis_loop(
        self,
        task_data: dict[str, object],
        hint: str | None = None,
        max_turns: int | None = None,
        outcome_sink: CognitiveOutcomeSink | None = None,
    ) -> CEGISRunResult:
        """
        Executes the full multi-turn CEGIS loop for a given task.
        Halts immediately once 100% of training demonstrations are satisfied.
        """
        t0 = time.perf_counter()
        effective_max_turns = max_turns or self.max_turns
        raw_train = task_data.get("train", [])
        train_pairs = cast(list[dict[str, list[list[int]]]], raw_train if isinstance(raw_train, list) else [])
        total_examples = len(train_pairs)
        traces: list[CEGISTurn] = []
        current_code: str = ""
        current_hypothesis: str | None = None
        turn_idx = 1
        limit_turns = effective_max_turns
        consecutive_zero_passes = 0
        while turn_idx <= limit_turns:
            turn_t0 = time.perf_counter()
            if turn_idx == 1:
                code, hypo, prompt = self.synthesize_turn_1(task_data, hint=hint, temperature=0.2)
                is_backtrack = False
            else:
                last_trace = traces[-1]
                should_backtrack = (
                    consecutive_zero_passes >= 1
                    and (turn_idx >= 3 or last_trace.execution_error is not None)
                )
                if should_backtrack:
                    failed_hypos = [t.hypothesis for t in traces if t.hypothesis]
                    if not failed_hypos and current_hypothesis:
                        failed_hypos = [current_hypothesis]
                    code, hypo, prompt = self.synthesize_backtrack_turn(
                        task_data=task_data,
                        turn_num=turn_idx,
                        failed_hypotheses=failed_hypos,
                        prior_error=last_trace.execution_error or (f"Cell diff on demo {(last_trace.first_failure_idx or 0) + 1}" if last_trace.failure_diff else None),
                        temperature=0.35,
                    )
                    is_backtrack = True
                else:
                    code, hypo, prompt = self.synthesize_repair_turn(
                        prior_code=current_code,
                        task_data=task_data,
                        failing_idx=last_trace.first_failure_idx or 0,
                        diff=last_trace.failure_diff,
                        err_msg=last_trace.execution_error,
                        turn_num=turn_idx,
                        temperature=0.2 + (min(turn_idx, 5) * 0.05),
                        prior_hypothesis=current_hypothesis,
                    )
                    is_backtrack = False
            current_code = code
            if hypo:
                current_hypothesis = hypo
            turn_elapsed = (time.perf_counter() - turn_t0) * 1000.0
            if not code or not code.strip():
                traces.append(
                    CEGISTurn(
                        turn=turn_idx,
                        code="",
                        passed_examples=0,
                        total_examples=total_examples,
                        first_failure_idx=0,
                        failure_diff=None,
                        execution_error="No executable Python code extracted from LLM response.",
                        prompt_used=prompt,
                        elapsed_ms=turn_elapsed,
                        hypothesis=current_hypothesis,
                        is_backtrack=is_backtrack,
                    )
                )
                consecutive_zero_passes += 1
                turn_idx += 1
                continue
            code, all_passed, passed_count, fail_idx, fail_diff, err_msg = self.verify_or_mutate_candidate(
                code, train_pairs
            )
            current_code = code
            if passed_count == 0:
                consecutive_zero_passes += 1
            else:
                consecutive_zero_passes = 0
            traces.append(
                CEGISTurn(
                    turn=turn_idx,
                    code=code,
                    passed_examples=passed_count,
                    total_examples=total_examples,
                    first_failure_idx=fail_idx,
                    failure_diff=fail_diff,
                    execution_error=err_msg,
                    prompt_used=prompt,
                    elapsed_ms=turn_elapsed,
                    hypothesis=current_hypothesis,
                    is_backtrack=is_backtrack,
                )
            )
            logger.info(
                "cegis_turn_evaluated",
                turn=turn_idx,
                passed=passed_count,
                total=total_examples,
                all_passed=all_passed,
                is_backtrack=is_backtrack,
                elapsed_ms=turn_elapsed,
            )
            if all_passed:
                total_elapsed = (time.perf_counter() - t0) * 1000.0
                raw_test = task_data.get("test", [])
                test_pairs = cast(list[dict[str, list[list[int]]]], raw_test if isinstance(raw_test, list) else [])
                test_preds = self.predict_test(code, test_pairs)
                res_ok = CEGISRunResult(
                    success=True,
                    final_code=code,
                    turns_taken=turn_idx,
                    turns=traces,
                    test_predictions=test_preds,
                    total_elapsed_ms=total_elapsed,
                    error_summary=None,
                )
                self._notify_outcome_sink(res_ok, task_data, hint=hint, outcome_sink=outcome_sink)
                return res_ok
            # Adaptive budget extension: if at current limit and showing positive progress, grant 1 bonus turn
            if turn_idx == limit_turns and passed_count > 0 and limit_turns < effective_max_turns + 2:
                logger.info(
                    "adaptive_cegis_turn_extended",
                    turn=turn_idx,
                    passed=passed_count,
                    total=total_examples,
                )
                limit_turns += 1
            turn_idx += 1
        total_elapsed = (time.perf_counter() - t0) * 1000.0
        res_fail = CEGISRunResult(
            success=False,
            final_code=current_code,
            turns_taken=len(traces),
            turns=traces,
            test_predictions=[],
            total_elapsed_ms=total_elapsed,
            error_summary=f"Failed to satisfy 100% of demonstrations after {len(traces)} turns.",
        )
        self._notify_outcome_sink(res_fail, task_data, hint=hint, outcome_sink=outcome_sink)
        return res_fail

    @staticmethod

    def predict_test(
        code: str, test_pairs: list[dict[str, list[list[int]]]]
    ) -> list[list[list[int]]]:
        """Runs the verified code on the unseen test input(s)."""
        predictions: list[list[list[int]]] = []
        for pair in test_pairs:
            outcome = execute_unshackled_python(code, pair["input"])
            if outcome.success and outcome.output_grid is not None:
                predictions.append(outcome.output_grid)
            else:
                predictions.append([])
        return predictions


__all__ = [
    "ANSI_DIFF_HIGHLIGHT", "ANSI_RESET", "ARC_ANSI_BG", "ARC_PALETTE_NAMES",
    "CANONICAL_PRIMITIVES_PROMPT", "CEGISResult", "CEGISRunResult", "CEGISTrace",
    "CEGISTurn", "CellMismatch", "DEFAULT_CONTAINER", "DEFAULT_MAX_TURNS",
    "DEFAULT_TIMEOUT_S", "ExecutionOutcome", "GridDiff", "PythonCEGISEngine",
    "UnshackledCEGISEngine", "_ALLOWED_CEGIS_IMPORT_MODULES",
    "_FORBIDDEN_CEGIS_ATTRS", "_FORBIDDEN_CEGIS_CALLS",
    "_build_restricted_cegis_globals", "compute_detailed_grid_diff",
    "execute_unshackled_python", "execute_unshackled_python_batch",
    "extract_hypothesis", "generate_ast_mutants", "normalize_to_int_grid",
    "parse_python_exception", "render_grid_ansi", "render_grid_side_by_side",
    "strip_comments_and_docstrings", "validate_cegis_ast_safety",
]
