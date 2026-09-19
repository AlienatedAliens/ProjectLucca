"""
Project Lucca — Interim Security Verification Suite (Round 4)
Verifies:
1. Complete disabling of host run_python across Service, RPC, and FileTool.
2. Purge of terminal, browser, and task_manager from launcher whitelist and defaults.
3. Strict hardening of notepad file arguments against UNC paths, drive specifiers, ADS, and absolute paths.
4. Blocking of fetch_url(render=True) headless browser rendering.
5. Strict path validation rejects colons, backslashes, UNC, and traversal.
"""

from pathlib import Path
import pytest

from lucca.core.exceptions import SandboxPathError
from lucca.sandbox.file_tool import SafeFileTool, validate_rel_path
from lucca.sandbox.launcher import AppLauncher
from lucca.sandbox.rpc import DockerRPCTransport
from lucca.sandbox.service import SandboxService
from lucca.sandbox.web_tool import fetch_url


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "sandbox_workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def launcher(workspace: Path) -> AppLauncher:
    return AppLauncher(workspace_root=workspace, execute=False)


@pytest.fixture
def file_tool(workspace: Path) -> SafeFileTool:
    return SafeFileTool(workspace_root=workspace)


@pytest.fixture
def service(workspace: Path) -> SandboxService:
    return SandboxService(workspace_root=workspace, use_direct_fallback=True, execute_apps=False)


# ---------------------------------------------------------------------------
# 1. run_python Disabling Tests (Defense in Depth)
# ---------------------------------------------------------------------------

def test_service_level_run_python_hard_blocked(service: SandboxService):
    """SandboxService must immediately intercept and reject run_python with policy error."""
    res = service.execute_tool(
        call_id="call-py-svc-1",
        tool_name="run_python",
        args={"code": "import os; os.system('calc.exe')"},
        confirmed=True,
    )
    assert res.ok is False
    assert res.exit_code == -1
    assert "policy_violation" in res.stderr
    assert "disabled until Milestone 2 container isolation lands" in res.stderr


def test_rpc_level_run_python_hard_blocked(file_tool: SafeFileTool):
    """DockerRPCTransport in direct fallback mode must reject run_python."""
    rpc = DockerRPCTransport(use_direct_fallback=True, fallback_file_tool=file_tool)
    res = rpc.execute(
        call_id="call-py-rpc-1",
        tool="run_python",
        args={"code": "print('malicious execution attempt')"},
    )
    assert res.ok is False
    assert res.exit_code == -1
    assert "policy_violation" in res.stderr
    assert "disabled until Milestone 2 container isolation lands" in res.stderr


def test_file_tool_level_run_python_hard_blocked(file_tool: SafeFileTool):
    """SafeFileTool.run_python must return policy violation and zero execution."""
    res, out = file_tool.run_python("print('direct host execution attempt')")
    assert res["ok"] is False
    assert res["exit_code"] == -1
    assert "policy_violation" in str(res["stderr"])
    assert "disabled on host pending Milestone 2 container isolation" in out


def test_file_tool_run_python_rejects_on_non_container_linux_environment(
    file_tool: SafeFileTool, monkeypatch: pytest.MonkeyPatch
):
    """
    Verifies that SafeFileTool.run_python asserts actual container boundary presence,
    not mere OS identity. Even on Linux / WSL2 / CI host environments, if LUCCA_SANDBOX_CONTAINER
    is not set and the container sentinel is absent, execution must be strictly blocked.
    """
    monkeypatch.delenv("LUCCA_SANDBOX_CONTAINER", raising=False)
    monkeypatch.setattr("sys.platform", "linux")

    res, out = file_tool.run_python("print('unauthorized host execution on linux')")
    assert res["ok"] is False
    assert res["exit_code"] == -1
    assert "policy_violation" in str(res["stderr"])
    assert "disabled on host pending Milestone 2 container isolation" in out


# ---------------------------------------------------------------------------
# 2. Host Launcher Whitelist Purge Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("disallowed_app", [
    "terminal",
    "windows terminal",
    "wt.exe",
    "browser",
    "edge",
    "msedge.exe",
    "task_manager",
    "taskmgr.exe",
    "powershell",
    "cmd",
])
def test_launcher_rejects_removed_and_unapproved_apps(launcher: AppLauncher, disallowed_app: str):
    """Host launcher must strictly refuse any application outside the approved whitelist."""
    ok, msg = launcher.launch(app_name=disallowed_app)
    assert ok is False
    assert "not in the approved whitelist" in msg


