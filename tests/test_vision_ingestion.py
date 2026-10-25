"""
WO-24 Phase 1 — Vision Ingestion Test Suite
Tests: screenshot capture encoding, ChatMessage multimodal field, llm_client injection,
text-only regression, static count gate (24 tools), confirmation gate (Class C).
"""

from __future__ import annotations

import base64
import io
import struct
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lucca.brain.llm_client import LLMClient
from lucca.core.capabilities import MAX_REGISTRY_TOOLS, get_default_native_tools
from lucca.core.schemas import ChatMessage
from lucca.sandbox.policy import requires_confirmation


# ---------------------------------------------------------------------------
# Helper: create a minimal valid JPEG bytestring in memory (1×1 white pixel).
# Used where a real mss is not available.
# ---------------------------------------------------------------------------
def _fake_jpeg_bytes() -> bytes:
    """Return a minimal single-pixel JPEG (≤ 200 bytes)."""
    try:
        from PIL import Image  # type: ignore[import-untyped]

        img = Image.new("RGB", (4, 4), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        # Fallback: hardcoded minimal JPEG
        return bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000"
            "ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432"
            "ffc0000b080001000101011100ffc4001f000001050101010101000000000000000001020304050607080910"
            "ffc4003b100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a"
            "ffda0008010100003f00fbef6a00ffd9"
        )


def _fake_b64_jpeg() -> str:
    return base64.b64encode(_fake_jpeg_bytes()).decode("ascii")


# ---------------------------------------------------------------------------
# 1. Static count gate: 24 tools after Phase 1
# ---------------------------------------------------------------------------
def test_static_tool_count_24() -> None:
    """WO-24 Phase 1 static gate: registry has exactly 24 tools."""
    tools = get_default_native_tools()
    assert len(tools) == 24, f"Expected 24 tools, got {len(tools)}: {sorted(tools.keys())}"
    assert MAX_REGISTRY_TOOLS == 24


# ---------------------------------------------------------------------------
# 2. screenshot_capture schema
# ---------------------------------------------------------------------------
def test_screenshot_capture_schema() -> None:
    """screenshot_capture is in the registry with correct taxonomy."""
    tools = get_default_native_tools()
    assert "screenshot_capture" in tools
    sc = tools["screenshot_capture"]
    assert sc.target == "shared"
    from lucca.core.schemas import Risk

    assert sc.risk == Risk.READ
    assert sc.parameters == {}  # no parameters per ratified schema


# ---------------------------------------------------------------------------
# 3. Confirmation gate: screenshot_capture must require confirmation (Class C)
# ---------------------------------------------------------------------------
def test_screenshot_capture_requires_confirmation() -> None:
    """screenshot_capture is Class C — confirmation gate must fire unconditionally."""
    assert requires_confirmation("screenshot_capture") is True
    # Also verify it's not a false positive on a Class A tool
    assert requires_confirmation("read_file") is False


# ---------------------------------------------------------------------------
# 4. ChatMessage image_b64 field
# ---------------------------------------------------------------------------
def test_chatmessage_image_b64_field() -> None:
    """ChatMessage has optional image_b64 field defaulting to None."""
    msg = ChatMessage(role="user", content="hello")
    assert msg.image_b64 is None  # text-only path: field present but None

    b64 = _fake_b64_jpeg()
    msg2 = ChatMessage(role="user", content="describe this", image_b64=b64)
    assert msg2.image_b64 == b64


def test_chatmessage_text_only_model_dump() -> None:
    """When image_b64 is None, model_dump(exclude_none=True) does NOT emit image_b64."""
    msg = ChatMessage(role="user", content="text only")
    d = msg.model_dump(exclude_none=True)
    assert "image_b64" not in d  # zero regression on text-only path


