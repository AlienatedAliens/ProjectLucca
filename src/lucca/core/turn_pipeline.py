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

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import structlog

from lucca.brain.prompt_builder import build_narration_messages
from lucca.core.cascade import EpistemicSubstrate
from lucca.core.config import load_heuristics
from lucca.core.exceptions import SchemeInterruptSignal, SchemeYieldSignal
from lucca.core.sanity_guard import SanityCheckGuard
from lucca.core.schemas import (
    ExecutionTier,
    JsonValue,
    RouteAction,
    RouteDecision,
    RuleOutcome,
    RuleState,
    Say,
    ToolCall,
    ToolResult,
)
from lucca.core.trace import TurnTrace, now_ns
from lucca.router.labeler import derive_label, persist_decision_label
from lucca.senses.ring_buffer import FLAG_ABORT, FLAG_EOS

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


def normalize_spelled_words(transcript: str) -> tuple[str, list[str]]:
    """
    Detects single-letter spelling sequences (hyphenated 'F-A-W-K-N-E-R', period-separated
    'F. A. W. K. N. E. R.', or space-separated single letters 'F A W K N E R') from ASR output,
    assembles them into title-cased words, and returns (normalized_transcript, detected_words).
    """
    detected_words: list[str] = []

    # 1. Period-separated letters (e.g. F. A. W. K. N. E. R. or F.A.W.K.N.E.R.)
    def replace_period(m: re.Match[str]) -> str:
        raw = str(m.group(0))
        letters = re.findall(r"[a-zA-Z]", raw)
        if len(letters) >= 3:
            w = str("".join(letters).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(r"\b[a-zA-Z]\.(?:\s*[a-zA-Z]\.){2,}", replace_period, transcript)

    # 2. Hyphen-separated letters (e.g. F-A-W-K-N-E-R or F - A - W - K - N - E - R)
    def replace_hyphen(m: re.Match[str]) -> str:
        raw = str(m.group(0))
        letters = re.findall(r"[a-zA-Z]", raw)
        if len(letters) >= 3:
            w = str("".join(letters).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(r"\b[a-zA-Z](?:\s*-\s*[a-zA-Z]){2,}\b", replace_hyphen, text)

    # 3. Space-separated single letters (e.g. F A W K N E R or W K N E R)
    def replace_spaces(m: re.Match[str]) -> str:
        raw = str(m.group(1))
        tokens = raw.split()
        if len(tokens) >= 3 and all(len(t) == 1 and t.isalpha() for t in tokens):
            w = str("".join(tokens).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(
        r"(?:^|(?<=\s))([a-zA-Z](?:\s+[a-zA-Z]){2,})(?=\s|[.,!?]|$)",
        replace_spaces,
        text,
    )

    return text, list(dict.fromkeys(detected_words))


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
            # WO-10.4 (F11): narrate ALL plan actions, not just the last.
            exec_lines: list[str] = []
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
            if exec_lines:
                combined = "\n".join(exec_lines)
                last_tool_res = ToolResult(
                    call_id=f"plan-{winning_outcome.rule_id}",
                    ok=not any("failed" in line for line in exec_lines),
                    content=combined,
                    elapsed_ms=0.0,
                )

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
                if is_file_or_web and trace is not None:
                    cue = self.orch.cascade.select_floor_cue(user_text, target_subs[0])
                    self.orch._speak_text(trace, cue)
                    self.orch._publish_caption(cue, source="assistant", is_final=False)
                cascade_res = self.orch.cascade.query(
                    user_text, substrates=target_subs, emit_floor_cue=False
                )
                epistemic_ctx = cascade_res.synthesized_context or None

        if yielded_context:
            yield_str = f"[Cognitive Bus Yield: {yielded_context['reason']}]"
            epistemic_ctx = f"{epistemic_ctx}\n{yield_str}" if epistemic_ctx else yield_str

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
        normalized_text, detected_words = normalize_spelled_words(user_text)
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
        has_registered_rule = any(
            r.status == "ACTIVE" for r in self.orch.rule_engine.rules.values()
        )

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

            tier = getattr(route_decision, "tier", ExecutionTier.ACT_THEN_NARRATE)
            self.orch.current_turn_tier = tier
            if tier == ExecutionTier.REFLEX:
                self.execute_reflex(
                    trace=trace,
                    winning_outcome=winning_outcome,
                    user_text=user_text,
                    decision_id=decision_id,
                )
                return
            elif winning_outcome and winning_outcome.plan:
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
            user_text=user_text,
            yielded_context=yielded_context,
            route_decision=route_decision,
            spelling_hint=spelling_hint,
            trace=trace if inp.origin == "voice" else None,
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
