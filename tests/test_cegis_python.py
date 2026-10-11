"""
Tests for Python CEGIS Autonomous Self-Repair Engine (WO-35 Milestone 35.1)
"""

from __future__ import annotations

import pytest

from lucca.reasoning.cegis_python import (
    CEGISResult,
    CEGISTrace,
    PythonCEGISEngine,
    parse_python_exception,
)


def test_parse_python_exception_standard() -> None:
    stderr = (
        'Traceback (most recent call last):\n'
        '  File "<string>", line 4, in <module>\n'
        'IndexError: list index out of range\n'
    )
    err_type, err_msg = parse_python_exception(stderr)
    assert err_type == "IndexError"
    assert err_msg == "list index out of range"


def test_parse_python_exception_assertion() -> None:
    stderr = (
        'Traceback (most recent call last):\n'
        '  File "<string>", line 10, in <module>\n'
        'AssertionError: Expected 5, got 6\n'
    )
    err_type, err_msg = parse_python_exception(stderr)
    assert err_type == "AssertionError"
    assert err_msg == "Expected 5, got 6"


def test_parse_python_exception_empty() -> None:
    err_type, err_msg = parse_python_exception("")
    assert err_type is None
    assert err_msg is None


def test_cegis_result_dataclass() -> None:
    trace = CEGISTrace(
        turn=1,
        code="print('Hello')",
        ok_exec=True,
        stdout="Hello",
        stderr="",
        error_type=None,
        error_message=None,
        elapsed_ms=12.5,
    )
    res = CEGISResult(
        success=True,
        final_code="print('Hello')",
        predicted_output="Hello",
        turns_taken=1,
        method="VERIFIED_PROGRAM",
        failure_stage=None,
        traces=[trace],
        total_elapsed_ms=12.5,
    )
    assert res.success is True
    assert res.predicted_output == "Hello"
    assert res.turns_taken == 1
    assert len(res.traces) == 1


def test_cegis_engine_mocked_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests multi-turn self-repair where Turn 1 fails and Turn 2 succeeds."""
    engine = PythonCEGISEngine(max_turns=3)

    # Mock _query_llm: Turn 1 produces buggy code, Turn 2 produces repaired code
    call_count = 0

    def mock_query(messages: list[dict[str, str]], temperature: float = 0.1, max_tokens: int = 512) -> tuple[str, str]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Buggy code: out of range index
            return "```python\nx = [1, 2]\nprint(x[5])\n```", "stop"
        else:
            # Repaired code: valid index
            return "```python\nx = [1, 2]\nprint(x[1])\n```", "stop"

    # Mock _execute_code
    exec_count = 0

    def mock_exec(code: str) -> tuple[bool, str, str]:
        nonlocal exec_count
        exec_count += 1
        if "5" in code:
            return False, "", "Traceback (most recent call last):\nIndexError: list index out of range\n"
        elif "1" in code:
            return True, "2", ""
        return False, "", "Unknown error"

    monkeypatch.setattr(engine, "_query_llm", mock_query)
    monkeypatch.setattr(engine, "_execute_code", mock_exec)

    res = engine.synthesize_and_repair("Get second element")
    assert res.success is True
    assert res.turns_taken == 2
    assert res.method == "VERIFIED_REPAIRED_PROGRAM"
    assert res.predicted_output == "2"
    assert len(res.traces) == 2
    assert res.traces[0].ok_exec is False
    assert res.traces[0].error_type == "IndexError"
    assert res.traces[1].ok_exec is True
