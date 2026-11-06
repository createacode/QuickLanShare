"""开放网段拨杆：四个 IP 刻点的连续滑动选择控件。"""

from __future__ import annotations

from typing import Any, ClassVar

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QFrame, QSizePolicy, QWidget

from . import theme

# 从左到右四个刻点对应的放通范围。
_DOT_SCOPES = ("last3", "last2", "last1", "all")
_SCOPE_TO_POS = {scope: index for index, scope in enumerate(_DOT_SCOPES)}
_MIN_POS = 0
_MAX_POS = 3


class NetworkScopeControl(QFrame):
    """四个 IP 刻点的滑动选择开关。

    刻点从左到右显示本机真实 IPv4，例如 ``192 / 168 / 1 / 10``：
    - 第 1 点：``192.*.*.*``
    - 第 2 点：``192.168.*.*``
    - 第 3 点：``192.168.1.*``
    - 第 4 点：全部开放（默认）。

    滑块只能拖动圆形小点，松手后吸附并提交；服务启停由电源按钮负责。
    """

    scopeCommitted = Signal(str)

    _FALLBACK_PARTS: ClassVar[tuple[str, str, str, str]] = ("192", "168", "1", "10")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeControl")
        self.setFixedSize(240, 64)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("开放网段")
        self._server_ip = ""
        self._scope = "all"
        self._target = _MAX_POS
        self._drag_target = _MAX_POS
        self._thumb = float(_MAX_POS)
        self._dragging = False
        self._animation = QPropertyAnimation(self, b"thumb", self)
        self._animation.setDuration(190)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.set_scope("all", animate=False)

    # ------------------------------------------------------------------ state
    def sizeHint(self) -> QSize:
        return QSize(240, 64)

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def current_display(self) -> str:
        return self._display_text(self._drag_target if self._dragging else self._target)

    def get_thumb(self) -> float:
        return self._thumb

    def set_thumb(self, value: float) -> None:
        self._thumb = max(float(_MIN_POS), min(float(_MAX_POS), float(value)))
        self.update()

    thumb = Property(float, fget=get_thumb, fset=set_thumb)

    def set_scope(self, scope: str, *, animate: bool = True) -> None:
        if scope not in _SCOPE_TO_POS:
            scope = "all"
        self._scope = scope
        target = _SCOPE_TO_POS[scope]
        self._target = target
        self._drag_target = target
        self._animate_to(target, animate=animate)
        self._update_tooltip()
        self.update()

    def set_server_ip(self, ip: str) -> None:
        self._server_ip = str(ip or "")
        self._update_tooltip()
        self.update()

    # ------------------------------------------------------------- geometry
    def _parts(self) -> tuple[str, str, str, str]:
        parts = self._server_ip.split(".")
        if len(parts) == 4 and all(part.isdigit() for part in parts):
            return parts[0], parts[1], parts[2], parts[3]
        return self._FALLBACK_PARTS

    def _dot_x(self, index: int) -> float:
        return 22.0 + index * (196.0 / 3.0)

    def _position_x(self, position: float) -> float:
        value = max(float(_MIN_POS), min(float(_MAX_POS), position))
        index = min(_MAX_POS - 1, int(value))
        fraction = value - index
        return self._dot_x(index) + (self._dot_x(index + 1) - self._dot_x(index)) * fraction

    def _position_from_x(self, x: float) -> float:
        if x <= self._dot_x(0):
            return float(_MIN_POS)
        for index in range(_MAX_POS):
            left = self._dot_x(index)
            right = self._dot_x(index + 1)
            if x <= right:
                return index + (x - left) / (right - left)
        return float(_MAX_POS)

    def _track_rect(self) -> QRectF:
        return QRectF(self._dot_x(0), 24, self._dot_x(_MAX_POS) - self._dot_x(0), 10)

    # ---------------------------------------------------------------- display
    def _display_text(self, target: int) -> str:
        p0, p1, p2, _p3 = self._parts()
        return {
            0: f"{p0}.*.*.*",
            1: f"{p0}.{p1}.*.*",
            2: f"{p0}.{p1}.{p2}.*",
            3: "全部开放",
        }.get(target, "全部开放")

    def _update_tooltip(self) -> None:
        p0, p1, p2, _p3 = self._parts()
        self.setToolTip(
            "开放网段\n"
            f"{p0} 点：{p0}.*.*.*\n"
            f"{p1} 点：{p0}.{p1}.*.*\n"
            f"{p2} 点：{p0}.{p1}.{p2}.*\n"
            "最右：全部开放\n"
            "拖动圆形小点，松手后生效。"
        )

    def _animate_to(self, target: int, *, animate: bool = True) -> None:
        self._animation.stop()
        if animate and self.isVisible():
            self._animation.setStartValue(self._thumb)
            self._animation.setEndValue(float(target))
            self._animation.start()
        else:
            self.set_thumb(float(target))

    # --------------------------------------------------------------- dragging
    def _thumb_hit(self, x: float, y: float) -> bool:
        center_x = self._position_x(self._thumb)
        return abs(x - center_x) <= 18 and 14 <= y <= 50

    def mousePressEvent(self, event: Any) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if not self._thumb_hit(event.position().x(), event.position().y()):
            event.accept()
            return
        self._dragging = True
        self._drag_target = self._target
        self._animation.stop()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: Any) -> None:
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        raw = self._position_from_x(event.position().x())
        # 吸附迟滞：指针必须明显越过下一格，拨杆才换档。
        while raw > self._drag_target + 0.58 and self._drag_target < _MAX_POS:
            self._drag_target += 1
        while raw < self._drag_target - 0.58 and self._drag_target > _MIN_POS:
            self._drag_target -= 1
        visual = max(
            float(self._drag_target) - 0.38,
            min(float(self._drag_target) + 0.38, raw),
        )
        self.set_thumb(visual)
        event.accept()

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            super().mouseReleaseEvent(event)
            return
        self._dragging = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._commit_position(self._drag_target)
        event.accept()

    def wheelEvent(self, event: Any) -> None:
        step = 1 if event.angleDelta().y() < 0 else -1
        target = max(_MIN_POS, min(_MAX_POS, self._target + step))
        if target != self._target:
            self._commit_position(target)
        event.accept()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            if self._target > _MIN_POS:
                self._commit_position(self._target - 1)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            if self._target < _MAX_POS:
                self._commit_position(self._target + 1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Home:
            self._commit_position(_MIN_POS)
            event.accept()
            return
        if event.key() == Qt.Key.Key_End:
            self._commit_position(_MAX_POS)
            event.accept()
            return
        super().keyPressEvent(event)

    def _commit_position(self, target: int) -> None:
        target = max(_MIN_POS, min(_MAX_POS, int(target)))
        self._target = target
        self._drag_target = target
        self._animate_to(target)
        scope = _DOT_SCOPES[target]
        changed = scope != self._scope
        self._scope = scope
        self._update_tooltip()
        self.update()
        if changed:
            self.scopeCommitted.emit(scope)

    # ---------------------------------------------------------------- painting
    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.setBrush(QBrush(QColor(theme.SURFACE_MUTED)))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        title_font = QFont(self.font())
        title_font.setPixelSize(10)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(theme.TEXT_SECONDARY))
        painter.drawText(
            QRectF(10, 4, 100, 14),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            "开放网段",
        )

        display_font = QFont(self.font())
        display_font.setPixelSize(11)
        display_font.setWeight(QFont.Weight.Bold)
        painter.setFont(display_font)
        painter.setPen(QColor(theme.ACCENT))
        metrics = QFontMetrics(display_font)
        display = metrics.elidedText(self.current_display, Qt.TextElideMode.ElideRight, 108)
        painter.drawText(
            QRectF(120, 3, 110, 16),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            display,
        )

        track = self._track_rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#DCE5F0")))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        thumb_x = self._position_x(self._thumb)
        active = QRectF(
            self._dot_x(0),
            track.top(),
            max(0.0, thumb_x - self._dot_x(0)),
            track.height(),
        )
        if active.width() > 0:
            painter.setBrush(QBrush(QColor(theme.ACCENT)))
            painter.drawRoundedRect(active, track.height() / 2, track.height() / 2)

        for index in range(4):
            x = self._dot_x(index)
            is_active = self._target >= index
            painter.setBrush(QBrush(QColor("#FFFFFF" if is_active else "#A8B6C8")))
            painter.drawEllipse(QRectF(x - 3.5, track.center().y() - 3.5, 7, 7))

        # 小圆点拨杆：白色隔离环 + 实心小点。
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawEllipse(QRectF(thumb_x - 7, track.center().y() - 7, 14, 14))
        painter.setBrush(QBrush(QColor(theme.ACCENT)))
        painter.drawEllipse(QRectF(thumb_x - 5, track.center().y() - 5, 10, 10))

        label_font = QFont(self.font())
        label_font.setPixelSize(10)
        label_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(label_font)
        for index, label in enumerate(self._parts()):
            x = self._dot_x(index)
            selected = index == self._target
            painter.setPen(QColor(theme.ACCENT if selected else theme.TEXT_MUTED))
            painter.drawText(
                QRectF(x - 22, 49, 44, 14),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                label,
            )
        painter.end()


__all__ = ["NetworkScopeControl"]
