"""
Unit tests for MemoryTab (UI Multi-Selection, Batch Pruning, and Factory Reset).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from lucca.core.studio_facade import StudioFacade
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore
from lucca.ui.settings_tabs.memory_tab import MemoryTab


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def master_key() -> bytes:
    return b"01234567890123456789012345678901"


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_memory_tab.sqlite"
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


@pytest.fixture
def memory_tab(qapp: QApplication, facade: StudioFacade) -> MemoryTab:
    dialog = QWidget()
    tab = MemoryTab(dialog=dialog, facade=facade)
    return tab


def test_memory_tab_initial_state(memory_tab: MemoryTab) -> None:
    assert memory_tab.table_mem.rowCount() == 0
    assert "Active Memories: 0" in memory_tab.lbl_mem_stat_active.text()
    assert memory_tab.btn_del_selected.isEnabled() is False
    assert memory_tab.btn_del_mem.isEnabled() is False


def test_memory_tab_single_and_multi_select(memory_tab: MemoryTab, facade: StudioFacade) -> None:
    # 1. Seed 3 facts
    m1 = facade.add_memory_fact("Fact 1: Lucca loves robotics", importance=0.85)
    m2 = facade.add_memory_fact("Fact 2: Quantum physics is fascinating", importance=0.9)
    m3 = facade.add_memory_fact("Fact 3: MicroScheme runs deterministically", importance=0.75)
    assert m1 > 0 and m2 > 0 and m3 > 0

    memory_tab._refresh_memories()
    assert memory_tab.table_mem.rowCount() == 3

    # 2. Select single row (row 0)
    memory_tab.table_mem.selectRow(0)
    selected_mids = memory_tab._get_selected_memory_ids()
    assert len(selected_mids) == 1
    assert memory_tab.btn_del_selected.isEnabled() is True
    assert "Prune Selected (1)" in memory_tab.btn_del_selected.text()
    assert memory_tab.btn_del_mem.isEnabled() is True
    assert f"#{selected_mids[0]}" in memory_tab.btn_del_mem.text()

    # 3. Select All
    memory_tab._select_all_memories()
    assert len(memory_tab._get_selected_memory_ids()) == 3
    assert "Prune Selected (3)" in memory_tab.btn_del_selected.text()
    assert "Prune Selected (3)" in memory_tab.btn_del_mem.text()
    assert "3 memories" in memory_tab.lbl_selection_status.text()

    # 4. Deselect All
    memory_tab._deselect_all_memories()
    assert len(memory_tab._get_selected_memory_ids()) == 0
    assert memory_tab.btn_del_selected.isEnabled() is False
    assert memory_tab.btn_del_mem.isEnabled() is False
    assert "Selected: 0 memories" in memory_tab.lbl_selection_status.text()


def test_memory_tab_batch_delete(memory_tab: MemoryTab, facade: StudioFacade) -> None:
    # Clear any previous state
    facade.factory_reset_memories(user_confirmed=True)

    m1 = facade.add_memory_fact("Alpha", importance=0.8)
    m2 = facade.add_memory_fact("Beta", importance=0.8)
    m3 = facade.add_memory_fact("Gamma", importance=0.8)

    memory_tab._refresh_memories()
    assert memory_tab.table_mem.rowCount() == 3

    # Select first 2 rows using QTableWidgetSelectionRange
    from PyQt6.QtWidgets import QTableWidgetSelectionRange
    memory_tab.table_mem.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 5), True)
    selected_ids = memory_tab._get_selected_memory_ids()
    assert len(selected_ids) == 2

    # Prune with confirmation mock
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information"):
            memory_tab._delete_selected_memories()

    # Verify 1 memory remains
    assert facade.get_memory_stats()["active_memories"] == 1
    assert memory_tab.table_mem.rowCount() == 1


def test_memory_tab_factory_reset(memory_tab: MemoryTab, facade: StudioFacade) -> None:
    # Add multiple memories
    for i in range(5):
        facade.add_memory_fact(f"Memory statement number {i}", importance=0.8)

    memory_tab._refresh_memories()
    assert memory_tab.table_mem.rowCount() >= 5

    # Factory reset with confirmation
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information"):
            memory_tab._factory_reset_memories()

    # Verify zero memories in DB and table
    stats = facade.get_memory_stats()
    assert stats["active_memories"] == 0
    assert memory_tab.table_mem.rowCount() == 0
    assert "Active Memories: 0" in memory_tab.lbl_mem_stat_active.text()


def test_memory_tab_delete_key_event(memory_tab: MemoryTab, facade: StudioFacade) -> None:
    facade.factory_reset_memories(user_confirmed=True)
    m = facade.add_memory_fact("Fact for delete key test", importance=0.8)
    memory_tab._refresh_memories()
    assert memory_tab.table_mem.rowCount() == 1

    memory_tab.table_mem.selectRow(0)
    assert len(memory_tab._get_selected_memory_ids()) == 1

    # Simulate pressing Delete key
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Delete,
        Qt.KeyboardModifier.NoModifier,
    )
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information"):
            memory_tab.table_mem.keyPressEvent(key_event)

    assert facade.get_memory_stats()["active_memories"] == 0


def test_memory_tab_live_refresh_preserves_selection(memory_tab: MemoryTab, facade: StudioFacade) -> None:
    facade.factory_reset_memories(user_confirmed=True)
    m1 = facade.add_memory_fact("Keep selected 1", importance=0.8)
    m2 = facade.add_memory_fact("Keep selected 2", importance=0.8)
    memory_tab._refresh_memories()

    # User selects a row
    memory_tab.table_mem.selectRow(0)
    selected_before = memory_tab._get_selected_memory_ids()
    assert len(selected_before) == 1

    # Live refresh triggers: should NOT clear user selection!
    memory_tab._maybe_live_refresh_memories()
    selected_after = memory_tab._get_selected_memory_ids()
    assert selected_after == selected_before
