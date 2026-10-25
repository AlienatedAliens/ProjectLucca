"""
Project Lucca — VisualSessionStore Acceptance Tests (WO-37 Phase 0)
D-BRAIN-05, D-SEC-04, D-AUD-01
"""

from __future__ import annotations

import base64
from pathlib import Path

from lucca.core.orchestrator import Orchestrator
from lucca.core.visual_session import VisualArtifact, VisualSessionStore
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


def test_visual_session_store_basic_and_dedup(tmp_path: Path) -> None:
    store = VisualSessionStore(tmp_path / "images")
    assert store.count == 0
    assert store.get_active() is None

    data = b"dummy_jpeg_bytes_for_testing"
    b64_data = base64.b64encode(data).decode("ascii")

    art1 = store.store_image(b64_data, description="test_1")
    assert isinstance(art1, VisualArtifact)
    assert art1.image_id == "img_01"
    assert art1.path.exists()
    assert art1.path.read_bytes() == data
    assert store.count == 1
    assert store.get_active() == art1
    assert store.get_by_id("img_01") == art1

    # Round trip load_b64
    loaded = store.load_b64(art1)
    assert loaded == b64_data

    # Dedup check
    art2 = store.store_image(b64_data, description="test_dup")
    assert art2.image_id == art1.image_id
    assert art2.sha256 == art1.sha256
    assert store.count == 1


def test_visual_session_store_eviction(tmp_path: Path) -> None:
    store = VisualSessionStore(tmp_path / "images")
    artifacts: list[VisualArtifact] = []

    for i in range(9):
        data = f"dummy_frame_{i}".encode()
        b64_data = base64.b64encode(data).decode("ascii")
        art = store.store_image(b64_data, description=f"frame_{i}")
        artifacts.append(art)

    assert store.count == 8
    # Oldest (img_01) should be evicted
    assert store.get_by_id("img_01") is None
    assert store.get_active() == artifacts[-1]


def test_visual_session_load_b64_missing_file_returns_none(tmp_path: Path) -> None:
    store = VisualSessionStore(tmp_path / "images")
    data = b"temp_image"
    b64_data = base64.b64encode(data).decode("ascii")
    art = store.store_image(b64_data)
    art.path.unlink()
    # TRAP 3: load_b64 must return None on OSError, never raise
    assert store.load_b64(art) is None


def test_orchestrator_visual_session_wiring(tmp_path: Path) -> None:
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, llm=FakeLLM(), execute_tools=False)
    try:
        assert hasattr(orch, "visual_session")
        assert isinstance(orch.visual_session, VisualSessionStore)
        assert orch.visual_session.count == 0

        # Simulate ui.attach_image
        data = b"ui_attached_jpeg"
        b64_data = base64.b64encode(data).decode("ascii")

        orch._pending_image_b64 = b64_data
        orch.visual_session.store_image(b64_data, description="user_upload")

        assert orch.visual_session.count == 1
        active = orch.visual_session.get_active()
        assert active is not None
        assert active.path.exists()
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
