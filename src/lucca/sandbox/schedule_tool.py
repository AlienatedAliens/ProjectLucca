"""
Project Lucca — Persistent Schedule Event & Reminder Tool
Validates ISO 8601 datetime, persists scheduled events to SQLite, and claims due events for firing.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import ulid


@dataclass(frozen=True)
class ScheduledEvent:
    event_id: str
    event_name: str
    iso_datetime: str
    due_ts: float
    message: str | None
    status: str
    created_at: float
    fired_at: float | None = None


def ensure_schedule_table(conn: sqlite3.Connection) -> None:
    """Idempotently creates the scheduled_events table and index."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_events (
            event_id TEXT PRIMARY KEY,
            event_name TEXT NOT NULL,
            iso_datetime TEXT NOT NULL,
            due_ts REAL NOT NULL,
            message TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'FIRED', 'CANCELLED')),
            created_at REAL NOT NULL,
            fired_at REAL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduled_events_status_due
            ON scheduled_events(status, due_ts)
        """
    )


def _open_schedule_conn(db_path: Path | str) -> sqlite3.Connection:
    p = Path(db_path) if isinstance(db_path, str) else db_path
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    ensure_schedule_table(conn)
    return conn


def schedule_event(
    event_name: str,
    iso_datetime: str,
    message: str | None = None,
    *,
    db_path: Path | str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """
    Validates ISO 8601 datetime, persists the reminder into SQLite (when conn or db_path
    is supplied), and returns a ULID event_id.
    """
    name = event_name.strip()
    if not name:
        raise ValueError("event_name cannot be empty")
    cleaned_iso = iso_datetime.strip()
    try:
        dt = datetime.fromisoformat(cleaned_iso)
    except ValueError as e:
        raise ValueError(f"Invalid ISO 8601 datetime '{iso_datetime}': {e}") from e

    event_id = str(ulid.ULID())
    due_ts = float(dt.timestamp())
    created_at = time.time()

    if conn is not None:
        ensure_schedule_table(conn)
        conn.execute(
            """
            INSERT INTO scheduled_events (
                event_id, event_name, iso_datetime, due_ts,
                message, status, created_at, fired_at
            ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, NULL)
            """,
            (event_id, name, cleaned_iso, due_ts, message, created_at),
        )
    elif db_path is not None:
        owned = _open_schedule_conn(db_path)
        try:
            with owned:
                owned.execute(
                    """
                    INSERT INTO scheduled_events (
                        event_id, event_name, iso_datetime, due_ts,
                        message, status, created_at, fired_at
                    ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, NULL)
                    """,
                    (event_id, name, cleaned_iso, due_ts, message, created_at),
                )
        finally:
            owned.close()

    return event_id


def _row_to_event(row: sqlite3.Row | tuple[object, ...]) -> ScheduledEvent:
    return ScheduledEvent(
        event_id=str(row[0]),
        event_name=str(row[1]),
        iso_datetime=str(row[2]),
        due_ts=float(str(row[3])),
        message=str(row[4]) if row[4] is not None else None,
        status=str(row[5]),
        created_at=float(str(row[6])),
        fired_at=float(str(row[7])) if row[7] is not None else None,
    )


def list_scheduled_events(
    *,
    status: str | None = "PENDING",
    db_path: Path | str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[ScheduledEvent]:
    """Lists scheduled events ordered by due_ts ascending."""
    if conn is None and db_path is None:
        return []

    owned: sqlite3.Connection | None = None
    active_conn = conn
    if active_conn is None and db_path is not None:
        owned = _open_schedule_conn(db_path)
        active_conn = owned

    if active_conn is None:
        return []
    try:
        ensure_schedule_table(active_conn)
        if status is not None:
            cur = active_conn.execute(
                """
                SELECT event_id, event_name, iso_datetime, due_ts,
                       message, status, created_at, fired_at
                FROM scheduled_events
                WHERE status = ?
                ORDER BY due_ts ASC
                """,
                (status.upper(),),
            )
        else:
            cur = active_conn.execute(
                """
                SELECT event_id, event_name, iso_datetime, due_ts,
                       message, status, created_at, fired_at
                FROM scheduled_events
                ORDER BY due_ts ASC
                """
            )
        return [_row_to_event(r) for r in cur.fetchall()]
    finally:
        if owned is not None:
            owned.close()


def claim_due_events(
    *,
    now: float | None = None,
    db_path: Path | str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[ScheduledEvent]:
    """Atomically claims all PENDING scheduled events with due_ts <= now and marks them FIRED."""
    if conn is None and db_path is None:
        return []

    current_time = now if now is not None else time.time()
    owned: sqlite3.Connection | None = None
    active_conn = conn
    if active_conn is None and db_path is not None:
        owned = _open_schedule_conn(db_path)
        active_conn = owned

    if active_conn is None:
        return []
    try:
        ensure_schedule_table(active_conn)
        cur = active_conn.execute(
            """
            SELECT event_id, event_name, iso_datetime, due_ts,
                   message, status, created_at, fired_at
            FROM scheduled_events
            WHERE status = 'PENDING' AND due_ts <= ?
            ORDER BY due_ts ASC
            """,
            (current_time,),
        )
        rows = cur.fetchall()
        if not rows:
            return []

        claimed: list[ScheduledEvent] = []
        for r in rows:
            ev = _row_to_event(r)
            active_conn.execute(
                """
                UPDATE scheduled_events
                SET status = 'FIRED', fired_at = ?
                WHERE event_id = ? AND status = 'PENDING'
                """,
                (current_time, ev.event_id),
            )
            claimed.append(
                ScheduledEvent(
                    event_id=ev.event_id,
                    event_name=ev.event_name,
                    iso_datetime=ev.iso_datetime,
                    due_ts=ev.due_ts,
                    message=ev.message,
                    status="FIRED",
                    created_at=ev.created_at,
                    fired_at=current_time,
                )
            )
        if owned is not None:
            owned.commit()
        return claimed
    finally:
        if owned is not None:
            owned.close()
