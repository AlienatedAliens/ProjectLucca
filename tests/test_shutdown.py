"""
Project Lucca — Shutdown Contract Integration Gate (F-ARCH-007)
Spec 01 §7, ADR-008
"""

import time
from multiprocessing import shared_memory
from unittest.mock import MagicMock

import pytest
import zmq

from lucca.core.ipc_schemas import decode_envelope
from lucca.core.orchestrator import Orchestrator
from lucca.main import Supervisor


@pytest.mark.tier2
def test_shutdown_order_spec01() -> None:
    """
    F-ARCH-007 (Spec 01 §7): Ordered shutdown sequence verification:
    1. Broadcast `ui.state offline`
    2. Broadcast `play.abort`
    3. Broadcast `sys.shutdown`
    4. Grace period (>= 0.5s) for child processes to exit cleanly
    5. Join child processes (timeout 3.0s) before forced terminate/kill
    6. Orchestrator stop & shared memory rings unlinked
    7. Terminate llama-server
    """
    call_log: list[str] = []

    supervisor = Supervisor()

    # Track child process operations
    child_mock = MagicMock()
    child_mock.is_alive.side_effect = [True, False]  # Alive when checking, exits on join

    def fake_join(timeout: float | None = None) -> None:
        call_log.append(f"child_join_{timeout}")

    child_mock.join = fake_join
    supervisor.children = {"test_child": child_mock}

    # Track llama-server termination
    llama_mock = MagicMock()
    llama_mock.poll.return_value = None  # Running

    def fake_llama_term() -> None:
        call_log.append("llama_terminate")

    llama_mock.terminate = fake_llama_term
    supervisor.llama_proc = llama_mock

    # Real orchestrator with sockets & rings
    orch = Orchestrator(execute_tools=False)
    orch.start()
    supervisor.orchestrator = orch
    supervisor.running = True

    # Connect bus listener
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(f"tcp://127.0.0.1:{supervisor.config.ipc.bus_port}")
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    time.sleep(0.1)

    # Wrap publish_offline to log its invocation
    real_publish_offline = orch.publish_offline

    def logged_publish_offline() -> None:
        call_log.append("publish_offline")
        real_publish_offline()

    orch.publish_offline = logged_publish_offline  # type: ignore[method-assign]

    # Wrap orch.stop to log its invocation
    real_orch_stop = orch.stop

    def logged_orch_stop() -> None:
        call_log.append("orchestrator_stop")
        real_orch_stop()

    orch.stop = logged_orch_stop  # type: ignore[method-assign]

    # Execute shutdown
    t_start = time.monotonic()
    supervisor.shutdown()
    t_elapsed = time.monotonic() - t_start

    # Verify grace period was at least 0.5s
    assert t_elapsed >= 0.5

    # Drain bus messages
    bus_messages: list[str] = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < 1.0:
        try:
            raw = sub.recv(flags=zmq.NOBLOCK)
            env = decode_envelope(raw)
            bus_messages.append(env.type)
        except zmq.ZMQError:
            time.sleep(0.05)

    sub.close(linger=0)
    ctx.destroy(linger=0)

    # Verify bus message sequence: ui.state offline -> play.abort -> sys.shutdown
    assert "ui.state" in bus_messages
    assert "play.abort" in bus_messages
    assert "sys.shutdown" in bus_messages
    ui_state_idx = bus_messages.index("ui.state")
    play_abort_idx = bus_messages.index("play.abort")
    sys_shutdown_idx = bus_messages.index("sys.shutdown")
    assert ui_state_idx < play_abort_idx < sys_shutdown_idx

    # Verify execution order:
    # publish_offline -> child join -> orchestrator_stop -> llama_terminate
    assert call_log.index("publish_offline") < call_log.index("child_join_3.0")
    assert call_log.index("child_join_3.0") < call_log.index("orchestrator_stop")
    assert call_log.index("orchestrator_stop") < call_log.index("llama_terminate")

    # Verify rings unlinked
    with pytest.raises(FileNotFoundError):
        shared_memory.SharedMemory("lucca_cap_ring")
    with pytest.raises(FileNotFoundError):
        shared_memory.SharedMemory("lucca_play_ring")
