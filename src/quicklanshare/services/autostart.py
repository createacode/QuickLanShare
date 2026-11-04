"""Windows 开机自启（当前用户，无需管理员权限）。

使用 ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` 注册启动命令。
自启时带 ``--autostart``；若用户选择静默，再带 ``--silent``，程序只在托盘运行。
手动双击 exe 不带这些参数，仍然正常显示主界面。
"""

from __future__ import annotations

import contextlib
import logging
import sys
from dataclasses import dataclass

from ..utils.paths import is_frozen, project_root

logger = logging.getLogger("quicklanshare.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "QuickLanShare"


class AutostartError(RuntimeError):
    """写入或删除注册表启动项失败。"""


@dataclass
class AutostartCommand:
    parts: list[str]

    @property
    def command_line(self) -> str:
        return " ".join(f'"{part}"' for part in self.parts)


def build_command(
    silent: bool,
    *,
    frozen: bool | None = None,
    executable: str | None = None,
) -> AutostartCommand:
    """构造自启命令；开发态使用 pythonw + main.py，冻结态直接使用 exe。"""
    if frozen is None:
        frozen = is_frozen()
    if executable is None:
        executable = sys.executable
    parts: list[str] = []
    if frozen:
        parts.append(executable)
    else:
        python = executable
        try:
            from pathlib import Path

            candidate = Path(python).with_name("pythonw.exe")
            if candidate.exists():
                python = str(candidate)
        except OSError:
            pass
        parts.extend([python, str(project_root() / "main.py")])
    parts.append("--autostart")
    if silent:
        parts.append("--silent")
    return AutostartCommand(parts)


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return isinstance(value, str) and bool(value)


def apply_autostart(enabled: bool, silent: bool) -> None:
    """启用/禁用开机自启；失败抛出 :class:`AutostartError`。"""
    if sys.platform != "win32":
        if enabled:
            raise AutostartError("当前系统不支持 Windows 注册表自启")
        return
    import winreg

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                command = build_command(silent)
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command.command_line)
                logger.info(
                    "已开启开机自启%s: %s", "（静默）" if silent else "", command.command_line
                )
            else:
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, VALUE_NAME)
                logger.info("已关闭开机自启")
    except OSError as exc:
        raise AutostartError(f"设置开机自启失败: {exc}") from exc


__all__ = ["AutostartCommand", "AutostartError", "apply_autostart", "build_command", "is_enabled"]
