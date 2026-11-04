"""图标与图标字体辅助函数。

Windows 10 / 11 自带 ``Segoe Fluent Icons``（Win11）或 ``Segoe MDL2 Assets``
（Win10），这里统一取可用的一种，避免额外图标资源与第三方图标库。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPixmap

from ..utils.paths import app_icon_path
from . import theme

logger = logging.getLogger("quicklanshare.ui")

GLYPHS: dict[str, str] = {
    "upload": "\ue898",
    "download": "\ue896",
    "folder": "\ue8b7",
    "link": "\ue71b",
    "copy": "\ue8c8",
    "settings": "\ue713",
    "info": "\ue946",
    "refresh": "\ue72c",
    "delete": "\ue74d",
    "open": "\ue8e5",
    "globe": "\ue774",
    "clock": "\ue823",
    "stop": "\ue71a",
    "power": "\ue7e8",
    "play": "\ue768",
    "file": "\ue8a5",
    "phone": "\ue8ea",
    "check": "\ue73e",
    "warning": "\ue7ba",
    "error": "\uea39",
    "chevron": "\ue70d",
    "add": "\ue710",
    "close": "\ue711",
    "zip": "\uf012",
}

_FONT_CANDIDATES = ("Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol")


def icon_font(pixel_size: int = 16) -> QFont:
    """返回带图标字形的字体。"""
    available = set(QFontDatabase.families())
    family = next((name for name in _FONT_CANDIDATES if name in available), "Segoe UI")
    font = QFont(family)
    font.setPixelSize(pixel_size)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def glyph_pixmap(
    name: str,
    *,
    size: int = 18,
    color: str = theme.TEXT_SECONDARY,
    scale: int = 2,
) -> QPixmap:
    """把图标字形渲染为高分辨率透明位图。"""
    glyph = GLYPHS.get(name, name)
    pixel = size * scale
    pixmap = QPixmap(pixel, pixel)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = icon_font(pixel)
    painter.setFont(font)
    painter.setPen(QColor(color))
    metrics = QFontMetrics(font)
    rect = QRectF(0, 0, pixel, pixel)
    bounds = metrics.boundingRect(glyph)
    center = QPointF(
        rect.center().x() - bounds.width() / 2 - bounds.left(),
        rect.center().y() - bounds.height() / 2 - bounds.top(),
    )
    painter.drawText(center, glyph)
    painter.end()
    pixmap.setDevicePixelRatio(float(scale))
    return pixmap


def glyph_icon(name: str, *, size: int = 18, color: str = theme.TEXT_SECONDARY) -> QIcon:
    return QIcon(glyph_pixmap(name, size=size, color=color))


def app_icon() -> QIcon:
    """应用图标：来自 ``app.ico``，缺失时用系统图标兜底并记录。"""
    path = app_icon_path()
    if path.exists():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    logger.warning("未找到可用的 app.ico（%s），已回退系统图标", path)
    return QIcon.fromTheme("folder", QIcon())
