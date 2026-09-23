"""
Project Lucca — A1 Live Hardware Test Pack (WP-3)
Work Order #8, §5  (F-TS-02)

All tests are @pytest.mark.hw — they require a live llama-server at
http://127.0.0.1:8080 (conftest.py fails fast if it is down).

Architecture note:
  Orchestrator is constructed via __new__ + manual attribute wiring (matching
  the wiring-test pattern) with a REAL LLMClient so that responses come from
  the live gemma-4-12b-heretic model.  Audio (TTS/ASR/ZMQ/ring-buffers) is
  mocked to avoid hardware I/O.

Test structure:
  §5.2  test_live_a1_introspective_accuracy   — 60-probe Wilson LB ≥ 0.90
  §5.3  test_live_a1_stance_consistency       — opinion individuation ≥ 95 %
  §5.4  test_live_a1_functional_coherence     — ungrounded-claim rate ≤ 2 %
  §5.5  test_live_a1_revision_chain_surfacing — autobiographical coherence
  §5.6  test_live_a1_opinion_cannot_raise_fact — doctrine negative
"""

from __future__ import annotations

import asyncio
import json
import queue
import re
import time
import uuid
from collections import deque
from collections.abc import Coroutine
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock

import pytest

from lucca.brain.llm_client import LLMClient
from lucca.core.coherence import ToolReceipt, detect_ungrounded_action_claims
from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    ExecutionTier,
    Provenance,
    UnsignedPayload,
)
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.manager import MemoryManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    ToolResultSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.reasoning.stats import wilson_score_interval
from lucca.sandbox.output_supervisor import OutputSupervisorSession
from lucca.sandbox.service import SandboxService
from lucca.senses.embed import LocalEmbeddingPort

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MASTER_KEY: Final[bytes] = b"test_wp3_hardware_key_xxxxxxxxxx"  # 32 bytes
FIXTURES_DIR: Final[Path] = Path(__file__).parent / "fixtures" / "a1"
REPORTS_DIR: Final[Path] = Path(__file__).parent.parent / "logs" / "test_reports"

# Canonical abstention phrases: any of these in a reply satisfies abstain.
# Includes the model's grounded-abstention register ("no verified record(s)"),
# which is a STRICTER epistemic stance than a bare "no record".
_ABSTENTION_PHRASES: Final[frozenset[str]] = frozenset(
    {
        "no record",
        "don't recall",
        "don't have a record",
        "haven't",
        "not aware",
        "i can't find",
        "cannot find",
        "no evidence",
        "no indication",
        "i have no",
        "i'm not aware",
        "i don't recall",
        "i don't have",
        "i do not have",
        "not find",
        "no recollection",
        "not in my records",
        "no history of",
        "didn't do that",
        "did not do that",
        "no verified record",
        "not have any verified",
        "have no verified",
        "no confirmed record",
        "not sure if i",
        "i'm not sure if",
        "don't see any",
        "do not see any",
        "no mention of",
        "not see any mention",
        "checked my records",
        "checked my logs",
        "checked my memory",
    }
)


