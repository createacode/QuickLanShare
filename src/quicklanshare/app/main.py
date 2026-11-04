"""应用入口：解析参数、初始化日志 / 配置 / 主题，创建主窗口。

``main()`` 是全工程唯一的启动实现；根 ``main.py``、``__main__.py`` 与
``gui-scripts`` 只做薄包装。
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from ..core.version import __software_name__, __version__
from ..services.config import Config
from ..ui import icons, theme
from ..ui.main_window import MainWindow
from ..utils.app_config import AppConfig, load_config
from ..utils.logging_setup import (
    close_fault_handler,
    install_crash_handlers,
    log_system_info,
    setup_logging,
)
from ..utils.paths import app_base_dir, app_icon_path, default_data_dir
from .single_instance import SingleInstanceGuard

logger = logging.getLogger("quicklanshare.app")

_QT_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=__software_name__,
        description="局域网文件快速传输桌面工具",
    )
    parser.add_argument("--version", action="version", version=f"{__software_name__} {__version__}")
    parser.add_argument("--debug", action="store_true", help="本次运行输出调试日志")
    parser.add_argument("--config", type=Path, default=None, help="指定配置文件的完整路径")
    parser.add_argument(
        "--autostart",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def _qt_message_handler(mode: QtMsgType, context: object, message: str) -> None:
    if message.startswith("QFont::") or "Could not parse stylesheet" in message:
        logger.debug("Qt: %s", message)
        return
    logger.log(_QT_LEVELS.get(mode, logging.INFO), "Qt: %s", message)


def _apply_cli_overrides(config: AppConfig, args: argparse.Namespace) -> None:
    if args.debug:
        config.ui.log_level = "DEBUG"


def main(argv: Sequence[str] | None = None) -> int:
    """应用主入口，返回进程退出码。"""
    arguments = list(sys.argv if argv is None else argv)
    parser = build_parser()
    args, qt_args = parser.parse_known_args(arguments[1:])
    program_args = [arguments[0], *qt_args]

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(program_args)
    app.setApplicationName(__software_name__)
    app.setOrganizationName("XAF")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(icons.app_icon())
    qInstallMessageHandler(_qt_message_handler)
    theme.apply_theme(app)

    config_path = args.config
    config_result = load_config(config_path)
    config = config_result.config
    _apply_cli_overrides(config, args)

    data_seed = Config(
        data_dir=default_data_dir(),
        auto_shutdown_enabled=config.server.auto_shutdown_enabled,
        auto_shutdown_hours=config.server.auto_shutdown_hours,
        open_browser=False,
        log_level=config.ui.log_level,
    )
    session = setup_logging(data_seed.log_dir, level=config.ui.log_level)
    fault_stream, _original_hook = install_crash_handlers(session.logger, session.log_dir)
    log_system_info(session.logger, app_base_dir(), data_seed.data_dir)
    _frozen_sanity()
    for message in config_result.messages:
        session.logger.warning(message)
    if config_result.fallback_reason:
        session.logger.warning(config_result.fallback_reason)
    if session.fallback_reason:
        session.logger.warning(session.fallback_reason)

    guard = SingleInstanceGuard(__software_name__)
    if not guard.acquire():
        session.logger.info("已有实例在运行，本次启动退出")
        close_fault_handler(fault_stream)
        return 0

    window: MainWindow | None = None
    start_hidden = bool(args.silent or (args.autostart and config.ui.autostart_silent))
    try:
        window = MainWindow(
            config,
            config_result.path,
            session,
            data_dir=data_seed.data_dir,
            autostart=True,
            start_hidden=start_hidden,
        )
        guard.activated.connect(window.show_from_tray)
        if start_hidden and window.tray_available:
            session.logger.info("静默自启：主界面不显示，仅托盘运行")
        else:
            if start_hidden:
                session.logger.warning("系统托盘不可用，静默自启降级为显示主界面")
            window.show()
            session.logger.info("界面已显示，配置文件: %s", config_result.path)
        exit_code = app.exec()
    except Exception:
        details = traceback.format_exc()
        logger.critical("应用启动失败\n%s", details)
        with contextlib.suppress(Exception):  # pragma: no cover - 无可用界面时
            QMessageBox.critical(
                None,
                f"{__software_name__} 启动失败",
                f"程序遇到无法恢复的错误：\n\n{details[-1200:]}",
            )
        exit_code = 1
    finally:
        if window is not None:
            window._save_settings()
            window._quitting = True
            if window.backend.is_running:
                window.backend.stop_server("app-exit")
                window.backend.wait_stopped(3.0)
        close_fault_handler(fault_stream)
        session.logger.info("进程退出，退出码 %s", exit_code)
        logging.shutdown()
    return exit_code


def _frozen_sanity() -> None:
    """冻结态自检：确认 Qt 平台插件被收集，缺失时写入日志。"""
    if not getattr(sys, "frozen", False):
        return
    plugin = Path(getattr(sys, "_MEIPASS", "")) / "PySide6" / "plugins" / "platforms"
    if not plugin.exists():
        logger.error("未找到 Qt 平台插件目录: %s", plugin)
    icon = app_icon_path()
    if not icon.exists():
        logger.error("未找到应用图标: %s", icon)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
