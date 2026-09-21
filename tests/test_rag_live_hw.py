"""
Project Lucca — Seeded RAG Live Hardware Battery (WP-4)
Work Order #8, §6.3  (F-TS-06)

All tests are @pytest.mark.hw — they require a live llama-server at
http://127.0.0.1:8080 (conftest.py fails fast if it is down).

Architecture note (mirrors the WP-3 A1 live pack):
  Orchestrator is constructed via __new__ + manual attribute wiring with a REAL
  LLMClient so responses come from the live gemma-4-12b-heretic model.  Audio
  (TTS/ASR/ZMQ/ring-buffers) is mocked to avoid hardware I/O.  No FakeLLM, no
  monkeypatched tools, no unittest.mock inside the assertion paths.

Tests:
  §6.3  test_live_rag_recall_abstention_conflict_battery
        60 probes (40 recall / 10 abstention / 10 conflict) over the seeded
        corpus; Wilson 95% LB >= 0.90; 0/10 conflict probes answered with the
        recollection; 0 fabrications on abstention probes.
        Reports -> logs/test_reports/rag_live_<ts>.json
  §6.3  test_live_rag_fast_path_three_turns
        D-ARCH-06 fast-path check: a fact stated in turn 1 (not seeded) is
        recalled in turn 3.

Run:  $env:LUCCA_TEST_TIER="T3"; uv run pytest -m hw -v
"""

from __future__ import annotations

import json
import queue
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock

import pytest

from lucca.brain.llm_client import LLMClient
from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import ExecutionTier
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.reasoning.stats import wilson_score_interval
from lucca.senses.embed import LocalEmbeddingPort
from tests.rag_harness import (
    MASTER_KEY,
    has_abstention,
    has_marker,
    load_probes,
    seed_rag_corpus,
    str_field,
    str_list_field,
    write_report,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WILSON_LB_TARGET: Final[float] = 0.90
CONFLICT_RECOLLECTION_WINS_ALLOWED: Final[int] = 0
ABSTENTION_FABRICATIONS_ALLOWED: Final[int] = 0


# ---------------------------------------------------------------------------
# Orchestrator factory — real LLM, mocked audio/ZMQ (WP-3 pattern)
# ---------------------------------------------------------------------------


def _make_rag_hw_orchestrator(tmp_path: Path) -> tuple[Orchestrator, MemoryStore, DatabaseManager]:
    """
    Build an Orchestrator wired for hardware testing:
      - Real LLMClient (llama-server at 127.0.0.1:8080)
      - Real MemoryStore backed by a fresh tmp SQLite DB
      - Mocked TTS, ASR, ZMQ, ring-buffers (no hardware audio I/O)
    """
    db_path = tmp_path / "hw_rag_memory.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()

    emb_port = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=MASTER_KEY, embedding_port=emb_port)
    refl = ReflectionEngine(db=db, store=store, master_key=MASTER_KEY)

    orch: Orchestrator = Orchestrator.__new__(Orchestrator)
    orch.config = get_config()
    orch.execute_tools = True
    orch.state = "idle"
    orch.running = True

    # Real LLM
    orch.llm = LLMClient()

    # Mocked audio/ZMQ
    orch.tts = MagicMock()
    orch.asr = MagicMock()
    orch._tts_queue = queue.Queue(maxsize=8)
    orch._tts_running = True
    orch.play_ring = MagicMock()
    orch.cap_ring = MagicMock()
    orch.ctx = MagicMock()
    orch.ctl_sock = MagicMock()
    orch.bus_sock = MagicMock()
    orch.ingest_sock = MagicMock()
    orch.chunker = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.sandbox = MagicMock()
    orch.sandbox.reset_turn = MagicMock()
    orch.sandbox.execute_apps = True

    # Memory / reflection
    orch.db = db
    orch.memory_store = store
    orch.reflection_engine = refl

    # Signers
    orch.user_signer = UserSpeechSigner(master_key=MASTER_KEY)
    orch.assistant_signer = AssistantUtteranceSigner(master_key=MASTER_KEY)
    orch.breach_signer = CoherenceBreachSigner(master_key=MASTER_KEY)

    # Turn state
    orch.current_turn_receipts = []
    orch.current_turn_tool_calls = []
    orch.current_turn_tier = ExecutionTier.FULL_LOOP
    orch.current_turn_tool_spoken = []
    orch.current_turn_tool_ok = True
    orch.current_turn_shadow_outcomes = []
    orch.pending_spoken_updates = deque()
    orch.history = []
    orch.executed_tools = []
    orch.current_turn_transcript = None
    orch.current_turn_assistant_reply = None
    orch.active_trace = None
    orch.active_turn_thread = None
    orch.prev_decision_record = None
    orch.prev_turn_ts = None
    orch.session_id = f"rag-hw-{uuid.uuid4().hex[:8]}"
    orch.active_detected_words = []
    orch._last_unspoken_tool_msg = None
    orch.quit_requested = False
    orch._last_ptt_press_ns = 0
    orch._last_pong = {}
    orch._confirm_event = MagicMock()
    orch._confirm_result = False
    orch._pending_confirmation_active = False
    orch._confirm_audio = None
    orch._confirm_via = None
    orch._confirm_lock = MagicMock()

    # Router and cascade
    from lucca.core.affect import AffectTracker
    from lucca.core.bdi_validator import SpeculativeBDIValidator
    from lucca.core.cascade import EpistemicSearchCascade
    from lucca.reasoning.lifecycle import RuleLifecycleManager

    orch.cascade = EpistemicSearchCascade(
        sandbox=orch.sandbox,
        memory_store=orch.memory_store,
    )
    orch.bdi_validator = SpeculativeBDIValidator(workspace_root=tmp_path / "workspace")
    orch.affect_tracker = AffectTracker()
    orch.rule_engine = RuleLifecycleManager(skills_dir=None)

    from lucca.router.heuristic import HeuristicRouter

    orch.router = HeuristicRouter(db=db, log_path=tmp_path / "decisions.jsonl")

    # Mock methods that require ZMQ/audio
    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._set_state = MagicMock()
    orch._tts_thread = MagicMock()

    return orch, store, db


