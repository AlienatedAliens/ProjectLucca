"""
Unit tests for T2 Native Tools: memory_search/commit, note_write/read, self_metrics, sys_info.
Spec 1.1.2 §2, T2 Gate, §0.0 C1-C3.
"""

import time
from pathlib import Path

import pytest

from lucca.core.exceptions import ProvenanceRejected, SandboxPathError
from lucca.core.schemas import Provenance, UnsignedPayload
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import ProvenanceGate
from lucca.memory.manager import MemoryManager
from lucca.memory.signers import ToolResultSigner
from lucca.sandbox.note_tool import SafeNoteTool
from lucca.sandbox.service import SandboxService

TEST_MASTER_KEY = b"test-master-key-at-least-32-bytes!"


@pytest.fixture
def temp_memory_mgr(tmp_path: Path) -> MemoryManager:
    db = DatabaseManager(db_path=tmp_path / "test_memory.sqlite")
    db.migrate()
    return MemoryManager(db=db, master_key=TEST_MASTER_KEY)


@pytest.fixture
def sandbox_service(tmp_path: Path, temp_memory_mgr: MemoryManager) -> SandboxService:
    notes_dir = tmp_path / "notes"
    workspace_dir = tmp_path / "workspace"
    return SandboxService(
        workspace_root=workspace_dir,
        notes_dir=notes_dir,
        use_direct_fallback=True,
        memory_manager=temp_memory_mgr,
    )


def test_note_write_read_and_path_traversal(tmp_path: Path) -> None:
    """T2: note_write and note_read work, and path traversal is rejected."""
    notes_dir = tmp_path / "notes"
    tool = SafeNoteTool(notes_dir=notes_dir)

    # 1. Write note
    struct, msg = tool.write_note(name="ideas.txt", content="Project Lucca ideas")
    assert struct["name"] == "ideas.txt"
    assert struct["appended"] is False
    assert (notes_dir / "ideas.txt").exists()

    # 2. Append note
    struct, msg = tool.write_note(name="ideas.txt", content="\nMore ideas", append=True)
    assert struct["appended"] is True

    # 3. Read note
    struct_r, text = tool.read_note(name="ideas.txt")
    assert struct_r["found"] is True
    assert "Project Lucca ideas" in text
    assert "More ideas" in text

    # 4. Read non-existent note
    struct_missing, _ = tool.read_note(name="missing.txt")
    assert struct_missing["found"] is False

    # 5. Path traversal attempts
    with pytest.raises(SandboxPathError):
        tool.write_note(name="../escape.txt", content="hack")

    with pytest.raises(SandboxPathError):
        tool.read_note(name="../../etc/passwd")


