"""IPv4 放通范围（四档预设，对应界面四档滑动开关）。

- ``last1``：同一网段（只开放最后 1 段，最严格）；
- ``last2``：放通最后 2 段；
- ``last3``：放通最后 3 段；
- ``all``：全部放通（默认），四档中最宽松。

本机回环地址始终放通，避免桌面端/本机浏览器被挡。
"""

from __future__ import annotations

import ipaddress

SCOPE_LAST1 = "last1"
SCOPE_LAST2 = "last2"
SCOPE_LAST3 = "last3"
SCOPE_ALL = "all"
SCOPES = (SCOPE_LAST1, SCOPE_LAST2, SCOPE_LAST3, SCOPE_ALL)
SCOPE_LABELS = {
    SCOPE_LAST1: "仅同一网段",
    SCOPE_LAST2: "开放后 2 段",
    SCOPE_LAST3: "开放后 3 段",
    SCOPE_ALL: "全部开放",
}

# 位 3 = 第 4 段，位 0 = 第 1 段；1 表示该段开放（通配）。
_MASK = {
    SCOPE_LAST1: 0b1000,
    SCOPE_LAST2: 0b1100,
    SCOPE_LAST3: 0b1110,
    SCOPE_ALL: 0b1111,
}
MASK_ALL = 0b1111


def normalize_ipv4(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if text.lower().startswith("::ffff:"):
        text = text[7:]
    if "%" in text:
        text = text.split("%", 1)[0]
    try:
        return str(ipaddress.IPv4Address(text))
    except ValueError:
        return None


def is_loopback(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    if text in ("::1", "localhost"):
        return True
    normalized = normalize_ipv4(value)
    return normalized is not None and normalized.startswith("127.")


def normalize_scope(scope: str | None) -> str:
    """只保留四档预设；无效值和新配置默认使用“全部开放”。"""
    return scope if scope in SCOPES else SCOPE_ALL


def scope_mask(scope: str | None) -> int:
    """返回 0-15 的开放位图；无效值按最严格的“同一网段”处理。"""
    return _MASK.get(scope or "", _MASK[SCOPE_LAST1])


def scope_segments(scope: str | None) -> list[bool]:
    """返回从左到右四段的开放状态，供界面/接口展示。"""
    mask = scope_mask(scope)
    return [bool(mask & (1 << index)) for index in range(4)]


def scope_label(scope: str | None) -> str:
    return SCOPE_LABELS.get(scope or "", SCOPE_LABELS[SCOPE_ALL])


def is_ip_allowed(server_ip: str | None, client_ip: str | None, scope: str) -> bool:
    if is_loopback(client_ip):
        return True
    mask = scope_mask(scope)
    if mask == MASK_ALL:
        return True
    server = normalize_ipv4(server_ip)
    client = normalize_ipv4(client_ip)
    if server is None or client is None:
        # 无法解析服务器地址时不锁死本机；非 IPv4 客户端按拒绝处理。
        return server is None
    if server.startswith("127."):
        return True
    server_parts = server.split(".")
    client_parts = client.split(".")
    for index in range(4):
        if not mask & (1 << index) and server_parts[index] != client_parts[index]:
            return False
    return True


__all__ = [
    "MASK_ALL",
    "SCOPES",
    "SCOPE_ALL",
    "SCOPE_LABELS",
    "SCOPE_LAST1",
    "SCOPE_LAST2",
    "SCOPE_LAST3",
    "is_ip_allowed",
    "is_loopback",
    "normalize_ipv4",
    "normalize_scope",
    "scope_label",
    "scope_mask",
    "scope_segments",
]