def test_launcher_allows_calculator(launcher: AppLauncher):
    """Calculator is on the approved whitelist and succeeds in simulation."""
    ok, msg = launcher.launch(app_name="calculator")
    assert ok is True
    assert "calculator" in msg.lower() or "calc" in msg.lower()


def test_launcher_allows_notepad_with_valid_file(launcher: AppLauncher, workspace: Path):
    """Notepad is permitted when pointing to an existing file inside the workspace."""
    sample_file = workspace / "test_doc.txt"
    sample_file.write_text("hello lucca", encoding="utf-8")

    ok, msg = launcher.launch(app_name="notepad", file_arg="test_doc.txt")
    assert ok is True
    assert "notepad" in msg.lower()


# ---------------------------------------------------------------------------
# 3. Notepad Path Hardening Tests (UNC, Absolute, Colons, Traversal)
# ---------------------------------------------------------------------------

def test_launcher_rejects_unc_backslash_path(launcher: AppLauncher):
    """Reject UNC backslash path (e.g. \\\\evil\\share\\payload.txt)."""
    ok, msg = launcher.launch(app_name="notepad", file_arg=r"\\evil\share\payload.txt")
    assert ok is False
    assert "UNC network paths are strictly forbidden" in msg


def test_launcher_rejects_unc_forward_slash_path(launcher: AppLauncher):
    """Reject UNC forward slash path (e.g. //evil/share/payload.txt)."""
    ok, msg = launcher.launch(app_name="notepad", file_arg="//evil/share/payload.txt")
    assert ok is False
    assert "UNC network paths are strictly forbidden" in msg


def test_launcher_rejects_absolute_windows_path(launcher: AppLauncher):
    """Reject absolute Windows path (e.g. C:\\Windows\\system32\\calc.exe)."""
    ok, msg = launcher.launch(app_name="notepad", file_arg=r"C:\Windows\system32\calc.exe")
    assert ok is False
    assert "Backslash is forbidden" in msg or "Absolute paths" in msg


def test_launcher_rejects_drive_specifier_forward_slash(launcher: AppLauncher):
    """Reject drive specifier with forward slash (e.g. C:/Windows/calc.exe)."""
    ok, msg = launcher.launch(app_name="notepad", file_arg="C:/Windows/calc.exe")
    assert ok is False
    assert "Absolute paths and drive letters are forbidden" in msg


def test_launcher_rejects_path_traversal(launcher: AppLauncher):
    """Reject relative traversal attempting to escape workspace."""
    ok, msg = launcher.launch(app_name="notepad", file_arg="../secret.env")
    assert ok is False
    assert "Path traversal segment '..' is forbidden" in msg or "Invalid file path argument" in msg


# ---------------------------------------------------------------------------
# 4. Web Fetch render=True Disabling Tests
# ---------------------------------------------------------------------------

def test_fetch_url_render_disabled_direct():
    """fetch_url(render=True) must raise SandboxPathError with render_disabled code."""
    with pytest.raises(SandboxPathError) as exc_info:
        fetch_url("https://example.com", render=True)
    assert exc_info.value.code == "render_disabled"
    assert "Headless browser rendering (render=True) is disabled on host" in exc_info.value.message


def test_fetch_url_render_disabled_via_service(service: SandboxService):
    """SandboxService.execute_tool must return ok=False when render=True is supplied."""
    res = service.execute_tool(
        call_id="call-web-render-1",
        tool_name="fetch_url",
        args={"url": "https://example.com", "render": True},
    )
    assert res.ok is False
    assert res.exit_code == 1
    assert "Headless browser rendering (render=True) is disabled on host" in res.stderr


# ---------------------------------------------------------------------------
# 5. Strict Relative Path Validation Hardening Tests
# ---------------------------------------------------------------------------

def test_validate_rel_path_rejects_colons_and_ads(workspace: Path):
    """validate_rel_path must reject colons to prevent drive letters and NTFS ADS streams."""
    with pytest.raises(SandboxPathError) as exc1:
        validate_rel_path("document.txt:secret_stream", workspace)
    assert exc1.value.code == "invalid_chars"
    assert "Colons" in exc1.value.message

    with pytest.raises(SandboxPathError) as exc2:
        validate_rel_path("D:/other/drive/file.txt", workspace)
    assert exc2.value.code == "invalid_chars"
    assert "Colons" in exc2.value.message
