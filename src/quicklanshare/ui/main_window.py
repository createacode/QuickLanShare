"""主窗口：文件传输 + 文本共享双栏工作台。

布局：
- 顶部：品牌、运行状态、连接信息、打开网页、服务电源、设置、更多
- 主体：左侧文件传输，右侧文本共享（QSplitter）
- 底部：状态栏（在线、自动关闭、日志抽屉）
"""

from __future__ import annotations

import contextlib
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PySide6.QtCore import QEasingCurve, QObject, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ..core.version import __software_name__, __version__, window_title
from ..services.config import Config
from ..utils.app_config import AppConfig, apply_window_geometry, save_config
from ..utils.format import human_size, human_time
from ..utils.logging_setup import LoggingSession, set_log_level
from ..utils.paths import app_base_dir, default_data_dir
from . import icons, theme
from .about_dialog import AboutDialog
from .backend import Backend
from .connection_popup import ConnectionPopup
from .logs_drawer import LogsDrawer
from .settings_dialog import SettingsDialog
from .text_panel import TextPanel
from .widgets import (
    DropZone,
    EmptyState,
    FileTable,
    SkeletonList,
    Toast,
    TransferPanel,
)

logger = logging.getLogger("quicklanshare.ui")


class _LogEmitter(QObject):
    message = Signal(str, str)


