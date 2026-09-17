"""
Project Lucca — Sandbox Host <-> Container RPC Transport
Spec 09 §1, §2
Communicates with in-container lucca-toolsrv via docker exec over stdin/stdout.
"""

import hashlib
import json
import shutil
import subprocess
import time
from typing import Any, cast

import structlog
from pydantic import JsonValue

from lucca.core.schemas import ToolResult
from lucca.sandbox.file_tool import SafeFileTool

logger = structlog.get_logger(__name__)


class DockerRPCTransport:
    """
    Host-side transport communicating with lucca-toolsrv inside a Docker container
    via `wsl -d Ubuntu -- docker exec -i <container> lucca-toolsrv`.
    Includes a fallback direct execution mode for fast headless test runs.
    """

    def __init__(
        self,
        container_name: str = "lucca-file-sandbox",
        wsl_distro: str = "Ubuntu",
        use_direct_fallback: bool = False,
        fallback_file_tool: SafeFileTool | None = None,
    ) -> None:
        self.container_name = container_name
        self.wsl_distro = wsl_distro
        self.use_direct_fallback = use_direct_fallback
        self.fallback_file_tool = fallback_file_tool

    def is_docker_available(self) -> bool:
        """Checks if WSL2 Docker CLI is available and responsive."""
        if shutil.which("wsl") is None:
            return False
        try:
            res = subprocess.run(  # noqa: S603
                ["wsl", "-d", self.wsl_distro, "--", "docker", "version"],  # noqa: S607
                capture_output=True,
                timeout=5.0,
                check=False,
            )
            return res.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def execute(
        self,
        call_id: str,
        tool: str,
        args: dict[str, Any],
        timeout_s: float = 15.0,
    ) -> ToolResult:
        """Executes a single tool call against the container or fallback tool."""
        t0 = time.perf_counter()

        if self.use_direct_fallback or not self.is_docker_available():
            return self._execute_direct(call_id, tool, args, t0)

        cmd = [
            "wsl",
            "-d",
            self.wsl_distro,
            "--",
            "docker",
            "exec",
            "-i",
            self.container_name,
            "lucca-toolsrv",
        ]

        req_payload = json.dumps({"call_id": call_id, "tool": tool, "args": args})

        try:
            proc = subprocess.Popen(  # noqa: S603, S607
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = proc.communicate(input=req_payload, timeout=timeout_s)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            if not stdout.strip():
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=proc.returncode if proc.returncode != 0 else -2,
                    stderr=stderr or "protocol: empty response from container",
                    elapsed_ms=elapsed_ms,
                )

            try:
                res_dict = json.loads(stdout.strip())
                ok = bool(res_dict.get("ok", False))
                structured = res_dict.get("structured")
                content = res_dict.get("content")

                # T-SBX-16: Host recomputes sha256 for read_file; mismatch => ok=False, audit
                if tool == "read_file" and ok and isinstance(structured, dict):
                    expected_sha = str(structured.get("sha256", ""))
                    is_trunc = bool(structured.get("truncated", False))
                    if expected_sha and not is_trunc and content is not None:
                        actual_sha = hashlib.sha256(str(content).encode("utf-8")).hexdigest()
                        if actual_sha != expected_sha:
                            logger.warning(
                                "sha256_audit_mismatch",
                                expected=expected_sha,
                                actual=actual_sha,
                            )
                            err_msg = (
                                f"audit failure: sha256 mismatch "
                                f"(expected {expected_sha}, computed {actual_sha})"
                            )
                            return ToolResult(
                                call_id=call_id,
                                ok=False,
                                exit_code=-4,
                                stderr=err_msg,
                                elapsed_ms=elapsed_ms,
                            )

                return ToolResult(
                    call_id=res_dict.get("call_id", call_id),
                    ok=ok,
                    exit_code=res_dict.get("exit_code", 0),
                    structured=structured,
                    content=content,
                    content_truncated=bool(res_dict.get("content_truncated", False)),
                    elapsed_ms=elapsed_ms,
                    stderr=res_dict.get("stderr", stderr),
                )
            except json.JSONDecodeError as json_err:
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-2,
                    stderr=f"protocol: invalid JSON ({json_err})",
                    elapsed_ms=elapsed_ms,
                )

        except subprocess.TimeoutExpired:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            # Send docker kill to the container exec process
            kill_cmd = [
                "wsl",
                "-d",
                self.wsl_distro,
                "--",
                "docker",
                "kill",
                "-s",
                "KILL",
                self.container_name,
            ]
            try:
                subprocess.run(  # noqa: S603, S607
                    kill_cmd, capture_output=True, timeout=2.0, check=False
                )
            except (subprocess.SubprocessError, OSError):
                pass

            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-2,
                stderr=f"timeout after {timeout_s}s",
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-2,
                stderr=f"transport_error: {exc}",
                elapsed_ms=elapsed_ms,
            )

    def _execute_direct(
        self,
        call_id: str,
        tool: str,
        args: dict[str, Any],
        t0: float,
    ) -> ToolResult:
        """Fallback in-process executor for unit tests."""
        file_tool = self.fallback_file_tool or SafeFileTool()
        try:
            if tool == "list_dir":
                res = file_tool.list_dir(
                    path=str(args.get("path", "")),
                    recursive=bool(args.get("recursive", False)),
                )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=cast(dict[str, JsonValue], res),
                    content_truncated=bool(res.get("truncated", False)),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
            if tool == "read_file":
                structured, content = file_tool.read_file(
                    path=str(args.get("path", "")),
                    max_bytes=int(args.get("max_bytes", 262144)),
                )
                if not structured.get("truncated", False):
                    actual_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    expected_sha = str(structured.get("sha256", ""))
                    if expected_sha and actual_sha != expected_sha:
                        err_msg = (
                            f"audit failure: sha256 mismatch "
                            f"(expected {expected_sha}, computed {actual_sha})"
                        )
                        return ToolResult(
                            call_id=call_id,
                            ok=False,
                            exit_code=-4,
                            stderr=err_msg,
                            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                        )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=cast(dict[str, JsonValue], structured),
                    content=content,
                    content_truncated=bool(structured.get("truncated", False)),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
            if tool == "write_file":
                structured_w = file_tool.write_file(
                    path=str(args.get("path", "")),
                    content=str(args.get("content", "")),
                    mode=str(args.get("mode", "create")),  # type: ignore[arg-type]
                )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=cast(dict[str, JsonValue], structured_w),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
            if tool == "search_text":
                structured_s, content_s = file_tool.search_text(
                    pattern=str(args.get("pattern", "")),
                    path=str(args.get("path", "")),
                    max_hits=int(args.get("max_hits", 200)),
                )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=cast(dict[str, JsonValue], structured_s),
                    content=content_s,
                    content_truncated=bool(structured_s.get("truncated", False)),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
            if tool == "run_python":
                structured_p, content_p = file_tool.run_python(
                    code=str(args.get("code", "")),
                    timeout=int(args.get("timeout", 10)),
                )
                exit_code_raw = structured_p.get("exit_code", -1)
                exit_code_int = int(str(exit_code_raw))
                return ToolResult(
                    call_id=call_id,
                    ok=bool(structured_p.get("ok", False)),
                    exit_code=exit_code_int,
                    structured=cast(dict[str, JsonValue], structured_p),
                    content=content_p,
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
            if tool == "delete_file":
                structured_d = file_tool.delete_file(path=str(args.get("path", "")))
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=cast(dict[str, JsonValue], structured_d),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )

            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-2,
                stderr=f"Unknown tool: {tool}",
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=str(exc),
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )
