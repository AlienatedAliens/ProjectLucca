"""
Project Lucca — Hotkeys & Push-To-Talk Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade


class HotkeysTab(QWidget):
    """Tab 5: Universal Push-to-Talk & Hotkey Listeners."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        grp_ptt = QGroupBox("Universal Push-to-Talk & Hotkey Listeners", self)
        f_ptt = QFormLayout(grp_ptt)

        self.combo_ptt_key = QComboBox(grp_ptt)
        self.combo_ptt_key.addItem("Alt-Gr / Right-Ctrl / Right-Shift (Universal Any)", "any")
        self.combo_ptt_key.addItem("Alt-Gr (Right Alt)", "alt_gr")
        self.combo_ptt_key.addItem("Right Control", "right_ctrl")
        self.combo_ptt_key.addItem("Right Shift", "right_shift")
        self.combo_ptt_key.addItem("Left Control", "left_ctrl")
        self.combo_ptt_key.addItem("Spacebar", "space")

        current_key = getattr(self.dialog, "current_ptt_key", "alt_gr")
        norm_key = current_key.replace("-", "_").lower() if current_key else "alt_gr"
        idx = self.combo_ptt_key.findData(norm_key)
        if idx < 0:
            idx = self.combo_ptt_key.findData(current_key)
        if idx >= 0:
            self.combo_ptt_key.setCurrentIndex(idx)
        f_ptt.addRow("Primary Push-to-Talk Key:", self.combo_ptt_key)

        self.combo_ptt_mode = QComboBox(grp_ptt)
        self.combo_ptt_mode.addItem("Hold-to-Talk (Records while key held down)", "hold")
        self.combo_ptt_mode.addItem("Toggle Mode (Press to start, press to stop)", "toggle")
        f_ptt.addRow("Hotkey Operation Mode:", self.combo_ptt_mode)

        self.spin_max_rec = QSpinBox(grp_ptt)
        self.spin_max_rec.setRange(5, 60)
        self.spin_max_rec.setValue(30)
        self.spin_max_rec.setSuffix(" seconds")
        f_ptt.addRow("Max Utterance Ceiling:", self.spin_max_rec)

        self.chk_wake_word = QCheckBox("Enable Hands-Free Local Wake Word ('Lucca')", grp_ptt)
        self.chk_wake_word.setChecked(True)
        f_ptt.addRow("Hands-Free Trigger:", self.chk_wake_word)

        layout.addWidget(grp_ptt)
        layout.addStretch()
