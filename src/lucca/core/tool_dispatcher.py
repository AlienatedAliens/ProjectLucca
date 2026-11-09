"""
Project Lucca — Tool Dispatcher & Receipt Deduplication (WO-43 Phase 2, Sub-Step 2.4)
Spec 01 §6, Spec 05, Spec 10

Encapsulates tool dispatch, semantic argument repair, speculative BDI validation,
MicroScheme skill execution, grounded memory_commit, self_history_search,
screenshot_capture, and table-driven sandbox tool execution + spoken feedback.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

import structlog
import ulid
from pydantic import JsonValue, ValidationError

from lucca.core.affect import AffectSignal
from lucca.core.capabilities import dispatch_invoke_skill
from lucca.core.config import load_heuristics
from lucca.core.schemas import (
    AssertFact,
    ChatMessage,
    Say,
    ToolCall,
    ToolResult,
    canonicalize_predicate,
    is_valid_predicate,
)
from lucca.core.trace import TurnTrace
from lucca.memory.extraction import FactExtractor
from lucca.reasoning.scheme.eval import evaluate_plan, evaluate_rule
from lucca.sandbox.schemas import TOOL_ARG_SCHEMAS, InvokeSkillArgs, MemoryCommitArgs

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculates Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            dels = curr[j] + 1
            subs = prev[j] + (0 if c1 == c2 else 1)
            curr.append(min(ins, dels, subs))
        prev = curr
    return prev[-1]


class ToolDispatcher:
    """Dispatches tool calls, skill invocations, and grounded memory commits for Orchestrator."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orch = orchestrator

    def _sign_and_record_tool_receipt(
        self,
        *,
        name: str,
        call_id: str,
        args: dict[str, JsonValue],
        ok: bool,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        """Unified helper to sign and record a tool execution receipt via Orchestrator."""
        self._orch._record_tool_receipt(
            name=name,
            call_id=call_id,
            args=args,
            ok=ok,
            output=output,
            error=error,
        )

    def _execute_and_record_sandbox_tool(
        self,
        call_id: str,
        tool_name: str,
        args: dict[str, JsonValue],
    ) -> ToolResult:
        """Table-driven execution + receipt recording for standard confirmed sandbox tools."""
        orch = self._orch
        res = orch.sandbox.execute_tool(
            call_id=call_id, tool_name=tool_name, args=args, confirmed=True
        )
        self._sign_and_record_tool_receipt(
            name=tool_name,
            call_id=call_id,
            args=args,
            ok=res.ok,
            output=res.content,
            error=res.stderr,
        )
        return res

    def _emit_spoken_tool_feedback(
        self,
        trace: TurnTrace,
        res: ToolResult,
        spoken_ok: str,
        speak: bool,
    ) -> ToolResult:
        """Table-driven spoken feedback emitter for dedicated tool handlers."""
        if not speak:
            return res
        orch = self._orch
        spoken_msg = spoken_ok if res.ok else f"Error: {res.stderr or 'action failed'}."
        print(f"[Lucca] {spoken_msg}", flush=True)
        orch._speak_text(trace, spoken_msg)
        orch.current_turn_tool_spoken.append(spoken_msg)
        return res

    def describe_tool_action(self, name: str, args: dict[str, JsonValue]) -> str:
        if name == "launch_app":
            app = str(args.get("app_name", "the application"))
            return f"launch {app}"
        if name == "write_file":
            path = str(args.get("path", "the file"))
            return f"write to {path}"
        if name == "delete_file":
            path = str(args.get("path", "the file"))
            return f"delete {path}"
        if name == "run_python":
            return "run the python script"
        if name == "fetch_url":
            url = str(args.get("url", "the web page"))
            return f"fetch {url}"
        if name == "memory_commit":
            o = str(args.get("o", "")).strip()
            p = str(args.get("p", "")).strip()
            if o and p:
                natural = {
                    "is_named": f"your name is {o}",
                    "lives_in": f"you live in {o}",
                    "works_at": f"you work at {o}",
                    "works_as": f"you work as {o}",
                    "born_on": f"you were born on {o}",
                    "birthday_is": f"your birthday is {o}",
                    "timezone_is": f"your timezone is {o}",
                }.get(p, f"{str(args.get('s', 'you')).strip()} {p.replace('_', ' ')} {o}")
                return f"save that {natural}"
        if name == "clipboard_read":
            return "read your clipboard"
        if name == "inbox_handoff":
            fname = str(args.get("filename", "the file"))
            return f"move {fname} into my workspace from your inbox"
        if name == "schedule_event":
            ev = str(args.get("event_name", "the event"))
            return f"schedule reminder for {ev}"
        if name == "artifact_verify":
            path = str(args.get("path", "the file"))
            return f"verify {path}"
        if name == "screenshot_capture":
            return "take a screenshot"
        return f"execute {name}"

    def handle_schedule_event(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self._execute_and_record_sandbox_tool(call_id, "schedule_event", args)

    def handle_artifact_verify(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self._execute_and_record_sandbox_tool(call_id, "artifact_verify", args)

    def handle_clipboard_read(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self._execute_and_record_sandbox_tool(call_id, "clipboard_read", args)

    def handle_inbox_handoff(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        return self._execute_and_record_sandbox_tool(call_id, "inbox_handoff", args)

    def handle_screenshot_capture(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        """WO-24 Phase 1: capture primary display and stage for multimodal injection."""
        orch = self._orch
        already_staged = getattr(orch, "_pending_image_b64", None) or getattr(
            orch, "current_turn_image_b64", None
        )
        if already_staged:
            b64 = already_staged
            width, height = 1280, 800
            ocr_text = None
        else:
            try:
                from lucca.sandbox.screenshot_tool import (  # noqa: PLC0415
                    capture_screenshot_with_ocr_fallback,
                )

                llm_cfg = getattr(getattr(orch, "config", None), "llm", None)
                mmproj_obj = getattr(llm_cfg, "mmproj", None) if llm_cfg else None
                b64, width, height, ocr_text = capture_screenshot_with_ocr_fallback(
                    mmproj=mmproj_obj
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("screenshot_capture_failed", error=str(exc))
                self._sign_and_record_tool_receipt(
                    name="screenshot_capture",
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=str(exc),
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    content=None,
                    stderr=f"screenshot_capture failed: {exc}",
                    elapsed_ms=0.0,
                )

        size_kb = round(len(b64) * 3 / 4 / 1024, 1)
        orch._pending_image_b64 = b64
        if hasattr(orch, "visual_session") and orch.visual_session is not None:
            orch.visual_session.store_image(b64_jpeg=b64, description="screenshot")

        has_real_ocr = bool(ocr_text and "no text detected" not in ocr_text.lower())
        receipt_output = f"[screenshot captured: {width}x{height}, {size_kb}KB]"
        if has_real_ocr and ocr_text:
            receipt_output = f"{receipt_output} {ocr_text}"

        self._sign_and_record_tool_receipt(
            name="screenshot_capture",
            call_id=call_id,
            args=args,
            ok=True,
            output=receipt_output,
            error=None,
        )
        content_msg = (
            f"[screenshot captured: {ocr_text}]"
            if (has_real_ocr and ocr_text)
            else "[screenshot captured]"
        )
        struct_data: dict[str, JsonValue] = {"width": width, "height": height, "size_kb": size_kb}
        if ocr_text:
            struct_data["ocr_text"] = ocr_text

        return ToolResult(
            call_id=call_id,
            ok=True,
            content=content_msg,
            structured=struct_data,
            elapsed_ms=0.0,
        )

    def handle_self_history_search(self, call_id: str, args: dict[str, JsonValue]) -> ToolResult:
        """WO-9 A14 (F18): expose the SELF_HISTORY substrate as a READ tool."""
        orch = self._orch
        schema_cls = TOOL_ARG_SCHEMAS.get("self_history_search")
        if schema_cls is not None:
            try:
                parsed_sh = schema_cls.model_validate(args)
                query = str(getattr(parsed_sh, "query", "")).strip()
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
        else:
            query = str(args.get("query", "")).strip()
            if not query:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr="invalid_arguments: query is required",
                    elapsed_ms=0.0,
                )
        cascade = getattr(orch, "cascade", None)
        if cascade is None:
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr="self-history substrate unavailable",
                elapsed_ms=0.0,
            )
        try:
            items = cascade.query_substrate_self_history(query)
        except Exception as exc:  # noqa: BLE001
            logger.debug("self_history_search_failed", error=str(exc))
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=f"self_history_search failed: {exc}",
                elapsed_ms=0.0,
            )
        lines = [f"- [{item.source}] {item.content}" for item in items[:10]]
        content = "\n".join(lines) if lines else "No self-history records match that query."
        self._sign_and_record_tool_receipt(
            name="self_history_search",
            call_id=call_id,
            args=args,
            ok=True,
            output=content,
            error=None,
        )
        return ToolResult(
            call_id=call_id,
            ok=True,
            exit_code=0,
            content=content,
            structured={"count": len(items)},
            elapsed_ms=0.0,
        )

    def handle_memory_commit(
        self,
        trace: TurnTrace,
        call_id: str,
        name: str,
        args: dict[str, JsonValue],
        speak: bool,
    ) -> ToolResult:
        """WO-9 A2 (ADR-010): grounded memory_commit."""
        orch = self._orch
        if not orch.memory_store:
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr="memory subsystem unavailable",
                elapsed_ms=0.0,
            )
        try:
            schema_cls = TOOL_ARG_SCHEMAS.get("memory_commit", MemoryCommitArgs)
            parsed = schema_cls.model_validate(args)
            if not isinstance(parsed, MemoryCommitArgs):
                parsed = MemoryCommitArgs.model_validate(args)
        except ValidationError as exc:
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    f"invalid_arguments: {exc}. Provide s, "
                    "p (lowercase snake_case slug, 2-41 chars), o, "
                    "and a verbatim quote from the user's words this turn."
                ),
                elapsed_ms=0.0,
            )

        canon_p = canonicalize_predicate(parsed.p)
        if not is_valid_predicate(canon_p):
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    f"invalid_predicate: '{parsed.p}' is not a valid "
                    "lowercase snake_case slug (2-41 chars)"
                ),
                elapsed_ms=0.0,
            )

        transcript_payload = getattr(orch, "_last_transcript_signed", None)
        payload_is_current = (
            transcript_payload is not None
            and getattr(transcript_payload, "trace_id", None) == trace.trace_id
        )
        if not payload_is_current and orch.current_turn_transcript:
            entry_id = orch._commit_transcript(orch.current_turn_transcript, trace)
            if entry_id:
                orch._early_transcript_commit = (entry_id, orch.current_turn_transcript)
                orch.current_turn_transcript = None
            transcript_payload = getattr(orch, "_last_transcript_signed", None)
            payload_is_current = (
                transcript_payload is not None
                and getattr(transcript_payload, "trace_id", None) == trace.trace_id
            )
        if not payload_is_current or transcript_payload is None:
            self._sign_and_record_tool_receipt(
                name=name,
                call_id=call_id,
                args=args,
                ok=False,
                output=None,
                error="no user utterance to ground against",
            )
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    "not_grounded: there is no user utterance this turn to ground the fact "
                    "against. Ask the user to state the fact in their own words first."
                ),
                elapsed_ms=0.0,
            )

        extractor = getattr(orch, "_fact_extractor", None)
        if extractor is None:
            extractor = FactExtractor(master_key=orch.signer_factory.master_key)
            orch._fact_extractor = extractor

        try:
            signed_facts = extractor.extract_and_sign(
                transcript_payload,
                [{"s": parsed.s, "p": parsed.p, "o": parsed.o, "quote": parsed.quote}],
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("extract_and_sign_failed", error=str(exc))
            self._sign_and_record_tool_receipt(
                name=name, call_id=call_id, args=args, ok=False, output=None, error=str(exc)
            )
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=f"memory_commit failed: {exc}",
                elapsed_ms=0.0,
            )

        if not signed_facts:
            self._sign_and_record_tool_receipt(
                name=name,
                call_id=call_id,
                args=args,
                ok=False,
                output=None,
                error="quote not grounded in user utterance",
            )
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    "not_grounded: the fact was NOT saved because the quote does not appear "
                    "verbatim in the user's words this turn. Say plainly that you did not save "
                    "it, or ask the user to say the fact in their own words."
                ),
                structured={"error": "not_grounded", "memory_eligible": False},
                elapsed_ms=0.0,
            )

        now = orch.clock.now_utc()
        saved_contents: list[str] = []
        for signed_fact in signed_facts:
            orch.memory_store.commit(signed_fact, now=now)
            saved_contents.append(str(signed_fact.content))

        saved_str = "; ".join(saved_contents)
        self._sign_and_record_tool_receipt(
            name=name, call_id=call_id, args=args, ok=True, output=saved_str, error=None
        )
        logger.info("grounded_memory_commit", facts=saved_str, trace_id=trace.trace_id)
        if speak:
            spoken = "Saved that to memory."
            orch._speak_text(trace, spoken)
            orch.current_turn_tool_spoken.append(spoken)
        saved_json: list[JsonValue] = list(saved_contents)
        return ToolResult(
            call_id=call_id,
            ok=True,
            exit_code=0,
            content=f"Saved to long-term memory: {saved_str}",
            structured={"saved": saved_json, "provenance": "USER_DERIVED"},
            elapsed_ms=0.0,
        )

    def handle_tool_call(
        self,
        trace: TurnTrace,
        name: str,
        args: dict[str, JsonValue],
        speak: bool = True,
    ) -> ToolResult | None:
        orch = self._orch
        # Semantic repair: if model invoked calc_math with Python code or equation solving, route to
        # run_python
        if name == "calc_math":
            expr_val = args.get("expr")
            code_val = args.get("code")
            raw_content = str(code_val if code_val is not None else (expr_val or ""))
            solve_match = re.search(
                r"^(.*?)=(.*?)(?:[;,]\s*|\s+)solve\s+for\s+([a-zA-Z_]\w*)$",
                raw_content.strip(),
                re.IGNORECASE,
            )
            if solve_match:
                lhs = solve_match.group(1).strip().rstrip(";,")
                rhs = solve_match.group(2).strip().rstrip(";,")
                var = solve_match.group(3).strip()
                sympy_code = (
                    f"import sympy as sp\n"
                    f"{var} = sp.Symbol('{var}')\n"
                    f"eq = sp.Eq({lhs}, {rhs})\n"
                    f"sol = sp.solve(eq, {var})\n"
                    f"print(f'{var} = {{sol}}')\n"
                )
                logger.info(
                    "tool_semantic_reroute",
                    from_tool="calc_math",
                    to_tool="run_python",
                    fix="equation_to_sympy",
                )
                name = "run_python"
                args = {"code": sympy_code}
            else:
                is_python_code = (
                    "code" in args
                    or "\n" in raw_content
                    or ";" in raw_content
                    or "import " in raw_content
                    or "def " in raw_content
                    or "print(" in raw_content
                    or len(raw_content) > 300
                )
                if is_python_code:
                    logger.info("tool_semantic_reroute", from_tool="calc_math",
                        to_tool="run_python")
                    name = "run_python"
                    args = {"code": raw_content}
        elif name == "run_python":
            if "expr" in args and "code" not in args:
                logger.info("tool_semantic_reroute", from_tool="run_python", fix="expr_to_code")
                args = {"code": str(args["expr"])}
        elif name in ("memory_search", "self_history_search", "search_web"):
            if not str(args.get("query", "")).strip():
                fallback_q = str(orch.current_turn_transcript or "memory query").strip()
                args = dict(args)
                args["query"] = fallback_q

        orch.executed_tools.append((name, args))
        call_id = str(ulid.ULID())
        orch.current_turn_tool_calls.append(ToolCall(tool=name, args=dict(args), call_id=call_id))
        if not orch.execute_tools:
            return None

        # Speculative BDI Invariant Validation (Milestone 4)
        bdi_validator = getattr(orch, "bdi_validator", None)
        if bdi_validator is not None:
            bdi_res = bdi_validator.validate_tool_call(
                name,
                args,
                taint_flags=getattr(orch.sandbox, "taint_flags", 0),
            )
            if not bdi_res.is_valid:
                logger.warning(
                    "bdi_invariant_violation",
                    tool=name,
                    reason=bdi_res.reason,
                    elapsed_us=bdi_res.elapsed_us,
                )
                orch.current_turn_tool_ok = False
                affect_tracker = getattr(orch, "affect_tracker", None)
                if affect_tracker is not None:
                    affect_tracker.record_signal(
                        AffectSignal.DEONTIC_REJECTION, custom_cause=bdi_res.reason
                    )
                err_msg = f"Speculative Invariant Violation: {bdi_res.reason}. Action prohibited."
                self._sign_and_record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=err_msg,
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-4,
                    stderr=err_msg,
                    elapsed_ms=bdi_res.elapsed_us / 1000.0,
                )

        # invoke_skill dispatch tool (T1.2)
        if name == "invoke_skill":
            schema_cls = TOOL_ARG_SCHEMAS.get("invoke_skill", InvokeSkillArgs)
            try:
                parsed_is = schema_cls.model_validate(args)
                skill_id = str(getattr(parsed_is, "skill_id", ""))
                raw_skill_args = getattr(parsed_is, "args", {})
                skill_args: dict[str, JsonValue] = (
                    dict(raw_skill_args) if isinstance(raw_skill_args, dict) else {}
                )
            except ValidationError as exc:
                orch.current_turn_tool_ok = False
                self._sign_and_record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=f"invalid_arguments: {exc}",
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )

            manifest_ids = getattr(orch, "current_manifest_skill_ids", None)
            ok, reason, payload = dispatch_invoke_skill(
                skill_id=skill_id,
                args=skill_args,
                rule_engine=orch.rule_engine,
                manifest_skill_ids=manifest_ids,
            )
            if not ok:
                orch.current_turn_tool_ok = False
                self._sign_and_record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=reason,
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=reason,
                    structured=payload,
                    elapsed_ms=0.0,
                )

            rule_entry = orch.rule_engine.rules[skill_id]
            rule_state = orch._build_rule_state(
                str(skill_args.get("query") or orch.current_turn_transcript or "")
            )
            for k, v in skill_args.items():
                if k != "query" and isinstance(v, str):
                    rule_state.entities.setdefault(k, []).append(v)
            outcome = evaluate_plan(rule_entry.definition, rule_state)
            if outcome.plan:
                sub_results: list[str] = []
                for sub_action in outcome.plan.actions:
                    if isinstance(sub_action, ToolCall):
                        sub_res = orch._handle_tool_call(
                            trace, sub_action.tool, dict(sub_action.args), speak=False
                        )
                        sub_status = (
                            "ok" if (sub_res is None or getattr(sub_res, "ok", True)) else "failed"
                        )
                        sub_results.append(f"{sub_action.tool}->{sub_status}")
                    elif isinstance(sub_action, Say) and speak:
                        orch._speak_text(trace, sub_action.text)
                    elif isinstance(sub_action, AssertFact):
                        orch._commit_lisp_assertion(sub_action, trace)
                        sub_results.append(
                            f"assert({sub_action.s} {sub_action.p} {sub_action.o})->ok"
                        )
                has_failures = any("->failed" in s for s in sub_results)
                skill_signal: Literal["tool_exit_zero", "pydantic_valid"] = (
                    "pydantic_valid" if has_failures else "tool_exit_zero"
                )
                orch.rule_engine.emit_execution_triple(
                    rule_id=skill_id,
                    plan=outcome.plan,
                    signal=skill_signal,
                    detail=f"invoke_skill {', '.join(sub_results)}",
                )
                res_content = (
                    f"Skill '{skill_id}' fired. "
                    f"Rationale: {outcome.plan.rationale or 'completed'}. "
                    f"Actions: {', '.join(sub_results) or 'none'}"
                )
                self._sign_and_record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=True,
                    output=res_content,
                    error=None,
                )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    content=res_content,
                    elapsed_ms=float(outcome.elapsed_us) / 1000.0,
                )
            else:
                err_msg = outcome.error or "conditions not met"
                orch.current_turn_tool_ok = False
                self._sign_and_record_tool_receipt(
                    name=name,
                    call_id=call_id,
                    args=args,
                    ok=False,
                    output=None,
                    error=f"Skill '{skill_id}' evaluated but did not fire: {err_msg}",
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    stderr=f"Skill '{skill_id}' evaluated but did not fire: {err_msg}",
                    elapsed_ms=float(outcome.elapsed_us) / 1000.0,
                )

        # Check if this is a MicroScheme skill invocation (Proposal A / D-REAS-04)
        target_rule_id = None
        if name.startswith("skill_"):
            target_rule_id = name[6:].replace("_", "-")
        elif name in orch.rule_engine.rules:
            target_rule_id = name

        if target_rule_id and target_rule_id in orch.rule_engine.rules:
            rule_entry = orch.rule_engine.rules[target_rule_id]
            rule_state = orch._build_rule_state(
                str(args.get("query") or orch.current_turn_transcript or "")
            )
            outcome = evaluate_rule(rule_entry.definition, rule_state)
            if outcome.plan:
                sub_results = []
                for sub_action in outcome.plan.actions:
                    if isinstance(sub_action, ToolCall):
                        sub_res = orch._handle_tool_call(
                            trace, sub_action.tool, dict(sub_action.args), speak=False
                        )
                        sub_status = (
                            "ok" if (sub_res is None or getattr(sub_res, "ok", True)) else "failed"
                        )
                        sub_results.append(f"{sub_action.tool}->{sub_status}")
                    elif isinstance(sub_action, Say) and speak:
                        orch._speak_text(trace, sub_action.text)
                    elif isinstance(sub_action, AssertFact):
                        orch._commit_lisp_assertion(sub_action, trace)
                        sub_results.append(
                            f"assert({sub_action.s} {sub_action.p} {sub_action.o})->ok"
                        )
                res = ToolResult(
                    call_id=call_id,
                    ok=True,
                    content=(
                        f"Skill '{target_rule_id}' fired. "
                        f"Rationale: {outcome.plan.rationale or 'completed'}. "
                        f"Actions: {', '.join(sub_results) or 'none'}"
                    ),
                    elapsed_ms=float(outcome.elapsed_us) / 1000.0,
                )
            else:
                err_msg = outcome.error or "conditions not met"
                res = ToolResult(
                    call_id=call_id,
                    ok=False,
                    stderr=f"Skill '{target_rule_id}' evaluated but did not fire: {err_msg}",
                    elapsed_ms=float(outcome.elapsed_us) / 1000.0,
                )
            if not res.ok:
                orch.current_turn_tool_ok = False
            self._sign_and_record_tool_receipt(
                name=name,
                call_id=call_id,
                args=args,
                ok=res.ok,
                output=res.content,
                error=res.stderr,
            )
            return res

        # Check confirmation requirement (WRITE / LAUNCH)
        human_confirmed = False
        if orch.sandbox.check_confirmation_needed(name):
            already_staged = getattr(orch, "_pending_image_b64", None) or getattr(
                orch, "current_turn_image_b64", None
            )
            if name == "screenshot_capture" and already_staged:
                logger.info("screenshot_confirmation_bypassed_user_pre_attached")
                human_confirmed = True
            else:
                confirmed = orch._request_confirmation(trace, name, args)
                if not confirmed:
                    logger.info("tool_execution_cancelled_by_user", tool=name)
                    cancel_msg = "Cancelled."
                    print(f"[Lucca] {cancel_msg}", flush=True)
                    if speak:
                        orch._speak_text(trace, cancel_msg)
                        orch.current_turn_tool_spoken.append(cancel_msg)
                    orch.current_turn_tool_ok = False
                    self._sign_and_record_tool_receipt(
                        name=name,
                        call_id=call_id,
                        args=args,
                        ok=False,
                        output=None,
                        error="cancelled by user",
                    )
                    return ToolResult(
                        call_id=call_id,
                        ok=False,
                        exit_code=-3,
                        stderr="cancelled by user",
                        elapsed_ms=0.0,
                    )
                human_confirmed = True

        if name == "memory_commit":
            return orch._handle_memory_commit(trace, call_id, name, args, speak)

        if name == "self_history_search":
            return orch._handle_self_history_search(call_id, args)

        if name == "schedule_event":
            res = orch._handle_schedule_event(call_id, args)
            ev = str(args.get("event_name", "the event"))
            return self._emit_spoken_tool_feedback(
                trace, res, f"I've noted that reminder for {ev}.", speak
            )

        if name == "artifact_verify":
            res = orch._handle_artifact_verify(call_id, args)
            path = str(args.get("path", "file"))
            sha = str((res.structured or {}).get("sha256", ""))[:8]
            return self._emit_spoken_tool_feedback(
                trace, res, f"Verified {path}: checksum is {sha}.", speak
            )

        if name == "clipboard_read":
            res = orch._handle_clipboard_read(call_id, args)
            return self._emit_spoken_tool_feedback(trace, res, "I read your clipboard.", speak)

        if name == "inbox_handoff":
            res = orch._handle_inbox_handoff(call_id, args)
            fname = str(args.get("filename", "file"))
            return self._emit_spoken_tool_feedback(
                trace, res, f"Imported {fname} from inbox into workspace.", speak
            )

        if name == "screenshot_capture":
            res = orch._handle_screenshot_capture(call_id, args)
            if speak and res.ok:
                spoken_msg = "I took a screenshot."
                print(f"[Lucca] {spoken_msg}", flush=True)
                orch._speak_text(trace, spoken_msg)
                orch.current_turn_tool_spoken.append(spoken_msg)
                pending_img = getattr(orch, "_pending_image_b64", None)
                if pending_img is not None:
                    img_msg = ChatMessage(
                        role="user",
                        content="[Screenshot attached — describe what you see in spoken prose, no "
                            "markdown.]",
                        image_b64=pending_img,
                    )
                    current_tool_messages = getattr(orch, "_current_tool_messages", None)
                    if current_tool_messages is not None:
                        current_tool_messages.append(img_msg)
                    else:
                        if not hasattr(orch, "_screenshot_pending_msgs"):
                            orch._screenshot_pending_msgs = []
                        orch._screenshot_pending_msgs.append(img_msg)
            elif speak and not res.ok:
                spoken_msg = f"Error: {res.stderr or 'action failed'}."
                print(f"[Lucca] {spoken_msg}", flush=True)
                orch._speak_text(trace, spoken_msg)
                orch.current_turn_tool_spoken.append(spoken_msg)
            return res

        # Corrective Search Query Injection & Category Grounding
        if name == "search_web" and "query" in args and isinstance(args["query"], str):
            q = str(args["query"])
            detected = getattr(orch, "active_detected_words", [])
            for target_w in detected:
                for tok in re.findall(r"\b[a-zA-Z]{3,}\b", q):
                    if (
                        tok.lower() != target_w.lower()
                        and _levenshtein_distance(tok.lower(), target_w.lower()) <= 2
                    ):
                        q = re.sub(rf"\b{re.escape(tok)}\b", target_w, q)
                if target_w.lower() not in q.lower():
                    q = f'"{target_w}" {q}'.strip()

            recent_ctx = " ".join(
                m.get("content", "") for m in orch.history[-2:] if isinstance(m, dict)
            )
            context_text = f"{orch.current_turn_transcript or ''} {recent_ctx}".lower()
            category_keywords = load_heuristics("search_category_keywords")
            for kw in category_keywords:
                if kw in context_text and kw not in q.lower():
                    q = f"{q} {kw}".strip()
            args["query"] = q

        res = orch.sandbox.execute_tool(
            call_id=call_id,
            tool_name=name,
            args=args,
            confirmed=True,
            human_confirmed=human_confirmed,
        )
        if (
            res.ok
            and name in ("search_web", "research", "research_topic")
            and isinstance(res.structured, dict)
        ):
            cand_res = res.structured.get("results") or res.structured.get("sources")
            if isinstance(cand_res, list):
                from lucca.core.proof_policy import evaluate_web_evidence_burden  # noqa: PLC0415

                res_dicts = [r for r in cand_res if isinstance(r, dict)]
                q_str = str(orch.current_turn_transcript or args.get("query", "")).strip()
                burden = evaluate_web_evidence_burden(
                    query_text=q_str,
                    search_results=res_dicts,
                    fallback_content=str(res.content or "")[:1500],
                    store=getattr(orch, "memory_store", None),
                    verifier=getattr(orch, "verifier", None),
                    deep_escalated=(
                        name in ("research", "research_topic") or bool(args.get("deep_extract"))
                    ),
                )
                res.structured["epistemic_burden"] = burden.to_metadata_dict()
                if res.content:
                    res.content = (
                        f"{res.content}\n\n"
                        f"[Evidentiary Burden & Walton Corroboration: {burden.summary_tag}]\n"
                        f"[{burden.guidance}]"
                    )
        affect_tracker = getattr(orch, "affect_tracker", None)
        if not res.ok:
            orch.current_turn_tool_ok = False
            if affect_tracker is not None:
                affect_tracker.record_signal(
                    AffectSignal.TOOL_FAILURE, custom_cause=res.stderr or f"{name} failed"
                )
        elif affect_tracker is not None:
            affect_tracker.record_signal(
                AffectSignal.TASK_SUCCESS, custom_cause=f"{name} completed successfully"
            )
        err_val = res.stderr if res.stderr else (res.content if not res.ok else None)
        self._sign_and_record_tool_receipt(
            name=name,
            call_id=call_id,
            args=args,
            ok=res.ok,
            output=res.content,
            error=err_val,
        )
        logger.info("tool_executed", tool=name, ok=res.ok, exit_code=res.exit_code)
        spoken_msg_final: str | None = None
        if res.ok:
            if name == "launch_app":
                app_name = str(args.get("app_name", "app"))
                spoken_msg_final = f"Launched {app_name}."
            elif name == "write_file":
                path = str(args.get("path", "file"))
                spoken_msg_final = f"Saved {path}."
            elif name == "delete_file":
                path = str(args.get("path", "file"))
                spoken_msg_final = f"Deleted {path}."
            elif name == "run_python":
                spoken_msg_final = "Python script executed."
            elif name == "query_capabilities":
                cat = str(args.get("category", "all")).lower()
                if cat in ("applications", "apps", "whitelisted_apps"):
                    spoken_msg_final = (
                        "I can launch desktop applications including Calculator, Notepad, and Edge."
                    )
                elif cat in ("hardware", "hardware_substrates"):
                    spoken_msg_final = (
                        "I run locally across a CUDA dGPU, Intel AI Boost NPU, "
                        "and multi-core host CPU."
                    )
                elif cat in ("memory", "memory_subsystem"):
                    spoken_msg_final = (
                        "I have persistent episodic and semantic memory backed by "
                        "SQLite and vector embeddings."
                    )
                else:
                    spoken_msg_final = (
                        "I can launch desktop applications like Calculator, Notepad, and Edge, "
                        "read and write files in your workspace, and remember our conversations "
                        "with persistent memory."
                    )
            elif name == "read_file":
                path = str(args.get("path", "file"))
                content = str(res.content or "").strip()
                if 0 < len(content) <= 150:
                    spoken_msg_final = f"Here is what's in {path}: {content}"
                else:
                    spoken_msg_final = f"I read {path}."
            elif name == "fetch_url":
                url = str(args.get("url", "the page"))
                spoken_msg_final = f"I fetched {url}."
            elif name == "inbox_handoff":
                spoken_msg_final = str(res.content or "Imported from inbox.")
            elif name == "list_dir":
                spoken_msg_final = str(res.content or "Checked directory.")
            else:
                spoken_msg_final = f"Executed {name}."
        elif res.exit_code == -2 or "sandbox unavailable" in (res.stderr or ""):
            spoken_msg_final = "My file sandbox isn't available — Docker isn't reachable."
        else:
            spoken_msg_final = f"Error: {res.stderr or 'action failed'}."

        if speak and spoken_msg_final:
            print(f"[Lucca] {spoken_msg_final}", flush=True)
            orch._speak_text(trace, spoken_msg_final)
            orch.current_turn_tool_spoken.append(spoken_msg_final)
        elif spoken_msg_final:
            orch._last_unspoken_tool_msg = spoken_msg_final
        return res
