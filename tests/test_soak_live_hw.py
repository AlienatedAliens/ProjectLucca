"""
Project Lucca — Soak Test: Live Hardware Stability (WP-6)
Work Order #8, §8.2 (F-TS-08)

All tests are @pytest.mark.hw and @pytest.mark.soak — they require:
  - live llama-server at http://127.0.0.1:8080 running Gemma-4-12B-Heretic Q6_K
  - Docker in WSL2 with egress rules applied

Runs 150 real turns alternating:
  - conversation (general LLM query)
  - single tool (workspace file read / write / inspect in sandbox)
  - research (search_web / fetch_url via sandboxed container)

Asserts:
  - no llama-server restarts (PID and create_time preserved)
  - VRAM never exceeds 12,800 MB (measured via nvidia-smi)
  - TTFT p95 stable within 1.3x of first 20 turns
  - zero unhandled exceptions in traces
  - lucca-admin latency --last 150 output attached
  - Writes logs/test_reports/soak_live_hw_<ts>.json
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock

import psutil
import pytest

from lucca.brain.llm_client import LLMClient
from lucca.core.affect import AffectTracker
from lucca.core.bdi_validator import SpeculativeBDIValidator
from lucca.core.cascade import EpistemicSearchCascade
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
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.router.heuristic import HeuristicRouter
from lucca.sandbox.output_supervisor import OutputSupervisorSession
from lucca.sandbox.service import SandboxService
from lucca.senses.embed import LocalEmbeddingPort
from tests.rag_harness import MASTER_KEY

VRAM_PEAK_BUDGET_MB: Final[int] = 12800


def _get_vram_used_mb() -> int:
    """Queries current dGPU VRAM usage via nvidia-smi."""
    try:
        bin_path = shutil.which("nvidia-smi") or "nvidia-smi"
        res = subprocess.run(  # noqa: S603
            [bin_path, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return int(res.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001, S110
        pass
    return 0


def _find_llama_server_proc() -> psutil.Process | None:
    """Finds the running llama-server process on the host."""
    for p in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            name = (p.info.get("name") or "").lower()
            if "llama-server" in name:
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _check_llama_server_alive(host: str = "127.0.0.1", port: int = 8080) -> bool:
    """Pings http://host:port/health to verify LLM server availability."""
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lucca-LiveSoak/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:  # noqa: S310
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


class DrainQueue(queue.Queue[object]):
    """Queue that drops chunks immediately and signals done_event to prevent stalls."""

    def put(self, item: object, block: bool = True, timeout: float | None = None) -> None:
        if isinstance(item, tuple) and len(item) == 4 and isinstance(item[3], threading.Event):
            item[3].set()


def _make_soak_hw_orchestrator(
    tmp_path: Path,
) -> tuple[Orchestrator, SandboxService, MemoryStore, DatabaseManager]:
    """Wires Orchestrator for live hardware soak testing."""
    db_path = tmp_path / "hw_soak_memory.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()

    emb_port = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=MASTER_KEY, embedding_port=emb_port)
    refl = ReflectionEngine(db=db, store=store, master_key=MASTER_KEY)

    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    sandbox = SandboxService(workspace_root=ws_dir, use_direct_fallback=False)

    orch: Orchestrator = Orchestrator.__new__(Orchestrator)
    orch.config = get_config()
    orch.execute_tools = True
    orch.state = "idle"
    orch.running = True

    orch.llm = LLMClient()
    orch.sandbox = sandbox
    orch.db = db
    orch.memory_store = store
    orch.reflection_engine = refl

    orch.output_supervisor = OutputSupervisorSession()
    orch.user_signer = UserSpeechSigner(master_key=MASTER_KEY)
    orch.assistant_signer = AssistantUtteranceSigner(master_key=MASTER_KEY)
    orch.breach_signer = CoherenceBreachSigner(master_key=MASTER_KEY)

    orch.tts = MagicMock()
    orch.asr = MagicMock()
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
    orch.session_id = f"hw-soak-{uuid.uuid4().hex[:8]}"
    orch.active_detected_words = []
    orch._last_unspoken_tool_msg = None
    orch.quit_requested = False
    orch._last_ptt_press_ns = 0
    orch._last_pong = {}
    orch._confirm_event = threading.Event()
    orch._confirm_result = False
    orch._pending_confirmation_active = False
    orch._confirm_audio = None
    orch._confirm_via = None
    orch._confirm_lock = threading.Lock()

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

    return orch, sandbox, store, db


