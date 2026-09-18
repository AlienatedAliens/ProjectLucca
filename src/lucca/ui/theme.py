"""
Project Lucca — Chrono Trigger SNES Visual Design System & Global Stylesheet
Spec 01 §1, ADR-005
"""

from __future__ import annotations

# Canonical Chrono Trigger Palette Constants
CT_BLUE_TOP = "#1c2e88"
CT_BLUE_MID = "#101c54"
CT_BLUE_BOT = "#081036"
CT_SILVER_BORDER = "#f0f4ff"
CT_GOLD_TEXT = "#ffd700"
CT_CYAN_GLOW = "#38bdf8"
CT_DARK_BG = "#060b24"
CT_SUB_PANEL = "#0e1848"

CHRONO_TRIGGER_STYLE_SHEET = """
/* Global Chrono Trigger SNES Application Theme */
QWidget {
    font-family: 'Segoe UI', 'Consolas', monospace;
    color: #ffffff;
    selection-background-color: #ffd700;
    selection-color: #081036;
}

QDialog, QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1c2e88, stop:0.45 #101c54, stop:1 #081036);
    border: 2px solid #f0f4ff;
    border-radius: 6px;
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #243896, stop:1 #121e5c);
    border: 2px solid #f0f4ff;
    border-radius: 4px;
    color: #ffd700;
    font-weight: bold;
    font-size: 11px;
    padding: 5px 14px;
    outline: none;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3550c4, stop:1 #1c2e88);
    border-color: #ffd700;
    color: #ffffff;
}
QPushButton:pressed {
    background: #ffd700;
    color: #081036;
    border-color: #ffffff;
}
QPushButton:disabled {
    background: #1e2648;
    color: #64748b;
    border-color: #475569;
}

QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #060b24;
    color: #ffffff;
    border: 1.5px solid #637bb5;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 11px;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1.5px solid #ffd700;
    background-color: #091032;
}

QSpinBox, QDoubleSpinBox {
    background-color: #060b24;
    color: #ffd700;
    font-weight: bold;
    border: 1.5px solid #637bb5;
    border-radius: 4px;
    padding: 4px 6px;
    font-size: 11px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1.5px solid #ffd700;
}

QComboBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #182878, stop:1 #0c143d);
    color: #ffd700;
    font-weight: bold;
    border: 1.5px solid #637bb5;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 11px;
}
QComboBox:focus, QComboBox:hover {
    border-color: #ffd700;
}
QComboBox QAbstractItemView {
    background-color: #081036;
    color: #ffffff;
    border: 1.5px solid #ffd700;
    selection-background-color: #243896;
    selection-color: #ffd700;
    padding: 4px;
}

QTabWidget::pane {
    border: 2px solid #637bb5;
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #121f5e, stop:1 #081036);
    top: -1px;
}
QTabBar::tab {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #162464, stop:1 #0c1438);
    border: 1.5px solid #50649c;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    color: #a8b8e0;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
    margin-right: 2px;
}
QTabBar::tab:hover {
    color: #ffd700;
    border-color: #889ec8;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #283d9e, stop:1 #16256c);
    border-color: #ffd700;
    color: #ffd700;
    border-bottom: 2px solid #ffd700;
}

QSlider::groove:horizontal {
    height: 8px;
    background: #060b24;
    border: 1.5px solid #637bb5;
    border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #243896, stop:1 #38bdf8);
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffe066, stop:1 #d4a017);
    border: 1.5px solid #ffffff;
    width: 14px;
    height: 18px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 2px;
}
QSlider::handle:horizontal:hover {
    background: #ffffff;
    border-color: #ffd700;
}

QProgressBar {
    background-color: #060b24;
    border: 1.5px solid #4a5f96;
    border-radius: 3px;
    text-align: center;
    color: #ffffff;
    font-size: 10px;
    font-weight: bold;
    height: 14px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #34d399);
    border-radius: 2px;
}

QGroupBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #142268, stop:1 #0a133d);
    border: 1.5px solid #637bb5;
    border-radius: 5px;
    margin-top: 18px;
    padding-top: 14px;
    font-size: 11px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #ffd700;
    font-weight: bold;
    background-color: #081036;
    border: 1px solid #ffd700;
    border-radius: 3px;
    left: 10px;
}

QTableWidget {
    background-color: #081036;
    alternate-background-color: #0e1848;
    color: #ffffff;
    border: 1.5px solid #4a5f96;
    border-radius: 4px;
    gridline-color: #243770;
    font-size: 11px;
}
QTableWidget::item:selected {
    background-color: #243896;
    color: #ffd700;
}
QHeaderView::section {
    background-color: #121e5c;
    color: #ffd700;
    font-weight: bold;
    padding: 4px 6px;
    border: 1px solid #243770;
    font-size: 11px;
}

QMenu {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1c2e88, stop:1 #081036);
    color: #ffffff;
    border: 2px solid #f0f4ff;
    border-radius: 5px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 22px 6px 12px;
    border-radius: 3px;
    color: #dce7ff;
    font-size: 11px;
    font-weight: 500;
}
QMenu::item:selected {
    background-color: #243896;
    color: #ffd700;
}
QMenu::separator {
    height: 1px;
    background: #4a5f96;
    margin: 4px 6px;
}
"""
