"""
Project Lucca — In-Container Tool Server (lucca-toolsrv)
Spec 09 §1, §4, §5
Handles JSON RPC over stdin/stdout inside Docker sandboxes.
Supports:
1. Single-shot execution (default, legacy docker exec per call)
2. Persistent streaming execution (--loop, 1 JSON request line -> 1 JSON response line)
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

from lucca.core.exceptions import SandboxPathError
from lucca.sandbox.file_tool import SafeFileTool


def dispatch_request(req_dict: dict[str, Any], file_tool: SafeFileTool) -> dict[str, Any]:
    """Dispatches an in-container tool call, guaranteeing a valid dict response."""
    t0 = time.perf_counter()
    call_id = str(req_dict.get("call_id", ""))
    tool = str(req_dict.get("tool", ""))
    args = req_dict.get("args", {})
    if not isinstance(args, dict):
        args = {}

    try:
        if tool == "list_dir":
            path = str(args.get("path", ""))
            recursive = bool(args.get("recursive", False))
            res = file_tool.list_dir(path=path, recursive=recursive)
            return {
                "call_id": call_id,
                "ok": True,
                "exit_code": 0,
                "structured": res,
                "content": None,
                "content_truncated": bool(res.get("truncated", False)),
                "stderr": "",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }

        elif tool == "read_file":
            path = str(args.get("path", ""))
            max_bytes = int(args.get("max_bytes", 262144))
            structured, content = file_tool.read_file(path=path, max_bytes=max_bytes)
            return {
                "call_id": call_id,
                "ok": True,
                "exit_code": 0,
                "structured": structured,
                "content": content,
                "content_truncated": bool(structured.get("truncated", False)),
                "stderr": "",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }

        elif tool == "write_file":
            path = str(args.get("path", ""))
            content = str(args.get("content", ""))
            mode = str(args.get("mode", "create"))
            if mode not in ("create", "overwrite", "append"):
                mode = "create"
            structured = file_tool.write_file(path=path, content=content, mode=mode)  # type: ignore[arg-type]
            return {
                "call_id": call_id,
                "ok": True,
                "exit_code": 0,
                "structured": structured,
                "content": None,
                "content_truncated": False,
                "stderr": "",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }

        elif tool == "search_text":
            pattern = str(args.get("pattern", ""))
            path = str(args.get("path", ""))
            max_hits = int(args.get("max_hits", 200))
            structured, content = file_tool.search_text(
                pattern=pattern, path=path, max_hits=max_hits
            )
            return {
                "call_id": call_id,
                "ok": True,
                "exit_code": 0,
                "structured": structured,
                "content": content,
                "content_truncated": bool(structured.get("truncated", False)),
                "stderr": "",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }

        elif tool == "run_python":
            code = str(args.get("code", ""))
            timeout = int(args.get("timeout", 10))
            structured, content = file_tool.run_python(code=code, timeout=timeout)
            ok = bool(structured.get("ok", False))
            exit_code = int(structured.get("exit_code", -1))
            return {
                "call_id": call_id,
                "ok": ok,
                "exit_code": exit_code,
                "structured": structured,
                "content": content,
                "content_truncated": False,
                "stderr": "",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }

        elif tool == "delete_file":
            path = str(args.get("path", ""))
            structured = file_tool.delete_file(path=path)
            return {
                "call_id": call_id,
                "ok": True,
                "exit_code": 0,
                "structured": structured,
                "content": None,
                "content_truncated": False,
                "stderr": "",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }

        else:
            return {
                "call_id": call_id,
                "ok": False,
                "exit_code": -2,
                "structured": None,
                "content": None,
                "content_truncated": False,
                "stderr": f"Unknown tool: {tool}",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }

    except SandboxPathError as err:
        return {
            "call_id": call_id,
            "ok": False,
            "exit_code": 1,
            "structured": {"code": err.code, "message": err.message},
            "content": None,
            "content_truncated": False,
            "stderr": f"{err.code}: {err.message}",
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "call_id": call_id,
            "ok": False,
            "exit_code": -1,
            "structured": None,
            "content": None,
            "content_truncated": False,
            "stderr": str(exc),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


def run_loop() -> None:
    """
    Persistent stdio loop.
    Invariant: Exactly one single-line JSON out per line in, always.
    Never lets an unhandled exception escape or corrupt stdout framing.
    """
    file_tool = SafeFileTool(workspace_root=Path("/workspace"))

    for line in sys.stdin:
        raw_line = line.strip()
        if not raw_line:
            continue

        call_id = ""
        try:
            req = json.loads(raw_line)
            if not isinstance(req, dict):
                raise ValueError("JSON request must be an object")
            call_id = str(req.get("call_id", ""))
            response = dispatch_request(req, file_tool)
        except json.JSONDecodeError as err:
            response = {
                "call_id": call_id,
                "ok": False,
                "exit_code": -2,
                "structured": None,
                "content": None,
                "content_truncated": False,
                "stderr": f"JSON decode error: {err}",
                "elapsed_ms": 0.0,
            }
        except Exception as exc:  # noqa: BLE001
            response = {
                "call_id": call_id,
                "ok": False,
                "exit_code": -1,
                "structured": None,
                "content": None,
                "content_truncated": False,
                "stderr": f"Unhandled dispatch exception: {exc}",
                "elapsed_ms": 0.0,
            }
        except BaseException as fatal:
            # Even on fatal process termination, attempt outputting framing line
            response = {
                "call_id": call_id,
                "ok": False,
                "exit_code": -99,
                "structured": None,
                "content": None,
                "content_truncated": False,
                "stderr": f"Fatal worker error: {fatal}",
                "elapsed_ms": 0.0,
            }
            try:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            except Exception:
                pass
            raise

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def run_server() -> None:
    """Single-shot execution reading entire stdin and exiting (legacy mode)."""
    t0 = time.perf_counter()
    raw_input = sys.stdin.read()
    if not raw_input.strip():
        response: dict[str, Any] = {
            "call_id": "",
            "ok": False,
            "exit_code": -2,
            "structured": None,
            "content": None,
            "content_truncated": False,
            "stderr": "Empty request on stdin",
            "elapsed_ms": 0.0,
        }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
        return

    try:
        req = json.loads(raw_input)
    except json.JSONDecodeError as err:
        response = {
            "call_id": "",
            "ok": False,
            "exit_code": -2,
            "structured": None,
            "content": None,
            "content_truncated": False,
            "stderr": f"JSON decode error: {err}",
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
        return

    file_tool = SafeFileTool(workspace_root=Path("/workspace"))
    response = dispatch_request(req, file_tool)
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    if "--loop" in sys.argv or "--persistent" in sys.argv:
        run_loop()
    else:
        run_server()
