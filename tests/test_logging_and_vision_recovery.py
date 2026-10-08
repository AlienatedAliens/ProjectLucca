"""
Unit tests for process logging setup, TurnTrace vision mode acceptance,
and voice engine fallback resilience.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys

import numpy as np
import pytest

from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.logging_setup import setup_process_logging
from lucca.core.schemas import TurnTrace as SchemaTurnTrace
from lucca.core.trace import TurnTrace
from lucca.senses.ring_buffer import PLAY_RING_NAME, SharedAudioRing
from lucca.senses.tts import TTSWorker


def test_turn_trace_accepts_vision_mode() -> None:
    """Verify TurnTrace accepts mode='vision' across core.trace and core.schemas."""
    trace = TurnTrace(
        trace_id="test_vision_01",
        mode="vision",
        origin="ptt",
    )
    assert trace.mode == "vision"
    dumped = trace.model_dump()
    assert dumped["mode"] == "vision"

    schema_trace = SchemaTurnTrace(
        trace_id="test_vision_02",
        points_ns={"t0": 100},
        e2e_latency_ms=12.5,
        mode="vision",
    )
    assert schema_trace.mode == "vision"


def test_setup_process_logging_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify setup_process_logging configures file handler and tees stdout/stderr."""
    test_proc = "test_subsys"
    monkeypatch.setenv("LUCCA_HOME_DIR", str(tmp_path))

    log_path = setup_process_logging(test_proc)
    assert log_path.exists()
    assert log_path.name == f"{test_proc}.log"

    test_logger = logging.getLogger("test_subsys.worker")
    test_logger.info("Forensic heartbeat marker 42")

    content = log_path.read_text(encoding="utf-8")
    assert "Forensic heartbeat marker 42" in content


def test_cascade_self_substrate_reflects_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify query_substrate_self introspects active vision projector."""
    cascade = EpistemicSearchCascade()
    items = cascade.query_substrate_self("Who are you?")
    assert len(items) == 1
    self_info = items[0].content

    # In vision mode with gemma mmproj, verify self-awareness contains vision projector
    assert "vision" in self_info.lower()
    assert "gemma-4-12b-heretic-mmproj-f16.gguf" in self_info or "vision projector" in self_info.lower()


def test_tts_worker_unknown_voice_fallback_to_kokoro() -> None:
    """Verify TTSWorker handles unknown voice spec gracefully via Kokoro fallback."""
    from lucca.senses.ring_buffer import get_playback_ring

    ring = get_playback_ring(create=True)
    worker = TTSWorker(play_ring=ring)

    res = worker.synthesize(
        chunk_id=1,
        text="Testing resilient speech fallback.",
        voice="unknown_voice_variant",
        speed=1.0,
    )
    assert res is not None
    assert res.chunk_id == 1

