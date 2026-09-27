"""
Project Lucca — Unified Sandbox Service
Spec 09, Spec 12, ADR-003, ADR-004
Orchestrates file-sandbox RPC, web-sandbox fetches, host launcher, and policy guards.
"""

import ast
import json
import math
import platform
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

import psutil
import structlog
from pydantic import BaseModel, JsonValue, ValidationError

from lucca.core.capabilities import get_capability_registry
from lucca.core.config import get_config
from lucca.core.schemas import Risk, ToolResult
from lucca.memory.manager import MemoryManager
from lucca.sandbox.file_tool import SafeFileTool
from lucca.sandbox.launcher import AppLauncher
from lucca.sandbox.note_tool import SafeNoteTool
from lucca.sandbox.policy import SequenceGuard, classify_risk, requires_confirmation
from lucca.sandbox.rpc import DockerRPCTransport
from lucca.sandbox.schemas import (
    EXTRA_TOOL_SCHEMAS,
    TOOL_ARG_SCHEMAS,
    ArtifactVerifyArgs,
    CalcMathArgs,
    ClipboardReadArgs,
    FetchUrlArgs,
    InboxHandoffArgs,
    LaunchAppArgs,
    MemoryCommitArgs,
    MemorySearchArgs,
    NoteReadArgs,
    NoteWriteArgs,
    ScheduleEventArgs,
    SearchWebArgs,
    SysInfoArgs,
)
from lucca.sandbox.artifact_tool import verify_artifact
from lucca.sandbox.clipboard_tool import read_clipboard_text
from lucca.sandbox.schedule_tool import schedule_event
from lucca.sandbox.search_tool import search_web
from lucca.sandbox.system_tools import get_system_metrics, list_running_processes
from lucca.sandbox.tasks import AsyncTaskInfo, AsyncTaskManager, TaskStatus
from lucca.sandbox.web_tool import fetch_url
from lucca.sandbox.workspace import WorkspaceManager

logger = structlog.get_logger(__name__)

_SAFE_MATH_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}

_SAFE_MATH_FUNCTIONS: dict[str, Callable[..., int | float]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
}


def _eval_ast_node(node: ast.AST) -> int | float | list[object] | tuple[object, ...]:
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")
    if isinstance(node, ast.UnaryOp):
        operand = _eval_ast_node(node.operand)
        if not isinstance(operand, (int, float)):
            raise ValueError("Unary operand must be numeric")
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise ValueError("Binary operands must be numeric")
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("division by zero")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError("integer division by zero")
            return left // right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError("modulo by zero")
            return left % right
        if isinstance(node.op, ast.Pow):
            if abs(right) > 1000:
                raise ValueError("Exponent too large (maximum allowed is 1000)")
            return left**right
        raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
    if isinstance(node, ast.Name):
        if node.id in _SAFE_MATH_CONSTANTS:
            return _SAFE_MATH_CONSTANTS[node.id]
        raise ValueError(f"Undefined variable or constant: {node.id}")
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "math":
            if node.attr in _SAFE_MATH_CONSTANTS:
                return _SAFE_MATH_CONSTANTS[node.attr]
            raise ValueError(f"Unknown math attribute: {node.attr}")
        raise ValueError("Attribute access only allowed on 'math'")
    if isinstance(node, ast.Call):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "math":
                func_name = node.func.attr
            else:
                raise ValueError("Call attribute access only allowed on 'math'")
        else:
            raise ValueError(f"Unsupported call target: {type(node.func).__name__}")

        if func_name not in _SAFE_MATH_FUNCTIONS:
            raise ValueError(f"Function '{func_name}' is not allowed in calc_math")
        if node.keywords:
            raise ValueError("Keyword arguments are not allowed")

        func = _SAFE_MATH_FUNCTIONS[func_name]
        raw_args = [_eval_ast_node(arg) for arg in node.args]
        call_res = func(*raw_args)
        if not isinstance(call_res, (int, float)):
            raise ValueError("Function did not return a numeric value")
        return call_res
    if isinstance(node, ast.Tuple):
        return tuple(_eval_ast_node(el) for el in node.elts)
    if isinstance(node, ast.List):
        return [_eval_ast_node(el) for el in node.elts]
    raise ValueError(f"Disallowed expression node: {type(node).__name__}")


