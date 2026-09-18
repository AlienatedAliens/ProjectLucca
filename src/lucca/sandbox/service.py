"""
Project Lucca — Unified Sandbox Service
Spec 09, Spec 12, ADR-003, ADR-004
Orchestrates file-sandbox RPC, web-sandbox fetches, host launcher, and policy guards.
"""

import json
from pathlib import Path

import structlog
from pydantic import JsonValue

from lucca.core.schemas import Risk, ToolResult
from lucca.sandbox.file_tool import SafeFileTool
from lucca.sandbox.launcher import AppLauncher
from lucca.sandbox.policy import SequenceGuard, classify_risk, requires_confirmation
from lucca.sandbox.rpc import DockerRPCTransport
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
            app_name = str(args.get("app_name", ""))
            file_arg = str(args["file"]) if "file" in args and args["file"] else None
            url_arg = str(args["url"]) if "url" in args and args["url"] else None

            ok, msg = self.launcher.launch(
                app_name=app_name,
                file_arg=file_arg,
                url_arg=url_arg,
            )
            return ToolResult(
                call_id=call_id,
                ok=ok,
                exit_code=0 if ok else -1,
                structured={"status": msg, "app_name": app_name},
                content=msg,
                elapsed_ms=0.0,
            )

        # 4. Web Fetch Tool
        if tool_name == "fetch_url":
            url = str(args.get("url", ""))
            render = bool(args.get("render", False))
            max_chars = int(str(args.get("max_chars", 20000)))
            try:
                structured, content = fetch_url(url=url, render=render, max_chars=max_chars)
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

        # 6. File Tools via RPC
        return self.rpc.execute(call_id=call_id, tool=tool_name, args=args)