class _QtLogHandler(logging.Handler):
    """把 logging 记录转成 Qt 信号，保证在界面线程更新控件。"""

    def __init__(self, emitter: _LogEmitter) -> None:
        super().__init__()
        self._emitter = emitter
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        with contextlib.suppress(Exception):
            self._emitter.message.emit(record.levelname, self.format(record))


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(
        self,
        config: AppConfig,
        config_path: Path,
        logging_session: LoggingSession,
        data_dir: Path | None = None,
        *,
        autostart: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.app_config = config
        self.config_path = config_path
        self.logging_session = logging_session
        self._data_dir = (data_dir or default_data_dir()).resolve()
        self._deadline = 0.0
        self._share_url = ""
        self._files: list[dict[str, Any]] = []
        self._quitting = False
        self._pending_restart = False
        self._tray_available = False
        self._skeleton_started = 0.0
        self._pending_files: list[dict[str, Any]] | None = None
        self._empty_mode = "empty"
        self._fade_animation: Any = None
        self._log_handler: _QtLogHandler | None = None
        self._log_emitter = _LogEmitter(self)
        self._autostart = autostart

        self.backend = Backend(self)
        self._build_ui()
        self._setup_tray()
        self._restore_geometry()
        self._connect_signals()
        self._install_log_bridge()
        self._set_running(False)
        self._update_countdown()
        self._log_dot.hide()

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._update_countdown)
        self._countdown_timer.start()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(15000)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start()

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(5000)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start()

        if autostart:
            self._set_empty_state("正在加载", "正在启动共享服务…", glyph="clock", action=None)
            self.file_stack.setCurrentWidget(self.empty_state)
            QTimer.singleShot(80, self.start_server)
        else:
            self._set_status("warn", "未启动")
            self._set_empty_state(
                "服务未启动",
                "点击“启动服务”开启局域网文件共享与文本共享。",
                glyph="stop",
                action="启动服务",
                mode="start",
            )
            self.file_stack.setCurrentWidget(self.empty_state)

    # ================================================================ UI build
    def _build_ui(self) -> None:
        self.setWindowTitle(window_title())
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(900, 480)
        self.setAcceptDrops(True)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("MainSplitter")
        self.splitter.setHandleWidth(12)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_files_column())
        self.text_panel = TextPanel()
        self.splitter.addWidget(self.text_panel)
        self.splitter.setStretchFactor(0, 62)
        self.splitter.setStretchFactor(1, 38)
        self.splitter.setSizes([720, 460])

        body_wrapper = QWidget()
        body_layout = QHBoxLayout(body_wrapper)
        body_layout.setContentsMargins(16, 12, 16, 8)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.splitter)
        outer.addWidget(body_wrapper, 1)

        outer.addWidget(self._build_status_bar())

        self.toast = Toast(self)
        self.connection_popup = ConnectionPopup(self)
        self.log_drawer = LogsDrawer(self)
        self.log_panel = self.log_drawer.panel

        self.empty_state.set_state(
            "暂无共享文件", "上传或拖拽文件后，这里会显示文件列表", action_text="选择文件上传"
        )
        self.file_table.apply_column_widths(self.app_config.ui.column_widths)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(64)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(32, 32))
        logo.setFixedSize(32, 32)
        layout.addWidget(logo)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        name = QLabel(__software_name__)
        name.setObjectName("BrandName")
        brand.addWidget(name)
        tagline = QLabel("局域网文件快传 · 桌面版")
        tagline.setObjectName("BrandSub")
        brand.addWidget(tagline)
        layout.addLayout(brand)

        version = QLabel(f"v{__version__}")
        version.setObjectName("VersionBadge")
        layout.addWidget(version, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(14)

        self.status_chip = QLabel("正在启动")
        self.status_chip.setObjectName("StatusChip")
        self.status_chip.setProperty("state", "busy")
        layout.addWidget(self.status_chip)

        self.address_button = QPushButton("服务未启动")
        self.address_button.setProperty("role", "address")
        self.address_button.setIcon(icons.glyph_icon("link", size=14, color=theme.ACCENT))
        self.address_button.setIconSize(QSize(14, 14))
        self.address_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.address_button.setMinimumWidth(120)
        self.address_button.setMaximumWidth(280)
        self.address_button.setToolTip("查看二维码与连接信息")
        layout.addWidget(self.address_button)
        layout.addStretch(1)

        self.open_web_button = QPushButton("打开网页")
        self.open_web_button.setProperty("role", "soft")
        self.open_web_button.setIcon(icons.glyph_icon("globe", size=15, color=theme.ACCENT))
        self.open_web_button.setIconSize(QSize(15, 15))
        self.open_web_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_web_button.setToolTip("在默认浏览器中打开共享页面")
        layout.addWidget(self.open_web_button)

        self.power_button = QPushButton()
        self.power_button.setProperty("role", "icon")
        self.power_button.setIcon(icons.glyph_icon("play", size=15))
        self.power_button.setIconSize(QSize(15, 15))
        self.power_button.setFixedSize(34, 34)
        self.power_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.power_button.setToolTip("启动服务")
        layout.addWidget(self.power_button)

        self.settings_button = QPushButton()
        self.settings_button.setProperty("role", "icon")
        self.settings_button.setIcon(icons.glyph_icon("settings", size=16))
        self.settings_button.setIconSize(QSize(16, 16))
        self.settings_button.setFixedSize(34, 34)
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("设置")
        layout.addWidget(self.settings_button)

        self.more_button = QPushButton("⋯")
        self.more_button.setProperty("role", "icon")
        self.more_button.setFixedSize(34, 34)
        self.more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_button.setToolTip("更多")
        self.more_menu = QMenu(self)
        data_action = QAction("数据目录", self.more_menu)
        data_action.triggered.connect(self.open_data_dir)
        self.more_menu.addAction(data_action)
        logs_action = QAction("日志目录", self.more_menu)
        logs_action.triggered.connect(self.open_log_dir)
        self.more_menu.addAction(logs_action)
        about_action = QAction("关于", self.more_menu)
        about_action.triggered.connect(self.open_about)
        self.more_menu.addAction(about_action)
        self.more_menu.addSeparator()
        quit_action = QAction("退出程序", self.more_menu)
        quit_action.triggered.connect(self.request_quit)
        self.more_menu.addAction(quit_action)
        self.more_button.setMenu(self.more_menu)
        layout.addWidget(self.more_button)
        return header

    def _build_files_column(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.drop_zone = DropZone(compact=True)
        layout.addWidget(self.drop_zone)

        self.transfer_panel = TransferPanel()
        layout.addWidget(self.transfer_panel)

        files_card = QFrame()
        files_card.setObjectName("Card")
        theme.add_shadow(files_card)
        files_layout = QVBoxLayout(files_card)
        files_layout.setContentsMargins(16, 12, 16, 12)
        files_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("共享文件")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        self.file_count_label = QLabel("共 0 个")
        self.file_count_label.setObjectName("Muted")
        header.addWidget(self.file_count_label)
        header.addStretch(1)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setProperty("role", "refresh")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(self.refresh_button)
        self.zip_button = QPushButton("打包下载")
        self.zip_button.setProperty("role", "soft")
        self.zip_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zip_button.setEnabled(False)
        header.addWidget(self.zip_button)
        self.delete_button = QPushButton("删除所选")
        self.delete_button.setProperty("role", "danger")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.setEnabled(False)
        header.addWidget(self.delete_button)
        files_layout.addLayout(header)

        self.file_stack = QStackedWidget()
        self.file_stack.setMinimumHeight(220)
        self.file_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.skeleton = SkeletonList(rows=5)
        self.file_table = FileTable()
        self.empty_state = EmptyState()
        self.file_stack.addWidget(self.skeleton)
        self.file_stack.addWidget(self.file_table)
        self.file_stack.addWidget(self.empty_state)
        self.file_stack.setCurrentWidget(self.skeleton)
        files_layout.addWidget(self.file_stack, 1)
        layout.addWidget(files_card, 1)
        return column

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(34)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(8)

        self.data_button = QPushButton("数据目录")
        self.data_button.setProperty("role", "link")
        self.data_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.data_button.setToolTip(str(self._data_dir))
        layout.addWidget(self.data_button)
        layout.addWidget(self._dot())
        self.status_online = QLabel("在线 0")
        self.status_online.setObjectName("Muted")
        layout.addWidget(self.status_online)
        layout.addWidget(self._dot())
        self.status_countdown = QLabel("未启动")
        self.status_countdown.setObjectName("Muted")
        layout.addWidget(self.status_countdown)
        self.adjust_button = QPushButton("调整")
        self.adjust_button.setProperty("role", "link")
        self.adjust_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.adjust_button.setToolTip("调整自动关闭时长")
        layout.addWidget(self.adjust_button)
        layout.addStretch(1)

        self._log_dot = QLabel("●")
        self._log_dot.setStyleSheet(f"color: {theme.DANGER}; font-size: 11px;")
        self._log_dot.setToolTip("有新错误，点击查看日志")
        self._log_dot.setFixedWidth(10)
        self._log_dot.hide()
        layout.addWidget(self._log_dot)
        self.logs_button = QPushButton("日志")
        self.logs_button.setProperty("role", "link")
        self.logs_button.setIcon(icons.glyph_icon("file", size=14, color=theme.TEXT_SECONDARY))
        self.logs_button.setIconSize(QSize(14, 14))
        self.logs_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logs_button.setToolTip("查看运行日志")
        layout.addWidget(self.logs_button)
        return bar

    @staticmethod
    def _dot() -> QLabel:
        label = QLabel("·")
        label.setObjectName("Muted")
        return label

    # ============================================================ interactions
    def _connect_signals(self) -> None:
        self.drop_zone.filesDropped.connect(self.upload_paths)
        self.drop_zone.browseRequested.connect(self.choose_files)
        self.empty_state.actionRequested.connect(self._on_empty_action)
        self.file_table.downloadRequested.connect(self.save_download)
        self.file_table.deleteRequested.connect(self.delete_files)
        self.file_table.copyLinkRequested.connect(self.copy_file_link)
        self.file_table.selectionCountChanged.connect(self._on_selection_changed)
        self.refresh_button.clicked.connect(lambda: self.load_files(show_skeleton=False))
        self.zip_button.clicked.connect(self.download_zip)
        self.delete_button.clicked.connect(
            lambda: self.delete_files(self.file_table.selected_names())
        )
        self.data_button.clicked.connect(self.open_data_dir)
        self.adjust_button.clicked.connect(self.open_settings)
        self.logs_button.clicked.connect(self._toggle_logs)
        self.address_button.clicked.connect(self.open_connection_popup)
        self.open_web_button.clicked.connect(self.open_web)
        self.power_button.clicked.connect(self._on_service_button)
        self.settings_button.clicked.connect(self.open_settings)
        self.connection_popup.copyRequested.connect(self.copy_share_url)
        self.connection_popup.openWebRequested.connect(self.open_web)
        self.transfer_panel.cancelRequested.connect(self.backend.cancel_transfer)
        self.log_drawer.panel.openLogDirRequested.connect(self.open_log_dir)
        self.log_drawer.visibilityChanged.connect(self._on_log_drawer_visibility)
        self.log_drawer.panel.errorReceived.connect(self._on_log_error)

        self.text_panel.sendRequested.connect(self.backend.send_chat)
        self.text_panel.deleteRequested.connect(self.backend.delete_chat)
        self.text_panel.historyRefreshRequested.connect(self.backend.refresh_chat)

        self.backend.started.connect(self._on_started)
        self.backend.start_failed.connect(self._on_start_failed)
        self.backend.stopped.connect(self._on_stopped)
        self.backend.files_loaded.connect(self._on_files_loaded)
        self.backend.files_failed.connect(self._on_files_failed)
        self.backend.room_updated.connect(self._on_room_updated)
        self.backend.delete_finished.connect(self._on_delete_finished)
        self.backend.operation_failed.connect(self._on_operation_failed)
        self.backend.auto_shutdown_changed.connect(self._on_auto_shutdown_changed)
        self.backend.upload_started.connect(self._on_upload_started)
        self.backend.upload_progress.connect(self.transfer_panel.update_task)
        self.backend.upload_finished.connect(self._on_transfer_finished)
        self.backend.download_started.connect(self._on_download_started)
        self.backend.download_progress.connect(self.transfer_panel.update_task)
        self.backend.download_finished.connect(self._on_transfer_finished)
        self.backend.chat_history.connect(self.text_panel.set_history)
        self.backend.chat_message.connect(self.text_panel.append_message)
        self.backend.chat_deleted.connect(self.text_panel.remove_message)
        self.backend.chat_status.connect(self.text_panel.set_sync_status)
        self.backend.chat_error.connect(self._on_chat_error)

    def _install_log_bridge(self) -> None:
        self._log_emitter.message.connect(self.log_panel.append_message)
        self._log_handler = _QtLogHandler(self._log_emitter)
        self.logging_session.logger.addHandler(self._log_handler)
        logger.info("界面已就绪，等待启动服务")

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("系统托盘不可用，关闭窗口将直接退出")
            self._tray_available = False
            return
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip(window_title())
        menu = QMenu(self)
        show_action = QAction("显示主界面", menu)
        show_action.triggered.connect(self.show_from_tray)
        menu.addAction(show_action)
        web_action = QAction("打开网页", menu)
        web_action.triggered.connect(self.open_web)
        menu.addAction(web_action)
        menu.addSeparator()
        quit_action = QAction("退出程序", menu)
        quit_action.triggered.connect(self.request_quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._tray_available = True

    def _restore_geometry(self) -> None:
        window = self.app_config.window
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 800)
        min_width = max(720, min(900, available.width() - 40))
        min_height = max(380, min(480, available.height() - 60))
        self.setMinimumSize(min_width, min_height)
        self.resize(
            max(min_width, min(window.width, available.width() - 40)),
            max(min_height, min(window.height, available.height() - 60)),
        )
        if window.x is not None and window.y is not None:
            rect = QRect(window.x, window.y, window.width, window.height)
            for screen_item in QGuiApplication.screens():
                if screen_item.availableGeometry().intersects(rect):
                    self.move(window.x, window.y)
                    break
        if window.maximized:
            self.setWindowState(Qt.WindowState.WindowMaximized)

    # =============================================================== lifecycle
    def start_server(self) -> None:
        if self.backend.is_running:
            return
        self._set_status("busy", "正在启动…")
        self.power_button.setEnabled(False)
        self._set_empty_state("正在加载", "正在启动共享服务…", glyph="clock", action=None)
        self.file_stack.setCurrentWidget(self.empty_state)
        logger.info("正在启动服务（端口 %s）", self.app_config.server.port)
        try:
            config = self._build_server_config()
        except Exception as exc:
            logger.exception("准备服务配置失败")
            self._on_start_failed(str(exc))
            return
        self._data_dir = config.data_dir
        self.data_button.setToolTip(str(self._data_dir))
        if config.fallback_reason:
            logger.warning(config.fallback_reason)
            self.toast.show_message(config.fallback_reason, duration=4200)
        if not self.backend.start_server(config):
            self.power_button.setEnabled(True)

    def _build_server_config(self) -> Config:
        server = self.app_config.server
        config = Config(
            host=server.host,
            port=server.port,
            data_dir=self._data_dir,
            auto_shutdown_enabled=server.auto_shutdown_enabled,
            auto_shutdown_hours=server.auto_shutdown_hours,
            open_browser=False,
            log_level=self.app_config.ui.log_level,
        )
        config.ensure_dirs()
        return config

    def _on_started(self, port: int, share_url: str, deadline: float) -> None:
        self._share_url = share_url
        self._deadline = deadline
        self.address_button.setText(self._address_text(share_url))
        self.address_button.setToolTip(share_url)
        self.connection_popup.set_info(share_url, f"http://127.0.0.1:{port}", 0)
        self._set_running(True)
        self._set_status("ok", "运行中")
        self.text_panel.set_service_available(True)
        logger.info("服务已就绪：%s", share_url)
        self.toast.show_message("服务已启动，局域网内可扫码访问")
        self.load_files(show_skeleton=True)
        self.backend.refresh_room_info()
        if self.app_config.server.open_browser:
            self.open_web()

    def _on_start_failed(self, message: str) -> None:
        self._set_running(False)
        self._set_status("error", "启动失败")
        self.text_panel.set_service_available(False)
        self._set_empty_state(
            "服务启动失败",
            message,
            glyph="warning",
            action="重试",
            tone="error",
            mode="start",
        )
        self.file_stack.setCurrentWidget(self.empty_state)
        logger.error("服务启动失败: %s", message)
        self.toast.show_message(f"启动失败：{message}", duration=4200)

    def _on_stopped(self, reason: str) -> None:
        self._deadline = 0.0
        self._share_url = ""
        self._set_running(False)
        self.text_panel.set_service_available(False)
        self.address_button.setText("服务未启动")
        self.address_button.setToolTip("服务未启动")
        self.connection_popup.clear()
        self.status_online.setText("在线 0")
        self._update_countdown()
        logger.info("服务已停止（%s）", reason)
        if self._quitting:
            self._finalize_quit()
            return
        if reason == "auto-shutdown":
            self.toast.show_message("已到自动关闭时间，程序即将退出", duration=3200)
            self._quitting = True
            self._save_settings()
            QTimer.singleShot(600, self._finalize_quit)
            return
        if self._pending_restart:
            self._pending_restart = False
            QTimer.singleShot(200, self.start_server)
            return
        self._set_status("warn", "已停止")
        self._set_empty_state(
            "服务已停止",
            "局域网共享已关闭。点击“启动服务”可重新开启。",
            glyph="stop",
            action="启动服务",
            mode="start",
        )
        self.file_stack.setCurrentWidget(self.empty_state)
        self.toast.show_message("服务已停止")

    def _on_service_button(self) -> None:
        if self.backend.is_running:
            if not self._confirm(
                "停止服务",
                "停止后局域网内的设备将无法访问共享页面。确定停止服务吗？",
                "停止服务",
                danger=True,
            ):
                return
            self.power_button.setEnabled(False)
            self._set_status("busy", "正在停止…")
            logger.info("用户请求停止服务")
            self.backend.stop_server("user-stop")
        else:
            self.start_server()

    def request_quit(self) -> None:
        if self._quitting:
            return
        if self.backend.active_transfers > 0 and not self._confirm(
            "退出程序",
            f"还有 {self.backend.active_transfers} 个传输任务未完成，退出会中断它们。确定退出吗？",
            "退出",
            danger=True,
        ):
            return
        self._quitting = True
        self._save_settings()
        if self.backend.is_running:
            self._set_status("busy", "正在退出…")
            logger.info("用户退出程序，正在停止服务")
            self.backend.stop_server("app-exit")
            QTimer.singleShot(6000, self._force_quit)
        else:
            self._finalize_quit()

    def _finalize_quit(self) -> None:
        self._save_settings()
        if self._log_handler is not None:
            self.logging_session.logger.removeHandler(self._log_handler)
            self._log_handler = None
        if getattr(self, "tray", None) is not None:
            self.tray.hide()
        logger.info("程序退出")
        QApplication.quit()

    def _force_quit(self) -> None:
        if not self._quitting:
            return
        logger.warning("停止服务超时，执行强制退出")
        QApplication.quit()

    # ================================================================ settings
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.app_config, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        previous = self.app_config
        updated = dialog.result_config
        updated.window = previous.window
        self.app_config = updated
        self._save_settings()
        set_log_level(updated.ui.log_level)
        logger.info("设置已保存")
        port_changed = previous.server.port != updated.server.port
        if port_changed:
            if self.backend.is_running:
                if self._confirm(
                    "重启服务",
                    "端口已修改，需要重启服务才能生效。现在重启吗？",
                    "立即重启",
                ):
                    self._pending_restart = True
                    self._set_status("busy", "正在重启…")
                    self.backend.stop_server("restart")
                else:
                    logger.info("端口修改将在下次启动服务时生效")
            else:
                logger.info("端口已保存，启动服务时生效")
        self.backend.apply_auto_shutdown(
            updated.server.auto_shutdown_enabled, updated.server.auto_shutdown_hours
        )
        self.toast.show_message("设置已保存")

    def _save_settings(self) -> None:
        try:
            apply_window_geometry(self.app_config, self)
            self.app_config.ui.column_widths = self.file_table.column_widths()
            save_config(self.app_config, self.config_path)
        except OSError:
            logger.exception("保存配置失败")

    def open_about(self) -> None:
        notices = app_base_dir() / "THIRD-PARTY-NOTICES.md"
        AboutDialog(notices, self).exec()

    # ================================================================== files
    def load_files(self, *, show_skeleton: bool = False) -> None:
        if show_skeleton:
            self.skeleton.start()
            self._skeleton_started = time.monotonic()
            self.file_stack.setCurrentWidget(self.skeleton)
        self.backend.refresh_files()

    def _on_files_loaded(self, files: list[Any]) -> None:
        clean = [item for item in files if isinstance(item, dict)]
        if self.file_stack.currentWidget() is self.skeleton:
            elapsed = time.monotonic() - self._skeleton_started
            delay = max(0, int((0.45 - elapsed) * 1000))
            self._pending_files = clean
            QTimer.singleShot(delay, self._apply_pending_files)
        else:
            self._apply_files(clean)

    def _apply_pending_files(self) -> None:
        if self._pending_files is None:
            return
        files = self._pending_files
        self._pending_files = None
        self._apply_files(files)

    def _apply_files(self, files: list[dict[str, Any]]) -> None:
        self._files = files
        self.skeleton.stop()
        self.file_table.set_files(files)
        self.file_count_label.setText(f"共 {len(files)} 个")
        if files:
            self.file_stack.setCurrentWidget(self.file_table)
            self._fade_in(self.file_table)
        else:
            self._set_empty_state(
                "暂无共享文件",
                "把文件拖到上方区域，或点击按钮选择文件上传。",
                glyph="folder",
                action="选择文件上传",
            )
            self.file_stack.setCurrentWidget(self.empty_state)
            self._fade_in(self.empty_state)
        self._on_selection_changed(len(self.file_table.selected_names()))

    def _on_files_failed(self, message: str) -> None:
        self.skeleton.stop()
        self._set_empty_state(
            "无法读取文件列表",
            message,
            glyph="warning",
            action="重试",
            tone="error",
            mode="reload",
        )
        self.file_stack.setCurrentWidget(self.empty_state)
        logger.warning("读取文件列表失败: %s", message)

    def _set_empty_state(
        self,
        title: str,
        detail: str,
        *,
        glyph: str = "folder",
        action: str | None = None,
        tone: str = "muted",
        mode: str = "empty",
    ) -> None:
        self._empty_mode = mode
        self.empty_state.set_state(title, detail, glyph=glyph, action_text=action, tone=tone)

    def _on_empty_action(self) -> None:
        if self._empty_mode == "reload":
            self.load_files(show_skeleton=True)
        elif self._empty_mode == "start":
            self.start_server()
        else:
            self.choose_files()

    def _on_selection_changed(self, count: int) -> None:
        self.delete_button.setEnabled(count > 0 and self.backend.is_running)
        if self.backend.is_running:
            self.zip_button.setEnabled(bool(self._files))

    def choose_files(self) -> None:
        if not self.backend.is_running:
            self.toast.show_message("服务未运行，请先启动服务", duration=2400)
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要共享的文件")
        if paths:
            self.upload_paths(paths)

    def upload_paths(self, paths: list[Any]) -> None:
        if not self.backend.is_running:
            self.toast.show_message("服务未运行，请先启动服务", duration=2400)
            return
        files = [Path(path) for path in paths if Path(path).is_file()]
        if not files:
            return
        logger.info("开始上传 %d 个文件", len(files))
        self.backend.upload_paths(files)

    def save_download(self, name: str) -> None:
        if not self.backend.is_running:
            self.toast.show_message("服务未运行，无法下载", duration=2400)
            return
        target, _ = QFileDialog.getSaveFileName(self, "保存文件", str(downloads_dir() / name))
        if not target:
            return
        logger.info("下载文件 %s -> %s", name, target)
        self.backend.download_file(name, Path(target))

    def download_zip(self) -> None:
        if not self.backend.is_running:
            self.toast.show_message("服务未运行，无法下载", duration=2400)
            return
        names = self.file_table.selected_names()
        if not names:
            names = [str(item.get("name")) for item in self._files if item.get("name")]
        if not names:
            self.toast.show_message("没有可打包的文件", duration=2400)
            return
        default_name = f"QuickLanShare_{time.strftime('%Y%m%d_%H%M%S')}.zip"
        target, _ = QFileDialog.getSaveFileName(
            self, "打包下载", str(downloads_dir() / default_name), "ZIP 压缩包 (*.zip)"
        )
        if not target:
            return
        logger.info("打包下载 %d 个文件", len(names))
        self.backend.download_zip(names, Path(target))

    def delete_files(self, names: list[str]) -> None:
        if not names:
            return
        if not self.backend.is_running:
            self.toast.show_message("服务未运行，无法删除", duration=2400)
            return
        preview = "、".join(names[:3]) + ("…" if len(names) > 3 else "")
        if not self._confirm(
            "删除文件",
            f"确定删除 {len(names)} 个文件吗？\n{preview}\n删除后无法恢复。",
            "删除",
            danger=True,
        ):
            return
        logger.info("请求删除 %d 个文件", len(names))
        self.backend.delete_files(names)

    def copy_share_url(self) -> None:
        url = self._share_url or self.backend.share_url
        if not url:
            self.toast.show_message("服务尚未启动", duration=2000)
            return
        QGuiApplication.clipboard().setText(url)
        self.toast.show_message("已复制共享链接")

    def copy_file_link(self, name: str) -> None:
        base = self._share_url or self.backend.share_url
        if not base:
            self.toast.show_message("服务尚未启动", duration=2000)
            return
        QGuiApplication.clipboard().setText(f"{base}/api/download/{quote(name, safe='')}")
        self.toast.show_message("已复制文件下载链接")

    # =============================================================== transfers
    def _on_upload_started(self, task_id: str, name: str, size: int) -> None:
        self.transfer_panel.add_task(task_id, name, "upload")
        self.transfer_panel.update_task(task_id, 0, size)
        logger.info("开始上传 %s (%s)", name, human_size(size))

    def _on_download_started(self, task_id: str, name: str, size: int) -> None:
        self.transfer_panel.add_task(task_id, name, "download")
        logger.info("开始下载 %s", name)

    def _on_transfer_finished(self, task_id: str, name: str, ok: bool, message: str) -> None:
        self.transfer_panel.finish_task(task_id, ok, message)
        if ok:
            self.toast.show_message(f"{name or '传输'}：{message}" if message else "传输完成")
        elif message and message != "已取消":
            self.toast.show_message(f"{name or '传输'}：{message}", duration=3600)
            logger.warning("传输失败 %s: %s", name, message)
        if self.file_stack.currentWidget() is not self.skeleton:
            self.backend.refresh_files()

    # ================================================================ statuses
    def _set_running(self, running: bool) -> None:
        self.drop_zone.setEnabled(running)
        self.open_web_button.setEnabled(running)
        self.refresh_button.setEnabled(running)
        self.zip_button.setEnabled(running and bool(self._files))
        self.delete_button.setEnabled(running and bool(self.file_table.selected_names()))
        self.power_button.setEnabled(True)
        if running:
            self.power_button.setIcon(icons.glyph_icon("power", size=15, color=theme.DANGER))
            self.power_button.setToolTip("停止服务")
            self.power_button.setProperty("tone", "danger")
        else:
            self.power_button.setIcon(icons.glyph_icon("play", size=15, color=theme.SUCCESS))
            self.power_button.setToolTip("启动服务")
            self.power_button.setProperty("tone", "success")
        self.power_button.style().unpolish(self.power_button)
        self.power_button.style().polish(self.power_button)
        if not running:
            self.status_countdown.setText("未启动")
            self.status_countdown.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")

    def _set_status(self, state: str, text: str) -> None:
        self.status_chip.setText(text)
        self.status_chip.setProperty("state", state)
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)

    def _update_countdown(self) -> None:
        if not self.backend.is_running:
            self.status_countdown.setText("未启动")
            self.status_countdown.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
            return
        if not self._deadline:
            self.status_countdown.setText("不自动关闭")
            self.status_countdown.setStyleSheet(f"color: {theme.SUCCESS}; font-size: 11px;")
            return
        remaining = max(0, int(self._deadline - time.time()))
        text = human_time(remaining)
        color = theme.DANGER if remaining <= 300 else theme.TEXT_SECONDARY
        self.status_countdown.setText(f"自动关闭 {text}")
        self.status_countdown.setStyleSheet(f"color: {color}; font-size: 11px;")
        if remaining <= 0:
            self.status_countdown.setText("正在自动关闭…")

    def _on_auto_shutdown_changed(self, enabled: bool, deadline: float) -> None:
        self._deadline = deadline if enabled else 0.0
        self._update_countdown()
        state = "已开启" if enabled else "已关闭"
        logger.info("自动关闭设置已更新：%s", state)
        self.toast.show_message(f"自动关闭{state}")

    def _on_room_updated(self, info: dict[str, Any]) -> None:
        online = int(info.get("total_clients") or 0)
        files = int(info.get("total_files") or 0)
        self.status_online.setText(f"在线 {online}")
        self.connection_popup.set_online(online)
        if (
            files != len(self._files)
            and self.backend.is_running
            and not self.backend.active_transfers
        ):
            # 网页端上传/删除后，让列表跟上服务端统计。
            self.load_files(show_skeleton=False)
        version = str(info.get("version") or "")
        if version and version != __version__:
            logger.warning("服务端版本 %s 与界面版本 %s 不一致", version, __version__)

    def _on_delete_finished(self, deleted: list[Any], failed: list[Any]) -> None:
        if deleted:
            self.toast.show_message(f"已删除 {len(deleted)} 个文件")
        if failed:
            self.toast.show_message(f"{len(failed)} 个文件删除失败", duration=3600)
            logger.warning("部分文件删除失败: %s", failed)

    def _on_operation_failed(self, message: str) -> None:
        logger.error(message)
        self.toast.show_message(message, duration=3600)

    def _on_chat_error(self, message: str) -> None:
        logger.warning(message)
        self.text_panel.show_error(message)

    def _refresh_stats(self) -> None:
        if self.backend.is_running:
            self.backend.refresh_room_info()

    def _auto_refresh(self) -> None:
        if not self.backend.is_running or self.backend.active_transfers:
            return
        if self.isMinimized() and self._tray_available:
            return
        self.backend.refresh_files()

    # ================================================================= window
    def open_connection_popup(self) -> None:
        if not self.backend.is_running:
            self.toast.show_message("服务尚未启动", duration=2200)
            return
        if self.connection_popup.isVisible():
            self.connection_popup.hide()
            return
        self.connection_popup.show_near(self.address_button)

    def open_web(self) -> None:
        url = self._share_url or self.backend.share_url
        if not url:
            self.toast.show_message("服务尚未启动", duration=2200)
            return
        QDesktopServices.openUrl(QUrl(url))

    def open_data_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._data_dir)))

    def open_log_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.logging_session.log_dir)))

    def _toggle_logs(self) -> None:
        self.log_drawer.toggle()
        if self.log_drawer.is_open:
            self._log_dot.hide()

    def _on_log_drawer_visibility(self, visible: bool) -> None:
        if visible:
            self._log_dot.hide()

    def _on_log_error(self) -> None:
        if not self.log_drawer.is_open:
            self._log_dot.show()

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.show_from_tray()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_settings()
        if self._quitting:
            event.accept()
            return
        if self._tray_available and self.app_config.ui.close_to_tray:
            event.ignore()
            self.hide()
            if not self.app_config.ui.tray_hint_shown:
                self.app_config.ui.tray_hint_shown = True
                self._save_settings()
                if getattr(self, "tray", None) is not None:
                    self.tray.showMessage(
                        __software_name__,
                        "程序已最小化到系统托盘，仍在后台提供局域网共享。",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000,
                    )
            logger.info("窗口关闭到系统托盘")
            return
        event.ignore()
        self.request_quit()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape and self.log_drawer.is_open:
            self.log_drawer.hide_drawer()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if getattr(self, "toast", None) is not None:
            self.toast.reposition()
        if getattr(self, "log_drawer", None) is not None:
            self.log_drawer.reposition()

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).is_file()
        ]
        if paths:
            self.upload_paths(paths)
            event.acceptProposedAction()

    def _fade_in(self, widget: QWidget) -> None:
        from PySide6.QtCore import QPropertyAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(220)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(
            lambda: widget.setGraphicsEffect(None)  # type: ignore[arg-type]
        )
        self._fade_animation = animation
        animation.start()

    def _confirm(
        self,
        title: str,
        text: str,
        accept_text: str,
        *,
        danger: bool = False,
    ) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
        box.setText(text)
        accept = box.addButton(accept_text, QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is accept

    @staticmethod
    def _address_text(url: str) -> str:
        if not url:
            return "服务未启动"
        return url.split("://", 1)[-1]

    @property
    def data_dir(self) -> Path:
        return self._data_dir


def downloads_dir() -> Path:
    """用户下载目录（不存在时回退到主目录）。"""
    from PySide6.QtCore import QStandardPaths

    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    path = Path(location) if location else Path.home() / "Downloads"
    return path if path.exists() else Path.home()


def run_window(
    config: AppConfig,
    config_path: Path,
    logging_session: LoggingSession,
    data_dir: Path,
    *,
    autostart: bool = True,
) -> MainWindow:
    """构造并返回主窗口（不进入事件循环，便于测试）。"""
    return MainWindow(
        config,
        config_path,
        logging_session,
        data_dir,
        autostart=autostart,
    )


def application_size_hint() -> QSize:
    return QSize(1200, 800)


__all__ = ["MainWindow", "application_size_hint", "run_window"]
