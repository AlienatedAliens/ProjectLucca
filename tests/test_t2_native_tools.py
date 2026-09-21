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


def test_memory_commit_and_search(sandbox_service: SandboxService) -> None:
    """T2: memory_commit writes user fact; memory_search retrieves it within Class A (<50ms)."""
    t0 = time.perf_counter()
    res_commit = sandbox_service.execute_tool(
        call_id="call-c1",
        tool_name="memory_commit",
        args={"content": "Lucca favourite dessert is tiramisu", "tags": ["preference"]},
    )
    t_commit = (time.perf_counter() - t0) * 1000.0
    assert res_commit.ok is True
    assert res_commit.structured is not None
    assert "memory_id" in res_commit.structured
    assert t_commit < 50.0  # Class A latency budget

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
    """T2: self_metrics returns 5-substrate telemetry within Class A (<50ms)."""
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
    assert elapsed < 50.0  # Class A latency budget


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
