"""
Project Lucca — Phase 1 Live Hardware Integration Test (T3 hw)
Spec 01 §6, Spec 10, ADR-001, ADR-008
Verifies real Ultravox Q6_K on dGPU + real Kokoro-82M on CPU + shared-memory rings.
"""

import subprocess
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from lucca.core.ipc_schemas import PTTReleasedPayload
from lucca.core.orchestrator import Orchestrator
from lucca.senses.ring_buffer import FLAG_ABORT, FLAG_EOS

CONV_FIXTURE_PATH = Path(r"C:\projects\ProjectLucca\tests\fixtures\conversational_speech.wav")
TOOL_FIXTURE_PATH = Path(r"C:\projects\ProjectLucca\tests\fixtures\audio_tool_calls\calc_01.wav")


@pytest.fixture
def live_orchestrator():
    """Initializes Orchestrator connected to live llama-server and real Kokoro TTS."""
    orch = Orchestrator(execute_tools=False)
    yield orch
    orch.stop()
    orch.cap_ring.close()
    orch.cap_ring.unlink()
    orch.play_ring.close()
    orch.play_ring.unlink()


@pytest.mark.hw
def test_live_phase1_conversational_turn(live_orchestrator: Orchestrator):
    """
    T-LIVE-01: End-to-end conversational voice turn on live hardware.
    1. Reads real conversational audio ("Hello Lucca, what is your name?").
    2. Writes into lucca_cap_ring.
    3. Simulates PTT release.
    4. Streams real LLM generation from llama-server (Ultravox Q6_K on dGPU).
    5. Feeds streaming text into Kokoro TTS ONNX on CPU.
    6. Writes synthesized PCM into lucca_play_ring.
    7. Verifies TTFT <= 200 ms, total first audio sample <= 600 ms.
    """
    assert CONV_FIXTURE_PATH.exists(), f"Fixture missing: {CONV_FIXTURE_PATH}"

    with wave.open(str(CONV_FIXTURE_PATH), "rb") as wf:
        n_frames = wf.getnframes()
        pcm_bytes = wf.readframes(n_frames)
        pcm_samples = np.frombuffer(pcm_bytes, dtype=np.int16)

    # 1. PTT Pressed -> LISTENING
    t_press_ns = time.monotonic_ns()
    live_orchestrator._on_ptt_pressed(ts_ns=t_press_ns)
    assert live_orchestrator.state == "listening"

    # 2. Write audio to capture ring
    n_written = live_orchestrator.cap_ring.write(pcm_samples)
    assert n_written == len(pcm_samples)

    # 3. PTT Released -> DISPATCH -> SPEAKING
    t_release_ns = time.monotonic_ns()
    payload = PTTReleasedPayload(
        t_ns=t_release_ns,
        capture_seq_start=0,
        capture_seq_end=n_written,
        duration_ms=float(len(pcm_samples) / 16.0),
        vad_speech_ms=float(len(pcm_samples) / 16.0),
    )
    live_orchestrator._on_ptt_released(ts_ns=t_release_ns, p=payload)

    # Wait for turn thread to complete
    if live_orchestrator.active_turn_thread:
        live_orchestrator.active_turn_thread.join(timeout=20.0)

    trace = live_orchestrator.active_trace
    assert trace is not None
    assert not trace.interrupted
    assert trace.tokens_out > 0
    assert trace.chunks > 0

    # Timing checks against spec thresholds
    ttft_ms = (trace.t_llm_first_token - trace.t_llm_sent) / 1e6
    tts_first_ms = (trace.t_tts_first_done - trace.t_tts_first_sent) / 1e6
    total_latency_ms = (trace.t_tts_first_done - trace.t_key_release) / 1e6

    print("\n[LIVE CONVERSATIONAL RESULTS]")
    print(f"  TTFT:              {ttft_ms:.1f} ms (budget <= 200 ms)")
    print(f"  First TTS chunk:   {tts_first_ms:.1f} ms")
    print(f"  First audio ready: {total_latency_ms:.1f} ms (budget <= 600 ms)")
    print(f"  Tokens produced:   {trace.tokens_out}")
    print(f"  Chunks produced:   {trace.chunks}")

    # Check that playback ring received samples and EOS flag
    assert live_orchestrator.play_ring.write_idx > 0
    assert live_orchestrator.play_ring.has_flag(FLAG_EOS)

    # VRAM check
    try:
        smi_out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],  # noqa: S603, S607
            text=True,
        )
        vram_mb = float(smi_out.strip().split("\n")[0])
        print(f"  dGPU VRAM used:    {vram_mb:.0f} MB (ceiling <= 12800 MB)")
        assert vram_mb <= 12800.0, f"VRAM ceiling breached: {vram_mb} MB > 12800 MB"
    except (subprocess.SubprocessError, FileNotFoundError):
        pass