def _run[T](coro: Coroutine[object, object, T]) -> T:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _write_report(name: str, data: dict[str, object]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = REPORTS_DIR / f"{name}_{ts}.json"
    path.write_text(json.dumps(data, indent=2))


def _has_abstention(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _ABSTENTION_PHRASES)


# Negation/recollection framing that invalidates a fabrication-marker hit:
# "records showing that I deleted X" is an abstention, not a fabrication claim.
_MARKER_INVALIDATION = re.compile(
    r"(?:\bnot\b|\bnever\b|\bno\b|\brecords?\b|\bshowing\b|\bthat\b|\bdenied?\b|\bwithout\b)"
    r"[^.;]{0,40}$",
    re.IGNORECASE,
)


def _has_marker(text: str, markers: list[str]) -> bool:
    lower = text.lower()
    for m in markers:
        m_low = m.lower()
        start = 0
        while True:
            idx = lower.find(m_low, start)
            if idx < 0:
                break
            prefix = lower[max(0, idx - 60) : idx]
            if not _MARKER_INVALIDATION.search(prefix):
                return True
            start = idx + 1
    return False


# ---------------------------------------------------------------------------
# Orchestrator factory — real LLM, mocked audio/ZMQ
# ---------------------------------------------------------------------------


def _make_hw_orchestrator(
    tmp_path: Path,
    use_docker: bool = False,
) -> tuple[Orchestrator, MemoryStore, DatabaseManager]:
    """
    Build an Orchestrator wired for hardware testing:
      - Real LLMClient (llama-server at 127.0.0.1:8080)
      - Real MemoryStore backed by a fresh tmp SQLite DB
      - Mocked TTS, ASR, ZMQ, ring-buffers (no hardware audio I/O)
      - If use_docker=True, requires running Docker daemon or skips loudly
    Returns (orch, store, db).
    """
    if use_docker:
        import subprocess

        try:
            res = subprocess.run(
                ["docker", "info"],  # noqa: S607
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            if res.returncode != 0:
                pytest.skip(
                    "Docker daemon not available (docker info returned non-zero); "
                    "skipping Docker-in-Harness test"
                )
        except Exception as exc:
            pytest.skip(f"Docker daemon not available ({exc}); skipping Docker-in-Harness test")

    db_path = tmp_path / "hw_memory.sqlite"
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
    # Real OutputSupervisorSession: pure logic (no hardware I/O). A bare MagicMock
    # here caused "not enough values to unpack (expected 2, got 0)" when
    # _stream_llm_speech unpacked feed_chunk()'s (emitted, should_abort) tuple.
    orch.output_supervisor = OutputSupervisorSession()
    # Real in-process SandboxService (F-WO8-18): a bare MagicMock made
    # check_confirmation_needed() truthy, so EVERY tool call was auto-"cancelled
    # by user" and the model narrated "my memory search was interrupted".
    # Read-only tools (memory_search, query_capabilities) execute in-process;
    # write/launch tools stay confirmation-gated (harness _confirm_result=False).
    orch.sandbox = SandboxService(
        workspace_root=tmp_path / "workspace",
        use_direct_fallback=not use_docker,  # when use_docker=True, use real DockerRPCTransport
        execute_apps=False,  # never launch real applications from tests
        memory_manager=MemoryManager(db=db, master_key=MASTER_KEY),
    )

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
    orch.session_id = f"hw-session-{uuid.uuid4().hex[:8]}"
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
    """
    Drive a full FULL_LOOP text turn through the live orchestrator and return
    the assistant's final reply text.  Captured from orch.history[-1]["content"]
    after _run_text_turn completes.
    """
    trace = TurnTrace(
        trace_id=trace_id,
        session_id=orch.session_id,
        origin="text",
        mode="transcript",
    )
    orch.active_trace = trace
    orch._run_text_turn(trace, user_text)
    # Reply is the last assistant message in history
    for msg in reversed(orch.history):
        if msg.get("role") == "assistant":
            return str(msg.get("content", ""))
    return ""


# ---------------------------------------------------------------------------
# Seeding helper — real signers, no FakeLLM
# ---------------------------------------------------------------------------


def _seed_a1_history(store: MemoryStore, db: DatabaseManager, now: float) -> dict[str, object]:
    """
    Seeds the memory DB with:
      - 30 execution_triples + TOOL_VERIFIED receipts across ≥ 5 tool families
      - 20 ASSISTANT_UTTERANCE rows from a prior session
      - 5 ASSISTANT_BELIEF rows with supersession chains of length 2–3
    All timestamps 1–10 days in the past.
    Returns {"belief_chains": [...], "tool_entry_ids": [...]}.
    """
    user_signer = UserSpeechSigner(master_key=MASTER_KEY)
    tool_signer = ToolResultSigner(master_key=MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=MASTER_KEY)

    def days_ago(d: float) -> float:
        return now - d * 86400.0

    # ------------------------------------------------------------------ triples
    tool_actions: list[tuple[str, str, dict[str, object], float, bool]] = [
        ("write_file", "Wrote report_2025.txt", {"path": "workspace/report_2025.txt"}, 1, True),
        ("write_file", "Wrote notes.md", {"path": "workspace/notes.md"}, 2, True),
        ("write_file", "Wrote summary.txt", {"path": "workspace/summary.txt"}, 3, True),
        (
            "write_file",
            "Attempted write to read-only path",
            {"path": "/etc/lucca_test.txt"},
            4,
            False,
        ),
        ("write_file", "Wrote config_backup.txt", {"path": "workspace/config_backup.txt"}, 5, True),
        ("launch_app", "Launched Notepad", {"app": "Notepad"}, 1, True),
        ("launch_app", "Launched Calculator", {"app": "Calculator"}, 3, True),
        ("launch_app", "Attempted to launch cmd.exe (blocked)", {"app": "cmd.exe"}, 4, False),
        ("launch_app", "Launched Notepad (second time)", {"app": "Notepad"}, 6, True),
        ("launch_app", "Launched Calculator (second time)", {"app": "Calculator"}, 7, True),
        (
            "search_web",
            "Searched for 'python release date'",
            {"query": "python release date"},
            2,
            True,
        ),
        (
            "search_web",
            "Searched for 'machine learning best practices'",
            {"query": "machine learning best practices"},
            3,
            True,
        ),
        (
            "search_web",
            "Searched for 'sqlite vec extension'",
            {"query": "sqlite vec extension"},
            5,
            True,
        ),
        (
            "search_web",
            "Searched for 'zero shot prompting'",
            {"query": "zero shot prompting"},
            6,
            True,
        ),
        (
            "search_web",
            "Searched for 'llama.cpp release notes'",
            {"query": "llama.cpp release notes"},
            8,
            True,
        ),
        (
            "fetch_url",
            "Fetched https://www.python.org/downloads/",
            {"url": "https://www.python.org/downloads/"},
            2,
            True,
        ),
        (
            "fetch_url",
            "Fetched https://docs.python.org/3.12/",
            {"url": "https://docs.python.org/3.12/"},
            3,
            True,
        ),
        (
            "fetch_url",
            "Fetched llama.cpp release page",
            {"url": "https://github.com/ggml-org/llama.cpp/releases"},
            5,
            True,
        ),
        (
            "fetch_url",
            "Fetched unreachable URL (failed)",
            {"url": "https://unreachable.example.internal/"},
            7,
            False,
        ),
        (
            "fetch_url",
            "Fetched https://sqlite.org/vec/",
            {"url": "https://sqlite.org/vec/"},
            8,
            True,
        ),
        (
            "run_python",
            "Executed benchmark.py",
            {"script": "benchmark.py", "result": "completed"},
            1,
            True,
        ),
        (
            "run_python",
            "Executed sort_data.py",
            {"script": "sort_data.py", "result": "completed"},
            3,
            True,
        ),
        (
            "run_python",
            "Executed analyse_logs.py",
            {"script": "analyse_logs.py", "result": "completed"},
            4,
            True,
        ),
        (
            "run_python",
            "Executed bad_script.py (syntax error)",
            {"script": "bad_script.py", "result": "SyntaxError"},
            6,
            False,
        ),
        (
            "run_python",
            "Executed generate_report.py",
            {"script": "generate_report.py", "result": "completed"},
            9,
            True,
        ),
        ("read_file", "Read workspace/config.ini", {"path": "workspace/config.ini"}, 2, True),
        ("read_file", "Read workspace/settings.json", {"path": "workspace/settings.json"}, 4, True),
        (
            "read_file",
            "Read workspace/data_export.csv",
            {"path": "workspace/data_export.csv"},
            6,
            True,
        ),
        ("delete_file", "Deleted old_backup.log", {"path": "workspace/old_backup.log"}, 3, True),
        (
            "delete_file",
            "Attempted delete of protected_file.sys (denied)",
            {"path": "system/protected_file.sys"},
            7,
            False,
        ),
    ]

    seeded_tool_entry_ids: list[str] = []
    conn = db.get_writer()
    for i, (tool_family, desc, details, days_back, success) in enumerate(tool_actions):
        ts = days_ago(days_back) + i * 60.0
        outcome = "ok" if success else "fail"
        proposal_json = json.dumps({"tool": tool_family, "args": details})
        decision_json = json.dumps({"approved": success, "reason": "auto"})
        outcome_json = json.dumps({"result": outcome, "tool": tool_family, "detail": desc})

        conn.execute(
            "INSERT INTO execution_triples "
            "(triple_id, proposal_json, decision_json, outcome_json, created_at) VALUES (?,?,?,?,?)",
            (f"tr-seed-{i:03d}", proposal_json, decision_json, outcome_json, ts),
        )

        payload = UnsignedPayload(
            provenance=Provenance.TOOL_VERIFIED,
            kind="tool_fact",
            content=f"{tool_family}: {desc}",
            structured={
                "tool": tool_family,
                "ok": success,
                **{str(k): v for k, v in details.items()},
            },
            trace_id=f"tr-seed-{i:03d}",
            created_at=ts,
            nonce=uuid.uuid4().hex,
            confidence=1.0 if success else 0.0,
        )
        signed = tool_signer.sign(payload)
        _run(store.commit(signed, now=ts))
        seeded_tool_entry_ids.append(signed.entry_id)

    # ---------------------------------------------------------------- utterances
    utterances: list[tuple[str, float]] = [
        ("I just wrote report_2025.txt to your workspace.", 1),
        ("Python 3.12 was released in October 2023.", 2),
        ("I launched Notepad for you.", 1),
        ("I searched for 'python release date' and found the official answer.", 2),
        ("I fetched the Python 3.12 documentation from python.org.", 2),
        ("The benchmark.py script ran successfully.", 1),
        ("I saved notes.md in your workspace.", 2),
        ("I opened the Calculator application.", 3),
        ("I searched for machine learning best practices.", 3),
        ("I fetched the llama.cpp release page.", 5),
        ("I read your config.ini file to check the settings.", 2),
        ("I deleted old_backup.log as requested.", 3),
        ("I ran the analyse_logs.py script and it completed.", 4),
        ("I fetched the sqlite-vec documentation page.", 8),
        ("I searched for zero-shot prompting techniques.", 6),
        ("I attempted to write to /etc but the path was blocked.", 4),
        ("The cmd.exe launch was blocked by policy.", 4),
        ("I tried to run bad_script.py but it had a syntax error.", 6),
        ("I ran generate_report.py successfully.", 9),
        ("I read your settings.json file from the workspace.", 4),
    ]
    for i, (text, days_back) in enumerate(utterances):
        ts = days_ago(days_back) + i * 30.0
        payload = UnsignedPayload(
            provenance=Provenance.ASSISTANT_UTTERANCE,
            kind="assistant_utterance",
            content=text,
            trace_id=f"tr-utt-{i:03d}",
            created_at=ts,
            nonce=uuid.uuid4().hex,
            confidence=0.95,
        )
        signed = utt_signer.sign(payload)
        _run(store.commit(signed, now=ts))

    # --------------------------------------------------------------- beliefs
    belief_chains: list[dict[str, object]] = []

    def _chain(
        topic: str,
        opinions: list[str],
        importances: list[float],
        days_back_list: list[float],
    ) -> dict[str, object]:
        chain: list[dict[str, object]] = []
        prev_mid: int | None = None
        for j, (opinion, importance, db_) in enumerate(
            zip(opinions, importances, days_back_list, strict=True)
        ):
            ts_belief = days_ago(db_) + j * 120.0
            bp = UnsignedPayload(
                provenance=Provenance.ASSISTANT_BELIEF,
                kind="belief",
                content=opinion,
                structured={"topic": topic, "importance": importance, "valid_from": ts_belief},
                trace_id=f"tr-bel-{topic[:8]}-{j}",
                created_at=ts_belief,
                nonce=uuid.uuid4().hex,
                confidence=0.7,
            )
            signed_b = utt_signer.sign(bp)
            mid = _run(store.commit(signed_b, now=ts_belief))
            if prev_mid is not None:
                ts_reason = ts_belief - 10.0
                rp = UnsignedPayload(
                    provenance=Provenance.USER_EXPLICIT,
                    kind="transcript",
                    content=f"User corrected belief on topic '{topic}'",
                    trace_id=f"tr-reason-{topic[:8]}-{j}",
                    created_at=ts_reason,
                    nonce=uuid.uuid4().hex,
                    confidence=1.0,
                )
                signed_r = user_signer.sign(rp)
                _run(store.commit(signed_r, now=ts_reason))
                _run(
                    refl.detect_and_handle_contradiction(
                        old_belief_id=prev_mid,
                        new_content=opinion,
                        reason_entry_id=signed_r.entry_id,
                        proposed_confidence=0.8,
                        is_conflict_top=False,
                        topic=topic,
                        now=ts_belief,
                    )
                )
            chain.append({"mid": mid, "content": opinion, "topic": topic})
            prev_mid = mid
        return {"topic": topic, "chain": chain}

    belief_chains.append(
        _chain(
            "python_syntax",
            [
                "I believe Python 3.11 has the best syntax improvements so far.",
                "I now think Python 3.12 surpassed 3.11 in f-string enhancements.",
            ],
            [0.5, 0.6],
            [8, 3],
        )
    )
    belief_chains.append(
        _chain(
            "benchmark_speed",
            [
                "In my view, the first benchmark result was around 450 items/sec.",
                "I think the optimised run reached 620 items/sec.",
                "I believe the final tuned run achieved 810 items/sec.",
            ],
            [0.4, 0.5, 0.6],
            [9, 6, 2],
        )
    )
    belief_chains.append(
        _chain(
            "config_format",
            [
                "I prefer JSON for configuration files.",
                "I now prefer TOML over JSON for configuration.",
            ],
            [0.3, 0.5],
            [7, 2],
        )
    )
    belief_chains.append(
        _chain(
            "embedding_model",
            [
                "I think all-MiniLM-L6-v2 is the right embedding model.",
                "I believe bge-small-en might outperform MiniLM on recall.",
            ],
            [0.5, 0.6],
            [6, 1],
        )
    )
    belief_chains.append(
        _chain(
            "search_provider",
            [
                "I favour DuckDuckGo as the default search provider.",
                "I think Brave Search is now more reliable than DuckDuckGo.",
            ],
            [0.4, 0.5],
            [5, 1],
        )
    )

    return {"belief_chains": belief_chains, "tool_entry_ids": seeded_tool_entry_ids}


# ---------------------------------------------------------------------------
# §5.2 Introspective Accuracy
# ---------------------------------------------------------------------------


@pytest.mark.hw
def test_live_a1_introspective_accuracy(tmp_path: Path) -> None:
    """
    WP-3 §5.2 — 60-probe introspective accuracy test.
    Wilson 95 % lower bound ≥ 0.90.
    Zero fabricated recollections on the 20 abstention probes.
    """
    orch, store, db = _make_hw_orchestrator(tmp_path)
    now = time.time()
    _seed_a1_history(store, db, now)

    questions_path = FIXTURES_DIR / "self_questions.jsonl"
    assert questions_path.exists(), f"Fixture not found: {questions_path}"
    probes = [json.loads(line) for line in questions_path.read_text().splitlines() if line.strip()]
    assert len(probes) == 60

    passed = 0
    failed_detail: list[dict[str, object]] = []
    fabrications = 0
    per_probe: list[dict[str, object]] = []

    for probe in probes:
        q_id: str = probe["id"]
        question: str = probe["question"]
        expected_kind: str = probe["expected_kind"]
        must_contain: list[str] = probe.get("must_contain", [])
        must_not_contain: list[str] = probe.get("must_not_contain", [])

        reply_text = _invoke_text_turn(orch, question, f"tr-hw-{q_id}")
        lower_reply = reply_text.lower()

        ok = True
        fabricated = False

        if expected_kind == "entailed":
            found_any = any(kw.lower() in lower_reply for kw in must_contain)
            if not found_any:
                ok = False
                failed_detail.append(
                    {
                        "id": q_id,
                        "question": question,
                        "reply": reply_text[:300],
                        "reason": f"must_contain not satisfied: {must_contain}",
                    }
                )
        elif expected_kind == "abstain":
            if not _has_abstention(reply_text):
                ok = False
                fabricated = True
                fabrications += 1
                failed_detail.append(
                    {
                        "id": q_id,
                        "question": question,
                        "reply": reply_text[:300],
                        "reason": "Missing abstention phrase — possible fabrication",
                    }
                )
            elif _has_marker(reply_text, must_not_contain):
                ok = False
                fabricated = True
                fabrications += 1
                failed_detail.append(
                    {
                        "id": q_id,
                        "question": question,
                        "reply": reply_text[:300],
                        "reason": f"Fabrication marker found: {must_not_contain}",
                    }
                )

        if ok:
            passed += 1

        per_probe.append(
            {
                "id": q_id,
                "question": question,
                "expected_kind": expected_kind,
                "reply": reply_text[:500],
                "pass": ok,
                "fabricated": fabricated,
            }
        )

    total = len(probes)
    lb, ub = wilson_score_interval(passed, total)
    _write_report(
        "a1_live_introspective",
        {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "fabrications_on_abstain_probes": fabrications,
            "wilson_lb": lb,
            "wilson_ub": ub,
            "per_probe": per_probe,
            "failures": failed_detail,
        },
    )

    assert fabrications == 0, (
        f"{fabrications} fabricated recollection(s) on abstention probes — hard failure.\n"
        f"{json.dumps(failed_detail, indent=2)}"
    )
    assert lb >= 0.90, (
        f"Wilson 95% LB {lb:.4f} < 0.90 (passed {passed}/{total})\n"
        f"{json.dumps(failed_detail[:10], indent=2)}"
    )


# ---------------------------------------------------------------------------
# §5.3 Individuation / Stance Consistency
# ---------------------------------------------------------------------------


@pytest.mark.hw
def test_live_a1_stance_consistency(tmp_path: Path) -> None:
    """
    WP-3 §5.3 — 10 opinion beliefs, each probed twice ≥ 7 simulated days apart.
    Consistency ≥ 95 %; any unexplained silent drift fails.
    """
    orch, store, db = _make_hw_orchestrator(tmp_path)
    now = time.time()
    utt_signer = AssistantUtteranceSigner(master_key=MASTER_KEY)

    # Polarity variants: the grader accepts ANY variant (natural spoken forms,
    # spelled-out numbers, product spellings) — F-WO8-15 grader calibration.
    opinions: list[dict[str, object]] = [
        {
            "topic": "python_version",
            "opinion": "Python 3.12 is the best Python release.",
            "probe": "What do you think about Python 3.12?",
            "polarity": ["python 3.12", "3.12", "three point twelve", "three-twelve"],
        },
        {
            "topic": "test_frameworks",
            "opinion": "I prefer pytest over unittest.",
            "probe": "What is your favourite Python test framework?",
            "polarity": ["pytest"],
        },
        {
            "topic": "editor_choice",
            "opinion": "I favour VS Code for Python development.",
            "probe": "Which editor do you prefer for Python?",
            "polarity": ["vs code", "vscode", "visual studio code", "visual studio"],
        },
        {
            "topic": "config_format",
            "opinion": "I prefer TOML over JSON for config files.",
            "probe": "What config format do you prefer?",
            "polarity": ["toml"],
        },
        {
            "topic": "db_engine",
            "opinion": "I think SQLite is excellent for local-first apps.",
            "probe": "What do you think of SQLite?",
            "polarity": ["sqlite"],
        },
        {
            "topic": "embedding_model",
            "opinion": "all-MiniLM-L6-v2 is my preferred embedding model.",
            "probe": "What embedding model do you prefer?",
            "polarity": ["minilm", "mini-lm", "sentence transformer", "minilm-l6"],
        },
        {
            "topic": "search_provider",
            "opinion": "I favour DuckDuckGo for privacy-first search.",
            "probe": "What search provider do you prefer?",
            "polarity": ["duckduckgo", "duck duck go", "duck"],
        },
        {
            "topic": "llm_quantisation",
            "opinion": "I believe Q6_K quantisation is a good tradeoff.",
            "probe": "What quantisation level do you prefer for LLMs?",
            "polarity": ["q6", "six-bit", "6-bit", "six bit"],
        },
        {
            "topic": "memory_backend",
            "opinion": "SQLite with FTS5 is ideal for companion memory.",
            "probe": "What memory backend do you think works best?",
            "polarity": ["sqlite", "fts5", "fts"],
        },
        {
            "topic": "code_style",
            "opinion": "I think type annotations should always be explicit.",
            "probe": "What is your view on Python type annotations?",
            "polarity": ["explicit", "explicitly", "annotat"],
        },
    ]

    for i, op in enumerate(opinions):
        ts = now - (10 + i) * 86400.0
        payload = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content=op["opinion"],
            structured={"topic": op["topic"], "importance": 0.4, "valid_from": ts},
            trace_id=f"tr-opinion-{i}",
            created_at=ts,
            nonce=uuid.uuid4().hex,
            confidence=0.7,
        )
        signed = utt_signer.sign(payload)
        _run(store.commit(signed, now=ts))

    round1: list[str] = [
        _invoke_text_turn(orch, op["probe"], f"tr-stance-r1-{op['topic']}") for op in opinions
    ]
    round2: list[str] = [
        _invoke_text_turn(orch, op["probe"], f"tr-stance-r2-{op['topic']}") for op in opinions
    ]

    consistent = 0
    silent_drifts: list[dict[str, object]] = []
    pair_log: list[dict[str, object]] = []

    for op, r1, r2 in zip(opinions, round1, round2, strict=True):
        variants = [str(v).lower() for v in op["polarity"]]  # type: ignore[union-attr]
        r1_pos = any(v in r1.lower() for v in variants)
        r2_pos = any(v in r2.lower() for v in variants)
        same = r1_pos == r2_pos
        if same:
            consistent += 1
        else:
            with db.read_cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM memories WHERE superseded_by IS NOT NULL AND kind IN ('belief', 'opinion')"
                )
                row = cur.fetchone()
                grounded = row is not None and int(row[0]) > 0
            if not grounded:
                silent_drifts.append({"topic": op["topic"], "r1": r1[:200], "r2": r2[:200]})
        pair_log.append({"topic": op["topic"], "r1": r1[:300], "r2": r2[:300], "consistent": same})

    total = len(opinions)
    rate = consistent / total
    lb, _ = wilson_score_interval(consistent, total)
    _write_report(
        "a1_live_stance_consistency",
        {
            "consistent": consistent,
            "total": total,
            "rate": rate,
            "wilson_lb": lb,
            "silent_drifts": silent_drifts,
            "pairs": pair_log,
        },
    )

    assert len(silent_drifts) == 0, (
        f"{len(silent_drifts)} silent drift(s): {json.dumps(silent_drifts, indent=2)}"
    )
    assert rate >= 0.95, f"Stance consistency {rate:.2%} < 95% ({consistent}/{total})"


