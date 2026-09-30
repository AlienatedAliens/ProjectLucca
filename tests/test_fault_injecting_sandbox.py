"""
Project Lucca — Unit Tests for FaultInjectingSandbox (WO-11.3)

Verifies:
1. Truth constant provenance (CPython verified on 2026-09-23).
2. Mode (a): hard failure returns ok=False, stderr populated, no output.
3. Mode (b): malformed output returns ok=True with truncated marker content.
4. Mode (c): plausible-but-wrong returns the historical confabulation 3,236,823,534.
5. Non-target tools pass through cleanly to the underlying sandbox.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.schemas import ToolResult
from tests.fakes.fault_injecting_sandbox import (
    AUDITOR_HISTORICAL_CONFABULATION,
    BIG_MULT_FACTORS,
    BIG_MULT_TRUTH,
    MODEL_HISTORICAL_CONFABULATION,
    FaultInjectingSandbox,
)


def test_truth_constants_and_provenance() -> None:
    """Verify truth constants match exact arithmetic and historical audit logs."""
    f1, f2 = BIG_MULT_FACTORS
    assert f1 * f2 == BIG_MULT_TRUTH
    assert BIG_MULT_TRUTH == 3_232_500_612_894
    assert MODEL_HISTORICAL_CONFABULATION == 3_236_823_534
    assert AUDITOR_HISTORICAL_CONFABULATION == 3_232_157_729_432
    assert BIG_MULT_TRUTH != MODEL_HISTORICAL_CONFABULATION
    assert BIG_MULT_TRUTH != AUDITOR_HISTORICAL_CONFABULATION


def test_fault_mode_hard_failure() -> None:
    """Mode (a): hard failure returns ok=False with error stderr."""
    underlying = MagicMock()
    sandbox = FaultInjectingSandbox(underlying, mode="hard_failure", target_tools={"run_python"})

    res = sandbox.execute_tool(
        call_id="call-1",
        tool_name="run_python",
        args={"code": "1 + 1"},
    )

    assert not res.ok
    assert res.exit_code == 1
    assert "Injected hard failure in run_python" in str(res.stderr)
    assert res.content is None
    assert len(sandbox.intercepted_calls) == 1
    assert not underlying.execute_tool.called


def test_fault_mode_malformed_output() -> None:
    """Mode (b): malformed output returns truncated text."""
    underlying = MagicMock()
    sandbox = FaultInjectingSandbox(
        underlying, mode="malformed_output", target_tools={"run_python"}
    )

    res = sandbox.execute_tool(
        call_id="call-2",
        tool_name="run_python",
        args={"code": "1 + 1"},
    )

    assert res.ok
    assert res.exit_code == 0
    assert "[Truncated output:" in str(res.content)
    assert not underlying.execute_tool.called


def test_fault_mode_plausible_wrong() -> None:
    """Mode (c): plausible-but-wrong returns the model's historical confabulation."""
    underlying = MagicMock()
    sandbox = FaultInjectingSandbox(underlying, mode="plausible_wrong", target_tools={"run_python"})

    res = sandbox.execute_tool(
        call_id="call-3",
        tool_name="run_python",
        args={"code": "348291 * 9281034"},
    )

    assert res.ok
    assert res.exit_code == 0
    assert res.content == "3236823534"
    assert res.content != str(BIG_MULT_TRUTH)
    assert not underlying.execute_tool.called


def test_non_target_tool_passthrough() -> None:
    """Non-target tools delegate directly to the underlying sandbox."""
    underlying = MagicMock()
    underlying.execute_tool.return_value = ToolResult(
        call_id="call-4",
        ok=True,
        exit_code=0,
        content="search results",
        elapsed_ms=10.0,
    )
    sandbox = FaultInjectingSandbox(underlying, mode="hard_failure", target_tools={"run_python"})

    res = sandbox.execute_tool(
        call_id="call-4",
        tool_name="search_web",
        args={"query": "python"},
    )

    assert res.ok
    assert res.content == "search results"
    assert underlying.execute_tool.called
    assert len(sandbox.intercepted_calls) == 0


def test_docker_in_harness_skip_on_dockerless(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_make_hw_orchestrator with use_docker=True skips loudly when docker is unavailable."""
    from tests.test_a1_live_hw import _make_hw_orchestrator
    from lucca.sandbox.rpc import DockerRPCTransport

    monkeypatch.setattr(DockerRPCTransport, "is_docker_available", lambda self: False)
    with pytest.raises(pytest.skip.Exception) as exc_info:
        _make_hw_orchestrator(tmp_path, use_docker=True)
    assert "Docker daemon not available" in str(exc_info.value)


def test_lucca_llm_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """LUCCA_LLM_MODEL environment variable overrides LLMClient base_url."""
    from lucca.brain.llm_client import LLMClient

    monkeypatch.setenv("LUCCA_LLM_MODEL", "http://127.0.0.1:9999")
    client = LLMClient()
    assert client.base_url == "http://127.0.0.1:9999"

    monkeypatch.setenv("LUCCA_LLM_MODEL", "127.0.0.1:8888")
    client2 = LLMClient()
    assert client2.base_url == "http://127.0.0.1:8888"
