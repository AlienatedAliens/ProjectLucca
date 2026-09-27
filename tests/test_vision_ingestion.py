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
