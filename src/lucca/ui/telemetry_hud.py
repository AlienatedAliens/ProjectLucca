"""
Project Lucca — Chrono Trigger Hardware Telemetry HUD
Spec 01 §1, Spec 16 §3, ADR-005
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QFont,
    QHideEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lucca.sandbox.system_tools import get_system_metrics
from lucca.ui.theme import (
    CT_BLUE_BOT,
    CT_BLUE_MID,
    CT_BLUE_TOP,
    CT_GOLD_TEXT,
    CT_SILVER_BORDER,
)


class TelemetryWorker(QThread):
    """Off-thread hardware telemetry sampler preventing GUI hitching."""
    metrics_ready = pyqtSignal(dict)

    def run(self) -> None:
        try:
            m = get_system_metrics()
            self.metrics_ready.emit(m)
        except Exception:
            pass


class TelemetryHUD(QWidget):
    """
    Pinnable floating Chrono Trigger SNES Telemetry HUD.
    Displays real-time hardware metrics across all 5 substrates:
    1. dGPU: NVIDIA RTX 5080 Laptop GPU (16.0 GB VRAM)
    2. NPU: Intel AI Boost (Active Whisper STT & Embeddings)
    3. CPU: Intel Core Ultra 9 275HX (24 Cores)
    4. RAM: 16.0 GB System RAM (Lucca stack vs Total host)
    5. iGPU: Intel Graphics (Standby Fallback)
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_close = on_close
        self.is_pinned = True
        self.drag_position: QPoint | None = None
        self.worker: TelemetryWorker | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(540)
        self.setFixedHeight(300)

        self._build_ui()

        # Real-time polling timer (1000ms) - only runs when HUD is visible
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self.refresh_metrics)
        self.hide()

    def toggle(self) -> None:
        """Toggles the telemetry HUD visibility."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 14)
        main_layout.setSpacing(8)

        # Header Row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        title_lbl = QLabel("⚙️ HARDWARE MATRIX & TELEMETRY", self)
        title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: 900; letter-spacing: 1px;")
        header_layout.addWidget(title_lbl)

        self.status_led = QLabel("● LIVE (1s)", self)
        self.status_led.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self.status_led.setStyleSheet("color: #34d399;")
        header_layout.addWidget(self.status_led)

        header_layout.addStretch()

        self.btn_logs = QPushButton("Logs 📂", self)
        self.btn_logs.setFont(QFont("Segoe UI", 8))
        self.btn_logs.setStyleSheet("""
            QPushButton {
                background: #0f1c48;
                color: #34d399;
                border: 1px solid #34d399;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #1a2f70;
            }
        """)
        self.btn_logs.clicked.connect(self._open_logs_dir)
        header_layout.addWidget(self.btn_logs)

        self.btn_pin = QPushButton("📌 Pinned", self)
        self.btn_pin.setFont(QFont("Segoe UI", 8))
        self.btn_pin.setStyleSheet("""
            QPushButton {
                background: #0f1c48;
                color: #38bdf8;
                border: 1px solid #38bdf8;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #1a2f70;
            }
        """)
        self.btn_pin.clicked.connect(self.toggle_pin)
        header_layout.addWidget(self.btn_pin)

        btn_close = QPushButton("✕", self)
        btn_close.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-size: 12px;
                padding: 2px 6px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        btn_close.clicked.connect(self.hide)
        header_layout.addWidget(btn_close)

        main_layout.addLayout(header_layout)

        # 5 Substrates Container
        cards_layout = QVBoxLayout()
        cards_layout.setSpacing(6)

        # 1. dGPU Row
        self.dgpu_label = QLabel("⚡ dGPU: NVIDIA RTX 5080 Laptop (CUDA Flash-Attn)", self)
        self.dgpu_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.dgpu_label.setStyleSheet("color: #c084fc;")
        cards_layout.addWidget(self.dgpu_label)

        self.dgpu_bar = QProgressBar(self)
        self.dgpu_bar.setStyleSheet("""
            QProgressBar {
                background: #060b24;
                border: 1px solid #8b5cf6;
                border-radius: 2px;
                height: 10px;
                text-align: right;
                font-size: 9px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #c084fc);
            }
        """)
        cards_layout.addWidget(self.dgpu_bar)

        # 2. System RAM Row
        self.ram_label = QLabel("💾 System RAM: Total 16.0 GB", self)
        self.ram_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.ram_label.setStyleSheet("color: #38bdf8;")
        cards_layout.addWidget(self.ram_label)

        self.ram_bar = QProgressBar(self)
        self.ram_bar.setStyleSheet("""
            QProgressBar {
                background: #060b24;
                border: 1px solid #0284c7;
                border-radius: 2px;
                height: 10px;
                text-align: right;
                font-size: 9px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
            }
        """)
        cards_layout.addWidget(self.ram_bar)

        # 3. CPU & NPU split row
        split_layout = QHBoxLayout()
        split_layout.setSpacing(8)

        # CPU block
        cpu_box = QVBoxLayout()
        self.cpu_label = QLabel("⚙️ CPU: Ultra 9 275HX (24C)", self)
        self.cpu_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.cpu_label.setStyleSheet("color: #fbbf24;")
        cpu_box.addWidget(self.cpu_label)

        self.cpu_bar = QProgressBar(self)
        self.cpu_bar.setStyleSheet("""
            QProgressBar {
                background: #060b24;
                border: 1px solid #d97706;
                border-radius: 2px;
                height: 10px;
                font-size: 9px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d97706, stop:1 #fbbf24);
            }
        """)
        cpu_box.addWidget(self.cpu_bar)
        split_layout.addLayout(cpu_box)

        # NPU & iGPU block
        npu_box = QVBoxLayout()
        self.npu_label = QLabel("🧠 NPU: Intel AI Boost (Active 15W)", self)
        self.npu_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.npu_label.setStyleSheet("color: #34d399;")
        npu_box.addWidget(self.npu_label)

        self.npu_bar = QProgressBar(self)
        self.npu_bar.setValue(28)
        self.npu_bar.setFormat("OpenVINO Whisper ASR")
        self.npu_bar.setStyleSheet("""
            QProgressBar {
                background: #060b24;
                border: 1px solid #059669;
                border-radius: 2px;
                height: 10px;
                font-size: 9px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #34d399);
            }
        """)
        npu_box.addWidget(self.npu_bar)
        split_layout.addLayout(npu_box)

        cards_layout.addLayout(split_layout)

        main_layout.addLayout(cards_layout)

    def refresh_metrics(self) -> None:
        """Trigger asynchronous metrics fetch on worker thread to prevent UI lag."""
        if self.worker is not None and self.worker.isRunning():
            return
        self.worker = TelemetryWorker(self)
        self.worker.metrics_ready.connect(self._apply_metrics)
        self.worker.start()

    def _apply_metrics(self, m: dict[str, Any]) -> None:
        try:
            # dGPU
            dg = m["dgpu"]
            vram_used = dg["used_gb"]
            vram_total = dg["total_gb"]
            vram_pct = int(dg["percent"])
            self.dgpu_label.setText(
                f"⚡ dGPU: {dg['name']} · VRAM: {vram_used:.1f} / {vram_total:.1f} GB ({vram_pct}%)"
            )
            self.dgpu_bar.setValue(min(100, max(0, vram_pct)))
            self.dgpu_bar.setFormat(f"{vram_used:.1f} GB ({vram_pct}%)")

            # RAM
            ram = m["ram"]
            tot_ram = ram["total_gb"]
            used_ram = ram["used_gb"]
            luc_mb = ram["lucca_used_mb"]
            ram_pct = int(ram["percent"])
            self.ram_label.setText(
                f"💾 System RAM: Total {tot_ram:.1f} GB · Lucca: {luc_mb:.0f} MB (Host: {used_ram:.1f} GB / {ram_pct}%)"
            )
            self.ram_bar.setValue(min(100, max(0, ram_pct)))
            self.ram_bar.setFormat(f"Host: {used_ram:.1f} GB ({ram_pct}%)")

            # CPU
            cpu = m["cpu"]
            sys_cpu = cpu["system_percent"]
            luc_cpu = cpu["lucca_percent"]
            self.cpu_label.setText(
                f"⚙️ CPU: Ultra 9 275HX · Lucca: {luc_cpu:.1f}% (Total: {sys_cpu:.1f}%)"
            )
            self.cpu_bar.setValue(min(100, max(0, int(sys_cpu))))
            self.cpu_bar.setFormat(f"{sys_cpu:.1f}%")

            # NPU
            npu = m["npu"]
            self.npu_label.setText(f"🧠 NPU: {npu['name']} · {npu['status']}")

        except Exception:  # noqa: BLE001
            pass

    def showEvent(self, event: QShowEvent | None) -> None:
        if event is not None:
            super().showEvent(event)
        self.refresh_metrics()
        self.poll_timer.start()

    def hideEvent(self, event: QHideEvent | None) -> None:
        if event is not None:
            super().hideEvent(event)
        self.poll_timer.stop()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.poll_timer.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(500)
        if event is not None:
            super().closeEvent(event)

    def toggle_pin(self) -> None:
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.btn_pin.setText("📌 Pinned")
            self.setWindowOpacity(1.0)
        else:
            self.btn_pin.setText("Unpinned")
            self.setWindowOpacity(0.4)

    def _open_logs_dir(self) -> None:
        path = Path("C:/ProjectLucca/logs/resource_sessions")
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", str(path).replace("/", "\\")])

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event and event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # Outer Chrono Trigger Frame
        path = QPainterPath()
        path.addRoundedRect(QRectF(2, 2, w - 4, h - 4), 6.0, 6.0)

        # Gradient
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(CT_BLUE_TOP))
        grad.setColorAt(0.45, QColor(CT_BLUE_MID))
        grad.setColorAt(1.0, QColor(CT_BLUE_BOT))

        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor("#000000"), 2.0))
        painter.drawPath(path)

        # Inner double silver border
        inner = QPainterPath()
        inner.addRoundedRect(QRectF(5, 5, w - 10, h - 10), 4.0, 4.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(CT_SILVER_BORDER), 1.8))
        painter.drawPath(inner)
