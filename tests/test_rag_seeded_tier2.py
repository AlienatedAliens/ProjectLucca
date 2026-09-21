"""
Project Lucca — Seeded RAG Harness, Tier 2 (WP-4)
Work Order #8, §6.1–6.2  (F-TS-06)

Harness: real MemoryStore (tmp SQLite DB) + real LocalEmbeddingPort (384-D
MiniLM) + real signers; the ONLY fake is FakeLLM, which records the exact
kwargs (memories / messages) the orchestrator built for each turn.

Assertions per §6.2:
  1. Recall probes: the built prompt contains the target fact (recall@k within
     the 2,048-token D-MEM-03 quota).
  2. Recollections are never framed as evidence: every ASSISTANT_UTTERANCE hit
     is grounding_eligible=False and, whenever it appears in the rendered
     memory context, its line carries the ASSISTANT_UTTERANCE provenance tag
     (or the D-MEM-04 "[Recollections (Non-Grounding)]" cascade frame).
  3. Abstention probes: no near-miss distractor is retrieved above the
     relevance floor (cross-channel RRF agreement).
  4. Quota utilisation is recorded for every probe (never exceeds budget).

Run:  $env:LUCCA_TEST_TIER="T2"; uv run pytest -m tier2 -q
"""

from __future__ import annotations

import queue
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock

import pytest

from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Done, ExecutionTier, LLMUsage, MemoryHit, Provenance, TokenDelta
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.retrieval import RRF_K_CONST, format_memory_context
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM
from tests.rag_harness import (
    MASTER_KEY,
    load_corpus,
    load_probes,
    seed_rag_corpus,
    str_field,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUOTA_TOKENS: Final[int] = 2048
QUOTA_CHAR_BUDGET: Final[int] = QUOTA_TOKENS * 4  # format_memory_context approx 4 chars/token

# Relevance floor for §6.2 abstention assertion: a hit only counts as
# "retrieved" (not a lexical accident) when BOTH the dense (sqlite-vec) and
# sparse (FTS5 BM25) channels independently surface it.  With Reciprocal Rank
# Fusion (k=60) a single-channel rank-1 hit scores 1/(k+1) ~= 0.0164, which is
# below the floor; cross-channel agreement always exceeds it.
RELEVANCE_FLOOR: Final[float] = 1.5 / (RRF_K_CONST + 1)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class ProbeRecord:
    """Per-probe capture of retrieval + rendered prompt context."""

    probe_id: str
    kind: str
    question: str
    target_fact_id: str
    target_content: str
    hits: list[MemoryHit] = field(default_factory=list)
    context: str = ""
    epistemic_context: str = ""

    @property
    def target_in_context(self) -> bool:
        return self.target_content.lower() in self.context.lower()

    @property
    def target_in_hits(self) -> bool:
        return any(hit.content == self.target_content for hit in self.hits)

    @property
    def context_chars(self) -> int:
        return len(self.context)


@dataclass
class RagBattery:
    """Result of running the full 60-probe battery once against the harness."""

    store: MemoryStore
    db: DatabaseManager
    orch: Orchestrator
    fake_llm: FakeLLM
    memory_ids: dict[str, int]
    corpus_by_id: dict[str, dict[str, object]]
    records: dict[str, ProbeRecord]
    now: float


# ---------------------------------------------------------------------------
# Orchestrator factory — real MemoryStore/embeddings, FakeLLM recorder
# ---------------------------------------------------------------------------


def _make_t2_orchestrator(
    tmp_path: Path,
) -> tuple[Orchestrator, MemoryStore, DatabaseManager, FakeLLM]:
    """Wire an Orchestrator exactly like the WP-3 hw factory but with FakeLLM."""
    db_path = tmp_path / "t2_rag_memory.sqlite"
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

    # FakeLLM recorder — captures memories/messages kwargs of every turn
    fake_llm = FakeLLM(
        script=[
            TokenDelta(delta="Okay. "),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=2)),
        ]
    )
    orch.llm = fake_llm

    # Mocked audio/ZMQ (no hardware I/O in T2)
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
    orch.session_id = "t2-rag-session"
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

    return orch, store, db, fake_llm


# ---------------------------------------------------------------------------
# Battery runner (module-scoped: seeds once, runs all 60 probes once)
# ---------------------------------------------------------------------------