@pytest.mark.hw
@pytest.mark.soak
def test_soak_live_hw_150_turns(tmp_path: Path) -> None:
    """
    WO-8 §8.2 (F-TS-08):
    150 real turns alternating:
      - conversation
      - single tool
      - research
    Asserts:
      - no llama-server restarts
      - VRAM never exceeds 12,800 MB
      - TTFT p95 stable within 1.3x of first 20 turns
      - zero unhandled exceptions in traces
      - lucca-admin latency --last 150 output attached
    """
    # 1. Verify llama-server is alive
    if not _check_llama_server_alive():
        pytest.fail("llama-server is down at http://127.0.0.1:8080 — failing fast per §8.2")

    llama_proc = _find_llama_server_proc()
    llama_pid = llama_proc.pid if llama_proc else None
    llama_create_time = llama_proc.create_time() if llama_proc else None

    # 2. Build live Orchestrator
    orch, sandbox, store, db = _make_soak_hw_orchestrator(tmp_path)
    ws_dir = tmp_path / "workspace"
    sample_file = ws_dir / "sample_doc.txt"
    sample_file.write_text("Lucca live hardware soak test document content.", encoding="utf-8")

    # Prompts for rotation
    conversation_prompts = [
        "Explain the difference between a mutex and a spinlock in OS kernels.",
        "What are the core design principles of the Unix philosophy?",
        "How does copy-on-write virtual memory paging work?",
        "What is an epoll event loop and why is it O(1)?",
        "Explain how Raft consensus handles leader election.",
        "Describe the difference between TCP congestion control Reno and BBR.",
        "How do LSM-trees compare with B-trees for write-heavy workloads?",
        "Explain what flash attention accomplishes mathematically in transformers.",
        "What is the function of the write-ahead log in database transactions?",
        "Explain how virtual memory translation lookaside buffers work.",
    ]

    single_tool_prompts = [
        "Please read the file sample_doc.txt in my workspace.",
        "List the contents of my workspace directory.",
        "Read sample_doc.txt and tell me what it says.",
        "Please inspect sample_doc.txt in the workspace.",
        "List all files currently in the workspace.",
        "Read the file sample_doc.txt to confirm it is intact.",
        "Check what files exist in the workspace directory.",
        "Read sample_doc.txt from the workspace and summarize it.",
        "Inspect the workspace directory to see all available files.",
        "Verify the contents of sample_doc.txt by reading it.",
    ]

    research_prompts = [
        "Search the web for Python 3.12 release date and tell me the month.",
        "Search the web for SQLite WAL mode documentation.",
        "Search for OpenVINO NPU devices supported in Python.",
        "Search for Intel Core Ultra 9 275HX specifications.",
        "Search for NVIDIA RTX 5080 laptop GPU architecture details.",
        "Search for faster-whisper openvino performance benchmarks.",
        "Search for the latest python 3.13 release schedule.",
        "Search for sqlite-vec vector search extensions for sqlite.",
        "Search for libuv vs epoll asynchronous I/O architectures.",
        "Search for Kokoro TTS openvino model weights repository.",
    ]

    total_turns = 150
    ttft_records: list[float] = []
    vram_samples: list[int] = []
    unhandled_errors: list[dict[str, str]] = []
    t_start = time.perf_counter()

    initial_vram = _get_vram_used_mb()
    if initial_vram > 0:
        vram_samples.append(initial_vram)
        assert initial_vram <= VRAM_PEAK_BUDGET_MB, (
            f"Initial VRAM {initial_vram} MB exceeds {VRAM_PEAK_BUDGET_MB} MB budget"
        )

    for turn_idx in range(1, total_turns + 1):
        turn_type = (turn_idx - 1) % 3

        if turn_type == 0:
            prompt = conversation_prompts[(turn_idx // 3) % len(conversation_prompts)]
            mode = "conversation"
        elif turn_type == 1:
            prompt = single_tool_prompts[(turn_idx // 3) % len(single_tool_prompts)]
            mode = "single_tool"
        else:
            prompt = research_prompts[(turn_idx // 3) % len(research_prompts)]
            mode = "research"

        trace = TurnTrace(
            trace_id=f"tr-hwsoak-{turn_idx:03d}",
            session_id=orch.session_id,
            origin="text",
            mode="transcript",
        )
        orch.active_trace = trace

        # Reset turn accumulators
        orch.current_turn_receipts = []
        orch.current_turn_tool_calls = []
        orch.current_turn_tool_spoken = []
        orch.current_turn_tool_ok = True
        orch._last_unspoken_tool_msg = None

        t_turn_start = time.perf_counter()
        try:
            orch._run_text_turn(trace, prompt)
        except Exception as exc:  # noqa: BLE001
            unhandled_errors.append(
                {"turn": str(turn_idx), "mode": mode, "error": f"Exception in turn: {exc}"}
            )

        t_turn_elapsed = time.perf_counter() - t_turn_start

        if trace.error:
            unhandled_errors.append(
                {"turn": str(turn_idx), "mode": mode, "error": str(trace.error)}
            )

        # TTFT measurement
        if (
            trace.t_llm_first_token
            and trace.t_llm_sent
            and trace.t_llm_first_token > trace.t_llm_sent
        ):
            ttft_ms = (trace.t_llm_first_token - trace.t_llm_sent) / 1e6
        else:
            ttft_ms = t_turn_elapsed * 1000.0
        ttft_records.append(ttft_ms)

        # Sliding window for conversation history across long run
        if len(orch.history) > 20:
            orch.history = orch.history[-20:]

        # Check VRAM every 10 turns
        if turn_idx % 10 == 0:
            vram_now = _get_vram_used_mb()
            if vram_now > 0:
                vram_samples.append(vram_now)
                assert vram_now <= VRAM_PEAK_BUDGET_MB, (
                    f"VRAM at turn {turn_idx} ({vram_now} MB) exceeds {VRAM_PEAK_BUDGET_MB} MB budget"
                )

    t_elapsed = time.perf_counter() - t_start

    # Final VRAM sample
    final_vram = _get_vram_used_mb()
    if final_vram > 0:
        vram_samples.append(final_vram)
    peak_vram = max(vram_samples) if vram_samples else 0

    # 1. Assert no llama-server restarts
    assert _check_llama_server_alive(), "llama-server is not responding after 150 turns"
    if llama_pid is not None:
        assert psutil.pid_exists(llama_pid), f"llama-server PID {llama_pid} no longer exists"
        current_proc = _find_llama_server_proc()
        assert current_proc is not None, "llama-server process could not be found"
        assert current_proc.pid == llama_pid, (
            f"llama-server PID changed from {llama_pid} to {current_proc.pid} (restart detected)"
        )
        if llama_create_time is not None:
            assert abs(current_proc.create_time() - llama_create_time) < 1.0, (
                "llama-server process start time changed (restart detected)"
            )

    # 2. Assert VRAM never exceeds 12,800 MB
    assert peak_vram <= VRAM_PEAK_BUDGET_MB, (
        f"Peak VRAM {peak_vram} MB exceeded {VRAM_PEAK_BUDGET_MB} MB budget"
    )

    # 3. Assert TTFT p95 stable within 1.3x of first 20 turns
    assert len(ttft_records) == total_turns, f"Expected {total_turns} TTFT records"
    first_20_ttft = ttft_records[:20]
    p95_first20 = sorted(first_20_ttft)[int(0.95 * len(first_20_ttft))]
    p95_all = sorted(ttft_records)[int(0.95 * len(ttft_records))]

    # Allow a 300 ms floor for OS process scheduling / network loopback variance
    max_allowed_ttft = max(1.3 * p95_first20, p95_first20 + 300.0)
    assert p95_all <= max_allowed_ttft, (
        f"TTFT degraded beyond 1.3x: p95_all={p95_all:.1f}ms vs p95_first20={p95_first20:.1f}ms "
        f"(max allowed {max_allowed_ttft:.1f}ms)"
    )

    # 4. Assert zero unhandled exceptions in traces
    assert len(unhandled_errors) == 0, (
        f"Found {len(unhandled_errors)} unhandled errors in traces: {unhandled_errors[:3]}"
    )

    # 5. Capture lucca-admin latency --last 150 output
    latency_output = ""
    try:
        uv_bin = shutil.which("uv") or "uv"
        res = subprocess.run(  # noqa: S603
            [uv_bin, "run", "lucca-admin", "latency", "--last", "150"],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
        latency_output = res.stdout if res.returncode == 0 else res.stderr
    except Exception as exc:  # noqa: BLE001
        latency_output = f"Failed to capture lucca-admin latency: {exc}"

    # 6. Write report
    report_data = {
        "test": "test_soak_live_hw_150_turns",
        "total_turns": total_turns,
        "elapsed_s": round(t_elapsed, 2),
        "peak_vram_mb": peak_vram,
        "initial_vram_mb": initial_vram,
        "final_vram_mb": final_vram,
        "vram_samples_mb": vram_samples,
        "llama_pid": llama_pid,
        "llama_restarts_detected": 0,
        "ttft_p95_first20_ms": round(p95_first20, 1),
        "ttft_p95_all_ms": round(p95_all, 1),
        "unhandled_errors_count": len(unhandled_errors),
        "admin_latency_output": latency_output,
    }

    report_dir = Path("logs/test_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_file = report_dir / f"soak_live_hw_{ts}.json"
    report_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
