"""
Unit tests for Senses subsystem (NPUProcess stop, socket cleanup, and bus shutdown).
Spec 01 §4, Spec 07, ADR-008 (F-SENS-012)
"""

import threading
import time
from unittest.mock import MagicMock

import pytest
import zmq

from lucca.core.config import get_config
from lucca.core.ipc_schemas import Envelope, encode_envelope
from lucca.senses.asr import ASRWorker
from lucca.senses.embed import EmbedWorker
from lucca.senses.npu_proc import NPUProcess
from lucca.senses.ring_buffer import SharedAudioRing
from lucca.senses.tts import TTSWorker


@pytest.fixture
def dummy_rings():
    cap = SharedAudioRing("test_npu_cap_s12", rate=16000, capacity_seconds=1, create=True)
    play = SharedAudioRing("test_npu_play_s12", rate=24000, capacity_seconds=1, create=True)
    yield cap, play
    cap.close()
    cap.unlink()
    play.close()
    play.unlink()


def test_npu_process_stop_terminates_loop(
    dummy_rings: tuple[SharedAudioRing, SharedAudioRing],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F-SENS-012: Ensure NPUProcess.stop() ends the polling loop cleanly."""
    cap_ring, play_ring = dummy_rings

    # Assign ephemeral ports to prevent collision with running services
    ctx = zmq.Context()
    ctl_router = ctx.socket(zmq.ROUTER)
    ctl_port = ctl_router.bind_to_random_port("tcp://127.0.0.1")

    bus_pub = ctx.socket(zmq.PUB)
    bus_port = bus_pub.bind_to_random_port("tcp://127.0.0.1")

    cfg = get_config()
    monkeypatch.setattr(cfg.ipc, "ctl_port", ctl_port)
    monkeypatch.setattr(cfg.ipc, "bus_port", bus_port)

    mock_asr = MagicMock(spec=ASRWorker)
    mock_tts = MagicMock(spec=TTSWorker)
    mock_embed = MagicMock(spec=EmbedWorker)

    proc = NPUProcess(
        cap_ring=cap_ring,
        play_ring=play_ring,
        asr=mock_asr,
        tts=mock_tts,
        embed=mock_embed,
    )

    t = threading.Thread(target=proc.start, daemon=True)
    t.start()

    time.sleep(0.05)
    assert proc.running is True

    # Calling stop() terminates the loop and cleans up sockets
    proc.stop()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert proc.running is False

    ctl_router.close(linger=0)
    bus_pub.close(linger=0)
    ctx.destroy(linger=0)


def test_npu_process_bus_sys_shutdown(
    dummy_rings: tuple[SharedAudioRing, SharedAudioRing],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F-SENS-012 / F-CORE-029: Ensure NPUProcess terminates its loop on bus sys.shutdown envelope."""
    cap_ring, play_ring = dummy_rings

    ctx = zmq.Context()
    ctl_router = ctx.socket(zmq.ROUTER)
    ctl_port = ctl_router.bind_to_random_port("tcp://127.0.0.1")

    bus_pub = ctx.socket(zmq.PUB)
    bus_port = bus_pub.bind_to_random_port("tcp://127.0.0.1")

    cfg = get_config()
    monkeypatch.setattr(cfg.ipc, "ctl_port", ctl_port)
    monkeypatch.setattr(cfg.ipc, "bus_port", bus_port)

    mock_asr = MagicMock(spec=ASRWorker)
    mock_tts = MagicMock(spec=TTSWorker)
    mock_embed = MagicMock(spec=EmbedWorker)

    proc = NPUProcess(
        cap_ring=cap_ring,
        play_ring=play_ring,
        asr=mock_asr,
        tts=mock_tts,
        embed=mock_embed,
    )

    t = threading.Thread(target=proc.start, daemon=True)
    t.start()

    time.sleep(0.1)
    assert proc.running is True

    # Broadcast sys.shutdown on bus
    env = Envelope(
        type="sys.shutdown", trace_id="", ts_ns=time.monotonic_ns(), src="core", payload={}
    )
    bus_pub.send(encode_envelope(env))

    t.join(timeout=2.0)
    assert not t.is_alive()
    assert proc.running is False

    proc.stop()
    ctl_router.close(linger=0)
    bus_pub.close(linger=0)
    ctx.destroy(linger=0)
