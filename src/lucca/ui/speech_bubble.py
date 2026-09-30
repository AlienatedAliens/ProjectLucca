"""
Project Lucca — Desktop Companion Speech Bubble
Spec 01 §1, Spec 16 §3, ADR-005
Chrono Trigger Classic Dialogue Box with 5-Line Bounded Paginated Engine
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime

os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.windows.warning=false")

from PyQt6.QtCore import QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QTextLayout,
)
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
    Displays bounded 5-line paginated dialogue, user inputs, status indicators,
    and interactive confirmation action buttons. Persistent with page navigation controls.
    """

    BUBBLE_WIDTH: int = 460
    BUBBLE_HEIGHT: int = 188
    MAX_LINES_PER_PAGE: int = 5

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

        # Fixed rock-solid dimensions to prevent Win32 High-DPI setGeometry thrashing
        self.bubble_width = self.BUBBLE_WIDTH
        self.bubble_min_height = self.BUBBLE_HEIGHT
        self.setFixedSize(self.BUBBLE_WIDTH, self.BUBBLE_HEIGHT)

        # Bubble content and pagination state
        self.current_text: str = ""
        self._full_text: str = ""
        self.status_text: str = ""
        self.source: str = "assistant"
        self.tail_direction: str = "left"

        self.pages: list[str] = [""]
        self.current_page_idx: int = 0
        self._user_navigated: bool = False

        # Blinking cursor indicator (▼)
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(450)
        self.cursor_timer.timeout.connect(self._toggle_cursor_blink)
        self._cursor_visible = True

        # Dismiss timer only used for brief confirmation result feedback
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._on_dismiss_timeout)

        # Typewriter timer preserved for backwards compatibility with tests
        self.typewriter_timer = QTimer(self)
        self.typewriter_timer.setInterval(22)

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 12, 18, 12)
        main_layout.setSpacing(4)

        # Header row: status / source indicator, live clock, latency badge, and close button
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

        # Subtle close button (✕)
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setFixedSize(18, 18)
        self.btn_close.setToolTip("Dismiss speech bubble")
        self.btn_close.setStyleSheet("""
            QPushButton {
                color: #94a3b8;
                background: transparent;
                border: none;
                font-size: 11px;
                font-weight: bold;
                border-radius: 3px;
                padding: 0px;
            }
            QPushButton:hover {
                color: #f87171;
                background: rgba(239, 68, 68, 0.2);
            }
        """)
        self.btn_close.clicked.connect(self.hide)
        header_layout.addWidget(self.btn_close)

        main_layout.addLayout(header_layout)

        # Body: Subtitle / Speech text (bounded to exactly 5 lines height)
        self.body_label = QLabel(self)
        self.body_font = QFont("Segoe UI", 11)
        self.body_label.setFont(self.body_font)
        self.body_label.setWordWrap(True)
        self.body_label.setFixedHeight(106)
        self.body_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body_label.setStyleSheet(
            "color: #ffffff; background: transparent; line-height: 1.35; font-weight: 500;"
        )
        main_layout.addWidget(self.body_label)

        # Footer row with pager navigation controls (◀ [ 1 / 3 ] ▶) and status cursor
        self.footer_widget = QWidget(self)
        self.footer_widget.setStyleSheet("background: transparent;")
        footer_layout = QHBoxLayout(self.footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(6)

        # Subtle pager controls
        self.btn_prev = QPushButton("◀", self.footer_widget)
        self.btn_prev.setFixedSize(22, 18)
        self.btn_prev.setToolTip("Previous page")
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background: #101c54;
                color: #ffd700;
                border: 1px solid #3b82f6;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: #1e3a8a;
                border-color: #ffd700;
            }
            QPushButton:disabled {
                background: #081036;
                color: #475569;
                border-color: #1e293b;
            }
        """)
        self.btn_prev.clicked.connect(self._prev_page)
        footer_layout.addWidget(self.btn_prev)

        self.lbl_page = QLabel("[ 1 / 1 ]", self.footer_widget)
        self.lbl_page.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.lbl_page.setStyleSheet("color: #ffd700; background: transparent;")
        footer_layout.addWidget(self.lbl_page)

        self.btn_next = QPushButton("▶", self.footer_widget)
        self.btn_next.setFixedSize(22, 18)
        self.btn_next.setToolTip("Next page")
        self.btn_next.setStyleSheet("""
            QPushButton {
                background: #101c54;
                color: #ffd700;
                border: 1px solid #3b82f6;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: #1e3a8a;
                border-color: #ffd700;
            }
            QPushButton:disabled {
                background: #081036;
                color: #475569;
                border-color: #1e293b;
            }
        """)
        self.btn_next.clicked.connect(self._next_page)
        footer_layout.addWidget(self.btn_next)

        footer_layout.addStretch()

        self.cursor_label = QLabel("▼", self.footer_widget)
        self.cursor_label.setStyleSheet(
            "color: #ffd700; font-size: 12px; font-weight: bold; background: transparent;"
        )
        self.cursor_label.hide()
        footer_layout.addWidget(self.cursor_label)

        main_layout.addWidget(self.footer_widget)

        # Interactive confirmation buttons container (hidden by default)
        self.confirm_widget = QWidget(self)
        self.confirm_widget.setStyleSheet("background: transparent;")
        confirm_layout = QHBoxLayout(self.confirm_widget)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
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

    def _paginate(self, text: str) -> list[str]:
        """Paginates text into discrete pages of at most MAX_LINES_PER_PAGE lines."""
        if not text.strip():
            return [text] if text else [""]

        content_width = self.BUBBLE_WIDTH - 44
        paragraphs = text.split("\n")
        all_lines: list[str] = []

        for para in paragraphs:
            if not para.strip():
                all_lines.append("")
                continue
            layout = QTextLayout(para, self.body_font)
            layout.beginLayout()
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(content_width)
                start = line.textStart()
                length = line.textLength()
                all_lines.append(para[start : start + length].strip())
            layout.endLayout()

        pages: list[str] = []
        curr: list[str] = []
        for line in all_lines:
            curr.append(line)
            if len(curr) == self.MAX_LINES_PER_PAGE:
                pages.append("\n".join(curr))
                curr = []
        if curr:
            pages.append("\n".join(curr))

        return pages or [""]

    def _update_page_display(self) -> None:
        """Refreshes the body label and page navigation indicator based on current page."""
        total_pages = max(1, len(self.pages))
        if self.current_page_idx >= total_pages:
            self.current_page_idx = total_pages - 1
        self.current_page_idx = max(self.current_page_idx, 0)

        page_text = self.pages[self.current_page_idx] if self.pages else ""
        self.body_label.setText(page_text)
        self.lbl_page.setText(f"[ {self.current_page_idx + 1} / {total_pages} ]")

        self.btn_prev.setEnabled(self.current_page_idx > 0)
        self.btn_next.setEnabled(self.current_page_idx < total_pages - 1)

        has_multi = total_pages > 1
        self.btn_prev.setVisible(has_multi)
        self.lbl_page.setVisible(has_multi)
        self.btn_next.setVisible(has_multi)

    def _prev_page(self) -> None:
        if self.current_page_idx > 0:
            self._user_navigated = True
            self.current_page_idx -= 1
            self._update_page_display()

    def _next_page(self) -> None:
        if self.current_page_idx < len(self.pages) - 1:
            self._user_navigated = True
            self.current_page_idx += 1
            self._update_page_display()

    def _toggle_cursor_blink(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.cursor_label.setVisible(self._cursor_visible)

    def show_caption(
        self,
        text: str,
        source: str = "assistant",
        is_final: bool = False,
    ) -> None:
        """
        Update and display the persistent speech bubble with bounded 5-line pagination.
        Never auto-dismisses on a timer; remains persistent until dismissed or superseded.
        """
        self.dismiss_timer.stop()
        self.cursor_timer.stop()
        self.cursor_label.hide()
        self.confirm_widget.hide()
        self.footer_widget.show()
        self.body_label.setFixedHeight(106)

        # Ensure unbroken tokens wrap within bubble width
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

        # Detect new turn vs continuation of active streaming
        is_new_turn = (
            source != self.source
            or not self.current_text
            or not text.startswith(self.current_text[: min(15, len(self.current_text))])
        )
        if is_new_turn:
            self._user_navigated = False
            self.current_page_idx = 0

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
            self.body_label.setStyleSheet("color: #ffd700; font-style: italic; font-weight: 500;")
        elif source == "user":
            self.header_label.setText("YOU")
            self.header_label.setStyleSheet(
                "color: #a6e3a1; font-weight: bold; letter-spacing: 1px;"
            )
            self.body_label.setStyleSheet("color: #ffffff; font-weight: 500;")
        else:
            self.header_label.setText("LUCCA")
            self.header_label.setStyleSheet(
                "color: #ffd700; font-weight: 900; letter-spacing: 1.5px;"
            )
            self.body_label.setStyleSheet("color: #ffffff; font-weight: 500; line-height: 1.35;")

        # Paginate text into 5-line chunks
        self.pages = self._paginate(text)

        # If the user has not manually turned pages, follow along with the active streaming speech
        if not self._user_navigated:
            self.current_page_idx = max(0, len(self.pages) - 1)

        self._update_page_display()

        if is_final:
            self.cursor_label.show()
            self.cursor_timer.start(450)

        self.show()

    def show_confirmation(self, prompt: str, summary: str = "") -> None:
        """Display an interactive confirmation prompt with Yes/No buttons."""
        self.dismiss_timer.stop()
        self.header_label.setText("CONFIRM ACTION ⚠️")
        self.header_label.setStyleSheet("color: #f38ba8; font-weight: bold;")
        display_text = prompt
        if summary:
            display_text += f"\n({summary})"
        self.body_label.setFixedHeight(75)
        self.body_label.setText(display_text)
        self.body_label.setStyleSheet("color: #cdd6f4; font-weight: 500;")
        self.footer_widget.hide()
        self.confirm_widget.show()
        self.show()

    def _handle_confirmation(self, accepted: bool) -> None:
        self.confirm_widget.hide()
        self.footer_widget.show()
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
        painter.end()
