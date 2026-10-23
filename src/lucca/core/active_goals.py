"""
Project Lucca — First-Class Shared Active Goal State Machine
WO-36 Milestone 36.2 & Spec D-REAS-09

Maintains active user goals and shared collaborative intent:
1. Gated strictly on USER_EXPLICIT or USER_DERIVED provenance envelopes.
2. Backed by persistent SQLite active_goals table (migration 0009).
3. Injects active goal context as a lightweight retrieval boost in HybridRetriever and EpisodeRecall.

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

import structlog

from lucca.core.schemas import Provenance

if TYPE_CHECKING:
    from lucca.memory.db import DatabaseManager

logger = structlog.get_logger(__name__)

ALLOWED_GOAL_PROVENANCES: Final[frozenset[str]] = frozenset(
    {
        str(Provenance.USER_EXPLICIT),
        str(Provenance.USER_DERIVED),
        "USER_EXPLICIT",
        "USER_DERIVED",
    }
)

GoalStatus = Literal["ACTIVE", "PAUSED", "COMPLETED", "ABANDONED"]


@dataclass
class ActiveGoal:
    goal_id: str
    title: str
    description: str
    status: GoalStatus
    priority: int
    provenance: str
    provenance_envelope_id: str
    created_at: float
    updated_at: float


class ActiveGoalManager:
    """Manages collaborative shared goals with provenance gating and memory biasing."""

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self.db = db
        self._in_memory_goals: dict[str, ActiveGoal] = {}

    def create_goal(
        self,
        title: str,
        description: str = "",
        provenance: str | Provenance = "USER_EXPLICIT",
        provenance_envelope_id: str = "",
        priority: int = 1,
    ) -> ActiveGoal:
        """
        Creates a new active goal.
        Raises ValueError if provenance is not USER_EXPLICIT or USER_DERIVED.
        """
        prov_str = str(provenance).strip()
        if prov_str not in ALLOWED_GOAL_PROVENANCES:
            raise ValueError(
                f"ActiveGoal creation requires USER_EXPLICIT or USER_DERIVED provenance, got '{prov_str}'"
            )

        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Goal title cannot be empty")

        now = time.time()
        goal_id = f"goal-{uuid.uuid4().hex[:12]}"
        env_id = provenance_envelope_id or f"env-{uuid.uuid4().hex[:8]}"

        goal = ActiveGoal(
            goal_id=goal_id,
            title=clean_title,
            description=description.strip(),
            status="ACTIVE",
            priority=priority,
            provenance=prov_str,
            provenance_envelope_id=env_id,
            created_at=now,
            updated_at=now,
        )

        self._in_memory_goals[goal_id] = goal

        if self.db is not None:
            try:
                with self.db.get_writer() as conn:
                    conn.execute(
                        """
                        INSERT INTO active_goals
                        (goal_id, title, description, status, priority, provenance, provenance_envelope_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            goal.goal_id,
                            goal.title,
                            goal.description,
                            goal.status,
                            goal.priority,
                            goal.provenance,
                            goal.provenance_envelope_id,
                            goal.created_at,
                            goal.updated_at,
                        ),
                    )
            except Exception as exc:
                logger.debug("active_goal_persist_failed", error=str(exc))

        logger.info("active_goal_created", goal_id=goal_id, title=clean_title, priority=priority)
        return goal

    def list_active_goals(self) -> list[ActiveGoal]:
        """Returns all currently active goals sorted by priority descending."""
        if self.db is not None:
            try:
                with self.db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT goal_id, title, description, status, priority,
                               provenance, provenance_envelope_id, created_at, updated_at
                        FROM active_goals
                        WHERE status = 'ACTIVE'
                        ORDER BY priority DESC, created_at DESC
                        """
                    )
                    rows = cur.fetchall()
                    goals: list[ActiveGoal] = []
                    for r in rows:
                        goals.append(
                            ActiveGoal(
                                goal_id=str(r[0]),
                                title=str(r[1]),
                                description=str(r[2]),
                                status=str(r[3]),  # type: ignore[arg-type]
                                priority=int(r[4]),
                                provenance=str(r[5]),
                                provenance_envelope_id=str(r[6]),
                                created_at=float(r[7]),
                                updated_at=float(r[8]),
                            )
                        )
                    return goals
            except Exception as exc:
                logger.debug("list_active_goals_db_failed", error=str(exc))

        return sorted(
            [g for g in self._in_memory_goals.values() if g.status == "ACTIVE"],
            key=lambda g: (g.priority, g.created_at),
            reverse=True,
        )

    def update_goal_status(self, goal_id: str, status: GoalStatus) -> bool:
        """Transitions goal status between ACTIVE, PAUSED, COMPLETED, ABANDONED."""
        valid_statuses = ("ACTIVE", "PAUSED", "COMPLETED", "ABANDONED")
        if status not in valid_statuses:
            raise ValueError(f"Invalid goal status '{status}'. Must be one of {valid_statuses}")

        now = time.time()
        updated = False

        if goal_id in self._in_memory_goals:
            g = self._in_memory_goals[goal_id]
            self._in_memory_goals[goal_id] = ActiveGoal(
                goal_id=g.goal_id,
                title=g.title,
                description=g.description,
                status=status,
                priority=g.priority,
                provenance=g.provenance,
                provenance_envelope_id=g.provenance_envelope_id,
                created_at=g.created_at,
                updated_at=now,
            )
            updated = True

        if self.db is not None:
            try:
                with self.db.get_writer() as conn:
                    cur = conn.execute(
                        "UPDATE active_goals SET status = ?, updated_at = ? WHERE goal_id = ?",
                        (status, now, goal_id),
                    )
                    if cur.rowcount > 0:
                        updated = True
            except Exception as exc:
                logger.debug("update_goal_status_db_failed", error=str(exc))

        return updated

    def get_goal_context_prompt(self, limit: int = 3) -> str | None:
        """Formats active goals into a compact prompt injection context."""
        active = self.list_active_goals()[:limit]
        if not active:
            return None
        items = [f"[{g.priority}] {g.title}" for g in active]
        return f"Active Shared Goals: {'; '.join(items)}"
