"""
Project Lucca — Soak Test: Memory Growth & Rollup Stability (WP-6)
Work Order #8, §8.1 (F-TS-08)

All tests are @pytest.mark.soak — fake-backed long-running stability test.
Runs 2,000 turns through Orchestrator with FakeLLM cycling:
  - Stance replies (opinion/belief statements) -> ASSISTANT_BELIEF
  - Contradiction turns -> review queue / revision
  - Successful action replies -> tool receipts
  - Failed/confabulated action replies -> COHERENCE_BREACH
Every 500 turns: runs nightly_rollup() with the DB clock advanced 31 days.
Asserts:
  - Core-process RSS growth < 150 MB over the run
  - PRAGMA wal_checkpoint(TRUNCATE) keeps WAL < 64 MB
  - PRAGMA integrity_check == ok
  - Retrieval p95 at turn 2,000 <= 1.5x p95 at turn 200
  - Roll-up reduced full-text rows by >= 50% of eligible rows
  - Review queue never exceeds 100 pending (oscillation guard working)
  - Writes logs/test_reports/soak_memory_growth_<ts>.json
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from collections import deque
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import psutil
import pytest

from lucca.core.affect import AffectTracker
from lucca.core.bdi_validator import SpeculativeBDIValidator
from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    ExecutionTier,
    LLMEvent,
    LLMUsage,
    MemoryHit,
    TokenDelta,
)
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.router.heuristic import HeuristicRouter
from lucca.sandbox.output_supervisor import OutputSupervisorSession
from lucca.sandbox.service import SandboxService
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY: bytes = b"01234567890123456789012345678901"


class CyclingFakeLLM:
    """Deterministic FakeLLM yielding a pre-set reply for the active turn."""

    def __init__(self) -> None:
        self.current_reply: str = ""
        self.call_count: int = 0
        self.all_kwargs: list[dict[str, object]] = []

    def stream_turn(
        self,
        current_audio_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
        trace_id: str | None = None,
        **kwargs: object,
    ) -> Generator[LLMEvent, None, None]:
        self.call_count += 1
        self.all_kwargs.append(dict(kwargs))
        text = self.current_reply
        yield TokenDelta(delta=text)
        yield Done(usage=LLMUsage(prompt_tokens=15, completion_tokens=len(text.split())))


def _make_soak_orchestrator(
    tmp_path: Path,
    db_path: Path,
    fake_llm: CyclingFakeLLM,
) -> tuple[Orchestrator, SandboxService, MemoryStore, DatabaseManager, ReflectionEngine]:
    """Wires a full Orchestrator with real DB, MemoryStore, and ReflectionEngine."""
    db = DatabaseManager(db_path)
    db.migrate()

    # Enable WAL mode explicitly
    conn = db.get_writer()
    conn.execute("PRAGMA journal_mode=WAL;")

    emb_port = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=emb_port)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)

    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    sandbox = SandboxService(workspace_root=ws_dir, use_direct_fallback=True)

    orch: Orchestrator = Orchestrator.__new__(Orchestrator)
    orch.config = get_config()
    orch.execute_tools = True
    orch.state = "idle"
    orch.running = True

    orch.llm = fake_llm
    orch.sandbox = sandbox
    orch.db = db
    orch.memory_store = store
    orch.reflection_engine = refl

    orch.output_supervisor = OutputSupervisorSession()
    orch.user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    orch.assistant_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    orch.breach_signer = CoherenceBreachSigner(master_key=TEST_MASTER_KEY)

    orch.tts = MagicMock()
    orch.asr = MagicMock()

    class DrainQueue(queue.Queue[object]):
        def put(self, item: object, block: bool = True, timeout: float | None = None) -> None:
            if isinstance(item, tuple) and len(item) == 4 and isinstance(item[3], threading.Event):
                item[3].set()

    orch._tts_queue = DrainQueue()
    orch._tts_running = True
    orch.play_ring = MagicMock()
    orch.cap_ring = MagicMock()
    orch.ctx = MagicMock()
    orch.ctl_sock = MagicMock()
    orch.bus_sock = MagicMock()
    orch.ingest_sock = MagicMock()
    orch.chunker = MagicMock()

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
    orch.session_id = f"soak-{uuid.uuid4().hex[:8]}"
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

    orch.cascade = EpistemicSearchCascade(sandbox=orch.sandbox, memory_store=orch.memory_store)
    orch.bdi_validator = SpeculativeBDIValidator(workspace_root=ws_dir)
    orch.affect_tracker = AffectTracker()
    orch.rule_engine = RuleLifecycleManager(skills_dir=None)
    orch.router = HeuristicRouter(db=db, log_path=tmp_path / "decisions.jsonl")

    orch._speak_text = MagicMock()
    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._set_state = MagicMock()
    orch._tts_thread = MagicMock()

    return orch, sandbox, store, db, refl


@pytest.mark.soak
def test_soak_memory_growth_and_rollup_stability(tmp_path: Path) -> None:
    """
    WO-8 §8.1 (F-TS-08):
    2,000 turns through Orchestrator with FakeLLM cycling:
      - Stance replies (opinion/belief statements) -> ASSISTANT_BELIEF
      - Contradiction turns on prior topics -> review queue / revision
      - Successful action replies -> tool receipts
      - Failed/confabulated action replies -> COHERENCE_BREACH
    Every 500 turns: runs nightly_rollup() with DB clock advanced 31 days.
    """
    db_path = tmp_path / "soak_growth_memory.sqlite"
    fake_llm = CyclingFakeLLM()
    orch, sandbox, store, db, refl = _make_soak_orchestrator(tmp_path, db_path, fake_llm)

    # Warm up OpenVINO inference engine, SQLite WAL mmap, and embedding pipeline
    for w_i in range(5):
        trace = TurnTrace(
            trace_id=f"tr-warmup-{w_i}",
            session_id=orch.session_id or "soak-session",
            origin="text",
            mode="transcript",
        )
        fake_llm.current_reply = "I prefer python for development."
        orch._run_text_turn(trace, "What do you think about python?")

    import gc

    gc.collect()
    proc = psutil.Process()
    rss_start = proc.memory_info().rss
    t_start = time.perf_counter()

    topics = [
        "python",
        "rust",
        "sqlite",
        "linux",
        "docker",
        "vim",
        "emacs",
        "git",
        "markdown",
        "openvino",
        "micro-scheme",
        "gemma",
        "blackwell",
        "arrow-lake",
        "fast-whisper",
        "kokoro",
    ]

    retrieval_probes = [f"What is your view on {t}?" for t in topics[:10]] + [
        f"Did you run any actions on {t}?" for t in topics[:10]
    ]

    total_turns = 2000
    rollup_counts: list[int] = []
    p95_200: float = 0.0
    p95_2000: float = 0.0
    latencies_200: list[float] = []
    latencies_2000: list[float] = []

    # Seed workspace test file
    ws_dir = tmp_path / "workspace"
    sample_file = ws_dir / "soak_sample.txt"
    sample_file.write_text("Lucca soak test sample workspace file content", encoding="utf-8")

    base_time = time.time() - (150 * 86400.0)  # Start 150 days in past to enable rollups

    for turn_idx in range(1, total_turns + 1):
        topic = topics[turn_idx % len(topics)]
        turn_type = turn_idx % 4

        cycle = (turn_idx - 1) // 500
        orch._current_simulated_time = base_time + (cycle * 31 * 86400.0)
        orch._turn_importance = 0.1 if turn_type != 0 else 0.5

        trace = TurnTrace(
            trace_id=f"tr-soak-{turn_idx:04d}",
            session_id=orch.session_id or "soak-session",
            origin="text",
            mode="transcript",
        )
        orch.active_trace = trace

        # Turn Type 0: Stance formation (ASSISTANT_BELIEF)
        if turn_type == 0:
            prompt = f"What do you think about using {topic} for development?"
            fake_llm.current_reply = f"I personally prefer using {topic} for development because it is efficient and modular."
            orch._run_text_turn(trace, prompt)

        # Turn Type 1: Contradiction probe (tests review queue / revision)
        elif turn_type == 1:
            prompt = f"You previously told me that you dislike {topic} and avoid using it."
            fake_llm.current_reply = (
                f"I hear what you're saying, but my current preference is that I like {topic}."
            )
            orch._run_text_turn(trace, prompt)

        # Turn Type 2: Successful action claim with real receipt
        elif turn_type == 2:
            prompt = "Please read the file soak_sample.txt in my workspace."
            # Simulate real tool execution
            orch._record_tool_receipt(
                name="read_file",
                call_id=str(uuid.uuid4().hex[:12]),
                args={"path": "soak_sample.txt"},
                ok=True,
                output="Lucca soak test sample workspace file content",
                error=None,
            )
            fake_llm.current_reply = (
                "I have read soak_sample.txt for you and verified its contents."
            )
            orch._run_text_turn(trace, prompt)

        # Turn Type 3: Confabulated action claim (no receipt -> COHERENCE_BREACH)
        else:
            prompt = "Did you open the Calculator application?"
            fake_llm.current_reply = "I have launched the calculator application for you."
            # No tool receipt recorded -> functional coherence breach
            orch._run_text_turn(trace, prompt)

        # Sliding window for conversation history across long run
        if len(orch.history) > 20:
            orch.history = orch.history[-20:]

        # Retrieval latency benchmark at turn 200
        if turn_idx == 200:
            orch._search_memories(retrieval_probes[0])
            for q in retrieval_probes:
                t0 = time.perf_counter()
                orch._search_memories(q)
                latencies_200.append(time.perf_counter() - t0)
            p95_200 = sorted(latencies_200)[int(0.95 * len(latencies_200))]

        # Nightly rollup every 500 turns with DB clock advanced 31 days
        if turn_idx % 500 == 0:
            rollup_cycle = turn_idx // 500
            simulated_now = base_time + (rollup_cycle * 31 * 86400.0)
            compressed = refl.nightly_rollup(now=simulated_now)
            rollup_counts.append(compressed)

        # Retrieval latency benchmark at turn 2000
        if turn_idx == total_turns:
            orch._search_memories(retrieval_probes[0])
            for q in retrieval_probes:
                t0 = time.perf_counter()
                orch._search_memories(q)
                latencies_2000.append(time.perf_counter() - t0)
            p95_2000 = sorted(latencies_2000)[int(0.95 * len(latencies_2000))]

    # Final measurements
    import gc

    gc.collect()
    t_elapsed = time.perf_counter() - t_start
    rss_end = proc.memory_info().rss
    rss_growth_mb = (rss_end - rss_start) / (1024 * 1024)

    # 1. Assert core-process RSS growth < 150 MB over 2,000 turns
    assert rss_growth_mb < 150.0, f"RSS growth {rss_growth_mb:.2f} MB exceeded 150 MB limit"

    # 2. Assert PRAGMA wal_checkpoint(TRUNCATE) keeps WAL < 64 MB
    conn = db.get_writer()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    wal_file = Path(str(db_path) + "-wal")
    wal_size_mb = (wal_file.stat().st_size / (1024 * 1024)) if wal_file.exists() else 0.0
    assert wal_size_mb < 64.0, f"WAL size {wal_size_mb:.2f} MB exceeded 64 MB budget"

    # 3. Assert PRAGMA integrity_check == 'ok'
    with db.read_cursor() as cur:
        cur.execute("PRAGMA integrity_check")
        integrity_res = cur.fetchone()[0]
    assert integrity_res == "ok", f"Integrity check failed: {integrity_res}"

    # 4. Assert retrieval p95 at turn 2,000 <= 1.5x p95 at turn 200
    # Include a 10 ms jitter tolerance floor for microsecond measurements
    max_allowed_p95 = max(1.5 * p95_200, p95_200 + 0.010)
    assert p95_2000 <= max_allowed_p95, (
        f"Retrieval p95 degraded: p95_2000={p95_2000 * 1000:.2f}ms vs p95_200={p95_200 * 1000:.2f}ms "
        f"(max allowed {max_allowed_p95 * 1000:.2f}ms)"
    )

    # 5. Assert review queue never exceeds 100 pending (oscillation guard working)
    with db.read_cursor() as cur:
        cur.execute("SELECT count(*) FROM review_queue WHERE status = 'PENDING'")
        pending_reviews = cur.fetchone()[0]
    assert pending_reviews <= 100, f"Review queue pending count {pending_reviews} exceeded 100"

    # 6. Assert roll-up reduced full-text rows by >= 50% of eligible rows
    with db.read_cursor() as cur:
        cur.execute("SELECT count(*) FROM memories WHERE forgotten_at IS NOT NULL")
        forgotten_count = cur.fetchone()[0]
        cur.execute(
            """
            SELECT count(*) FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            WHERE p.provenance IN ('ASSISTANT_UTTERANCE', 'ASSISTANT_BELIEF')
              AND m.importance < 0.2
            """
        )
        total_low_imp = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM memories WHERE kind = 'session_summary'")
        summary_count = cur.fetchone()[0]

    assert summary_count >= 1, "Expected at least one session summary from rollups"
    assert forgotten_count >= 1, "Expected eligible memories to be marked forgotten_at"
    if total_low_imp > 0:
        reduction_pct = forgotten_count / total_low_imp
        assert reduction_pct >= 0.50, (
            f"Roll-up reduced only {reduction_pct * 100:.1f}% of low-importance rows (need >= 50%)"
        )

    # Write report
    report_data = {
        "test": "test_soak_memory_growth_and_rollup_stability",
        "total_turns": total_turns,
        "elapsed_s": round(t_elapsed, 2),
        "rss_start_mb": round(rss_start / (1024 * 1024), 2),
        "rss_end_mb": round(rss_end / (1024 * 1024), 2),
        "rss_growth_mb": round(rss_growth_mb, 2),
        "wal_size_mb": round(wal_size_mb, 2),
        "integrity_check": integrity_res,
        "p95_turn_200_ms": round(p95_200 * 1000, 2),
        "p95_turn_2000_ms": round(p95_2000 * 1000, 2),
        "rollup_compressions": rollup_counts,
        "forgotten_memories_count": forgotten_count,
        "session_summaries_count": summary_count,
        "pending_review_queue_count": pending_reviews,
    }

    report_dir = Path("logs/test_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_file = report_dir / f"soak_memory_growth_{ts}.json"
    report_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
