"""
Project Lucca — A1 Memory & Reflection Runtime Wiring Tests
Work Order #8 (WP-2), Remediation of F-TS-03 (S1), F-TS-04, Spec §7, D-MEM-04

Verifies the 5 runtime wiring scenarios:
1. Belief formation fires on stance reply and not on action report; disabled by setting.
2. Seeded belief + USER_EXPLICIT correction turn -> belief superseded (unflagged case),
   pending_spoken_updates enqueued and spoken on next turn.
3. Flagged case (kind="user_model") -> review queue row, belief intact, nothing spoken.
4. Failed write_file + "I saved it" narration -> COHERENCE_BREACH row with matching trace_id.
5. Roll-up scheduler runs once across simulated 48h clock with restart in between.
"""

from __future__ import annotations

import asyncio
import queue
import time
from collections import deque
from collections.abc import Coroutine
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.coherence import ToolReceipt
from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    ExecutionTier,
    Provenance,
    ToolCall,
    UnsignedPayload,
)
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine, is_rollup_due
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


def _run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture
def test_orch(tmp_path: Path) -> Orchestrator:
    db = DatabaseManager(tmp_path / "test_wiring_mem.sqlite")
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
    orch.user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    orch.assistant_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    orch.breach_signer = CoherenceBreachSigner(master_key=TEST_MASTER_KEY)

    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._set_state = MagicMock()
    return orch


# ============================================================================
# Scenario 1: Belief Formation on Stance Reply vs Action Report vs Setting
# ============================================================================


