"""
Project Lucca — Episodic & Semantic Memory Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
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

        # Memory Table
        self.table_mem = QTableWidget(0, 6, grp_filter)
        self.table_mem.setHorizontalHeaderLabels(
            ["ID", "Kind", "Content / Fact Statement", "Importance", "Provenance", "Created At"]
        )
        hdr_mem = self.table_mem.horizontalHeader()
        if hdr_mem is not None:
            hdr_mem.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_mem.cellClicked.connect(self._on_memory_selected)
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

        btn_save_mem = QPushButton("💾 Save Changes", grp_inspect)
        btn_save_mem.clicked.connect(self._save_memory_changes)
        h_edit_act.addWidget(btn_save_mem)

        btn_del_mem = QPushButton("🗑️ Prune Memory", grp_inspect)
        btn_del_mem.clicked.connect(self._delete_selected_memory)
        h_edit_act.addWidget(btn_del_mem)

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

        try:
            mems = self.facade.list_memories(search=search)
            if kind_filter:
                mems = [m for m in mems if m.get("kind") == kind_filter]

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
        except Exception as exc:
            _LOG.debug("refresh_memories_failed: %s", exc)
            print(f"[UI] Memory refresh error: {exc}")

    def _on_memory_selected(self, row: int, col: int) -> None:
        item = self.table_mem.item(row, 0)
        if not item:
            return
        try:
            mid = int(item.text())
            self._current_selected_mid = mid
            content_item = self.table_mem.item(row, 2)
            imp_item = self.table_mem.item(row, 3)
            prov_item = self.table_mem.item(row, 4)

            self.lbl_inspect_id.setText(f"Memory ID: #{mid}")
            self.lbl_inspect_prov.setText(
                f"Provenance: {prov_item.text() if prov_item else 'Unknown'}"
            )
            if content_item:
                self.txt_inspect_content.setPlainText(content_item.text())
            if imp_item:
                val = int(float(imp_item.text()) * 100)
                self.slider_inspect_imp.setValue(val)
        except Exception as exc:
            _LOG.debug("select_memory_failed: %s", exc)

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

    def _delete_selected_memory(self) -> None:
        if self._current_selected_mid is None:
            return
        res = QMessageBox.question(
            self, "Confirm Deletion", f"Permanently prune memory #{self._current_selected_mid}?"
        )
        if res == QMessageBox.StandardButton.Yes:
            try:
                self.facade.forget_memory(self._current_selected_mid, user_confirmed=True)
                self._current_selected_mid = None
                self.txt_inspect_content.clear()
                self._refresh_memories()
            except Exception as exc:
                _LOG.debug("delete_memory_failed: %s", exc)
                QMessageBox.critical(self, "Error", f"Failed to delete memory: {exc}")

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
