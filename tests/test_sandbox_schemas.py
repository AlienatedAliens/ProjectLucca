"""
Tests for Proposal F / D-SEC-04: Sandbox Pydantic Schemas and Argument Validation.
"""

from unittest.mock import MagicMock

from lucca.ports import ToolResult
from lucca.sandbox.file_tool import SafeFileTool
from lucca.sandbox.rpc import DockerRPCTransport
from lucca.sandbox.schemas import ReadFileArgs, RunPythonArgs
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


def test_run_python_missing_code_rejected() -> None:
    service = SandboxService()
    res = service.execute_tool(
        call_id="test-rp-missing",
        tool_name="run_python",
        args={},
        confirmed=True,
    )
    assert not res.ok
    assert res.exit_code == -1
    assert "invalid_arguments" in res.stderr


def test_run_python_timeout_s_out_of_bounds_rejected() -> None:
    service = SandboxService()
    # Upper bound violation (>60)
    res_high = service.execute_tool(
        call_id="test-rp-high",
        tool_name="run_python",
        args={"code": "1 + 1", "timeout_s": 120},
        confirmed=True,
    )
    assert not res_high.ok
    assert res_high.exit_code == -1
    assert "invalid_arguments" in res_high.stderr

    # Lower bound violation (<1)
    res_low = service.execute_tool(
        call_id="test-rp-low",
        tool_name="run_python",
        args={"code": "1 + 1", "timeout_s": 0},
        confirmed=True,
    )
    assert not res_low.ok
    assert res_low.exit_code == -1
    assert "invalid_arguments" in res_low.stderr


def test_run_python_legacy_timeout_coerced() -> None:
    parsed = RunPythonArgs.model_validate({"code": "print('hello')", "timeout": 25})
    assert parsed.timeout_s == 25
    assert parsed.code == "print('hello')"


def test_run_python_valid_args_reaches_execution() -> None:
    service = SandboxService(use_direct_fallback=False)
    service.rpc.is_docker_available = MagicMock(return_value=True)
    service.rpc.execute = MagicMock(
        return_value=ToolResult(
            call_id="test-rp-ok",
            ok=True,
            exit_code=0,
            content="success",
            elapsed_ms=1.0,
        )
    )

    res = service.execute_tool(
        call_id="test-rp-ok",
        tool_name="run_python",
        args={"code": "x = 42", "timeout_s": 10},
        confirmed=True,
    )
    assert res.ok
    assert service.rpc.execute.called
    called_tool = service.rpc.execute.call_args[1]["tool"]
    called_args = service.rpc.execute.call_args[1]["args"]
    assert called_tool == "run_python"
    assert called_args["code"] == "x = 42"
    assert called_args["timeout_s"] == 10


def test_run_python_async_schema_validation() -> None:
    service = SandboxService()
    res_invalid = service.execute_tool(
        call_id="test-rpa-invalid",
        tool_name="run_python_async",
        args={"code": "x = 1", "max_output_bytes": 9999999},
        confirmed=True,
    )
    assert not res_invalid.ok
    assert res_invalid.exit_code == -1
    assert "invalid_arguments" in res_invalid.stderr


def test_unregistered_tool_rejected_fail_closed() -> None:
    service = SandboxService()
    res = service.execute_tool(
        call_id="test-unregistered",
        tool_name="totally_unknown_tool_name_xyz",
        args={"param": "value"},
        confirmed=True,
    )
    assert not res.ok
    assert res.exit_code == -1
    assert res.stderr == "schema_not_registered"


def test_service_validation_with_pydantic_model_instance(tmp_path) -> None:
    (tmp_path / "hello.txt").write_text("world", encoding="utf-8")
    service = SandboxService(workspace_root=tmp_path, use_direct_fallback=True)
    res = service.execute_tool(
        call_id="test-model-arg",
        tool_name="read_file",
        args=ReadFileArgs(path="hello.txt"),
        confirmed=True,
    )
    assert res.ok
    assert res.content == "world"


def test_orchestrator_invoke_skill_validation() -> None:
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.trace import TurnTrace
    from tests.fakes.fake_asr import FakeASR
    from tests.fakes.fake_tts import FakeTTS

    orchestrator = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    try:
        trace = TurnTrace(trace_id="test-invoke-schema-trace", t_capture_start=0)
        # Missing skill_id should be rejected with invalid_arguments
        res = orchestrator._handle_tool_call(
            trace=trace,
            name="invoke_skill",
            args={},
            speak=False,
        )
        assert res is not None
        assert res.ok is False
        assert res.exit_code == -1
        assert "invalid_arguments" in res.stderr
        assert orchestrator.current_turn_tool_ok is False
    finally:
        orchestrator.stop()
        orchestrator.cap_ring.close()
        orchestrator.cap_ring.unlink()
        orchestrator.play_ring.close()
        orchestrator.play_ring.unlink()
