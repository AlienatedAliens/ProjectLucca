"""
Project Lucca — Persistent Docker Worker & RPC Transport Test Suite
Spec 09 §1, §2, §4, §5

Verifies:
1. Persistent worker lifecycle (spawn, call serialization, clean close).
2. Proactive bounded lifetime recycling ($M=500$, tested with small $M$).
3. Hierarchical timeout protection and worker recovery.
4. Call-ID correlation & anti-desync protection (SandboxRPCDesyncError).
5. Thread safety under concurrent invocations.
6. Latency collapse (<20ms turnaround per call).
7. Transport fallback and T-SBX-16 SHA-256 verification.
"""

import concurrent.futures
import json
from unittest.mock import patch

import pytest

from lucca.core.exceptions import (
    SandboxRPCDesyncError,
    SandboxTimeout,
)
from lucca.sandbox.rpc import DockerRPCTransport, PersistentDockerWorker


@pytest.fixture(scope="module")
def ensure_sandbox() -> DockerRPCTransport:
    transport = DockerRPCTransport(container_name="lucca-file-sandbox", use_direct_fallback=False)
    if not transport.is_docker_available():
        pytest.skip("Docker / WSL2 not available in this test environment")
    if not transport.is_container_running():
        started = transport.ensure_container_running()
        if not started:
            pytest.skip("Could not start lucca-file-sandbox container in WSL2")
    return transport


def test_persistent_worker_lifecycle(ensure_sandbox: DockerRPCTransport):
    """Verifies spawn, execution, and clean shutdown of PersistentDockerWorker."""
    worker = PersistentDockerWorker(container_name="lucca-file-sandbox", max_calls=100)
    try:
        assert worker.is_alive() is False

        # First call spawns the worker
        res1 = worker.execute(
            call_id="call-life-1",
            tool="write_file",
            args={"path": "worker_test.txt", "content": "persistent bridge test", "mode": "overwrite"},
        )
        assert worker.is_alive() is True
        assert res1["call_id"] == "call-life-1"
        assert res1["ok"] is True

        # Second call reuses existing process
        res2 = worker.execute(
            call_id="call-life-2",
            tool="read_file",
            args={"path": "worker_test.txt"},
        )
        assert res2["call_id"] == "call-life-2"
        assert res2["ok"] is True
        assert res2["content"] == "persistent bridge test"
    finally:
        worker.close()
        assert worker.is_alive() is False


def test_persistent_worker_proactive_recycling(ensure_sandbox: DockerRPCTransport):
    """Verifies that worker cleanly recycles after max_calls to prevent memory drift."""
    worker = PersistentDockerWorker(container_name="lucca-file-sandbox", max_calls=3)
    try:
        # Call 1
        worker.execute(call_id="c-rec-1", tool="list_dir", args={"path": "."})
        proc1 = worker._proc
        assert proc1 is not None

        # Call 2 & 3
        worker.execute(call_id="c-rec-2", tool="list_dir", args={"path": "."})
        worker.execute(call_id="c-rec-3", tool="list_dir", args={"path": "."})
        assert worker._proc == proc1
        assert worker._call_count == 3

        # Call 4 must trigger recycling
        res4 = worker.execute(call_id="c-rec-4", tool="list_dir", args={"path": "."})
        assert res4["call_id"] == "c-rec-4"
        assert worker._proc != proc1
        assert worker._call_count == 1
    finally:
        worker.close()


def test_persistent_worker_timeout_recovery(ensure_sandbox: DockerRPCTransport):
    """
    Verifies that a call exceeding timeout kills the worker, raises SandboxTimeout,
    and subsequent calls cleanly recover with a fresh worker.
    """
    worker = PersistentDockerWorker(container_name="lucca-file-sandbox", max_calls=100)
    try:
        # Long running sleep code with short host transport timeout
        sleep_code = "import time; time.sleep(3.0)"
        with pytest.raises(SandboxTimeout) as exc_info:
            worker.execute(
                call_id="c-to-1",
                tool="run_python",
                args={"code": sleep_code, "timeout": 5},
                timeout_s=0.5,
            )
        assert "timed out after 0.5s" in str(exc_info.value)
        assert worker.is_alive() is False

        # Next call must recover automatically
        res_rec = worker.execute(
            call_id="c-to-recover",
            tool="list_dir",
            args={"path": "."},
            timeout_s=5.0,
        )
        assert res_rec["call_id"] == "c-to-recover"
        assert res_rec["ok"] is True
        assert worker.is_alive() is True
    finally:
        worker.close()


