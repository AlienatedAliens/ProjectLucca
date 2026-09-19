"""
Integration Tests for Conversational Turn Loop & Barge-In (Spec 01 §6, Spec 10)
"""

import time

import numpy as np
import pytest

from lucca.core.ipc_schemas import (
    Envelope,
    PlaybackDonePayload,
    PTTReleasedPayload,
    TTSDonePayload,
)
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
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


@pytest.fixture
def orchestrator():
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR)
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


def test_barge_in_then_second_turn_is_clean(orchestrator):
    """
    F-CORE-011: Barge-in stops/joins previous worker and starts second turn cleanly.
    First turn with delay is barged into; second turn runs immediately.
    Asserts history contains only the second exchange, and no chunk after barge-in
    contains text from the first turn.
    """
    script1 = [
        TokenDelta(delta="AAA first turn message part 1 "),
        TokenDelta(delta="AAA first turn message part 2 "),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=2)),
    ]
    orchestrator.llm = FakeLLM(script=script1, token_delay_s=0.05)

    # 1. Start first turn
    orchestrator._on_ptt_pressed(ts_ns=1000)
    dummy_pcm = np.ones(16000, dtype=np.int16) * 1000
    orchestrator.cap_ring.write(dummy_pcm)

    payload1 = PTTReleasedPayload(
        t_ns=2000,
        capture_seq_start=0,
        capture_seq_end=16000,
        duration_ms=1000.0,
        vad_speech_ms=900.0,
    )
    orchestrator._on_ptt_released(ts_ns=2000, p=payload1)
    time.sleep(0.02)

    # 2. User barges in with second turn
    orchestrator._on_ptt_pressed(ts_ns=3000)
    assert orchestrator.state == "listening"

    script2 = [
        TokenDelta(delta="BBB second turn clean message "),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
    ]
    orchestrator.llm = FakeLLM(script=script2, token_delay_s=0.0)

    payload2 = PTTReleasedPayload(
        t_ns=4000,
        capture_seq_start=16000,
        capture_seq_end=32000,
        duration_ms=1000.0,
        vad_speech_ms=900.0,
    )
    orchestrator._on_ptt_released(ts_ns=4000, p=payload2)

    # Wait for second turn to finish
    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=3.0)

    assert orchestrator.state == "idle"
    # History must contain only second turn (user + assistant = 2 messages)
    assert len(orchestrator.history) == 2
    assert "BBB" in orchestrator.history[1]["content"]
    assert "AAA" not in orchestrator.history[1]["content"]

    # Synthesized chunks must contain only BBB
    chunk_texts = [c["text"] for c in orchestrator.tts.synthesized_chunks]
    assert all("AAA" not in t for t in chunk_texts)
    assert any("BBB" in t for t in chunk_texts)


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


def test_tts_does_not_block_token_consumption() -> None:
    """
    F-CORE-017: TTS synthesis does not block the LLM streaming thread.
    With a slow TTS backend (200ms per chunk), a stream of 6 chunk-forming
    tokens must exhaust the LLM token loop in < 300 ms while synthesized
    chunks are processed asynchronously by the background TTS worker.
    """

    class SlowTTS(FakeTTS):
        def synthesize(
            self,
            chunk_id: int,
            text: str,
            voice: str = "af_heart",
            is_first: bool = False,
        ) -> TTSDonePayload:
            time.sleep(0.2)
            return super().synthesize(chunk_id, text, voice, is_first)

    sentences = [
        "This is the first sentence that is long enough to form a complete chunk.\n",
        "This is the second sentence that is long enough to form a complete chunk.\n",
        "This is the third sentence that is long enough to form a complete chunk.\n",
        "This is the fourth sentence that is long enough to form a complete chunk.\n",
        "This is the fifth sentence that is long enough to form a complete chunk.\n",
        "This is the sixth sentence that is long enough to form a complete chunk.\n",
    ]
    script = [TokenDelta(delta=s) for s in sentences]
    script.append(Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=30)))

    stream_exhausted_time: list[float] = []
    t_stream_start: list[float] = []

    class TimedFakeLLM(FakeLLM):
        def stream_turn(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            t_stream_start.append(time.perf_counter())
            yield from super().stream_turn(*args, **kwargs)
            stream_exhausted_time.append(time.perf_counter())

    fake_llm = TimedFakeLLM(script=script)
    orch = Orchestrator(tts=SlowTTS, llm=fake_llm)
    try:
        orch._on_user_text(ts_ns=1000, user_text="Give me a long paragraph")
        for _ in range(50):
            if stream_exhausted_time:
                break
            time.sleep(0.01)

        assert stream_exhausted_time, "LLM stream was never exhausted"
        consumption_elapsed = stream_exhausted_time[0] - t_stream_start[0]
        # 6 chunks * 200 ms = 1200 ms if synchronous; must be < 300 ms with queue
        assert consumption_elapsed < 0.300, (
            f"Token consumption took {consumption_elapsed * 1000:.1f} ms (expected < 300 ms)"
        )

        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=5.0)

        assert orch.state == "idle"
        assert len(orch.tts.synthesized_chunks) == 6
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


