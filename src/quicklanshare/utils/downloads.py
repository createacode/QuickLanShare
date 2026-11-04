"""下载目录解析：优先使用 Windows 已知文件夹中的“下载”。

Windows 允许把“下载”文件夹重定向到 D 盘或其他位置，因此不能简单拼
``%USERPROFILE%\\Downloads``。Qt 的 ``DownloadLocation`` 会调用
``SHGetKnownFolderPath`` 读取真实位置；若 Qt 没有返回，再读注册表
``User Shell Folders`` 中的 Downloads GUID 作为兜底。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"
_USER_SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
_SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _registry_downloads() -> Path | None:
    if sys.platform != "win32":
        return None
    import winreg

    for key_name in (_USER_SHELL_FOLDERS, _SHELL_FOLDERS):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
                value, _ = winreg.QueryValueEx(key, _DOWNLOADS_GUID)
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            expanded = os.path.expandvars(value)
            if expanded:
                return Path(expanded)
    return None


def known_download_dir() -> Path:
    """返回 Windows 已知的下载目录；不保证目录已经存在。"""
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    if location:
        return Path(location)
    registry = _registry_downloads()
    if registry is not None:
        return registry
    return Path.home() / "Downloads"


def default_download_dir() -> Path:
    """当前用户真实的下载目录；不存在时回退到主目录。"""
    path = known_download_dir()
    if path.is_dir():
        return path
    fallback = Path.home() / "Downloads"
    if fallback.is_dir():
        return fallback
    return Path.home()


def resolve_download_dir(configured: str | None = None) -> Path:
    """用户自定义目录有效则使用它，否则使用当前用户下载目录。"""
    if configured:
        custom = Path(configured).expanduser()
        if custom.is_dir():
            return custom
    return default_download_dir()


def desktop_dir() -> Path:
    """当前用户桌面目录（Windows 同样可能被重定向）。"""
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    if location:
        path = Path(location)
        if path.is_dir():
            return path
    fallback = Path.home() / "Desktop"
    return fallback if fallback.is_dir() else Path.home()


def unique_download_path(directory: Path, name: str) -> Path:
    """在下载目录内生成不覆盖已有文件的目标路径。"""
    directory.mkdir(parents=True, exist_ok=True)
    safe = _INVALID_NAME.sub("_", Path(name).name).strip() or "download"
    candidate = directory / safe
    if not candidate.exists():
        return candidate
    suffix = candidate.suffix
    stem = candidate.stem or "download"
    for index in range(1, 10000):
        alternative = directory / f"{stem} ({index}){suffix}"
        if not alternative.exists():
            return alternative
    raise OSError("无法生成不重复的下载文件名")


__all__ = [
    "default_download_dir",
    "desktop_dir",
    "known_download_dir",
    "resolve_download_dir",
    "unique_download_path",
]