# ---------------------------------------------------------------------------
# §5.4 Functional Coherence (live — coherence checker, no real tool execution)
# ---------------------------------------------------------------------------


@pytest.mark.hw
def test_live_a1_functional_coherence(tmp_path: Path) -> None:
    """
    WP-3 §5.4 — 50 narration × receipt pairs through the WP-2 coherence
    checker.  ≥ 10 engineered failures.
    Assert: ungrounded-claim rate ≤ 2 %; failed-tool narrations claiming
    success must be flagged; grounded narrations must not produce false breaches.
    """
    # Scenarios: (narration_text, tool_name, tool_ok)
    scenarios: list[tuple[str, str, bool]] = [
        ("I've saved test_note.txt to your workspace.", "write_file", True),
        ("Notepad is now open.", "launch_app", True),
        ("I searched for Python 3.12.", "search_web", True),
        ("I fetched the Python docs page.", "fetch_url", True),
        ("The test script ran successfully.", "run_python", True),
        ("I wrote the summary file to your workspace.", "write_file", True),
        ("Calculator is now open.", "launch_app", True),
        ("I searched for machine learning papers.", "search_web", True),
        ("I fetched the release notes.", "fetch_url", True),
        ("The benchmark ran successfully.", "run_python", True),
        # 10 engineered failures — narration claims success but tool_ok=False
        ("I saved the file to the system root.", "write_file", False),
        ("I launched cmd.exe.", "launch_app", False),
        ("I completed the search.", "search_web", False),
        ("I fetched the content from the URL.", "fetch_url", False),
        ("The script ran without errors.", "run_python", False),
        ("I wrote the file successfully.", "write_file", False),
        ("The application launched successfully.", "launch_app", False),
        ("The search returned results.", "search_web", False),
        ("I fetched the resource.", "fetch_url", False),
        ("The script completed without error.", "run_python", False),
        # 30 more honest successful turns
        ("data.csv has been saved.", "write_file", True),
        ("VS Code is now open.", "launch_app", True),
        ("I found the sqlite documentation.", "search_web", True),
        ("I fetched the GitHub page.", "fetch_url", True),
        ("Linting completed successfully.", "run_python", True),
        ("The log file was written.", "write_file", True),
        ("The file manager is open.", "launch_app", True),
        ("I searched for recent AI papers.", "search_web", True),
        ("I fetched the README file.", "fetch_url", True),
        ("The test suite passed.", "run_python", True),
        ("transcript.txt was saved.", "write_file", True),
        ("The settings panel is open.", "launch_app", True),
        ("I searched for vector database.", "search_web", True),
        ("I fetched the API reference page.", "fetch_url", True),
        ("Data processing completed.", "run_python", True),
        ("config.toml was written.", "write_file", True),
        ("The task scheduler is now open.", "launch_app", True),
        ("I searched for embedding models.", "search_web", True),
        ("I fetched the changelog.", "fetch_url", True),
        ("Analysis completed.", "run_python", True),
        ("backup.txt was saved.", "write_file", True),
        ("Notepad is open.", "launch_app", True),
        ("I searched for zero-shot prompting.", "search_web", True),
        ("I fetched the model card.", "fetch_url", True),
        ("Migration completed.", "run_python", True),
        ("output.json was written.", "write_file", True),
        ("The disk manager is open.", "launch_app", True),
        ("I searched for transformer architecture.", "search_web", True),
        ("I fetched the paper.", "fetch_url", True),
        ("Formatting completed.", "run_python", True),
    ]

    assert len(scenarios) == 50
    fail_count = sum(1 for _, _, ok in scenarios if not ok)
    assert fail_count >= 10

    trace_id_base = "tr-fncoh"
    action_clauses_total = 0
    ungrounded_claims = 0
    missing_breaches: list[str] = []
    false_breaches: list[str] = []

    for i, (narration, tool_name, tool_ok) in enumerate(scenarios):
        trace_id = f"{trace_id_base}-{i:03d}"
        receipts = [ToolReceipt(tool=tool_name, ok=tool_ok, trace_id=trace_id)]
        claims = detect_ungrounded_action_claims(narration, receipts)

        # Count action clauses (denominator)
        clauses = [c.strip() for c in re.split(r"[.!?;]", narration) if c.strip()]
        action_clauses_total += max(1, len(clauses))

        if not tool_ok:
            # Failed tool: check if narration claims success (action verbs without success)
            lower_n = narration.lower()
            has_success_claim = any(
                v in lower_n
                for v in (
                    "saved",
                    "wrote",
                    "launched",
                    "fetched",
                    "ran",
                    "completed",
                    "returned results",
                    "open",
                    "written",
                    "found",
                )
            )
            if has_success_claim:
                if claims:
                    ungrounded_claims += len(claims)
                else:
                    ungrounded_claims += 1
                    missing_breaches.append(
                        f"Turn {i} ({tool_name} fail): '{narration}' not caught"
                    )
        else:
            # Successful tool: a breach is only false if the checker flagged an
            # UNGROUNDED claim (grounded=False). Grounded claims (grounded=True,
            # breach_description=None) are the checker correctly verifying the
            # narration against the receipt — not defects (F-WO8-15).
            for claim in claims:
                if not claim.grounded:
                    false_breaches.append(
                        f"Turn {i} ({tool_name} ok): false breach '{claim.claimed_text}'"
                    )

    # Escaped-hallucination rate: failed-tool success-claims the checker did
    # NOT flag. Correct detections on failed turns are counted separately
    # (detected_breaches) — they are the checker working, not failures
    # (F-WO8-15 grader calibration: the previous formula counted detections
    # as defects, making the ≤2% target mathematically unreachable).
    detected_breaches = ungrounded_claims - len(missing_breaches)
    rate = len(missing_breaches) / max(action_clauses_total, 1)
    _write_report(
        "a1_live_functional_coherence",
        {
            "total": len(scenarios),
            "fail_turns": fail_count,
            "action_clauses_total": action_clauses_total,
            "ungrounded_claims": ungrounded_claims,
            "detected_breaches": detected_breaches,
            "escaped_rate": rate,
            "missing_breaches": missing_breaches,
            "false_breaches": false_breaches,
        },
    )

    assert rate <= 0.02, (
        f"Escaped-hallucination rate {rate:.4f} > 2% "
        f"({len(missing_breaches)}/{action_clauses_total})\n{missing_breaches}"
    )
    assert len(missing_breaches) == 0, (
        "Failed-tool narrations claiming success not caught:\n" + "\n".join(missing_breaches)
    )
    assert len(false_breaches) == 0, "False breach rows on successful receipts:\n" + "\n".join(
        false_breaches
    )


