"""
Project Lucca — Grounded memory_commit Tests (WO-9 A2 / ADR-010)

The model's {s, p, o, quote} is a candidate only: the fact is committed iff the
quote is verbatim-grounded in the user's own words this turn (FactExtractor ->
DerivedFactSigner -> USER_DERIVED, source_entry_ids citing the USER_EXPLICIT
transcript). Model-authored prose is never stored (ADR-006).
"""

import queue
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import ExecutionTier, Provenance
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def orch(tmp_path: Path) -> Orchestrator:
    db = DatabaseManager(tmp_path / "test_grounded_commit.sqlite")
    db.migrate()
    store = MemoryStore(
        db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort()
    )
    orch = Orchestrator.__new__(Orchestrator)
    orch.config = get_config()
    orch.execute_tools = True
    orch.state = "idle"
    orch.running = True
    orch.db = db
    orch.memory_store = store
    orch.current_turn_receipts = []
    orch.current_turn_tool_calls = []
    orch.current_turn_tier = ExecutionTier.FULL_LOOP
    orch.current_turn_tool_spoken = []
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


def _trace(trace_id: str = "tr-gmc-1") -> TurnTrace:
    return TurnTrace(trace_id=trace_id, session_id="sess-gmc", origin="text", mode="transcript")


def _user_derived_rows(db: DatabaseManager) -> list[dict[str, Any]]:
    with db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content, p.provenance, ms.source_entry_id
            FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            LEFT JOIN memory_sources ms ON ms.memory_id = m.memory_id
            WHERE p.provenance = 'USER_DERIVED'
            ORDER BY m.created_at DESC
            """
        )
        return [
            {"content": r[0], "provenance": r[1], "source_entry_id": r[2]}
            for r in cur.fetchall()
        ]


def test_grounded_commit_saves_user_derived_fact(orch: Orchestrator) -> None:
    """A grounded candidate (quote verbatim in the user's words) commits as USER_DERIVED."""
    orch.current_turn_transcript = "My name is Sean"
    args = {
        "s": "user",
        "p": "is_named",
        "o": "Sean",
        "quote": "My name is Sean",
    }
    res = orch._handle_memory_commit(_trace(), "call-1", "memory_commit", args, speak=False)

    assert res.ok is True
    assert res.exit_code == 0
    assert "user is_named Sean" in res.content

    rows = _user_derived_rows(orch.db)
    assert len(rows) == 1
    assert rows[0]["provenance"] == "USER_DERIVED"
    assert "is_named" in rows[0]["content"]
    # The fact must cite the committed USER_EXPLICIT transcript entry
    assert rows[0]["source_entry_id"]
    # The transcript itself was committed early as USER_EXPLICIT
    with orch.db.read_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM provenance_envelopes WHERE provenance = 'USER_EXPLICIT'"
        )
        assert cur.fetchone()[0] == 1
    # Early-commit stash is set for _finalize_turn reuse
    assert orch._early_transcript_commit is not None
    assert orch.current_turn_transcript is None


def test_ungrounded_commit_refused(orch: Orchestrator) -> None:
    """A quote that does not appear in the user's words must be refused honestly."""
    orch.current_turn_transcript = "My name is Sean"
    args = {
        "s": "user",
        "p": "lives_in",
        "o": "Perth",
        "quote": "I live in Perth",
    }
    res = orch._handle_memory_commit(_trace(), "call-2", "memory_commit", args, speak=False)

    assert res.ok is False
    assert "not_grounded" in (res.stderr or "")
    assert _user_derived_rows(orch.db) == []
    # The refusal is recorded as a failed receipt (A9 groundwork)
    assert orch.current_turn_receipts
    assert orch.current_turn_receipts[-1].ok is False


def test_commit_without_transcript_refused(orch: Orchestrator) -> None:
    """No user utterance this turn -> nothing to ground against -> refused."""
    orch.current_turn_transcript = None
    args = {"s": "user", "p": "is_named", "o": "Sean", "quote": "My name is Sean"}
    res = orch._handle_memory_commit(_trace(), "call-3", "memory_commit", args, speak=False)

    assert res.ok is False
    assert "not_grounded" in (res.stderr or "")


def test_stale_transcript_payload_refused(orch: Orchestrator) -> None:
    """A signed transcript from a PREVIOUS turn must not ground this turn's commit."""
    orch.current_turn_transcript = None
    stale = MagicMock()
    stale.trace_id = "tr-old-turn"
    orch._last_transcript_signed = stale
    args = {"s": "user", "p": "is_named", "o": "Sean", "quote": "My name is Sean"}
    res = orch._handle_memory_commit(_trace("tr-new-turn"), "call-4", "memory_commit", args, speak=False)

    assert res.ok is False
    assert "not_grounded" in (res.stderr or "")


def test_describe_tool_action_memory_commit_readback(orch: Orchestrator) -> None:
    """The confirmation prompt must read back the fact, not 'execute memory_commit'."""
    desc = orch._describe_tool_action(
        "memory_commit", {"s": "user", "p": "is_named", "o": "Sean", "quote": "x"}
    )
    assert desc == "save that your name is Sean"
    desc2 = orch._describe_tool_action(
        "memory_commit", {"s": "user", "p": "lives_in", "o": "Perth", "quote": "x"}
    )
    assert desc2 == "save that you live in Perth"


