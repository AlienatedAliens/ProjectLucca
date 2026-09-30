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


import structlog

logger = structlog.get_logger(__name__)


class QuickChatBar(QWidget):
    """
    Floating desktop text input bar allowing manual typing to Lucca
    as an alternative or companion to voice PTT, with direct screenshot attachment.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        on_send_text: Callable[[str], None] | None = None,
        on_send_message: Callable[[str, str | None], None] | None = None,
        on_ptt_press: Callable[[], None] | None = None,
        on_ptt_release: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_send_text = on_send_text
        self.on_send_message = on_send_message
        self.on_ptt_press = on_ptt_press
        self.on_ptt_release = on_ptt_release

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setFixedWidth(460)
        self.setFixedHeight(50)
        self._is_recording = False
        self.attached_image_b64: str | None = None

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # Camera / Screen Capture button
        self.btn_camera = QPushButton("📷", self)
        self.btn_camera.setToolTip("Capture active screen / attach image to prompt")
        self.btn_camera.setStyleSheet("""
            QPushButton {
                background-color: #1a2860;
                color: #ffd700;
                border: 1px solid #4a62a8;
                border-radius: 5px;
                padding: 5px 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #243884;
                border-color: #ffd700;
            }
        """)
        self.btn_camera.clicked.connect(self._on_capture_screen)
        layout.addWidget(self.btn_camera)

        # Image Attachment Chip (Hidden until image captured)
        self.btn_chip = QPushButton("🖼️ Screen ✕", self)
        self.btn_chip.setToolTip("Click to remove attached screen capture")
        self.btn_chip.setStyleSheet("""
            QPushButton {
                background-color: #314278;
                color: #ffd700;
                border: 1px solid #ffd700;
                border-radius: 4px;
                padding: 4px 7px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a1525;
                color: #ff6b6b;
                border-color: #ff6b6b;
            }
        """)
        self.btn_chip.clicked.connect(self._clear_attached_image)
        self.btn_chip.hide()
        layout.addWidget(self.btn_chip)

        # Input line edit with Chrono Trigger deep blue styling
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Message Lucca or press 🎙️ to talk...")
        self.input_field.setFont(QFont("Segoe UI", 10))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #0c1432;
                color: #ffffff;
                border: 1px solid #314278;
                border-radius: 5px;
                padding: 5px 10px;
                selection-background-color: #ffd700;
                selection-color: #000000;
            }
            QLineEdit:focus {
                border: 1px solid #ffd700;
            }
        """)
        self.input_field.returnPressed.connect(self._handle_submit)
        layout.addWidget(self.input_field)

        # Send button with SNES gold styling
        self.btn_send = QPushButton("Send", self)
        self.btn_send.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #ffd700;
                color: #081036;
                border: 1px solid #ffffff;
                border-radius: 5px;
                padding: 5px 12px;
                font-weight: 900;
            }
            QPushButton:hover {
                background-color: #ffe44d;
            }
            QPushButton:pressed {
                background-color: #e6c200;
            }
        """)
        self.btn_send.clicked.connect(self._handle_submit)
        layout.addWidget(self.btn_send)

        # Mouse PTT button with toggle recording state
        self.btn_talk = QPushButton("🎙️", self)
        self.btn_talk.setToolTip("Click to talk (Toggle recording)")
        self.btn_talk.setStyleSheet("""
            QPushButton {
                background-color: #1a2860;
                color: #58d68d;
                border: 1px solid #4a62a8;
                border-radius: 5px;
                padding: 5px 9px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #243884;
                border-color: #ffd700;
            }
        """)
        self.btn_talk.clicked.connect(self._toggle_talk)
        layout.addWidget(self.btn_talk)

        # Close button
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setToolTip("Close chat bar")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #8892b0;
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

    def _toggle_talk(self) -> None:
        if not self._is_recording:
            self._is_recording = True
            self.btn_talk.setText("⏹️")
            self.btn_talk.setToolTip("Recording audio... Click to send!")
            self.btn_talk.setStyleSheet("""
                QPushButton {
                    background-color: #e63946;
                    color: #ffffff;
                    border: 1px solid #ffffff;
                    border-radius: 5px;
                    padding: 5px 9px;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)
            if self.on_ptt_press:
                self.on_ptt_press()
        else:
            self._is_recording = False
            self.btn_talk.setText("🎙️")
            self.btn_talk.setToolTip("Click to talk (Toggle recording)")
            self.btn_talk.setStyleSheet("""
                QPushButton {
                    background-color: #1a2860;
                    color: #58d68d;
                    border: 1px solid #4a62a8;
                    border-radius: 5px;
                    padding: 5px 9px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #243884;
                    border-color: #ffd700;
                }
            """)
            if self.on_ptt_release:
                self.on_ptt_release()

    def set_recording_state(self, is_rec: bool) -> None:
        if self._is_recording != is_rec:
            self._toggle_talk()

    def _on_capture_screen(self) -> None:
        try:
            from lucca.core.studio_facade import StudioFacade  # noqa: PLC0415

            b64, w, _ = StudioFacade.capture_screenshot()
            self.attached_image_b64 = b64
            self.btn_chip.setText(f"🖼️ {w}px ✕")
            self.btn_chip.show()
            self.input_field.setPlaceholderText("Ask Lucca about this screen, or hit Send...")
            self.input_field.setFocus()
        except Exception as exc:  # noqa: BLE001
            logger.debug("chat_bar_screen_capture_failed", error=str(exc))

    def _clear_attached_image(self) -> None:
        self.attached_image_b64 = None
        self.btn_chip.hide()
        self.input_field.setPlaceholderText("Message Lucca or press 🎙️ to talk...")

    def _handle_submit(self) -> None:
        text = self.input_field.text().strip()
        img = self.attached_image_b64
        if not text and not img:
            return
        if not text and img:
            text = "Describe what you see on my screen."
        self._clear_attached_image()
        self.input_field.clear()
        if self.on_send_message:
            self.on_send_message(text, img)
        elif self.on_send_text:
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
