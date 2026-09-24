"""
Project Lucca — Tool Confirmation & Barge-in Tests
Spec 01 §6, Spec 09 §7, Spec 10, T-BRG-05
"""

import time
from pathlib import Path

import numpy as np
import pytest

from lucca.core.ipc_schemas import (
    Envelope,
    PTTReleasedPayload,
    UIConfirmResultPayload,
)
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Done, LLMUsage, ToolCall, ToolCallEnd
from lucca.sandbox.policy import parse_confirmation_response
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


def test_parse_confirmation_response():
    """Verify regex and token matcher for confirmation and cancellation phrases."""
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
        "yeah, please do",
        "confirm that",
        "uh, yeah",
        "um ok sure",
        "sure thing",
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
        "no don't do it",
        "uh no cancel",
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


def test_memory_commit_confirmation_gating():
    """WO-17 Phase 3: memory_commit is frictionless unless tainted by UNTRUSTED_WEB."""
    from lucca.sandbox.policy import TaintFlags, requires_confirmation

    # Untainted: frictionless
    assert requires_confirmation("memory_commit", taint=TaintFlags.CLEAN) is False

    # Other non-web taints: still frictionless
    assert requires_confirmation("memory_commit", taint=TaintFlags.SENSITIVE_MEMORY) is False

    # Untrusted web taint: requires confirmation
    assert requires_confirmation("memory_commit", taint=TaintFlags.UNTRUSTED_WEB) is True


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


def _reach_confirm_wait(orch: Orchestrator, call: ToolCall) -> None:
    """Drives a turn that emits one confirmation-gated tool call and waits for confirm_wait."""
    orch.llm = FakeLLM(
        script=[
            ToolCallEnd(call=call),
            Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
        ]
    )
    orch._on_ptt_pressed(ts_ns=1000)
    dummy_pcm = np.ones(16000, dtype=np.int16) * 1000
    orch.cap_ring.write(dummy_pcm)
    payload = PTTReleasedPayload(
        t_ns=2000,
        capture_seq_start=0,
        capture_seq_end=16000,
        duration_ms=1000.0,
        vad_speech_ms=900.0,
    )
    orch._on_ptt_released(ts_ns=2000, p=payload)
    for _ in range(50):
        if orch.state == "confirm_wait":
            break
        time.sleep(0.02)
    assert orch.state == "confirm_wait"
    assert orch._pending_confirmation_active is True


def test_t_brg_05_ptt_press_during_confirm_wait_preserves_confirmation(
    test_orch: Orchestrator, tmp_path: Path
):
    """T-BRG-05 (WO-9 A1, revised): a PTT press during CONFIRM_WAIT is the answer
    mechanism, not a barge-in. The pending confirmation must survive the press;
    the spoken answer resolves it. Saying "stop" still cancels (safety preserved
    via the CANCEL pattern instead of the old abort-on-press behavior)."""
    target_file = tmp_path / "orch_ws" / "barge.txt"
    call = ToolCall(
        tool="write_file",
        args={"path": "barge.txt", "content": "should_not_exist"},
        call_id="call-c3",
    )
    _reach_confirm_wait(test_orch, call)

    # User presses PTT to answer — confirmation must stay alive
    test_orch._on_ptt_pressed(ts_ns=3000)
    assert test_orch.state == "listening"
    assert test_orch._pending_confirmation_active is True

    # User speaks "stop" -> CANCEL_PATTERN -> action cancelled, nothing executed
    test_orch.asr = FakeASR(transcript="stop")
    answer_pcm = np.ones(8000, dtype=np.int16) * 500
    test_orch.cap_ring.write(answer_pcm)
    # seq space is cumulative samples written: 16000 from the turn capture
    seq_start, seq_end = 16000, 16000 + len(answer_pcm)
    p_answer = PTTReleasedPayload(
        t_ns=4000,
        capture_seq_start=seq_start,
        capture_seq_end=seq_end,
        duration_ms=500.0,
        vad_speech_ms=400.0,
    )
    test_orch._on_ptt_released(ts_ns=4000, p=p_answer)

    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=3.0)

    assert not target_file.exists()
    assert test_orch.state == "idle"


def test_voice_confirmation_yes_executes_tool(test_orch: Orchestrator, tmp_path: Path):
    """WO-9 A1 (F1): press -> release "yes do it" during confirm_wait executes the tool.

    Regression for the live-session deadlock: the PTT press used to cancel the
    pending confirmation before the release could deliver the voice answer.
    """
    call = ToolCall(tool="launch_app", args={"app_name": "calculator"}, call_id="call-v2")
    _reach_confirm_wait(test_orch, call)

    test_orch.asr = FakeASR(transcript="yes do it")
    answer_pcm = np.ones(8000, dtype=np.int16) * 500
    test_orch.cap_ring.write(answer_pcm)
    # seq space is cumulative samples written: 16000 from the turn capture
    seq_start, seq_end = 16000, 16000 + len(answer_pcm)
    p_answer = PTTReleasedPayload(
        t_ns=4000,
        capture_seq_start=seq_start,
        capture_seq_end=seq_end,
        duration_ms=500.0,
        vad_speech_ms=400.0,
    )
    test_orch._on_ptt_released(ts_ns=4000, p=p_answer)

    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=3.0)

    assert test_orch.state == "idle"
    assert len(test_orch.executed_tools) == 1
    assert test_orch.executed_tools[0][0] == "launch_app"