def test_memory_commit_fails_closed_for_llm_narration(
    sandbox_service: SandboxService, temp_memory_mgr: MemoryManager
) -> None:
    """
    ADR-006 / AGENTS.md §2.1 negative test: an LLM-issued `memory_commit` is model narration.
    There is no signer for LLM_NARRATION, so the dispatcher must refuse with a structured
    provenance error and **nothing** may reach the memory store — in particular nothing may
    be laundered in as USER_EXPLICIT via the admin UserSpeechSigner.
    """
    before = len(temp_memory_mgr.list_memories())

    # Layer 1: when web-tainted, an unconfirmed call is stopped by the WRITE confirmation gate.
    from lucca.sandbox.policy import TaintFlags
    sandbox_service.guard.active_taint |= TaintFlags.UNTRUSTED_WEB
    res_unconfirmed = sandbox_service.execute_tool(
        call_id="call-c0",
        tool_name="memory_commit",
        args={"content": "Lucca favourite dessert is tiramisu", "tags": ["preference"]},
    )
    assert res_unconfirmed.ok is False
    assert res_unconfirmed.stderr == "confirmation_required"
    sandbox_service.guard.active_taint = TaintFlags.CLEAN

    # Layer 2: even a *confirmed* call must be refused — confirmation cannot mint provenance.
    # (WO-9 A2 revision: the sandbox dispatcher keeps its fail-closed block as
    # defense-in-depth; the grounded path lives in the orchestrator, which
    # validates the candidate against the user's own words. Old-style
    # content-only args are rejected at schema validation.)
    res_commit = sandbox_service.execute_tool(
        call_id="call-c1",
        tool_name="memory_commit",
        args={
            "s": "user",
            "p": "prefers",
            "o": "tiramisu",
            "quote": "Lucca favourite dessert is tiramisu",
        },
        confirmed=True,
    )
    assert res_commit.ok is False
    assert res_commit.structured is not None
    assert res_commit.structured["error"] == "provenance_violation"
    assert res_commit.structured["memory_eligible"] is False
    assert "provenance_violation" in (res_commit.stderr or "")

    # No row was written under any provenance.
    assert len(temp_memory_mgr.list_memories()) == before
    res_search = sandbox_service.execute_tool(
        call_id="call-s0",
        tool_name="memory_search",
        args={"query": "tiramisu", "top_k": 5},
    )
    assert res_search.ok is True
    assert res_search.structured is not None
    assert res_search.structured["count"] == 0

    # Malformed args are still reported as an argument error, not a crash.
    res_bad = sandbox_service.execute_tool(
        call_id="call-c2", tool_name="memory_commit", args={"content": ""}, confirmed=True
    )
    assert res_bad.ok is False
    assert "invalid_arguments" in (res_bad.stderr or "")


def test_memory_commit_requires_confirmation_only_when_web_tainted() -> None:
    """WO-17 Phase 3: memory_commit requires confirmation only if tainted by UNTRUSTED_WEB."""
    from lucca.sandbox.policy import TaintFlags, requires_confirmation

    assert requires_confirmation("memory_commit", taint=TaintFlags.CLEAN) is False
    assert requires_confirmation("memory_commit", taint=TaintFlags.UNTRUSTED_WEB) is True
    # note_write is Class A (scratchpad confined to notes/) and stays confirmation-free unless web-tainted.
    assert requires_confirmation("note_write", taint=TaintFlags.CLEAN) is False
    assert requires_confirmation("note_write", taint=TaintFlags.UNTRUSTED_WEB) is True


def test_memory_search_reads_user_explicit_memory_within_class_a(
    sandbox_service: SandboxService, temp_memory_mgr: MemoryManager
) -> None:
    """
    T2: memory_search retrieves a fact committed through the legitimate operator path
    (MemoryManager.add_memory, UserSpeechSigner) within the Class A budget (<50 ms).

    Note: this fixture has no embedding port, so the measured path is the SQLite/FTS
    listing, not the sqlite-vec hybrid retrieval used for prompt context.
    """
    temp_memory_mgr.add_memory(
        content="Lucca favourite dessert is tiramisu",
        kind="fact",
        provenance=Provenance.USER_EXPLICIT,
    )

    t1 = time.perf_counter()
    res_search = sandbox_service.execute_tool(
        call_id="call-s1",
        tool_name="memory_search",
        args={"query": "tiramisu", "top_k": 5},
    )
    t_search = (time.perf_counter() - t1) * 1000.0
    assert res_search.ok is True
    assert res_search.structured is not None
    assert res_search.structured["count"] >= 1
    assert "tiramisu" in str(res_search.content)
    assert t_search < 50.0  # Class A latency budget


