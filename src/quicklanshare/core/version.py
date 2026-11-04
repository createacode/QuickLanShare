"""版本、作者与版权的唯一真源。

本模块是工程中唯一的版本号与版权信息来源：``pyproject.toml``、
``scripts/gen_version_info.py``、``scripts/sync_version.py``、界面标题、
``VERSION.txt`` 与文档都从这里的变量派生，禁止在其它位置写第二份。
"""

from __future__ import annotations

__software_name__ = "QuickLanShare"
__version__ = "3.4.0"
__author__ = "XAF"
__copyright_ym__ = "2026.11"


def copyright_suffix() -> str:
    """返回统一的版权后缀，例如 ``- Copyright © XAF 2026.11``。"""
    return f"- Copyright © {__author__} {__copyright_ym__}"


def window_title() -> str:
    """主窗口 / 托盘 / 文档标题使用的完整标题。"""
    return f"{__software_name__} v{__version__} {copyright_suffix()}"


__all__ = [
    "__author__",
    "__copyright_ym__",
    "__software_name__",
    "__version__",
    "copyright_suffix",
    "window_title",
]