def _run_probe(battery: RagBattery, probe: dict[str, object]) -> ProbeRecord:
    probe_id = str_field(probe, "id")
    question = str_field(probe, "question")
    target_fact_id = str_field(probe, "target_fact_id")
    target_row = battery.corpus_by_id.get(target_fact_id, {})
    target_content = str_field(target_row, "content")

    trace = TurnTrace(
        trace_id=f"tr-rag-t2-{probe_id}",
        session_id=battery.orch.session_id or "t2-rag-session",
        origin="text",
        mode="transcript",
    )
    battery.orch.active_trace = trace
    battery.orch._run_text_turn(trace, question)

    memories: list[MemoryHit] = battery.fake_llm.last_memories or []
    context = format_memory_context(memories, max_tokens=QUOTA_TOKENS, now=battery.now)
    epistemic = battery.fake_llm.last_kwargs.get("epistemic_context")
    return ProbeRecord(
        probe_id=probe_id,
        kind=str_field(probe, "kind"),
        question=question,
        target_fact_id=target_fact_id,
        target_content=target_content,
        hits=list(memories),
        context=context,
        epistemic_context=str(epistemic) if isinstance(epistemic, str) else "",
    )


@pytest.fixture(scope="module")
def rag_battery(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RagBattery]:
    module_tmp = tmp_path_factory.mktemp("rag_t2")

    # Module-scoped LUCCA_HOME isolation (mirrors conftest autouse fixture)
    mp = pytest.MonkeyPatch()
    home = module_tmp / "lucca_home"
    for sub in ("models", "data", "workspace", "inbox", "logs", "cache", "tmp"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    mp.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()

    try:
        orch, store, db, fake_llm = _make_t2_orchestrator(module_tmp)
        now = time.time()
        memory_ids = seed_rag_corpus(store, now)
        corpus_by_id = {str_field(row, "id"): row for row in load_corpus()}

        battery = RagBattery(
            store=store,
            db=db,
            orch=orch,
            fake_llm=fake_llm,
            memory_ids=memory_ids,
            corpus_by_id=corpus_by_id,
            records={},
            now=now,
        )
        for probe in load_probes():
            record = _run_probe(battery, probe)
            battery.records[record.probe_id] = record

        yield battery
    finally:
        mp.undo()
        get_config.cache_clear()


# ---------------------------------------------------------------------------
# §6.2 Assertion 1 — recall probes: target fact present in the built prompt
# ---------------------------------------------------------------------------


@pytest.mark.tier2
def test_t2_rag_recall_target_fact_in_prompt(rag_battery: RagBattery) -> None:
    """Every recall probe (N=40) must surface its target fact (recall@8 == 1.0)."""
    recall_records = [r for r in rag_battery.records.values() if r.kind == "recall"]
    assert len(recall_records) == 40

    misses: list[dict[str, object]] = []
    for record in recall_records:
        if not record.target_in_context or not record.target_in_hits:
            misses.append(
                {
                    "id": record.probe_id,
                    "question": record.question,
                    "target_fact_id": record.target_fact_id,
                    "target_in_hits": record.target_in_hits,
                    "target_in_context": record.target_in_context,
                    "retrieved": [h.content[:80] for h in record.hits],
                }
            )

    recall_at_k = (len(recall_records) - len(misses)) / len(recall_records)
    assert not misses, (
        f"recall@8 == {recall_at_k:.3f}; {len(misses)} probe(s) missing target fact:\n"
        + "\n".join(str(m) for m in misses)
    )


# ---------------------------------------------------------------------------
# §6.2 Assertion 2 — recollections never framed as evidence
# ---------------------------------------------------------------------------


@pytest.mark.tier2
def test_t2_rag_recollection_never_framed_as_evidence(rag_battery: RagBattery) -> None:
    """
    Recollection rows (ASSISTANT_UTTERANCE) must be grounding_eligible=False and
    must only ever appear in the prompt under a provenance tag or the D-MEM-04
    "[Recollections (Non-Grounding)]" quoting frame — never as evidence.
    """
    recollection_contents = [
        str_field(row, "content")
        for row in rag_battery.corpus_by_id.values()
        if str_field(row, "role") == "recollection"
    ]
    assert len(recollection_contents) == 10

    violations: list[str] = []
    for record in rag_battery.records.values():
        # (a) every recollection hit is non-grounding
        for hit in record.hits:
            if hit.provenance == Provenance.ASSISTANT_UTTERANCE and hit.grounding_eligible:
                violations.append(
                    f"{record.probe_id}: recollection hit is grounding_eligible: {hit.content[:80]}"
                )

        # (b) every recollection surfaced in the memory context carries its
        #     provenance tag on the same rendered line
        for line in record.context.splitlines():
            for content in recollection_contents:
                if content.lower() in line.lower() and "ASSISTANT_UTTERANCE" not in line:
                    violations.append(
                        f"{record.probe_id}: recollection rendered without provenance tag: {line[:120]}"
                    )

        # (c) if the cascade produced an epistemic context, recollections there
        #     must sit under the non-grounding quoting frame
        if record.epistemic_context:
            for content in recollection_contents:
                if content.lower() in record.epistemic_context.lower():
                    frame_idx = record.epistemic_context.find("[Recollections (Non-Grounding)]")
                    content_idx = record.epistemic_context.lower().find(content.lower())
                    if frame_idx == -1 or content_idx < frame_idx:
                        violations.append(
                            f"{record.probe_id}: recollection in epistemic context outside "
                            f"non-grounding frame: {content[:80]}"
                        )

    assert not violations, (
        f"{len(violations)} recollection-as-evidence violation(s):\n" + "\n".join(violations[:20])
    )


# ---------------------------------------------------------------------------
# §6.2 Assertion 3 — abstention probes: no distractor above the relevance floor
# ---------------------------------------------------------------------------


@pytest.mark.tier2
def test_t2_rag_abstention_no_distractor_above_floor(rag_battery: RagBattery) -> None:
    """
    For abstention probes (fact absent from corpus) no near-miss distractor may
    be retrieved above the relevance floor (RELEVANCE_FLOOR = 1.5/(RRF_K+1),
    i.e. cross-channel dense+sparse agreement).
    """
    distractor_contents = {
        str_field(row, "content")
        for row in rag_battery.corpus_by_id.values()
        if str_field(row, "role") == "distractor"
    }
    assert len(distractor_contents) == 20

    abstention_records = [r for r in rag_battery.records.values() if r.kind == "abstention"]
    assert len(abstention_records) == 10

    violations: list[dict[str, object]] = []
    for record in abstention_records:
        for hit in record.hits:
            if hit.content in distractor_contents and hit.score >= RELEVANCE_FLOOR:
                violations.append(
                    {
                        "id": record.probe_id,
                        "question": record.question,
                        "distractor": hit.content,
                        "score": hit.score,
                        "floor": RELEVANCE_FLOOR,
                    }
                )

    assert not violations, (
        f"{len(violations)} near-miss distractor(s) above relevance floor "
        f"{RELEVANCE_FLOOR:.4f} on abstention probes:\n" + "\n".join(str(v) for v in violations)
    )


# ---------------------------------------------------------------------------
# §6.2 Assertion 4 — D-MEM-03 quota respected + utilisation recorded
# ---------------------------------------------------------------------------


@pytest.mark.tier2
def test_t2_rag_quota_utilisation(rag_battery: RagBattery) -> None:
    """Rendered memory context stays within the 2,048-token budget for all probes."""
    over: list[str] = []
    utilisations: list[float] = []
    for record in rag_battery.records.values():
        utilisation = record.context_chars / QUOTA_CHAR_BUDGET
        utilisations.append(utilisation)
        if record.context_chars > QUOTA_CHAR_BUDGET:
            over.append(f"{record.probe_id}: {record.context_chars} chars > {QUOTA_CHAR_BUDGET}")

    from tests.rag_harness import write_report

    write_report(
        "rag_tier2",
        {
            "probes": len(rag_battery.records),
            "relevance_floor": RELEVANCE_FLOOR,
            "quota_char_budget": QUOTA_CHAR_BUDGET,
            "max_quota_utilisation": max(utilisations) if utilisations else 0.0,
            "mean_quota_utilisation": (
                sum(utilisations) / len(utilisations) if utilisations else 0.0
            ),
            "recall_hits": {
                r.probe_id: r.target_in_context
                for r in rag_battery.records.values()
                if r.kind == "recall"
            },
        },
    )

    assert not over, f"{len(over)} probe(s) exceeded the memory quota:\n" + "\n".join(over)
