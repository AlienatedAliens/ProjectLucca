"""
WO-26 Phase 1 Functional Acceptance Tests: Mind-Mouth Interiority Barrier.

Verifies:
1. Positive Control: Contradictory user input triggers belief supersession and revision
   without enqueuing spoken audio to Kokoro TTS or polluting LLM conversational history.
2. Negative Control: Non-revision system events (telemetry/watchdog alerts) passed to
   _speak_text are strictly quarantined from audio output.
3. Sibling Test: Autobiographical fact revision updates paraconsistent memory cleanly
   with zero TTS emission.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

import queue
from collections import deque
from pathlib import Path

from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.trace import TurnTrace
from lucca.core.schemas import (
    ExecutionTier,
    Provenance,
    UnsignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def test_orch(tmp_path: Path) -> Orchestrator:
    db = DatabaseManager(tmp_path / "test_interiority_mem.sqlite")
    db.migrate()
    embedding_port = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=embedding_port)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)

    orch = Orchestrator.__new__(Orchestrator)
    orch.config = get_config()
    orch.execute_tools = True
    orch.state = "idle"
    orch.running = True
    orch.db = db
    orch.memory_store = store
    orch.reflection_engine = refl
    orch.current_turn_receipts = []
    orch.current_turn_tool_calls = []
    orch.current_turn_tier = ExecutionTier.FULL_LOOP
    orch.pending_spoken_updates = deque()
    orch.history = []
    orch.executed_tools = []
    orch.current_turn_transcript = None
    orch.current_turn_assistant_reply = None
    orch.active_trace = None
    orch.router = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.sandbox = MagicMock()
    orch.affect_tracker = MagicMock()
    orch.play_ring = MagicMock()
    orch._tts_queue = queue.Queue()
    orch.tts = MagicMock()
    orch.asr = MagicMock()
    orch.speech_output = MagicMock()
    orch.user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    orch.assistant_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    orch.breach_signer = CoherenceBreachSigner(master_key=TEST_MASTER_KEY)

    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._set_state = MagicMock()

    from lucca.core.belief_service import BeliefService
    orch.beliefs = BeliefService(db=db, reflection_engine=refl, clock=orch.clock if hasattr(orch, "clock") else None, orchestrator=orch)
    return orch


def test_positive_control_belief_revision_not_spoken(test_orch: Orchestrator) -> None:
    """
    Positive Control:
    - Seed an initial belief ("user lives in the United States").
    - User explicitly contradicts ("I don't live in the US, I live in Japan").
    - Contradiction is detected and superseded in SQLite.
    - maybe_speak_pending_updates is invoked on next turn.
    - Assert _speak_text was NEVER called for the revision text.
    - Assert conversational history is NOT polluted with [Lucca Revision] debug strings.
    - Assert _publish_caption was invoked with source="system".
    """
    now = time.time()
    p_init = UnsignedPayload(
        content="I think you live in the United States.",
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        nonce="nonce_loc_01",
        created_at=now - 50.0,
        trace_id="tr-seed-loc",
        confidence=0.8,
        structured={
            "importance": 0.4,
            "topic": "user residence",
            "valid_from": now - 50.0,
        },
    )
    signed_init = test_orch.assistant_signer.sign(p_init)
    seed_mid = test_orch.memory_store.commit(signed_init)

    # User correction turn
    trace_corr = TurnTrace(
        trace_id="tr-corr-japan", session_id="s1", origin="text", mode="transcript"
    )
    test_orch.active_trace = trace_corr
    test_orch.current_turn_transcript = "I don't live in the US, I live in Japan."
    test_orch.current_turn_assistant_reply = "Got it, you're based in Japan!"
    test_orch._finalize_turn(trace_corr, None)

    # 1. Old belief must be superseded
    assert test_orch.db is not None
    with test_orch.db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (seed_mid,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[1] is not None

    # 2. Captions mock tracking
    test_orch._publish_caption = MagicMock()

    # 3. Next turn arrives: _maybe_speak_pending_updates is triggered
    trace_next = TurnTrace(
        trace_id="tr-turn-next-loc", session_id="s1", origin="text", mode="transcript"
    )
    test_orch._maybe_speak_pending_updates(trace_next)

    # Queue must be drained
    assert len(test_orch.pending_spoken_updates) == 0

    # Interiority Barrier: _speak_text must NOT be called for the revision!
    assert not test_orch._speak_text.called, "TTS _speak_text must not be called for belief revisions"

    # Conversational history must not contain system revision strings
    assert not any("[Lucca Revision]" in str(m.get("content")) for m in test_orch.history)
    assert not any("I've revised a belief" in str(m.get("content")) for m in test_orch.history)

    # System caption was emitted
    test_orch._publish_caption.assert_called_once()
    call_args = test_orch._publish_caption.call_args
    assert call_args.kwargs.get("source") == "system" or (len(call_args.args) > 1 and call_args.args[1] == "system")


def test_negative_control_non_revision_system_message_quarantined(test_orch: Orchestrator) -> None:
    """
    Negative Control (Reviewer Note):
    - A non-revision system message (e.g. watchdog alert, cognitive bus message)
      passed to _speak_text must stay strictly out of TTS audio output.
    """
    mock_speech_output = MagicMock()
    test_orch.speech_output = mock_speech_output

    trace = TurnTrace(trace_id="tr-sys-alert", session_id="s1", origin="text", mode="transcript")

    # Pass various system and revision strings directly to _speak_text
    system_messages = [
        "[System Watchdog] Memory pressure is normal.",
        "[Cognitive Bus Yield: define: no term]",
        "[Lucca Revision] 💡 I've revised a belief I had — previously: X",
        "I've revised a belief I had — previously: Y",
    ]

    for msg in system_messages:
        Orchestrator._speak_text(test_orch, trace, msg)
        assert not mock_speech_output.speak_text.called, f"System message must not reach TTS: {msg}"

    # Verify regular user-facing text DOES get spoken
    Orchestrator._speak_text(test_orch, trace, "Hello, how can I help you today?")
    mock_speech_output.speak_text.assert_called_once_with(trace, "Hello, how can I help you today?")


def test_sibling_autobiographical_fact_update(test_orch: Orchestrator) -> None:
    """
    Sibling Test (Reviewer Note):
    - User updates an autobiographical preference fact ("My favorite editor is Neovim, not VSCode").
    - Confirms that different topics / entities also adhere strictly to the interiority barrier.
    """
    now = time.time()
    p_init = UnsignedPayload(
        content="I think your favorite code editor is VSCode.",
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        nonce="nonce_editor_01",
        created_at=now - 50.0,
        trace_id="tr-seed-editor",
        confidence=0.75,
        structured={
            "importance": 0.3,
            "topic": "preferred code editor",
            "valid_from": now - 50.0,
        },
    )
    signed_init = test_orch.assistant_signer.sign(p_init)
    seed_mid = test_orch.memory_store.commit(signed_init)

    trace_corr = TurnTrace(
        trace_id="tr-corr-editor", session_id="s1", origin="text", mode="transcript"
    )
    test_orch.active_trace = trace_corr
    test_orch.current_turn_transcript = "Actually, my favorite code editor is Neovim."
    test_orch.current_turn_assistant_reply = "Neovim it is!"
    test_orch._finalize_turn(trace_corr, None)

    # Next turn
    trace_next = TurnTrace(
        trace_id="tr-turn-next-editor", session_id="s1", origin="text", mode="transcript"
    )
    test_orch._speak_text = MagicMock()
    test_orch._maybe_speak_pending_updates(trace_next)

    assert not test_orch._speak_text.called, "Sibling fact revision must not trigger TTS audio"
    assert not any("Neovim" in str(m.get("content")) for m in test_orch.history if "revised" in str(m.get("content")).lower())
