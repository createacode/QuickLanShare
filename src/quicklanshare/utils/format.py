"""人类可读的尺寸、时间与文本格式化。"""

from __future__ import annotations

from datetime import datetime


def human_size(num: int | float) -> str:
    """把字节数格式化为 ``1.2 GB`` 这样的字符串。"""
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < 1024.0:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{value:.1f}TB"


def human_time(seconds: float) -> str:
    """把秒数格式化为 ``HH:MM:SS`` / ``MM:SS``。"""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_mtime(timestamp: float) -> str:
    """Unix 时间戳 → ``YYYY-MM-DD HH:MM``。"""
    if not timestamp:
        return "-"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def shorten(text: str, limit: int = 60) -> str:
    """中间省略的长文本，用于日志与提示。"""
    if len(text) <= limit:
        return text
    keep = max(1, (limit - 1) // 2)
    return f"{text[:keep]}…{text[-keep:]}"