def _invoke_text_turn(orch: Orchestrator, user_text: str, trace_id: str) -> str:
    """Drive a full FULL_LOOP text turn and return the assistant's final reply."""
    trace = TurnTrace(
        trace_id=trace_id,
        session_id=orch.session_id or "rag-hw",
        origin="text",
        mode="transcript",
    )
    orch.active_trace = trace
    orch._run_text_turn(trace, user_text)
    for msg in reversed(orch.history):
        if msg.get("role") == "assistant":
            return str(msg.get("content", ""))
    return ""


# ---------------------------------------------------------------------------
# §6.3 — 60-probe live battery
# ---------------------------------------------------------------------------


@pytest.mark.hw
def test_live_rag_recall_abstention_conflict_battery(tmp_path: Path) -> None:
    """
    WP-4 §6.3 — 60 probes over the seeded corpus with the real model:
      - 40 recall (expected: entailed, must_contain)
      - 10 abstention (expected: abstain; 0 fabrications allowed)
      - 10 conflict (expected: fact_wins; 0/10 recollection wins allowed)
    Wilson 95% LB over all 60 must be >= 0.90.
    """
    orch, store, _db = _make_rag_hw_orchestrator(tmp_path)
    now = time.time()
    seed_rag_corpus(store, now)

    passed = 0
    fabrications = 0
    recollection_wins = 0
    per_probe: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for probe in load_probes():
        probe_id = str_field(probe, "id")
        expected = str_field(probe, "expected")
        question = str_field(probe, "question")
        must_contain = str_list_field(probe, "must_contain")
        must_not_contain = str_list_field(probe, "must_not_contain")

        reply = _invoke_text_turn(orch, question, f"tr-rag-live-{probe_id}")

        ok = False
        fabricated = False
        recollection_win = False
        reason = ""

        if expected == "entailed":
            ok = has_marker(reply, must_contain)
            if not ok:
                reason = f"must_contain not satisfied: {must_contain}"
        elif expected == "abstain":
            if not has_abstention(reply):
                fabricated = True
                reason = "Missing abstention phrase — possible fabrication"
            elif has_marker(reply, must_not_contain):
                fabricated = True
                reason = f"Fabrication marker found: {must_not_contain}"
            ok = not fabricated
        elif expected == "fact_wins":
            if has_marker(reply, must_not_contain):
                recollection_win = True
                reason = f"Recollection value surfaced instead of fact: {must_not_contain}"
            elif not has_marker(reply, must_contain):
                reason = f"Fact value missing from reply: {must_contain}"
            ok = not recollection_win and has_marker(reply, must_contain)

        if fabricated:
            fabrications += 1
        if recollection_win:
            recollection_wins += 1
        if ok:
            passed += 1
        else:
            failures.append(
                {
                    "id": probe_id,
                    "expected": expected,
                    "question": question,
                    "reply": reply[:300],
                    "reason": reason,
                }
            )

        per_probe.append(
            {
                "id": probe_id,
                "expected": expected,
                "question": question,
                "reply": reply[:500],
                "pass": ok,
                "fabricated": fabricated,
                "recollection_win": recollection_win,
            }
        )

    total = len(per_probe)
    lb, ub = wilson_score_interval(passed, total)
    report_path = write_report(
        "rag_live",
        {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "wilson_lb": lb,
            "wilson_ub": ub,
            "abstention_fabrications": fabrications,
            "conflict_recollection_wins": recollection_wins,
            "per_probe": per_probe,
            "failures": failures,
        },
    )

    assert fabrications == ABSTENTION_FABRICATIONS_ALLOWED, (
        f"{fabrications} fabricated answer(s) on abstention probes — hard failure.\n"
        f"Report: {report_path}\n{json.dumps(failures[:10], indent=2)}"
    )
    assert recollection_wins == CONFLICT_RECOLLECTION_WINS_ALLOWED, (
        f"{recollection_wins}/10 conflict probes answered with the recollection "
        f"(allowed {CONFLICT_RECOLLECTION_WINS_ALLOWED}).\n"
        f"Report: {report_path}\n{json.dumps(failures[:10], indent=2)}"
    )
    assert lb >= WILSON_LB_TARGET, (
        f"Wilson 95% LB {lb:.4f} < {WILSON_LB_TARGET} (passed {passed}/{total}).\n"
        f"Report: {report_path}\n{json.dumps(failures[:10], indent=2)}"
    )


