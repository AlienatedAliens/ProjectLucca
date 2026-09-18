"""
Project Lucca — Concentric Radial Commorose Menu
Spec 01 §1, ADR-005
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import NamedTuple

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRegion,
)
from PyQt6.QtWidgets import QWidget

from lucca.ui.theme import CT_BLUE_BOT, CT_BLUE_MID, CT_BLUE_TOP, CT_GOLD_TEXT, CT_SILVER_BORDER


class CommoroseAction(NamedTuple):
    label: str
    icon: str
    callback: Callable[[], None]
    description: str


class CommoroseRadialMenu(QWidget):
    """
    Battlefield-style concentric radial annular menu anchored around the CompanionSprite.
    Leaves the center hole (radius 88px) completely transparent so Lucca is 100% visible.
    8 mathematically spaced sectors with 3° uniform radial slit cuts and hover blooms.
    """

    def __init__(
        self,
        actions: list[CommoroseAction],
        parent: QWidget | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.comm_actions = actions
        self.on_close = on_close

        # Frameless, translucent, stays on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self.menu_size = 400
        self.setFixedSize(self.menu_size, self.menu_size)

        # Concentric geometry
        self.cx = self.menu_size / 2.0
        self.cy = self.menu_size / 2.0
        self.r_in = 88.0
        self.r_out = 175.0
        self.hovered_sector = -1

        # Smooth bloom-out animation state
        self.anim_scale = 0.0
        self.anim_opacity = 0.0
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self._on_anim_tick)

        self._update_mask()
        self.hide()

    def _update_mask(self) -> None:
        """Sets an annular mask so the 88px center hole passes mouse clicks straight to Lucca."""
        outer_rect = QRect(
            int(self.cx - self.r_out - 10),
            int(self.cy - self.r_out - 10),
            int((self.r_out + 10) * 2),
            int((self.r_out + 10) * 2),
        )
        inner_rect = QRect(
            int(self.cx - self.r_in),
            int(self.cy - self.r_in),
            int(self.r_in * 2),
            int(self.r_in * 2),
        )
        annular_region = QRegion(outer_rect, QRegion.RegionType.Ellipse).subtracted(
            QRegion(inner_rect, QRegion.RegionType.Ellipse)
        )
        self.setMask(annular_region)

    def toggle(self, center: QPoint) -> None:
        """Toggles Commorose radial menu open or closed."""
        if self.isVisible():
            self.hide()
            if self.on_close:
                self.on_close()
        else:
            self.show_around(center)

    def show_around(self, center: QPoint) -> None:
        """Positions menu centered on Lucca and triggers bloom-in animation."""
        top_left_x = int(center.x() - self.cx)
        top_left_y = int(center.y() - self.cy)
        self.move(top_left_x, top_left_y)
        self.anim_scale = 0.5
        self.anim_opacity = 0.2
        self.hovered_sector = -1
        self.show()
        self.raise_()
        self.activateWindow()
        self.anim_timer.start()

    def _on_anim_tick(self) -> None:
        self.anim_scale += 0.12 * (1.0 - self.anim_scale) + 0.02
        self.anim_opacity += 0.18 * (1.0 - self.anim_opacity) + 0.04
        if self.anim_scale >= 0.99 and self.anim_opacity >= 0.99:
            self.anim_scale = 1.0
            self.anim_opacity = 1.0
            self.anim_timer.stop()
        self.update()

    def _get_sector_path(self, idx: int, is_hovered: bool) -> QPainterPath:
        num = len(self.comm_actions)
        if num == 0:
            return QPainterPath()

        span = 360.0 / num
        gap = 3.0
        half_angle = (span - gap) / 2.0

        center_deg = -90.0 + (idx * span)
        deg1 = center_deg - half_angle
        deg2 = center_deg + half_angle

        rad1 = math.radians(deg1)
        rad2 = math.radians(deg2)
        rad_c = math.radians(center_deg)

        # Radial bloom on hover
        offset_dist = 6.0 if is_hovered else 0.0
        ox = offset_dist * math.cos(rad_c)
        oy = offset_dist * math.sin(rad_c)

        ccx = self.cx + ox
        ccy = self.cy + oy

        # Arc endpoints
        ox1 = ccx + self.r_out * math.cos(rad1)
        oy1 = ccy + self.r_out * math.sin(rad1)

        ix1 = ccx + self.r_in * math.cos(rad1)
        iy1 = ccy + self.r_in * math.sin(rad1)
        ix2 = ccx + self.r_in * math.cos(rad2)
        iy2 = ccy + self.r_in * math.sin(rad2)

        path = QPainterPath()
        path.moveTo(ix1, iy1)
        path.lineTo(ox1, oy1)

        # Outer arc
        rect_out = QRectF(ccx - self.r_out, ccy - self.r_out, self.r_out * 2, self.r_out * 2)
        path.arcTo(rect_out, -deg1, -(deg2 - deg1))

        # Line to inner arc
        path.lineTo(ix2, iy2)

        # Inner arc back
        rect_in = QRectF(ccx - self.r_in, ccy - self.r_in, self.r_in * 2, self.r_in * 2)
        path.arcTo(rect_in, -deg2, (deg2 - deg1))
        path.closeSubpath()

        return path

    def _get_sector_at(self, pos: QPointF) -> int:
        dx = pos.x() - self.cx
        dy = pos.y() - self.cy
        dist = math.hypot(dx, dy)

        # If inside center hole or outside outer boundary
        if dist < self.r_in or dist > (self.r_out + 15):
            return -1

        # Angle in degrees [-180, 180]
        deg = math.degrees(math.atan2(dy, dx))
        # Standardize relative to -90° (top)
        shifted = (deg + 90.0) % 360.0

        num = len(self.comm_actions)
        span = 360.0 / num
        idx = int((shifted + (span / 2.0)) % 360.0 // span)
        if 0 <= idx < num:
            return idx
        return -1

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        pos = event.position()
        old = self.hovered_sector
        self.hovered_sector = self._get_sector_at(pos)
        if old != self.hovered_sector:
            self.update()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None or event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position()
        idx = self._get_sector_at(pos)
        if idx >= 0 and idx < len(self.comm_actions):
            action = self.comm_actions[idx]
            self.hide()
            if self.on_close:
                self.on_close()
            # Trigger action callback
            action.callback()
        else:
            # Clicked outside ring: close menu
            self.hide()
            if self.on_close:
                self.on_close()

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            self.hide()
            if self.on_close:
                self.on_close()
            event.accept()

    def keyPressEvent(self, event: object) -> None:
        # Esc closes menu
        self.hide()
        if self.on_close:
            self.on_close()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.anim_opacity)

        num = len(self.comm_actions)
        span = 360.0 / num

        for i, act in enumerate(self.comm_actions):
            is_hover = i == self.hovered_sector
            path = self._get_sector_path(i, is_hover)

            # Gradient fill
            grad = QLinearGradient(0, 0, 0, self.menu_size)
            if is_hover:
                grad.setColorAt(0.0, QColor("#2d4bc4"))
                grad.setColorAt(0.5, QColor("#1c2f88"))
                grad.setColorAt(1.0, QColor("#0d184a"))
            else:
                grad.setColorAt(0.0, QColor(CT_BLUE_TOP))
                grad.setColorAt(0.5, QColor(CT_BLUE_MID))
                grad.setColorAt(1.0, QColor(CT_BLUE_BOT))

            painter.setBrush(QBrush(grad))
            pen_color = QColor(CT_GOLD_TEXT if is_hover else CT_SILVER_BORDER)
            painter.setPen(QPen(pen_color, 2.0 if is_hover else 1.6))
            painter.drawPath(path)

            # Draw icon and label at polar midpoint
            center_deg = -90.0 + (i * span)
            rad_c = math.radians(center_deg)
            offset_dist = 6.0 if is_hover else 0.0
            ccx = self.cx + offset_dist * math.cos(rad_c)
            ccy = self.cy + offset_dist * math.sin(rad_c)

            icon_r = 118.0
            label_r = 145.0

            ix = ccx + icon_r * math.cos(rad_c)
            iy = ccy + icon_r * math.sin(rad_c)
            lx = ccx + label_r * math.cos(rad_c)
            ly = ccy + label_r * math.sin(rad_c)

            # Draw icon
            painter.setFont(QFont("Segoe UI Emoji", 14))
            painter.drawText(
                QRectF(ix - 18, iy - 14, 36, 28),
                Qt.AlignmentFlag.AlignCenter,
                act.icon,
            )

            # Draw label
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.setPen(QPen(QColor(CT_GOLD_TEXT if is_hover else "#dce7ff")))
            painter.drawText(
                QRectF(lx - 45, ly - 10, 90, 20),
                Qt.AlignmentFlag.AlignCenter,
                act.label,
            )
