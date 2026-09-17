"""
Project Lucca — Working Memory & Task Journal
Spec 04 §2, Spec 10 (T-MEM-14)
"""

import time
from typing import Any

from lucca.memory.db import DatabaseManager


class WorkingMemory:
    """
    Ephemeral in-memory working state for multi-step tasks.
    Keeps typed state while a task is active.
    On close, state is cleared and discarded without persisting to the memories table.
    Lifecycle events are recorded in task_journal.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self._tasks: dict[str, dict[str, Any]] = {}

    def open_task(self, task_id: str, now: float | None = None) -> None:
        current_time = now if now is not None else time.time()
        self._tasks[task_id] = {}
        writer = self.db.get_writer()
        writer.execute(
            "INSERT OR REPLACE INTO task_journal(task_id, opened_at) VALUES (?, ?)",
            (task_id, current_time),
        )

    def set(self, task_id: str, key: str, value: Any) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} is not open")
        self._tasks[task_id][key] = value

    def get(self, task_id: str, key: str, default: Any = None) -> Any:
        if task_id not in self._tasks:
            return default
        return self._tasks[task_id].get(key, default)

    def get_state(self, task_id: str) -> dict[str, Any]:
        return dict(self._tasks.get(task_id, {}))

    def close_task(
        self,
        task_id: str,
        outcome: str = "completed",
        now: float | None = None,
    ) -> None:
        current_time = now if now is not None else time.time()
        if task_id in self._tasks:
            self._tasks[task_id].clear()
            del self._tasks[task_id]
        writer = self.db.get_writer()
        writer.execute(
            "UPDATE task_journal SET closed_at = ?, outcome = ? WHERE task_id = ?",
            (current_time, outcome, task_id),
        )
