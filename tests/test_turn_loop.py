"""
Integration Tests for Conversational Turn Loop & Barge-In (Spec 01 §6, Spec 10)
"""

import time

import numpy as np
import pytest

from lucca.core.ipc_schemas import ASRResultPayload, PTTReleasedPayload
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    LLMUsage,
    MemoryHit,
    Provenance,
    RetrievalQuery,
    SignedPayload,
    TokenDelta,
)
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

    # F-CORE-014: Stale worker's finally block must NOT reset state to idle
    assert orchestrator.state == "listening"


def test_stale_worker_does_not_reset_state(orchestrator):
    """
    F-CORE-014: Stale worker's finally block must not force state to idle
    when a barge-in has moved orchestrator to listening/thinking.
    """
    fake_script = [
        TokenDelta(delta="A slow response that will be interrupted "),
        TokenDelta(delta="by barge in."),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=2)),
    ]
    orchestrator.llm = FakeLLM(script=fake_script, token_delay_s=0.05)

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
    time.sleep(0.02)

    # Barge-in mid-speech: moves state to listening
    orchestrator._on_ptt_pressed(ts_ns=3000)
    assert orchestrator.state == "listening"

    # Wait for old worker thread to terminate its finally block
    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=2.0)

    # State must STILL be listening, NOT clobbered to idle or postturn
    assert orchestrator.state == "listening"


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


class FakeMemoryStore:
    def __init__(self, search_results: list[MemoryHit] | None = None) -> None:
        self.search_results = search_results or []
        self.commits: list[SignedPayload] = []
        self.queries: list[RetrievalQuery] = []

    async def search(self, q: RetrievalQuery) -> list[MemoryHit]:
        self.queries.append(q)
        return self.search_results

    async def commit(self, payload: SignedPayload) -> int:
        self.commits.append(payload)
        return len(self.commits)


class FakeASR:
    def __init__(self, transcript: str = "open calculator") -> None:
        self.transcript = transcript

    def transcribe(self, pcm_int16: object) -> ASRResultPayload:
        return ASRResultPayload(
            text=self.transcript,
            segments=[],
            avg_logprob=0.0,
            model="fake-asr",
            audio_sha256="abc",
            elapsed_ms=10.0,
        )


def test_turn_reaches_postturn_and_commits_transcript() -> None:
    fake_asr = FakeASR(transcript="open calculator")
    fake_memory = FakeMemoryStore()
    fake_llm = FakeLLM(script=[Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=2))])
    orch = Orchestrator(tts=FakeTTS, asr=fake_asr, llm=fake_llm, memory_store=fake_memory)
    try:
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
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=5.0)

        assert orch.state == "idle"
        assert len(fake_memory.commits) == 1
        commit = fake_memory.commits[0]
        assert commit.provenance == Provenance.USER_EXPLICIT
        assert commit.content == "open calculator"
        assert orch.last_decision is not None
        assert orch.last_decision.executed_path in {"RULE", "LLM"}
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


def test_orchestrator_retrieves_and_injects_memories() -> None:
    now = time.time()
    memory_hit = MemoryHit(
        memory_id=1,
        content="User preferred editor is VSCode",
        provenance=Provenance.USER_EXPLICIT,
        score=0.95,
        source_turn_id="turn-prev",
        kind="fact",
        created_at=now - 100,
        valid_from=now - 100,
    )
    fake_memory = FakeMemoryStore(search_results=[memory_hit])
    fake_llm = FakeLLM(script=[Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=2))])
    orch = Orchestrator(tts=FakeTTS, llm=fake_llm, memory_store=fake_memory)
    try:
        orch._on_user_text(ts_ns=5000, user_text="What is my favorite editor?")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=2.0)

        assert len(fake_memory.queries) >= 1
        assert fake_memory.queries[0].query_text == "What is my favorite editor?"
        assert fake_llm.last_memories == [memory_hit]
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