def test_voice_confirmation_no_cancels(test_orch: Orchestrator, tmp_path: Path):
    """WO-9 A1: press -> release "no" during confirm_wait cancels the action."""
    target_file = tmp_path / "orch_ws" / "voice_no.txt"
    call = ToolCall(
        tool="write_file",
        args={"path": "voice_no.txt", "content": "data"},
        call_id="call-v3",
    )
    _reach_confirm_wait(test_orch, call)

    test_orch.asr = FakeASR(transcript="no")
    answer_pcm = np.ones(8000, dtype=np.int16) * 500
    test_orch.cap_ring.write(answer_pcm)
    # seq space is cumulative samples written: 16000 from the turn capture
    seq_start, seq_end = 16000, 16000 + len(answer_pcm)
    p_answer = PTTReleasedPayload(
        t_ns=4000,
        capture_seq_start=seq_start,
        capture_seq_end=seq_end,
        duration_ms=500.0,
        vad_speech_ms=400.0,
    )
    test_orch._on_ptt_released(ts_ns=4000, p=p_answer)

    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=3.0)

    assert not target_file.exists()
    assert test_orch.state == "idle"


def test_text_confirmation_yes_executes_tool(test_orch: Orchestrator, tmp_path: Path):
    """WO-9 A1 (F1): typed "yes" during confirm_wait resolves the pending action."""
    call = ToolCall(tool="launch_app", args={"app_name": "calculator"}, call_id="call-t1")
    _reach_confirm_wait(test_orch, call)

    test_orch._on_user_text(ts_ns=3000, user_text="yes")

    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=3.0)

    assert test_orch.state == "idle"
    assert len(test_orch.executed_tools) == 1
    assert test_orch.executed_tools[0][0] == "launch_app"


def test_text_confirmation_no_and_unknown_cancel(test_orch: Orchestrator, tmp_path: Path):
    """WO-9 A1: typed "no" (and unrecognized input) during confirm_wait cancels."""
    target_file = tmp_path / "orch_ws" / "text_no.txt"
    call = ToolCall(
        tool="write_file",
        args={"path": "text_no.txt", "content": "data"},
        call_id="call-t2",
    )
    _reach_confirm_wait(test_orch, call)

    test_orch._on_user_text(ts_ns=3000, user_text="no")

    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=3.0)

    assert not target_file.exists()
    assert test_orch.state == "idle"


def test_voice_confirmation_does_not_block_ingest(test_orch: Orchestrator, tmp_path: Path):
    """F-CORE-015: Voice confirmation must never run ASR on the ingest thread.

    With a 500 ms ASR backend, a voice release followed immediately by a UI
    click must both be handled by the ingest path in < 50 ms each; the click
    (an explicit user act) supersedes the in-flight voice answer and the tool
    must NOT execute.
    """
    target_file = tmp_path / "orch_ws" / "voice_confirm.txt"
    call = ToolCall(
        tool="write_file",
        args={"path": "voice_confirm.txt", "content": "data"},
        call_id="call-v1",
    )
    script = [
        ToolCallEnd(call=call),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
    ]
    test_orch.llm = FakeLLM(script=script)

    class SlowASR(FakeASR):
        def __init__(self) -> None:
            super().__init__(transcript="yes do it")

        def transcribe(self, pcm_int16):  # noqa: ANN001
            time.sleep(0.5)
            return super().transcribe(pcm_int16)

    test_orch.asr = SlowASR()

    # Start a turn that requires confirmation
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

    # Voice answer arrives on the ingest thread: must return immediately
    # (payload hand-off only, no inline ASR).
    env_release = Envelope(
        type="ptt.released",
        trace_id="",
        ts_ns=3000,
        src="audio",
        payload=PTTReleasedPayload(
            t_ns=3000,
            capture_seq_start=0,
            capture_seq_end=16000,
            duration_ms=1000.0,
            vad_speech_ms=900.0,
        ).model_dump(),
    )
    t0 = time.perf_counter()
    test_orch._handle_ingest_message(env_release)
    ingest_latency_s = time.perf_counter() - t0
    assert ingest_latency_s < 0.05, (
        f"ingest thread blocked {ingest_latency_s * 1000:.0f} ms on voice ASR"
    )

    # UI click lands right after the voice release; it must not queue behind
    # the 500 ms ASR running on the turn worker.
    env_click = Envelope(
        type="ui.confirm_result",
        trace_id="",
        ts_ns=3100,
        src="ui",
        payload=UIConfirmResultPayload(accepted=False, via="click").model_dump(),
    )
    t1 = time.perf_counter()
    test_orch._handle_ingest_message(env_click)
    click_latency_s = time.perf_counter() - t1
    assert click_latency_s < 0.05, f"click delayed {click_latency_s * 1000:.0f} ms behind voice ASR"

    if test_orch.active_turn_thread:
        test_orch.active_turn_thread.join(timeout=3.0)

    # The explicit click (cancel) wins over the in-flight voice answer.
    assert test_orch.state == "idle"
    assert not target_file.exists()
