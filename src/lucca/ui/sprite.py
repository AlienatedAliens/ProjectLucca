import json
import logging
import math
from collections.abc import Callable

logger = logging.getLogger(__name__)


from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QWidget

from lucca.core.config import get_resource_path
from lucca.ui.states import THEMES, AvatarTheme


class CompanionSprite(QWidget):
    def __init__(self, size: int = 140) -> None:
        super().__init__()
        self.sprite_size = size
        self.state = "idle"
        self.theme: AvatarTheme = THEMES["idle"]

        # Callbacks for desktop integration
        self.on_geometry_changed: Callable[[], None] | None = None
        self.on_toggle_chat: Callable[[], None] | None = None
        self.on_context_menu: Callable[[QPoint], None] | None = None
        self.on_toggle_commorose: Callable[[QPoint], None] | None = None

        # Animation state
        self.phase = 0.0
        self.mouth_aperture = 0.0  # 0.0 (closed) to 1.0 (wide open)
        self.drag_position: QPoint | None = None
        self.press_start_pos: QPoint | None = None

        # Single vs Double click dispatcher
        self.single_click_timer = QTimer(self)
        self.single_click_timer.setSingleShot(True)
        self.single_click_timer.setInterval(220)
        self.single_click_timer.timeout.connect(self._trigger_single_click)

        # Sprite sheets & frames
        self.sprites_dir = get_resource_path("assets/sprites/lucca")
        self.pixmaps: dict[str, list[QPixmap]] = {}
        self.sprite_scale = 3
        self._load_sprites()

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

    def _load_sprites(self) -> None:
        manifest_path = self.sprites_dir / "manifest.json"
        if not manifest_path.exists():
            return
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            self.sprite_scale = int(manifest.get("scale", 3))
            states = manifest.get("states", {})
            for state_name, info in states.items():
                frames = info.get("frames", [])
                pms: list[QPixmap] = []
                for frame_file in frames:
                    fp = self.sprites_dir / frame_file
                    if fp.exists():
                        pm = QPixmap(str(fp))
                        if not pm.isNull():
                            pms.append(pm)
                if pms:
                    self.pixmaps[state_name] = pms
        except Exception as exc:  # noqa: BLE001
            logger.debug("load_sprites_failed: %s", exc)
            self.pixmaps = {}

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

        # Check if we have pixel-art sprite frames loaded
        if self.pixmaps:
            # 1. Subtle ambient state aura behind character
            glow_color = QColor(self.theme.glow_color)
            glow_color.setAlpha(40 + int(math.sin(self.phase) * 20.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow_color))
            glow_r = (self.sprite_size / 2.0) - 10.0 + (math.sin(self.phase) * 3.0)
            painter.drawEllipse(
                QRectF(center_x - glow_r, center_y - glow_r, glow_r * 2, glow_r * 2)
            )

            # 2. Select sprite frame based on state & audio
            pix: QPixmap | None = None
            if self.state == "speaking" and "speaking" in self.pixmaps:
                frames = self.pixmaps["speaking"]
                # frame 0: mouth closed, frame 1: mouth open
                if self.mouth_aperture > 0.08 and len(frames) > 1:
                    pix = frames[1]
                else:
                    pix = frames[0]
            elif self.state == "thinking" and "thinking" in self.pixmaps:
                frames = self.pixmaps["thinking"]
                idx = int(self.phase * 2.5) % len(frames)
                pix = frames[idx]
            elif self.state in self.pixmaps:
                frames = self.pixmaps[self.state]
                idx = int(self.phase * 1.5) % len(frames)
                pix = frames[idx]
            elif "idle" in self.pixmaps:
                pix = self.pixmaps["idle"][0]

            if pix:
                scaled_w = pix.width() * self.sprite_scale
                scaled_h = pix.height() * self.sprite_scale
                scaled = pix.scaled(
                    scaled_w,
                    scaled_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
                bob = int(math.sin(self.phase) * 2.0) if self.state == "idle" else 0
                draw_x = int(center_x - (scaled.width() / 2.0))
                draw_y = int(center_y - (scaled.height() / 2.0)) + bob
                painter.drawPixmap(draw_x, draw_y, scaled)
                painter.end()
                return

        # Fallback: Geometric vector companion orb
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
        painter.drawEllipse(QRectF(center_x - glow_r, center_y - glow_r, glow_r * 2, glow_r * 2))

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
            mouth_rect = QRectF(center_x - (mouth_w / 2), mouth_y - (mouth_h / 2), mouth_w, mouth_h)
            painter.drawEllipse(mouth_rect)
        else:
            # Closed happy arc smile
            path = QPainterPath()
            path.moveTo(center_x - (mouth_w / 2), mouth_y)
            path.quadTo(center_x, mouth_y + 4.0, center_x + (mouth_w / 2), mouth_y)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.end()

    # Desktop interaction & mouse support
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            self.press_start_pos = event.globalPosition().toPoint()
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event and event.buttons() & Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton and self.press_start_pos:
            dist = (event.globalPosition().toPoint() - self.press_start_pos).manhattanLength()
            if dist < 6:
                # Potential single click: wait 220ms for possible double click
                self.single_click_timer.start()
            self.press_start_pos = None
            self.drag_position = None
            event.accept()

    def _trigger_single_click(self) -> None:
        # Single Click on Lucca: brings up subtitle / type message / click to talk button
        if self.on_toggle_chat:
            self.on_toggle_chat()

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            # Double Click on Lucca: opens Commorose, clicking twice closes it
            self.single_click_timer.stop()
            if self.on_toggle_commorose:
                center = self.geometry().center()
                self.on_toggle_commorose(center)
            event.accept()

    def contextMenuEvent(self, event: object) -> None:
        if self.on_context_menu:
            global_pos = self.cursor().pos()
            self.on_context_menu(global_pos)

    def moveEvent(self, event: QMoveEvent | None) -> None:
        super().moveEvent(event)
        if self.on_geometry_changed:
            self.on_geometry_changed()

    def reset_position(self) -> None:
        """Reset avatar position to bottom-right corner."""
        screen = self.screen()
        if screen:
            geom = screen.availableGeometry()
            self.move(geom.width() - self.width() - 50, geom.height() - self.height() - 70)
        else:
            self.move(100, 100)
        if self.on_geometry_changed:
            self.on_geometry_changed()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Hides avatar to background system tray instead of destroying window."""
        if event is not None:
            event.ignore()
        self.hide()

    def toggle_always_on_top(self) -> bool:
        """Toggle WindowStaysOnTopHint and return new state."""
        flags = self.windowFlags()
        is_on_top = bool(flags & Qt.WindowType.WindowStaysOnTopHint)
        if is_on_top:
            self.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
        self.show()
        return not is_on_top
