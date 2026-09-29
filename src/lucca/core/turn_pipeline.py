"""
Project Lucca — Unified Turn Execution Pipeline
Spec D-ARCH-05, D-HON-01, WO-11.1, WO-12.2

Unifies voice and text execution into a single, cohesive file-level pipeline.
Input adapters (_run_turn, _run_text_turn) in Orchestrator normalize voice/text
signals into TurnInput and delegate to TurnPipeline.run().

Phases:
1. Normalization & Spelled-Word Attractor Neutralization
2. Previous Turn Latching & Outcome Labeling
3. Rule State Evaluation & Intent Routing
4. Tier Dispatch (REFLEX / ACT_THEN_NARRATE / FULL_LOOP)
5. Epistemic Context Synthesis, Intent-Based Tool Gating & LLM Streaming Loop
6. Turn Finalization, Autonomic Reflection & Belief Extraction

Zero-Any invariant enforced.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import structlog

from lucca.brain.prompt_builder import (
    build_narration_messages,
)
from lucca.core.cascade import EpistemicSubstrate
from lucca.core.config import load_heuristics
from lucca.core.exceptions import SchemeInterruptSignal, SchemeYieldSignal
from lucca.core.proof_policy import is_cross_reference_command
from lucca.core.sanity_guard import SanityCheckGuard
from lucca.core.schemas import (
    AssertFact,
    ChatMessage,
    ExecutionTier,
    JsonValue,
    PendingRatification,
    RouteAction,
    RouteDecision,
    RuleOutcome,
    RuleState,
    Say,
    ToolCall,
    ToolResult,
)
from lucca.core.self_diagnosis import is_self_diagnosis_query
from lucca.core.text_utils import normalize_spelled_words, normalize_transcript
from lucca.core.trace import TurnTrace, now_ns
from lucca.router.labeler import derive_label, persist_decision_label
from lucca.sandbox.policy import parse_confirmation_response
from lucca.senses.ring_buffer import FLAG_ABORT, FLAG_EOS

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


def aggregate_plan_narration_summary(
    executed_steps: list[tuple[str, dict[str, JsonValue], bool, str]],
    cancelled_steps: list[tuple[str, dict[str, JsonValue]]] | None = None,
    failed_step_order: int | None = None,
) -> str:
    """Aggregates multi-action plan execution into a unified narration trace (ITEM-017).

    Ensures that spoken narration verbalizes the *whole executed sequence* aggregated
    from per-step receipts, rather than only the final step's result.
    If a partial failure occurred, explicitly identifies the failed step and cancelled remainder.
    """
    lines: list[str] = []
    for i, (tool, args, ok, detail) in enumerate(executed_steps, 1):
        args_str = ", ".join(f"{k}={v!r}" for k, v in args.items()) if args else ""
        status = "ok" if ok else "failed"
        detail_snip = f": {detail}" if detail else ""
        lines.append(f"Step {i}: {tool}({args_str}) -> {status}{detail_snip}")

    if failed_step_order is not None and cancelled_steps:
        cancelled_tools = ", ".join(tool for tool, _ in cancelled_steps)
        lines.append(
            f"Remaining steps cancelled due to Step {failed_step_order} failure: {cancelled_tools}"
        )

    return "\n".join(lines)


def synthesize_plan_narration(
    executed_steps: list[tuple[str, dict[str, JsonValue], bool, str]],
    cancelled_steps: list[tuple[str, dict[str, JsonValue]]] | None = None,
    failed_step_order: int | None = None,
) -> str:
    """Produces honest, deterministic multi-step spoken summary (ITEM-017 / D-HON-01).

    Generates natural language citing every executed step in sequence,
    and naming any failed step and cancelled remainder.
    """
    if not executed_steps:
        return "No plan steps were executed."

    if failed_step_order is not None and failed_step_order <= len(executed_steps):
        failed_tool, _, _ok, fail_msg = executed_steps[failed_step_order - 1]
        cancelled_str = ""
        if cancelled_steps:
            tools_list = ", ".join(t for t, _ in cancelled_steps)
            cancelled_str = f" I cancelled the remaining steps ({tools_list})."
        err_detail = f" with error: {fail_msg}" if fail_msg else ""
        prior_steps = executed_steps[: failed_step_order - 1]
        prior_str = ""
        if prior_steps:
            prior_tools = ", ".join(t for t, _, _, _ in prior_steps)
            prior_str = f"After running {prior_tools}, "
        fail_part = f"Step {failed_step_order} ({failed_tool}) failed{err_detail}."
        res = f"{prior_str}{fail_part}{cancelled_str}"
        return res.strip()

    step_descriptions: list[str] = []
    for tool, args, _ok, _detail in executed_steps:
        if tool == "search_web":
            q = str(args.get("query", "") or args.get("q", ""))
            step_descriptions.append(f"searched the web for '{q}'" if q else "searched the web")
        elif tool == "fetch_url":
            u = str(args.get("url", ""))
            step_descriptions.append(f"fetched {u}" if u else "fetched the page")
        elif tool in ("note_write", "write_note"):
            t = str(args.get("name", "") or args.get("topic", "") or args.get("title", ""))
            step_descriptions.append(f"wrote note '{t}'" if t else "wrote to notes")
        elif tool in ("note_read", "read_note"):
            t = str(args.get("name", "") or args.get("topic", "") or args.get("query", ""))
            step_descriptions.append(f"read note '{t}'" if t else "read notes")
        elif tool == "read_file":
            p = str(args.get("path", ""))
            step_descriptions.append(f"read file '{p}'" if p else "read file")
        elif tool == "write_file":
            p = str(args.get("path", ""))
            step_descriptions.append(f"wrote file '{p}'" if p else "wrote file")
        elif tool == "launch_app":
            a = str(args.get("app", ""))
            step_descriptions.append(f"launched {a}" if a else "launched application")
        elif tool == "calc_math":
            step_descriptions.append("calculated result")
        else:
            step_descriptions.append(f"executed {tool}")

    if len(step_descriptions) == 1:
        return f"I {step_descriptions[0]}."
    if len(step_descriptions) == 2:
        return f"I {step_descriptions[0]} and {step_descriptions[1]}."
    all_but_last = ", ".join(step_descriptions[:-1])
    return f"I {all_but_last}, and {step_descriptions[-1]}."


def is_code_synthesis_request(user_text: str) -> bool:
    """Detects whether an utterance is explicitly a programming/code synthesis request."""
    if not user_text:
        return False
    lower = user_text.lower().strip()
    if lower.startswith("def ") or (lower.startswith("import ") and "def " in lower):
        return True
    if lower.startswith("complete the following python function") or lower.startswith(
        "write a python function"
    ):
        return True
    return False


class DifficultyEstimator:
    """
    Evaluates turn difficulty and reasoning demands to dynamically toggle
    extended thinking tokens (When2Think heuristic, Spec §7, D-BRAIN-05 v2, D-META-01).

    In accordance with D-BRAIN-05 v2, routine and standard conversational turns
    bypass extended thinking (enable_thinking=False) to preserve llama-server's
    prefix KV cache and maintain sub-350ms TTFT.
    Extended thinking (enable_thinking=True) is reserved for explicit user requests
    demanding deliberate multi-step reasoning ('think step by step', 'deep think',
    'take your time and think', 'enable thinking').
    """

    EXPLICIT_THINKING_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\b(think\s+step\s+by\s+step|step\s*-\s*by\s*-\s*step\s+reasoning|"
            r"deliberate\s+carefully|take\s+your\s+time\s+and\s+think|"
            r"deep\s+think(ing)?|enable\s+thinking|with\s+thinking|"
            r"think\s+through\s+this\s+step\s+by\s+step)\b",
            re.IGNORECASE,
        ),
    )

    FAST_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\b(quick\s+answer|quick\s+question|short\s+answer|in\s+one\s+word|"
            r"just\s+tell\s+me|don'?t\s+overthink|fast\s+summary)\b",
            re.IGNORECASE,
        ),
    )

    def should_enable_thinking(self, user_text: str, intent: str | None = None) -> bool:
        """
        Determines whether extended thinking should be enabled for this turn.
        Returns True ONLY if user explicitly requested deep deliberation/thinking mode,
        False for all standard conversational and routine turns.
        """
        if not user_text or not user_text.strip():
            return False

        clean_text = user_text.strip()

        # 1. Fast-path explicit suppressors
        for pat in self.FAST_PATH_PATTERNS:
            if pat.search(clean_text):
                return False

        # 2. Explicit user request for extended thinking (D-BRAIN-05 v2)
        for pat in self.EXPLICIT_THINKING_PATTERNS:
            if pat.search(clean_text):
                return True

        # 3. Default to False: preserves llama-server prefix KV cache and sub-350ms TTFT
        return False


class SubTurnScratchpadBuffer:
    """Decoupled intermediate tool deliberation scratchpad (WO-26 Phase 5).

    Executes intermediate tool calls, coordinate math, and multi-turn execution traces
    in an isolated sub-turn buffer with an independent character/token budget.
    Ensures that heavy intermediate traces never starve subsequent generation rounds
    and never leak un-synthesized raw dumps into long-term conversational history.
    """

    def __init__(
        self,
        max_total_chars: int = 24000,
        max_single_output_chars: int = 4000,
        head_chars: int = 2000,
        tail_chars: int = 1500,
    ) -> None:
        self.max_total_chars: int = max_total_chars
        self.max_single_output_chars: int = max_single_output_chars
        self.head_chars: int = head_chars
        self.tail_chars: int = tail_chars
        self._messages: list[ChatMessage] = []
        self._intermediate_traces: list[dict[str, JsonValue]] = []
        self.truncated_count: int = 0

    @property
    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    def append(self, msg: ChatMessage) -> None:
        """Appends a ChatMessage directly to the scratchpad buffer."""
        self._messages.append(msg)

    def add_assistant_tool_call(
        self,
        call_id: str,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        thought: str = "",
    ) -> None:
        """Appends an assistant tool call to the isolated scratchpad buffer."""
        self._messages.append(
            ChatMessage(
                role="assistant",
                content=thought,
                tool_calls=[
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args),
                        },
                    }
                ],
            )
        )

    def add_tool_result(
        self,
        call_id: str,
        tool_name: str,
        raw_output: str,
        is_error: bool = False,
    ) -> None:
        """Appends a tool execution result to the isolated scratchpad buffer with bounding."""
        content = raw_output or ""
        total_len = len(content)
        if total_len > self.max_single_output_chars:
            omitted = max(0, total_len - (self.head_chars + self.tail_chars))
            head = content[: self.head_chars]
            tail = content[-self.tail_chars :] if self.tail_chars > 0 else ""
            bounded_output = (
                f"{head}\n\n[... Truncated in scratchpad buffer: {omitted} characters omitted to preserve synthesis budget ...]\n\n{tail}"
            )
            self.truncated_count += 1
            logger.info(
                "scratchpad_tool_output_bounded",
                tool=tool_name,
                original_len=total_len,
                bounded_len=len(bounded_output),
            )
        else:
            bounded_output = content

        self._messages.append(
            ChatMessage(
                role="tool",
                content=bounded_output,
                tool_call_id=call_id,
                name=tool_name,
            )
        )
        self._intermediate_traces.append(
            {
                "call_id": call_id,
                "tool": tool_name,
                "raw_len": total_len,
                "is_error": is_error,
            }
        )

    def add_user_directive(self, directive_text: str) -> None:
        """Appends an isolated mid-turn steering directive (e.g. repeat guard, honesty nudge)."""
        self._messages.append(ChatMessage(role="user", content=directive_text))

    def clear(self) -> None:
        """Resets the scratchpad buffer."""
        self._messages.clear()
        self._intermediate_traces.clear()
        self.truncated_count = 0


def detect_operational_ambiguity(text: str) -> tuple[bool, str | None]:
    """Detects open-ended business, financial, fee, or rounding ambiguities (WO-26 Phase 5).

    Returns (is_ambiguous, reason). If ambiguous, Lucca states the operational assumption
    on line 1 before calculation. Non-ambiguous queries return (False, None) to avoid
    superfluous assumptions.
    """
    if not text or not text.strip():
        return False, None
    lower = text.lower()

    # Fast check: exclude simple math or common non-financial questions
    if re.search(r"^\s*(what is|\d+\s*[\+\-\*\/]|\d+\s+multiplied|\d+\s+divided)", lower):
        if not any(k in lower for k in ("interest", "fee", "tax", "tip", "pallet", "round")):
            return False, None

    # 1. Financial interest without specifying simple vs compound
    has_interest = bool(re.search(r"\b(interest|rate of interest|earns interest|accrues interest|loan)\b", lower))
    has_explicit_convention = bool(re.search(r"\b(simple interest|compound(ed)?|compounding|apr|apy)\b", lower))
    if has_interest and not has_explicit_convention:
        return True, "Interest calculation without explicit simple vs compound convention specified"

    # 2. Multi-tier fee/tip/tax where base is ambiguous (subtotal vs grand total)
    has_fee = bool(re.search(r"\b(fee|service fee|delivery fee|convenience fee|vendor fee|tax|tip)\b", lower))
    has_multiple_costs = bool(re.search(r"\b(delivery|shipping|travel|expenses|freight|tip|subtotal)\b", lower))
    if has_fee and has_multiple_costs and "%" in text:
        if not re.search(r"\b(applied (strictly )?to|on (the )?(subtotal|groceries|merchandise|work) only)\b", lower):
            return True, "Percentage fee application ambiguous across subtotal vs grand total"

    # 3. Discrete physical entity packing/rounding without explicit rounding direction
    has_discrete_packing = bool(re.search(r"\b(how many\s+(pallets?|boxes|crates|containers|buses|vans|trips|hurdles))\b", lower))
    has_explicit_rounding = bool(re.search(r"\b(round(ed)? (up|down|to nearest)|ceiling|floor|at least|exact(ly)?)\b", lower))
    if has_discrete_packing and not has_explicit_rounding:
        return True, "Discrete physical unit allocation without explicit floor/ceil rounding direction"

    return False, None


@dataclass(frozen=True)
class TurnInput:
    """Unified turn input model bridging voice and text execution paths."""

    user_text: str
    trace: TurnTrace
    origin: Literal["voice", "text"]
    mode: Literal["audio", "transcript"] = "transcript"
    vad_speech_ms: float = 1000.0
    current_audio_b64: str | None = None
    current_text: str | None = None


class TurnPipeline:
    """
    Stateful execution pipeline executing the unified turn life-cycle.
    Maintains 100% behavioral parity across voice and text modalities.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self.orch = orchestrator
        self.sanity_guard = SanityCheckGuard()
        self.difficulty_estimator = DifficultyEstimator()

    # ------------------------------------------------------------------------
    # Phase 0: Turn State Reset
    # ------------------------------------------------------------------------

    def reset_turn_state(self) -> None:
        """Reset per-turn state for sandbox, supervisor, flags, and tool tracking."""
        self.orch.sandbox.reset_turn()
        self.orch.output_supervisor.reset_turn()
        self.orch.play_ring.clear_flag(FLAG_ABORT)
        self.orch.play_ring.clear_flag(FLAG_EOS)
        self.orch.current_turn_tool_calls = []
        self.orch.current_turn_receipts = []
        self.orch.current_turn_tier = ExecutionTier.FULL_LOOP
        self.orch.current_turn_tool_spoken = []
        self.orch.current_turn_tool_ok = True
        self.orch._last_unspoken_tool_msg = None
        self.orch._ratification_offered_this_turn = False
        self.orch.current_turn_plan = None

    # ------------------------------------------------------------------------
    # Phase 4 Helpers: REFLEX & ACT_THEN_NARRATE Dispatch
    # ------------------------------------------------------------------------

    def execute_reflex(
        self,
        trace: TurnTrace,
        winning_outcome: RuleOutcome | None,
        user_text: str,
        decision_id: str | None,
    ) -> None:
        """
        Execute a REFLEX tier turn: run plan or built-in emergency reflex,
        emit triple, and finalize.
        """
        try:
            if winning_outcome and winning_outcome.plan:
                tool_executions: list[str] = []
                for action in winning_outcome.plan.actions:
                    if isinstance(action, Say):
                        self.orch._speak_text(trace, action.text)
                        self.orch._publish_caption(action.text, source="assistant", is_final=True)
                    elif isinstance(action, ToolCall):
                        tool_res = self.orch._handle_tool_call(
                            trace, action.tool, dict(action.args), speak=True
                        )
                        status = (
                            "ok"
                            if (tool_res is None or getattr(tool_res, "ok", True))
                            else "failed"
                        )
                        args_str = ", ".join(f"{k}={v!r}" for k, v in action.args.items())
                        tool_executions.append(f"[Executed {action.tool}({args_str}) -> {status}]")
                    elif isinstance(action, AssertFact):
                        self.orch._commit_lisp_assertion(action, trace)
                        tool_executions.append(f"[Asserted {action.s} {action.p} {action.o}]")

                self.orch.rule_engine.emit_execution_triple(
                    rule_id=winning_outcome.rule_id,
                    plan=winning_outcome.plan,
                    signal="tool_exit_zero",
                    detail="REFLEX execution",
                )

                user_msg = user_text or "[Voice audio]"
                spoken_msg = " ".join(
                    a.text for a in winning_outcome.plan.actions if isinstance(a, Say)
                )
                exec_details = " ".join(tool_executions)
                assistant_msg = (
                    f"{spoken_msg} {exec_details}".strip()
                    if spoken_msg
                    else (exec_details or f"[Rule executed: {winning_outcome.rule_id}]")
                )
                self.orch.history.append({"role": "user", "content": user_msg})
                self.orch.history.append({"role": "assistant", "content": assistant_msg})
                self.orch.play_ring.set_flag(FLAG_EOS)
            else:
                # Built-in Emergency Reflex Fallback (<150ms halt)
                self.orch._abort_turn()
                lower_t = (user_text or "").lower()
                if any(w in lower_t for w in ("shut down", "turn off", "exit", "quit")):
                    ack_msg = "Shutting down."
                    self.orch.on_quit_requested()
                elif "pause" in lower_t:
                    ack_msg = "Paused."
                elif "mute" in lower_t:
                    ack_msg = "Muted."
                else:
                    ack_msg = "Stopped."

                self.orch._speak_text(trace, ack_msg)
                self.orch._publish_caption(ack_msg, source="assistant", is_final=True)
                user_msg = user_text or "[Voice audio]"
                self.orch.history.append({"role": "user", "content": user_msg})
                self.orch.history.append(
                    {"role": "assistant", "content": f"[Emergency Reflex: {ack_msg}]"}
                )
                self.orch.play_ring.set_flag(FLAG_EOS)
        finally:
            self.orch._finalize_turn(trace, decision_id)

    def execute_act_then_narrate(
        self,
        trace: TurnTrace,
        winning_outcome: RuleOutcome,
        user_text: str,
        decision_id: str | None,
    ) -> None:
        """
        Execute an ACT_THEN_NARRATE tier turn: run plan tools, emit triple,
        and stream narration.
        """
        try:
            last_tool_res: ToolResult | None = None
            last_tool_name: str = ""
            last_tool_args: dict[str, JsonValue] = {}
            # WO-10.4 (F11) & WO-22 Phase 1 (ITEM-017): narrate ALL plan actions, not just the last.
            exec_lines: list[str] = []
            step_tuples: list[tuple[str, dict[str, JsonValue], bool, str]] = []
            if winning_outcome.plan:
                for action in winning_outcome.plan.actions:
                    if isinstance(action, ToolCall):
                        tool_res = self.orch._handle_tool_call(
                            trace, action.tool, dict(action.args), speak=False
                        )
                        last_tool_res = tool_res
                        last_tool_name = action.tool
                        last_tool_args = dict(action.args)
                        ok = tool_res is None or getattr(tool_res, "ok", True)
                        raw_detail = (
                            str(getattr(tool_res, "content", "") or "")
                            or str(getattr(tool_res, "stderr", "") or "")
                        )[:200]
                        args_str = ", ".join(f"{k}={v!r}" for k, v in action.args.items())
                        status_str = "ok" if ok else "failed"
                        exec_lines.append(
                            f"{action.tool}({args_str}) -> {status_str}: {raw_detail}"
                        )
                        step_tuples.append((action.tool, dict(action.args), ok, raw_detail))
                    elif isinstance(action, AssertFact):
                        self.orch._commit_lisp_assertion(action, trace)
                        exec_lines.append(f"assert({action.s} {action.p} {action.o}) -> ok")
                        step_tuples.append(
                            (
                                "assert_fact",
                                {"s": action.s, "p": action.p, "o": action.o},
                                True,
                                "ok",
                            )
                        )
            if exec_lines:
                combined = "\n".join(exec_lines)
                last_tool_res = ToolResult(
                    call_id=f"plan-{winning_outcome.rule_id}",
                    ok=not any("failed" in line for line in exec_lines),
                    content=combined,
                    elapsed_ms=0.0,
                )
            else:
                say_actions = [
                    a.text for a in winning_outcome.plan.actions if isinstance(a, Say)
                ]
                if say_actions:
                    spoken = " ".join(say_actions)
                    self.orch._speak_text(trace, spoken)
                    self.orch._publish_caption(spoken, source="assistant", is_final=True)
                    user_msg = user_text or "[Voice audio]"
                    self.orch.history.append({"role": "user", "content": user_msg})
                    self.orch.history.append({"role": "assistant", "content": spoken})
                    self.orch.play_ring.set_flag(FLAG_EOS)
                    self.orch._finalize_turn(trace, decision_id)
                    return

            signal: Literal["tool_exit_zero", "pydantic_valid"] = (
                "tool_exit_zero"
                if (last_tool_res is None or getattr(last_tool_res, "ok", True))
                else "pydantic_valid"
            )
            self.orch.rule_engine.emit_execution_triple(
                rule_id=winning_outcome.rule_id,
                plan=winning_outcome.plan,
                signal=signal,
                detail="ACT_THEN_NARRATE execution",
            )

            mem_hits = self.orch._search_memories(user_text) if user_text else []
            eff_user_text = user_text
            if (
                last_tool_res
                and getattr(last_tool_res, "ok", True)
                and getattr(last_tool_res, "content", None)
            ):
                sanity_res = self.sanity_guard.validate(
                    tool_name=last_tool_name or winning_outcome.rule_id,
                    tool_args=last_tool_args,
                    tool_output=str(last_tool_res.content),
                    user_query=user_text or "",
                )
                if not sanity_res.is_valid and sanity_res.directive:
                    logger.warning(
                        "act_then_narrate_sanity_anomaly_detected",
                        tool=last_tool_name,
                        violation=sanity_res.violation_type,
                        reason=sanity_res.reason,
                    )
                    eff_user_text = (
                        f"{user_text}\n\n{sanity_res.directive}"
                        if user_text
                        else sanity_res.directive
                    )

            narration_msgs = build_narration_messages(
                tool_name=last_tool_name or winning_outcome.rule_id,
                tool_args=last_tool_args,
                tool_result=last_tool_res,
                user_text=eff_user_text,
                memories=mem_hits,
                stance_tag=self.orch.affect_tracker.get_prompt_suffix_tag(),
            )
            enable_thinking = self.difficulty_estimator.should_enable_thinking(
                user_text,
                intent="act_then_narrate",
            )
            trace.enable_thinking = enable_thinking
            self.orch._stream_llm_speech(
                trace=trace,
                user_msg=user_text or "[Voice audio]",
                decision_id=decision_id,
                messages=narration_msgs,
                enable_thinking=enable_thinking,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("act_then_narrate_error", error=str(e))
            self.orch._finalize_turn(trace, decision_id)

    # ------------------------------------------------------------------------
    # Phase 5 Helpers: Epistemic Context & Intent-Based Tool Gating
    # ------------------------------------------------------------------------

    def build_epistemic_context(
        self,
        user_text: str,
        yielded_context: dict[str, object] | None = None,
        route_decision: RouteDecision | None = None,
        spelling_hint: str | None = None,
        trace: TurnTrace | None = None,
    ) -> str | None:
        """
        Build epistemic context from search cascade, yield signals, F13 clarify hints,
        and spelling hints.
        """
        epistemic_ctx: str | None = None
        if user_text:
            is_epistemic, target_subs, _ = self.orch.cascade.classify_intent(user_text)
            if is_epistemic:
                is_file_or_web = any(
                    s in target_subs for s in (EpistemicSubstrate.WORKSPACE, EpistemicSubstrate.WEB)
                )
                is_ptt = getattr(trace, "origin", "ptt") == "ptt"
                if is_file_or_web and trace is not None and is_ptt:
                    cue = self.orch.cascade.select_floor_cue(user_text, target_subs[0])
                    self.orch._speak_text(trace, cue)
                    self.orch._publish_caption(cue, source="assistant", is_final=False)
                cascade_res = self.orch.cascade.query(
                    user_text, substrates=target_subs, emit_floor_cue=False
                )
                epistemic_ctx = cascade_res.synthesized_context or None

        if yielded_context and yielded_context.get("reason") not in ("define: no term", "no term", ""):
            yield_str = f"[Cognitive Bus Yield: {yielded_context['reason']}]"
            epistemic_ctx = f"{epistemic_ctx}\n{yield_str}" if epistemic_ctx else yield_str

        # WO-21 Phase 4: Theory of Mind User Knowledge Directive (Spec D-REAS-09)
        user_model = getattr(self.orch, "user_model", None)
        if user_model is not None and user_text:
            try:
                user_model_dir = user_model.format_directive(user_text)
                if user_model_dir:
                    if trace is not None:
                        trace.user_model_fired = True
                    um_block = f"[Theory of Mind — User Knowledge State]\n{user_model_dir}"
                    epistemic_ctx = f"{epistemic_ctx}\n\n{um_block}" if epistemic_ctx else um_block
            except Exception as exc:  # noqa: BLE001
                logger.debug("user_model_directive_error", error=str(exc))

        # WO-21 Phase 4: Case-Based Reasoning Episode Recall Precedents (Spec 06 §4)
        episode_recall = getattr(self.orch, "episode_recall", None)
        if episode_recall is not None and user_text:
            try:
                ep_hints = episode_recall.format_hints(user_text, limit=2)
                if ep_hints:
                    if trace is not None:
                        trace.episode_recall_fired = True
                    epistemic_ctx = f"{epistemic_ctx}\n\n{ep_hints}" if epistemic_ctx else ep_hints
            except Exception as exc:  # noqa: BLE001
                logger.debug("episode_recall_hints_error", error=str(exc))

        # WO-10.3 (F13): CLARIFY gets a brief-question directive
        if route_decision is not None and route_decision.action == RouteAction.CLARIFY:
            clarify_hint = (
                "[Clarify Mode: The user's utterance was very short or ambiguous. "
                "If the intent is unclear, ask ONE brief clarifying question in your "
                "companion voice. If the intent is still reasonably clear, answer "
                "directly without asking.]"
            )
            epistemic_ctx = f"{epistemic_ctx}\n{clarify_hint}" if epistemic_ctx else clarify_hint

        if spelling_hint:
            epistemic_ctx = f"{epistemic_ctx}\n{spelling_hint}" if epistemic_ctx else spelling_hint

        # WO-26 Phase 5: Defensive Disambiguation Directive (F-REAS-102)
        if user_text:
            is_ambiguous, ambig_reason = detect_operational_ambiguity(user_text)
            if is_ambiguous:
                disambig_hint = (
                    f"[Defensive Disambiguation Directive: {ambig_reason}. "
                    "State your operational assumption explicitly on line 1 before providing "
                    "calculations or numerical conclusions (e.g. 'Assumption: ...').]"
                )
                epistemic_ctx = f"{epistemic_ctx}\n\n{disambig_hint}" if epistemic_ctx else disambig_hint

        return epistemic_ctx

    def detect_follow_up_and_gate_tools(
        self,
        rule_state: RuleState,
        text_for_gate: str,
    ) -> list[object] | None:
        """
        Intent-based tool gating — suppress tools ONLY for dangerous or pure chit-chat.
        Returns empty list if tools are suppressed, or None to let _stream_llm_speech decide.
        """
        turn_tools: list[object] | None = None
        intent = rule_state.intent if hasattr(rule_state, "intent") else "unknown"
        toolless_intents = {"dangerous"}

        # WO-10.6 (F20): follow-up patterns are config-driven (heuristics.toml)
        follow_up_patterns = load_heuristics("follow_up_patterns")
        is_follow_up = False
        if text_for_gate:
            u_low = text_for_gate.lower()
            is_follow_up = any(p in u_low for p in follow_up_patterns)
            if not is_follow_up and self.orch.history:
                last_asst = next(
                    (
                        m.get("content", "")
                        for m in reversed(self.orch.history)
                        if m.get("role") == "assistant"
                    ),
                    "",
                )
                search_cues = ("search", "found", "look", "judge", "suburb", "results", "?")
                if any(w in last_asst.lower() for w in search_cues):
                    is_follow_up = True

        if intent in toolless_intents or (intent == "chit_chat" and not is_follow_up):
            turn_tools = []
            logger.info(
                "tool_gating_suppressed",
                intent=intent,
                reason="conversational or dangerous intent — tools withheld",
            )
        return turn_tools

    # ------------------------------------------------------------------------
    # Master Execution Pipeline (Phases 1 through 6)
    # ------------------------------------------------------------------------

    def run(self, inp: TurnInput) -> None:
        """
        Executes a single conversational turn end-to-end across all phases.
        Guarantees 100% parity across voice and text input origins.
        """
        trace = inp.trace
        user_text = inp.user_text

        # Phase 0: Reset turn state
        self.reset_turn_state()
        self.orch.current_turn_transcript = user_text
        decision_id: str | None = None

        if trace.interrupted:
            return

        # Phase 1: Input Normalization & Spelled-Word Attractor Neutralization
        normalized_text = normalize_transcript(user_text)
        _, detected_words = normalize_spelled_words(user_text)
        self.orch.active_detected_words = detected_words
        eff_user_text = normalized_text
        spelling_hint: str | None = None
        if detected_words:
            all_corrupt: list[str] = []
            for w in detected_words:
                c_vars = self.orch._neutralize_context_attractors(w)
                all_corrupt.extend(c_vars)
            w_str = ", ".join(f"'{w}'" for w in detected_words)
            if all_corrupt:
                c_str = ", ".join(f"'{c}'" for c in sorted(set(all_corrupt)))
                spelling_hint = (
                    f"[User Explicit Spelling Correction: The target entity is {w_str}. "
                    f"Disregard phonetically confused prior references to {c_str}. "
                    f"You must search for and reference {w_str} exactly.]"
                )
            else:
                spelling_hint = (
                    f"[User Explicit Spelling Correction: The target entity is spelled {w_str}. "
                    f"You must search for and reference {w_str} exactly.]"
                )

        eval_user_text = eff_user_text or user_text

        # Phase 2: Prior Turn Latching & Outcome Labeling
        if self.orch.prev_decision_record and self.orch.db is not None:
            try:
                next_intent, next_conf, _ = self.orch.router.classify_intent(eval_user_text)
                time_to_next = (
                    (time.time() - self.orch.prev_turn_ts) if self.orch.prev_turn_ts else None
                )
                label, reason = derive_label(
                    self.orch.prev_decision_record,
                    next_transcript=eval_user_text,
                    next_intent=next_intent,
                    next_intent_conf=next_conf,
                    time_to_next_turn_s=time_to_next,
                )
                persist_decision_label(
                    self.orch.db,
                    self.orch.prev_decision_record.decision_id,
                    label,
                    reason,
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("prev_decision_label_error", error=str(e))

        # Cross-Reference Intent Check (WO-21 Phase 3 Amendment B)
        if eval_user_text and is_cross_reference_command(eval_user_text):
            self.orch._handle_cross_reference(trace, eval_user_text)
            return

        # Ratification Confirmation Check (WO-21 Phase 3)
        pending = getattr(self.orch, "_pending_ratification", None)
        if isinstance(pending, PendingRatification) and eval_user_text:
            decision = parse_confirmation_response(eval_user_text)
            if decision == "confirm":
                self.orch._pending_ratification = None
                self.orch._commit_ratified_fact(pending, trace)
                ack_msg = f"Remembered that {pending.claim}."
                self.orch._speak_text(trace, ack_msg)
                self.orch._publish_caption(ack_msg, source="assistant", is_final=True)
                self.orch.history.append({"role": "user", "content": user_text})
                self.orch.history.append({"role": "assistant", "content": ack_msg})
                self.orch.play_ring.set_flag(FLAG_EOS)
                self.orch._finalize_turn(trace, None)
                return
            elif decision == "cancel":
                self.orch._pending_ratification = None
                ack_msg = "Okay, I won't remember that."
                self.orch._speak_text(trace, ack_msg)
                self.orch._publish_caption(ack_msg, source="assistant", is_final=True)
                self.orch.history.append({"role": "user", "content": user_text})
                self.orch.history.append({"role": "assistant", "content": ack_msg})
                self.orch.play_ring.set_flag(FLAG_EOS)
                self.orch._finalize_turn(trace, None)
                return
            else:
                # User said something else: clear pending offer (Trap 1: max 1 offer/turn)
                self.orch._pending_ratification = None

        # Diagnostic Self-Reasoning Check (WO-22 Phase 2)
        if eval_user_text and is_self_diagnosis_query(eval_user_text):
            _diagnoses, diag_speech = self.orch.run_self_diagnosis(eval_user_text, trace)
            self.orch.history.append({"role": "user", "content": user_text})
            self.orch.history.append({"role": "assistant", "content": diag_speech})
            self.orch.play_ring.set_flag(FLAG_EOS)
            self.orch._finalize_turn(trace, None)
            return

        # Phase 3: Rule State & Route Decision
        rule_state = self.orch._build_rule_state(eval_user_text, mode=inp.mode)
        yielded_context: dict[str, object] | None = None
        shadow_outcomes: list[RuleOutcome] = []
        active_outcomes: list[RuleOutcome] = []
        try:
            shadow_outcomes = self.orch.rule_engine.evaluate(rule_state, mode="shadow")
            active_outcomes = self.orch.rule_engine.evaluate(rule_state, mode="active")
            self.orch.current_turn_shadow_outcomes = shadow_outcomes
        except SchemeYieldSignal as e:
            logger.info("scheme_rule_yielded_to_core", reason=e.reason, context=e.context)
            yielded_context = {"reason": e.reason, "context": e.context}
        except SchemeInterruptSignal as e:
            logger.warning("scheme_rule_interrupted_core", reason=e.reason)
            self.orch._abort_turn()
            self.orch._speak_text(trace, f"Interrupted: {e.reason}")
            self.orch._finalize_turn(trace, None)
            return

        any_quarantine_fired = any(o.fired for o in shadow_outcomes)
        any_active_fired = any(o.fired for o in active_outcomes)
        has_registered_rule = any_active_fired

        route_decision = None
        try:
            vad_ms = int(inp.vad_speech_ms)
            route_decision = self.orch.router.route(
                transcript=eval_user_text,
                any_active_rule_fired=any_active_fired,
                any_quarantine_rule_fired=any_quarantine_fired,
                vad_speech_ms=vad_ms,
                trace_id=trace.trace_id,
                session_id=self.orch.session_id,
                hour_local=rule_state.hour_local,
                weekday=rule_state.weekday,
                session_turns=rule_state.session_turns,
                mode=inp.mode,
                has_registered_rule=has_registered_rule,
                last_tool=rule_state.last_tool,
                last_tool_ok=rule_state.last_tool_ok,
            )
            decision_id = (
                self.orch.router.last_decision_record.decision_id
                if self.orch.router.last_decision_record
                else None
            )
        except Exception as e:  # noqa: BLE001
            logger.error("router_execution_error", error=str(e))
        trace.t_route_done = now_ns()

        # Phase 4: Tier Dispatch (REFLEX / ACT_THEN_NARRATE Early Exit)
        if route_decision and route_decision.action == RouteAction.RULE:
            winning_outcome: RuleOutcome | None = None
            for outcome in active_outcomes:
                if outcome.fired and not outcome.errored and outcome.plan is not None:
                    winning_outcome = outcome
                    break

            if winning_outcome is None:
                lower_t = (user_text or "").lower()
                from lucca.router.heuristic import EMERGENCY_REFLEX_PATTERN  # noqa: PLC0415

                if EMERGENCY_REFLEX_PATTERN.search(lower_t):
                    self.orch.current_turn_tier = ExecutionTier.REFLEX
                    self.execute_reflex(
                        trace=trace,
                        winning_outcome=None,
                        user_text=user_text,
                        decision_id=decision_id,
                    )
                    return
                # Router selected RULE, but no rule plan fired and utterance
                # is not an emergency stop/pause. Fall through to Phase 5 LLM Full Loop.
                logger.warning(
                    "rule_route_no_plan_falling_back_to_llm",
                    text=user_text,
                    intent=getattr(route_decision, "intent", None),
                )
            else:
                has_tool_calls = any(
                    isinstance(a, ToolCall)
                    for a in winning_outcome.plan.actions
                )
                tier = (
                    getattr(route_decision, "tier", ExecutionTier.ACT_THEN_NARRATE)
                    if has_tool_calls
                    else ExecutionTier.REFLEX
                )
                self.orch.current_turn_tier = tier
                if tier == ExecutionTier.REFLEX:
                    self.execute_reflex(
                        trace=trace,
                        winning_outcome=winning_outcome,
                        user_text=user_text,
                        decision_id=decision_id,
                    )
                    return
                elif winning_outcome.plan:
                    self.execute_act_then_narrate(
                        trace=trace,
                        winning_outcome=winning_outcome,
                        user_text=user_text,
                        decision_id=decision_id,
                    )
                    return

        # Phase 5: Epistemic Context, Tool Gating & Streaming LLM Full Loop
        mem_hits = self.orch._search_memories(user_text) if user_text else []
        epistemic_ctx = self.build_epistemic_context(
            user_text=eval_user_text or user_text,
            yielded_context=yielded_context,
            route_decision=route_decision,
            spelling_hint=spelling_hint,
            trace=trace,
        )

        turn_tools = self.detect_follow_up_and_gate_tools(
            rule_state=rule_state,
            text_for_gate=eval_user_text or user_text,
        )

        current_text = (
            inp.current_text if inp.current_text is not None else (eval_user_text or user_text)
        )

        enable_thinking = self.difficulty_estimator.should_enable_thinking(
            eval_user_text or user_text,
            intent=rule_state.intent if hasattr(rule_state, "intent") else None,
        )
        trace.enable_thinking = enable_thinking

        # Tier 3 Code Synthesis with Autonomous Docker Preflight Loop (WO-26 Phase 4)
        if is_code_synthesis_request(eval_user_text or user_text):
            self.orch._stream_code_synthesis(
                trace=trace,
                user_msg=user_text or "[Code Synthesis]",
                decision_id=decision_id,
                current_text=current_text,
                memories=mem_hits,
                epistemic_context=epistemic_ctx,
            )
            return

        self.orch._stream_llm_speech(
            trace=trace,
            user_msg=user_text or "[Voice audio]",
            decision_id=decision_id,
            current_audio_b64=inp.current_audio_b64,
            current_text=current_text,
            memories=mem_hits,
            epistemic_context=epistemic_ctx,
            tools=turn_tools,
            enable_thinking=enable_thinking,
        )