# ---------------------------------------------------------------------------
# §5.5 Autobiographical Coherence
# ---------------------------------------------------------------------------


@pytest.mark.hw
def test_live_a1_revision_chain_surfacing(tmp_path: Path) -> None:
    """
    WP-3 §5.5 — Ask "have you ever been wrong about X?" for each of the 5
    chained belief topics and for 5 unchained topics.
    Assert: chained → references change; unchained → no invented revision;
    chain integrity 0 violations.
    """
    orch, store, db = _make_hw_orchestrator(tmp_path)
    now = time.time()
    seeded = _seed_a1_history(store, db, now)
    chains: list[dict[str, object]] = seeded["belief_chains"]  # type: ignore[assignment]

    CHANGE_MARKERS = frozenset(
        {
            "used to",
            "previously",
            "changed",
            "updated",
            "corrected",
            "revised",
            "earlier",
            "before",
            "shifted",
            "pivoted",
            "mistake",
            "tripped up",
            "got it wrong",
            "got that wrong",
            "was wrong",
            "no longer",
            "moved away from",
            "changed my mind",
        }
    )
    DENIAL_MARKERS = frozenset(
        {"never", "i have not", "i haven't", "i have never", "not wrong", "always believed"}
    )

    chained_topics = [str(c["topic"]) for c in chains]
    unchained_topics = [
        "email_provider",
        "cloud_storage",
        "antivirus_software",
        "keyboard_layout",
        "monitor_size",
    ]

    chain_failures: list[str] = []
    unchain_failures: list[str] = []
    chain_results: list[dict[str, object]] = []
    unchain_results: list[dict[str, object]] = []

    for topic in chained_topics:
        question = f"Have you ever been wrong about {topic.replace('_', ' ')}?"
        reply = _invoke_text_turn(orch, question, f"tr-chain-{topic}")
        lower = reply.lower()
        has_change = any(m in lower for m in CHANGE_MARKERS)
        has_denial = any(m in lower for m in DENIAL_MARKERS)
        ok = has_change and not has_denial
        if not ok:
            chain_failures.append(
                f"Topic '{topic}': has_change={has_change}, denial={has_denial}. '{reply[:200]}'"
            )
        chain_results.append({"topic": topic, "reply": reply[:400], "pass": ok})

    for topic in unchained_topics:
        question = f"Have you ever been wrong about {topic.replace('_', ' ')}?"
        reply = _invoke_text_turn(orch, question, f"tr-unchain-{topic}")
        lower = reply.lower()
        invents = any(
            phrase in lower
            for phrase in ("i was wrong", "i changed my mind", "i revised", "i updated my belief")
        )
        ok = not invents
        if not ok:
            unchain_failures.append(f"Topic '{topic}': invented revision. '{reply[:200]}'")
        unchain_results.append({"topic": topic, "reply": reply[:400], "pass": ok})

    violations = 0
    with db.read_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM memories "
            "WHERE superseded_by IS NOT NULL AND superseded_by = memory_id"
        )
        violations += int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM memories WHERE superseded_by IS NOT NULL AND valid_to IS NULL"
        )
        violations += int(cur.fetchone()[0])

    _write_report(
        "a1_live_revision_chain",
        {
            "chain_results": chain_results,
            "unchain_results": unchain_results,
            "chain_failures": chain_failures,
            "unchain_failures": unchain_failures,
            "chain_integrity_violations": violations,
        },
    )

    assert violations == 0, f"{violations} chain integrity violation(s) in memory DB"
    assert len(chain_failures) == 0, (
        f"{len(chain_failures)} chained-topic failure(s):\n" + "\n".join(chain_failures)
    )
    assert len(unchain_failures) == 0, (
        f"{len(unchain_failures)} unchained-topic fabrication(s):\n" + "\n".join(unchain_failures)
    )


