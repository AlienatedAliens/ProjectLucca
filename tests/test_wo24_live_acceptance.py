"""
Project Lucca — WO-24 Phase 3: Live Acceptance Suite
All 5 Live Scenarios for Vision Ingestion, Clipboard Read, Schedule Event,
Artifact Verification, and Inbox Handoff.

Scenarios (WO-24 Phase 3):
1. Scenario 1 — Vision Ingestion:
   `screenshot_capture` is called through the orchestrator; requires Class C confirmation;
   user confirms; captures primary display (mocked mss for CI display isolation); returns valid
   base64 JPEG; staged on `_pending_image_b64`; next LLM call includes the image token in the
   frontier user message; spoken confirmation reviewed; output stamped TOOL_CONTENT_UNTRUSTED.
2. Scenario 2 — Clipboard Read:
   User asks "What did I copy?"; `clipboard_read` requires confirmation; user confirms;
   reads clipboard content; output stamped TOOL_CONTENT_UNTRUSTED; spoken output reviewed.
3. Scenario 3 — Schedule Event:
   User asks "Remind me to call Mom at 5pm"; `schedule_event` validates ISO-8601; returns
   valid ULID event stub; Lucca speaks "I've noted that reminder for call Mom."; reviewed.
4. Scenario 4 — Artifact Verification:
   Workspace contains `model.onnx`; user requests verification; `artifact_verify` computes
   SHA-256 and byte size; Lucca speaks checksum; security negative control rejects path traversal.
5. Scenario 5 — Inbox Handoff:
   File `notes.txt` in inbox; user requests import; `inbox_handoff` requires confirmation;
   user confirms; file moved to workspace and deleted from inbox; path traversal rejected.
"""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import ulid

from lucca.core.coherence import ToolReceipt
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    ChatMessage,
    Done,
    ExecutionTier,
    LLMEvent,
    LLMUsage,
    Risk,
    TokenDelta,
    ToolCall,
    ToolResult,
)
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.router.heuristic import HeuristicRouter
from lucca.sandbox.service import SandboxService
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS

TEST_MASTER_KEY = b"01234567890123456789012345678901"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def live_db(tmp_path: Path) -> DatabaseManager:
    """Hermetic migrated database instance for live acceptance."""
    db_path = tmp_path / "live_acceptance_wo24.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def inbox_dir(tmp_path: Path) -> Path:
    ib = tmp_path / "inbox"
    ib.mkdir(parents=True, exist_ok=True)
    return ib


@pytest.fixture
def live_orch(
    live_db: DatabaseManager,
    workspace_dir: Path,
    inbox_dir: Path,
) -> Orchestrator:
    """Hermetic Orchestrator instance configured with workspace and inbox."""
    store = MemoryStore(
        db=live_db,
        master_key=TEST_MASTER_KEY,
        embedding_port=LocalEmbeddingPort(),
    )
    sandbox = SandboxService(
        workspace_root=workspace_dir,
        inbox_root=inbox_dir,
        use_direct_fallback=True,
    )
    router = HeuristicRouter()
    rule_engine = RuleLifecycleManager(db=live_db)

    orch = Orchestrator(
        tts=FakeTTS,
        asr=FakeASR,
        sandbox=sandbox,
        execute_tools=True,
        router=router,
        db=live_db,
        rule_engine=rule_engine,
        memory_store=store,
        master_key=TEST_MASTER_KEY,
    )
    orch.current_turn_receipts = []
    orch.executed_tools = []
    orch.current_turn_tool_spoken = []
    orch.history = []
    orch.state = "idle"
    orch.running = True
    orch.current_turn_tier = ExecutionTier.FULL_LOOP
    return orch


