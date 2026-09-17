"""
Project Lucca — Desktop Companion Speech Bubble
Spec 01 §1, Spec 16 §3, ADR-005
"""

from collections.abc import Callable

from PyQt6.QtCore import QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SpeechBubble(QWidget):
    """
    Floating, frameless, translucent speech bubble widget anchored to CompanionSprite.
    Displays live subtitles, user inputs, listening/thinking indicators,
    and interactive confirmation action buttons.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        on_confirm: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_confirm = on_confirm

        # Window flags for transparent floating overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.bubble_width = 340
        self.bubble_min_height = 80
        self.setFixedWidth(self.bubble_width)

        # Bubble content
        self.current_text = ""
        self.status_text = ""
        self.source = "assistant"
        # "left" points towards sprite on left, "right" to sprite on right
        self.tail_direction = "left"

        # Auto-dismiss timer (6 seconds after speech ends)
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._on_dismiss_timeout)

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 20)
        main_layout.setSpacing(6)

        # Header: status / source indicator
        self.header_label = QLabel(self)
        header_font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        self.header_label.setFont(header_font)
        self.header_label.setStyleSheet("color: #89b4fa; background: transparent;")
        main_layout.addWidget(self.header_label)

        # Body: Subtitle / Speech text
        self.body_label = QLabel(self)
        body_font = QFont("Segoe UI", 11)
        self.body_label.setFont(body_font)
        self.body_label.setWordWrap(True)
        self.body_label.setStyleSheet("color: #cdd6f4; background: transparent; line-height: 1.3;")
        main_layout.addWidget(self.body_label)

        # Interactive confirmation buttons container (hidden by default)
        self.confirm_widget = QWidget(self)
        self.confirm_widget.setStyleSheet("background: transparent;")
        confirm_layout = QHBoxLayout(self.confirm_widget)
        confirm_layout.setContentsMargins(0, 4, 0, 0)
        confirm_layout.setSpacing(8)

        self.btn_yes = QPushButton("✓ Yes, proceed", self.confirm_widget)
        self.btn_yes.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #11111b;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #94e2d5;
            }
        """)
        self.btn_yes.clicked.connect(lambda: self._handle_confirmation(True))
        confirm_layout.addWidget(self.btn_yes)

        self.btn_no = QPushButton("✕ Cancel", self.confirm_widget)
        self.btn_no.setStyleSheet("""
            QPushButton {
                background-color: #f38ba8;
                color: #11111b;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #eba0ac;
            }
        """)
        self.btn_no.clicked.connect(lambda: self._handle_confirmation(False))
        confirm_layout.addWidget(self.btn_no)

        confirm_layout.addStretch()
        self.confirm_widget.hide()
        main_layout.addWidget(self.confirm_widget)

    def show_caption(
        self,
        text: str,
        source: str = "assistant",
        is_final: bool = False,
    ) -> None:
        """Update and display the speech bubble with text."""
        self.dismiss_timer.stop()
        self.confirm_widget.hide()
        self.source = source
        self.current_text = text

        if source == "status":
            self.header_label.setText("STATUS")
            self.header_label.setStyleSheet("color: #f9e2af; font-weight: bold;")
            self.body_label.setText(text)
            self.body_label.setStyleSheet("color: #fab387; font-style: italic;")
        elif source == "user":
            self.header_label.setText("YOU")
            self.header_label.setStyleSheet("color: #a6e3a1; font-weight: bold;")
            self.body_label.setText(f'"{text}"')
            self.body_label.setStyleSheet("color: #cdd6f4;")
        else:
            self.header_label.setText("LUCCA")
            self.header_label.setStyleSheet("color: #89b4fa; font-weight: bold;")
            self.body_label.setText(text)
            self.body_label.setStyleSheet("color: #cdd6f4;")

        self.adjustSize()
        self.show()

        if is_final:
            # Auto-dismiss after 6 seconds
            self.dismiss_timer.start(6000)

    def show_confirmation(self, prompt: str, summary: str = "") -> None:
        """Display an interactive confirmation prompt with Yes/No buttons."""
        self.dismiss_timer.stop()
        self.header_label.setText("CONFIRM ACTION ⚠️")
        self.header_label.setStyleSheet("color: #f38ba8; font-weight: bold;")
        display_text = prompt
        if summary:
            display_text += f"\n({summary})"
        self.body_label.setText(display_text)
        self.body_label.setStyleSheet("color: #cdd6f4; font-weight: 500;")
        self.confirm_widget.show()
        self.adjustSize()
        self.show()

    def _handle_confirmation(self, accepted: bool) -> None:
        self.confirm_widget.hide()
        self.header_label.setText("DECISION RECORDED")
        status = "Accepted ✓" if accepted else "Cancelled ✕"
        self.body_label.setText(f"Action {status}")
        self.dismiss_timer.start(2500)
        if self.on_confirm:
            self.on_confirm(accepted)

    def anchor_to(
        self,
        sprite_geometry: QRect | QRectF | None,
        screen_geometry: QRect | QRectF | None = None,
    ) -> None:
        """Reposition the bubble relative to the companion sprite."""
        if sprite_geometry is None:
            return

        sx = int(sprite_geometry.x())
        sy = int(sprite_geometry.y())
        sw = int(sprite_geometry.width())

        bw = self.width()

        # Place to the right of sprite if there is room on screen
        target_x = sx + sw + 12
        self.tail_direction = "left"

        if screen_geometry and target_x + bw > screen_geometry.width():
            # Flip to left side of sprite
            target_x = sx - bw - 12
            self.tail_direction = "right"

        # Align vertically with upper third of sprite
        target_y = max(10, sy - 15)

        self.move(target_x, target_y)
        self.update()

    def _on_dismiss_timeout(self) -> None:
        self.hide()

    def mousePressEvent(self, event: object) -> None:
        # Click on bubble dismisses it immediately
        self.hide()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # Bubble background: dark slate with 92% opacity
        bg_color = QColor("#181825")
        bg_color.setAlpha(240)

        # Border color based on source
        if self.source == "status":
            border_color = QColor("#fab387")
        elif self.source == "user":
            border_color = QColor("#a6e3a1")
        elif self.confirm_widget.isVisible():
            border_color = QColor("#f38ba8")
        else:
            border_color = QColor("#89b4fa")

        # Main rounded rectangle
        rect_path = QPainterPath()
        corner_radius = 12.0
        rect_path.addRoundedRect(QRectF(2, 2, w - 4, h - 10), corner_radius, corner_radius)

        # Draw tail pointing to Lucca
        tail_path = QPainterPath()
        if self.tail_direction == "left":
            tail_y = min(h - 18.0, 32.0)
            tail_path.moveTo(4.0, tail_y)
            tail_path.lineTo(0.0, tail_y + 8.0)
            tail_path.lineTo(4.0, tail_y + 16.0)
        else:
            tail_y = min(h - 18.0, 32.0)
            tail_path.moveTo(w - 4.0, tail_y)
            tail_path.lineTo(w, tail_y + 8.0)
            tail_path.lineTo(w - 4.0, tail_y + 16.0)

        combined = rect_path.united(tail_path)

        # Subtle shadow / glow
        shadow_color = QColor(0, 0, 0, 80)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow_color))
        painter.drawPath(combined.translated(2, 2))

        # Fill bubble
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.5))
        painter.drawPath(combined)
