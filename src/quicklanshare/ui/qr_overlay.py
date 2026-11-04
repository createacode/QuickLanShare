"""二维码控件：顶部小二维码、悬浮预览与居中大图遮罩。"""

from __future__ import annotations

import base64
from typing import Any

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..utils.qr import qr_data_uri
from . import theme


def qr_pixmap(url: str, size: int) -> QPixmap:
    """把 URL 生成指定尺寸的二维码位图。"""
    if not url:
        return QPixmap()
    try:
        payload = base64.b64decode(qr_data_uri(url).split(",", 1)[1])
    except Exception:
        return QPixmap()
    pixmap = QPixmap()
    if not pixmap.loadFromData(payload):
        return QPixmap()
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class QrButton(QPushButton):
    """带悬停信号的二维码按钮。"""

    hoverChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "icon")
        self.setFixedSize(30, 30)
        self.setIconSize(QSize(22, 22))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 不使用 tooltip：悬停时已经显示大二维码，tooltip 会把它遮住。
        self.setAccessibleName("二维码，点击放大")

    def enterEvent(self, event: Any) -> None:
        self.hoverChanged.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self.hoverChanged.emit(False)
        super().leaveEvent(event)


class QrPeek(QFrame):
    """鼠标悬停时显示的大二维码浮层（不抢鼠标事件）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("QrPeek")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        self._qr = QLabel()
        self._qr.setFixedSize(180, 180)
        self._qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr.setStyleSheet("background: white; border-radius: 10px;")
        layout.addWidget(self._qr)
        caption = QLabel("手机扫码打开")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(caption)
        self.hide()

    def set_url(self, url: str) -> None:
        self._qr.setPixmap(qr_pixmap(url, 176))
        self.adjustSize()

    def show_near(self, anchor: QWidget) -> None:
        self.adjustSize()
        origin = anchor.mapToGlobal(QPoint(anchor.width() + 10, anchor.height() // 2 - 20))
        screen = QGuiApplication.screenAt(origin) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            x = min(max(area.left() + 8, origin.x()), area.right() - self.width() - 8)
            y = min(max(area.top() + 8, origin.y()), area.bottom() - self.height() - 8)
            origin = QPoint(x, y)
        self.move(origin)
        self.show()
        self.raise_()


class QrOverlay(QWidget):
    """居中二维码大图；点击卡片外区域关闭。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("QrOverlay")
        self.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch(1)

        self._card = QFrame()
        self._card.setObjectName("QrCard")
        self._card.setFixedWidth(360)
        theme.add_shadow(self._card, blur=36, offset_y=10, alpha=40)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(28, 24, 28, 22)
        card_layout.setSpacing(10)
        title = QLabel("手机扫码打开")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)
        self._qr = QLabel()
        self._qr.setFixedSize(260, 260)
        self._qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr.setStyleSheet("background: white; border-radius: 12px;")
        card_layout.addWidget(self._qr, 0, Qt.AlignmentFlag.AlignHCenter)
        self._url = QLabel()
        self._url.setObjectName("UrlText")
        self._url.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url.setWordWrap(True)
        self._url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self._url)
        hint = QLabel("点击二维码以外的区域关闭")
        hint.setObjectName("Muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(hint)
        layout.addWidget(self._card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

    def show_for(self, url: str) -> None:
        if not url:
            return
        self._url.setText(url)
        self._qr.setPixmap(qr_pixmap(url, 252))
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def close_overlay(self) -> None:
        self.hide()

    def mousePressEvent(self, event: Any) -> None:
        if not self._card.geometry().contains(event.position().toPoint()):
            self.close_overlay()
        event.accept()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(15, 23, 42, 115))
        painter.end()


__all__ = ["QrButton", "QrOverlay", "QrPeek", "qr_pixmap"]