# ---------------------------------------------------------------------------
# 5. llm_client: multimodal message format injection
# ---------------------------------------------------------------------------
def test_llm_client_injects_image_b64_into_last_user_message() -> None:
    """When a message carries image_b64, llm_client promotes frontier user message
    to multimodal content array with OpenAI image_url format."""
    b64 = _fake_b64_jpeg()

    # Build a message list where the last user message has image_b64
    msgs = [
        ChatMessage(role="system", content="system prompt"),
        ChatMessage(role="user", content="what is on my screen?", image_b64=b64),
    ]

    # Intercept the HTTP POST and capture the payload
    captured_payload: dict = {}

    def fake_stream(*args: Any, **kwargs: Any) -> Any:
        captured_payload.update(kwargs.get("json", {}))
        return MagicMock(
            __enter__=lambda s: s,
            __exit__=lambda *a: None,
            status_code=200,
            iter_lines=lambda: iter(["data: [DONE]"]),
        )

    import httpx

    with patch.object(httpx.Client, "stream", fake_stream):
        client = LLMClient(base_url="http://localhost:9999")
        list(client.stream_turn(messages=msgs))

    # Verify the payload's messages array
    payload_messages = captured_payload.get("messages", [])
    # Find the last user message in payload
    last_user = next((m for m in reversed(payload_messages) if m.get("role") == "user"), None)
    assert last_user is not None, "No user message in payload"
    content = last_user.get("content")
    assert isinstance(content, list), (
        f"Expected multimodal list content, got {type(content).__name__}"
    )
    # Must contain a text block and an image_url block
    types = [block.get("type") for block in content]
    assert "text" in types, f"Missing text block in content: {types}"
    assert "image_url" in types, f"Missing image_url block in content: {types}"
    # Verify image URL format
    img_block = next(b for b in content if b.get("type") == "image_url")
    url = img_block["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,"), f"Wrong image URL format: {url[:50]}"
    assert b64 in url, "base64 data not in image URL"


def test_llm_client_image_b64_consumed_after_call() -> None:
    """image_b64 is cleared from the ChatMessage object after llm_client consumes it."""
    b64 = _fake_b64_jpeg()
    msgs = [
        ChatMessage(role="system", content="sys"),
        ChatMessage(role="user", content="screenshot", image_b64=b64),
    ]

    import httpx

    def fake_stream(*args: Any, **kwargs: Any) -> Any:
        return MagicMock(
            __enter__=lambda s: s,
            __exit__=lambda *a: None,
            status_code=200,
            iter_lines=lambda: iter(["data: [DONE]"]),
        )

    with patch.object(httpx.Client, "stream", fake_stream):
        client = LLMClient(base_url="http://localhost:9999")
        list(client.stream_turn(messages=msgs))

    # After stream_turn, image_b64 must be None on the message object
    assert msgs[1].image_b64 is None, "image_b64 was not cleared after LLM call — TRAP 3 violation"


def test_llm_client_text_only_regression() -> None:
    """When no message carries image_b64, the payload content is a plain string (no regression)."""
    msgs = [
        ChatMessage(role="system", content="sys"),
        ChatMessage(role="user", content="what time is it?"),
    ]

    captured_payload: dict = {}

    import httpx

    def fake_stream(*args: Any, **kwargs: Any) -> Any:
        captured_payload.update(kwargs.get("json", {}))
        return MagicMock(
            __enter__=lambda s: s,
            __exit__=lambda *a: None,
            status_code=200,
            iter_lines=lambda: iter(["data: [DONE]"]),
        )

    with patch.object(httpx.Client, "stream", fake_stream):
        client = LLMClient(base_url="http://localhost:9999")
        list(client.stream_turn(messages=msgs))

    payload_messages = captured_payload.get("messages", [])
    last_user = next((m for m in reversed(payload_messages) if m.get("role") == "user"), None)
    assert last_user is not None
    content = last_user.get("content")
    assert isinstance(content, str), (
        f"Text-only path regression: expected str content, got {type(content).__name__}"
    )


