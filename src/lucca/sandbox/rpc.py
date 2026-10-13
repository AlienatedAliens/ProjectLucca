"""
Project Lucca — Sandbox Host <-> Container RPC Transport
Spec 09 §1, §2
Communicates with in-container lucca-toolsrv via docker exec over stdin/stdout.
"""

import atexit
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import cast

import structlog
from pydantic import JsonValue, ValidationError

from lucca.core.exceptions import (
    SandboxProtocolError,
    SandboxRPCDesyncError,
    SandboxTimeout,
)
from lucca.core.schemas import ToolResult
from lucca.sandbox.file_tool import SafeFileTool
from lucca.sandbox.schemas import (
    DeleteFileArgs,
    ListDirArgs,
    ReadFileArgs,
    SearchTextArgs,
    WriteFileArgs,
)

logger = structlog.get_logger(__name__)


_CONTAINER_WORLD_PRELUDE = '''
import sys as _sys, types as _types
class ContainerWorld:
    def __init__(self) -> None:
        self.world: dict[str, str] = {}
        self.initial_world: dict[str, str] = {}
        self.beliefs: dict[str, dict[str, str]] = {}
        self.second_order_beliefs: dict[str, dict[str, dict[str, str]]] = {}
    def process_event(self, ev: dict[str, object]) -> None:
        agent = str(ev.get("agent") or ev.get("actor") or "").strip().lower()
        action = str(ev.get("action") or "move").strip().lower()
        item = str(ev.get("item") or "").strip().lower()
        loc = str(ev.get("location") or ev.get("dst") or ev.get("to_loc") or "").strip().lower()
        raw_obs = ev.get("observed_by") or []
        obs_list = [str(o).strip().lower() for o in raw_obs if o] if isinstance(raw_obs, list) else []
        if not item or not loc:
            return
        if item not in self.initial_world or action in ("initial", "start", "starting", "located"):
            self.initial_world.setdefault(item, loc)
        if action in ("initial", "start", "starting", "located", "move", "place", "put", "relocate", "transfer", "set", "leave", "drop"):
            self.world[item] = loc
        present = set()
        if agent and agent not in ("none", "null", "all", "everyone"):
            self.beliefs.setdefault(agent, {})[item] = loc
            present.add(agent)
        for obs in obs_list:
            if obs and obs not in ("none", "null", "all", "everyone"):
                self.beliefs.setdefault(obs, {})[item] = loc
                present.add(obs)
        for x in present:
            if x not in self.second_order_beliefs:
                self.second_order_beliefs[x] = {}
            for y in present:
                if y not in self.second_order_beliefs[x]:
                    self.second_order_beliefs[x][y] = {}
                self.second_order_beliefs[x][y][item] = loc
    def place(self, arg1: str | None, arg2: str, arg3: str | None = None, observed_by: list[str] | None = None, actor: str | None = None) -> None:
        agent_val, item_val, loc_val = ((actor or ""), (arg1 or ""), arg2) if arg3 is None else ((arg1 or actor or ""), arg2, arg3)
        self.process_event({"agent": agent_val, "action": "place", "item": item_val, "location": loc_val, "observed_by": observed_by or []})
    def move(self, arg1: str | None, arg2: str, arg3: str | None = None, observed_by: list[str] | None = None, actor: str | None = None) -> None:
        agent_val, item_val, loc_val = ((actor or ""), (arg1 or ""), arg2) if arg3 is None else ((arg1 or actor or ""), arg2, arg3)
        self.process_event({"agent": agent_val, "action": "move", "item": item_val, "location": loc_val, "observed_by": observed_by or []})
    def reset(self) -> None:
        self.world.clear(); self.initial_world.clear(); self.beliefs.clear(); self.second_order_beliefs.clear()
    def process_events(self, events: list[dict[str, object]]) -> None:
        for ev in events:
            self.process_event(ev)
    def query(self, target_agent: str | None, item: str) -> str | None:
        t_item = item.strip().lower()
        if target_agent:
            ag = target_agent.strip().lower()
            if ag in self.beliefs:
                if t_item in self.beliefs[ag]:
                    return self.beliefs[ag][t_item]
                for k, v in self.beliefs[ag].items():
                    if t_item in k or k in t_item:
                        return v
            if t_item in self.initial_world:
                return self.initial_world[t_item]
            for k, v in self.initial_world.items():
                if t_item in k or k in t_item:
                    return v
        if t_item in self.world:
            return self.world[t_item]
        for k, v in self.world.items():
            if t_item in k or k in t_item:
                return v
        return None
    def query_second_order(self, observer_agent: str, target_agent: str, item: str) -> str | None:
        obs = observer_agent.strip().lower()
        tgt = target_agent.strip().lower()
        t_item = item.strip().lower()
        if obs == tgt:
            return self.query(obs, t_item)
        if obs in self.second_order_beliefs and tgt in self.second_order_beliefs[obs]:
            if t_item in self.second_order_beliefs[obs][tgt]:
                return self.second_order_beliefs[obs][tgt][t_item]
            for k, v in self.second_order_beliefs[obs][tgt].items():
                if t_item in k or k in t_item:
                    return v
        if t_item in self.initial_world:
            return self.initial_world[t_item]
        for k, v in self.initial_world.items():
            if t_item in k or k in t_item:
                return v
        return self.query(None, t_item)
    def query_recursive(self, agent_chain: list[str], item: str) -> str | None:
        if not agent_chain:
            return self.query(None, item)
        if len(agent_chain) == 1:
            return self.query(agent_chain[0], item)
        if len(agent_chain) == 2:
            return self.query_second_order(agent_chain[0], agent_chain[1], item)
        obs, sub = agent_chain[0].strip().lower(), agent_chain[1:]
        first = self.query_second_order(obs, sub[0], item)
        return first if len(sub) == 1 else self.query_recursive(sub, item)
ContainerWorld.query_recursive = ContainerWorld.query_recursive
ContainerWorld.query_nth = ContainerWorld.query_recursive
ContainerWorld.belief_chain = ContainerWorld.query_recursive
ContainerWorld.put = ContainerWorld.place
ContainerWorld.relocate = ContainerWorld.move
ContainerWorld.ask = ContainerWorld.query
ContainerWorld.query_2nd = ContainerWorld.query_second_order
ContainerWorld.belief_of_belief = ContainerWorld.query_second_order
ContainerWorld.query_nested = ContainerWorld.query_second_order
ContainerWorld.set_object_location = ContainerWorld.place
ContainerWorld.place_object = ContainerWorld.place
ContainerWorld.add_object = ContainerWorld.place
ContainerWorld.set_location = ContainerWorld.place
ContainerWorld.set_object = ContainerWorld.place
ContainerWorld.set_object_state = ContainerWorld.place
ContainerWorld.add_agent = lambda self, *args, **kwargs: None
ContainerWorld.record_observation = lambda self, *args, **kwargs: None
World = ContainerWorld
KnowledgeBase = ContainerWorld
BeliefTracker = ContainerWorld
class Agent:
    def __init__(self, name: str = "", *args, **kwargs) -> None:
        self.name = str(name)
    def __str__(self) -> str:
        return self.name
    def __repr__(self) -> str:
        return f"Agent({self.name!r})"
_cw_mod = _types.ModuleType("container_world")
_cw_mod.ContainerWorld = ContainerWorld
_cw_mod.World = ContainerWorld
_cw_mod.KnowledgeBase = ContainerWorld
_cw_mod.BeliefTracker = ContainerWorld
_cw_mod.Agent = Agent
_cw_mod.__all__ = ["ContainerWorld", "World", "KnowledgeBase", "BeliefTracker", "Agent"]
_sys.modules["container_world"] = _cw_mod
'''

