"""
Integration Tests for Conversational Turn Loop & Barge-In (Spec 01 §6, Spec 10)
"""

import time

import numpy as np
import pytest

from lucca.core.ipc_schemas import PTTReleasedPayload
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Done, LLMUsage, TokenDelta
from lucca.senses.ring_buffer import FLAG_ABORT
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


@pytest.fixture
def orchestrator():
    orch = Orchestrator(tts=FakeTTS)
    yield orch
    orch.stop()
    orch.cap_ring.close()
    orch.cap_ring.unlink()
    orch.play_ring.close()
    orch.play_ring.unlink()


def test_full_turn_state_progression(orchestrator):
    # Setup FakeLLM
    fake_script = [
        TokenDelta(delta="Hello "),
        TokenDelta(delta="there! "),
        TokenDelta(delta="I am Lucca. "),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=3)),
    ]
    orchestrator.llm = FakeLLM(script=fake_script)

    # 1. PTT Pressed -> LISTENING
    orchestrator._on_ptt_pressed(ts_ns=1000)
    assert orchestrator.state == "listening"

    # Write dummy audio into capture ring (1 second of 16kHz audio = 16000 samples)
    dummy_pcm = np.ones(16000, dtype=np.int16) * 1000
    orchestrator.cap_ring.write(dummy_pcm)

    # 2. PTT Released -> DISPATCH -> SPEAKING -> POSTTURN -> IDLE
    payload = PTTReleasedPayload(
        t_ns=2000,
        capture_seq_start=0,
        capture_seq_end=16000,
        duration_ms=1000.0,
        vad_speech_ms=900.0,
    )
    orchestrator._on_ptt_released(ts_ns=2000, p=payload)

    # Wait for turn thread to complete
    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=5.0)

    assert orchestrator.state == "idle"
    assert orchestrator.active_trace is not None
    assert orchestrator.active_trace.tokens_out == 3
    assert not orchestrator.active_trace.interrupted


def test_barge_in_mid_speech(orchestrator):
    # Setup FakeLLM with inter-token delay to simulate active speech
    fake_script = [
        TokenDelta(delta="This is a long sentence that should be interrupted "),
        TokenDelta(delta="by the user pressing push to talk again. "),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=2)),
    ]
    orchestrator.llm = FakeLLM(script=fake_script, token_delay_s=0.05)

    # Start turn
    orchestrator._on_ptt_pressed(ts_ns=1000)
    dummy_pcm = np.ones(16000, dtype=np.int16) * 1000
    orchestrator.cap_ring.write(dummy_pcm)

    payload = PTTReleasedPayload(
        t_ns=2000,
        capture_seq_start=0,
        capture_seq_end=16000,
        duration_ms=1000.0,
        vad_speech_ms=900.0,
    )
    orchestrator._on_ptt_released(ts_ns=2000, p=payload)

    # Wait until thinking/speaking
    time.sleep(0.02)

    # User presses PTT again mid-speech -> BARGE IN!
    orchestrator._on_ptt_pressed(ts_ns=3000)

    # Assert instant transition to listening
    assert orchestrator.state == "listening"
    # Assert playback ring abort flag set immediately
    assert orchestrator.play_ring.has_flag(FLAG_ABORT)
    # Assert active trace marked interrupted
    assert orchestrator.active_trace is not None
    assert orchestrator.active_trace.interrupted

    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=2.0)


def test_user_text_turn_loop(orchestrator):
    fake_script = [
        TokenDelta(delta="I am functioning "),
        TokenDelta(delta="normally. "),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=2)),
    ]
    orchestrator.llm = FakeLLM(script=fake_script)

    # User sends typed text
    orchestrator._on_user_text(ts_ns=5000, user_text="Status report?")

    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=2.0)

    assert orchestrator.state == "idle"
    assert len(orchestrator.history) == 2
    assert orchestrator.history[0] == {"role": "user", "content": "Status report?"}
    assert orchestrator.history[1]["role"] == "assistant"
    assert "functioning normally" in orchestrator.history[1]["content"]


def test_silence_discard(orchestrator):
    # Setup PTT release with 0ms speech and no ASR text
    orchestrator.asr = None
    payload = PTTReleasedPayload(
        t_ns=6000,
        capture_seq_start=0,
        capture_seq_end=1600,
        duration_ms=100.0,
        vad_speech_ms=0.0,
    )
    orchestrator._on_ptt_released(ts_ns=6000, p=payload)

    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=1.0)

    # Should safely return to idle without running LLM
    assert orchestrator.state == "idle"

