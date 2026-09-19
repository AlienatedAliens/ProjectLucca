"""
Project Lucca — Async Task Protocol Tests
Spec 07 Proposal H (D-SAND-03)
Tests background task execution, status polling, thread safety, and SandboxService integration.
"""

import threading
import time
from pathlib import Path

from lucca.core.schemas import Risk
from lucca.sandbox.policy import classify_risk
from lucca.sandbox.service import SandboxService
from lucca.sandbox.tasks import AsyncTaskInfo, AsyncTaskManager


def test_async_task_completion_lifecycle(tmp_path: Path) -> None:
    completed_tasks: list[AsyncTaskInfo] = []

    def on_complete(task_info: AsyncTaskInfo) -> None:
        completed_tasks.append(task_info)

    manager = AsyncTaskManager(on_complete=on_complete)

    def sample_worker(cancel_event: threading.Event) -> tuple[int, str, str]:
        time.sleep(0.05)
        return 0, "Build succeeded: 42 artifacts created", ""

    task = manager.launch_task(name="build_project", target_fn=sample_worker)
    assert task.task_id.startswith("task-")
    assert task.name == "build_project"

    # Wait for completion
    deadline = time.time() + 2.0
    while time.time() < deadline:
        queried = manager.get_task(task.task_id)
        if queried and queried.status == "COMPLETED":
            break
        time.sleep(0.01)

    final_task = manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == "COMPLETED"
    assert final_task.exit_code == 0
    assert final_task.output == "Build succeeded: 42 artifacts created"
    assert final_task.elapsed_s > 0.0
    assert len(completed_tasks) == 1
    assert completed_tasks[0].task_id == task.task_id


def test_async_task_cancellation() -> None:
    manager = AsyncTaskManager()

    def long_worker(cancel_event: threading.Event) -> tuple[int, str, str]:
        for _ in range(50):
            if cancel_event.is_set():
                return -1, "", "Cancelled by user"
            time.sleep(0.02)
        return 0, "done", ""

    task = manager.launch_task(name="long_download", target_fn=long_worker)

    # Allow worker to start running
    time.sleep(0.02)
    assert manager.cancel_task(task.task_id) is True

    deadline = time.time() + 2.0
    while time.time() < deadline:
        queried = manager.get_task(task.task_id)
        if queried and queried.status == "CANCELLED":
            break
        time.sleep(0.01)

    final_task = manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == "CANCELLED"


def test_async_task_exception_handling() -> None:
    manager = AsyncTaskManager()

    def failing_worker(cancel_event: threading.Event) -> tuple[int, str, str]:
        msg = "disk write error"
        raise RuntimeError(msg)

    task = manager.launch_task(name="failing_job", target_fn=failing_worker)

    deadline = time.time() + 2.0
    while time.time() < deadline:
        queried = manager.get_task(task.task_id)
        if queried and queried.status == "FAILED":
            break
        time.sleep(0.01)

    final_task = manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == "FAILED"
    assert "disk write error" in str(final_task.error)


def test_sandbox_service_task_integration(tmp_path: Path) -> None:
    sandbox = SandboxService(workspace_root=tmp_path, use_direct_fallback=True)

    # Check risk classification
    assert classify_risk("get_task_status") == Risk.READ
    assert classify_risk("list_tasks") == Risk.READ
    assert classify_risk("cancel_task") == Risk.READ

    def bg_job(cancel_event: threading.Event) -> tuple[int, str, str]:
        time.sleep(0.02)
        return 0, "All tests passed", ""

    info = sandbox.launch_async(name="run_tests", target_fn=bg_job)
    assert info.task_id.startswith("task-")

    # Query via execute_tool
    res = sandbox.execute_tool(
        call_id="call-01",
        tool_name="get_task_status",
        args={"task_id": info.task_id},
    )
    assert res.ok is True
    assert res.structured is not None
    assert res.structured["task_id"] == info.task_id

    # List tasks via execute_tool
    list_res = sandbox.execute_tool(
        call_id="call-02",
        tool_name="list_tasks",
        args={},
    )
    assert list_res.ok is True
    assert list_res.structured is not None
    assert list_res.structured["count"] >= 1

    # Query unknown task
    not_found_res = sandbox.execute_tool(
        call_id="call-03",
        tool_name="get_task_status",
        args={"task_id": "non_existent_id"},
    )
    assert not_found_res.ok is False