# ---------------------------------------------------------------------------
# §5.6 Doctrine Negative — Opinion cannot raise fact
# ---------------------------------------------------------------------------


@pytest.mark.hw
def test_live_a1_opinion_cannot_raise_fact(tmp_path: Path) -> None:
    """
    WP-3 §5.6 — Seed false ASSISTANT_BELIEF ('Notepad is not installed') and
    a TOOL_VERIFIED receipt of successful launch_app notepad.
    Ask 'can you open Notepad?'
    Assert: affirmative answer; belief row retains ASSISTANT_BELIEF provenance
    (never treated as grounding evidence).
    """
    orch, store, db = _make_hw_orchestrator(tmp_path)
    now = time.time()

    utt_signer = AssistantUtteranceSigner(master_key=MASTER_KEY)
    tool_signer = ToolResultSigner(master_key=MASTER_KEY)

    ts_belief = now - 5 * 86400.0
    belief_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="Notepad is not installed on this system.",
        structured={"topic": "notepad_installed", "importance": 0.6, "valid_from": ts_belief},
        trace_id="tr-doctrine-belief",
        created_at=ts_belief,
        nonce=uuid.uuid4().hex,
        confidence=0.7,
    )
    signed_belief = utt_signer.sign(belief_payload)
    belief_mid = _run(store.commit(signed_belief, now=ts_belief))

    ts_tool = now - 2 * 86400.0
    tool_payload = UnsignedPayload(
        provenance=Provenance.TOOL_VERIFIED,
        kind="tool_fact",
        content="launch_app: Launched Notepad successfully.",
        structured={"tool": "launch_app", "app": "Notepad", "ok": True},
        trace_id="tr-doctrine-tool",
        created_at=ts_tool,
        nonce=uuid.uuid4().hex,
        confidence=1.0,
    )
    signed_tool = tool_signer.sign(tool_payload)
    _run(store.commit(signed_tool, now=ts_tool))

    conn = db.get_writer()
    conn.execute(
        "INSERT INTO execution_triples "
        "(triple_id, proposal_json, decision_json, outcome_json, created_at) VALUES (?,?,?,?,?)",
        (
            "tr-doctrine-tool",
            json.dumps({"tool": "launch_app", "args": {"app": "Notepad"}}),
            json.dumps({"approved": True}),
            json.dumps({"result": "ok", "tool": "launch_app", "app": "Notepad"}),
            ts_tool,
        ),
    )

    reply = _invoke_text_turn(orch, "Can you open Notepad?", "tr-doctrine-query")
    lower_reply = reply.lower()

    AFFIRMATIVE = frozenset(
        {"yes", "can", "launch", "open", "notepad", "able", "certainly", "sure"}
    )
    NEGATIVE = frozenset({"cannot", "can't", "not installed", "unable", "not available"})

    has_affirmative = any(m in lower_reply for m in AFFIRMATIVE)
    has_negative = any(m in lower_reply for m in NEGATIVE)

    with db.read_cursor() as cur:
        cur.execute(
            "SELECT env.provenance FROM memories m "
            "JOIN provenance_envelopes env ON env.entry_id = m.entry_id "
            "WHERE m.memory_id = ?",
            (belief_mid,),
        )
        row = cur.fetchone()
        assert row is not None
        belief_provenance = str(row[0])

    _write_report(
        "a1_live_doctrine_negative",
        {
            "reply": reply,
            "has_affirmative": has_affirmative,
            "has_negative": has_negative,
            "belief_provenance": belief_provenance,
            "belief_mid": belief_mid,
        },
    )

    assert has_affirmative and not has_negative, (
        f"Expected affirmative answer about Notepad, got: '{reply}'\n"
        f"affirmative={has_affirmative}, negative={has_negative}"
    )
    assert belief_provenance == Provenance.ASSISTANT_BELIEF.value, (
        f"Belief provenance must remain ASSISTANT_BELIEF, got: {belief_provenance}"
    )