# ---------------------------------------------------------------------------
# 6. capture_screenshot: encoding + budget constraint (with mocked mss)
# ---------------------------------------------------------------------------
def test_capture_screenshot_encoding_constraints() -> None:
    """capture_screenshot returns (b64_str, width, height) with decoded JPEG ≤ 200 KB and
    width ≤ 1280px. Uses a mocked mss.mss() to avoid requiring a real display."""
    import mss as mss_module

    # Build a fake 100×50 BGRA screenshot
    fake_width, fake_height = 100, 50
    bgra_pixel = bytes([30, 120, 200, 255])  # BGRA: B=30, G=120, R=200, A=255
    fake_raw = bgra_pixel * (fake_width * fake_height)

    fake_monitor = {"left": 0, "top": 0, "width": fake_width, "height": fake_height}

    class FakeScreenshot:
        width = fake_width
        height = fake_height
        raw = fake_raw

    class FakeSct:
        monitors = [None, fake_monitor]

        def grab(self, mon: dict) -> FakeScreenshot:
            return FakeScreenshot()

        def __enter__(self) -> "FakeSct":
            return self

        def __exit__(self, *a: Any) -> None:
            pass

    with patch.object(mss_module, "mss", return_value=FakeSct()):
        from lucca.sandbox.screenshot_tool import capture_screenshot

        b64, w, h = capture_screenshot(max_width=1280, quality=75)

    # Validate result
    assert isinstance(b64, str) and len(b64) > 0
    decoded = base64.b64decode(b64)
    assert len(decoded) <= 200 * 1024, f"JPEG exceeds 200KB budget: {len(decoded)} bytes"
    assert w <= 1280, f"Width {w} exceeds 1280px limit"
    assert h > 0
    # Verify it decodes as a JPEG (starts with FF D8)
    assert decoded[:2] == b"\xff\xd8", "Decoded bytes are not a valid JPEG"


# ---------------------------------------------------------------------------
# 7. _handle_screenshot_capture orchestrator handler (unit, no real display)
# ---------------------------------------------------------------------------
def test_handle_screenshot_capture_orchestrator_ok() -> None:
    """_handle_screenshot_capture stores _pending_image_b64 and returns TOOL_CONTENT_UNTRUSTED
    (content= not structured= only)."""
    from unittest.mock import MagicMock, patch

    from lucca.core.orchestrator import Orchestrator

    orch = object.__new__(Orchestrator)
    orch.sandbox = MagicMock()
    orch._record_tool_receipt = MagicMock()
    orch._pending_image_b64 = None

    fake_b64 = _fake_b64_jpeg()

    with patch(
        "lucca.core.orchestrator.capture_screenshot",
        return_value=(fake_b64, 100, 50),
        create=True,
    ):
        with patch(
            "lucca.sandbox.screenshot_tool.capture_screenshot",
            return_value=(fake_b64, 100, 50),
        ):
            res = orch._handle_screenshot_capture("call-001", {})

    assert res.ok is True
    assert res.content == "[screenshot captured]"
    assert res.structured is not None
    assert res.structured["width"] == 100
    assert res.structured["height"] == 50
    # TRAP 3: pending image staged
    assert getattr(orch, "_pending_image_b64", None) == fake_b64


def test_handle_screenshot_capture_orchestrator_error_path() -> None:
    """On capture failure, _handle_screenshot_capture returns ok=False and clears receipt."""
    from lucca.core.orchestrator import Orchestrator

    orch = object.__new__(Orchestrator)
    orch.sandbox = MagicMock()
    orch._record_tool_receipt = MagicMock()
    orch._pending_image_b64 = None

    with patch(
        "lucca.sandbox.screenshot_tool.capture_screenshot",
        side_effect=RuntimeError("display not available"),
    ):
        res = orch._handle_screenshot_capture("call-002", {})

    assert res.ok is False
    assert "display not available" in (res.stderr or "")
    # _pending_image_b64 must NOT be set on failure (TRAP 3)
    assert getattr(orch, "_pending_image_b64", None) is None


# ---------------------------------------------------------------------------
# 8. User-attached screen image flow through prompt builder and llm_client
# ---------------------------------------------------------------------------
def test_build_messages_with_attached_image() -> None:
    from lucca.brain.prompt_builder import build_messages

    fake_b64 = _fake_b64_jpeg()
    msgs = build_messages(current_text="Look at this screen", current_image_b64=fake_b64)
    user_msgs = [m for m in msgs if m.role == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0].image_b64 == fake_b64


