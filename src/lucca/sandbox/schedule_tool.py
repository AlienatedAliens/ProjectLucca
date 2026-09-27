"""
Project Lucca — Schedule Event Stub Tool
Validates ISO 8601 datetime and records schedule intent.
"""

from __future__ import annotations

from datetime import datetime
import ulid


def schedule_event(event_name: str, iso_datetime: str, message: str | None = None) -> str:
    """
    Validates datetime format and returns a ULID event_id.
    """
    name = event_name.strip()
    if not name:
        raise ValueError("event_name cannot be empty")
    try:
        datetime.fromisoformat(iso_datetime.strip())
    except ValueError as e:
        raise ValueError(f"Invalid ISO 8601 datetime '{iso_datetime}': {e}") from e

    return str(ulid.ULID())
