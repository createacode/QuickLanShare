"""把 asyncio HTTP 服务托管在后台线程，供 Qt 主线程复用。

界面线程只与本模块交互：启动 / 停止、提交协程、读取端口与自动关闭截止时间。
所有网络与文件异步操作都在同一个后台事件循环里执行，避免跨线程使用
``aiohttp`` 对象。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

from ..services.config import Config
from .server import FileTransferServer

logger = logging.getLogger("quicklanshare.runtime")


class RuntimeStartError(RuntimeError):
    """后台服务启动失败（端口占用、证书错误等）。"""


@dataclass
class RuntimeCallbacks:
    """后台线程回调；实现方必须保证线程安全（Qt 信号会自动排队）。"""

    on_started: Callable[[int, str, float], None] | None = None
    on_stopped: Callable[[str], None] | None = None
    on_error: Callable[[BaseException], None] | None = None


class ServerRuntime:
    """后台服务器生命周期与任务提交入口。"""

    def __init__(self, callbacks: RuntimeCallbacks | None = None) -> None:
        self.callbacks = callbacks or RuntimeCallbacks()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: FileTransferServer | None = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None
        self._port = 0
        self._deadline = 0.0
        self._stopped = False
        self._stop_requested = False

    # ------------------------------------------------------------------ state
    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and not self._stopped)

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        scheme = "https" if self._server and self._server.config.scheme == "https" else "http"
        return f"{scheme}://127.0.0.1:{self._port}"

    @property
    def share_url(self) -> str:
        if self._server is None:
            return ""
        return self._server.share_url()

    @property
    def server(self) -> FileTransferServer | None:
        return self._server

    @property
    def auto_shutdown_deadline(self) -> float:
        return self._deadline

    def remaining_seconds(self) -> int:
        if not self._deadline:
            return 0
        return max(0, int(self._deadline - time.time()))

    # --------------------------------------------------------------- lifecycle
    def start(self, config: Config, timeout: float = 20.0) -> None:
        """启动后台线程并等待监听成功；失败抛出 :class:`RuntimeStartError`。"""
        if self.is_running:
            return
        self._ready.clear()
        self._start_error = None
        self._stopped = False
        self._stop_requested = False
        self._thread = threading.Thread(
            target=self._thread_main, args=(config,), name="qls-server", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout):
            self._thread = None
            raise RuntimeStartError("启动超时：服务器未在预期时间内就绪")
        if self._start_error is not None:
            error = self._start_error
            self._start_error = None
            raise RuntimeStartError(str(error)) from error

    def _thread_main(self, config: Config) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        reason = "unknown"
        did_start = False
        try:
            server = FileTransferServer(config)
            self._server = server
            reason = loop.run_until_complete(self._serve(server))
            did_start = True
        except BaseException as exc:
            self._start_error = exc
            logger.exception("后台服务启动失败")
            if self.callbacks.on_error is not None:
                self.callbacks.on_error(exc)
            if not self._ready.is_set():
                self._ready.set()
        finally:
            try:
                self._drain_tasks(loop)
            finally:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:  # pragma: no cover - 关闭阶段
                    logger.debug("关闭异步生成器失败", exc_info=True)
                loop.close()
                self._loop = None
                self._stopped = True
                if self._server is not None:
                    self._deadline = 0.0
                if did_start and self.callbacks.on_stopped is not None:
                    self.callbacks.on_stopped(reason)

    async def _serve(self, server: FileTransferServer) -> str:
        port = await server.start()
        self._port = port
        if server.config.auto_shutdown_enabled:
            server.enable_auto_shutdown()
            deadline = float(server.shutdown_deadline or 0.0)
        else:
            deadline = 0.0
        self._deadline = deadline
        self._ready.set()
        if self.callbacks.on_started is not None:
            self.callbacks.on_started(port, server.share_url(), deadline)
        await server.wait_stopped()
        await server.aclose()
        return server.stop_reason or "stopped"

    def _drain_tasks(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        except RuntimeError:
            return
        if not pending:
            return
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

    def stop(self, reason: str = "user-exit") -> None:
        """请求停止（可在任意线程调用）。"""
        if self._stop_requested:
            return
        self._stop_requested = True
        loop = self._loop
        server = self._server
        if loop is None or server is None:
            return
        try:
            loop.call_soon_threadsafe(server.request_stop, reason)
        except RuntimeError:  # 事件循环已关闭
            logger.debug("停止请求到达时事件循环已关闭")

    def join(self, timeout: float = 8.0) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    # ------------------------------------------------------------- task bridge
    def submit(
        self,
        coroutine: Coroutine[Any, Any, Any],
        callback: Callable[[Future[Any]], None] | None = None,
    ) -> Future[Any]:
        """把协程提交到后台事件循环，返回 ``concurrent.futures.Future``。"""
        loop = self._loop
        if loop is None or loop.is_closed() or not loop.is_running():
            coroutine.close()
            raise RuntimeError("服务未运行，无法提交任务")
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        if callback is not None:
            future.add_done_callback(callback)
        return future

    def update_auto_shutdown(
        self,
        enabled: bool,
        hours: float,
        callback: Callable[[Future[Any]], None] | None = None,
    ) -> Future[Any]:
        """即时应用自动关闭设置，完成后回调新的截止时间。"""

        async def apply() -> float:
            server = self._server
            if server is None:
                return 0.0
            server.configure_auto_shutdown(enabled, hours)
            deadline = float(server.shutdown_deadline or 0.0)
            self._deadline = deadline
            return deadline

        return self.submit(apply(), callback)
