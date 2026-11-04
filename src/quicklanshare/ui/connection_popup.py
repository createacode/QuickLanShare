"""连接信息弹层：二维码、局域网地址、本机地址与在线人数。"""

from __future__ import annotations

import base64

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..utils.qr import qr_data_uri
from . import theme


class ConnectionPopup(QFrame):
    """从顶部地址胶囊弹出的连接信息面板。"""

    openWebRequested = Signal()
    copyRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("Popup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        title = QLabel("连接信息")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        self._online = QLabel("服务未启动")
        self._online.setObjectName("Muted")
        layout.addWidget(self._online)

        self._qr = QLabel("启动服务后生成二维码")
        self._qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr.setFixedSize(180, 180)
        self._qr.setObjectName("QrFrame")
        self._qr.setStyleSheet(
            f"background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 12px;"
            f" color: {theme.TEXT_MUTED}; font-size: 11px;"
        )
        layout.addWidget(self._qr, 0, Qt.AlignmentFlag.AlignHCenter)

        self._url = QLabel("—")
        self._url.setObjectName("UrlText")
        self._url.setWordWrap(True)
        self._url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._url)

        self._local = QLabel("")
        self._local.setObjectName("Muted")
        self._local.setWordWrap(True)
        layout.addWidget(self._local)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._copy = QPushButton("复制链接")
        self._copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy.clicked.connect(self.copyRequested.emit)
        buttons.addWidget(self._copy)
        self._open = QPushButton("打开网页")
        self._open.setProperty("role", "primary")
        self._open.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open.clicked.connect(self.openWebRequested.emit)
        buttons.addWidget(self._open)
        layout.addLayout(buttons)
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        self._copy.setEnabled(enabled)
        self._open.setEnabled(enabled)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        painter.fillPath(path, QColor(theme.SURFACE))
        painter.setPen(QColor(theme.BORDER))
        painter.drawPath(path)
        painter.end()

    def set_info(self, share_url: str, local_url: str, online: int = 0) -> None:
        self._url.setText(share_url)
        self._local.setText(f"本机 {local_url}")
        self._online.setText(f"局域网共享中 · 在线 {online} 台设备")
        self._set_enabled(True)
        self._qr.setPixmap(QPixmap())
        self._qr.setText("二维码生成中…")
        try:
            payload = base64.b64decode(qr_data_uri(share_url).split(",", 1)[1])
            pixmap = QPixmap()
            if pixmap.loadFromData(payload):
                self._qr.setText("")
                self._qr.setPixmap(
                    pixmap.scaled(
                        168,
                        168,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        except Exception:
            self._qr.setText("二维码不可用")
        self.adjustSize()

    def set_online(self, online: int) -> None:
        if self._copy.isEnabled():
            self._online.setText(f"局域网共享中 · 在线 {online} 台设备")

    def clear(self) -> None:
        self._url.setText("服务未启动")
        self._local.setText("")
        self._online.setText("服务未启动")
        self._qr.setPixmap(QPixmap())
        self._qr.setText("启动服务后生成二维码")
        self._set_enabled(False)
        self.adjustSize()

    def show_near(self, anchor: QWidget) -> None:
        """在触发按钮下方显示，并限制在屏幕内。"""
        self.adjustSize()
        origin = anchor.mapToGlobal(QPoint(0, anchor.height() + 8))
        screen = QGuiApplication.screenAt(origin) or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = min(max(available.left() + 8, origin.x()), available.right() - self.width() - 8)
            y = min(max(available.top() + 8, origin.y()), available.bottom() - self.height() - 8)
            origin = QPoint(x, y)
        self.move(origin)
        self.show()


__all__ = ["ConnectionPopup"]