def test_scenario_1_belief_formation_on_stance_reply(test_orch: Orchestrator) -> None:
    """
    Scenario 1 (revised by WO-9 A12 / F9):
    - LLM reply containing a stance marker in FULL_LOOP tier forms an ASSISTANT_BELIEF.
    - Stance claims on ACTION turns (tool calls present) now ALSO form beliefs —
      the old zero-tool-call gate left a systematic blind spot exactly on turns
      where Lucca was acting. Action receipts are separately recorded as
      ASSISTANT_ACTION (WO-9 A9), so the belief track is no longer the only
      record of what happened.
    - Disabled by config.memory.form_beliefs = False.
    """
    # 1. Stance reply formation
    trace1 = TurnTrace(trace_id="tr-stance-1", session_id="s1", origin="text", mode="transcript")
    test_orch.active_trace = trace1
    test_orch.current_turn_assistant_reply = (
        "I think TypeScript with strict mode is much safer than plain JavaScript."
    )
    test_orch.current_turn_tier = ExecutionTier.FULL_LOOP
    test_orch.current_turn_tool_calls = []
    test_orch._finalize_turn(trace1, None)

    assert test_orch.db is not None
    with test_orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content, p.provenance, m.kind, m.importance
            FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            WHERE p.provenance = 'ASSISTANT_BELIEF'
            """
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert "typescript" in str(rows[0][0]).lower()
        assert rows[0][1] == "ASSISTANT_BELIEF"
        assert rows[0][2] == "belief"

    # 2. Action report (tool calls present) does NOT form an assistant belief
    trace2 = TurnTrace(trace_id="tr-act-1", session_id="s1", origin="text", mode="transcript")
    test_orch.active_trace = trace2
    test_orch.current_turn_assistant_reply = "I think that file is now deleted as requested."
    test_orch.current_turn_tool_calls = [
        ToolCall(tool="delete_file", args={"path": "notes.txt"}, call_id="c1")
    ]
    test_orch._finalize_turn(trace2, None)

    with test_orch.db.read_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM memories m JOIN provenance_envelopes p "
            "ON m.entry_id = p.entry_id WHERE p.provenance = 'ASSISTANT_BELIEF'"
        )
        # A12: the action-turn stance claim now forms a belief too (count 2)
        assert cur.fetchone()[0] == 2

    # 3. Setting disabled: form_beliefs = False
    test_orch.config.memory.form_beliefs = False
    trace3 = TurnTrace(trace_id="tr-dis-1", session_id="s1", origin="text", mode="transcript")
    test_orch.active_trace = trace3
    test_orch.current_turn_assistant_reply = (
        "I believe Rust is the most memory-safe systems language."
    )
    test_orch.current_turn_tool_calls = []
    test_orch._finalize_turn(trace3, None)

    with test_orch.db.read_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM memories m JOIN provenance_envelopes p "
            "ON m.entry_id = p.entry_id WHERE p.provenance = 'ASSISTANT_BELIEF'"
        )
        assert cur.fetchone()[0] == 2  # Count still 2 (beliefs disabled)


# ============================================================================
# Scenario 2: Unflagged Contradiction Supersession & Spoken Update Enqueue
# ============================================================================


def test_scenario_2_unflagged_contradiction_supersession(test_orch: Orchestrator) -> None:
    """
    Scenario 2:
    - Seed an initial belief about user preference.
    - User gives explicit correction (USER_EXPLICIT).
    - Contradiction is detected, belief is superseded, and spoken_update is enqueued.
    - Spoken on the next turn via _stream_llm_speech or _maybe_speak_pending_updates.
    """
    now = time.time()
    p_init = UnsignedPayload(
        content="I think your favorite programming language is Java.",
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        nonce="nonce_java_01",
        created_at=now - 50.0,
        trace_id="tr-seed-java",
        confidence=0.7,
        structured={
            "importance": 0.3,
            "topic": "favorite programming language",
            "valid_from": now - 50.0,
        },
    )
    signed_init = test_orch.assistant_signer.sign(p_init)
    seed_mid = _run(test_orch.memory_store.commit(signed_init))

    # User correction turn
    trace_corr = TurnTrace(
        trace_id="tr-corr-python", session_id="s1", origin="text", mode="transcript"
    )
    test_orch.active_trace = trace_corr
    test_orch.current_turn_transcript = "Actually, my favorite programming language is Python."
    test_orch.current_turn_assistant_reply = "Understood, I have updated my understanding."
    test_orch._finalize_turn(trace_corr, None)

    # 1. Old belief must be superseded (valid_to IS NOT NULL)
    assert test_orch.db is not None
    with test_orch.db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (seed_mid,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[1] is not None

    # 2. pending_spoken_updates must contain a belief revision sentence referencing old and new
    assert len(test_orch.pending_spoken_updates) == 1
    spoken_update = test_orch.pending_spoken_updates[0]
    lower_su = spoken_update.lower()
    # The spoken update must reference the old belief (java) and new content (python)
    assert "java" in lower_su, f"Expected 'java' in spoken update: {spoken_update}"
    assert "python" in lower_su, f"Expected 'python' in spoken update: {spoken_update}"

    # 3. On next turn, _maybe_speak_pending_updates speaks it and records it in history
    trace_next = TurnTrace(
        trace_id="tr-turn-next", session_id="s1", origin="text", mode="transcript"
    )
    test_orch._maybe_speak_pending_updates(trace_next)
    assert len(test_orch.pending_spoken_updates) == 0
    test_orch._speak_text.assert_called_with(trace_next, spoken_update)
    assert any(m.get("content") == spoken_update for m in test_orch.history)


# ============================================================================
# Scenario 3: Flagged Contradiction (kind="user_model") Queued into Review
# ============================================================================


def test_scenario_3_flagged_user_model_review_queue(test_orch: Orchestrator) -> None:
    """
    Scenario 3:
    - Seed belief with kind="user_model".
    - Contradictory user utterance arrives.
    - Contradiction triggers Review Flag 1 (kind == "user_model").
    - Row is created in review_queue; belief is NOT superseded; nothing spoken.
    """
    now = time.time()
    p_um = UnsignedPayload(
        content="User prefers email notifications over mobile alerts.",
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="user_model",
        nonce="nonce_um_01",
        created_at=now - 100.0,
        trace_id="tr-um-seed",
        confidence=0.8,
        structured={
            "importance": 0.4,
            "topic": "notifications",
            "valid_from": now - 100.0,
        },
    )
    signed_um = test_orch.assistant_signer.sign(p_um)
    um_mid = _run(test_orch.memory_store.commit(signed_um))

    # User contradicts the user_model belief
    trace_um_corr = TurnTrace(
        trace_id="tr-um-corr", session_id="s1", origin="text", mode="transcript"
    )
    test_orch.active_trace = trace_um_corr
    test_orch.current_turn_transcript = "I prefer mobile alerts instead of email notifications."
    test_orch.current_turn_assistant_reply = "Got it."
    test_orch._finalize_turn(trace_um_corr, None)

    # 1. Review queue row created
    assert test_orch.db is not None
    with test_orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT review_id, belief_id, trigger_reason, status
            FROM review_queue WHERE belief_id = ?
            """,
            (um_mid,),
        )
        q_row = cur.fetchone()
        assert q_row is not None
        assert "kind_user_model" in q_row[2]
        assert q_row[3] == "PENDING"

        # 2. Original belief remains intact (valid_to IS NULL)
        cur.execute("SELECT valid_to FROM memories WHERE memory_id = ?", (um_mid,))
        assert cur.fetchone()[0] is None

    # 3. Nothing is queued to be spoken
    assert len(test_orch.pending_spoken_updates) == 0


