"""IPv4 放通范围。

按 IPv4 前几段匹配：
- ``last1``：同前三段（只放通最后一位），默认；
- ``last2``：同前两段（放通最后 2 位）；
- ``last3``：同第一段（放通最后 3 位）；
- ``all``：全部放通。

本机回环地址始终放通，避免桌面端/本机浏览器被挡。
"""

from __future__ import annotations

import ipaddress

SCOPE_LAST1 = "last1"
SCOPE_LAST2 = "last2"
SCOPE_LAST3 = "last3"
SCOPE_ALL = "all"
SCOPES = (SCOPE_LAST1, SCOPE_LAST2, SCOPE_LAST3, SCOPE_ALL)
_PREFIX = {SCOPE_LAST1: 3, SCOPE_LAST2: 2, SCOPE_LAST3: 1}


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
    normalized = normalize_ipv4(value)
    return normalized is not None and normalized.startswith("127.")


def is_ip_allowed(server_ip: str | None, client_ip: str | None, scope: str) -> bool:
    if scope not in SCOPES:
        scope = SCOPE_LAST1
    if is_loopback(client_ip):
        return True
    if scope == SCOPE_ALL:
        return True
    server = normalize_ipv4(server_ip)
    client = normalize_ipv4(client_ip)
    if server is None or client is None:
        # 无法解析服务器地址时不锁死本机；非 IPv4 客户端按拒绝处理。
        return server is None
    if server.startswith("127."):
        return True
    prefix = _PREFIX[scope]
    return client.split(".")[:prefix] == server.split(".")[:prefix]


__all__ = [
    "SCOPES",
    "SCOPE_ALL",
    "SCOPE_LAST1",
    "SCOPE_LAST2",
    "SCOPE_LAST3",
    "is_ip_allowed",
    "is_loopback",
    "normalize_ipv4",
]