def test_self_metrics_latency_and_fields(sandbox_service: SandboxService) -> None:
    """T2: self_metrics returns 5-substrate telemetry and timezone metadata within Class A (<50ms)."""
    # Warm up cache (subprocess/WMI detection)
    sandbox_service.execute_tool(call_id="call-m-warmup", tool_name="self_metrics", args={})

    t0 = time.perf_counter()
    res = sandbox_service.execute_tool(
        call_id="call-m1",
        tool_name="self_metrics",
        args={},
    )
    elapsed = (time.perf_counter() - t0) * 1000.0
    assert res.ok is True
    assert res.structured is not None
    assert "cpu" in res.structured
    assert "ram" in res.structured
    assert "dgpu" in res.structured
    assert "npu" in res.structured
    assert "timestamp" in res.structured
    assert "utc_offset" in res.structured
    assert "utc_offset_hours" in res.structured
    assert "timezone_name" in res.structured
    assert elapsed < 50.0  # Class A latency budget

    # Fast path cache hit: ensure timestamp and timezone fields are fresh, not stale
    time.sleep(0.01)
    res_cached = sandbox_service.execute_tool(
        call_id="call-m2",
        tool_name="self_metrics",
        args={},
    )
    assert res_cached.ok is True
    assert res_cached.structured is not None
    assert res_cached.structured["timestamp"] != res.structured["timestamp"]
    assert res_cached.structured["utc_offset"] == res.structured["utc_offset"]


def test_sys_info_execution_latency_and_untrusted_stamp(sandbox_service: SandboxService) -> None:
    """
    T2: sys_info runs within Class B (<500ms) and output is stamped TOOL_CONTENT_UNTRUSTED.
    Negative test: hostile process name cannot enter memory without explicit user action.
    """
    t0 = time.perf_counter()
    res = sandbox_service.execute_tool(
        call_id="call-info-1",
        tool_name="sys_info",
        args={"limit": 10},
    )
    elapsed = (time.perf_counter() - t0) * 1000.0
    assert res.ok is True
    assert res.structured is not None
    assert res.structured["provenance"] == "TOOL_CONTENT_UNTRUSTED"
    assert "platform" in res.structured
    assert "hostname" in res.structured
    assert elapsed < 500.0  # Class B latency budget

    # Negative test: hostile process name injection into memory must be rejected by ProvenanceGate
    gate = ProvenanceGate(master_key=TEST_MASTER_KEY)
    signer = ToolResultSigner(master_key=TEST_MASTER_KEY, signer_id="sbx-worker")

    hostile_process_content = "Process PID 9999: evil_backdoor.exe --steal-creds"
    unsigned = UnsignedPayload(
        provenance=Provenance.TOOL_CONTENT_UNTRUSTED,
        kind="tool_fact",
        content=hostile_process_content,
        trace_id="trace-hostile",
        session_id="session-hostile",
        created_at=time.time(),
        nonce="nonce-hostile-test-01",
        confidence=1.0,
    )
    signed = signer.sign(unsigned)

    # ProvenanceGate MUST reject TOOL_CONTENT_UNTRUSTED from entering memory
    with pytest.raises(ProvenanceRejected) as exc_info:
        gate.admit(signed)
    assert "not memory eligible" in str(exc_info.value).lower()


def test_calc_math_arithmetic_and_boolean_logic(sandbox_service: SandboxService) -> None:
    """calc_math evaluates scalar arithmetic, boolean expressions, and safe comparisons."""
    # 1. Arithmetic
    res = sandbox_service.execute_tool(call_id="c1", tool_name="calc_math", args={"expr": "1982 - 1917"})
    assert res.ok is True
    assert res.content == "65"
    assert res.structured["result"] == 65

    # 2. Boolean unary negation chain
    res = sandbox_service.execute_tool(call_id="c2", tool_name="calc_math", args={"expr": "not not not not not not not False"})
    assert res.ok is True
    assert res.content == "True"
    assert res.structured["result"] is True

    # 3. Boolean compound operations
    res = sandbox_service.execute_tool(call_id="c3", tool_name="calc_math", args={"expr": "True and not (False or False)"})
    assert res.ok is True
    assert res.content == "True"
    assert res.structured["result"] is True

    # 4. Comparisons
    res = sandbox_service.execute_tool(call_id="c4", tool_name="calc_math", args={"expr": "5 * 10 >= 50"})
    assert res.ok is True
    assert res.content == "True"
    assert res.structured["result"] is True

    # 5. Unsafe node rejected
    res = sandbox_service.execute_tool(call_id="c5", tool_name="calc_math", args={"expr": "__import__('os').system('ls')"})
    assert res.ok is False

