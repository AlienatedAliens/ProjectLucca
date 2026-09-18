"""
Unit tests for Supervisor process supervision, backoff restarts, and heartbeat tracking.
Spec 01 §3, §7, ADR-008 (F-CORE-005)
"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from lucca.core.ipc_schemas import Envelope
from lucca.core.orchestrator import Orchestrator
from lucca.main import Supervisor


def _dummy_exit_child() -> None:
    """Helper process target that immediately exits with code 1."""
    import sys

    sys.exit(1)


def test_dead_child_is_restarted_with_backoff(capsys: pytest.CaptureFixture[str]) -> None:
    """F-CORE-005: Supervisor restarts crashing child up to 5x with backoff, then marks DEGRADED."""
    supervisor = Supervisor()
    supervisor.backoff_base = 0.001
    supervisor.max_restart_backoff = 0.01
    supervisor._targets["test_child"] = _dummy_exit_child

    mock_orch = MagicMock(spec=Orchestrator)
    supervisor.orchestrator = mock_orch

    def fake_spawn(name: str) -> MagicMock:
        mock_p = MagicMock()
        mock_p.is_alive.return_value = False
        mock_p.exitcode = 1
        return mock_p

    supervisor._spawn_child = fake_spawn  # type: ignore[assignment]
    supervisor.children["test_child"] = fake_spawn("test_child")
    supervisor.running = True

    # Run supervisor loop in thread until degraded (5 restarts)
    def stop_when_degraded() -> None:
        t0 = time.monotonic()
        while time.monotonic() - t0 < 2.0:
            if "test_child" not in supervisor.children:
                supervisor.running = False
                break
            time.sleep(0.01)
        supervisor.running = False

    watcher = threading.Thread(target=stop_when_degraded, daemon=True)
    watcher.start()

    supervisor.run_forever()
    watcher.join(timeout=1.0)

    # Assert test_child was popped after 5 attempts
    assert "test_child" not in supervisor.children
    assert len(supervisor._restart_attempts.get("test_child", [])) >= 5

    # Assert DEGRADED was logged to stderr and notified to orchestrator
    _, err = capsys.readouterr()
    assert "DEGRADED: test_child failed 5x in 10 min" in err
    mock_orch._set_state.assert_called_with("degraded", detail="test_child_crashed_5x")


def test_heartbeat_tracks_pong_and_dead_peers(monkeypatch: pytest.MonkeyPatch) -> None:
    """F-CORE-005: Orchestrator tracks peer pongs and detects dead peers after 3 misses."""
    mock_llm = MagicMock()
    orch = Orchestrator(llm=mock_llm, execute_tools=False)

    fake_now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: fake_now)

    orch.register_peer("audio")
    orch.register_peer("npu")

    # Both peers alive
    assert orch.dead_peers(misses=3) == set()

    # Advance time past 3 misses (2.0s * 3 = 6.0s)
    fake_now += 6.1
    assert orch.dead_peers(misses=3) == {"audio", "npu"}

    # Simulate sys.pong from npu
    env_pong = Envelope(
        type="sys.pong",
        trace_id="",
        ts_ns=int(fake_now * 1e9),
        src="npu",
        payload={"rss_mb": 150.0, "queue_depth": 0},
    )
    orch._handle_ingest_message(env_pong)

    # npu is now alive, audio remains dead
    assert orch.dead_peers(misses=3) == {"audio"}
