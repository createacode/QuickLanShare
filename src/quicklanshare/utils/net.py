"""网络相关辅助函数：本机地址、Host 白名单、管理员检测。"""

from __future__ import annotations

import ctypes
import logging
import socket
import sys
import webbrowser

logger = logging.getLogger("quicklanshare.net")


def collect_local_hosts() -> set[str]:
    """收集本机可合法访问的 Host，用于抵御 DNS rebinding。

    攻击者控制的域名解析到局域网 IP 时，浏览器的 ``Host`` 头仍是攻击者域名，
    不在本集合内即被拒绝。
    """
    hosts: set[str] = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    try:
        hostname = socket.gethostname()
        short = hostname.split(".")[0]
        hosts.update({hostname, hostname.lower(), short, short.lower(), f"{short}.local"})
    except OSError:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None):
            sockaddr = item[4]
            if sockaddr:
                hosts.add(str(sockaddr[0]).strip("[]"))
    except OSError:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            hosts.add(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        pass
    return {host.lower().rstrip(".") for host in hosts if host}


def get_local_ip() -> str:
    """获取用于展示二维码 / 局域网地址的主 IP。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        logger.warning("无法获取本机局域网 IP，回退到 127.0.0.1")
        return "127.0.0.1"


def open_browser(url: str) -> bool:
    """用系统默认浏览器打开链接（服务端/无 Qt 场景使用）。"""
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:  # pragma: no cover - 平台相关
        logger.exception("打开浏览器失败: %s", url)
        return False


def is_admin() -> bool:
    """当前进程是否具备管理员权限（仅 Windows 有意义）。"""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # pragma: no cover - 旧系统 / 受限环境
        return False


def os_description() -> str:
    """返回适合写入日志的系统描述，例如 ``Windows 10.0.19045``。"""
    if sys.platform == "win32":
        version = sys.getwindowsversion()
        return f"Windows {version.major}.{version.minor}.{version.build}"
    return sys.platform