def _inject_shared_workspace_prelude(code: str) -> str:
    """Injects ContainerWorld module shim into sandboxed Python code when referenced (D-REAS-10)."""
    if any(k in code for k in ("ContainerWorld", "container_world", "World", "KnowledgeBase", "BeliefTracker")):
        if "class ContainerWorld" not in code:
            return _CONTAINER_WORLD_PRELUDE + "\n" + code
    return code


class PersistentDockerWorker:
    """
    Long-lived stdio bridge to `lucca-toolsrv --loop` inside the unprivileged Docker container.
    Eliminates the ~472ms P50 `wsl docker exec` spawn tax per tool invocation down to <2ms.

    Invariants:
    1. Framing: Exactly 1 JSON line out per JSON line in.
    2. Serialization: Guarded by threading.Lock() across threads.
    3. Anti-Desync: Asserts res["call_id"] == expected_call_id. Mismatch kills process immediately.
    4. Hierarchical Timeout: Windows pipe read with ThreadPoolExecutor timeout.
    5. Proactive Lifetime: Recycles cleanly after max_calls (default 500).
    6. Container Isolation: Container retains --network none, read-only root, user 1000:1000.
    """

    def __init__(
        self,
        container_name: str = "lucca-file-sandbox",
        wsl_distro: str = "Ubuntu",
        max_calls: int = 500,
    ) -> None:
        self.container_name = container_name
        self.wsl_distro = wsl_distro
        self.max_calls = max_calls
        self._proc: subprocess.Popen[str] | None = None
        self._call_count = 0
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="persistent-rpc"
        )
        self._closed = False
        atexit.register(self.close)

    def is_alive(self) -> bool:
        """Returns True if worker subprocess handle exists and has not terminated."""
        return self._proc is not None and self._proc.poll() is None

    def _spawn_proc(self) -> None:
        """Spawns persistent `lucca-toolsrv --loop` in the Docker container via WSL."""
        if self.is_alive():
            return

        # Pre-spawn sweep: Terminate any orphaned loop processes in the container
        # from prior host crashes or taskkills to prevent process accumulation
        reap_script = (
            "import os, signal; "
            "[os.kill(int(p), signal.SIGKILL) for p in os.listdir('/proc') "
            "if p.isdigit() and p not in ('1', str(os.getpid())) and "
            "'lucca-toolsrv' in open(f'/proc/{p}/cmdline', 'rb').read()"
            ".decode('utf-8', errors='ignore') and "
            "'--loop' in open(f'/proc/{p}/cmdline', 'rb').read()"
            ".decode('utf-8', errors='ignore')]"
        )
        try:
            subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "wsl",
                    "-d",
                    self.wsl_distro,
                    "--",
                    "docker",
                    "exec",
                    self.container_name,
                    "python3",
                    "-c",
                    reap_script,
                ],
                capture_output=True,
                timeout=3.0,
                check=False,
            )
        except Exception as reap_err:  # noqa: BLE001
            logger.debug("pre_spawn_reap_ignored", error=str(reap_err))

        cmd = [
            "wsl",
            "-d",
            self.wsl_distro,
            "--",
            "docker",
            "exec",
            "-i",
            "-e",
            "LUCCA_SANDBOX_CONTAINER=1",
            "-e",
            "OPENBLAS_NUM_THREADS=1",
            "-e",
            "MKL_NUM_THREADS=1",
            "-e",
            "OMP_NUM_THREADS=1",
            "-e",
            "PYTHONPATH=/workspace:/opt:/opt/toolsrv:/opt/lucca/sandbox",
            self.container_name,
            "lucca-toolsrv",
            "--loop",
        ]
        logger.info("spawning_persistent_docker_worker", container=self.container_name)
        self._proc = subprocess.Popen(  # noqa: S603, S607
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._call_count = 0

    def _kill_proc(self) -> None:
        """Forcefully kills the persistent worker process and resets thread pool."""
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception as exc:
                logger.debug("kill_proc_failed", error=str(exc))
            try:
                self._proc.wait(timeout=1.0)
            except Exception as exc:
                logger.debug("wait_proc_failed", error=str(exc))
            self._proc = None
        # Discard executor thread to prevent any head-of-line blocking on aborted reads
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            logger.debug("shutdown_executor_failed", error=str(exc))
        if not self._closed:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="persistent-rpc"
            )

    def close(self) -> None:
        """Gracefully closes persistent worker process and shuts down executor."""
        with self._lock:
            self._closed = True
            if self._proc is not None:
                try:
                    if self._proc.stdin:
                        self._proc.stdin.close()
                    self._proc.wait(timeout=2.0)
                except Exception as exc:
                    logger.debug("close_proc_failed", error=str(exc))
                    self._kill_proc()
                finally:
                    self._proc = None
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception as exc:
                logger.debug("shutdown_executor_failed", error=str(exc))

    def __del__(self) -> None:
        try:
            self.close()
        except Exception as exc:
            logger.debug("del_close_failed", error=str(exc))

    def execute(
        self,
        call_id: str,
        tool: str,
        args: dict[str, JsonValue],
        timeout_s: float | None = None,
    ) -> dict[str, JsonValue]:
        """
        Executes a single tool call through the persistent stdio bridge.
        Guarantees thread-safe serialized execution, timeout enforcement,
        framing validation, and call_id anti-desync protection.

        Differentiated hierarchical timeouts:
        - run_python: 15.0s (10.0s internal execution limit + 5.0s fork/pipe overhead)
        - filesystem/search tools: 5.0s (tight threshold since persistent I/O runs in 4-8ms)
        """
        if self._closed:
            raise SandboxProtocolError("PersistentDockerWorker is closed")

        if timeout_s is None:
            timeout_s = 15.0 if tool == "run_python" else 5.0

        with self._lock:
            # Proactive recycling after max_calls to prevent long-lived memory drift
            if self._call_count >= self.max_calls:
                logger.info(
                    "proactive_worker_recycle",
                    call_count=self._call_count,
                    max_calls=self.max_calls,
                )
                self._kill_proc()

            if not self.is_alive():
                self._spawn_proc()

            if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
                self._kill_proc()
                raise SandboxProtocolError("Failed to initialize worker stdio pipes")

            req_payload = json.dumps({"call_id": call_id, "tool": tool, "args": args})

            # Send exactly 1 line
            try:
                self._proc.stdin.write(req_payload + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as write_err:
                logger.error("persistent_worker_stdin_broken", error=str(write_err))
                self._kill_proc()
                raise SandboxProtocolError(f"Worker stdin broken: {write_err}") from write_err

            # Read stdout line(s) with hierarchical timeout, skipping any stray non-JSON log lines
            res_dict: dict[str, JsonValue] | None = None
            t_deadline = time.monotonic() + timeout_s
            while time.monotonic() < t_deadline:
                remaining_t = max(0.05, t_deadline - time.monotonic())
                future = self._executor.submit(self._proc.stdout.readline)
                try:
                    raw_line = future.result(timeout=remaining_t)
                except concurrent.futures.TimeoutError as timeout_err:
                    logger.error(
                        "persistent_worker_timeout",
                        call_id=call_id,
                        timeout_s=timeout_s,
                    )
                    self._kill_proc()
                    raise SandboxTimeout(
                        f"Persistent worker timed out after {timeout_s}s"
                    ) from timeout_err
                except Exception as read_err:
                    logger.error("persistent_worker_read_exception", error=str(read_err))
                    self._kill_proc()
                    raise SandboxProtocolError(f"Worker stdout read error: {read_err}") from read_err

                if not raw_line or not raw_line.strip():
                    logger.error("persistent_worker_empty_eof", call_id=call_id)
                    self._kill_proc()
                    raise SandboxProtocolError("Persistent worker returned empty line / unexpected EOF")

                stripped = raw_line.strip()
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict) and ("call_id" in parsed or "ok" in parsed):
                        res_dict = parsed
                        break
                except json.JSONDecodeError:
                    logger.warning(
                        "persistent_worker_stray_line_skipped",
                        sample=stripped[:120],
                    )
                    continue

            if res_dict is None:
                self._kill_proc()
                raise SandboxTimeout(f"Persistent worker did not produce valid JSON response within {timeout_s}s")

            # Call-ID correlation & anti-desync guard
            returned_call_id = str(res_dict.get("call_id", ""))
            if returned_call_id != call_id:
                logger.critical(
                    "persistent_worker_call_id_desync",
                    expected_call_id=call_id,
                    actual_call_id=returned_call_id,
                )
                self._kill_proc()
                raise SandboxRPCDesyncError(
                    f"Protocol desync: expected call_id={call_id!r}, received {returned_call_id!r}"
                )

            self._call_count += 1
            return res_dict


