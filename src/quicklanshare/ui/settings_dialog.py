"""设置对话框：端口、浏览器开关、自动关闭、托盘行为与日志级别。"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
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
from ..utils.downloads import default_download_dir
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
        self.setMinimumSize(560, 520)
        self.resize(580, 720)
        self._download_dir_custom = False
        self._original = config
        self.result_config: AppConfig = copy.deepcopy(config)
        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

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

        access_group, access_layout = _group(
            "访问控制", "用四档滑块选择放通范围；服务运行时修改会立即生效。"
        )
        self.ip_scope_combo = QComboBox()
        self.ip_scope_combo.addItem("仅放通最后一位（同一网段）", "last1")
        self.ip_scope_combo.addItem("放通最后 2 位", "last2")
        self.ip_scope_combo.addItem("放通最后 3 位", "last3")
        self.ip_scope_combo.addItem("全部放通", "all")
        self.ip_scope_combo.setFixedWidth(240)
        self.ip_scope_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        access_layout.addWidget(
            _row(
                "IP 放通范围",
                self.ip_scope_combo,
                "例：本机 192.168.1.10，可选 192.168.1.x / 192.168.x.x / 192.x.x.x / 全部。"
                "顶部四档滑块与服务运行时修改都会立即生效；本机 127.0.0.1 始终允许。",
            )
        )
        layout.addWidget(access_group)

        startup_group, startup_layout = _group(
            "启动", "登录 Windows 后自动启动 QuickLanShare；双击 exe 仍会正常打开主界面。"
        )
        self.autostart_toggle = ToggleSwitch()
        startup_layout.addWidget(
            _row(
                "开机自启",
                self.autostart_toggle,
                "默认关闭。开启后，登录 Windows 时自动启动本程序。",
            )
        )
        self.silent_toggle = ToggleSwitch()
        self.silent_row = _row(
            "静默自启",
            self.silent_toggle,
            "开启后开机不显示主界面，只在系统托盘运行；点击托盘图标可显示。",
        )
        startup_layout.addWidget(self.silent_row)
        layout.addWidget(startup_group)

        download_group, download_layout = _group(
            "下载", "默认保存到当前用户的下载目录；可改为其他磁盘位置。"
        )
        picker = QWidget()
        picker_layout = QHBoxLayout(picker)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        picker_layout.setSpacing(8)
        self.download_dir_edit = QLineEdit()
        self.download_dir_edit.setReadOnly(True)
        self.download_dir_edit.setMinimumWidth(260)
        self.download_dir_edit.setCursor(Qt.CursorShape.IBeamCursor)
        picker_layout.addWidget(self.download_dir_edit, 1)
        self.download_dir_button = QPushButton("更改…")
        self.download_dir_button.setCursor(Qt.CursorShape.PointingHandCursor)
        picker_layout.addWidget(self.download_dir_button)
        self.download_reset_button = QPushButton("恢复默认")
        self.download_reset_button.setProperty("role", "link")
        self.download_reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        picker_layout.addWidget(self.download_reset_button)
        download_layout.addWidget(
            _row(
                "默认下载位置",
                picker,
                "自动识别 Windows 已知“下载”文件夹，包括已移动到 D 盘等位置；"
                "“恢复默认”会重新跟随系统设置。",
            )
        )
        layout.addWidget(download_group)

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
        footer.setContentsMargins(24, 10, 24, 18)
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
        outer.addLayout(footer)

        self.auto_toggle.toggled.connect(self.hours_spin.setEnabled)
        self.autostart_toggle.toggled.connect(self._on_autostart_toggled)
        self.download_dir_button.clicked.connect(self._choose_download_dir)
        self.download_reset_button.clicked.connect(self._reset_download_dir)

    def _on_autostart_toggled(self, checked: bool) -> None:
        self.silent_row.setVisible(checked)
        self.silent_toggle.setEnabled(checked)
        if not checked:
            self.silent_toggle.setChecked(False)

    def _choose_download_dir(self) -> None:
        start = self.download_dir_edit.text() or str(default_download_dir())
        chosen = QFileDialog.getExistingDirectory(self, "选择默认下载目录", start)
        if chosen:
            self.download_dir_edit.setText(chosen)
            self._download_dir_custom = True

    def _reset_download_dir(self) -> None:
        self._download_dir_custom = False
        self.download_dir_edit.setText(str(default_download_dir()))

    def _load_values(self) -> None:
        server = self.result_config.server
        self.port_spin.setValue(server.port)
        self.browser_toggle.setChecked(server.open_browser)
        scope_index = self.ip_scope_combo.findData(server.ip_scope)
        self.ip_scope_combo.setCurrentIndex(max(0, scope_index))
        self.auto_toggle.setChecked(server.auto_shutdown_enabled)
        self.hours_spin.setValue(server.auto_shutdown_hours)
        self.hours_spin.setEnabled(server.auto_shutdown_enabled)
        self.tray_toggle.setChecked(self.result_config.ui.close_to_tray)
        level_index = self.level_combo.findText(self.result_config.ui.log_level)
        self.level_combo.setCurrentIndex(max(0, level_index))
        self.autostart_toggle.setChecked(self.result_config.ui.autostart)
        self.silent_toggle.setChecked(self.result_config.ui.autostart_silent)
        if not self.result_config.ui.autostart:
            self.silent_toggle.setChecked(False)
        self.silent_row.setVisible(self.result_config.ui.autostart)
        self.silent_toggle.setEnabled(self.result_config.ui.autostart)
        self._download_dir_custom = bool(self.result_config.ui.download_dir)
        self.download_dir_edit.setText(
            self.result_config.ui.download_dir or str(default_download_dir())
        )

    # ----------------------------------------------------------------- save
    def _on_save(self) -> None:
        self.error_label.hide()
        config = copy.deepcopy(self._original)
        config.server.port = int(self.port_spin.value())
        config.server.open_browser = self.browser_toggle.isChecked()
        config.server.auto_shutdown_enabled = self.auto_toggle.isChecked()
        config.server.auto_shutdown_hours = float(self.hours_spin.value())
        config.server.ip_scope = str(self.ip_scope_combo.currentData() or "last1")
        config.ui.close_to_tray = self.tray_toggle.isChecked()
        config.ui.log_level = self.level_combo.currentText()
        config.ui.autostart = self.autostart_toggle.isChecked()
        config.ui.autostart_silent = (
            self.autostart_toggle.isChecked() and self.silent_toggle.isChecked()
        )
        if self._download_dir_custom:
            download_dir = Path(self.download_dir_edit.text()).expanduser()
            if not download_dir.is_dir():
                self._show_error("下载目录不存在，请重新选择")
                return
            config.ui.download_dir = str(download_dir)
        else:
            config.ui.download_dir = ""
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
