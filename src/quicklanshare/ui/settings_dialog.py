"""设置对话框：端口、浏览器开关、自动关闭、托盘行为与日志级别。"""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..utils.app_config import (
    LOG_LEVELS,
    MAX_AUTO_SHUTDOWN_HOURS,
    MIN_AUTO_SHUTDOWN_HOURS,
    AppConfig,
)
from . import theme
from .widgets import ToggleSwitch


def _group(title: str, description: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("SettingGroup")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    heading = QLabel(title)
    heading.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {theme.TEXT};")
    layout.addWidget(heading)
    if description:
        hint = QLabel(description)
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
    return frame, layout


def _row(label_text: str, widget: QWidget, hint_text: str = "") -> QWidget:
    row = QWidget()
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    label = QLabel(label_text)
    label.setObjectName("Secondary")
    top.addWidget(label)
    top.addStretch(1)
    top.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)
    layout.addLayout(top)
    if hint_text:
        hint = QLabel(hint_text)
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
    return row


class SettingsDialog(QDialog):
    """返回一份修改后的 :class:`AppConfig` 副本。"""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置 - QuickLanShare")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._original = config
        self.result_config: AppConfig = copy.deepcopy(config)
        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("设置")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel("修改后点击保存；端口变更需要重启服务才能生效。")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        server_group, server_layout = _group("服务", "服务在局域网内提供网页版上传、下载与聊天。")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setFixedWidth(140)
        self.port_spin.setCursor(Qt.CursorShape.PointingHandCursor)
        server_layout.addWidget(
            _row("监听端口", self.port_spin, "端口被占用时会自动顺延；修改后需重启服务。")
        )
        self.browser_toggle = ToggleSwitch()
        server_layout.addWidget(
            _row(
                "启动服务后自动打开网页",
                self.browser_toggle,
                "默认关闭。需要时也可以随时点击界面上的“打开网页”。",
            )
        )
        layout.addWidget(server_group)

        shutdown_group, shutdown_layout = _group(
            "自动关闭", "默认在 24 小时后自动关闭程序；关闭开关后程序会一直运行。"
        )
        self.auto_toggle = ToggleSwitch()
        shutdown_layout.addWidget(
            _row("启用自动关闭", self.auto_toggle, "自动关闭会同时停止服务并退出程序。")
        )
        self.hours_spin = QDoubleSpinBox()
        self.hours_spin.setRange(MIN_AUTO_SHUTDOWN_HOURS, MAX_AUTO_SHUTDOWN_HOURS)
        self.hours_spin.setDecimals(1)
        self.hours_spin.setSingleStep(1.0)
        self.hours_spin.setSuffix(" 小时")
        self.hours_spin.setFixedWidth(160)
        self.hours_spin.setCursor(Qt.CursorShape.PointingHandCursor)
        shutdown_layout.addWidget(_row("自动关闭时长", self.hours_spin, "可设置 0.1 至 720 小时。"))
        layout.addWidget(shutdown_group)

        behavior_group, behavior_layout = _group("窗口与日志")
        self.tray_toggle = ToggleSwitch()
        behavior_layout.addWidget(
            _row(
                "关闭窗口时最小化到托盘",
                self.tray_toggle,
                "关闭后点击窗口 × 将直接退出程序。",
            )
        )
        self.level_combo = QComboBox()
        self.level_combo.addItems(list(LOG_LEVELS))
        self.level_combo.setFixedWidth(160)
        self.level_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        behavior_layout.addWidget(_row("日志级别", self.level_combo))
        layout.addWidget(behavior_group)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {theme.DANGER}; font-size: 12px;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        layout.addStretch(1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        save = QPushButton("保存")
        save.setProperty("role", "primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        footer.addWidget(save)
        layout.addLayout(footer)

        self.auto_toggle.toggled.connect(self.hours_spin.setEnabled)

    def _load_values(self) -> None:
        server = self.result_config.server
        self.port_spin.setValue(server.port)
        self.browser_toggle.setChecked(server.open_browser)
        self.auto_toggle.setChecked(server.auto_shutdown_enabled)
        self.hours_spin.setValue(server.auto_shutdown_hours)
        self.hours_spin.setEnabled(server.auto_shutdown_enabled)
        self.tray_toggle.setChecked(self.result_config.ui.close_to_tray)
        level_index = self.level_combo.findText(self.result_config.ui.log_level)
        self.level_combo.setCurrentIndex(max(0, level_index))

    # ----------------------------------------------------------------- save
    def _on_save(self) -> None:
        self.error_label.hide()
        config = copy.deepcopy(self._original)
        config.server.port = int(self.port_spin.value())
        config.server.open_browser = self.browser_toggle.isChecked()
        config.server.auto_shutdown_enabled = self.auto_toggle.isChecked()
        config.server.auto_shutdown_hours = float(self.hours_spin.value())
        config.ui.close_to_tray = self.tray_toggle.isChecked()
        config.ui.log_level = self.level_combo.currentText()
        if not 1 <= config.server.port <= 65535:
            self._show_error("端口必须在 1 到 65535 之间")
            return
        if config.server.auto_shutdown_enabled and not (
            MIN_AUTO_SHUTDOWN_HOURS <= config.server.auto_shutdown_hours <= MAX_AUTO_SHUTDOWN_HOURS
        ):
            self._show_error("自动关闭时长不合法")
            return
        self.result_config = config
        self.accept()

    def _show_error(self, text: str) -> None:
        self.error_label.setText(text)
        self.error_label.show()

    def set_versions(self, version: str) -> None:
        """保留扩展点：在标题上显示版本信息。"""
        self.setWindowTitle(f"设置 - QuickLanShare v{version}")


__all__ = ["SettingsDialog"]
