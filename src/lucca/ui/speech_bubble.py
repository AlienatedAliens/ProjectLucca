"""
Project Lucca — Desktop Companion Speech Bubble
Spec 01 §1, Spec 16 §3, ADR-005
"""

import os
from collections.abc import Callable
from datetime import datetime

os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.windows.warning=false")

from PyQt6.QtCore import QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
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

        self.bubble_width = 460
        self.bubble_min_height = 84
        self.setFixedWidth(self.bubble_width)

        # Bubble content
        self.current_text = ""
        self._full_text = ""
        self._char_index = 0
        self.status_text = ""
        self.source = "assistant"
        # "left" points towards sprite on left, "right" to sprite on right
        self.tail_direction = "left"

        # Typewriter Text Engine
        self.typewriter_timer = QTimer(self)
        self.typewriter_timer.setInterval(22)
        self.typewriter_timer.timeout.connect(self._on_typewriter_tick)

        # Blinking cursor indicator (▼)
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(450)
        self.cursor_timer.timeout.connect(self._toggle_cursor_blink)
        self._cursor_visible = True

        # Auto-dismiss timer (7 seconds after speech ends)
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._on_dismiss_timeout)

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 18)
        main_layout.setSpacing(6)

        # Header row: status / source indicator with Chrono Trigger Gold Nameplate & Live Clock
        header_layout = QHBoxLayout()
        self.header_label = QLabel(self)
        header_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        self.header_label.setFont(header_font)
        self.header_label.setStyleSheet(
            "color: #ffd700; background: transparent; letter-spacing: 1px;"
        )
        header_layout.addWidget(self.header_label)

        header_layout.addStretch()

        self.clock_label = QLabel(self)
        self.clock_label.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self.clock_label.setStyleSheet("color: #93c5fd; background: transparent;")
        header_layout.addWidget(self.clock_label)

        self.latency_label = QLabel("", self)
        self.latency_label.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self.latency_label.setStyleSheet("""
            QLabel {
                color: #34d399;
                background: #064e3b;
                border: 1px solid #059669;
                border-radius: 3px;
                padding: 1px 4px;
            }
        """)
        self.latency_label.hide()
        header_layout.addWidget(self.latency_label)

        main_layout.addLayout(header_layout)

        # Body: Subtitle / Speech text
        self.body_label = QLabel(self)
        body_font = QFont("Segoe UI", 11)
        self.body_label.setFont(body_font)
        self.body_label.setWordWrap(True)
        self.body_label.setStyleSheet(
            "color: #ffffff; background: transparent; line-height: 1.35; font-weight: 500;"
        )
        main_layout.addWidget(self.body_label)

        # Footer row with blinking cursor prompt
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.cursor_label = QLabel("▼", self)
        self.cursor_label.setStyleSheet(
            "color: #ffd700; font-size: 13px; font-weight: bold; background: transparent;"
        )
        self.cursor_label.hide()
        footer_layout.addWidget(self.cursor_label)
        main_layout.addLayout(footer_layout)

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
                border: 1px solid #ffffff;
                border-radius: 4px;
                padding: 4px 14px;
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
                border: 1px solid #ffffff;
                border-radius: 4px;
                padding: 4px 14px;
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

    def _on_typewriter_tick(self) -> None:
        if self._char_index < len(self._full_text):
            self._char_index += 1
            self.body_label.setText(self._full_text[: self._char_index])
            char = self._full_text[self._char_index - 1]
            if char == ",":
                self.typewriter_timer.setInterval(180)
            elif char in (".", "!", "?"):
                self.typewriter_timer.setInterval(350)
            else:
                self.typewriter_timer.setInterval(48)
        else:
            self.typewriter_timer.stop()
            self.cursor_label.show()
            self.cursor_timer.start(450)

    def _toggle_cursor_blink(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.cursor_label.setVisible(self._cursor_visible)

    def show_caption(
        self,
        text: str,
        source: str = "assistant",
        is_final: bool = False,
    ) -> None:
        """Update and display the speech bubble with audio-synchronized streaming reveal."""
        self.dismiss_timer.stop()
        self.typewriter_timer.stop()
        self.cursor_timer.stop()
        self.cursor_label.hide()
        self.confirm_widget.hide()

        # Ensure unbroken tokens (e.g. repetition loops or raw code) wrap within bubble width
        def _wrap_unbroken(s: str, max_chunk: int = 35) -> str:
            parts: list[str] = []
            for token in s.split(" "):
                if len(token) > max_chunk:
                    chunks = [token[i : i + max_chunk] for i in range(0, len(token), max_chunk)]
                    parts.append(" ".join(chunks))
                else:
                    parts.append(token)
            return " ".join(parts)

        text = _wrap_unbroken(text)
        self.source = source
        self.current_text = text
        self._full_text = text

        now_str = datetime.now().strftime("%I:%M %p")
        self.clock_label.setText(now_str)

        if source == "status":
            self.header_label.setText("STATUS")
            self.header_label.setStyleSheet(
                "color: #fab387; font-weight: bold; letter-spacing: 1px;"
            )
            self.body_label.setText(text)
            self.body_label.setStyleSheet("color: #ffd700; font-style: italic; font-weight: 500;")
            self.adjustSize()
        elif source == "user":
            self.header_label.setText("YOU")
            self.header_label.setStyleSheet(
                "color: #a6e3a1; font-weight: bold; letter-spacing: 1px;"
            )
            self.body_label.setText(f'"{text}"')
            self.body_label.setStyleSheet("color: #ffffff; font-weight: 500;")
            self.adjustSize()
        else:
            self.header_label.setText("LUCCA")
            self.header_label.setStyleSheet(
                "color: #ffd700; font-weight: 900; letter-spacing: 1.5px;"
            )
            self.body_label.setStyleSheet("color: #ffffff; font-weight: 500; line-height: 1.35;")

            # Pre-size bubble to final text dimensions before typewriter reveal
            self.body_label.setText(text)
            self.adjustSize()

            # Use progressive audio-paced reveal for Lucca's speech
            if len(text) > 4:
                self._char_index = 0
                self.body_label.setText("")
                self.typewriter_timer.setInterval(48)
                self.typewriter_timer.start()
            else:
                self.cursor_label.show()
                self.cursor_timer.start(450)

        self.show()

        if is_final:
            self.dismiss_timer.start(7000)

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

    def set_latency_ms(self, ms: float | None) -> None:
        """Set the latency badge in milliseconds, or hide it if None or non-positive."""
        if ms is not None and ms > 0:
            self.latency_label.setText(f"{ms:.0f} ms")
            self.latency_label.show()
        else:
            self.latency_label.setText("")
            self.latency_label.hide()

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
        bh = self.height()

        screen_left = int(screen_geometry.left()) if screen_geometry else 0
        screen_right = int(screen_geometry.right()) if screen_geometry else 1920
        screen_top = int(screen_geometry.top()) if screen_geometry else 0
        screen_bottom = int(screen_geometry.bottom()) if screen_geometry else 1080

        # Place to the right of sprite if there is room on screen
        target_x = sx + sw + 12
        self.tail_direction = "left"

        if target_x + bw > screen_right:
            # Flip to left side of sprite
            target_x = sx - bw - 12
            self.tail_direction = "right"

        if target_x < screen_left:
            target_x = screen_left + 10

        # Align vertically with upper third of sprite
        target_y = max(screen_top + 10, sy - 15)

        # Prevent bubble from protruding off the bottom of the screen
        if target_y + bh > screen_bottom:
            target_y = max(screen_top + 10, screen_bottom - bh - 10)

        self.move(target_x, target_y)
        self.update()

    def _on_dismiss_timeout(self) -> None:
        self.hide()

    def mousePressEvent(self, event: object) -> None:
        # Natural audio-paced streaming text cannot be skipped by clicking
        if not self.typewriter_timer.isActive():
            self.hide()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # Outer box path
        rect_path = QPainterPath()
        corner_radius = 8.0
        rect_path.addRoundedRect(QRectF(3, 3, w - 6, h - 8), corner_radius, corner_radius)

        # Tail pointing towards avatar
        tail_path = QPainterPath()
        if self.tail_direction == "left":
            tail_y = min(h - 22.0, 32.0)
            tail_path.moveTo(4.0, tail_y)
            tail_path.lineTo(0.0, tail_y + 8.0)
            tail_path.lineTo(4.0, tail_y + 16.0)
        else:
            tail_y = min(h - 22.0, 32.0)
            tail_path.moveTo(w - 4.0, tail_y)
            tail_path.lineTo(w, tail_y + 8.0)
            tail_path.lineTo(w - 4.0, tail_y + 16.0)

        combined = rect_path.united(tail_path)

        # Drop shadow for elevation
        shadow_color = QColor(0, 0, 0, 160)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow_color))
        painter.drawPath(combined.translated(3, 3))

        # Authentic Chrono Trigger Royal Blue gradient fill
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#1c2e88"))
        grad.setColorAt(0.45, QColor("#101c54"))
        grad.setColorAt(1.0, QColor("#081036"))

        painter.setBrush(QBrush(grad))
        # Outer dark border
        painter.setPen(QPen(QColor("#000000"), 2.0))
        painter.drawPath(combined)

        # Inner double-beveled silver-white highlight frame
        inner_path = QPainterPath()
        inner_path.addRoundedRect(QRectF(6, 6, w - 12, h - 14), 5.0, 5.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#f0f4ff"), 1.8))
        painter.drawPath(inner_path)

        # Subtle gold accent line on top border
        painter.setPen(QPen(QColor("#ffd700"), 1.0))
        painter.drawLine(10, 7, int(w - 10), 7)