# ============================================================================
# Scenario 4: Failed Tool Execution + False Action Narration -> Breach
# ============================================================================


def test_scenario_4_failed_tool_action_claim_records_breach(test_orch: Orchestrator) -> None:
    """
    Scenario 4:
    - A tool execution fails (e.g. write_file returns ok=False).
    - Companion narrates false success: "I have saved your document to report.pdf."
    - Receipt-aware coherence checker detects the discrepancy.
    - COHERENCE_BREACH row is committed to memory with the turn's trace_id.
    """
    trace_fail = TurnTrace(
        trace_id="tr-breach-write-fail", session_id="s1", origin="text", mode="transcript"
    )
    test_orch.active_trace = trace_fail

    # Record failed receipt on orchestrator
    test_orch.current_turn_receipts = [
        ToolReceipt(
            tool="write_file",
            ok=False,
            call_id="call_fail_01",
            args={"path": "report.pdf"},
            error="disk write error: permission denied",
        )
    ]
    test_orch.current_turn_assistant_reply = "I have saved your document to report.pdf."

    # Direct coherence check check
    breach = test_orch._check_functional_coherence(
        test_orch.current_turn_assistant_reply, test_orch.current_turn_receipts
    )
    assert breach is not None
    assert "write_file" in breach.lower() or "failed" in breach.lower() or "save" in breach.lower()

    # Finalize turn
    test_orch._finalize_turn(trace_fail, None)

    # Verify COHERENCE_BREACH envelope in database
    assert test_orch.db is not None
    with test_orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content, p.provenance, p.trace_id, p.grounding_eligible
            FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            WHERE p.provenance = 'COHERENCE_BREACH'
            """
        )
        b_row = cur.fetchone()
        assert b_row is not None
        assert b_row[1] == "COHERENCE_BREACH"
        assert b_row[2] == "tr-breach-write-fail"
        assert b_row[3] == 1  # Grounding eligible ground truth (ADR-006 / §2.1)


# ============================================================================
# Scenario 5: Nightly Roll-up Scheduler Across 48h Clock & Restart
# ============================================================================


def test_scenario_5_rollup_scheduler_48h_clock_with_restart(
    test_orch: Orchestrator, tmp_path: Path
) -> None:
    """
    Scenario 5:
    - Base clock at Day 1 00:00.
    - Day 1 02:30 -> Not due (rollup_hour_local=3).
    - Day 1 03:30 -> Due and executes once. Records last_rollup_at in system_metadata.
    - Day 1 04:30 -> Already ran today, does not run again.
    - Restart: new ReflectionEngine / Orchestrator instance loading same SQLite DB.
    - Day 1 23:50 -> Still False.
    - Day 2 02:40 -> Still False.
    - Day 2 03:10 -> Due and executes once for Day 2.
    """
    # Fix Day 1 midnight timestamp (1774000000.0 aligned to local midnight)
    dt_base = time.localtime(1774000000.0)
    day1_midnight = 1774000000.0 - (dt_base.tm_hour * 3600 + dt_base.tm_min * 60 + dt_base.tm_sec)

    t_day1_230am = day1_midnight + 2.5 * 3600.0
    t_day1_330am = day1_midnight + 3.5 * 3600.0
    t_day1_430am = day1_midnight + 4.5 * 3600.0

    # 1. Day 1 02:30: not due
    assert not is_rollup_due(None, t_day1_230am, rollup_hour_local=3)
    assert test_orch.maybe_run_nightly_rollup(now=t_day1_230am) == 0

    # 2. Day 1 03:30: due!
    assert is_rollup_due(None, t_day1_330am, rollup_hour_local=3)
    test_orch.maybe_run_nightly_rollup(now=t_day1_330am)

    # Check timestamp persisted in system_metadata
    assert test_orch.reflection_engine is not None
    persisted_ts = test_orch.reflection_engine.get_last_rollup_at()
    assert persisted_ts == t_day1_330am

    # 3. Day 1 04:30: already completed today, not due
    assert not is_rollup_due(persisted_ts, t_day1_430am, rollup_hour_local=3)
    assert test_orch.maybe_run_nightly_rollup(now=t_day1_430am) == 0

    # 4. Simulate process restart: new ReflectionEngine on same DB
    refl_restarted = ReflectionEngine(
        db=test_orch.db, store=test_orch.memory_store, master_key=TEST_MASTER_KEY
    )
    test_orch.reflection_engine = refl_restarted
    restarted_ts = refl_restarted.get_last_rollup_at()
    assert restarted_ts == t_day1_330am

    # Day 1 late night (23:50): not due
    t_day1_1150pm = day1_midnight + 23.83 * 3600.0
    assert not is_rollup_due(restarted_ts, t_day1_1150pm, rollup_hour_local=3)
    assert test_orch.maybe_run_nightly_rollup(now=t_day1_1150pm) == 0

    # Day 2 02:40: not due yet
    t_day2_240am = day1_midnight + 24 * 3600.0 + 2.67 * 3600.0
    assert not is_rollup_due(restarted_ts, t_day2_240am, rollup_hour_local=3)
    assert test_orch.maybe_run_nightly_rollup(now=t_day2_240am) == 0

    # Day 2 03:10: due for Day 2!
    t_day2_310am = day1_midnight + 24 * 3600.0 + 3.17 * 3600.0
    assert is_rollup_due(restarted_ts, t_day2_310am, rollup_hour_local=3)
    test_orch.maybe_run_nightly_rollup(now=t_day2_310am)

    # Updated timestamp persisted
    assert refl_restarted.get_last_rollup_at() == t_day2_310am


def test_orchestrator_default_runtime_wiring_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 1 verification: Orchestrator default constructor wires live DB & MemoryStore with CPU embedder."""
    monkeypatch.setenv("LUCCA_HOME", str(tmp_path))
    from tests.fakes.fake_asr import FakeASR
    from tests.fakes.fake_llm import FakeLLM
    from tests.fakes.fake_tts import FakeTTS

    orch = Orchestrator(llm=FakeLLM(), tts=FakeTTS, asr=FakeASR, execute_tools=False)
    try:
        assert orch.db is not None
        assert orch.memory_store is not None
        worker = getattr(getattr(orch.memory_store, "embedding_port", None), "worker", None)
        assert worker is not None
        assert worker.device == "CPU"
    finally:
        orch.stop()


