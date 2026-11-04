"""底部日志抽屉：需要时滑出，平时不占用主界面空间。"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from . import theme
from .widgets import LogPanel


class LogsDrawer(QFrame):
    """覆盖在窗口底部的运行日志面板。"""

    visibilityChanged = Signal(bool)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Drawer")
        self.setFrameShape(QFrame.Shape.NoFrame)
        theme.add_shadow(self, blur=34, offset_y=8, alpha=34)
        self._closing = False
        self._open = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.panel = LogPanel(self, closable=True)
        layout.addWidget(self.panel)
        self.panel.closeRequested.connect(self.hide_drawer)
        self._animation = QPropertyAnimation(self, b"pos", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._on_animation_finished)
        self.hide()

    @property
    def is_open(self) -> bool:
        return self._open

    def _geometry_targets(self) -> tuple[QPoint, QPoint]:
        parent = self.parentWidget()
        if parent is None:
            return QPoint(0, 0), QPoint(0, 0)
        width = max(480, parent.width() - 40)
        height = max(240, min(420, parent.height() - 140))
        x = max(12, (parent.width() - width) // 2)
        target_y = max(72, parent.height() - height - 42)
        hidden_y = parent.height()
        self.resize(width, height)
        return QPoint(x, target_y), QPoint(x, hidden_y)

    def toggle(self) -> None:
        if self._open:
            self.hide_drawer()
        else:
            self.show_drawer()

    def show_drawer(self) -> None:
        self._animation.stop()
        target, hidden = self._geometry_targets()
        self._closing = False
        self._open = True
        self.setGeometry(hidden.x(), hidden.y(), self.width(), self.height())
        self.show()
        self.raise_()
        self._animation.setStartValue(hidden)
        self._animation.setEndValue(target)
        self._animation.start()
        self.visibilityChanged.emit(True)

    def hide_drawer(self) -> None:
        if not self._open:
            return
        self._animation.stop()
        _target, hidden = self._geometry_targets()
        self._closing = True
        self._open = False
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(hidden)
        self._animation.start()
        self.visibilityChanged.emit(False)

    def _on_animation_finished(self) -> None:
        if self._closing:
            self.hide()
            self._closing = False

    def reposition(self) -> None:
        """父窗口尺寸变化时同步位置。"""
        if not self._open:
            return
        target, _ = self._geometry_targets()
        QTimer.singleShot(0, lambda: self.move(target) if self._open else None)


__all__ = ["LogsDrawer"]
