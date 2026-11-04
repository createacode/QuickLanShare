"""关于对话框：名称、版本、作者、版权与第三方许可入口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.version import (
    __author__,
    __copyright_ym__,
    __software_name__,
    __version__,
    copyright_suffix,
)
from . import icons, theme


class AboutDialog(QDialog):
    def __init__(
        self,
        notices_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._notices_path = notices_path
        self.setWindowTitle(f"关于 {__software_name__} v{__version__} {copyright_suffix()}")
        self.setModal(True)
        self.setFixedWidth(460)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(14)
        icon_label = QLabel()
        pixmap = icons.app_icon().pixmap(56, 56)
        icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(56, 56)
        header.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        names = QVBoxLayout()
        names.setSpacing(2)
        title = QLabel(__software_name__)
        title.setObjectName("PageTitle")
        names.addWidget(title)
        version = QLabel(f"版本 {__version__}")
        version.setObjectName("Secondary")
        names.addWidget(version)
        names.addStretch(1)
        header.addLayout(names, 1)
        layout.addLayout(header)

        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {theme.BORDER};")
        layout.addWidget(divider)

        description = QLabel(
            "QuickLanShare 是一款局域网文件快速传输工具：桌面端负责启动服务、"
            "拖拽上传与下载管理，手机或其他电脑打开网页即可互传文件。"
        )
        description.setWordWrap(True)
        description.setObjectName("Secondary")
        layout.addWidget(description)

        meta = QLabel(
            f"作者：{__author__}\n"
            f"版权：Copyright © {__author__} {__copyright_ym__}\n"
            "目标平台：Windows 10 / Windows 11 x64\n"
            "界面：PySide6（Qt for Python）"
        )
        meta.setObjectName("Secondary")
        meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(meta)

        hint = QLabel("本项目按 LGPL-3.0 动态使用 Qt / PySide6；你可以自行替换程序目录中的 Qt 库。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch(1)
        footer = QHBoxLayout()
        notices = QPushButton("第三方许可")
        notices.setCursor(Qt.CursorShape.PointingHandCursor)
        notices.setEnabled(self._notices_path is not None and self._notices_path.exists())
        notices.clicked.connect(self._open_notices)
        footer.addWidget(notices)
        footer.addStretch(1)
        close = QPushButton("关闭")
        close.setProperty("role", "primary")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)

    def _open_notices(self) -> None:
        if self._notices_path is not None and self._notices_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._notices_path)))


__all__ = ["AboutDialog"]