def test_turn_commit_writes_hmac_signatures(test_orch: Orchestrator) -> None:
    """Phase 1 verification: commits write rows into SQLite with valid HMAC-SHA256 signatures."""
    trace = TurnTrace(
        trace_id="tr-phase1-verify", session_id="s1", origin="text", mode="transcript"
    )
    test_orch.active_trace = trace
    t0 = time.perf_counter()

    # 1. Transcript commit
    user_entry_id = test_orch._commit_transcript("I live in Melbourne", trace)
    assert user_entry_id is not None

    # 2. Assistant utterance commit
    test_orch._commit_assistant_utterance("Got it, Melbourne is great.", trace)

    # 3. Action receipt commit
    test_orch.current_turn_receipts = [
        ToolReceipt(
            tool="self_metrics",
            ok=True,
            call_id="call-m1",
            args={},
            output='{"status": "ok"}',
        )
    ]
    test_orch._commit_action_receipts(trace)
    finalize_latency_ms = (time.perf_counter() - t0) * 1000.0
    assert finalize_latency_ms < 500.0, f"Finalize latency {finalize_latency_ms}ms too high"

    # Verification: SQLite has valid signed rows for all three
    assert test_orch.db is not None
    with test_orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT p.entry_id, p.provenance, p.signature, p.signer_id
            FROM provenance_envelopes p
            WHERE p.trace_id = 'tr-phase1-verify'
            """
        )
        rows = cur.fetchall()
        assert len(rows) >= 3
        provs = {r[1] for r in rows}
        assert "USER_EXPLICIT" in provs
        assert "ASSISTANT_UTTERANCE" in provs
        assert "ASSISTANT_ACTION" in provs
        for r in rows:
            sig = r[2]
            signer = r[3]
            assert sig and len(sig) == 44  # HMAC-SHA256 base64 digest is 44 chars
            assert signer and len(signer) > 0

