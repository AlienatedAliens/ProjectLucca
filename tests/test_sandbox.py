"""
Project Lucca — Hardened Sandbox File Tool Tests
Spec 09 §9 (T-SBX-01, T-SBX-02, T-SBX-03, P-03)
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from lucca.core.exceptions import SandboxPathError
from lucca.sandbox.container_spec import (
    get_file_sandbox_run_args,
    get_web_sandbox_run_args,
)
from lucca.sandbox.file_tool import SafeFileTool, validate_rel_path
from lucca.sandbox.launcher import AppLauncher
from lucca.sandbox.policy import SequenceGuard
from lucca.sandbox.rpc import DockerRPCTransport
from lucca.sandbox.web_tool import validate_url_ssrf
from lucca.sandbox.workspace import WorkspaceManager


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "sandbox_workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def file_tool(workspace: Path) -> SafeFileTool:
    return SafeFileTool(workspace_root=workspace)


def test_t_sbx_01_malicious_path_fixtures(workspace: Path):
    """T-SBX-01: Malicious paths raise SandboxPathError with correct code; benign paths pass."""
    malicious = [
        ("../escape.txt", "traversal"),
        ("../../etc/passwd", "traversal"),
        ("/absolute/path", "traversal"),
        ("subdir/../../escape", "traversal"),
        ("~/.bashrc", "traversal"),
        ("~/notes.txt", "traversal"),
        ("file..%2f..%2fetc", "invalid_chars"),  # % is rejected
        ("hello%20world.txt", "invalid_chars"),  # % is rejected
        ("win\\path\\test", "invalid_chars"),  # backslash rejected
        ("nul", "reserved"),  # Windows reserved device
        ("nul.txt", "reserved"),
        ("CON", "reserved"),
        ("com1.dat", "reserved"),
        ("aux.json", "reserved"),
        ("file\x00name.txt", "invalid_chars"),  # NUL byte
        ("a" * 1025, "too_long"),  # > 1024 chars
        ("dir//file.txt", "invalid_chars"),  # consecutive slashes
        ("", "invalid_chars"),  # empty string
    ]

    for path_str, expected_code in malicious:
        with pytest.raises(SandboxPathError) as exc_info:
            validate_rel_path(path_str, workspace_root=workspace)
        assert exc_info.value.code == expected_code, (
            f"Failed for {path_str}: got {exc_info.value.code}, expected {expected_code}"
        )

    # Benign paths pass
    benign = [
        "file.txt",
        "notes/todo.md",
        "deep/nested/directory/file.py",
        "project-name_v1.0.tar.gz",
        "UPPERCASE_FILE.TXT",
    ]
    for p in benign:
        target = validate_rel_path(p, workspace_root=workspace)
        assert target.is_relative_to(workspace)


def test_t_sbx_03_read_file_truncation_and_binary(file_tool: SafeFileTool, workspace: Path):
    """T-SBX-03: read_file 300 KiB -> truncated flag, 256 KiB content; binary -> is_binary."""
    # 1. 300 KiB file
    large_file = workspace / "large.txt"
    chunk = b"A" * 1024
    large_file.write_bytes(chunk * 300)

    structured, content = file_tool.read_file("large.txt")
    assert structured["truncated"] is True
    assert len(content.encode("utf-8")) == 262144
    assert structured["size"] == 300 * 1024

    # 2. Binary file sniff
    bin_file = workspace / "binary.dat"
    bin_file.write_bytes(b"hello world\x00more data")
    with pytest.raises(SandboxPathError) as exc:
        file_tool.read_file("binary.dat")
    assert exc.value.code == "is_binary"


def test_file_write_create_mode_and_delete(file_tool: SafeFileTool, workspace: Path):
    """Test file creation, overwrite, append, and deletion."""
    # Create mode
    res = file_tool.write_file("test.txt", "Initial content", mode="create")
    assert isinstance(res["size"], int) and res["size"] > 0
    assert (workspace / "test.txt").read_text() == "Initial content"

    # Create mode when file already exists -> traversal/exists error
    with pytest.raises(SandboxPathError):
        file_tool.write_file("test.txt", "New content", mode="create")

    # Overwrite mode
    file_tool.write_file("test.txt", "Updated", mode="overwrite")
    assert (workspace / "test.txt").read_text() == "Updated"

    # Append mode
    file_tool.write_file("test.txt", " appended", mode="append")
    assert (workspace / "test.txt").read_text() == "Updated appended"

    # Delete
    del_res = file_tool.delete_file("test.txt")
    assert del_res["deleted"] is True
    assert not (workspace / "test.txt").exists()


@given(st.text())
@settings(
    max_examples=100, deadline=1000, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_p_03_validate_rel_path_fuzz(workspace: Path, s: str):
    """P-03: Any string -> resolves under /workspace or raises SandboxPathError; never other exception."""
    try:
        resolved = validate_rel_path(s, workspace_root=workspace)
        assert resolved.is_relative_to(workspace)
    except SandboxPathError:
        pass
    except Exception as e:
        pytest.fail(f"Unexpected exception {type(e).__name__}: {e} for input {s!r}")


def test_t_sbx_search_text(file_tool: SafeFileTool, workspace: Path):
    """Test text search in sandbox workspace."""
    (workspace / "doc1.txt").write_text("Lucca is a desktop companion agent.")
    sub = workspace / "sub"
    sub.mkdir()
    (sub / "code.py").write_text("# Project Lucca core\ndef hello(): pass")
    (workspace / "empty.txt").write_text("Nothing relevant here.")

    # Search for 'lucca' (case-insensitive)
    structured, content = file_tool.search_text(pattern="lucca")
    assert len(structured["hits"]) == 2
    assert "doc1.txt" in content
    assert "code.py" in content

    # Search for non-existent pattern
    structured_empty, _ = file_tool.search_text(pattern="nonexistent_xyz")
    assert len(structured_empty["hits"]) == 0


def test_t_sbx_04_run_python_security(file_tool: SafeFileTool):
    """T-SBX-04: Python execution disabled on host pending Milestone 2 container isolation."""
    res, out = file_tool.run_python("print('sandbox test ok')")
    assert res["ok"] is False
    assert res["exit_code"] == -1
    assert "policy_violation" in res["stderr"]
    assert "disabled on host" in out


def test_t_sbx_13_ssrf_blocking():
    """T-SBX-13: SSRF protection blocks private, loopback, link-local, and IPv6 URLs."""
    blocked_urls = [
        "http://127.0.0.1:8080/metrics",
        "http://127.0.1.1/",
        "http://localhost:3000",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/admin",
        "http://172.16.0.1/",
        "http://192.168.1.1/router",
        "http://[::1]/secret",
        "ftp://example.com/file",
        "file:///etc/passwd",
    ]
    for url in blocked_urls:
        with pytest.raises((SandboxPathError, ValueError)):
            validate_url_ssrf(url)

    # Max length limits
    long_url = "https://example.com/" + ("a" * 513)
    with pytest.raises((SandboxPathError, ValueError)):
        validate_url_ssrf(long_url)

    long_query = "https://example.com/search?q=" + ("b" * 130)
    with pytest.raises((SandboxPathError, ValueError)):
        validate_url_ssrf(long_query)

    # Allowed public URL
    normalized, _ip = validate_url_ssrf("https://example.com/valid?query=test")
    assert normalized.startswith("https://example.com/valid")


def test_t_sbx_14_launcher_whitelist_and_rate_limits(workspace: Path):
    """T-SBX-14: Whitelist matching, non-whitelisted rejection, and launch rate limiting."""
    launcher = AppLauncher(workspace_root=workspace, execute=False)

    # 1. Non-whitelisted app rejected
    ok, msg = launcher.launch("cmd")
    assert not ok
    assert "whitelist" in msg.lower()

    ok, msg = launcher.launch("powershell")
    assert not ok
    assert "whitelist" in msg.lower()

    # 2. Whitelisted app succeeds
    ok, msg = launcher.launch("calculator")
    assert ok
    assert "calculator" in msg.lower()

    # 3. Spacing limit: second launch within 5s is rate-limited
    ok, msg = launcher.launch("notepad")
    assert not ok
    assert "rate limit" in msg.lower() or "spacing" in msg.lower()


def test_t_sbx_19_sequence_guard():
    """T-SBX-19: Forbidden sequences (read_file -> fetch_url) and (fetch_url -> write_file) blocked."""
    guard = SequenceGuard()

    # (read_file -> fetch_url) blocked
    allowed, _ = guard.check_and_record("read_file")
    assert allowed is True
    allowed, reason = guard.check_and_record("fetch_url")
    assert allowed is False
    assert "Forbidden sequence" in reason

    # Turn reset clears history
    guard.reset()
    # (fetch_url -> write_file) blocked
    allowed, _ = guard.check_and_record("fetch_url")
    assert allowed is True
    allowed, reason = guard.check_and_record("write_file")
    assert allowed is False
    assert "Forbidden sequence" in reason

    # Permitted sequences
    guard.reset()
    assert guard.check_and_record("list_dir")[0] is True
    assert guard.check_and_record("read_file")[0] is True
    assert guard.check_and_record("search_text")[0] is True


def test_t_sbx_05_workspace_cleanup(workspace: Path):
    """T-SBX-05: Task close/reset wipes workspace entries."""
    mgr = WorkspaceManager(workspace_root=workspace)

    # Populate workspace
    (workspace / "file1.txt").write_text("data 1")
    (workspace / "file2.txt").write_text("data 2")
    sub = workspace / "nested"
    sub.mkdir()
    (sub / "subfile.txt").write_text("sub data")

    assert mgr.get_total_size() > 0

    # Reset workspace
    mgr.reset_workspace()

    # Workspace directory exists and is empty
    assert workspace.exists()
    assert list(workspace.iterdir()) == []


def test_t_sbx_17_container_spec_snapshot():
    """T-SBX-17: Container spec snapshot tests."""
    file_args = get_file_sandbox_run_args(workspace_path=r"C:\test\ws")
    assert "--network" in file_args
    assert file_args[file_args.index("--network") + 1] == "none"
    assert "--cap-drop=ALL" in file_args
    assert "--security-opt=no-new-privileges" in file_args
    assert "--gpus" not in file_args
    assert "--privileged" not in file_args

    web_args = get_web_sandbox_run_args(call_id="call-test-123")
    assert "--network" in web_args
    assert web_args[web_args.index("--network") + 1] == "lucca-net"
    assert "--read-only" in web_args
    assert "--cap-drop=ALL" in web_args
    assert not any("--mount" in a for a in web_args)
    assert not any(a == "-v" for a in web_args)


def test_t_sbx_16_host_sha256_audit(workspace: Path, file_tool: SafeFileTool):
    """T-SBX-16: Host recomputes sha256 of read_file content; mismatch => ok=False, audit."""
    transport = DockerRPCTransport(
        use_direct_fallback=True,
        fallback_file_tool=file_tool,
    )
    (workspace / "audit.txt").write_text("authentic content")

    # 1. Authentic read succeeds
    res = transport.execute("call-1", "read_file", {"path": "audit.txt"})
    assert res.ok is True
    assert res.content == "authentic content"
    assert res.structured is not None
    assert res.structured["sha256"] == hashlib.sha256(b"authentic content").hexdigest()

    # 2. Tampered response from container triggers audit failure
    mock_transport = DockerRPCTransport(use_direct_fallback=False)
    fake_stdout = json.dumps(
        {
            "call_id": "call-2",
            "ok": True,
            "exit_code": 0,
            "structured": {
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
            },
            "content": "tampered content",
            "content_truncated": False,
        }
    )
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (fake_stdout, "")
    mock_proc.returncode = 0

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mock_transport, "is_docker_available", lambda: True)
        mp.setattr(mock_transport, "is_container_running", lambda: True)
        mp.setattr("subprocess.Popen", lambda *args, **kwargs: mock_proc)
        res_tampered = mock_transport.execute("call-2", "read_file", {"path": "audit.txt"})
        assert res_tampered.ok is False
        assert res_tampered.exit_code == -4
        assert "sha256 mismatch" in res_tampered.stderr


def test_query_capabilities_manifest(workspace: Path) -> None:
    """Verifies that query_capabilities returns full manifest and respects categories."""
    from lucca.core.schemas import Risk
    from lucca.sandbox.policy import classify_risk, requires_confirmation
    from lucca.sandbox.service import SandboxService

    # Check risk classification
    assert classify_risk("query_capabilities") == Risk.READ
    assert requires_confirmation("query_capabilities") is False

    service = SandboxService(workspace_root=workspace, use_direct_fallback=True)

    # 1. Query all
    res = service.execute_tool("call-cap-1", "query_capabilities", {})
    assert res.ok is True
    assert res.exit_code == 0
    assert res.structured is not None
    assert "tools" in res.structured
    assert "fetch_url" in res.structured["tools"]
    assert "reasoning_pathways" in res.structured
    assert "whitelisted_apps" in res.structured
    assert set(res.structured["whitelisted_apps"]) == set(service.launcher.apps.keys())
    assert "hardware_substrates" in res.structured

    # 2. Query category
    res_pathways = service.execute_tool(
        "call-cap-2", "query_capabilities", {"category": "reasoning_pathways"}
    )
    assert res_pathways.ok is True
    assert res_pathways.structured is not None
    assert "reasoning_pathways" in res_pathways.structured
    pathways = res_pathways.structured["reasoning_pathways"]
    assert pathways == {}


def test_fallback_disabled_refuses_host_execution(workspace: Path) -> None:
    """F-SBX-001 / D-AUD-13: Docker unavailable + use_direct_fallback=False -> refusal result, no local execution."""
    from unittest.mock import patch

    from lucca.sandbox.service import SandboxService

    with patch("lucca.sandbox.rpc.DockerRPCTransport.is_docker_available", return_value=False):
        # Explicit use_direct_fallback=False refuses
        service = SandboxService(workspace_root=workspace, use_direct_fallback=False)
        res = service.execute_tool(
            "call-refuse-1",
            "write_file",
            {"path": "test_refuse.txt", "content": "hello"},
            confirmed=True,
        )
        assert res.ok is False
        assert res.exit_code == -2
        assert "sandbox unavailable" in res.stderr
        assert not (workspace / "test_refuse.txt").exists()

        # Default constructor (no args) defaults use_direct_fallback=False and refuses
        default_service = SandboxService(workspace_root=workspace)
        assert default_service.rpc.use_direct_fallback is False
        res2 = default_service.execute_tool(
            "call-refuse-2", "read_file", {"path": "test.txt"}, confirmed=True
        )
        assert res2.ok is False
        assert res2.exit_code == -2
        assert "sandbox unavailable" in res2.stderr


def test_orchestrator_speaks_sandbox_unavailable_notice() -> None:
    """F-SBX-001 / D-AUD-13: Orchestrator speaks honest notice when sandbox refuses."""
    from unittest.mock import MagicMock, patch

    from lucca.core.orchestrator import Orchestrator
    from lucca.core.schemas import ToolResult
    from lucca.core.trace import TurnTrace
    from tests.fakes.fake_tts import FakeTTS

    orch = Orchestrator(tts=FakeTTS, execute_tools=True)
    try:
        orch._request_confirmation = MagicMock(return_value=True)  # type: ignore[method-assign]
        trace = TurnTrace(trace_id="test-trace", start_ns=0)
        with (
            patch.object(orch.sandbox, "execute_tool") as mock_exec,
            patch.object(orch, "_speak_text") as mock_speak,
        ):
            mock_exec.return_value = ToolResult(
                call_id="call-1",
                ok=False,
                exit_code=-2,
                stderr="sandbox unavailable: Docker/WSL not reachable",
                elapsed_ms=1.0,
            )
            orch._handle_tool_call(trace, "write_file", {"path": "test.txt", "content": "hello"})
            mock_speak.assert_called_once_with(
                trace, "My file sandbox isn't available — Docker isn't reachable."
            )
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


def test_orchestrator_speaks_query_capabilities_and_read_tools() -> None:
    """Ensure Orchestrator speaks query_capabilities, read_file, and fetch_url results."""
    from unittest.mock import MagicMock, patch

    from lucca.core.orchestrator import Orchestrator
    from lucca.core.schemas import ToolResult
    from lucca.core.trace import TurnTrace
    from tests.fakes.fake_tts import FakeTTS

    orch = Orchestrator(tts=FakeTTS, execute_tools=True)
    try:
        orch._request_confirmation = MagicMock(return_value=True)  # type: ignore[method-assign]
        trace = TurnTrace(trace_id="test-trace", start_ns=0)

        with (
            patch.object(orch.sandbox, "execute_tool") as mock_exec,
            patch.object(orch, "_speak_text") as mock_speak,
        ):
            # 1. query_capabilities (all / general tour)
            mock_exec.return_value = ToolResult(call_id="c1", ok=True, exit_code=0, elapsed_ms=0.0)
            orch._handle_tool_call(trace, "query_capabilities", {})
            mock_speak.assert_called_with(
                trace,
                "I can launch desktop applications like Calculator, Notepad, and Edge, "
                "read and write files in your workspace, and remember our conversations "
                "with persistent memory.",
            )
            assert len(orch.current_turn_tool_spoken) == 1

            # 2. query_capabilities (applications)
            orch._handle_tool_call(trace, "query_capabilities", {"category": "applications"})
            mock_speak.assert_called_with(
                trace,
                "I can launch desktop applications including Calculator, Notepad, and Edge.",
            )

            # 3. read_file
            mock_exec.return_value = ToolResult(
                call_id="c2", ok=True, exit_code=0, content="Sample file content", elapsed_ms=0.0
            )
            orch._handle_tool_call(trace, "read_file", {"path": "sample.txt"})
            mock_speak.assert_called_with(
                trace, "Here is what's in sample.txt: Sample file content"
            )

            # 4. fetch_url
            mock_exec.return_value = ToolResult(
                call_id="c3", ok=True, exit_code=0, content="Web content", elapsed_ms=0.0
            )
            orch._handle_tool_call(trace, "fetch_url", {"url": "https://example.com"})
            mock_speak.assert_called_with(trace, "I fetched https://example.com.")
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


def test_tool_only_turn_records_history() -> None:
    """F-CORE-015: Ensure turns with pure tool calls record spoken response into history."""
    from unittest.mock import MagicMock

    from lucca.core.orchestrator import Orchestrator
    from lucca.core.schemas import Done, LLMUsage, ToolCall, ToolCallEnd
    from tests.fakes.fake_llm import FakeLLM
    from tests.fakes.fake_tts import FakeTTS

    script = [
        ToolCallEnd(call=ToolCall(tool="query_capabilities", args={}, call_id="c-1")),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=10)),
    ]
    fake_llm = FakeLLM(script=script)
    orch = Orchestrator(tts=FakeTTS, llm=fake_llm, execute_tools=True)
    try:
        orch._request_confirmation = MagicMock(return_value=True)  # type: ignore[method-assign]
        orch._on_user_text(ts_ns=1000, user_text="Give me the tour")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=5.0)

        assert len(orch.history) == 2
        assert orch.history[0]["role"] == "user"
        assert orch.history[0]["content"] == "Give me the tour"
        assert orch.history[1]["role"] == "assistant"
        assert "I can launch desktop applications" in orch.history[1]["content"]
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


def test_no_hardcoded_project_paths() -> None:
    """F-SBX-012: Ensure no hardcoded project paths exist in src/lucca/sandbox."""
    sandbox_dir = Path(__file__).resolve().parent.parent / "src" / "lucca" / "sandbox"
    forbidden = [
        "C:\\projects\\ProjectLucca",
        "C:/projects/ProjectLucca",
        "C:\\ProjectLucca",
        "C:/ProjectLucca",
    ]
    violations: list[str] = []
    for py_file in sandbox_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for bad in forbidden:
            if bad.lower() in content.lower():
                violations.append(f"{py_file.name}: found {bad}")
    assert not violations, f"Hardcoded project paths found in sandbox: {violations}"


def test_whitelist_load_and_save_enforces_d_aud_10(tmp_path: Path) -> None:
    """Verifies that tool_whitelist.toml loads, saves, and strictly rejects forbidden shells (D-AUD-10)."""
    from lucca.ui.settings_dialog import SettingsDialog, load_whitelist_apps, save_whitelist_apps

    toml_file = tmp_path / "tool_whitelist.toml"
    initial_apps = [
        {
            "key": "calc",
            "name": "Calculator",
            "path": "calc.exe",
            "tier": "Trusted",
            "status": "Active",
        },
        {
            "key": "terminal",
            "name": "Terminal",
            "path": "wt.exe",
            "tier": "Trusted",
            "status": "Active",
        },
    ]
    save_whitelist_apps(initial_apps, config_path=toml_file)

    loaded = load_whitelist_apps(config_path=toml_file)
    assert len(loaded) == 2
    assert loaded[0]["path"] == "calc.exe"
    assert loaded[1]["path"] == "wt.exe"

    # Shell rejection invariant
    for forbidden in ("cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "wsl.exe"):
        assert forbidden in SettingsDialog.FORBIDDEN_SHELLS


def test_search_web_execution_and_guard(workspace: Path) -> None:
    """Verifies that search_web executes via SandboxService and is guarded by SequenceGuard."""
    from unittest.mock import patch
    from lucca.core.schemas import Risk
    from lucca.sandbox.service import SandboxService
    from lucca.sandbox.policy import classify_risk, SequenceGuard

    assert classify_risk("search_web") == Risk.NETWORK

    service = SandboxService(workspace_root=workspace, use_direct_fallback=True)

    fake_html = """
    <div class="result__body">
        <h2 class="result__title"><a href="https://example.com/item">Example Item</a></h2>
        <a class="result__snippet">This is an example snippet text.</a>
        <a class="result__url" href="https://example.com/item">example.com/item</a>
    </div>
    """

    class MockResponse:
        status_code = 200
        text = fake_html

    with patch("httpx.Client.get", return_value=MockResponse()):
        res = service.execute_tool("call-sw-1", "search_web", {"query": "test search", "max_results": 3})
        assert res.ok is True
        assert res.exit_code == 0
        assert res.structured is not None
        assert res.structured["query"] == "test search"
        assert res.structured["results_count"] == 1
        assert "Example Item" in res.content

    # Verify SequenceGuard blocks read_file -> search_web
    guard = SequenceGuard()
    guard.check_and_record("read_file")
    allowed, reason = guard.check_and_record("search_web")
    assert not allowed
    assert "Forbidden sequence" in reason

