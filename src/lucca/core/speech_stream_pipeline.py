"""
Project Lucca — Speech Stream Pipeline (WO-43 Phase 2.2)
Spec: plans/wo43_refactor_and_power/02_PHASE2_ORCHESTRATOR_DECOMPOSITION_AND_ORGAN_WIRING_SPEC.md §3

Extracted from Orchestrator: encapsulates streaming LLM response generation,
multi-round tool convergence loop, BDI / tool-fit pre-execution guards,
output supervisor chunk gating, and non-empty synthesis fallback.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

import structlog
from pydantic import JsonValue

from lucca.brain.chunker import StreamingChunker, sanitize_for_voice
from lucca.brain.prompt_builder import get_all_tool_definitions
from lucca.core.coherence import detect_promised_action_claims
from lucca.core.convergence import TracebackDivergenceGuard
from lucca.core.ipc_schemas import Envelope, PlayBeginPayload
from lucca.core.schemas import (
    ChatMessage,
    MemoryHit,
    TokenDelta,
    ToolCallEnd,
    ToolDefinition,
    ToolResult,
)
from lucca.core.tool_shortlister import check_tool_fit
from lucca.core.trace import TurnTrace, now_ns
from lucca.core.turn_pipeline import SubTurnScratchpadBuffer
from lucca.senses.ring_buffer import FLAG_ABORT, FLAG_EOS

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


class SpeechStreamPipeline:
    """Encapsulates streaming LLM speech generation and multi-round tool convergence."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orch = orchestrator

    def select_verbal_cue(self, tool_name: str) -> str:
        """Selects a natural verbal thinking cue per Proposal I / Owner Section 6 requirement."""
        t = tool_name.lower()
        if "read" in t or "cat" in t or "inspect" in t:
            return "Checking that file for you..."
        if "write" in t or "save" in t:
            return "Writing that down now..."
        if "launch" in t or "open" in t:
            return "Opening that up..."
        if "calc" in t:
            return "Running that calculation..."
        if "query" in t:
            return "Checking my systems..."
        if "fetch" in t or "web" in t:
            return "Looking that up online..."
        if "skill" in t:
            return "Executing that procedure..."
        return "On it, working on that now..."

    def register_receipt_citation_urls(
        self,
        tool_name: str,
        tool_args: Mapping[str, object],
        tool_res: ToolResult,
    ) -> None:
        """
        Registers verified URLs from search, fetch, or browse receipts on the output supervisor.
        """
        orch = self._orch
        if tool_name == "search_web" and getattr(tool_res, "structured", None):
            search_urls: list[str] = []
            structured = tool_res.structured or {}
            search_items = structured.get("results") or structured.get("sources") or []
            if isinstance(search_items, list):
                for s_item in search_items:
                    if isinstance(s_item, dict) and s_item.get("url"):
                        search_urls.append(str(s_item["url"]))
            if tool_res.content:
                search_urls.extend(re.findall(r"https?://[^\s<>\"'()]+", tool_res.content))
            if hasattr(orch.output_supervisor, "register_allowed_urls"):
                orch.output_supervisor.register_allowed_urls(search_urls)
        elif tool_name in ("fetch_url", "browse_page"):
            target_u = tool_args.get("url")
            to_register: list[str] = []
            if isinstance(target_u, str) and target_u:
                to_register.append(target_u)
            res_structured = getattr(tool_res, "structured", None)
            if isinstance(res_structured, dict):
                u_val = res_structured.get("url")
                if isinstance(u_val, str) and u_val:
                    to_register.append(u_val)
                emb = res_structured.get("embedded_links")
                if isinstance(emb, list):
                    to_register.extend(str(x) for x in emb if x)
            if to_register and hasattr(orch.output_supervisor, "register_allowed_urls"):
                orch.output_supervisor.register_allowed_urls(to_register)

    def stream_llm_speech(
        self,
        trace: TurnTrace,
        user_msg: str,
        decision_id: str | None,
        messages: list[ChatMessage] | None = None,
        current_audio_b64: str | None = None,
        current_image_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        tools: list[ToolDefinition] | None = None,
        max_rounds: int = 8,
        epistemic_context: str | None = None,
        enable_thinking: bool | None = None,
        user_model_directive: str | None = None,
        episode_hints: list[str] | str | None = None,
        grammar: str | None = None,
    ) -> None:
        """
        Executes streaming LLM response generation with multi-step tool re-prompting
        and verbal thinking cues (Proposals I, J & D-BRAIN-03).
        """
        orch = self._orch
        orch._maybe_speak_pending_updates(trace)

        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        orch._publish_bus(begin_env)

        chunk_index = 0
        chunker = StreamingChunker()
        first_token_seen = False
        full_response_text: list[str] = []
        scratchpad_buffer = SubTurnScratchpadBuffer()
        tool_receipts: list[dict[str, JsonValue]] = []
        # WO-9 A5 + WO-43 Sub-Step 2.3: repeated-call & traceback divergence guard state
        call_signatures: list[str] = []
        divergence_guard = TracebackDivergenceGuard(
            max_recurrence=2,
            max_steps=max(12, max_rounds * 2),
            similarity_threshold=0.99,
        )
        loop_diverged = False

        if tools is None:
            if orch.execute_tools:
                active_rules = [r for r in orch.rule_engine.rules.values() if r.status == "ACTIVE"]
                tools = get_all_tool_definitions(active_rules)
            else:
                tools = []

        # If an image is already attached to this turn, strip screenshot_capture
        # so the model never attempts to capture screen or trigger confirmation prompts.
        turn_has_image = bool(
            current_image_b64
            or getattr(orch, "_pending_image_b64", None)
            or getattr(orch, "current_turn_image_b64", None)
        )
        if turn_has_image and tools:

            def _is_screenshot_tool(t: object) -> bool:
                if isinstance(t, dict):
                    fn = t.get("function")
                    if isinstance(fn, dict) and fn.get("name") == "screenshot_capture":
                        return True
                    if t.get("name") == "screenshot_capture":
                        return True
                fn = getattr(t, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None) == "screenshot_capture":
                        return True
                if getattr(t, "name", None) == "screenshot_capture":
                    return True
                return False

            tools = [t for t in tools if not _is_screenshot_tool(t)]
            logger.info("screenshot_tool_suppressed_image_in_context", remaining_tools=len(tools))

        # Seed session-scoped allowed URLs from conversation history & epistemic context
        history_urls: list[str] = []
        for h_msg in orch.history:
            content_val = h_msg.get("content", "")
            if content_val:
                history_urls.extend(re.findall(r"https?://[^\s<>\"'()]+", content_val))
        if epistemic_context:
            history_urls.extend(re.findall(r"https?://[^\s<>\"'()]+", epistemic_context))
        # If user query references local dev or ports, seed localhost into allowed URLs
        local_cues = ("localhost", "127.0.0.1", "ollama", "port", "api server")
        if user_msg and any(w in user_msg.lower() for w in local_cues):
            history_urls.extend(["http://localhost", "http://127.0.0.1"])
        if history_urls and hasattr(orch.output_supervisor, "register_allowed_urls"):
            orch.output_supervisor.register_allowed_urls(history_urls)
        sup_ctx: list[dict[str, str]] = [
            {"role": str(m.get("role", "")), "content": str(m.get("content", ""))}
            for m in orch.history[-4:]
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]
        if user_msg:
            sup_ctx.append({"role": "user", "content": user_msg})
        if hasattr(orch.output_supervisor, "set_turn_context"):
            orch.output_supervisor.set_turn_context(sup_ctx if sup_ctx else user_msg)

        def _trigger_supervisor_abort(
            reason_msg: str, offending_chunk: str, breach_type: str | None = None
        ) -> None:
            nonlocal chunk_index
            logger.warning(
                "output_supervisor_tier1_abort",
                reason=reason_msg,
                chunk=offending_chunk,
                breach_type=breach_type,
                trace_id=trace.trace_id,
            )
            trace.interrupted = True
            orch.play_ring.set_flag(FLAG_ABORT)
            orch.speech_output.clear_queue()
            is_citation_breach = (
                breach_type == "ungrounded_citation"
                or "ungrounded" in reason_msg.lower()
                or "citation" in reason_msg.lower()
            )
            if is_citation_breach:
                refusal = (
                    "I apologize, but I do not have a verified source for "
                    "that citation and won't guess."
                )
            else:
                refusal = "I cannot fulfill that request as it violates core safety invariants."
            orch._publish_caption(refusal, source="assistant", is_final=True)
            orch._speak_text(trace, refusal)
            orch.current_turn_assistant_reply = refusal
            orch.history.append({"role": "user", "content": user_msg})
            orch.history.append({"role": "assistant", "content": refusal})

        current_stance = orch.affect_tracker.get_prompt_suffix_tag()
        first_python_err: str | None = None
        python_turns_taken: int = 0
        rejected_round_span: tuple[int, int] | None = None

        try:
            for round_num in range(1, max_rounds + 1):
                if trace.interrupted or orch._cancel_token.is_set():
                    break

                was_diverged_at_round_start = loop_diverged
                round_tool_called = False
                round_response_text: list[str] = []
                round_failed_tools: list[str] = []
                pre_round_text_len = len(full_response_text)
                print(f"[Lucca R{round_num}] " if round_num > 1 else "[Lucca] ", end="", flush=True)
                if round_num == 1:
                    trace.t_llm_sent = now_ns()

                # WO-9 A5: convergence loop — tools stay available every round
                # and the loop terminates when the model stops calling tools.
                # The hard cap is a runaway guard only: on the final round tools
                # are withdrawn and the model must summarise honestly.
                if round_num == max_rounds and tools:
                    scratchpad_buffer.add_user_directive(
                        "[Tool Budget Reached: You have used the maximum number "
                        "of tool rounds. Do not call any more tools. Summarise "
                        "what you found and what you could NOT verify; never "
                        "fabricate missing facts.]"
                    )
                    trace.cap_hit = True
                    logger.info("tool_round_cap_reached", max_rounds=max_rounds)
                round_tools = [] if (round_num == max_rounds or loop_diverged) else tools

                for event in orch.llm.stream_turn(
                    current_audio_b64=current_audio_b64 if round_num == 1 else None,
                    current_image_b64=current_image_b64 if round_num == 1 else None,
                    current_text=current_text or user_msg,
                    history=orch.history,
                    memories=memories,
                    tools=round_tools,
                    messages=messages,
                    tool_messages=scratchpad_buffer.messages if scratchpad_buffer.messages
                        else None,
                    trace_id=trace.trace_id,
                    epistemic_context=epistemic_context,
                    stance_tag=current_stance,
                    enable_thinking=enable_thinking,
                    user_model_directive=user_model_directive,
                    episode_hints=episode_hints,
                    grammar=grammar if not round_tools else None,
                ):
                    if trace.interrupted or orch._cancel_token.is_set():
                        break

                    if isinstance(event, TokenDelta) and event.delta:
                        if rejected_round_span is not None:
                            r_start, r_end = rejected_round_span
                            del full_response_text[r_start:r_end]
                            pre_round_text_len = len(full_response_text)
                            rejected_round_span = None
                            chunker = StreamingChunker()
                            if hasattr(orch, "speech_output") and orch.speech_output is not None:
                                orch.speech_output.clear_queue()

                        if not first_token_seen:
                            first_token_seen = True
                            trace.t_llm_first_token = now_ns()

                        trace.tokens_out += 1
                        full_response_text.append(event.delta)
                        round_response_text.append(event.delta)
                        print(event.delta, end="", flush=True)

                        accumulated = "".join(full_response_text)
                        orch._publish_caption(accumulated, source="assistant", is_final=False)

                        for chunk in chunker.feed(event.delta):
                            if trace.interrupted:
                                break

                            eval_text = (
                                chunk.raw_text if getattr(chunk, "raw_text", None) else chunk.text
                            )
                            emitted_chunks, should_abort = orch.output_supervisor.feed_chunk(
                                chunk, eval_text, verified_receipts=tool_receipts
                            )
                            if should_abort:
                                _trigger_supervisor_abort(
                                    "Tier 1 Capitulation/Provenance breach", eval_text
                                )
                                break

                            for em_chunk, _em_gate in emitted_chunks:
                                clean_chunk_text = sanitize_for_voice(em_chunk.text)
                                if not clean_chunk_text:
                                    continue
                                if chunk_index == 0:
                                    trace.t_first_chunk = now_ns()
                                    orch._set_state("speaking")

                                orch._enqueue_tts_chunk(trace, em_chunk.chunk_id, clean_chunk_text)
                                chunk_index += 1

                    elif isinstance(event, ToolCallEnd):
                        if was_diverged_at_round_start:
                            logger.warning(
                                "subturn_tool_call_ignored_after_divergence",
                                round_num=round_num,
                                tool=event.call.tool,
                            )
                            continue
                        round_tool_called = True
                        call_id = event.call.call_id
                        tool_name = event.call.tool
                        tool_args = dict(event.call.args)

                        # Speculative BDI Validation (Milestone 4)
                        bdi_res = orch.bdi_validator.validate_tool_call(
                            tool_name,
                            tool_args,
                            taint_flags=getattr(getattr(orch, "sandbox", None), "taint_flags", 0),
                        )
                        if not bdi_res.is_valid:
                            round_failed_tools.append(tool_name)
                            logger.warning(
                                "speculative_bdi_call_rejected",
                                tool=tool_name,
                                reason=bdi_res.reason,
                                elapsed_us=bdi_res.elapsed_us,
                            )
                            content_str = (
                                f"Speculative Invariant Violation: {bdi_res.reason}. "
                                "Action prohibited."
                            )
                            scratchpad_buffer.add_assistant_tool_call(
                                call_id=call_id,
                                tool_name=tool_name,
                                tool_args=tool_args,
                            )
                            scratchpad_buffer.add_tool_result(
                                call_id=call_id,
                                tool_name=tool_name,
                                raw_output=content_str,
                                is_error=True,
                            )
                            continue

                        # BFCL <tool_fit_check> guard via VerifierWorker (WO-36 §36.5)
                        verifier_inst = getattr(orch, "verifier", None)
                        if user_msg and verifier_inst is not None:
                            if not check_tool_fit(tool_name, user_msg, verifier=verifier_inst):
                                round_failed_tools.append(tool_name)
                                logger.warning(
                                    "tool_fit_guard_rejected",
                                    tool=tool_name,
                                    query=user_msg[:80],
                                )
                                content_str = (
                                    f"<tool_fit_check> Tool '{tool_name}' rejected: "
                                    "query does not require this tool."
                                )
                                scratchpad_buffer.add_assistant_tool_call(
                                    call_id=call_id,
                                    tool_name=tool_name,
                                    tool_args=tool_args,
                                )
                                scratchpad_buffer.add_tool_result(
                                    call_id=call_id,
                                    tool_name=tool_name,
                                    raw_output=content_str,
                                    is_error=True,
                                )
                                continue

                        # Emit verbal thinking cue before tool execution (Proposal I)
                        cue = orch._select_verbal_cue(tool_name)
                        print(f'\n[Lucca Cue] "{cue}"', flush=True)
                        orch._speak_text(trace, cue)

                        # Execute tool
                        tool_res = orch._handle_tool_call(trace, tool_name, tool_args, speak=False)

                        if tool_res is not None:
                            if tool_name == "run_python":
                                python_turns_taken += 1
                                code_executed = str(tool_args.get("code", ""))
                                if not tool_res.ok and first_python_err is None:
                                    first_python_err = str(
                                        tool_res.stderr or tool_res.content or "ExecutionError"
                                    )
                                    orch._log_impasse_to_backlog(
                                        query=user_msg or "run_python execution",
                                        code=code_executed,
                                        error_trace=first_python_err,
                                    )
                                elif tool_res.ok:
                                    if (
                                        getattr(orch, "episodic_code_cache", None) is not None
                                        and code_executed.strip()
                                    ):
                                        try:
                                            orch.episodic_code_cache.retain_episode(
                                                query=user_msg or "run_python execution",
                                                code=code_executed,
                                                output=str(tool_res.content or ""),
                                                method="OrchestratorRunPython",
                                                turns_taken=python_turns_taken,
                                            )
                                        except Exception as cbr_err:  # noqa: BLE001
                                            logger.debug(
                                                "run_python_cbr_retain_failed", error=str(cbr_err)
                                            )
                                    sink_inst = getattr(
                                        orch, "cognitive_outcome_sink", None
                                    ) or getattr(orch, "cognitive_sink", None)
                                    if sink_inst is not None:
                                        try:
                                            sink_inst.record_cegis_outcome(
                                                task_id=f"turn-{trace.trace_id[:8]}",
                                                problem_summary=user_msg[:120]
                                                if user_msg
                                                else "run_python execution",
                                                engine_name="OrchestratorRunPython",
                                                success=True,
                                                turns_taken=python_turns_taken,
                                                final_code=code_executed,
                                                turn_1_error=first_python_err,
                                                verified_strategy="Multi-round tool loop repair"
                                                if python_turns_taken >= 2
                                                else "Direct run_python",
                                                status_label="VERIFIED_REPAIRED_PROGRAM"
                                                if python_turns_taken >= 2
                                                else "CHECKED_FORMALIZATION_AGREED",
                                            )
                                        except Exception as sink_err:  # noqa: BLE001
                                            logger.debug(
                                                "run_python_outcome_sink_failed",
                                                error=str(sink_err),
                                            )
                            if not tool_res.ok:
                                round_failed_tools.append(tool_name)
                            if tool_res.ok:
                                tool_target = str(
                                    tool_args.get("path")
                                    or tool_args.get("filename")
                                    or tool_args.get("name")
                                    or tool_args.get("title")
                                    or tool_args.get("target")
                                    or tool_args.get("command")
                                    or tool_args.get("app_name")
                                    or tool_args.get("url")
                                    or tool_args.get("query")
                                    or tool_args.get("code")
                                    or ""
                                )
                                tool_receipts.append({"action": tool_name, "target": tool_target})
                                self.register_receipt_citation_urls(tool_name, tool_args, tool_res)

                            if tool_res.content:
                                content_str = str(tool_res.content)
                            elif tool_res.structured:
                                content_str = json.dumps(tool_res.structured)
                            elif tool_res.stderr and not tool_res.ok:
                                content_str = f"Error: {tool_res.stderr}"
                            elif not tool_res.ok:
                                content_str = f"Error: {tool_name} failed"
                            else:
                                content_str = "Success"
                        else:
                            content_str = "Action completed."

                        scratchpad_buffer.add_assistant_tool_call(
                            call_id=call_id,
                            tool_name=tool_name,
                            tool_args=tool_args,
                        )
                        scratchpad_buffer.add_tool_result(
                            call_id=call_id,
                            tool_name=tool_name,
                            raw_output=content_str,
                            is_error=not (tool_res is not None and tool_res.ok),
                        )

                        # WO-9 A5 + WO-43 Sub-Step 2.3: repeated-call & TracebackDivergenceGuard
                        call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                        call_signatures.append(call_sig)
                        err_sig = (
                            content_str[:120]
                            if not (tool_res is not None and tool_res.ok)
                            else None
                        )
                        div_report = divergence_guard.record_step(
                            state_repr=call_sig,
                            error_signature=err_sig,
                        )
                        if div_report.diverged or call_signatures.count(call_sig) >= 2:
                            if (
                                not (tool_res is not None and tool_res.ok)
                                or len(call_signatures) >= 3
                            ):
                                loop_diverged = True
                            reason_str = (
                                div_report.reason.value
                                if div_report.reason is not None
                                else "state_cycle"
                            )
                            logger.warning(
                                "subturn_loop_diverged",
                                round_num=round_num,
                                tool=tool_name,
                                reason=reason_str,
                                detail=div_report.detail,
                                step_count=div_report.step_count,
                            )
                            scratchpad_buffer.add_user_directive(
                                "[Repeat Guard: You already issued this exact "
                                "call and it returned a result above. Use that "
                                "result, or try a different approach — do not "
                                f"repeat it. Divergence Guard ({reason_str}): "
                                f"{div_report.detail}. Synthesize your final response now without "
                                "calling further tools.]"
                            )
                        # WO-13.1: Pre-Narration Sanity-Check Guard (Fault Mode C)
                        if tool_res is not None and tool_res.ok and content_str:
                            sanity_res = orch.turn_pipeline.sanity_guard.validate(
                                tool_name=tool_name,
                                tool_args=tool_args,
                                tool_output=content_str,
                                user_query=user_msg,
                            )
                            if not sanity_res.is_valid and sanity_res.directive:
                                logger.warning(
                                    "tool_output_sanity_anomaly_detected",
                                    round_num=round_num,
                                    tool=tool_name,
                                    violation=sanity_res.violation_type,
                                    reason=sanity_res.reason,
                                )
                                scratchpad_buffer.add_user_directive(sanity_res.directive)

                # WO-11.2: G1+G6 unified honesty & register nudge (D-HON-01)
                if round_failed_tools:
                    failed_names = ", ".join(dict.fromkeys(round_failed_tools))
                    logger.info(
                        "tool_failure_honesty_nudge_injected",
                        round_num=round_num,
                        failed_tools=failed_names,
                    )
                    honesty_text = (
                        f"[Honesty Directive: A tool you called this turn failed "
                        f"({failed_names}). State the failure plainly. Never guess, "
                        "estimate, or fabricate the result the tool was supposed to "
                        "produce — especially numbers. Do not use celebration, "
                        "confidence, or success register when reporting failed or "
                        "unverified results. If solving an analytical, logic, or "
                        "mathematical problem, you may provide your step-by-step "
                        "chain-of-thought derivation clearly labeled as an analytical "
                        "derivation rather than claiming tool execution.]"
                    )
                    if round_num < max_rounds and any(
                        t in ("run_python", "bash", "execute_code") for t in round_failed_tools
                    ):
                        logger.info(
                            "tool_failure_feedback_loop_injected",
                            round_num=round_num,
                            failed_tools=failed_names,
                        )
                        honesty_text += (
                            f"\n[Execution Feedback Loop: Tool '{
                                failed_names}' produced an execution error or traceback. "
                            "Diagnose the error, fix the syntax/logic/attribute mistake, and "
                            "re-call the tool to verify the result.]"
                        )
                    scratchpad_buffer.add_user_directive(honesty_text)

                if not round_tool_called:
                    if (
                        round_num < max_rounds
                        and tools
                        and getattr(orch.output_supervisor, "turn_has_stalled", False)
                    ):
                        logger.info(
                            "stalling_research_question_intercepted_forcing_tool_execution",
                            round_num=round_num,
                        )
                        scratchpad_buffer.add_user_directive(
                            "[Autonomous Research Directive: Do not output "
                            "conversational filler, cheerleading, or empty promises. "
                            "Do not ask rhetorical permission questions or request "
                            "clarification. Execute search_web or fetch_url immediately "
                            "to retrieve and present the verified facts.]"
                        )
                        orch.output_supervisor.turn_has_stalled = False
                        rejected_round_span = (pre_round_text_len, len(full_response_text))
                        continue
                    if round_num < max_rounds and tools:
                        round_text_str = "".join(round_response_text).strip()
                        active_receipts = (
                            list(getattr(orch, "current_turn_receipts", [])) or tool_receipts
                        )
                        promises = (
                            detect_promised_action_claims(
                                round_text_str,
                                user_context=sup_ctx if sup_ctx else user_msg,
                            )
                            if not active_receipts
                            else []
                        )
                        if promises:
                            logger.info(
                                "promised_action_without_tool_call_intercepted",
                                round_num=round_num,
                                promises=promises[:2],
                            )
                            rejected_round_span = (pre_round_text_len, len(full_response_text))
                            scratchpad_buffer.add_user_directive(
                                "[Honesty Directive: You stated you would perform "
                                f"an action ({' ; '.join(promises[:2])}) but issued "
                                "no tool call. Discard your previous draft response. "
                                "Either call the appropriate tool now, or state plainly "
                                "that you have NOT done it and will not pretend otherwise.]"
                            )
                            continue
                        if round_text_str:
                            ungrounded_breach = orch._check_functional_coherence(
                                round_text_str,
                                active_receipts,
                                user_context=sup_ctx if sup_ctx else user_msg,
                            )
                            if ungrounded_breach:
                                logger.info(
                                    "ungrounded_action_claim_without_receipt_intercepted",
                                    round_num=round_num,
                                    breach=ungrounded_breach,
                                )
                                rejected_round_span = (pre_round_text_len, len(full_response_text))
                                scratchpad_buffer.add_user_directive(
                                    "[Honesty & Grounding Directive: Your previous draft response "
                                    f"({round_text_str[:160]!r}) claimed or simulated performing "
                                    f"an action without a verified tool receipt ({
                                        ungrounded_breach}). "
                                    "Discard that draft completely and respond again from scratch: "
                                    "either call an available tool now to perform the action "
                                        "for real, "
                                    "or state plainly and honestly that you cannot perform "
                                        "or inspect "
                                    "that action directly and have NOT done so.]"
                                )
                                continue
                    break
                if was_diverged_at_round_start:
                    break

            # WO-9 A5: convergence telemetry
            trace.rounds_used = round_num

            # Flush remaining chunker text
            if not trace.interrupted and not orch._cancel_token.is_set():
                for chunk in chunker.flush():
                    if trace.interrupted or orch._cancel_token.is_set():
                        break
                    eval_text = chunk.raw_text if getattr(chunk, "raw_text", None) else chunk.text
                    emitted_chunks, should_abort = orch.output_supervisor.feed_chunk(
                        chunk, eval_text, verified_receipts=tool_receipts
                    )
                    if should_abort:
                        _trigger_supervisor_abort(
                            "Tier 1 Capitulation/Provenance breach on flush", eval_text
                        )
                        break

                    for em_chunk, _em_gate in emitted_chunks:
                        clean_chunk_text = sanitize_for_voice(em_chunk.text)
                        if not clean_chunk_text:
                            continue
                        if chunk_index == 0:
                            trace.t_first_chunk = now_ns()
                            orch._set_state("speaking")
                        orch._enqueue_tts_chunk(trace, em_chunk.chunk_id, clean_chunk_text)
                        chunk_index += 1

                # Final flush of output supervisor lookahead buffer
                if not trace.interrupted and not orch._cancel_token.is_set():
                    emitted_final, should_abort = orch.output_supervisor.flush()
                    if should_abort:
                        _trigger_supervisor_abort(
                            "Tier 1 Capitulation unrefuted end-of-stream", ""
                        )
                    else:
                        for em_chunk, _em_gate in emitted_final:
                            clean_final_text = sanitize_for_voice(em_chunk.text)
                            if not clean_final_text:
                                continue
                            if chunk_index == 0:
                                trace.t_first_chunk = now_ns()
                                orch._set_state("speaking")
                            orch._enqueue_tts_chunk(trace, em_chunk.chunk_id, clean_final_text)
                            chunk_index += 1

                if chunk_index > 0 and not trace.interrupted and not orch._cancel_token.is_set():
                    orch.speech_output.wait_for_playback(trace)

                if not trace.interrupted and not orch._cancel_token.is_set():
                    orch.play_ring.set_flag(FLAG_EOS)

            trace.t_llm_done = now_ns()
            print("\n", flush=True)

            # WO-26 Phase 5: Non-Empty Synthesis Guardrail
            has_successful_tool = any(r.get("action") for r in tool_receipts) or any(
                not t.get("is_error", False) for t in scratchpad_buffer._intermediate_traces
            )
            synthesized_text = "".join(full_response_text).strip()
            if (
                has_successful_tool
                and not synthesized_text
                and not trace.interrupted
                and not orch._cancel_token.is_set()
            ):
                logger.warning(
                    "non_empty_synthesis_guardrail_triggered",
                    trace_id=trace.trace_id,
                    tools=[r.get("action") for r in tool_receipts],
                )
                scratchpad_buffer.add_user_directive(
                    "[Non-Empty Synthesis Directive: Your tool execution succeeded. "
                    "Summarize the tool output for the user now in clean spoken prose. "
                    "Do not emit empty text or whitespace.]"
                )
                for event in orch.llm.stream_turn(
                    current_audio_b64=None,
                    current_text="Summarize the tool output for the user.",
                    history=orch.history,
                    memories=memories,
                    tools=[],
                    tool_messages=scratchpad_buffer.messages,
                    trace_id=trace.trace_id,
                    epistemic_context=epistemic_context,
                    stance_tag=current_stance,
                    enable_thinking=False,
                ):
                    if trace.interrupted or orch._cancel_token.is_set():
                        break
                    if isinstance(event, TokenDelta) and event.delta:
                        if not first_token_seen:
                            first_token_seen = True
                            trace.t_llm_first_token = now_ns()
                        trace.tokens_out += 1
                        full_response_text.append(event.delta)
                        for chunk in chunker.feed(event.delta):
                            if trace.interrupted:
                                break
                            clean_chunk_text = sanitize_for_voice(chunk.text)
                            if not clean_chunk_text:
                                continue
                            if chunk_index == 0:
                                trace.t_first_chunk = now_ns()
                                orch._set_state("speaking")
                            orch._enqueue_tts_chunk(trace, chunk.chunk_id, clean_chunk_text)
                            chunk_index += 1

                for chunk in chunker.flush():
                    if trace.interrupted or orch._cancel_token.is_set():
                        break
                    clean_chunk_text = sanitize_for_voice(chunk.text)
                    if clean_chunk_text:
                        if chunk_index == 0:
                            trace.t_first_chunk = now_ns()
                            orch._set_state("speaking")
                        orch._enqueue_tts_chunk(trace, chunk.chunk_id, clean_chunk_text)
                        chunk_index += 1

                if not "".join(full_response_text).strip():
                    tool_name_used = (
                        str(tool_receipts[0].get("action", "the tool"))
                        if tool_receipts
                        else "the tool"
                    )
                    fallback_msg = (
                        orch._last_unspoken_tool_msg
                        if isinstance(orch._last_unspoken_tool_msg, str)
                        and orch._last_unspoken_tool_msg.strip()
                        else f"I completed the operation using {tool_name_used}."
                    )
                    full_response_text.append(fallback_msg)
                    orch._speak_text(trace, fallback_msg)
                    orch._publish_caption(fallback_msg, source="assistant", is_final=True)

                if chunk_index > 0 and not trace.interrupted and not orch._cancel_token.is_set():
                    orch.speech_output.wait_for_playback(trace)

                if not trace.interrupted and not orch._cancel_token.is_set():
                    orch.play_ring.set_flag(FLAG_EOS)

            elif (
                not full_response_text
                and orch._last_unspoken_tool_msg
                and not trace.interrupted
                and not orch._cancel_token.is_set()
            ):
                orch._speak_text(trace, orch._last_unspoken_tool_msg)
                orch.current_turn_tool_spoken.append(orch._last_unspoken_tool_msg)
                orch._publish_caption(
                    orch._last_unspoken_tool_msg, source="assistant", is_final=True
                )
                orch.play_ring.set_flag(FLAG_EOS)

            # WO-21 Phase 3: Proactive Web-Fact Ratification Flow
            ratification_offer = (
                orch._check_and_offer_ratification(trace)
                if (not trace.interrupted and not orch._cancel_token.is_set())
                else None
            )

            # Record turn in history
            if not trace.interrupted and not orch._cancel_token.is_set():
                reply_parts: list[str] = []
                if full_response_text:
                    reply_parts.append("".join(full_response_text))
                if orch.current_turn_tool_spoken:
                    reply_parts.extend(orch.current_turn_tool_spoken)
                if ratification_offer:
                    reply_parts.append(ratification_offer)
                if reply_parts:
                    reply_str = " ".join(reply_parts)
                    orch.history.append({"role": "user", "content": user_msg})
                    orch.history.append({"role": "assistant", "content": reply_str})
                    orch.current_turn_assistant_reply = reply_str
                    if full_response_text or ratification_offer:
                        orch._publish_caption(reply_str, source="assistant", is_final=True)

        except Exception as exc:  # noqa: BLE001
            trace.error = str(exc)
            if not trace.interrupted:
                logger.error("turn_execution_error", trace_id=trace.trace_id, error=str(exc))
                print(f"\n[Error] {exc}", flush=True)
                orch._publish_caption(
                    "Sorry, I had trouble processing that request.",
                    source="status",
                    is_final=True,
                )
            trace.interrupted = True
        finally:
            orch._finalize_turn(trace, decision_id)