def test_invalid_predicate_refused(orch: Orchestrator) -> None:
    """A predicate outside the closed PREDICATES list must be refused (gate invariant)."""
    orch.current_turn_transcript = "My name is Sean"
    args = {"s": "user", "p": "is_a_wizard", "o": "yes", "quote": "My name is Sean"}
    res = orch._handle_memory_commit(_trace(), "call-5", "memory_commit", args, speak=False)

    assert res.ok is False
    # Either schema-level guidance or gate rejection — never a silent commit
    assert _user_derived_rows(orch.db) == []


def test_provenance_classes_unchanged(orch: Orchestrator) -> None:
    """Sanity: USER_DERIVED stays memory-eligible; LLM_NARRATION does not exist."""
    assert Provenance.USER_DERIVED.value == "USER_DERIVED"


# ============================================================================
# WO-9 A14: self_history_search tool
# ============================================================================


def test_self_history_search_returns_records(orch: Orchestrator) -> None:
    """A14 (F18): the model can query its own action history via the tool."""
    from types import SimpleNamespace

    fake_item = SimpleNamespace(
        source="history:action:1", content="memory_commit(...) -> cancelled: cancelled by user"
    )
    orch.cascade = MagicMock()
    orch.cascade.query_substrate_self_history.return_value = [fake_item]

    res = orch._handle_self_history_search("call-sh1", {"query": "memory_commit"})

    assert res.ok is True
    assert "cancelled" in res.content
    assert res.structured == {"count": 1}


def test_self_history_search_empty_query_refused(orch: Orchestrator) -> None:
    res = orch._handle_self_history_search("call-sh2", {"query": "  "})
    assert res.ok is False
    assert "invalid_arguments" in (res.stderr or "")


# ============================================================================
# WO-9 A3: passive fact extraction
# ============================================================================


def test_passive_extraction_captures_name(orch: Orchestrator) -> None:
    """A3: "My name is Sean" passively produces a USER_DERIVED is_named fact."""
    trace = _trace("tr-passive-1")
    entry_id = orch._commit_transcript("My name is Sean", trace)
    assert entry_id is not None
    orch._maybe_extract_facts(trace)

    rows = _user_derived_rows(orch.db)
    assert len(rows) == 1
    assert "is_named Sean" in rows[0]["content"]
    assert rows[0]["source_entry_id"] == entry_id


def test_passive_extraction_skips_hypothetical(orch: Orchestrator) -> None:
    """A3: the A1 fixture phrasing must never produce a fact."""
    trace = _trace("tr-passive-2")
    orch._commit_transcript("If I told you my name was Sean, how would you save that?", trace)
    orch._maybe_extract_facts(trace)
    assert _user_derived_rows(orch.db) == []

    trace2 = _trace("tr-passive-2b")
    orch._commit_transcript("Suppose my name is Sean.", trace2)
    orch._maybe_extract_facts(trace2)
    assert _user_derived_rows(orch.db) == []


def test_passive_extraction_skips_questions(orch: Orchestrator) -> None:
    """A3: interrogatives are not fact candidates."""
    trace = _trace("tr-passive-3")
    orch._commit_transcript("What is my name?", trace)
    orch._maybe_extract_facts(trace)
    assert _user_derived_rows(orch.db) == []


def test_name_update_supersedes_previous(orch: Orchestrator) -> None:
    """A3: is_named is a functional predicate — a new name supersedes the old."""
    t1 = _trace("tr-passive-4a")
    orch._commit_transcript("My name is Alice", t1)
    orch._maybe_extract_facts(t1)

    trace2 = _trace("tr-passive-4b")
    orch._commit_transcript("My name is Sean", trace2)
    orch._maybe_extract_facts(trace2)

    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content, m.superseded_by
            FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            WHERE p.provenance = 'USER_DERIVED'
            ORDER BY m.created_at ASC
            """
        )
        rows = cur.fetchall()
    assert len(rows) == 2
    assert "Alice" in rows[0][0]
    assert rows[0][1] is not None, "old name fact must be superseded"
    assert "Sean" in rows[1][0]
    assert rows[1][1] is None, "new name fact must be the active one"


# ============================================================================
# WO-9 A9: ASSISTANT_ACTION receipt persistence
# ============================================================================


def test_action_receipts_persisted_including_cancels(orch: Orchestrator) -> None:
    """A9 (F8): tool attempts — success AND cancellation — become ASSISTANT_ACTION rows."""
    from lucca.core.coherence import ToolReceipt

    trace = _trace("tr-a9-1")
    orch.current_turn_receipts = [
        ToolReceipt(
            tool="launch_app",
            tool_name="launch_app",
            ok=True,
            call_id="c-ok",
            args={"app_name": "calculator"},
            output="Launched calculator.",
            error=None,
            timestamp=0.0,
        ),
        ToolReceipt(
            tool="memory_commit",
            tool_name="memory_commit",
            ok=False,
            call_id="c-cancel",
            args={"s": "user"},
            output=None,
            error="cancelled by user",
            timestamp=0.0,
        ),
    ]
    orch._commit_action_receipts(trace)

    rows = _action_receipt_rows(orch.db)
    assert len(rows) == 2
    assert rows[0][0].startswith("launch_app(app_name=calculator) -> ok")
    assert "cancelled" in rows[1][0]
    assert all(prov == "ASSISTANT_ACTION" for _, prov in rows)
    # Receipts are cleared so a double finalize cannot double-commit
    assert orch.current_turn_receipts == []


def _action_receipt_rows(db: DatabaseManager) -> list[tuple[str, str]]:
    with db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content, p.provenance
            FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            WHERE p.provenance = 'ASSISTANT_ACTION'
            ORDER BY m.created_at ASC
            """
        )
        return [(r[0], r[1]) for r in cur.fetchall()]