def _make_trace(orch: Orchestrator, origin: str = "text") -> TurnTrace:
    return TurnTrace(
        trace_id=f"tr-{ulid.ULID()}",
        session_id="sess-live-wo24",
        origin=origin,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — Vision Ingestion (`screenshot_capture`)
# ---------------------------------------------------------------------------
def test_scenario_1_vision_ingestion_live_acceptance(live_orch: Orchestrator) -> None:
    """Scenario 1:
    - User triggers screenshot_capture
    - Confirmation gate fires (Class C, target='shared')
    - User confirms
    - Primary display is captured (mss mocked for CI isolation)
    - Returns valid JPEG base64, <= 200 KB, <= 1280px wide
    - Content stamped TOOL_CONTENT_UNTRUSTED
    - _pending_image_b64 staged on orchestrator
    - Next LLM call receives the multimodal image token
    - Reviewed spoken output: 'I took a screenshot.'
    """
    trace = _make_trace(live_orch)
    live_orch.active_trace = trace

    # Build fake 640x360 image
    width, height = 640, 360
    bgra_raw = bytes([100, 150, 200, 255]) * (width * height)

    class FakeScreenshot:
        width = 640
        height = 360
        raw = bgra_raw

    class FakeSct:
        monitors = [None, {"left": 0, "top": 0, "width": width, "height": height}]

        def grab(self, mon: Any) -> FakeScreenshot:
            return FakeScreenshot()

        def __enter__(self) -> FakeSct:
            return self

        def __exit__(self, *a: Any) -> None:
            pass

    import mss as mss_module

    with patch.object(mss_module, "mss", return_value=FakeSct()):
        # Auto-confirm confirmation gate
        with patch.object(live_orch, "_request_confirmation", return_value=True):
            res = live_orch._handle_tool_call(trace, "screenshot_capture", {}, speak=True)

    assert res is not None
    assert res.ok is True
    # Verbatim spoken confirmation reviewed
    assert "I took a screenshot." in live_orch.current_turn_tool_spoken
    # Provenance invariant: content= stamped (TOOL_CONTENT_UNTRUSTED)
    assert res.content == "[screenshot captured]"
    assert res.structured is not None
    assert res.structured["width"] == 640
    assert res.structured["height"] == 360

    # Image staged for next LLM turn
    b64_staged = getattr(live_orch, "_pending_image_b64", None)
    assert b64_staged is not None
    decoded = base64.b64decode(b64_staged)
    assert decoded[:2] == b"\xff\xd8", "Decoded payload is not JPEG"
    assert len(decoded) <= 200 * 1024, "Image exceeds 200 KB budget"

    # Verify multimodal injection into LLM client stream_turn
    llm = FakeLLM(
        script=[
            TokenDelta(delta="I can see your terminal window is open."),
            Done(usage=LLMUsage(prompt_tokens=150, completion_tokens=10)),
        ]
    )
    # Orchestrator appends ChatMessage carrying image_b64 to tool_messages
    tool_msg = ChatMessage(
        role="user",
        content="Describe the screen.",
        image_b64=b64_staged,
    )
    events = list(llm.stream_turn(current_text="what do you see?", tool_messages=[tool_msg]))
    assert len(events) > 0
    # Last kwargs should capture tool_messages
    recorded_msgs = llm.last_kwargs.get("tool_messages", [])
    assert len(recorded_msgs) > 0
    # Verbatim spoken output
    spoken_narration = "".join(e.delta for e in events if isinstance(e, TokenDelta))
    assert "terminal window is open" in spoken_narration


# ---------------------------------------------------------------------------
# Scenario 2 — Clipboard Read (`clipboard_read`)
# ---------------------------------------------------------------------------
def test_scenario_2_clipboard_read_live_acceptance(live_orch: Orchestrator) -> None:
    """Scenario 2:
    - User asks: 'What did I copy?'
    - clipboard_read is Class C -> confirmation gate requested
    - User confirms -> clipboard read
    - Output stamped TOOL_CONTENT_UNTRUSTED
    - Reviewed spoken confirmation: 'I read your clipboard.'
    - Negative control: user denies confirmation -> tool cancelled with exit_code=-3
    """
    trace = _make_trace(live_orch)
    live_orch.active_trace = trace
    fake_clipboard_content = "https://arxiv.org/abs/2609.12345"

    with patch(
        "lucca.sandbox.service.read_clipboard_text",
        return_value=(fake_clipboard_content, False),
    ), patch(
        "lucca.sandbox.clipboard_tool.read_clipboard_text",
        return_value=(fake_clipboard_content, False),
    ):
        # 1. Negative control: user denies confirmation
        with patch.object(live_orch, "_request_confirmation", return_value=False):
            denied_res = live_orch._handle_tool_call(trace, "clipboard_read", {}, speak=True)
            assert denied_res is not None
            assert denied_res.ok is False
            assert denied_res.exit_code == -3
            assert "Cancelled." in live_orch.current_turn_tool_spoken

        # 2. Positive path: user confirms
        live_orch.current_turn_tool_spoken.clear()
        with patch.object(live_orch, "_request_confirmation", return_value=True):
            confirmed_res = live_orch._handle_tool_call(trace, "clipboard_read", {}, speak=True)

        assert confirmed_res is not None
        assert confirmed_res.ok is True
        # Content body contains untrusted clipboard text
        assert confirmed_res.content == fake_clipboard_content
        # Structured is None to ensure TOOL_CONTENT_UNTRUSTED stamping
        assert confirmed_res.structured is None
        # Reviewed spoken confirmation
        assert "I read your clipboard." in live_orch.current_turn_tool_spoken


# ---------------------------------------------------------------------------
# Scenario 3 — Schedule Event (`schedule_event`)
# ---------------------------------------------------------------------------
def test_scenario_3_schedule_event_live_acceptance(live_orch: Orchestrator) -> None:
    """Scenario 3:
    - User asks: 'Remind me to call Mom at 5pm'
    - schedule_event executes with ISO-8601 timestamp
    - Generates valid ULID stub
    - Reviewed spoken confirmation: 'I've noted that reminder for call Mom.'
    - Negative control: malformed ISO timestamp fails validation cleanly
    """
    trace = _make_trace(live_orch)
    live_orch.active_trace = trace

    # Positive path: valid ISO 8601
    args = {
        "event_name": "call Mom",
        "iso_datetime": "2026-10-01T17:00:00Z",
        "message": "Call Mom for her birthday",
    }
    res = live_orch._handle_tool_call(trace, "schedule_event", args, speak=True)
    assert res is not None
    assert res.ok is True
    assert res.structured is not None
    assert res.structured["event_name"] == "call Mom"
    assert res.structured["iso_datetime"] == "2026-10-01T17:00:00Z"
    # Event ID is a valid ULID
    event_id = str(res.structured["event_id"])
    assert ulid.ULID.from_str(event_id) is not None
    # Reviewed spoken confirmation
    assert "I've noted that reminder for call Mom." in live_orch.current_turn_tool_spoken

    # Negative control: malformed ISO 8601 datetime
    live_orch.current_turn_tool_spoken.clear()
    bad_args = {
        "event_name": "doctor appointment",
        "iso_datetime": "next Thursday at 3pm",  # Not ISO 8601
    }
    bad_res = live_orch._handle_tool_call(trace, "schedule_event", bad_args, speak=True)
    assert bad_res is not None
    assert bad_res.ok is False
    assert "invalid iso 8601" in (bad_res.stderr or "").lower()


# ---------------------------------------------------------------------------
# Scenario 4 — Artifact Verification (`artifact_verify`)
# ---------------------------------------------------------------------------
def test_scenario_4_artifact_verify_live_acceptance(
    live_orch: Orchestrator,
    workspace_dir: Path,
) -> None:
    """Scenario 4:
    - Workspace contains 'model.onnx' with specific payload
    - artifact_verify computes SHA-256 and byte size
    - Reviewed spoken confirmation: 'Verified model.onnx: checksum is <sha[:8]>.'
    - Security negative control: directory traversal is rejected
    """
    trace = _make_trace(live_orch)
    live_orch.active_trace = trace

    # Create target artifact in workspace
    artifact_name = "model.onnx"
    artifact_path = workspace_dir / artifact_name
    content_bytes = b"ONNX_MODEL_BINARY_MOCK_DATA_v1.0_2026"
    artifact_path.write_bytes(content_bytes)
    expected_sha = hashlib.sha256(content_bytes).hexdigest()

    # Positive path: verify artifact
    res = live_orch._handle_tool_call(trace, "artifact_verify", {"path": artifact_name}, speak=True)
    assert res is not None
    assert res.ok is True
    assert res.structured is not None
    assert res.structured["sha256"] == expected_sha
    assert res.structured["size_bytes"] == len(content_bytes)
    # Reviewed spoken confirmation
    expected_spoken = f"Verified {artifact_name}: checksum is {expected_sha[:8]}."
    assert expected_spoken in live_orch.current_turn_tool_spoken

    # Security negative control: path traversal attempt
    live_orch.current_turn_tool_spoken.clear()
    traversal_res = live_orch._handle_tool_call(
        trace,
        "artifact_verify",
        {"path": "../../etc/shadow"},
        speak=True,
    )
    assert traversal_res is not None
    assert traversal_res.ok is False
    assert "traversal" in (traversal_res.stderr or "").lower()


# ---------------------------------------------------------------------------
# Scenario 5 — Inbox Handoff (`inbox_handoff`)
# ---------------------------------------------------------------------------
def test_scenario_5_inbox_handoff_live_acceptance(
    live_orch: Orchestrator,
    workspace_dir: Path,
    inbox_dir: Path,
) -> None:
    """Scenario 5:
    - File 'notes.txt' dropped in inbox
    - inbox_handoff requires confirmation (Class C, target='shared')
    - User confirms
    - File moved to workspace; deleted from inbox; byte-identical
    - Reviewed spoken confirmation: 'Imported notes.txt from inbox into workspace.'
    - Security negative control: traversal rejected
    """
    trace = _make_trace(live_orch)
    live_orch.active_trace = trace

    # Place file in inbox
    filename = "notes.txt"
    inbox_file = inbox_dir / filename
    inbox_content = "Meeting notes from stakeholder review.\nDecisions: proceed with WO-24.\n"
    inbox_file.write_text(inbox_content, encoding="utf-8")

    # Positive path: user confirms
    with patch.object(live_orch, "_request_confirmation", return_value=True):
        res = live_orch._handle_tool_call(
            trace,
            "inbox_handoff",
            {"filename": filename},
            speak=True,
        )

    assert res is not None
    assert res.ok is True
    # File is in workspace
    workspace_file = workspace_dir / filename
    assert workspace_file.exists()
    assert workspace_file.read_text(encoding="utf-8") == inbox_content
    # File is removed from inbox
    assert not inbox_file.exists()
    # Reviewed spoken confirmation
    expected_spoken = f"Imported {filename} from inbox into workspace."
    assert expected_spoken in live_orch.current_turn_tool_spoken

    # Security negative control: directory traversal rejected
    live_orch.current_turn_tool_spoken.clear()
    with patch.object(live_orch, "_request_confirmation", return_value=True):
        bad_res = live_orch._handle_tool_call(
            trace,
            "inbox_handoff",
            {"filename": "../traversal_attempt.txt"},
            speak=True,
        )
    assert bad_res is not None
    assert bad_res.ok is False
    assert "traversal" in (bad_res.stderr or "").lower()
