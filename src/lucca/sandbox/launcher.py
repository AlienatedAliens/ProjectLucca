"""
Project Lucca — Hardened Host Application Launcher
Spec 09 §6, TM-04
Launches whitelisted desktop applications with rate limiting and argument validation.
"""

import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import psutil
import structlog
from pydantic import JsonValue

if sys.platform == "win32":
    import ctypes
else:
    ctypes = None  # type: ignore[assignment]

from lucca.core.config import get_config
from lucca.core.exceptions import SandboxPathError
from lucca.sandbox.file_tool import validate_rel_path
from lucca.sandbox.web_tool import validate_url_ssrf

logger = structlog.get_logger(__name__)

# Windows process creation flags
DETACHED_PROCESS: int = 0x00000008
CREATE_NEW_PROCESS_GROUP: int = 0x00000200


class AppLauncher:
    """
    Hardened host process launcher for whitelisted desktop applications.
    Enforces strict rate limits (<= 3/min, min 5s between launches),
    never uses shell=True, and validates templated parameters.
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        workspace_root: Path | str | None = None,
        execute: bool = True,
    ) -> None:
        self.config = get_config()
        self.workspace_root = (
            Path(workspace_root)
            if workspace_root is not None
            else self.config.resolve_path("workspace")
        )
        self.execute = execute
        self.launch_history: list[float] = []

        cfg_dir = self.config.resolve_path("config")
        cfg_file = Path(config_path) if config_path else cfg_dir / "tool_whitelist.toml"
        self.apps = self._load_whitelist(cfg_file)

    def _load_whitelist(self, cfg_file: Path) -> dict[str, dict[str, JsonValue]]:
        """Loads whitelist from TOML or fallback default mapping."""
        defaults: dict[str, dict[str, JsonValue]] = {
            "calculator": {
                "exe": "calc.exe",
                "aliases": ["calculator", "calc"],
                "args": [],
                "single_instance": True,
            },
            "notepad": {
                "exe": "notepad.exe",
                "aliases": ["notepad", "text editor"],
                "args": ["{file?}"],
                "single_instance": False,
            },
        }

        if cfg_file.exists():
            try:
                with open(cfg_file, "rb") as f:
                    data = tomllib.load(f)
                    if "apps" in data and isinstance(data["apps"], dict):
                        apps_dict: dict[str, dict[str, JsonValue]] = data["apps"]
                        return apps_dict
            except Exception as exc:  # noqa: BLE001
                logger.warning("whitelist_load_failed", error=str(exc))

        return defaults

    def find_app_entry(self, name: str) -> tuple[str, dict[str, JsonValue]] | None:
        """Finds app config by key or alias (case-insensitive)."""
        target = name.strip().lower()
        for app_id, entry in self.apps.items():
            if app_id.lower() == target:
                return app_id, entry
            aliases = [a.lower() for a in entry.get("aliases", [])]
            if target in aliases:
                return app_id, entry
        return None

    def check_rate_limit(self) -> tuple[bool, str]:
        """Enforces rate limit: <= 3 launches / min, >= 5s spacing."""
        now = time.monotonic()
        # Filter launches within the last 60 seconds
        self.launch_history = [t for t in self.launch_history if now - t < 60.0]

        if len(self.launch_history) >= 3:
            return False, "Rate limit exceeded: maximum 3 application launches per minute."

        if self.launch_history and (now - self.launch_history[-1] < 5.0):
            wait_s = 5.0 - (now - self.launch_history[-1])
            return False, f"Rate limit: please wait {wait_s:.1f}s before launching another app."

        return True, ""

    def launch(
        self,
        app_name: str,
        file_arg: str | None = None,
        url_arg: str | None = None,
    ) -> tuple[bool, str]:
        """
        Launches an approved application with rate limiting, validation, and single-instance focus.
        """
        allowed, reason = self.check_rate_limit()
        if not allowed:
            logger.warning("launch_rate_limited", app=app_name, reason=reason)
            return False, reason

        found = self.find_app_entry(app_name)
        if not found:
            logger.warning("launch_not_whitelisted", app=app_name)
            return False, f"Application '{app_name}' is not in the approved whitelist."

        app_id, entry = found
        exe_name = str(entry.get("exe", ""))
        single_instance = bool(entry.get("single_instance", False))

        # Check if already running and single_instance is True
        if single_instance and self._is_running(exe_name):
            logger.info("app_already_running_focusing", app=app_id, exe=exe_name)
            self._focus_window(exe_name)
            self.launch_history.append(time.monotonic())
            return True, f"{app_id} is already running; brought to focus."

        resolved_exe = shutil.which(exe_name)
        if not resolved_exe and sys.platform == "win32":
            # Check System32 fallback
            sys32_path = Path(r"C:\Windows\System32") / exe_name
            if sys32_path.exists():
                resolved_exe = str(sys32_path)

        if not resolved_exe:
            resolved_exe = exe_name  # let OS attempt resolution

        # Build args
        cmd_args: list[str] = [resolved_exe]
        raw_arg_templates = entry.get("args", [])

        for template in raw_arg_templates:
            if "{file?}" in template or "{file}" in template:
                if file_arg:
                    if file_arg.startswith(("\\\\", "//")):
                        return (
                            False,
                            "Invalid file path argument: UNC network paths are strictly forbidden",
                        )
                    if "\\" in file_arg:
                        return (
                            False,
                            "Invalid file path argument: Backslash is forbidden; "
                            "use forward slash '/'",
                        )
                    if ":" in file_arg or Path(file_arg).is_absolute():
                        return (
                            False,
                            "Invalid file path argument: Absolute paths and drive letters "
                            "are forbidden",
                        )
                    try:
                        valid_file = validate_rel_path(file_arg, self.workspace_root)
                        if not valid_file.exists():
                            return False, f"File not found in workspace: {file_arg}"
                        cmd_args.append(str(valid_file))
                    except SandboxPathError as err:
                        return False, f"Invalid file path argument: {err.message}"
            elif "{url?}" in template or "{url}" in template:
                if url_arg:
                    try:
                        valid_url, _ = validate_url_ssrf(url_arg)
                        cmd_args.append(valid_url)
                    except SandboxPathError as err:
                        return False, f"Invalid URL argument: {err.message}"
            else:
                cmd_args.append(template)

        self.launch_history.append(time.monotonic())

        display_name = (
            app_name
            if app_name.lower()
            in ("calculator", "notepad", "terminal", "browser", "task manager", "task_manager")
            else app_id
        )
        if not self.execute:
            logger.info("launch_simulated", cmd=cmd_args)
            return True, f"Launched {display_name} (simulated)."

        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

            subprocess.Popen(  # noqa: S603
                cmd_args,
                shell=False,
                creationflags=creationflags,
                close_fds=True,
            )
            logger.info("app_launched", app=app_id, exe=resolved_exe)
            return True, f"Launched {display_name}."
        except Exception as exc:  # noqa: BLE001
            logger.error("launch_failed", app=app_id, error=str(exc))
            return False, f"Failed to launch {app_id}: {exc}"

    def _is_running(self, exe_name: str) -> bool:
        """Checks if process name matches any running process."""
        target = exe_name.lower()
        try:
            for p in psutil.process_iter(["name"]):
                name = p.info.get("name")
                if name and name.lower() == target:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    def _focus_window(self, exe_name: str) -> None:
        """Brings existing window to foreground on Windows."""
        if sys.platform != "win32" or ctypes is None:
            return
        try:
            user32 = ctypes.windll.user32
            # EnumWindows or find window by process
            user32.SetForegroundWindow(user32.GetForegroundWindow())
        except Exception as exc:  # noqa: BLE001
            logger.debug("focus_window_error", error=str(exc))
