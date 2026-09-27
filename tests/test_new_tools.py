"""
Project Lucca — WO-24 Phase 0: Four Deferred Native Tools & Cap Raise
Tests for schedule_event, artifact_verify, clipboard_read, inbox_handoff.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
import ulid

from lucca.core.capabilities import (
    MAX_REGISTRY_TOOLS,
    CapabilityRegistry,
    get_default_native_tools,
)
from lucca.core.schemas import Risk, ToolParameter, ToolResult, ToolSchema, TurnTrace
from lucca.sandbox.policy import requires_confirmation
from lucca.sandbox.service import SandboxService


def test_static_tool_count_and_cap_gates():
    """Static gate: registry has exactly 23 tools and MAX_REGISTRY_TOOLS is 23."""
    tools = get_default_native_tools()
    assert len(tools) == 23, f"Expected exactly 23 native tools in Phase 0, found {len(tools)}"
    assert MAX_REGISTRY_TOOLS == 23, f"Expected MAX_REGISTRY_TOOLS to be 23, got {MAX_REGISTRY_TOOLS}"

    # CapabilityRegistry must construct cleanly without raising
    registry = CapabilityRegistry(tools=tools)
    assert len(registry.tools) == 23

    # Adding a 24th tool must trip the cap gate
    oversized = dict(tools)
    oversized["extra_tool_24"] = ToolSchema(
        name="extra_tool_24",
        description="extra",
        parameters={},
        risk=Risk.READ,
        target="self",
    )
    with pytest.raises(ValueError, match="Registry cap exceeded"):
        CapabilityRegistry(tools=oversized)


def test_new_tool_taxonomies_and_schemas():
    """Verify tool metadata for all 4 new tools per ratified spec."""
    tools = get_default_native_tools()

    # 1. schedule_event (Class A, self, READ)
    assert "schedule_event" in tools
    se = tools["schedule_event"]
    assert se.target == "self"
    assert se.risk == Risk.READ
    assert "event_name" in se.parameters and se.parameters["event_name"].required
    assert "iso_datetime" in se.parameters and se.parameters["iso_datetime"].required
    assert "message" in se.parameters and not se.parameters["message"].required

    # 2. artifact_verify (Class A, self, READ)
    assert "artifact_verify" in tools
    av = tools["artifact_verify"]
    assert av.target == "self"
    assert av.risk == Risk.READ
    assert "path" in av.parameters and av.parameters["path"].required

    # 3. clipboard_read (Class C, shared, READ)
    assert "clipboard_read" in tools
    cr = tools["clipboard_read"]
    assert cr.target == "shared"
    assert cr.risk == Risk.READ
    assert len(cr.parameters) == 0

    # 4. inbox_handoff (Class C, shared, WRITE)
    assert "inbox_handoff" in tools
    ih = tools["inbox_handoff"]
    assert ih.target == "shared"
    assert ih.risk == Risk.WRITE
    assert "filename" in ih.parameters and ih.parameters["filename"].required


def test_class_c_confirmation_policy_enforcement():
    """Class C tools must require user confirmation; Class A must run frictionless."""
    # Class C shared sensory boundary: requires confirmation
    assert requires_confirmation("clipboard_read") is True
    assert requires_confirmation("inbox_handoff") is True

    # Class A self: frictionless (unless untrusted web taint)
    assert requires_confirmation("schedule_event") is False
    assert requires_confirmation("artifact_verify") is False


def test_artifact_verify_functional(tmp_path: Path):
    """artifact_verify returns correct sha256 and byte size; blocks path traversal."""
    ws = tmp_path / "workspace"
    inbox = tmp_path / "inbox"
    ws.mkdir()
    inbox.mkdir()

    service = SandboxService(workspace_root=ws, inbox_root=inbox)

    # Seed known file
    data = b"Hello Project Lucca Artifact Verification"
    expected_sha = hashlib.sha256(data).hexdigest()
    (ws / "artifact.dat").write_bytes(data)

    res = service.execute_tool(
        call_id="call-av-1",
        tool_name="artifact_verify",
        args={"path": "artifact.dat"},
        confirmed=True,
    )
    assert res.ok is True
    assert res.structured is not None
    assert res.structured["sha256"] == expected_sha
    assert res.structured["size_bytes"] == len(data)
    assert res.structured["path"] == "artifact.dat"

    # Negative control: path traversal disallowed
    res_trav = service.execute_tool(
        call_id="call-av-2",
        tool_name="artifact_verify",
        args={"path": "../secret.txt"},
        confirmed=True,
    )
    assert res_trav.ok is False
    assert "traversal" in res_trav.stderr.lower()

    # Negative control: missing file
    res_miss = service.execute_tool(
        call_id="call-av-3",
        tool_name="artifact_verify",
        args={"path": "nonexistent.txt"},
        confirmed=True,
    )
    assert res_miss.ok is False


def test_clipboard_read_functional(tmp_path: Path):
    """clipboard_read truncates at 2000 chars, stamps TOOL_CONTENT_UNTRUSTED (structured=None)."""
    ws = tmp_path / "workspace"
    inbox = tmp_path / "inbox"
    service = SandboxService(workspace_root=ws, inbox_root=inbox)

    # 1. Unconfirmed call must fail closed
    unconfirmed_res = service.execute_tool(
        call_id="call-cr-0",
        tool_name="clipboard_read",
        args={},
        confirmed=False,
    )
    assert unconfirmed_res.ok is False
    assert "confirmation_required" in unconfirmed_res.stderr

    # 2. Confirmed call with mocked text
    mock_text = "Sample clipboard text from user application."
    with patch("lucca.sandbox.service.read_clipboard_text", return_value=(mock_text, False)):
        res = service.execute_tool(
            call_id="call-cr-1",
            tool_name="clipboard_read",
            args={},
            confirmed=True,
        )
        assert res.ok is True
        assert res.content == mock_text
        # TRAP 2: structured must be None so provenance gate stamps TOOL_CONTENT_UNTRUSTED
        assert res.structured is None

    # 3. Truncation control (over 2000 chars)
    long_mock = "A" * 2500
    with patch(
        "lucca.sandbox.service.read_clipboard_text",
        return_value=(long_mock[:2000], True),
    ):
        res_trunc = service.execute_tool(
            call_id="call-cr-2",
            tool_name="clipboard_read",
            args={},
            confirmed=True,
        )
        assert res_trunc.ok is True
        assert len(res_trunc.content or "") == 2000
        assert res_trunc.content_truncated is True
        assert res_trunc.structured is None


def test_inbox_handoff_functional(tmp_path: Path):
    """inbox_handoff moves file from inbox to workspace; blocks traversal; fails unconfirmed."""
    ws = tmp_path / "workspace"
    inbox = tmp_path / "inbox"
    ws.mkdir()
    inbox.mkdir()

    service = SandboxService(workspace_root=ws, inbox_root=inbox)

    # Seed inbox file
    (inbox / "handoff_data.csv").write_text("col1,col2\nval1,val2")

    # 1. Unconfirmed call fails closed
    unconfirmed = service.execute_tool(
        call_id="call-ih-0",
        tool_name="inbox_handoff",
        args={"filename": "handoff_data.csv"},
        confirmed=False,
    )
    assert unconfirmed.ok is False
    assert "confirmation_required" in unconfirmed.stderr
    assert (inbox / "handoff_data.csv").exists()

    # 2. Confirmed call succeeds and moves file
    res = service.execute_tool(
        call_id="call-ih-1",
        tool_name="inbox_handoff",
        args={"filename": "handoff_data.csv"},
        confirmed=True,
    )
    assert res.ok is True
    assert not (inbox / "handoff_data.csv").exists()
    assert (ws / "handoff_data.csv").exists()
    assert (ws / "handoff_data.csv").read_text() == "col1,col2\nval1,val2"

    # 3. Negative control: path traversal
    res_trav = service.execute_tool(
        call_id="call-ih-2",
        tool_name="inbox_handoff",
        args={"filename": "../other.txt"},
        confirmed=True,
    )
    assert res_trav.ok is False

    # 4. Negative control: missing file
    res_miss = service.execute_tool(
        call_id="call-ih-3",
        tool_name="inbox_handoff",
        args={"filename": "ghost.txt"},
        confirmed=True,
    )
    assert res_miss.ok is False


def test_schedule_event_functional(tmp_path: Path):
    """schedule_event validates datetime and produces a valid ULID."""
    ws = tmp_path / "workspace"
    inbox = tmp_path / "inbox"
    service = SandboxService(workspace_root=ws, inbox_root=inbox)

    # Valid event
    res = service.execute_tool(
        call_id="call-se-1",
        tool_name="schedule_event",
        args={
            "event_name": "Team Standup",
            "iso_datetime": "2026-10-01T10:00:00+08:00",
            "message": "Weekly review",
        },
        confirmed=True,
    )
    assert res.ok is True
    assert res.structured is not None
    event_id = res.structured.get("event_id")
    assert isinstance(event_id, str)
    assert len(event_id) == 26
    # Valid ULID check
    parsed_ulid = ulid.ULID.from_str(event_id)
    assert str(parsed_ulid) == event_id

    # Negative control: invalid datetime
    res_bad_dt = service.execute_tool(
        call_id="call-se-2",
        tool_name="schedule_event",
        args={
            "event_name": "Call Mum",
            "iso_datetime": "next Thursday morning",
        },
        confirmed=True,
    )
    assert res_bad_dt.ok is False
    assert "invalid iso 8601" in res_bad_dt.stderr.lower()

    # Negative control: empty event name
    res_empty = service.execute_tool(
        call_id="call-se-3",
        tool_name="schedule_event",
        args={
            "event_name": "   ",
            "iso_datetime": "2026-10-01T10:00:00+08:00",
        },
        confirmed=True,
    )
    assert res_empty.ok is False


def test_orchestrator_action_descriptions_and_confirmation_hooks(tmp_path: Path):
    """Orchestrator action descriptions correctly format human confirmation requests."""
    from lucca.core.orchestrator import Orchestrator
    from tests.fakes.fake_asr import FakeASR
    from tests.fakes.fake_tts import FakeTTS

    ws = tmp_path / "orch_ws"
    ws.mkdir()
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    orch.sandbox.workspace_mgr.workspace_root = ws
    orch.sandbox.file_tool.workspace_root = ws

    try:
        desc_cr = orch._describe_tool_action("clipboard_read", {})
        assert desc_cr == "read your clipboard"

        desc_ih = orch._describe_tool_action("inbox_handoff", {"filename": "data.csv"})
        assert desc_ih == "move data.csv into my workspace from your inbox"

        desc_se = orch._describe_tool_action("schedule_event", {"event_name": "dentist"})
        assert desc_se == "schedule reminder for dentist"

        desc_av = orch._describe_tool_action("artifact_verify", {"path": "summary.txt"})
        assert desc_av == "verify summary.txt"

        # Direct handler tests on orchestrator
        trace = TurnTrace(
            trace_id="test-trace-1",
            points_ns={},
            e2e_latency_ms=0.0,
            mode="transcript",
        )

        # Test schedule_event through orchestrator handler
        res_se = orch._handle_schedule_event(
            call_id="call-se-orch",
            args={"event_name": "Doctor", "iso_datetime": "2026-10-02T14:30:00Z"},
        )
        assert res_se.ok is True
        assert "Doctor" in (res_se.content or "")

        # Test artifact_verify through orchestrator handler
        (ws / "doc.txt").write_text("Hello doc")
        res_av = orch._handle_artifact_verify(
            call_id="call-av-orch",
            args={"path": "doc.txt"},
        )
        assert res_av.ok is True
        assert "doc.txt" in (res_av.content or "")

    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


def test_clipboard_read_orchestrator_confirm_flow(tmp_path: Path):
    """End-to-end confirm flow: clipboard_read pauses in confirm_wait; accepted via click executes."""
    import time
    import numpy as np
    from lucca.core.ipc_schemas import PTTReleasedPayload
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.schemas import Done, LLMUsage, ToolCall, ToolCallEnd
    from tests.fakes.fake_asr import FakeASR
    from tests.fakes.fake_llm import FakeLLM
    from tests.fakes.fake_tts import FakeTTS

    ws = tmp_path / "orch_ws"
    ws.mkdir()
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    orch.sandbox.workspace_mgr.workspace_root = ws
    orch.sandbox.file_tool.workspace_root = ws

    try:
        call = ToolCall(tool="clipboard_read", args={}, call_id="call-cr-e2e")
        orch.llm = FakeLLM(
            script=[
                ToolCallEnd(call=call),
                Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
            ]
        )

        orch._on_ptt_pressed(ts_ns=1000)
        orch.cap_ring.write(np.ones(16000, dtype=np.int16) * 1000)
        payload = PTTReleasedPayload(
            t_ns=2000,
            capture_seq_start=0,
            capture_seq_end=16000,
            duration_ms=1000.0,
            vad_speech_ms=900.0,
        )
        orch._on_ptt_released(ts_ns=2000, p=payload)

        for _ in range(50):
            if orch.state == "confirm_wait":
                break
            time.sleep(0.02)

        assert orch.state == "confirm_wait"
        assert orch._pending_confirmation_active is True

        # Accept confirmation
        orch.confirm_action(accepted=True, via="click")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=2.0)

        assert ("clipboard_read", {}) in orch.executed_tools
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


def test_inbox_handoff_orchestrator_confirm_flow(tmp_path: Path):
    """End-to-end confirm flow: inbox_handoff pauses in confirm_wait; accepted via click executes."""
    import time
    import numpy as np
    from lucca.core.ipc_schemas import PTTReleasedPayload
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.schemas import Done, LLMUsage, ToolCall, ToolCallEnd
    from tests.fakes.fake_asr import FakeASR
    from tests.fakes.fake_llm import FakeLLM
    from tests.fakes.fake_tts import FakeTTS

    ws = tmp_path / "orch_ws"
    inbox = tmp_path / "inbox"
    ws.mkdir()
    inbox.mkdir()
    (inbox / "report.csv").write_text("a,b,c")

    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    orch.sandbox.workspace_mgr.workspace_root = ws
    orch.sandbox.workspace_mgr.inbox_root = inbox
    orch.sandbox.file_tool.workspace_root = ws

    try:
        call = ToolCall(tool="inbox_handoff", args={"filename": "report.csv"}, call_id="call-ih-e2e")
        orch.llm = FakeLLM(
            script=[
                ToolCallEnd(call=call),
                Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=1)),
            ]
        )

        orch._on_ptt_pressed(ts_ns=1000)
        orch.cap_ring.write(np.ones(16000, dtype=np.int16) * 1000)
        payload = PTTReleasedPayload(
            t_ns=2000,
            capture_seq_start=0,
            capture_seq_end=16000,
            duration_ms=1000.0,
            vad_speech_ms=900.0,
        )
        orch._on_ptt_released(ts_ns=2000, p=payload)

        for _ in range(50):
            if orch.state == "confirm_wait":
                break
            time.sleep(0.02)

        assert orch.state == "confirm_wait"
        assert orch._pending_confirmation_active is True

        # Accept confirmation
        orch.confirm_action(accepted=True, via="click")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=2.0)

        assert ("inbox_handoff", {"filename": "report.csv"}) in orch.executed_tools
        assert (ws / "report.csv").exists()
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
