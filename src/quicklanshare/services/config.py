"""HTTP 服务端的运行时配置。

与界面配置（``utils.app_config``）分离：本模块只描述一次运行所需的参数，
不含窗口几何、日志级别等用户偏好；界面配置负责持久化并生成 :class:`Config`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..utils.paths import bundle_dir, default_data_dir, prepare_data_dir

APP_NAME = "QuickLanShare"

MIB = 1024 * 1024
GIB = 1024 * MIB


@dataclass
class Config:
    """服务端运行配置（默认值即产品默认行为）。"""

    host: str = "0.0.0.0"
    port: int = 8888
    port_attempts: int = 10
    data_dir: Path = field(default_factory=default_data_dir)
    client_dir: Path = field(default_factory=lambda: bundle_dir() / "client")
    used_fallback: bool = False
    fallback_reason: str | None = None

    # 传输限制（字节）
    max_upload_size: int = 25 * GIB
    zip_size_limit: int = 20 * GIB
    upload_chunk_size: int = 8 * MIB
    max_chunk_size: int = 32 * MIB
    max_json_size: int = 2 * MIB

    # 聊天
    max_chat_message: int = 500
    chat_memory_limit: int = 2000

    # 生命周期：默认 24 小时后自动关闭；界面可配置为不关闭
    auto_shutdown_enabled: bool = True
    auto_shutdown_hours: float = 24.0
    auto_shutdown_max_hours: float = 720.0
    auto_shutdown_extend_hours: float = 3.0
    open_browser: bool = False

    # 可选 TLS（两个文件必须同时提供）
    ssl_cert: Path | None = None
    ssl_key: Path | None = None

    # 安全 / 网络
    allow_any_host: bool = False
    allowed_hosts: set[str] = field(default_factory=set)
    ip_scope: str = "last1"

    # 杂项
    log_level: str = "INFO"
    access_log: bool = True
    zip_compression: str = "stored"  # "stored" | "deflate"
    stale_upload_max_age: int = 24 * 3600

    # ------------------------------------------------------------------ paths
    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def chat_dir(self) -> Path:
        return self.data_dir / "chat"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def tmp_dir(self) -> Path:
        return self.state_dir / "tmp"

    @property
    def session_dir(self) -> Path:
        return self.state_dir / "uploads"

    @property
    def counts_file(self) -> Path:
        return self.state_dir / "download_counts.json"

    @property
    def scheme(self) -> str:
        return "https" if self.ssl_cert and self.ssl_key else "http"

    def ensure_dirs(self) -> None:
        """创建运行目录；exe 同级不可写时回退到 ``%LOCALAPPDATA%``。"""
        base, reason = prepare_data_dir(self.data_dir)
        self.data_dir = base
        self.used_fallback = reason is not None
        self.fallback_reason = reason
