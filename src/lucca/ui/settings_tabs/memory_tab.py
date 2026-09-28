"""
Project Lucca — Episodic & Semantic Memory Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = structlog.get_logger(__name__)


class MemoryTab(QWidget):
    """Tab 7: Episodic & Semantic Memory System."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self._current_selected_mid: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Database Stats Header Banner
        grp_stats = QGroupBox("Memory Store Statistics & Database Topology", self)
        h_stats = QHBoxLayout(grp_stats)
        self.lbl_mem_stat_active = QLabel("Active: --", grp_stats)
        self.lbl_mem_stat_total = QLabel("Total Records: --", grp_stats)
        self.lbl_mem_stat_size = QLabel("Disk Size: --", grp_stats)
        self.lbl_mem_stat_active.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.lbl_mem_stat_total.setStyleSheet("color: #ffffff; font-weight: bold;")
        self.lbl_mem_stat_size.setStyleSheet("color: #38bdf8; font-weight: bold;")
        h_stats.addWidget(self.lbl_mem_stat_active)
        h_stats.addWidget(self.lbl_mem_stat_total)
        h_stats.addWidget(self.lbl_mem_stat_size)
        h_stats.addStretch()

        btn_vacuum = QPushButton("🧹 Vacuum & Optimize DB", grp_stats)
        btn_vacuum.clicked.connect(self._vacuum_memory_db)
        h_stats.addWidget(btn_vacuum)

        btn_factory_reset = QPushButton("💥 Factory Reset / Hard Purge (Clears All Stores)", grp_stats)
        btn_factory_reset.setToolTip(
            "Permanently eradicate all memories, knowledge graphs, decisions, and induced rules across all backing stores"
        )
        btn_factory_reset.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #881337, stop:1 #4c0519); "
            "border: 2px solid #f43f5e; color: #ffffff; font-weight: bold; padding: 5px 12px; } "
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #be123c, stop:1 #700b30); "
            "border-color: #fda4af; } "
            "QPushButton:pressed { background: #fda4af; color: #4c0519; }"
        )
        btn_factory_reset.clicked.connect(self._factory_reset_memories)
        h_stats.addWidget(btn_factory_reset)

        layout.addWidget(grp_stats)

        # Filter & Search Toolbar
        grp_filter = QGroupBox("Memory Explorer, Semantic Filters & Knowledge Inspector", self)
        v_filter = QVBoxLayout(grp_filter)

        h_toolbar = QHBoxLayout()
        h_toolbar.addWidget(QLabel("Category Filter:", grp_filter))
        self.combo_mem_kind = QComboBox(grp_filter)
        self.combo_mem_kind.addItem("All Categories", "")
        self.combo_mem_kind.addItem("Episodic Conversation Turns", "episodic")
        self.combo_mem_kind.addItem("Semantic Facts & Knowledge", "fact")
        self.combo_mem_kind.addItem("User Preferences", "preference")
        self.combo_mem_kind.currentIndexChanged.connect(self._refresh_memories)
        h_toolbar.addWidget(self.combo_mem_kind)

        self.line_mem_search = QLineEdit(grp_filter)
        self.line_mem_search.setPlaceholderText("Search content, intent keywords, or provenance...")
        self.line_mem_search.returnPressed.connect(self._refresh_memories)
        h_toolbar.addWidget(self.line_mem_search, stretch=2)

        btn_search = QPushButton("🔍 Search", grp_filter)
        btn_search.clicked.connect(self._refresh_memories)
        h_toolbar.addWidget(btn_search)

        btn_add_fact = QPushButton("➕ Teach New Fact", grp_filter)
        btn_add_fact.clicked.connect(self._add_new_fact_dialog)
        h_toolbar.addWidget(btn_add_fact)

        v_filter.addLayout(h_toolbar)

        # Batch Selection & Management Bar
        h_batch = QHBoxLayout()
        self.lbl_selection_status = QLabel("Selected: 0 memories", grp_filter)
        self.lbl_selection_status.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
        h_batch.addWidget(self.lbl_selection_status)
        h_batch.addSpacing(10)

        btn_select_all = QPushButton("☑️ Select All Visible", grp_filter)
        btn_select_all.setToolTip("Select all visible memories in the table (Ctrl+A)")
        btn_select_all.clicked.connect(self._select_all_memories)
        h_batch.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("⬜ Deselect All", grp_filter)
        btn_deselect_all.setToolTip("Clear current selection")
        btn_deselect_all.clicked.connect(self._deselect_all_memories)
        h_batch.addWidget(btn_deselect_all)

        h_batch.addSpacing(10)

        self.btn_del_selected = QPushButton("🗑️ Prune Selected (0)", grp_filter)
        self.btn_del_selected.setToolTip("Permanently delete selected memories (Del)")
        self.btn_del_selected.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7f1d1d, stop:1 #450a0a); "
            "border: 1.5px solid #ef4444; color: #fca5a5; } "
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #991b1b, stop:1 #581c87); "
            "color: #ffffff; border-color: #f87171; } "
            "QPushButton:disabled { background: #1e2648; color: #64748b; border-color: #475569; }"
        )
        self.btn_del_selected.setEnabled(False)
        self.btn_del_selected.clicked.connect(self._delete_selected_memories)
        h_batch.addWidget(self.btn_del_selected)

        h_batch.addStretch()

        btn_batch_reset = QPushButton("💥 Factory Reset All Memories", grp_filter)
        btn_batch_reset.setToolTip("Reset memory store to zero active memories")
        btn_batch_reset.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #881337, stop:1 #4c0519); "
            "border: 1.5px solid #f43f5e; color: #ffffff; font-weight: bold; } "
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #be123c, stop:1 #700b30); "
            "border-color: #fda4af; color: #ffffff; }"
        )
        btn_batch_reset.clicked.connect(self._factory_reset_memories)
        h_batch.addWidget(btn_batch_reset)

        v_filter.addLayout(h_batch)

        # Memory Table with multi-row selection
        self.table_mem = QTableWidget(0, 6, grp_filter)
        self.table_mem.setHorizontalHeaderLabels(
            ["ID", "Kind", "Content / Fact Statement", "Importance", "Provenance", "Created At"]
        )
        self.table_mem.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_mem.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_mem.setAlternatingRowColors(True)
        self.table_mem.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr_mem = self.table_mem.horizontalHeader()
        if hdr_mem is not None:
            hdr_mem.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr_mem.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hdr_mem.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            hdr_mem.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            hdr_mem.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            hdr_mem.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.table_mem.itemSelectionChanged.connect(self._on_memory_selection_changed)

        # Context menu for quick pruning and selection
        self.table_mem.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_mem.customContextMenuRequested.connect(self._show_table_context_menu)

        # Delete & Backspace keyboard shortcuts
        orig_key_press = self.table_mem.keyPressEvent

        def _table_key_press(event: QKeyEvent) -> None:
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                if self._get_selected_memory_ids():
                    self._delete_selected_memories()
                    event.accept()
                    return
            orig_key_press(event)

        self.table_mem.keyPressEvent = _table_key_press

        v_filter.addWidget(self.table_mem)

        # Selected Memory Inspector & Editor
        grp_inspect = QGroupBox("Selected Memory Inspector & Human-in-the-Loop Editor", grp_filter)
        v_inspect = QVBoxLayout(grp_inspect)

        h_meta = QHBoxLayout()
        self.lbl_inspect_id = QLabel("Memory ID: None", grp_inspect)
        self.lbl_inspect_prov = QLabel("Provenance: None", grp_inspect)
        self.lbl_inspect_conf = QLabel("Confidence: 1.0", grp_inspect)
        self.lbl_inspect_id.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        h_meta.addWidget(self.lbl_inspect_id)
        h_meta.addWidget(self.lbl_inspect_prov)
        h_meta.addWidget(self.lbl_inspect_conf)
        h_meta.addStretch()
        v_inspect.addLayout(h_meta)

        self.txt_inspect_content = QPlainTextEdit(grp_inspect)
        self.txt_inspect_content.setFont(QFont("Consolas", 10))
        self.txt_inspect_content.setMaximumHeight(70)
        v_inspect.addWidget(self.txt_inspect_content)

        h_edit_act = QHBoxLayout()
        h_edit_act.addWidget(QLabel("Importance:", grp_inspect))
        self.slider_inspect_imp = QSlider(Qt.Orientation.Horizontal, grp_inspect)
        self.slider_inspect_imp.setRange(0, 100)
        self.slider_inspect_imp.setValue(80)
        self.lbl_inspect_imp_val = QLabel("0.80", grp_inspect)
        self.slider_inspect_imp.valueChanged.connect(
            lambda val: self.lbl_inspect_imp_val.setText(f"{(val / 100.0):.2f}")
        )
        h_edit_act.addWidget(self.slider_inspect_imp)
        h_edit_act.addWidget(self.lbl_inspect_imp_val)

        self.btn_save_mem = QPushButton("💾 Save Changes", grp_inspect)
        self.btn_save_mem.clicked.connect(self._save_memory_changes)
        h_edit_act.addWidget(self.btn_save_mem)

        self.btn_del_mem = QPushButton("🗑️ Prune Memory", grp_inspect)
        self.btn_del_mem.clicked.connect(self._delete_selected_memories)
        h_edit_act.addWidget(self.btn_del_mem)

        h_edit_act.addStretch()
        v_inspect.addLayout(h_edit_act)

        v_filter.addWidget(grp_inspect)
        layout.addWidget(grp_filter)

        # Autobiographical Belief Revision & Review Queue (Spec D-MEM-04 / Rung A1)
        grp_review = QGroupBox("Belief Revision & Review Queue (Spec D-MEM-04, Rung A1)", self)
        v_review = QVBoxLayout(grp_review)

        h_rev_top = QHBoxLayout()
        self.lbl_review_count = QLabel("Pending Revisions: 0", grp_review)
        self.lbl_review_count.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        h_rev_top.addWidget(self.lbl_review_count)
        h_rev_top.addStretch()

        btn_refresh_rev = QPushButton("🔄 Refresh Queue", grp_review)
        btn_refresh_rev.clicked.connect(self._refresh_review_queue)
        h_rev_top.addWidget(btn_refresh_rev)

        btn_appr_rev = QPushButton("✅ Approve Revision", grp_review)
        btn_appr_rev.clicked.connect(self._approve_selected_review)
        h_rev_top.addWidget(btn_appr_rev)

        btn_rej_rev = QPushButton("❌ Reject Revision", grp_review)
        btn_rej_rev.clicked.connect(self._reject_selected_review)
        h_rev_top.addWidget(btn_rej_rev)

        v_review.addLayout(h_rev_top)

        # Review Table
        self.table_review = QTableWidget(0, 6, grp_review)
        self.table_review.setHorizontalHeaderLabels(
            [
                "Review ID",
                "Belief ID",
                "Old Content",
                "Proposed Content",
                "Trigger Reason",
                "Status",
            ]
        )
        hdr_rev = self.table_review.horizontalHeader()
        if hdr_rev is not None:
            hdr_rev.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            hdr_rev.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        v_review.addWidget(self.table_review)

        # Topic Review Management
        h_topic_box = QHBoxLayout()
        h_topic_box.addWidget(QLabel("Review-Required Topics:", grp_review))
        self.combo_rev_topics = QComboBox(grp_review)
        h_topic_box.addWidget(self.combo_rev_topics, stretch=1)

        self.line_new_topic = QLineEdit(grp_review)
        self.line_new_topic.setPlaceholderText("Topic name...")
        h_topic_box.addWidget(self.line_new_topic)

        btn_add_topic = QPushButton("➕ Mark Topic", grp_review)
        btn_add_topic.clicked.connect(self._add_review_topic)
        h_topic_box.addWidget(btn_add_topic)

        btn_del_topic = QPushButton("➖ Unmark Topic", grp_review)
        btn_del_topic.clicked.connect(self._remove_review_topic)
        h_topic_box.addWidget(btn_del_topic)

        v_review.addLayout(h_topic_box)
        layout.addWidget(grp_review)

        self._refresh_memories()

        # WO-9 A10 (F17): periodic live refresh while the memory tab is visible.
        self._mem_refresh_timer = QTimer(self)
        self._mem_refresh_timer.setInterval(5000)
        self._mem_refresh_timer.timeout.connect(self._maybe_live_refresh_memories)
        self._mem_refresh_timer.start()

    def _maybe_live_refresh_memories(self) -> None:
        """WO-9 A10: refresh the memory table only when visible and active."""
        if not self.isVisible():
            return
        tabs = getattr(self.dialog, "tabs", None)
        if tabs is not None and tabs.currentIndex() != 7:
            return

        # If user has an active selection or is typing in the inspector,
        # update only stats labels to avoid wiping the table and interrupting them!
        if self._get_selected_memory_ids() or self.txt_inspect_content.hasFocus():
            try:
                st = self.facade.get_memory_stats()
                self.lbl_mem_stat_active.setText(f"Active Memories: {st.get('active_memories', 0)}")
                self.lbl_mem_stat_total.setText(f"Total Records: {st.get('total_memories', 0)}")
                self.lbl_mem_stat_size.setText(f"DB Size: {st.get('db_size_kb', 0)} KB")
            except Exception as exc:
                _LOG.debug("get_memory_stats_failed: %s", exc)
            return

        self._refresh_memories()

    def _refresh_memories(self) -> None:
        try:
            st = self.facade.get_memory_stats()
            self.lbl_mem_stat_active.setText(f"Active Memories: {st.get('active_memories', 0)}")
            self.lbl_mem_stat_total.setText(f"Total Records: {st.get('total_memories', 0)}")
            self.lbl_mem_stat_size.setText(f"DB Size: {st.get('db_size_kb', 0)} KB")
        except Exception as exc:
            _LOG.debug("get_memory_stats_failed: %s", exc)

        search = self.line_mem_search.text().strip()
        kind_filter = str(self.combo_mem_kind.currentData())

        prev_selected = set(self._get_selected_memory_ids())

        try:
            mems = self.facade.list_memories(search=search)
            if kind_filter:
                mems = [m for m in mems if m.get("kind") == kind_filter]

            self.table_mem.blockSignals(True)
            self.table_mem.setRowCount(0)
            for m in mems:
                row = self.table_mem.rowCount()
                self.table_mem.insertRow(row)

                mid = str(m.get("memory_id", ""))
                kind = str(m.get("kind", ""))
                content = str(m.get("content", ""))
                imp = f"{float(m.get('importance', 0.8)):.2f}"
                prov = str(m.get("provenance", "USER_EXPLICIT"))
                ts = datetime.fromtimestamp(float(m.get("created_at", time.time()))).strftime(
                    "%Y-%m-%d %H:%M"
                )

                self.table_mem.setItem(row, 0, QTableWidgetItem(mid))
                self.table_mem.setItem(row, 1, QTableWidgetItem(kind))
                self.table_mem.setItem(row, 2, QTableWidgetItem(content))
                self.table_mem.setItem(row, 3, QTableWidgetItem(imp))
                self.table_mem.setItem(row, 4, QTableWidgetItem(prov))
                self.table_mem.setItem(row, 5, QTableWidgetItem(ts))

            # Re-apply selection if rows still exist
            if prev_selected:
                for r in range(self.table_mem.rowCount()):
                    it = self.table_mem.item(r, 0)
                    if it and it.text().isdigit() and int(it.text()) in prev_selected:
                        self.table_mem.selectRow(r)

            self.table_mem.blockSignals(False)
            self._on_memory_selection_changed()

        except Exception as exc:
            self.table_mem.blockSignals(False)
            _LOG.debug("refresh_memories_failed: %s", exc)
            print(f"[UI] Memory refresh error: {exc}")

    def _get_selected_memory_ids(self) -> list[int]:
        selected_rows = set()
        for idx in self.table_mem.selectedIndexes():
            selected_rows.add(idx.row())
        ids: list[int] = []
        for r in sorted(selected_rows):
            item = self.table_mem.item(r, 0)
            if item and item.text().isdigit():
                ids.append(int(item.text()))
        return ids

    def _select_all_memories(self) -> None:
        self.table_mem.selectAll()

    def _deselect_all_memories(self) -> None:
        self.table_mem.clearSelection()

    def _show_table_context_menu(self, pos: QPoint) -> None:
        selected_ids = self._get_selected_memory_ids()
        menu = QMenu(self)
        if selected_ids:
            count = len(selected_ids)
            del_text = (
                f"🗑️ Prune Selected ({count})"
                if count > 1
                else f"🗑️ Prune Memory #{selected_ids[0]}"
            )
            act_del = menu.addAction(del_text)
            act_del.triggered.connect(self._delete_selected_memories)
            menu.addSeparator()
            act_desel = menu.addAction("⬜ Deselect All")
            act_desel.triggered.connect(self._deselect_all_memories)

        act_sel_all = menu.addAction("☑️ Select All Visible")
        act_sel_all.triggered.connect(self._select_all_memories)

        menu.addSeparator()
        act_reset = menu.addAction("💥 Factory Reset All Memories")
        act_reset.triggered.connect(self._factory_reset_memories)

        menu.exec(self.table_mem.viewport().mapToGlobal(pos))

    def _on_memory_selection_changed(self) -> None:
        selected_ids = self._get_selected_memory_ids()
        count = len(selected_ids)

        if count == 0:
            self._current_selected_mid = None
            self.lbl_selection_status.setText("Selected: 0 memories")
            self.btn_del_selected.setText("🗑️ Prune Selected (0)")
            self.btn_del_selected.setEnabled(False)

            self.lbl_inspect_id.setText("Memory ID: None")
            self.lbl_inspect_prov.setText("Provenance: None")
            self.lbl_inspect_conf.setText("Confidence: 1.0")
            self.txt_inspect_content.clear()
            self.txt_inspect_content.setEnabled(False)
            self.slider_inspect_imp.setEnabled(False)
            self.btn_save_mem.setEnabled(False)
            self.btn_del_mem.setText("🗑️ Prune Memory")
            self.btn_del_mem.setEnabled(False)

        elif count == 1:
            mid = selected_ids[0]
            self._current_selected_mid = mid
            self.lbl_selection_status.setText(f"Selected: 1 memory (#{mid})")
            self.btn_del_selected.setText("🗑️ Prune Selected (1)")
            self.btn_del_selected.setEnabled(True)

            self.txt_inspect_content.setEnabled(True)
            self.slider_inspect_imp.setEnabled(True)
            self.btn_save_mem.setEnabled(True)
            self.btn_del_mem.setText(f"🗑️ Prune Memory #{mid}")
            self.btn_del_mem.setEnabled(True)

            # Populate inspector with the single memory's data
            for r in range(self.table_mem.rowCount()):
                it = self.table_mem.item(r, 0)
                if it and it.text() == str(mid):
                    content_item = self.table_mem.item(r, 2)
                    imp_item = self.table_mem.item(r, 3)
                    prov_item = self.table_mem.item(r, 4)
                    self.lbl_inspect_id.setText(f"Memory ID: #{mid}")
                    self.lbl_inspect_prov.setText(
                        f"Provenance: {prov_item.text() if prov_item else 'Unknown'}"
                    )
                    self.lbl_inspect_conf.setText("Confidence: 1.0")
                    if content_item:
                        self.txt_inspect_content.setPlainText(content_item.text())
                    if imp_item:
                        try:
                            val = int(float(imp_item.text()) * 100)
                            self.slider_inspect_imp.setValue(val)
                        except ValueError:
                            pass
                    break

        else:  # count > 1
            self._current_selected_mid = None
            self.lbl_selection_status.setText(f"Selected: {count} memories")
            self.btn_del_selected.setText(f"🗑️ Prune Selected ({count})")
            self.btn_del_selected.setEnabled(True)

            self.lbl_inspect_id.setText(f"{count} Memories Selected")
            id_preview = ", ".join(f"#{m}" for m in selected_ids[:6])
            if count > 6:
                id_preview += f", ... (+{count - 6} more)"
            self.lbl_inspect_prov.setText(f"IDs: {id_preview}")
            self.lbl_inspect_conf.setText(f"Batch ({count} items)")
            self.txt_inspect_content.setPlainText(
                f"{count} memories selected for batch operations.\n"
                f"Click 'Prune Selected ({count})' or press Delete to remove them all."
            )
            self.txt_inspect_content.setEnabled(False)
            self.slider_inspect_imp.setEnabled(False)
            self.btn_save_mem.setEnabled(False)
            self.btn_del_mem.setText(f"🗑️ Prune Selected ({count})")
            self.btn_del_mem.setEnabled(True)

    def _on_memory_selected(self, row: int, col: int) -> None:
        """Row clicked callback (kept for API compatibility)."""
        self._on_memory_selection_changed()

    def _save_memory_changes(self) -> None:
        if self._current_selected_mid is None:
            return
        new_txt = self.txt_inspect_content.toPlainText().strip()
        imp = self.slider_inspect_imp.value() / 100.0
        try:
            self.facade.update_memory(self._current_selected_mid, new_txt, imp)
            self._refresh_memories()
            QMessageBox.information(
                self, "Memory Updated", f"Memory #{self._current_selected_mid} saved successfully."
            )
        except Exception as exc:
            _LOG.debug("save_memory_failed: %s", exc)
            QMessageBox.critical(self, "Error", f"Failed to save memory: {exc}")

    def _delete_selected_memories(self) -> None:
        """Prunes all currently selected memories with explicit user confirmation."""
        selected_ids = self._get_selected_memory_ids()
        if not selected_ids:
            QMessageBox.information(
                self, "No Selection", "Please select one or more memories to prune."
            )
            return

        count = len(selected_ids)
        if count == 1:
            msg = f"Permanently prune memory #{selected_ids[0]}?"
        else:
            id_preview = ", ".join(f"#{i}" for i in selected_ids[:8])
            if count > 8:
                id_preview += f", ... (+{count - 8} more)"
            msg = (
                f"Permanently prune {count} selected memories?\n\n"
                f"Selected IDs: {id_preview}\n\n"
                f"This will soft-delete and audit all {count} memories."
            )

        res = QMessageBox.question(
            self,
            "Confirm Pruning",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            try:
                self.facade.forget_memories(selected_ids, user_confirmed=True)
                self._current_selected_mid = None
                self.txt_inspect_content.clear()
                self._refresh_memories()
                QMessageBox.information(
                    self,
                    "Pruning Complete",
                    f"Successfully pruned {count} {'memory' if count == 1 else 'memories'}.",
                )
            except Exception as exc:
                _LOG.debug("delete_memories_failed: %s", exc)
                QMessageBox.critical(self, "Error", f"Failed to prune memories: {exc}")

    def _delete_selected_memory(self) -> None:
        """Prunes currently selected memory or memories (backward compatibility)."""
        self._delete_selected_memories()

    def _factory_reset_memories(self) -> None:
        """Permanently eradicates all memories, knowledge graphs, decisions, and rules across all stores."""
        reply = QMessageBox.warning(
            self,
            "Factory Reset & Hard Purge Confirmation",
            "⚠️ FACTORY RESET / HARD PURGE (CLEARS ALL STORES)\n\n"
            "Are you sure you want to permanently erase ALL memories, knowledge graph entities and relations, "
            "routing decisions, and induced rules across all backing stores?\n\n"
            "This action executes an atomic hard purge and CANNOT be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                pruned_count = self.facade.factory_reset_memories(user_confirmed=True)
                self._current_selected_mid = None
                self.txt_inspect_content.clear()
                self._refresh_memories()
                self._refresh_review_queue()
                QMessageBox.information(
                    self,
                    "Factory Reset Complete",
                    f"Lucca's memory and knowledge stores have been completely eradicated.\n\n"
                    f"Total purged records: {pruned_count}.",
                )
            except Exception as exc:
                _LOG.debug("factory_reset_failed: %s", exc)
                QMessageBox.critical(self, "Error", f"Failed to factory reset memories: {exc}")

    def _add_new_fact_dialog(self) -> None:
        text, ok = QInputDialog.getMultiLineText(
            self, "Teach Lucca a Fact", "Enter knowledge statement or preference:"
        )
        if ok and text.strip():
            try:
                mid = self.facade.add_memory_fact(
                    content=text.strip(),
                    importance=0.85,
                )
                self._refresh_memories()
                QMessageBox.information(
                    self, "Knowledge Stored", f"Stored fact as memory #{mid} with vector embedding."
                )
            except Exception as exc:
                _LOG.debug("add_memory_fact_failed: %s", exc)
                QMessageBox.critical(self, "Error", f"Failed to add fact: {exc}")

    def _vacuum_memory_db(self) -> None:
        try:
            self.facade.vacuum_database()
            self._refresh_memories()
            QMessageBox.information(
                self, "Vacuum Complete", "SQLite database and vector indices optimized."
            )
        except Exception as exc:
            _LOG.debug("vacuum_memory_db_failed: %s", exc)
            QMessageBox.critical(self, "Error", f"Vacuum failed: {exc}")

    def _refresh_review_queue(self) -> None:
        try:
            items = self.facade.list_review_queue(status="ALL")
            self.table_review.setRowCount(0)
            pending_count = 0
            for it in items:
                row = self.table_review.rowCount()
                self.table_review.insertRow(row)

                rid = str(it.get("review_id", ""))
                bid = str(it.get("belief_id") or "-")
                old_c = str(it.get("old_content") or "-")
                new_c = str(it.get("proposed_content", ""))
                reason = str(it.get("trigger_reason", ""))
                status = str(it.get("status", "PENDING"))
                if status == "PENDING":
                    pending_count += 1

                self.table_review.setItem(row, 0, QTableWidgetItem(rid))
                self.table_review.setItem(row, 1, QTableWidgetItem(bid))
                self.table_review.setItem(row, 2, QTableWidgetItem(old_c))
                self.table_review.setItem(row, 3, QTableWidgetItem(new_c))
                self.table_review.setItem(row, 4, QTableWidgetItem(reason))
                self.table_review.setItem(row, 5, QTableWidgetItem(status))

            self.lbl_review_count.setText(f"Pending Revisions: {pending_count}")

            # Also refresh topic dropdown
            self.combo_rev_topics.clear()
            topics = self.facade.list_review_required_topics()
            for t in topics:
                self.combo_rev_topics.addItem(t)
        except Exception as exc:
            _LOG.debug("refresh_review_queue_failed: %s", exc)
            print(f"[UI] Review queue refresh error: {exc}")

    def _approve_selected_review(self) -> None:
        row = self.table_review.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a review item to approve.")
            return
        item_id = self.table_review.item(row, 0)
        item_status = self.table_review.item(row, 5)
        if not item_id or not item_status:
            return
        review_id = item_id.text()
        if item_status.text() != "PENDING":
            QMessageBox.information(
                self, "Already Decided", f"Item '{review_id}' is already {item_status.text()}."
            )
            return
        try:
            new_mid = self.facade.approve_review(review_id, decided_by="ui-operator")
            QMessageBox.information(
                self,
                "Revision Approved",
                f"Review '{review_id}' approved. New memory ID: #{new_mid}.",
            )
            self._refresh_memories()
        except Exception as exc:
            _LOG.debug("approve_review_failed: %s", exc)
            QMessageBox.critical(self, "Error", f"Failed to approve review: {exc}")

    def _reject_selected_review(self) -> None:
        row = self.table_review.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a review item to reject.")
            return
        item_id = self.table_review.item(row, 0)
        item_status = self.table_review.item(row, 5)
        if not item_id or not item_status:
            return
        review_id = item_id.text()
        if item_status.text() != "PENDING":
            QMessageBox.information(
                self, "Already Decided", f"Item '{review_id}' is already {item_status.text()}."
            )
            return
        try:
            self.facade.reject_review(review_id, decided_by="ui-operator")
            QMessageBox.information(
                self, "Revision Rejected", f"Review '{review_id}' rejected. Old belief preserved."
            )
            self._refresh_review_queue()
        except Exception as exc:
            _LOG.debug("reject_review_failed: %s", exc)
            QMessageBox.critical(self, "Error", f"Failed to reject review: {exc}")

    def _add_review_topic(self) -> None:
        topic = self.line_new_topic.text().strip()
        if not topic:
            return
        self.facade.mark_topic_review_required(topic)
        self.line_new_topic.clear()
        self._refresh_review_queue()

    def _remove_review_topic(self) -> None:
        topic = self.combo_rev_topics.currentText().strip()
        if not topic:
            return
        self.facade.unmark_topic_review_required(topic)
        self._refresh_review_queue()