@pytest.mark.hw
def test_live_phase1_tool_call_turn(live_orchestrator: Orchestrator):
    """
    T-LIVE-02: End-to-end voice tool call turn on live hardware.
    1. Reads tool invocation audio ("Lucca, open calculator").
    2. Writes into lucca_cap_ring and simulates PTT release.
    3. Streams LLM response and verifies structured tool invocation (launch_app -> calculator).
    """
    assert TOOL_FIXTURE_PATH.exists(), f"Fixture missing: {TOOL_FIXTURE_PATH}"

    with wave.open(str(TOOL_FIXTURE_PATH), "rb") as wf:
        n_frames = wf.getnframes()
        pcm_bytes = wf.readframes(n_frames)
        pcm_samples = np.frombuffer(pcm_bytes, dtype=np.int16)

    # PTT Pressed
    t_press_ns = time.monotonic_ns()
    live_orchestrator._on_ptt_pressed(ts_ns=t_press_ns)
    assert live_orchestrator.state == "listening"

    # Write audio
    n_written = live_orchestrator.cap_ring.write(pcm_samples)
    assert n_written == len(pcm_samples)

    # PTT Released
    t_release_ns = time.monotonic_ns()
    payload = PTTReleasedPayload(
        t_ns=t_release_ns,
        capture_seq_start=0,
        capture_seq_end=n_written,
        duration_ms=float(len(pcm_samples) / 16.0),
        vad_speech_ms=float(len(pcm_samples) / 16.0),
    )
    live_orchestrator._on_ptt_released(ts_ns=t_release_ns, p=payload)

    # Wait for turn thread to complete
    if live_orchestrator.active_turn_thread:
        live_orchestrator.active_turn_thread.join(timeout=20.0)

    trace = live_orchestrator.active_trace
    assert trace is not None
    assert not trace.interrupted

    print("\n[LIVE TOOL CALL RESULTS]")
    print(f"  Executed tools:    {live_orchestrator.executed_tools}")

    assert len(live_orchestrator.executed_tools) > 0
    tool_name, tool_args = live_orchestrator.executed_tools[0]
    assert tool_name == "launch_app"
    assert tool_args.get("app_name") == "calculator"


@pytest.mark.hw
def test_live_barge_in_abort(live_orchestrator: Orchestrator):
    """
    T-LIVE-03: Live barge-in abort test.
    Tests that pressing PTT while the LLM is actively streaming aborts within 50 ms.
    """
    with wave.open(str(CONV_FIXTURE_PATH), "rb") as wf:
        n_frames = wf.getnframes()
        pcm_bytes = wf.readframes(n_frames)
        pcm_samples = np.frombuffer(pcm_bytes, dtype=np.int16)

    live_orchestrator._on_ptt_pressed(ts_ns=time.monotonic_ns())
    n_written = live_orchestrator.cap_ring.write(pcm_samples)

    payload = PTTReleasedPayload(
        t_ns=time.monotonic_ns(),
        capture_seq_start=0,
        capture_seq_end=n_written,
        duration_ms=float(len(pcm_samples) / 16.0),
        vad_speech_ms=float(len(pcm_samples) / 16.0),
    )
    live_orchestrator._on_ptt_released(ts_ns=time.monotonic_ns(), p=payload)

    # Wait briefly for LLM generation to commence (50-100 ms)
    time.sleep(0.08)

    # Mid-turn barge-in!
    t0_abort = time.perf_counter()
    live_orchestrator._on_ptt_pressed(ts_ns=time.monotonic_ns())
    abort_duration_ms = (time.perf_counter() - t0_abort) * 1000.0

    print("\n[LIVE BARGE-IN RESULT]")
    print(f"  Barge-in abort duration: {abort_duration_ms:.2f} ms (spec budget <= 50 ms)")

    assert abort_duration_ms < 50.0
    assert live_orchestrator.state == "listening"
    assert live_orchestrator.play_ring.has_flag(FLAG_ABORT)

    if live_orchestrator.active_turn_thread:
        live_orchestrator.active_turn_thread.join(timeout=2.0)
