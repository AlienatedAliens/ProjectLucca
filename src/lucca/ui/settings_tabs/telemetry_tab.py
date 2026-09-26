"""
Project Lucca — Telemetry & Live Session Logs Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lucca.core.config import get_config
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = structlog.get_logger(__name__)


class TelemetryTab(QWidget):
    """Tab 8: Telemetry & Live Session Logs."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Live Substrate Snapshot
        grp_snap = QGroupBox("Live Host Computing Substrates (1000ms Polling)", self)
        h_snap = QHBoxLayout(grp_snap)
        self.lbl_snap_dgpu = QLabel("dGPU: RTX 5080 (16 GB)", grp_snap)
        self.lbl_snap_npu = QLabel("NPU: AI Boost", grp_snap)
        self.lbl_snap_cpu = QLabel("CPU: Ultra 9 275HX", grp_snap)
        self.lbl_snap_ram = QLabel("RAM: 16 GB Total", grp_snap)
        self.lbl_snap_dgpu.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.lbl_snap_npu.setStyleSheet("color: #58d68d; font-weight: bold;")
        self.lbl_snap_cpu.setStyleSheet("color: #f39c12; font-weight: bold;")
        self.lbl_snap_ram.setStyleSheet("color: #38bdf8; font-weight: bold;")
        h_snap.addWidget(self.lbl_snap_dgpu)
        h_snap.addWidget(self.lbl_snap_npu)
        h_snap.addWidget(self.lbl_snap_cpu)
        h_snap.addWidget(self.lbl_snap_ram)
        h_snap.addStretch()

        btn_refresh_snap = QPushButton("🔄 Refresh Snapshot", grp_snap)
        btn_refresh_snap.clicked.connect(self._refresh_diag_snapshot)
        h_snap.addWidget(btn_refresh_snap)
        layout.addWidget(grp_snap)

        # Embedded Session Telemetry Log Viewer
        grp_logs = QGroupBox("Session Telemetry Log Viewer & Progression History", self)
        v_logs = QVBoxLayout(grp_logs)

        h_log_ctrl = QHBoxLayout()
        h_log_ctrl.addWidget(QLabel("Session Log File:", grp_logs))
        self.combo_log_files = QComboBox(grp_logs)
        self.combo_log_files.currentIndexChanged.connect(self._load_selected_log_file)
        h_log_ctrl.addWidget(self.combo_log_files, stretch=2)

        self.btn_refresh_logs = QPushButton("🔄 Reload File", grp_logs)
        self.btn_refresh_logs.clicked.connect(self._scan_and_reload_logs)
        h_log_ctrl.addWidget(self.btn_refresh_logs)

        self.chk_auto_tail = QCheckBox("▶ Auto-Tail Live (1s)", grp_logs)
        self.chk_auto_tail.setChecked(True)
        h_log_ctrl.addWidget(self.chk_auto_tail)

        btn_open_folder = QPushButton("📁 Open Logs Directory", grp_logs)
        btn_open_folder.clicked.connect(self._open_logs_dir)
        h_log_ctrl.addWidget(btn_open_folder)

        v_logs.addLayout(h_log_ctrl)

        # Dual View Tabs: Parsed Table vs Raw JSONL
        self.tabs_log_view = QTabWidget(grp_logs)

        # Tab A: Parsed Metrics Table
        self.table_logs = QTableWidget(0, 6, grp_logs)
        self.table_logs.setHorizontalHeaderLabels(
            [
                "Timestamp",
                "Host RAM %",
                "Lucca RSS (MB)",
                "dGPU VRAM (Used / Total)",
                "CPU % (Host / Lucca)",
                "NPU Status",
            ]
        )
        hdr_logs = self.table_logs.horizontalHeader()
        if hdr_logs is not None:
            hdr_logs.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr_logs.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabs_log_view.addTab(self.table_logs, "📊 Parsed Telemetry Table")

        # Tab B: Raw JSONL Log Viewer
        self.txt_raw_log = QPlainTextEdit(grp_logs)
        self.txt_raw_log.setReadOnly(True)
        self.txt_raw_log.setFont(QFont("Consolas", 9))
        self.tabs_log_view.addTab(self.txt_raw_log, "📄 Raw JSONL Text")

        v_logs.addWidget(self.tabs_log_view)
        layout.addWidget(grp_logs)

        # Auto-tail timer (only active when Tab 8 is visible)
        self.log_tail_timer = QTimer(self)
        self.log_tail_timer.setInterval(1000)
        self.log_tail_timer.timeout.connect(self._on_log_tail_tick)
        self.log_tail_timer.start()

    def _refresh_diag_snapshot(self) -> None:
        try:
            m = self.facade.get_system_metrics()
            ram = m["ram"]
            dgpu = m["dgpu"]
            cpu = m["cpu"]
            npu = m["npu"]

            self.lbl_snap_ram.setText(
                f"RAM: {ram['percent']}% (Lucca {ram.get('lucca_used_mb', 0):.0f} MB)"
            )
            self.lbl_snap_dgpu.setText(
                f"dGPU: {dgpu.get('used_gb', 0):.1f} / {dgpu.get('total_gb', 16.0):.1f} GB"
            )
            self.lbl_snap_cpu.setText(
                f"CPU: {cpu['system_percent']:.1f}% (Lucca {cpu['lucca_percent']:.1f}%)"
            )
            self.lbl_snap_npu.setText(f"NPU: {npu['status'].split(' ')[0]}")
        except Exception as exc:
            _LOG.debug("refresh_diag_snapshot_failed: %s", exc)

    def _scan_and_reload_logs(self) -> None:
        log_dir = Path("C:/ProjectLucca/logs/resource_sessions")
        log_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(list(log_dir.glob("*.jsonl")), reverse=True)

        current = self.combo_log_files.currentData()
        self.combo_log_files.blockSignals(True)
        self.combo_log_files.clear()
        for f in files:
            size_kb = round(f.stat().st_size / 1024, 1)
            self.combo_log_files.addItem(f"{f.name} ({size_kb} KB)", str(f))

        # Check general traces as fallback
        traces_file = Path("C:/ProjectLucca/logs/traces.jsonl")
        if traces_file.exists():
            self.combo_log_files.addItem(
                f"traces.jsonl ({round(traces_file.stat().st_size / 1024, 1)} KB)", str(traces_file)
            )

        if current:
            idx = self.combo_log_files.findData(current)
            if idx >= 0:
                self.combo_log_files.setCurrentIndex(idx)
        self.combo_log_files.blockSignals(False)

        self._load_selected_log_file()

    def _load_selected_log_file(self) -> None:
        path_str = self.combo_log_files.currentData()
        if not path_str or not Path(path_str).exists():
            return

        try:
            text = Path(path_str).read_text(encoding="utf-8")
            self.txt_raw_log.setPlainText(text)

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            self.table_logs.setRowCount(0)

            # Show last 50 entries
            for line in lines[-50:]:
                try:
                    data = json.loads(line)
                    ts = data.get("timestamp", "")
                    if "T" in ts:
                        ts = ts.split("T")[1].split(".")[0]

                    ram = data.get("ram", {})
                    dgpu = data.get("dgpu", {})
                    cpu = data.get("cpu", {})
                    npu = data.get("npu", {})

                    row = self.table_logs.rowCount()
                    self.table_logs.insertRow(row)
                    self.table_logs.setItem(row, 0, QTableWidgetItem(ts))
                    self.table_logs.setItem(
                        row, 1, QTableWidgetItem(f"{ram.get('percent', 0):.1f}%")
                    )
                    self.table_logs.setItem(
                        row,
                        2,
                        QTableWidgetItem(
                            f"{ram.get('lucca_rss_mb', ram.get('lucca_used_mb', 0)):.0f} MB"
                        ),
                    )
                    self.table_logs.setItem(
                        row,
                        3,
                        QTableWidgetItem(
                            f"{dgpu.get('used_vram_gb', dgpu.get('used_gb', 0)):.1f} / {dgpu.get('total_vram_gb', dgpu.get('total_gb', 16.0)):.1f} GB"
                        ),
                    )
                    self.table_logs.setItem(
                        row,
                        4,
                        QTableWidgetItem(
                            f"{cpu.get('system_percent', 0):.1f}% / {cpu.get('lucca_percent', 0):.1f}%"
                        ),
                    )
                    self.table_logs.setItem(
                        row, 5, QTableWidgetItem(str(npu.get("status", "Active")))
                    )
                except Exception as exc:
                    _LOG.debug("parse_log_line_failed: %s", exc)

            self.table_logs.scrollToBottom()
        except Exception as exc:
            _LOG.debug("load_selected_log_file_failed: %s", exc)
            self.txt_raw_log.setPlainText(f"Error loading log file: {exc}")

    def _on_log_tail_tick(self) -> None:
        tabs = getattr(self.dialog, "tabs", None)
        is_active_tab = (tabs is not None and tabs.currentIndex() == 8)
        if self.chk_auto_tail.isChecked() and self.isVisible() and is_active_tab:
            self._refresh_diag_snapshot()
            self._load_selected_log_file()

    def _open_logs_dir(self) -> None:
        app_cfg = getattr(self.dialog, "app_config", None)
        home = app_cfg.home_dir if app_cfg else get_config().home_dir
        path = home / "logs" / "resource_sessions"
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", str(path)])  # noqa: S603, S607