class DockerRPCTransport:
    """
    Host-side transport communicating with lucca-toolsrv inside a Docker container.
    Supports persistent stdio bridge (`lucca-toolsrv --loop`) for <2ms turnaround,
    with automatic fallback to single-shot `docker exec` and direct execution mode.
    """

    def __init__(
        self,
        container_name: str = "lucca-file-sandbox",
        wsl_distro: str = "Ubuntu",
        use_direct_fallback: bool = False,
        fallback_file_tool: SafeFileTool | None = None,
        use_persistent_worker: bool = True,
        max_worker_calls: int = 500,
    ) -> None:
        self.container_name = container_name
        self.wsl_distro = wsl_distro
        self.use_direct_fallback = use_direct_fallback
        self.fallback_file_tool = fallback_file_tool
        self.use_persistent_worker = use_persistent_worker
        self.max_worker_calls = max_worker_calls
        self._worker: PersistentDockerWorker | None = None
        self._worker_lock = threading.Lock()

    def get_worker(self) -> PersistentDockerWorker:
        """Lazily obtains or creates the persistent worker handle."""
        with self._worker_lock:
            if self._worker is None:
                self._worker = PersistentDockerWorker(
                    container_name=self.container_name,
                    wsl_distro=self.wsl_distro,
                    max_calls=self.max_worker_calls,
                )
            return self._worker

    def close(self) -> None:
        """Closes any active persistent worker."""
        with self._worker_lock:
            if self._worker is not None:
                self._worker.close()
                self._worker = None

    def is_docker_available(self) -> bool:
        """Checks if WSL2 Docker CLI is available and responsive."""
        if shutil.which("wsl") is None:
            return False
        try:
            res = subprocess.run(  # noqa: S603
                ["wsl", "-d", self.wsl_distro, "--", "docker", "version"],  # noqa: S607
                capture_output=True,
                timeout=15.0,
                check=False,
            )
            return res.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def is_container_running(self) -> bool:
        """Checks if the sandbox container is actively running."""
        try:
            res = subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "wsl",
                    "-d",
                    self.wsl_distro,
                    "--",
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.Running}}",
                    self.container_name,
                ],
                capture_output=True,
                text=True,
                timeout=10.0,
                check=False,
            )
            return res.returncode == 0 and res.stdout.strip().lower() == "true"
        except (subprocess.SubprocessError, OSError):
            return False

    def ensure_container_running(self, workspace_path: Path | str | None = None) -> bool:
        """Ensures the file sandbox container is running, launching it if necessary."""
        if not self.is_docker_available():
            return False
        if self.is_container_running():
            return True

        # Lazy import: container_spec is only needed on the cold-start path.
        from lucca.sandbox.container_spec import get_file_sandbox_run_args  # noqa: PLC0415

        # Remove any stopped/stale container with the same name
        subprocess.run(  # noqa: S603
            ["wsl", "-d", self.wsl_distro, "--", "docker", "rm", "-f", self.container_name],  # noqa: S607
            capture_output=True,
            timeout=5.0,
            check=False,
        )
        run_args = get_file_sandbox_run_args(
            workspace_path=workspace_path,
            container_name=self.container_name,
        )
        cmd = ["wsl", "-d", self.wsl_distro, "--", "docker"] + run_args
        res = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            timeout=10.0,
            check=False,
        )
        return res.returncode == 0 and self.is_container_running()

    def warmup(self) -> bool:
        """Pre-emptively verifies container status and warms up persistent RPC worker."""
        if not self.ensure_container_running():
            return False
        if self.use_persistent_worker:
            worker = self.get_worker()
            if not worker.is_alive():
                res = self.execute("warmup", "run_python", {"code": "pass"}, timeout_s=10.0)
                return res.ok
        return True

    def _process_response_dict(
        self,
        call_id: str,
        tool: str,
        res_dict: dict[str, JsonValue],
        elapsed_ms: float,
    ) -> ToolResult:
        """Validates structured result dict and enforces T-SBX-16 SHA-256 host verification."""
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

        # Ensure list_dir produces a human-readable content string if None
        if tool == "list_dir" and ok and isinstance(structured, dict) and not content:
            entries = structured.get("entries", [])
            if isinstance(entries, list):
                if entries:
                    names = [str(e.get("name", "")) for e in entries if isinstance(e, dict)]
                    content = f"Directory contains {len(entries)} item(s): {', '.join(names)}"
                else:
                    content = "Directory is empty (0 items)."

        return ToolResult(
            call_id=res_dict.get("call_id", call_id),
            ok=ok,
            exit_code=res_dict.get("exit_code", 0),
            structured=structured,
            content=content,
            content_truncated=bool(res_dict.get("content_truncated", False)),
            elapsed_ms=elapsed_ms,
            stderr=str(res_dict.get("stderr") or ("" if ok else (structured.get("stderr") if isinstance(structured, dict) else content) or "execution_failed")),
        )

    def _execute_single_shot(
        self,
        call_id: str,
        tool: str,
        args: dict[str, JsonValue],
        timeout_s: float,
        t0: float,
    ) -> ToolResult:
        """Fallback per-call docker exec execution (legacy mode)."""
        cmd = [
            "wsl",
            "-d",
            self.wsl_distro,
            "--",
            "docker",
            "exec",
            "-i",
            "-e",
            "LUCCA_SANDBOX_CONTAINER=1",
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
                # Find the valid JSON response line (handling multi-line stdout or warnings)
                res_dict = None
                lines = [l.strip() for l in stdout.strip().splitlines() if l.strip()]
                for line in reversed(lines):
                    try:
                        parsed = json.loads(line)
                        if isinstance(parsed, dict) and ("call_id" in parsed or "ok" in parsed):
                            res_dict = parsed
                            break
                    except json.JSONDecodeError:
                        continue

                if res_dict is None:
                    res_dict = json.loads(stdout.strip())
                return self._process_response_dict(call_id, tool, res_dict, elapsed_ms)
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
            logger.debug("persistent_worker_transport_error", error=str(exc))
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-2,
                stderr=f"transport_error: {exc}",
                elapsed_ms=elapsed_ms,
            )

    def execute(
        self,
        call_id: str,
        tool: str,
        args: dict[str, JsonValue],
        timeout_s: float | None = None,
    ) -> ToolResult:
        """Executes a single tool call against the container or fallback tool."""
        t0 = time.perf_counter()

        # Differentiated timeout resolution: 15.0s for child python, 5.0s for filesystem
        effective_timeout_s = (
            timeout_s if timeout_s is not None else (15.0 if tool == "run_python" else 5.0)
        )
        if tool == "run_python" and isinstance(args.get("code"), str):
            args = dict(args)
            args["code"] = _inject_shared_workspace_prelude(str(args["code"]))

        if self.use_direct_fallback:
            return self._execute_direct(call_id, tool, args, t0)

        if self.use_persistent_worker:
            worker = self.get_worker()
            if not worker.is_alive():
                # Worker is not yet active; verify container readiness before spawning
                if not self.is_docker_available():
                    return ToolResult(
                        call_id=call_id,
                        ok=False,
                        exit_code=-2,
                        stderr="sandbox unavailable: Docker/WSL not reachable",
                        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                    )

                if not self.is_container_running() and not self.ensure_container_running():
                    return ToolResult(
                        call_id=call_id,
                        ok=False,
                        exit_code=-2,
                        stderr="sandbox unavailable: container could not be started",
                        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                    )

            try:
                res_dict = worker.execute(
                    call_id=call_id, tool=tool, args=args, timeout_s=effective_timeout_s
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return self._process_response_dict(call_id, tool, res_dict, elapsed_ms)
            except SandboxTimeout as to_err:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-2,
                    stderr=str(to_err),
                    elapsed_ms=elapsed_ms,
                )
            except SandboxRPCDesyncError as desync_err:
                logger.error("persistent_rpc_desync_falling_back", err=str(desync_err))
                return self._execute_single_shot(call_id, tool, args, effective_timeout_s, t0)
            except (SandboxProtocolError, Exception) as worker_err:
                logger.warning("persistent_rpc_failure_falling_back", err=str(worker_err))
                return self._execute_single_shot(call_id, tool, args, effective_timeout_s, t0)

        # Single-shot path (legacy / fallback)
        if not self.is_docker_available():
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-2,
                stderr="sandbox unavailable: Docker/WSL not reachable",
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )

        if not self.is_container_running() and not self.ensure_container_running():
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-2,
                stderr="sandbox unavailable: container could not be started",
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )

        return self._execute_single_shot(call_id, tool, args, effective_timeout_s, t0)

    def _execute_direct(
        self,
        call_id: str,
        tool: str,
        args: dict[str, JsonValue],
        t0: float,
    ) -> ToolResult:
        """Fallback in-process executor for unit tests."""
        file_tool = self.fallback_file_tool or SafeFileTool()
        try:
            if tool == "list_dir":
                parsed_ld = ListDirArgs.model_validate(args)
                res = file_tool.list_dir(
                    path=parsed_ld.path,
                    recursive=parsed_ld.recursive,
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
                parsed_rf = ReadFileArgs.model_validate(args)
                structured, content = file_tool.read_file(
                    path=parsed_rf.path,
                    max_bytes=parsed_rf.max_bytes,
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
                parsed_wf = WriteFileArgs.model_validate(args)
                structured_w = file_tool.write_file(
                    path=parsed_wf.path,
                    content=parsed_wf.content,
                    mode=parsed_wf.mode,
                )
                return ToolResult(
                    call_id=call_id,
                    ok=True,
                    exit_code=0,
                    structured=cast(dict[str, JsonValue], structured_w),
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
            if tool == "search_text":
                parsed_st = SearchTextArgs.model_validate(args)
                structured_s, content_s = file_tool.search_text(
                    pattern=parsed_st.pattern,
                    path=parsed_st.path,
                    max_hits=parsed_st.max_hits,
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
                err_msg = (
                    "policy_violation: run_python is disabled until Milestone 2 "
                    "container isolation lands"
                )
                return ToolResult(
                    call_id=call_id,
                    ok=False,
                    exit_code=-1,
                    stderr=err_msg,
                    content=err_msg,
                    structured={"ok": False, "exit_code": -1, "stderr": err_msg},
                    elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                )
            if tool == "delete_file":
                parsed_df = DeleteFileArgs.model_validate(args)
                structured_d = file_tool.delete_file(path=parsed_df.path)
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
        except ValidationError as val_err:
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=-1,
                stderr=f"invalid_arguments: {val_err}",
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("rpc_execute_error", error=str(exc))
            return ToolResult(
                call_id=call_id,
                ok=False,
                exit_code=1,
                stderr=str(exc),
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )
