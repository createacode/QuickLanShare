"""运行目录解析：开发态取项目根目录，冻结态取 exe 同级目录。

所有可写数据（上传文件、聊天记录、配置、日志）都通过本模块定位，
禁止在其它模块里拼接 ``sys._MEIPASS``、盘符或开发机绝对路径。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "QuickLanShare"
APP_DIR_NAME = APP_NAME

DATA_SUBDIRS = (
    "uploads",
    "chat",
    "logs",
    "state",
    "state/tmp",
    "state/uploads",
    "config",
)


def is_frozen() -> bool:
    """当前进程是否由 PyInstaller 冻结后运行。"""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """源码根目录（开发态）。"""
    return Path(__file__).resolve().parents[3]


def app_base_dir() -> Path:
    """便携基准目录：冻结态为 exe 所在目录，开发态为项目根目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def bundle_dir() -> Path:
    """只读资源根目录：冻结态为 ``sys._MEIPASS``，开发态为项目根目录。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_base_dir()))
    return project_root()


def resource_path(*parts: str) -> Path:
    """解析随包分发的只读资源，例如 ``client/index.html``、``app.ico``。"""
    return bundle_dir().joinpath(*parts)


def default_data_dir() -> Path:
    """默认数据目录：便携模式放在 exe 同级。"""
    return app_base_dir()


def local_appdata_dir() -> Path:
    """不可写时的回退根目录：``%LOCALAPPDATA%\\QuickLanShare``。"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME}"


def ensure_directory(path: Path) -> None:
    """创建目录并做一次写测试，失败时抛出 ``OSError``。"""
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".write-test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()


def prepare_data_dir(preferred: Path | None = None) -> tuple[Path, str | None]:
    """准备数据目录，必要时回退到 ``%LOCALAPPDATA%``。

    返回 ``(可用目录, 回退说明)``。回退说明为 ``None`` 表示使用了首选目录。
    """
    primary = (preferred or default_data_dir()).resolve()
    try:
        ensure_directory(primary)
        for sub in DATA_SUBDIRS:
            (primary / sub).mkdir(parents=True, exist_ok=True)
        return primary, None
    except OSError as exc:
        fallback = local_appdata_dir()
        ensure_directory(fallback)
        for sub in DATA_SUBDIRS:
            (fallback / sub).mkdir(parents=True, exist_ok=True)
        reason = f"目录不可写（{exc}），已回退到 {fallback}"
        return fallback, reason


def app_icon_path() -> Path:
    """图标路径：优先随包资源，其次 exe 同级。"""
    bundled = resource_path("app.ico")
    if bundled.exists():
        return bundled
    return app_base_dir() / "app.ico"
