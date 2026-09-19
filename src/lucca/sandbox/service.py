"""
Project Lucca — Unified Sandbox Service
Spec 09, Spec 12, ADR-003, ADR-004
Orchestrates file-sandbox RPC, web-sandbox fetches, host launcher, and policy guards.
"""

import json
import threading
from collections.abc import Callable
from pathlib import Path

import structlog
from pydantic import JsonValue, ValidationError

from lucca.core.schemas import Risk, ToolResult
from lucca.sandbox.file_tool import SafeFileTool
from lucca.sandbox.launcher import AppLauncher
from lucca.sandbox.policy import SequenceGuard, classify_risk, requires_confirmation
from lucca.sandbox.rpc import DockerRPCTransport
from lucca.sandbox.schemas import FetchUrlArgs, LaunchAppArgs
from lucca.sandbox.tasks import AsyncTaskInfo, AsyncTaskManager, TaskStatus
from lucca.sandbox.web_tool import fetch_url
from lucca.sandbox.workspace import WorkspaceManager

logger = structlog.get_logger(__name__)


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
        use_direct_fallback: bool = False,
        execute_apps: bool = True,
        tasks: AsyncTaskManager | None = None,
    ) -> None:
        self.workspace_mgr = WorkspaceManager(workspace_root=workspace_root)
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
        return requires_confirmation(tool_name)

    def execute_tool(
        self,
        call_id: str,
        tool_name: str,
        args: dict[str, JsonValue],
        confirmed: bool = False,
    ) -> ToolResult:
        """
        Validates and executes a tool call under sandbox security policy.
        """
        # 1. Sequence Guard Check
        allowed, reason = self.guard.check_and_record(tool_name)
        if not allowed:
            logger.warning("sequence_guard_blocked", tool=tool_name, reason=reason)
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-2,
                stderr=reason,
                elapsed_ms=0.0,
            )

        # 2. Confirmation Check
        if self.check_confirmation_needed(tool_name) and not confirmed:
            logger.info("confirmation_required", tool=tool_name, call_id=call_id)
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-3,
                stderr="confirmation_required",
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
                structured, content = fetch_url(
                    url=parsed_url.url,
                    render=parsed_url.render,
                    max_chars=parsed_url.max_chars,
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
            capabilities: dict[str, JsonValue] = {
                "tools": [
                    "launch_app",
                    "read_file",
                    "write_file",
                    "fetch_url",
                    "query_capabilities",
                    "get_task_status",
                    "list_tasks",
                    "cancel_task",
                ],
                "whitelisted_apps": list(self.launcher.apps.keys()),
                "reasoning_pathways": {},
                "workspace": str(self.workspace_mgr.workspace_root),
                "memory_subsystem": "SQLite-vec episodic & semantic memory (data/memory.sqlite)",
                "hardware_substrates": {
                    "dGPU": "NVIDIA GeForce RTX 5080 Laptop GPU (16 GB) - LLM llama-server",
                    "NPU": "Intel AI Boost NPU (OpenVINO) - Whisper ASR & 384-D vector embeddings",
                    "CPU": "Intel Core Ultra 9 275HX - Orchestrator, ZeroMQ IPC, Kokoro TTS",
                    "RAM": "16 GB Physical Host Memory",
                },
            }
            if category != "all" and category in capabilities:
                content_str = json.dumps({category: capabilities[category]}, indent=2)
                structured_data = {category: capabilities[category]}
            else:
                content_str = json.dumps(capabilities, indent=2)
                structured_data = capabilities

            return ToolResult(
                call_id=call_id,
                ok=True,
                exit_code=0,
                structured=structured_data,
                content=content_str,
                elapsed_ms=0.0,
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
        if tool_name == "run_python":
            if self.rpc.use_direct_fallback or not self.rpc.is_docker_available():
                err_msg = "policy_violation: run_python is disabled until Milestone 2 container isolation lands (requires active container sandbox)"
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=err_msg,
                    content=err_msg,
                    structured={"ok": False, "exit_code": -1, "stderr": err_msg},
                    elapsed_ms=0.0,
                )
            return self.rpc.execute(call_id=call_id, tool=tool_name, args=args)

        # 8. File Tools via RPC
        return self.rpc.execute(call_id=call_id, tool=tool_name, args=args)