def test_llm_client_stream_turn_with_attached_image() -> None:
    from lucca.brain.llm_client import LLMClient

    client = LLMClient(base_url="http://localhost:9999")
    fake_b64 = _fake_b64_jpeg()

    captured_payload: dict[str, Any] = {}

    from contextlib import contextmanager

    @contextmanager
    def _mock_stream(method: str, url: str, **kwargs: Any) -> Any:
        nonlocal captured_payload
        captured_payload = kwargs.get("json", {})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"content": "I see it"}}]}',
            "data: [DONE]",
        ]
        mock_resp.close = MagicMock()
        yield mock_resp

    with patch.object(client.http_client, "stream", side_effect=_mock_stream):
        events = list(
            client.stream_turn(current_text="Do you see yourself?", current_image_b64=fake_b64)
        )

    assert len(events) > 0
    msgs = captured_payload.get("messages", [])
    user_msgs = [m for m in msgs if m.get("role") == "user"]
    assert len(user_msgs) >= 1
    last_user = user_msgs[-1]
    assert isinstance(last_user["content"], list)
    image_blocks = [c for c in last_user["content"] if c.get("type") == "image_url"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"] == f"data:image/jpeg;base64,{fake_b64}"


def test_turn_pipeline_with_attached_image_suppresses_screenshot_tool() -> None:
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.trace import TurnTrace
    from lucca.core.turn_pipeline import TurnInput, TurnPipeline

    orch = object.__new__(Orchestrator)
    orch.sandbox = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.play_ring = MagicMock()
    orch.db = None
    orch.prev_decision_record = None
    orch.active_detected_words = []
    orch.cascade = MagicMock()
    orch.cascade.classify_intent.return_value = (False, [], None)
    orch.rule_engine = MagicMock()
    orch.rule_engine.evaluate.return_value = []
    orch.router = MagicMock()
    orch.router.classify_intent.return_value = ("chit_chat", 0.9, {})
    orch.router.route.return_value = None
    orch.router.last_decision_record = None
    orch.history = []
    orch.executed_tools = []
    orch._search_memories = MagicMock(return_value=[])
    orch._pending_image_b64 = "staged-image-data"
    orch._stream_llm_speech = MagicMock()
    orch.session_id = "test-session"

    pipeline = TurnPipeline(orch)
    fake_trace = TurnTrace(
        trace_id="test-trace",
        session_id="test-session",
        origin="text",
        mode="vision",
    )
    inp = TurnInput(
        user_text="What is on my screen?",
        trace=fake_trace,
        origin="text",
        image_b64="direct-image-data",
    )

    fake_tools = [
        MagicMock(name="screenshot_capture"),
        MagicMock(name="search_web"),
    ]
    fake_tools[0].name = "screenshot_capture"
    fake_tools[1].name = "search_web"

    with patch.object(pipeline, "detect_follow_up_and_gate_tools", return_value=fake_tools):
        pipeline.run(inp)

    # 1. _pending_image_b64 on orch was cleared
    assert getattr(orch, "_pending_image_b64", None) is None
    # 2. _stream_llm_speech was called with current_image_b64="direct-image-data"
    assert orch._stream_llm_speech.called
    kwargs = orch._stream_llm_speech.call_args.kwargs
    assert kwargs.get("current_image_b64") == "direct-image-data"
    # 3. screenshot_capture tool was suppressed from tools
    passed_tools = kwargs.get("tools", [])
    assert len(passed_tools) == 1
    assert passed_tools[0].name == "search_web"


def test_stream_llm_speech_strips_screenshot_tool_when_image_present() -> None:
    from lucca.core.capabilities import get_default_native_tools, tool_schema_to_definition
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.trace import TurnTrace

    orch = object.__new__(Orchestrator)
    orch._maybe_speak_pending_updates = MagicMock()
    orch._publish_bus = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.affect_tracker = MagicMock()
    orch.affect_tracker.get_prompt_suffix_tag.return_value = ""
    orch.bdi_validator = MagicMock()
    orch.history = []
    orch.execute_tools = True
    orch.rule_engine = MagicMock()
    orch.rule_engine.rules = {}
    orch._cancel_token = MagicMock()
    orch._cancel_token.is_set.return_value = False
    orch.speech_output = MagicMock()
    orch.play_ring = MagicMock()
    orch._finalize_turn = MagicMock()

    captured_tools: list[Any] = []

    def _mock_stream_turn(**kwargs: Any) -> Any:
        nonlocal captured_tools
        captured_tools = kwargs.get("tools", [])
        return iter([])

    orch.llm = MagicMock()
    orch.llm.stream_turn = _mock_stream_turn

    fake_trace = TurnTrace(trace_id="t1", session_id="s1")

    # Pass all 24 tools
    all_tools = [tool_schema_to_definition(t) for t in get_default_native_tools().values()]
    assert any(
        getattr(getattr(t, "function", None), "name", None) == "screenshot_capture"
        for t in all_tools
    )

    orch._stream_llm_speech(
        trace=fake_trace,
        user_msg="Look at this",
        decision_id=None,
        current_image_b64="some-image-b64",
        tools=all_tools,
    )

    assert not any(
        getattr(getattr(t, "function", None), "name", None) == "screenshot_capture"
        for t in captured_tools
    )


def test_morning_turn_zero_vision_query_no_greeting_hijack() -> None:
    """Morning turn zero vision query must NOT be hijacked by time-greeting-v1 rule."""
    from lucca.reasoning.lifecycle import RuleLifecycleManager
    from lucca.core.schemas import RuleState
    from lucca.core.trace import TurnTrace

    rlm = RuleLifecycleManager(skills_dir="config/skills")
    state = RuleState(
        user_text="Can you see yourself in this image?",
        intent="unknown",
        hour_local=7,
        session_turns=0,
    )
    outcomes = rlm.evaluate(state, mode="active")
    fired_ids = [o.rule_id for o in outcomes if o.fired]
    assert "time-greeting-v1" not in fired_ids

    # Confirmation bypass test with current_turn_image_b64
    from lucca.core.orchestrator import Orchestrator

    orch = object.__new__(Orchestrator)
    orch.sandbox = MagicMock()
    orch.sandbox.check_confirmation_needed.return_value = True
    orch.execute_tools = True
    orch.current_turn_image_b64 = "test-image-bytes"
    orch._pending_image_b64 = None
    orch.current_turn_tool_spoken = []
    orch.current_turn_tool_ok = True
    orch.executed_tools = []
    orch.current_turn_tool_calls = []
    orch.rule_engine = MagicMock()
    orch.rule_engine.rules = {}
    orch._record_tool_receipt = MagicMock()
    fake_trace = TurnTrace(trace_id="t-bypass", session_id="s1")
    with patch.object(orch, "_request_confirmation", return_value=False) as mock_req:
        res = orch._handle_tool_call(fake_trace, "screenshot_capture", {}, speak=False)
        mock_req.assert_not_called()
        assert res.ok is True
        assert res.structured is not None and res.structured.get("width") == 1280
        assert orch._pending_image_b64 == "test-image-bytes"


def test_turn_pipeline_run_with_image_input() -> None:
    """Verifies TurnPipeline.run executes end-to-end with an image without import or runtime errors."""
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.schemas import RouteAction, RouteDecision, RuleState
    from lucca.core.trace import TurnTrace
    from lucca.core.turn_pipeline import TurnInput, TurnPipeline

    orch = object.__new__(Orchestrator)
    orch.config = MagicMock()
    orch.db = None
    orch.session_id = "test-session"
    orch.prev_decision_record = None
    orch.prev_turn_ts = None
    orch.history = []
    orch.sandbox = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.play_ring = MagicMock()
    orch._pending_image_b64 = "initial-pending-b64"
    orch.rule_engine = MagicMock()
    orch.rule_engine.rules = {}
    orch.rule_engine.evaluate.return_value = []
    orch._build_rule_state = MagicMock(return_value=RuleState(
        transcript="Can you see yourself in the image?",
        transcript_lower="can you see yourself in the image?",
        intent="unknown",
        hour_local=12,
        session_turns=0,
    ))
    orch.router = MagicMock()
    orch.router.route.return_value = RouteDecision(
        action=RouteAction.LLM,
        prediction_set=[RouteAction.LLM],
        elapsed_us=100,
        intent="unknown",
        confidence=0.5,
        entities={},
    )
    orch.cascade = MagicMock()
    orch.cascade.classify_intent.return_value = (False, [], None)
    orch.router.last_decision_record = None
    orch.execute_tools = True
    orch._stream_llm_speech = MagicMock()
    orch._search_memories = MagicMock(return_value=[])
    orch.last_turn_timestamp = None
    orch._neutralize_context_attractors = MagicMock(return_value=[])

    pipeline = TurnPipeline(orch)
    trace = TurnTrace(trace_id="t-img-pipe", session_id="test-session")
    inp = TurnInput(
        trace=trace,
        origin="text",
        user_text="Can you see yourself in the image?",
        image_b64="turn-img-b64",
    )

    pipeline.run(inp)

    orch._stream_llm_speech.assert_called_once()
    call_kwargs = orch._stream_llm_speech.call_args.kwargs
    assert call_kwargs["current_image_b64"] == "turn-img-b64"
    tools_passed = call_kwargs["tools"]
    assert tools_passed is not None
    assert not any(
        getattr(getattr(t, "function", None), "name", None) == "screenshot_capture"
        for t in tools_passed
    )
    assert orch.current_turn_image_b64 == "turn-img-b64"


def test_multiturn_sticky_image_continuity(tmp_path: Any) -> None:
    """WO-37 Phase 1: verifies sticky session image reload on follow-up vision turns."""
    from pathlib import Path
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.schemas import RouteAction, RouteDecision, RuleState
    from lucca.core.trace import TurnTrace
    from lucca.core.turn_pipeline import TurnInput, TurnPipeline
    from lucca.core.visual_session import VisualSessionStore

    store_dir = Path(tmp_path) / "sessions" / "images"
    vstore = VisualSessionStore(store_dir)
    raw_b64 = _fake_b64_jpeg()

    orch = object.__new__(Orchestrator)
    orch.config = MagicMock()
    orch.db = None
    orch.session_id = "test-multiturn-session"
    orch.prev_decision_record = None
    orch.prev_turn_ts = None
    orch.history = []
    orch.sandbox = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.play_ring = MagicMock()
    orch._pending_image_b64 = None
    orch.visual_session = vstore
    orch.rule_engine = MagicMock()
    orch.rule_engine.rules = {}
    orch.rule_engine.evaluate.return_value = []
    orch._build_rule_state = MagicMock(return_value=RuleState(
        transcript="Can you see yourself in the image?",
        transcript_lower="can you see yourself in the image?",
        intent="unknown",
        hour_local=12,
        session_turns=0,
    ))
    orch.router = MagicMock()
    orch.router.route.return_value = RouteDecision(
        action=RouteAction.LLM,
        prediction_set=[RouteAction.LLM],
        elapsed_us=100,
        intent="unknown",
        confidence=0.5,
        entities={},
    )
    orch.cascade = MagicMock()
    orch.cascade.classify_intent.return_value = (False, [], None)
    orch.router.last_decision_record = None
    orch.execute_tools = True
    orch._stream_llm_speech = MagicMock()
    orch._search_memories = MagicMock(return_value=[])
    orch.last_turn_timestamp = None
    orch._neutralize_context_attractors = MagicMock(return_value=[])
    orch._finalize_turn = MagicMock()

    pipeline = TurnPipeline(orch)

    # Turn 1: Attach image & ask vision question
    vstore.store_image(raw_b64, description="user_upload")
    trace1 = TurnTrace(trace_id="t1", session_id="test-multiturn-session")
    inp1 = TurnInput(
        trace=trace1,
        origin="text",
        user_text="Can you see yourself in the image?",
        image_b64=raw_b64,
    )
    pipeline.run(inp1)

    orch._stream_llm_speech.assert_called_once()
    assert orch._stream_llm_speech.call_args.kwargs["current_image_b64"] == raw_b64
    assert orch.current_turn_image_b64 == raw_b64

    # Turn 2: Follow-up question with NO new image, but visual query ("What does it look like?")
    orch._stream_llm_speech.reset_mock()
    orch._build_rule_state.return_value = RuleState(
        transcript="What does it look like?",
        transcript_lower="what does it look like?",
        intent="unknown",
        hour_local=12,
        session_turns=1,
    )
    trace2 = TurnTrace(trace_id="t2", session_id="test-multiturn-session")
    inp2 = TurnInput(
        trace=trace2,
        origin="text",
        user_text="What does it look like?",
        image_b64=None,
    )
    pipeline.run(inp2)

    orch._stream_llm_speech.assert_called_once()
    # Image must be reloaded from visual session store!
    assert orch._stream_llm_speech.call_args.kwargs["current_image_b64"] == raw_b64
    assert orch.current_turn_image_b64 == raw_b64

    # Turn 3: Follow-up question with NO new image and NON-vision query ("Tell me a joke")
    orch._stream_llm_speech.reset_mock()
    orch._build_rule_state.return_value = RuleState(
        transcript="Tell me a joke",
        transcript_lower="tell me a joke",
        intent="unknown",
        hour_local=12,
        session_turns=2,
    )
    trace3 = TurnTrace(trace_id="t3", session_id="test-multiturn-session")
    inp3 = TurnInput(
        trace=trace3,
        origin="text",
        user_text="Tell me a joke",
        image_b64=None,
    )
    pipeline.run(inp3)

    orch._stream_llm_speech.assert_called_once()
    assert orch._stream_llm_speech.call_args.kwargs["current_image_b64"] is None
    assert orch.current_turn_image_b64 is None


def test_vision_guard_no_image(tmp_path: Any) -> None:
    """WO-37 Phase 1: verifies Epistemic Vision Guard halts turn with refusal if store empty."""
    from pathlib import Path
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.trace import TurnTrace
    from lucca.core.turn_pipeline import TurnInput, TurnPipeline
    from lucca.core.visual_session import VisualSessionStore

    store_dir = Path(tmp_path) / "sessions" / "images"
    vstore = VisualSessionStore(store_dir)

    orch = object.__new__(Orchestrator)
    orch.config = MagicMock()
    orch.db = None
    orch.session_id = "test-guard-session"
    orch.prev_decision_record = None
    orch.prev_turn_ts = None
    orch.history = []
    orch.sandbox = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.play_ring = MagicMock()
    orch._pending_image_b64 = None
    orch.visual_session = vstore
    orch._speak_text = MagicMock()
    orch._publish_caption = MagicMock()
    orch._finalize_turn = MagicMock()
    orch._stream_llm_speech = MagicMock()

    pipeline = TurnPipeline(orch)

    # User asks vision query with no image in store
    trace = TurnTrace(trace_id="t-guard", session_id="test-guard-session")
    inp = TurnInput(
        trace=trace,
        origin="text",
        user_text="What do you see in the screenshot?",
        image_b64=None,
    )
    pipeline.run(inp)

    # LLM must NEVER be called
    orch._stream_llm_speech.assert_not_called()
    orch._speak_text.assert_called_once()
    spoken_text = orch._speak_text.call_args.args[1]
    assert "don't have an active image in our session" in spoken_text
    assert orch.history[-1]["content"] == spoken_text
    orch._finalize_turn.assert_called_once()

    # Now verify UI_CLEAR_IMAGE behavior
    raw_b64 = _fake_b64_jpeg()
    vstore.store_image(raw_b64)
    assert vstore.count == 1
    vstore.clear()
    assert vstore.count == 0

    orch._speak_text.reset_mock()
    orch._finalize_turn.reset_mock()
    trace2 = TurnTrace(trace_id="t-guard-2", session_id="test-guard-session")
    inp2 = TurnInput(
        trace=trace2,
        origin="text",
        user_text="Describe what you see in this picture",
        image_b64=None,
    )
    pipeline.run(inp2)

    orch._stream_llm_speech.assert_not_called()
    orch._speak_text.assert_called_once()
    assert "don't have an active image" in orch._speak_text.call_args.args[1]
    orch._finalize_turn.assert_called_once()