def evaluate_math_expr(expr: str) -> int | float:
    """Safely evaluates a mathematical expression using an AST allowlist."""
    cleaned = expr.strip()
    if not cleaned or len(cleaned) > 500:
        raise ValueError("Expression must be non-empty and under 500 characters")
    tree = ast.parse(cleaned, mode="eval")
    res = _eval_ast_node(tree.body)
    if not isinstance(res, (int, float)):
        raise ValueError("Expression did not evaluate to a numeric value")
    return res


class SandboxService:
    """
    Unified entry point for all sandboxed capabilities:
    - Enforces turn sequence guards (e.g. read_file -> fetch_url prevention)
    - Enforces risk classification and confirmation prerequisites
    - Routes file tools to file-sandbox (via docker exec RPC or direct fallback)
    - Routes fetch_url to web tool with SSRF guards
    - Routes launch_app to host AppLauncher with whitelist and rate limiting
    """

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        inbox_root: Path | str | None = None,
        use_direct_fallback: bool = False,
        execute_apps: bool = True,
        tasks: AsyncTaskManager | None = None,
        notes_dir: Path | str | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self.workspace_mgr = WorkspaceManager(workspace_root=workspace_root, inbox_root=inbox_root)
        self.file_tool = SafeFileTool(workspace_root=self.workspace_mgr.workspace_root)
        self.rpc = DockerRPCTransport(
            container_name="lucca-file-sandbox",
            use_direct_fallback=use_direct_fallback,
            fallback_file_tool=self.file_tool,
        )
        self.launcher = AppLauncher(
            workspace_root=self.workspace_mgr.workspace_root,
            execute=execute_apps,
        )
        self.guard = SequenceGuard()
        self.tasks = tasks if tasks is not None else AsyncTaskManager()
        self.note_tool = SafeNoteTool(notes_dir=notes_dir)
        self._memory_manager = memory_manager

    def get_memory_manager(self) -> MemoryManager:
        if self._memory_manager is None:
            cfg = get_config()
            mk = None
            if cfg.master_key and len(cfg.master_key.strip()) >= 32:
                mk = cfg.master_key.strip().encode("utf-8")
            elif getattr(cfg.env, "mode", "prod") == "dev":
                mk = b"01234567890123456789012345678901"
            try:
                self._memory_manager = MemoryManager(master_key=mk)
            except Exception as exc:
                logger.debug("init_memory_manager_failed", error=str(exc))
                self._memory_manager = MemoryManager(master_key=None)
        return self._memory_manager

    def launch_async(
        self,
        name: str,
        target_fn: Callable[[threading.Event], tuple[int, str, str]],
        metadata: dict[str, str] | None = None,
    ) -> AsyncTaskInfo:
        """Launches a background asynchronous task."""
        return self.tasks.launch_task(name=name, target_fn=target_fn, metadata=metadata)

    def reset_turn(self) -> None:
        """Resets turn sequence guard at the start of a turn."""
        self.guard.reset()

    def get_tool_risk(self, tool_name: str) -> Risk:
        """Returns risk level of the tool."""
        return classify_risk(tool_name)

    def check_confirmation_needed(self, tool_name: str) -> bool:
        """Checks whether tool requires user confirmation (WRITE / LAUNCH)."""
        return requires_confirmation(tool_name, taint=self.guard.active_taint)

    def execute_tool(
        self,
        call_id: str,
        tool_name: str,
        args: dict[str, JsonValue] | BaseModel,
        confirmed: bool = False,
        human_confirmed: bool = False,
    ) -> ToolResult:
        """
        Validates and executes a tool call under sandbox security policy.
        """
        # 1. Sequence Guard Check
        allowed, reason = self.guard.check_and_record(tool_name, args)
        if not allowed:
            # A human voice/text grant may override the single-turn *sequence* block only.
            # The exfiltration token check (policy.py:232-243) is NEVER overridable.
            if not (human_confirmed and self.guard.is_sequence_block(reason)):
                logger.warning("sequence_guard_blocked", tool=tool_name, reason=reason)
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-2,
                    stderr=reason,
                    elapsed_ms=0.0,
                )
            self.guard.record_tool(tool_name)

        # 2. Confirmation Check
        if self.check_confirmation_needed(tool_name) and not (confirmed or human_confirmed):
            logger.info("confirmation_required", tool=tool_name, call_id=call_id)
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-3,
                stderr="confirmation_required",
                elapsed_ms=0.0,
            )

        # 2.5 Central Tool-Arg Validation Registry (WO-19a / F-FEAT-01)
        schema_cls = TOOL_ARG_SCHEMAS.get(tool_name) or EXTRA_TOOL_SCHEMAS.get(tool_name)
        if schema_cls is None:
            logger.warning("tool_schema_not_registered", tool=tool_name, call_id=call_id)
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-1,
                stderr="schema_not_registered",
                elapsed_ms=0.0,
            )

        try:
            schema_cls.model_validate(args)
        except ValidationError as exc:
            logger.warning("tool_arg_validation_failed", tool=tool_name, error=str(exc))
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-1,
                stderr=f"invalid_arguments: {exc}",
                elapsed_ms=0.0,
            )

        # 3. Host Application Launcher
        if tool_name == "launch_app":
            try:
                parsed_app = LaunchAppArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )

            ok, msg = self.launcher.launch(
                app_name=parsed_app.app_name,
                file_arg=parsed_app.file,
                url_arg=parsed_app.url,
            )
            return ToolResult(
                call_id=call_id,
                ok=ok,
                exit_code=0 if ok else -1,
                structured={"status": msg, "app_name": parsed_app.app_name},
                content=msg,
                elapsed_ms=0.0,
            )

        # 4. Web Fetch Tool
        if tool_name == "fetch_url":
            try:
                parsed_url = FetchUrlArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                allow_render = getattr(self, "allow_render", False)
                structured, content = fetch_url(
                    url=parsed_url.url,
                    render=parsed_url.render,
                    max_chars=parsed_url.max_chars,
                    allow_render=allow_render,
                )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=structured,
                    content=content,
                    content_truncated=bool(structured.get("content_truncated", False)),
                    elapsed_ms=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("fetch_url_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=0.0,
                )

        # 4a. Browse Page Tool (Path 2: Interactive Browser Engine)
        if tool_name in ("browse_page", "render_page"):
            url_val = str(args.get("url", "")).strip()
            if not url_val:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr="invalid_arguments: missing 'url'",
                    elapsed_ms=0.0,
                )
            max_chars = int(args.get("max_chars", 20000))
            try:
                # Lazy import: browser_tool pulls Playwright only when rendering is requested.
                from lucca.sandbox.browser_tool import render_page  # noqa: PLC0415

                structured, content = render_page(url=url_val, max_chars=max_chars)
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=structured,
                    content=content,
                    content_truncated=bool(structured.get("content_truncated", False)),
                    elapsed_ms=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("browse_page_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=0.0,
                )

        # 4b. Web Search Tool
        if tool_name == "search_web":
            try:
                parsed_search = SearchWebArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                structured, content = search_web(
                    query=parsed_search.query,
                    max_results=parsed_search.max_results,
                )
                return ToolResult(
                    call_id=call_id,
                    ok=bool(structured.get("ok", True)),
                    exit_code=0 if structured.get("ok", True) else 1,
                    structured=structured,
                    content=content,
                    elapsed_ms=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("search_web_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=0.0,
                )

        # 4c. Arithmetic Tool
        if tool_name == "calc_math":
            try:
                parsed_math = CalcMathArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                res = evaluate_math_expr(parsed_math.expr)
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured={"expr": parsed_math.expr, "result": res},
                    content=str(res),
                    elapsed_ms=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("calc_math_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=0.0,
                )

        # 5. Query Capabilities Tool
        if tool_name == "query_capabilities":
            category = str(args.get("category", "all"))
            registry = get_capability_registry()
            structured_data = registry.get_capabilities_manifest(
                category=category,
                workspace_root=self.workspace_mgr.workspace_root,
                whitelisted_apps=list(self.launcher.apps.keys()),
            )
            content_str = json.dumps(structured_data, indent=2)

            return ToolResult(
                call_id=call_id,
                ok=True,
                exit_code=0,
                structured=structured_data,
                content=content_str,
                elapsed_ms=0.0,
            )

        # 5b. Memory Search Tool
        if tool_name == "memory_search":
            t0 = time.perf_counter()
            try:
                parsed_mem_search = MemorySearchArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                mgr = self.get_memory_manager()
                all_hits = mgr.list_memories(search=parsed_mem_search.query)
                top_hits = all_hits[: parsed_mem_search.top_k]
                content_lines = [
                    f"- [{h.get('kind', 'fact')}/{h.get('provenance', 'USER_EXPLICIT')}] "
                    f"{h.get('content')}"
                    for h in top_hits
                ]
                content_str = (
                    "\n".join(content_lines) if content_lines else "No relevant memories found."
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured={"hits": top_hits, "count": len(top_hits)},
                    content=content_str,
                    elapsed_ms=elapsed_ms,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("memory_search_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )

        # 5c. Memory Commit Tool — FAIL CLOSED (ADR-006 / AGENTS.md §2.1).
        #
        # The content of an LLM-issued tool call is LLM_NARRATION. There is no signer for
        # that provenance class, and the ProvenanceGate rejects it by design. An earlier
        # implementation wrote the content via MemoryManager.add_memory(), which defaults to
        # UserSpeechSigner(signer_id="ui-admin") and therefore laundered model text into
        # memory as authenticated USER_EXPLICIT — the exact failure the doctrine forbids.
        #
        # Until an ADR defines a legitimate commit path (e.g. rule-engine dispatch with
        # entity-derived content signed USER_DERIVED by ExtractorSigner, or an explicit
        # user-confirmation turn signed on the user's own utterance), this tool refuses.
        # The schema stays registered for taxonomy completeness (spec §2 / handover §0.1:
        # "declaring a schema without a dispatcher must fail closed, never crash").
        if tool_name == "memory_commit":
            try:
                MemoryCommitArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            logger.warning(
                "memory_commit_refused_llm_narration",
                call_id=call_id,
                reason="no signer exists for LLM_NARRATION (ADR-006)",
            )
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=(
                    "provenance_violation: memory_commit cannot store model-authored content. "
                    "Long-term memory accepts only USER_EXPLICIT (user speech), USER_DERIVED "
                    "(extractor), TOOL_VERIFIED (sandbox) or LISP_ASSERTION (rule engine) "
                    "envelopes; LLM narration has no signer. Ask the user to state the fact "
                    "themselves, or use note_write for a scratchpad."
                ),
                structured={
                    "error": "provenance_violation",
                    "provenance": "LLM_NARRATION",
                    "memory_eligible": False,
                },
                elapsed_ms=0.0,
            )

        # 5d. Scratchpad Note Write
        if tool_name == "note_write":
            t0 = time.perf_counter()
            try:
                parsed_note_w = NoteWriteArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                structured, content_msg = self.note_tool.write_note(
                    name=parsed_note_w.name,
                    content=parsed_note_w.content,
                    append=parsed_note_w.append,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=structured,
                    content=content_msg,
                    elapsed_ms=elapsed_ms,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("note_write_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )

        # 5e. Scratchpad Note Read
        if tool_name == "note_read":
            t0 = time.perf_counter()
            try:
                parsed_note_r = NoteReadArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                structured, note_text = self.note_tool.read_note(name=parsed_note_r.name)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return ToolResult(
                    call_id=call_id,
                    ok=bool(structured.get("found", True)),
                    exit_code=0 if structured.get("found", True) else 1,
                    structured=structured,
                    content=note_text,
                    elapsed_ms=elapsed_ms,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("note_read_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )

        # 5f. Self Hardware Metrics
        if tool_name == "self_metrics":
            t0 = time.perf_counter()
            try:
                metrics = get_system_metrics()
                content_str = json.dumps(metrics, indent=2)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=metrics,
                    content=content_str,
                    elapsed_ms=elapsed_ms,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("self_metrics_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )

        # 5g. Host System Info (Untrusted Host Readonly)
        if tool_name == "sys_info":
            t0 = time.perf_counter()
            try:
                parsed_sys = SysInfoArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                boot_time = psutil.boot_time()
                uptime_s = max(0.0, time.time() - boot_time)
                processes = list_running_processes(
                    filter_name=parsed_sys.filter_name,
                    limit=parsed_sys.limit,
                )
                structured = {
                    "platform": platform.platform(),
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "hostname": platform.node(),
                    "uptime_seconds": round(uptime_s, 1),
                    "cpu_count": psutil.cpu_count(logical=True) or 1,
                    "process_count": len(processes),
                    "provenance": "TOOL_CONTENT_UNTRUSTED",
                }
                proc_lines = "\n".join(
                    f"- PID {p.get('pid')}: {p.get('name')} "
                    f"(CPU {p.get('cpu_pct')}%, MEM {p.get('mem_pct')}%)"
                    for p in processes
                )
                content = (
                    f"Host System Info (Untrusted Host Inspection):\n"
                    f"OS: {platform.platform()} ({platform.machine()})\n"
                    f"Hostname: {platform.node()}\n"
                    f"Uptime: {uptime_s / 3600.0:.1f} hours\n"
                    f"Processes ({len(processes)}):\n{proc_lines}"
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=structured,
                    content=content,
                    elapsed_ms=elapsed_ms,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("sys_info_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )

        # 6. Async Task Management Tools
        if tool_name == "get_task_status":
            task_id = str(args.get("task_id", ""))
            task = self.tasks.get_task(task_id)
            if not task:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"Task not found: {task_id}",
                    elapsed_ms=0.0,
                )
            return ToolResult(
                call_id=call_id,
                ok=True,
                exit_code=0,
                structured={
                    "task_id": task.task_id,
                    "name": task.name,
                    "status": task.status,
                    "elapsed_s": round(task.elapsed_s, 2),
                    "exit_code": task.exit_code,
                    "output": task.output,
                    "error": task.error,
                },
                content=(
                    f"Task '{task.name}' [{task.task_id}] status: {task.status} "
                    f"(elapsed: {task.elapsed_s:.1f}s)"
                ),
                elapsed_ms=0.0,
            )

        if tool_name == "cancel_task":
            task_id = str(args.get("task_id", ""))
            success = self.tasks.cancel_task(task_id)
            return ToolResult(
                call_id=call_id,
                ok=success,
                exit_code=0 if success else 1,
                structured={"task_id": task_id, "cancelled": success},
                content=(
                    f"Task {task_id} cancellation: "
                    f"{'success' if success else 'failed or not running'}"
                ),
                elapsed_ms=0.0,
            )

        if tool_name == "list_tasks":
            raw_filter = args.get("status")
            status_filter: TaskStatus | None = None
            if isinstance(raw_filter, str):
                upper_filter = raw_filter.upper()
                if upper_filter in ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"):
                    status_filter = upper_filter  # type: ignore[assignment]
            task_list = self.tasks.list_tasks(status=status_filter)
            tasks_data = [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "status": t.status,
                    "elapsed_s": round(t.elapsed_s, 2),
                }
                for t in task_list
            ]
            return ToolResult(
                call_id=call_id,
                ok=True,
                exit_code=0,
                structured={"tasks": tasks_data, "count": len(tasks_data)},
                content=f"{len(tasks_data)} task(s) found",
                elapsed_ms=0.0,
            )

        # 7. run_python execution under container isolation
        if tool_name in ("run_python", "run_python_async"):
            if self.rpc.use_direct_fallback or not self.rpc.is_docker_available():
                err_msg = (
                    f"policy_violation: {tool_name} requires the active container "
                    "sandbox (Docker CE in WSL2)"
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=err_msg,
                    content=err_msg,
                    structured={"ok": False, "exit_code": -1, "stderr": err_msg},
                    elapsed_ms=0.0,
                )
            if tool_name == "run_python_async":
                # WO-10.5 (F15): launch under Docker in a background task and
                # return the task ID immediately so long jobs never block the
                # voice loop (D-SAND-03).
                code = str(args.get("code", ""))
                task_name = str(args.get("name", "python-job"))[:60]
                container_id = getattr(self.rpc, "container_id", "lucca-sandbox")

                def _docker_python(cancel_event: threading.Event) -> tuple[int, str, str]:
                    cmd = ["docker", "exec", str(container_id), "python3", "-c", code]
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=3600, check=False
                    )
                    if cancel_event.is_set():
                        return -1, "", "cancelled by user"
                    return proc.returncode, proc.stdout, proc.stderr

                info = self.tasks.launch_task(task_name, _docker_python)
                content = (
                    f"Started background task '{info.name}' [{info.task_id}]. "
                    "Check progress with get_task_status."
                )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured={
                        "task_id": info.task_id,
                        "name": info.name,
                        "status": info.status,
                    },
                    content=content,
                    elapsed_ms=0.0,
                )
        # 8. New Native Tools (WO-24 Phase 0)
        if tool_name == "schedule_event":
            try:
                parsed_ev = ScheduleEventArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                ev_id = schedule_event(parsed_ev.event_name, parsed_ev.iso_datetime, parsed_ev.message)
                content = f"Event '{parsed_ev.event_name}' scheduled for {parsed_ev.iso_datetime} (ID: {ev_id})"
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    content=content,
                    structured={
                        "event_id": ev_id,
                        "event_name": parsed_ev.event_name,
                        "iso_datetime": parsed_ev.iso_datetime,
                        "message": parsed_ev.message,
                    },
                    elapsed_ms=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("schedule_event_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=0.0,
                )

        if tool_name == "artifact_verify":
            try:
                parsed_av = ArtifactVerifyArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                sha, size = verify_artifact(self.workspace_mgr.workspace_root, parsed_av.path)
                content = f"Verified {parsed_av.path}: SHA-256 {sha}, size {size} bytes"
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    content=content,
                    structured={"sha256": sha, "size_bytes": size, "path": parsed_av.path},
                    elapsed_ms=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("artifact_verify_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=0.0,
                )

        if tool_name == "clipboard_read":
            try:
                text, truncated = read_clipboard_text(max_chars=2000)
                content = text if text else "Clipboard is empty."
                # TRAP 2: structured MUST be None so output is stamped TOOL_CONTENT_UNTRUSTED
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    content=content,
                    structured=None,
                    content_truncated=truncated,
                    elapsed_ms=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("clipboard_read_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=0.0,
                )

        if tool_name == "inbox_handoff":
            try:
                parsed_inbox = InboxHandoffArgs.model_validate(args)
            except ValidationError as exc:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=f"invalid_arguments: {exc}",
                    elapsed_ms=0.0,
                )
            try:
                dest = self.workspace_mgr.import_from_inbox(parsed_inbox.filename)
                content = f"Imported '{parsed_inbox.filename}' into workspace."
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    content=content,
                    structured={"filename": parsed_inbox.filename, "dest_path": str(dest)},
                    elapsed_ms=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("inbox_handoff_failed", error=str(exc))
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=1,
                    stderr=str(exc),
                    elapsed_ms=0.0,
                )

        # 9. File Tools via RPC
        return self.rpc.execute(call_id=call_id, tool=tool_name, args=args)

    def close(self) -> None:
        """Closes the underlying RPC transport."""
        if hasattr(self, "rpc") and hasattr(self.rpc, "close"):
            self.rpc.close()
