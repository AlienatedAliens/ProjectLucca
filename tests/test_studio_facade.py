"""
Unit tests for StudioFacade (F-ARCH-104 / WO-18e).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.schemas import RuleState
from lucca.core.studio_facade import StudioFacade
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore


@pytest.fixture
def master_key() -> bytes:
    return b"01234567890123456789012345678901"


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_memory.sqlite"
    db = DatabaseManager(db_path=db_file)
    db.migrate()
    return db


@pytest.fixture
def test_store(test_db: DatabaseManager, master_key: bytes) -> MemoryStore:
    return MemoryStore(db=test_db, master_key=master_key)


@pytest.fixture
def facade(test_db: DatabaseManager, test_store: MemoryStore, master_key: bytes) -> StudioFacade:
    return StudioFacade(
        db=test_db,
        store=test_store,
        master_key=master_key,
    )


def test_facade_memory_lifecycle(facade: StudioFacade) -> None:
    # 1. Add fact
    mid = facade.add_memory_fact("The speed of light is 299792458 m/s", importance=0.9)
    assert mid > 0

    # 2. Stats
    stats = facade.get_memory_stats()
    assert stats["active_memories"] == 1
    assert stats["total_memories"] == 1

    # 3. List
    mems = facade.list_memories(search="speed of light")
    assert len(mems) == 1
    assert mems[0]["memory_id"] == mid
    assert "299792458" in str(mems[0]["content"])

    # 4. Update
    new_mid = facade.update_memory(mid, "The speed of light in vacuum is approx 300000 km/s", importance=0.95)
    assert new_mid > 0
    assert new_mid != mid

    # 5. Forget (Trap 2: routes through store.forget(user_confirmed=True))
    facade.forget_memory(new_mid, user_confirmed=True)
    facade.forget_memory(mid, user_confirmed=True)

    # Stats after forget
    stats_after = facade.get_memory_stats()
    assert stats_after["active_memories"] == 0
    assert stats_after["forgotten_memories"] == 2


def test_facade_vacuum_database_locked_error(facade: StudioFacade, monkeypatch: pytest.MonkeyPatch) -> None:
    # Trap 3: OperationalError("database is locked") must surface as clean RuntimeError
    def mock_execute(sql: str) -> None:
        raise sqlite3.OperationalError("database is locked")

    fake_conn = MagicMock()
    fake_conn.execute.side_effect = mock_execute
    monkeypatch.setattr(facade.db, "get_writer", lambda: fake_conn)

    with pytest.raises(RuntimeError, match="shut down Lucca core"):
        facade.vacuum_database()


def test_facade_lisp_and_skills(facade: StudioFacade) -> None:
    # 1. LISP parse
    parsed = facade.parse_rule(
        '(rule "test-rule-v1" :when (intent= "test") :plan (list (say "hi")) :priority 5)'
    )
    assert parsed.rule_id == "test-rule-v1"
    assert parsed.priority == 5

    # 2. LISP evaluate
    state = RuleState(intent="test")
    result = facade.evaluate_rule(parsed, state)
    assert result.fired is True
    assert result.errored is False

    # 3. Stats UCL
    ucl = facade.rule_of_three_ucl(n_clusters=10)
    assert ucl > 0.0

    # 4. Skills directory
    skills_dir = facade.get_skills_dir()
    assert isinstance(skills_dir, Path)


def test_facade_telemetry() -> None:
    metrics = StudioFacade.get_system_metrics()
    assert "ram" in metrics
    assert "cpu" in metrics
    assert "dgpu" in metrics
    assert "npu" in metrics


def test_facade_forget_memories_and_factory_reset(facade: StudioFacade) -> None:
    # 1. Add multiple memories
    m1 = facade.add_memory_fact("Fact 1: Lucca loves engineering", importance=0.8)
    m2 = facade.add_memory_fact("Fact 2: Water boils at 100 degrees Celsius", importance=0.85)
    m3 = facade.add_memory_fact("Fact 3: Python is expressive", importance=0.75)
    assert m1 > 0 and m2 > 0 and m3 > 0

    stats = facade.get_memory_stats()
    assert stats["active_memories"] == 3

    # 2. Batch forget 2 memories
    count = facade.forget_memories([m1, m2], user_confirmed=True)
    assert count == 2

    stats = facade.get_memory_stats()
    assert stats["active_memories"] == 1
    remaining = facade.list_memories()
    assert len(remaining) == 1
    assert remaining[0]["memory_id"] == m3

    # 3. Add more facts
    m4 = facade.add_memory_fact("Fact 4: The earth orbits the sun", importance=0.9)
    m5 = facade.add_memory_fact("Fact 5: Sound travels in waves", importance=0.8)
    assert facade.get_memory_stats()["active_memories"] == 3

    # 4. Factory reset memories to zero
    reset_count = facade.factory_reset_memories(user_confirmed=True)
    assert reset_count >= 3

    stats_zero = facade.get_memory_stats()
    assert stats_zero["active_memories"] == 0
    assert len(facade.list_memories()) == 0

    # 5. Factory reset on empty store returns 0
    assert facade.factory_reset_memories(user_confirmed=True) == 0
