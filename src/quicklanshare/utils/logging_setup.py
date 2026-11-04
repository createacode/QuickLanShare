"""日志系统：时间戳文件、按大小轮转、按天/数量清理、崩溃落盘。

命名规则：``log_YYYYMMDD_HHMMSS_NN.log``（``NN`` 为同一秒内的序号）。
单个文件不超过 10 MB，保留最近 30 天或最新 100 个文件。
"""

from __future__ import annotations

import contextlib
import faulthandler
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Any

from .paths import ensure_directory, local_appdata_dir

LOG_FILE_RE = re.compile(r"^log_(\d{8})_(\d{6})_(\d{2})\.log$")
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_MAX_FILES = 100
LOGGER_NAME = "quicklanshare"


class SessionFileHandler(logging.Handler):
    """按时间戳命名、按大小切换文件的日志 Handler。"""

    def __init__(
        self,
        directory: Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__()
        self.directory = directory
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self.encoding = encoding
        self.stream: IO[str] | None = None
        self.current_path: Path | None = None
        self.last_error: str | None = None
        self._open_new()

    # ------------------------------------------------------------------ files
    def _open_new(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        for index in range(100):
            candidate = self.directory / f"log_{now:%Y%m%d_%H%M%S}_{index:02d}.log"
            try:
                handle = open(  # noqa: SIM115 - 长期持有的日志流
                    candidate, "x", encoding=self.encoding, newline=""
                )
            except FileExistsError:
                continue
            except OSError as exc:  # pragma: no cover - 磁盘异常
                self.last_error = str(exc)
                return
            self.stream = handle
            self.current_path = candidate
            return
        self.last_error = "同一秒内日志文件过多"

    def _close_stream(self) -> None:
        if self.stream is not None:
            with contextlib.suppress(OSError):
                self.stream.close()
            self.stream = None

    def _rotate(self) -> None:
        self._close_stream()
        self._open_new()

    # ------------------------------------------------------------------- emit
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record) + "\n"
            data = message.encode(self.encoding, errors="replace")
            if self.stream is None:
                self._open_new()
            if self.stream is None:
                return
            if self.current_path is not None:
                try:
                    size = self.current_path.stat().st_size
                except OSError:
                    size = 0
                if size > 0 and size + len(data) > self.max_bytes:
                    self._rotate()
            if self.stream is not None:
                self.stream.write(message)
                self.stream.flush()
        except Exception:
            self.last_error = "日志写入失败"
            self.handleError(record)

    def close(self) -> None:
        self._close_stream()
        super().close()


@dataclass
class LoggingSession:
    """一次日志系统的初始化结果。"""

    logger: logging.Logger
    log_dir: Path
    log_file: Path | None
    fallback_reason: str | None = None
    handler: SessionFileHandler | None = None
    messages: list[str] = field(default_factory=list)


def resolve_log_dir(preferred: Path) -> tuple[Path, str | None]:
    """日志目录：优先 exe 同级 ``logs/``，不可写时回退到 ``%LOCALAPPDATA%``。"""
    try:
        ensure_directory(preferred)
        return preferred, None
    except OSError as exc:
        fallback = local_appdata_dir() / "logs"
        ensure_directory(fallback)
        return fallback, f"日志目录不可写（{exc}），已回退到 {fallback}"


def cleanup_old_logs(
    directory: Path,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    max_files: int = DEFAULT_MAX_FILES,
) -> int:
    """清理过期或超出数量的历史日志，返回删除数量。"""
    try:
        candidates = [path for path in directory.glob("log_*.log") if LOG_FILE_RE.match(path.name)]
    except OSError:
        return 0
    candidates.sort(key=lambda item: item.name, reverse=True)
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for index, path in enumerate(candidates):
        try:
            too_many = index >= max_files
            too_old = path.stat().st_mtime < cutoff
            if too_many or too_old:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def setup_logging(
    log_dir: Path,
    level: str = "INFO",
    *,
    console: bool = True,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> LoggingSession:
    """初始化包级日志，返回日志会话（含实际目录与文件）。"""
    resolved_dir, fallback_reason = resolve_log_dir(log_dir)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(_normalize_level(level))
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        with contextlib.suppress(Exception):  # pragma: no cover - 关闭旧 handler
            handler.close()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    session = LoggingSession(logger=logger, log_dir=resolved_dir, log_file=None)
    file_handler = SessionFileHandler(resolved_dir, max_bytes=max_bytes)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    session.handler = file_handler
    session.log_file = file_handler.current_path
    session.fallback_reason = fallback_reason
    if file_handler.last_error:
        session.messages.append(f"日志文件创建失败: {file_handler.last_error}")

    if console and sys.stderr is not None:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logging.captureWarnings(True)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    # HTTP 访问日志默认只记录警告，避免刷屏界面日志面板；调试时可在设置中调低级别。
    logging.getLogger("quicklanshare.access").setLevel(logging.WARNING)
    removed = cleanup_old_logs(resolved_dir)
    if removed:
        logger.info("已清理 %d 个历史日志文件", removed)
    if fallback_reason:
        logger.warning(fallback_reason)
    return session


def _normalize_level(level: str) -> int:
    name = str(level or "INFO").upper()
    value = getattr(logging, name, logging.INFO)
    return int(value) if isinstance(value, int) else logging.INFO


def set_log_level(level: str) -> None:
    """运行时调整包级日志级别。"""
    logging.getLogger(LOGGER_NAME).setLevel(_normalize_level(level))


def install_crash_handlers(logger: logging.Logger, log_dir: Path) -> tuple[IO[str] | None, Any]:
    """注册 ``sys.excepthook``、``threading.excepthook`` 与 ``faulthandler``。

    返回 ``(faulthandler 文件句柄, 原 excepthook)``，调用方退出时应关闭文件。
    """

    def _log_exception(
        exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        logger.critical("未捕获的异常", exc_info=(exc_type, exc, tb))

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        error = args.exc_value or RuntimeError("未知线程异常")
        logger.critical(
            "线程 %s 未捕获异常",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, error, args.exc_traceback),
        )

    original_hook = sys.excepthook
    sys.excepthook = _log_exception
    threading.excepthook = _thread_hook

    fault_stream: IO[str] | None = None
    try:
        ensure_directory(log_dir)
        fault_path = log_dir / "faulthandler.log"
        fault_stream = open(  # noqa: SIM115 - faulthandler 需要长期持有的句柄
            fault_path, "a", encoding="utf-8"
        )
        faulthandler.enable(fault_stream, all_threads=True)
    except OSError:
        fault_stream = None
    return fault_stream, original_hook


def close_fault_handler(stream: IO[str] | None) -> None:
    """关闭 faulthandler 输出流，退出前调用。"""
    if stream is None:
        return
    try:
        faulthandler.disable()
        stream.close()
    except Exception:  # pragma: no cover - 退出阶段
        pass


def current_log_path(log_dir: Path) -> Path | None:
    """用于测试 / 排错：最近一个日志文件。"""
    try:
        files = sorted(log_dir.glob("log_*.log"), key=lambda item: item.name, reverse=True)
    except OSError:
        return None
    return files[0] if files else None


def log_system_info(logger: logging.Logger, app_dir: Path, data_dir: Path) -> None:
    """启动时写入版本、路径、系统与权限信息。"""
    from ..core.version import __version__
    from .net import is_admin, os_description

    logger.info("QuickLanShare v%s 启动", __version__)
    logger.info("系统: %s | 管理员: %s", os_description(), is_admin())
    logger.info("程序目录: %s", app_dir)
    logger.info("数据目录: %s", data_dir)
    logger.info("Python: %s | 进程: %s", sys.version.split()[0], os.getpid())
