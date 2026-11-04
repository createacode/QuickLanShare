"""界面配置：``config/config.json`` 的读写、校验、备份与迁移。

配置遵循 ``schema_version`` 约定；写入是原子的（临时文件 + ``os.replace``），
写入前保留 ``config.json.bak``；读到损坏内容时改名为 ``config.json.corrupt``
并回退默认值，绝不因配置损坏导致启动失败。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .paths import ensure_directory, local_appdata_dir

SCHEMA_VERSION = 1
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
IP_SCOPES = ("last1", "last2", "last3", "all")
MIN_PORT = 1
MAX_PORT = 65535
MIN_AUTO_SHUTDOWN_HOURS = 0.1
MAX_AUTO_SHUTDOWN_HOURS = 720.0

logger = logging.getLogger("quicklanshare.config")


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(minimum, min(maximum, number))


def _safe_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _safe_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


@dataclass
class WindowState:
    width: int = 1200
    height: int = 800
    x: int | None = None
    y: int | None = None
    maximized: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> WindowState:
        default = cls()
        x_raw = raw.get("x")
        y_raw = raw.get("y")
        return cls(
            width=_clamp_int(raw.get("width"), 800, 8000, default.width),
            height=_clamp_int(raw.get("height"), 520, 8000, default.height),
            x=int(x_raw) if isinstance(x_raw, int) else None,
            y=int(y_raw) if isinstance(y_raw, int) else None,
            maximized=_safe_bool(raw.get("maximized"), False),
        )


@dataclass
class ServerSettings:
    host: str = "0.0.0.0"
    port: int = 8888
    auto_shutdown_enabled: bool = True
    auto_shutdown_hours: float = 24.0
    open_browser: bool = False
    ip_scope: str = "last1"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ServerSettings:
        default = cls()
        scope = _safe_str(raw.get("ip_scope"), default.ip_scope)
        if scope not in IP_SCOPES:
            scope = default.ip_scope
        return cls(
            host=_safe_str(raw.get("host"), default.host),
            port=_clamp_int(raw.get("port"), 1, MAX_PORT, default.port),
            auto_shutdown_enabled=_safe_bool(
                raw.get("auto_shutdown_enabled"), default.auto_shutdown_enabled
            ),
            auto_shutdown_hours=_clamp_float(
                raw.get("auto_shutdown_hours"),
                MIN_AUTO_SHUTDOWN_HOURS,
                MAX_AUTO_SHUTDOWN_HOURS,
                default.auto_shutdown_hours,
            ),
            open_browser=_safe_bool(raw.get("open_browser"), default.open_browser),
            ip_scope=scope,
        )


@dataclass
class UiSettings:
    close_to_tray: bool = True
    tray_hint_shown: bool = False
    log_level: str = "INFO"
    first_run: bool = True
    column_widths: list[int] = field(default_factory=lambda: [76, 108, 48, 72, 104])
    last_tab: int = 0
    autostart: bool = False
    autostart_silent: bool = False
    download_dir: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> UiSettings:
        default = cls()
        widths = raw.get("column_widths")
        clean_widths = list(default.column_widths)
        if isinstance(widths, list):
            for index, value in enumerate(widths[: len(clean_widths)]):
                clean_widths[index] = _clamp_int(value, 40, 2000, clean_widths[index])
        level = _safe_str(raw.get("log_level"), default.log_level).upper()
        if level not in LOG_LEVELS:
            level = default.log_level
        return cls(
            close_to_tray=_safe_bool(raw.get("close_to_tray"), default.close_to_tray),
            tray_hint_shown=_safe_bool(raw.get("tray_hint_shown"), default.tray_hint_shown),
            log_level=level,
            first_run=_safe_bool(raw.get("first_run"), default.first_run),
            column_widths=clean_widths,
            last_tab=_clamp_int(raw.get("last_tab"), 0, 5, 0),
            autostart=_safe_bool(raw.get("autostart"), default.autostart),
            autostart_silent=_safe_bool(raw.get("autostart_silent"), default.autostart_silent),
            download_dir=_safe_str(raw.get("download_dir"), "").strip(),
        )


@dataclass
class AppConfig:
    schema_version: int = SCHEMA_VERSION
    window: WindowState = field(default_factory=WindowState)
    server: ServerSettings = field(default_factory=ServerSettings)
    ui: UiSettings = field(default_factory=UiSettings)

    # --------------------------------------------------------------- 序列化
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppConfig:
        if not isinstance(raw, dict):
            raise ValueError("配置根节点必须是对象")
        config = cls()
        window = raw.get("window")
        server = raw.get("server")
        ui = raw.get("ui")
        if isinstance(window, dict):
            config.window = WindowState.from_dict(window)
        if isinstance(server, dict):
            config.server = ServerSettings.from_dict(server)
        if isinstance(ui, dict):
            config.ui = UiSettings.from_dict(ui)
        config.schema_version = _clamp_int(
            raw.get("schema_version"), 1, SCHEMA_VERSION, SCHEMA_VERSION
        )
        return config


@dataclass
class ConfigLoadResult:
    config: AppConfig
    path: Path
    fallback_reason: str | None = None
    messages: list[str] = field(default_factory=list)


def config_directory(preferred_base: Path | None = None) -> tuple[Path, str | None]:
    """返回可写的配置目录；exe 同级不可写时回退到 ``%LOCALAPPDATA%``。"""
    base = preferred_base
    if base is None:
        from .paths import app_base_dir

        base = app_base_dir()
    preferred = base / "config"
    try:
        ensure_directory(preferred)
        return preferred, None
    except OSError as exc:
        fallback = local_appdata_dir() / "config"
        ensure_directory(fallback)
        return fallback, f"配置目录不可写（{exc}），已回退到 {fallback}"


def default_config_path(preferred_base: Path | None = None) -> Path:
    directory, _ = config_directory(preferred_base)
    return directory / "config.json"


def load_config(path: Path | None = None) -> ConfigLoadResult:
    """读取配置；任何异常都回退默认值并保留现场。"""
    if path is None:
        path = default_config_path()
    messages: list[str] = []
    fallback_reason: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent != default_config_path().parent:
            fallback_reason = f"使用回退配置目录 {path.parent}"
    except OSError as exc:
        fallback = local_appdata_dir() / "config"
        ensure_directory(fallback)
        path = fallback / "config.json"
        fallback_reason = f"配置目录不可写（{exc}），已回退到 {fallback}"
    if not path.exists():
        default = AppConfig()
        result = ConfigLoadResult(
            config=default, path=path, fallback_reason=fallback_reason, messages=messages
        )
        try:
            save_config(default, path)
        except OSError as exc:
            messages.append(f"创建默认配置失败: {exc}")
        return result
    try:
        raw_text = path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
        config = AppConfig.from_dict(raw)
    except (OSError, ValueError, TypeError) as exc:
        corrupt = path.with_name(path.name + ".corrupt")
        try:
            os.replace(path, corrupt)
        except OSError:
            corrupt = path
        messages.append(f"配置文件损坏，已回退默认值（{exc}），原文件: {corrupt}")
        default = AppConfig()
        try:
            save_config(default, path)
        except OSError as save_exc:
            messages.append(f"写入默认配置失败: {save_exc}")
        return ConfigLoadResult(
            config=default, path=path, fallback_reason=fallback_reason, messages=messages
        )
    return ConfigLoadResult(
        config=config, path=path, fallback_reason=fallback_reason, messages=messages
    )


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    """原子写入配置，写入前保留 ``.bak``。"""
    if path is None:
        path = default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_dict(), ensure_ascii=False, indent=2, sort_keys=False)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    if path.exists():
        with contextlib.suppress(OSError):
            shutil.copy2(path, path.with_name(path.name + ".bak"))
    os.replace(tmp, path)
    return path


def apply_window_geometry(config: AppConfig, window: Any) -> None:
    """把窗口位置 / 大小写入配置（退出时调用）。"""
    geometry = window.saveGeometry()
    if geometry.isEmpty():
        return
    rect = window.normalGeometry() if window.isMaximized() else window.geometry()
    config.window.width = max(800, rect.width())
    config.window.height = max(520, rect.height())
    config.window.x = rect.x()
    config.window.y = rect.y()
    config.window.maximized = bool(window.isMaximized())


def list_field_names() -> list[str]:
    """配置字段名，用于文档与测试。"""
    return [item.name for item in fields(AppConfig)]
