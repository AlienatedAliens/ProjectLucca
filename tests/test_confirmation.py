"""
Project Lucca — Tool Confirmation & Barge-in Tests
Spec 01 §6, Spec 09 §7, Spec 10, T-BRG-05
"""

import time
from pathlib import Path

import numpy as np
import pytest

from lucca.core.ipc_schemas import PTTReleasedPayload
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Done, LLMUsage, ToolCall, ToolCallEnd
from lucca.sandbox.policy import parse_confirmation_response
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


def test_parse_confirmation_response():
    """Verify regex matcher for confirmation and cancellation phrases."""
    positives = [
        "yes",
        "YES",
        "yeah",
        "yep",
        "do it",
        "Do it please",
        "go ahead",
        "confirm",
        "sure",
        "proceed",
        "ok",
        "okay",
    ]
    for p in positives:
        assert parse_confirmation_response(p) == "confirm", f"Failed for {p}"

    negatives = [
        "no",
        "NO",
        "nope",
        "cancel",
        "stop",
        "don't",
        "dont do it",
        "nevermind",
        "abort",
    ]
    for n in negatives:
        assert parse_confirmation_response(n) == "cancel", f"Failed for {n}"

    unknowns = [
        "what time is it",
        "hello there",
        "play some music",
        "",
        "   ",
    ]
    for u in unknowns:
        assert parse_confirmation_response(u) == "unknown", f"Failed for {u}"


@pytest.fixture
def test_orch(tmp_path: Path):
    ws = tmp_path / "orch_ws"
    ws.mkdir()
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    orch.sandbox.workspace_mgr.workspace_root = ws
    orch.sandbox.file_tool.workspace_root = ws
    orch.sandbox.launcher.workspace_root = ws
    orch.sandbox.launcher.execute = False  # Dry-run launcher
    yield orch
    orch.stop()
    orch.cap_ring.close()
    orch.cap_ring.unlink()
    orch.play_ring.close()
    orch.play_ring.unlink()


def test_confirm_flow_accepted_via_click(test_orch: Orchestrator):
    """Confirm flow: Tool requiring confirmation pauses in confirm_wait; accepted via click executes."""
    call = ToolCall(tool="launch_app", args={"app_name": "calculator"}, call_id="call-c1")
    script = [
        ToolCallEnd(call=call),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
    ]
    test_orch.llm = FakeLLM(script=script)

    # Start turn
    test_orch._on_ptt_pressed(ts_ns=1000)
    dummy_pcm = np.ones(16000, dtype=np.int16) * 1000
    test_orch.cap_ring.write(dummy_pcm)

    payload = PTTReleasedPayload(
        t_ns=2000,
        capture_seq_start=0,
        capture_seq_end=16000,
        duration_ms=1000.0,
        vad_speech_ms=900.0,
    )
    test_orch._on_ptt_released(ts_ns=2000, p=payload)

    # Give turn thread time to hit confirm_wait
    for _ in range(50):
        if test_orch.state == "confirm_wait":
            break
        time.sleep(0.02)

    assert test_orch.state == "confirm_wait"
    assert test_orch._pending_confirmation_active is True

    # User clicks Confirm in UI
    test_orch.confirm_action(accepted=True, via="click")

    # Turn thread should finish
    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=2.0)

    assert test_orch.state == "idle"
    # Verify tool was executed
    assert len(test_orch.executed_tools) == 1
    assert test_orch.executed_tools[0][0] == "launch_app"


def test_confirm_flow_rejected_via_click(test_orch: Orchestrator, tmp_path: Path):
    """Confirm flow: Tool requiring confirmation cancelled via UI click -> tool NOT executed."""
    target_file = tmp_path / "orch_ws" / "secret.txt"
    call = ToolCall(
        tool="write_file",
        args={"path": "secret.txt", "content": "data"},
        call_id="call-c2",
    )
    script = [
        ToolCallEnd(call=call),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
    ]
    test_orch.llm = FakeLLM(script=script)

    test_orch._on_ptt_pressed(ts_ns=1000)
    dummy_pcm = np.ones(16000, dtype=np.int16) * 1000
    test_orch.cap_ring.write(dummy_pcm)

    payload = PTTReleasedPayload(
        t_ns=2000,
        capture_seq_start=0,
        capture_seq_end=16000,
        duration_ms=1000.0,
        vad_speech_ms=900.0,
    )
    test_orch._on_ptt_released(ts_ns=2000, p=payload)

    for _ in range(50):
        if test_orch.state == "confirm_wait":
            break
        time.sleep(0.02)

    assert test_orch.state == "confirm_wait"
    assert test_orch._pending_confirmation_active is True

    # User clicks Cancel
    test_orch.confirm_action(accepted=False, via="click")

    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=2.0)

    assert test_orch.state == "idle"
    # Assert file was NOT created
    assert not target_file.exists()


def test_t_brg_05_barge_in_during_confirm_wait_cancels(test_orch: Orchestrator, tmp_path: Path):
    """T-BRG-05: Barge-in during CONFIRM_WAIT cancels the pending action (nothing executed)."""
    target_file = tmp_path / "orch_ws" / "barge.txt"
    call = ToolCall(
        tool="write_file",
        args={"path": "barge.txt", "content": "should_not_exist"},
        call_id="call-c3",
    )
    script = [
        ToolCallEnd(call=call),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
    ]
    test_orch.llm = FakeLLM(script=script)

    test_orch._on_ptt_pressed(ts_ns=1000)
    dummy_pcm = np.ones(16000, dtype=np.int16) * 1000
    test_orch.cap_ring.write(dummy_pcm)

    payload = PTTReleasedPayload(
        t_ns=2000,
        capture_seq_start=0,
        capture_seq_end=16000,
        duration_ms=1000.0,
        vad_speech_ms=900.0,
    )
    test_orch._on_ptt_released(ts_ns=2000, p=payload)

    for _ in range(50):
        if test_orch.state == "confirm_wait":
            break
        time.sleep(0.02)

    assert test_orch.state == "confirm_wait"

    # User presses PTT again (barge in during confirm_wait)
    test_orch._on_ptt_pressed(ts_ns=3000)
    assert test_orch.state == "listening"

    # User releases PTT with empty / unrecognized audio (not "yes")
    # Release PTT
    p_barge = PTTReleasedPayload(
        t_ns=4000,
        capture_seq_start=0,
        capture_seq_end=100,
        duration_ms=10.0,
        vad_speech_ms=0.0,
    )
    test_orch._on_ptt_released(ts_ns=4000, p=p_barge)

    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=2.0)

    # File must NOT have been written
    assert not target_file.exists()