# ---------------------------------------------------------------------------
# §6.3 — D-ARCH-06 fast-path check (3 consecutive turns)
# ---------------------------------------------------------------------------


@pytest.mark.hw
def test_live_rag_fast_path_three_turns(tmp_path: Path) -> None:
    """
    WP-4 §6.3 — D-ARCH-06 fast-path context sync: run 3 consecutive turns where
    turn 3 depends on a fact stated in turn 1 (not seeded) — assert it is
    recalled.
    """
    orch, _store, _db = _make_rag_hw_orchestrator(tmp_path)

    reply_1 = _invoke_text_turn(
        orch, "Please remember that my sister's name is Priya.", "tr-fast-1"
    )
    assert reply_1.strip(), "Turn 1 produced an empty reply"

    reply_2 = _invoke_text_turn(orch, "Thanks, good to know.", "tr-fast-2")
    assert reply_2.strip(), "Turn 2 produced an empty reply"

    reply_3 = _invoke_text_turn(orch, "What is my sister's name?", "tr-fast-3")

    write_report(
        "rag_live_fast_path",
        {
            "turn_1_reply": reply_1[:500],
            "turn_2_reply": reply_2[:500],
            "turn_3_reply": reply_3[:500],
            "recalled": "priya" in reply_3.lower(),
        },
    )

    assert "priya" in reply_3.lower(), (
        f"D-ARCH-06 fast-path miss: turn 3 reply did not recall the turn-1 fact.\n"
        f"Turn 3 reply: {reply_3[:300]}"
    )