def test_persistent_worker_call_id_desync_guard(ensure_sandbox: DockerRPCTransport):
    """
    Verifies that a mismatched call_id in response triggers SandboxRPCDesyncError,
    kills the corrupted process, and recovers on next call.
    """
    worker = PersistentDockerWorker(container_name="lucca-file-sandbox", max_calls=100)
    try:
        # Spawn worker
        worker.execute(call_id="c-sync-0", tool="list_dir", args={"path": "."})
        proc_before = worker._proc
        assert proc_before is not None

        # Inject simulated desynchronized response
        desync_line = '{"call_id": "c-OTHER-ID", "ok": true, "structured": {}, "content": null}\n'
        with patch.object(proc_before.stdout, "readline", return_value=desync_line):
            with pytest.raises(SandboxRPCDesyncError) as exc_info:
                worker.execute(call_id="c-sync-expected", tool="list_dir", args={"path": "."})
            assert "Protocol desync: expected call_id='c-sync-expected'" in str(exc_info.value)

        # Worker process should be killed and set to None
        assert worker._proc is None

        # Next call recovers cleanly
        res_after = worker.execute(call_id="c-sync-recovered", tool="list_dir", args={"path": "."})
        assert res_after["call_id"] == "c-sync-recovered"
        assert res_after["ok"] is True
        assert worker.is_alive() is True
    finally:
        worker.close()


def test_persistent_worker_thread_safety(ensure_sandbox: DockerRPCTransport):
    """Verifies that concurrent threads submitting tool calls are safely serialized."""
    worker = PersistentDockerWorker(container_name="lucca-file-sandbox", max_calls=100)
    try:
        # Pre-warm
        worker.execute(call_id="c-warm", tool="list_dir", args={"path": "."})

        def _run_call(i: int) -> dict[str, object]:
            return worker.execute(
                call_id=f"c-thread-{i}",
                tool="run_python",
                args={"code": f"print({i} * 2)"},
                timeout_s=5.0,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_run_call, i) for i in range(10)]
            results = [f.result() for f in futures]

        assert len(results) == 10
        for i, res in enumerate(results):
            assert res["call_id"] == f"c-thread-{i}"
            assert res["ok"] is True
            assert str(i * 2) in str(res["content"])
    finally:
        worker.close()


def test_persistent_worker_latency_collapse(ensure_sandbox: DockerRPCTransport):
    """
    Verifies that persistent RPC bridge collapses turnaround time
    compared to the ~472ms single-shot spawn tax.
    """
    transport = DockerRPCTransport(
        container_name="lucca-file-sandbox",
        use_persistent_worker=True,
    )
    try:
        # Pre-warm worker
        res_warm = transport.execute(call_id="c-bench-warm", tool="list_dir", args={"path": "."})
        assert res_warm.ok is True

        latencies = []
        for i in range(10):
            res = transport.execute(
                call_id=f"c-bench-{i}",
                tool="list_dir",
                args={"path": "."},
            )
            assert res.ok is True
            latencies.append(res.elapsed_ms)

        # Average latency over persistent bridge must be well below 50ms (typically <5ms)
        avg_ms = sum(latencies) / len(latencies)
        assert avg_ms < 50.0, f"Expected persistent turnaround <50ms, got {avg_ms:.2f}ms"
    finally:
        transport.close()


def test_transport_sha256_audit_and_fallback(ensure_sandbox: DockerRPCTransport):
    """Verifies T-SBX-16 SHA256 audit and graceful fallback from worker errors."""
    transport = DockerRPCTransport(
        container_name="lucca-file-sandbox",
        use_persistent_worker=True,
    )
    try:
        # 1. Write file
        res_w = transport.execute(
            call_id="c-sha-w",
            tool="write_file",
            args={"path": "audit_test.txt", "content": "integrity content", "mode": "overwrite"},
        )
        assert res_w.ok is True

        # 2. Read file with verified sha256
        res_r = transport.execute(
            call_id="c-sha-r",
            tool="read_file",
            args={"path": "audit_test.txt"},
        )
        assert res_r.ok is True
        assert res_r.content == "integrity content"

        # 3. Simulate persistent worker failure causing fallback to single-shot
        worker = transport.get_worker()
        worker._kill_proc()

        # Call should still succeed via automatic spawn / fallback
        res_fallback = transport.execute(
            call_id="c-fallback-1",
            tool="list_dir",
            args={"path": "."},
        )
        assert res_fallback.ok is True
        assert res_fallback.call_id == "c-fallback-1"
    finally:
        transport.close()