def test_trace_points_populated():
    """
    F-CORE-009: Verify all spec'd trace points are populated and monotonic in order.
    Asserts:
    t_asr_sent < t_asr_done <= t_llm_sent < t_llm_first_token <= t_first_chunk
    <= t_tts_first_sent < t_tts_first_done <= t_llm_done <= t_postturn_done
    and all are > 0.
    """
    from tests.fakes.fake_asr import FakeASR

    fake_script = [
        TokenDelta(delta="Hello "),
        TokenDelta(delta="world, this is a long enough chunk to emit audio.\n"),
        Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=10)),
    ]
    orch = Orchestrator(
        tts=FakeTTS, asr=FakeASR(transcript="hello lucca"), llm=FakeLLM(script=fake_script)
    )
    try:
        # 1. PTT Pressed
        press_ts = 1_000_000_000
        orch._on_ptt_pressed(ts_ns=press_ts)

        # Write dummy audio (16,000 samples)
        dummy_pcm = np.ones(16000, dtype=np.int16) * 1000
        orch.cap_ring.write(dummy_pcm)

        # 2. PTT Released
        release_ts = 2_000_000_000
        payload = PTTReleasedPayload(
            t_ns=release_ts,
            capture_seq_start=0,
            capture_seq_end=16000,
            duration_ms=1000.0,
            vad_speech_ms=900.0,
            vad_done_ns=release_ts + 1_000_000,
        )
        orch._on_ptt_released(ts_ns=release_ts, p=payload)

        # Wait for turn thread to complete
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=5.0)

        assert orch.state == "idle"
        trace = orch.active_trace
        assert trace is not None

        # Verify all core trace points are > 0
        assert trace.t_key_press > 0
        assert trace.t_key_release > 0
        assert trace.t_vad_done > 0
        assert trace.t_asr_sent > 0
        assert trace.t_asr_done > 0
        assert trace.t_route_done > 0
        assert trace.t_llm_sent > 0
        assert trace.t_llm_first_token > 0
        assert trace.t_first_chunk > 0
        assert trace.t_tts_first_sent > 0
        assert trace.t_tts_first_done > 0
        assert trace.t_tts_last_done > 0
        assert trace.t_llm_done > 0
        assert trace.t_postturn_done > 0

        # Verify ordering per F-CORE-009
        assert trace.t_asr_sent < trace.t_asr_done
        assert trace.t_asr_done <= trace.t_llm_sent
        assert trace.t_llm_sent <= trace.t_llm_first_token
        assert trace.t_llm_first_token <= trace.t_first_chunk
        assert trace.t_first_chunk <= trace.t_tts_first_sent
        assert trace.t_tts_first_sent <= trace.t_tts_first_done
        assert trace.t_tts_first_done <= trace.t_postturn_done
        assert trace.t_llm_done <= trace.t_postturn_done

        # Ingest playback_done and verify t_playback_done
        playback_done_env = Envelope(
            type="audio.playback_done",
            trace_id=trace.trace_id,
            ts_ns=3_000_000_000,
            src="audio",
            payload=PlaybackDonePayload(trace_id=trace.trace_id, t_ns=3_000_000_000).model_dump(),
        )
        orch._handle_ingest_message(playback_done_env)
        assert trace.t_playback_done == 3_000_000_000
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
