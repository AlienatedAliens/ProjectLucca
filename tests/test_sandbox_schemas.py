"""
Tests for Proposal F / D-SEC-04: Sandbox Pydantic Schemas and Argument Validation.
"""

from lucca.sandbox.file_tool import SafeFileTool
from lucca.sandbox.rpc import DockerRPCTransport
from lucca.sandbox.service import SandboxService


def test_rpc_direct_fallback_invalid_args_rejected(tmp_path) -> None:
    transport = DockerRPCTransport(
        use_direct_fallback=True,
        fallback_file_tool=SafeFileTool(workspace_root=tmp_path),
    )
    # read_file requires path (min_length=1)
    res = transport._execute_direct(
        call_id="test-1",
        tool="read_file",
        args={"path": ""},
        t0=0.0,
    )
    assert not res.ok
    assert res.exit_code == -1
    assert "invalid_arguments" in res.stderr


def test_service_launch_app_invalid_args_rejected() -> None:
    service = SandboxService()
    # launch_app requires app_name with min_length=1
    res = service.execute_tool(
        call_id="test-2",
        tool_name="launch_app",
        args={"app_name": ""},
        confirmed=True,
    )
    assert not res.ok
    assert res.exit_code == -1
    assert "invalid_arguments" in res.stderr