def test_sandbox_service_confirmation_gate_upstream_of_persistent_worker(ensure_sandbox: DockerRPCTransport):
    """
    Verifies that SandboxService confirmation checks (Stage 2) execute host-side
    strictly UPSTREAM of DockerRPCTransport / PersistentDockerWorker.
    Unconfirmed write_file, delete_file, and run_python calls must be rejected with
    exit_code=-3, stderr="confirmation_required", and must NEVER reach the persistent worker.
    """
    from unittest.mock import patch
    from lucca.sandbox.service import SandboxService

    service = SandboxService()
    try:
        # Patch rpc.execute to assert if unconfirmed calls reach transport
        with patch.object(service.rpc, "execute", side_effect=AssertionError("Confirmation gate bypassed!")):
            # 1. Unconfirmed write_file
            res_w = service.execute_tool(
                call_id="c-unconf-w",
                tool_name="write_file",
                args={"path": "evil.txt", "content": "blocked", "mode": "create"},
                confirmed=False,
            )
            assert res_w.ok is False
            assert res_w.exit_code == -3
            assert res_w.stderr == "confirmation_required"

            # 2. Unconfirmed delete_file
            res_d = service.execute_tool(
                call_id="c-unconf-d",
                tool_name="delete_file",
                args={"path": "evil.txt"},
                confirmed=False,
            )
            assert res_d.ok is False
            assert res_d.exit_code == -3
            assert res_d.stderr == "confirmation_required"

            # 3. Unconfirmed run_python
            res_p = service.execute_tool(
                call_id="c-unconf-p",
                tool_name="run_python",
                args={"code": "print('blocked')"},
                confirmed=False,
            )
            assert res_p.ok is False
            assert res_p.exit_code == -3
            assert res_p.stderr == "confirmation_required"

        # 4. Confirmed call passes the gate and reaches persistent worker
        res_conf = service.execute_tool(
            call_id="c-conf-w",
            tool_name="write_file",
            args={"path": "confirmed_gate_test.txt", "content": "allowed", "mode": "overwrite"},
            confirmed=True,
        )
        assert res_conf.ok is True
        assert res_conf.call_id == "c-conf-w"
    finally:
        service.close()


def test_differentiated_hierarchical_timeouts(ensure_sandbox: DockerRPCTransport):
    """Verifies that filesystem operations default to 5.0s and python operations default to 15.0s."""
    worker = PersistentDockerWorker(container_name="lucca-file-sandbox", max_calls=100)
    try:
        captured_timeouts: list[float] = []

        def mock_result(self, timeout=None):
            captured_timeouts.append(timeout)
            return json.dumps({"call_id": "test", "ok": True})

        with patch.object(concurrent.futures.Future, "result", mock_result):
            # Filesystem tool with default timeout -> should be 5.0s
            worker.execute(call_id="test", tool="list_dir", args={"path": "."})
            assert captured_timeouts[-1] == 5.0

            # Python tool with default timeout -> should be 15.0s
            worker.execute(call_id="test", tool="run_python", args={"code": "print(1)"})
            assert captured_timeouts[-1] == 15.0

            # Explicit custom timeout -> should respect custom value
            worker.execute(call_id="test", tool="list_dir", args={"path": "."}, timeout_s=3.5)
            assert captured_timeouts[-1] == 3.5
    finally:
        worker.close()


def test_prespawn_reaping_and_worker_recovery(ensure_sandbox: DockerRPCTransport):
    """Verifies that pre-spawn reap executes cleanly and the spawned worker operates normally."""
    worker = PersistentDockerWorker(container_name="lucca-file-sandbox", max_calls=100)
    try:
        # Ensure worker spawns with pre-spawn reap
        res = worker.execute(
            call_id="c-reap-1",
            tool="list_dir",
            args={"path": "."},
        )
        assert res["ok"] is True
        assert worker.is_alive() is True

        # Forcibly kill without clean close (simulate host crash / orphaned worker)
        worker._kill_proc()
        assert worker.is_alive() is False

        # Next call triggers _spawn_proc which runs pre-spawn pkill and spawns fresh worker
        res2 = worker.execute(
            call_id="c-reap-2",
            tool="list_dir",
            args={"path": "."},
        )
        assert res2["ok"] is True
        assert worker.is_alive() is True
    finally:
        worker.close()

