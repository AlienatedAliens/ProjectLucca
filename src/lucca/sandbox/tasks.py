"""
Project Lucca — Long Asynchronous Task Protocol
Spec 07 Proposal H (D-SAND-03)
Manages non-blocking background tasks with unique IDs, thread-safe status tracking,
spoken acknowledgments, and IPC completion notifications.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import structlog
import ulid

logger = structlog.get_logger(__name__)

TaskStatus = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]


@dataclass
class AsyncTaskInfo:
    task_id: str
    name: str
    status: TaskStatus
    start_time: float
    end_time: float | None = None
    exit_code: int | None = None
    output: str | None = None
    error: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def elapsed_s(self) -> float:
        end = self.end_time if self.end_time is not None else time.time()
        return max(0.0, end - self.start_time)


class AsyncTaskManager:
    """
    Thread-safe orchestrator for long-running asynchronous background tasks.
    Prevents blocking the voice interaction loop while ensuring honest progress tracking.
    """

    def __init__(
        self,
        on_complete: Callable[[AsyncTaskInfo], None] | None = None,
    ) -> None:
        self.on_complete = on_complete
        self._tasks: dict[str, AsyncTaskInfo] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def launch_task(
        self,
        name: str,
        target_fn: Callable[[threading.Event], tuple[int, str, str]],
        metadata: dict[str, str] | None = None,
    ) -> AsyncTaskInfo:
        """
        Launches a background worker function.
        target_fn signature: (cancel_event: threading.Event) -> (exit_code, stdout, stderr)
        """
        task_id = f"task-{ulid.ULID()}"
        cancel_event = threading.Event()

        task_info = AsyncTaskInfo(
            task_id=task_id,
            name=name,
            status="PENDING",
            start_time=time.time(),
            metadata=metadata or {},
        )

        with self._lock:
            self._tasks[task_id] = task_info
            self._cancel_flags[task_id] = cancel_event

        thread = threading.Thread(
            target=self._worker_wrapper,
            args=(task_id, target_fn, cancel_event),
            name=f"async-{name}-{task_id[:8]}",
            daemon=True,
        )

        with self._lock:
            self._threads[task_id] = thread
        thread.start()

        logger.info("async_task_launched", task_id=task_id, name=name)
        return task_info

    def _worker_wrapper(
        self,
        task_id: str,
        target_fn: Callable[[threading.Event], tuple[int, str, str]],
        cancel_event: threading.Event,
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = "RUNNING"

        exit_code = 0
        output_str = ""
        error_str = ""

        try:
            exit_code, output_str, error_str = target_fn(cancel_event)
            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    task.end_time = time.time()
                    if cancel_event.is_set():
                        task.status = "CANCELLED"
                        task.exit_code = -1
                        task.error = "Task cancelled by user"
                    elif exit_code == 0:
                        task.status = "COMPLETED"
                        task.exit_code = 0
                        task.output = output_str
                    else:
                        task.status = "FAILED"
                        task.exit_code = exit_code
                        task.error = error_str
        except Exception as exc:  # noqa: BLE001
            logger.error("async_task_failed", task_id=task_id, error=str(exc))
            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    task.end_time = time.time()
                    task.status = "FAILED"
                    task.exit_code = -2
                    task.error = str(exc)

        # Notify completion callback
        if self.on_complete:
            with self._lock:
                task_snapshot = self._tasks.get(task_id)
            if task_snapshot:
                try:
                    self.on_complete(task_snapshot)
                except Exception as cb_exc:  # noqa: BLE001
                    logger.warning("async_task_callback_error", error=str(cb_exc))

    def get_task(self, task_id: str) -> AsyncTaskInfo | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[AsyncTaskInfo]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            flag = self._cancel_flags.get(task_id)
            task = self._tasks.get(task_id)
            if flag and task and task.status in ("PENDING", "RUNNING"):
                flag.set()
                logger.info("async_task_cancel_requested", task_id=task_id)
                return True
        return False
