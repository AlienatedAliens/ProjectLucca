"""
Project Lucca — Desktop Companion Quick Chat Bar
Spec 01 §1, Spec 16 §3, ADR-005
"""

from collections.abc import Callable

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


class QuickChatBar(QWidget):
    """
    Floating desktop text input bar allowing manual typing to Lucca
    as an alternative or companion to voice PTT.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        on_send_text: Callable[[str], None] | None = None,
        on_ptt_press: Callable[[], None] | None = None,
        on_ptt_release: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_send_text = on_send_text
        self.on_ptt_press = on_ptt_press
        self.on_ptt_release = on_ptt_release

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setFixedWidth(360)
        self.setFixedHeight(48)

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        # Input line edit
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Type a command or message to Lucca...")
        self.input_field.setFont(QFont("Segoe UI", 10))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #11111b;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px 10px;
                selection-background-color: #89b4fa;
                selection-color: #11111b;
            }
            QLineEdit:focus {
                border: 1px solid #89b4fa;
            }
        """)
        self.input_field.returnPressed.connect(self._handle_submit)
        layout.addWidget(self.input_field)

        # Send button
        self.btn_send = QPushButton("Send", self)
        self.btn_send.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
                border-radius: 6px;
                padding: 5px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
        """)
        self.btn_send.clicked.connect(self._handle_submit)
        layout.addWidget(self.btn_send)

        # Mouse PTT button ("Hold to Talk")
        self.btn_talk = QPushButton("🎙️", self)
        self.btn_talk.setToolTip("Click and hold to talk")
        self.btn_talk.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #a6e3a1;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #a6e3a1;
            }
            QPushButton:pressed {
                background-color: #a6e3a1;
                color: #11111b;
            }
        """)
        self.btn_talk.pressed.connect(self._on_talk_pressed)
        self.btn_talk.released.connect(self._on_talk_released)
        layout.addWidget(self.btn_talk)

        # Close button
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setToolTip("Close chat bar")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #6c7086;
                border: none;
                font-size: 11px;
                padding: 2px 4px;
            }
            QPushButton:hover {
                color: #f38ba8;
            }
        """)
        self.btn_close.clicked.connect(self.hide)
        layout.addWidget(self.btn_close)

    def _handle_submit(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        if self.on_send_text:
            self.on_send_text(text)

    def _on_talk_pressed(self) -> None:
        if self.on_ptt_press:
            self.on_ptt_press()

    def _on_talk_released(self) -> None:
        if self.on_ptt_release:
            self.on_ptt_release()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event and event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.input_field.setFocus()

    def anchor_to(self, sprite_geometry: QRect | QRectF | None) -> None:
        """Reposition input bar directly beneath the companion sprite."""
        if sprite_geometry is None:
            return

        sx = int(sprite_geometry.x())
        sy = int(sprite_geometry.y())
        sw = int(sprite_geometry.width())
        sh = int(sprite_geometry.height())

        bar_w = self.width()

        # Center horizontally under sprite
        target_x = sx + (sw // 2) - (bar_w // 2)
        target_y = sy + sh + 8

        self.move(target_x, target_y)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # Dark container background
        bg_color = QColor("#181825")
        bg_color.setAlpha(245)

        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, w - 2, h - 2), 10.0, 10.0)

        # Shadow
        shadow_color = QColor(0, 0, 0, 90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow_color)
        painter.drawPath(path.translated(2, 2))

        # Fill & border
        painter.setBrush(bg_color)
        painter.setPen(QPen(QColor("#45475a"), 1.2))
        painter.drawPath(path)
