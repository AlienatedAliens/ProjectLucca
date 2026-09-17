"""
Project Lucca — Companion Avatar Sprite Widget
Spec 01 §1, ADR-005
"""

import math

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from lucca.ui.states import THEMES, AvatarTheme


class CompanionSprite(QWidget):
    def __init__(self, size: int = 140) -> None:
        super().__init__()
        self.sprite_size = size
        self.state = "idle"
        self.theme: AvatarTheme = THEMES["idle"]

        # Animation state
        self.phase = 0.0
        self.mouth_aperture = 0.0  # 0.0 (closed) to 1.0 (wide open)
        self.drag_position: QPoint | None = None

        # Window properties: frameless, always-on-top, translucent
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(self.sprite_size, self.sprite_size)

        # Position at bottom-right corner of screen by default
        self.move(100, 100)

        # 30 FPS animation timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_tick)
        self.anim_timer.start(33)

    def set_state(self, state: str) -> None:
        if state in THEMES:
            self.state = state
            self.theme = THEMES[state]
            self.update()

    def set_mouth_aperture(self, dbfs: float) -> None:
        """Scales dBFS (-60 to -10) to mouth aperture (0.0 to 1.0)."""
        clamped = max(-60.0, min(-10.0, dbfs))
        norm = (clamped + 60.0) / 50.0  # 0.0 to 1.0
        self.mouth_aperture = float(math.pow(norm, 1.5))
        self.update()

    def _on_tick(self) -> None:
        self.phase += self.theme.pulse_speed
        if self.state != "speaking":
            # Decay mouth aperture smoothly to closed
            self.mouth_aperture = max(0.0, self.mouth_aperture - 0.1)
        self.update()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() / 2.0
        center_y = self.height() / 2.0
        base_radius = (self.sprite_size / 2.0) - 15.0

        # Breathing pulse
        pulse = math.sin(self.phase) * 3.0
        radius = base_radius + pulse

        # 1. Outer Glow Aura
        glow_color = QColor(self.theme.glow_color)
        glow_color.setAlpha(60 + int(math.sin(self.phase) * 25.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_color))
        glow_r = radius + 6
        painter.drawEllipse(
            QRectF(center_x - glow_r, center_y - glow_r, glow_r * 2, glow_r * 2)
        )

        # 2. Main Body Orb
        body_color = QColor(self.theme.primary_color)
        painter.setBrush(QBrush(body_color))
        painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))

        # 3. Expressive Eyes
        eye_color = QColor(self.theme.eye_color)
        painter.setBrush(QBrush(eye_color))
        eye_offset_x = radius * 0.35
        eye_y = center_y - (radius * 0.15)
        eye_width = 7.0
        eye_height = 11.0

        # Natural blink cycle
        is_blinking = (int(self.phase * 5.0) % 70) == 0
        current_eye_h = 2.0 if is_blinking else eye_height

        left_eye_rect = QRectF(
            center_x - eye_offset_x - (eye_width / 2), eye_y, eye_width, current_eye_h
        )
        right_eye_rect = QRectF(
            center_x + eye_offset_x - (eye_width / 2), eye_y, eye_width, current_eye_h
        )
        painter.drawEllipse(left_eye_rect)
        painter.drawEllipse(right_eye_rect)

        # 4. Animated Mouth
        mouth_color = QColor(self.theme.mouth_color)
        painter.setPen(QPen(mouth_color, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        mouth_y = center_y + (radius * 0.25)
        mouth_w = 14.0

        if self.mouth_aperture > 0.05:
            # Open mouth ellipse
            mouth_h = max(3.0, self.mouth_aperture * 18.0)
            painter.setBrush(QBrush(mouth_color))
            mouth_rect = QRectF(
                center_x - (mouth_w / 2), mouth_y - (mouth_h / 2), mouth_w, mouth_h
            )
            painter.drawEllipse(mouth_rect)
        else:
            # Closed happy arc smile
            path = QPainterPath()
            path.moveTo(center_x - (mouth_w / 2), mouth_y)
            path.quadTo(center_x, mouth_y + 4.0, center_x + (mouth_w / 2), mouth_y)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    # Mouse drag support
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event and event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
