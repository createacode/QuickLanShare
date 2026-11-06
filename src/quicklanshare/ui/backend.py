"""界面与后台服务之间的 Qt 桥接层。

负责启动 / 停止服务器、提交传输任务、转发进度与结果。所有 Qt 信号都在
主线程接收（跨线程发射会自动排队），界面代码因此不需要自己处理线程。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections.abc import Coroutine
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..services.chat_client import ChatSocketClient
from ..services.config import Config
from ..services.local_client import (
    LocalClientError,
    LocalShareClient,
    TransferCancelled,
)
from ..services.runtime import RuntimeCallbacks, RuntimeStartError, ServerRuntime

logger = logging.getLogger("quicklanshare.backend")


class Backend(QObject):
    """服务器与本地传输任务的 Qt 门面。"""

    started = Signal(int, str, float)
    start_failed = Signal(str)
    stopped = Signal(str)
    files_loaded = Signal(list)
    files_failed = Signal(str)
    room_updated = Signal(dict)
    delete_finished = Signal(list, list)
    upload_started = Signal(str, str, int)
    upload_progress = Signal(str, int, int)
    upload_finished = Signal(str, str, bool, str)
    download_started = Signal(str, str, int)
    download_progress = Signal(str, int, int)
    download_finished = Signal(str, str, bool, str)
    auto_shutdown_changed = Signal(bool, float)
    operation_failed = Signal(str)
    chat_history = Signal(list)
    chat_message = Signal(dict)
    chat_deleted = Signal(str)
    chat_bulk_deleted = Signal(list)
    chat_edited = Signal(dict)
    chat_status = Signal(str)
    chat_error = Signal(str)
    profile_updated = Signal(dict)
    scope_updated = Signal(dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runtime = ServerRuntime(
            RuntimeCallbacks(on_started=self._on_started, on_stopped=self._on_stopped)
        )
        self._client: LocalShareClient | None = None
        self._chat_client: ChatSocketClient | None = None
        self._config: Config | None = None
        self._cancel_events: dict[str, threading.Event] = {}
        self._transfers: dict[str, str] = {}
        self._pending_auto_enabled = False
        self._last_error = ""

    # ------------------------------------------------------------------ state
    @property
    def is_running(self) -> bool:
        return self._runtime.is_running

    @property
    def port(self) -> int:
        return self._runtime.port

    @property
    def share_url(self) -> str:
        return self._runtime.share_url

    @property
    def local_url(self) -> str:
        return self._runtime.base_url

    @property
    def deadline(self) -> float:
        return self._runtime.auto_shutdown_deadline

    @property
    def active_transfers(self) -> int:
        return len(self._transfers)

    @property
    def config(self) -> Config | None:
        return self._config

    # -------------------------------------------------------------- lifecycle
    def start_server(self, config: Config) -> bool:
        """启动后台服务；失败时发出 ``start_failed`` 并返回 ``False``。"""
        if self._runtime.is_running:
            return True
        self._config = config
        try:
            self._runtime.start(config)
        except RuntimeStartError as exc:
            logger.error("服务启动失败: %s", exc)
            self._last_error = str(exc)
            self.start_failed.emit(str(exc))
            return False
        self._client = LocalShareClient(self._runtime.base_url)
        self._start_chat_socket()
        self.refresh_profile()
        self.refresh_scope()
        logger.info("后台服务已就绪，端口 %s", self._runtime.port)
        return True

    def _start_chat_socket(self) -> None:
        """启动文本共享订阅（与网页端同一个房间）。"""
        self.chat_status.emit("connecting")
        chat_client = ChatSocketClient(
            self._runtime.base_url,
            on_history=self.chat_history.emit,
            on_message=self.chat_message.emit,
            on_deleted=self.chat_deleted.emit,
            on_status=self.chat_status.emit,
            on_shutdown=lambda _reason: self.chat_status.emit("offline"),
            on_bulk_deleted=self.chat_bulk_deleted.emit,
            on_edited=self.chat_edited.emit,
            on_profile=self.profile_updated.emit,
            on_scope=self.scope_updated.emit,
        )
        self._chat_client = chat_client
        try:
            self._runtime.submit(chat_client.run())
        except RuntimeError as exc:
            logger.warning("文本共享订阅启动失败: %s", exc)
            self.chat_status.emit("offline")

    def stop_server(self, reason: str = "user-stop") -> None:
        self._runtime.stop(reason)

    def wait_stopped(self, timeout: float = 8.0) -> bool:
        return self._runtime.join(timeout)

    def _on_started(self, port: int, share_url: str, deadline: float) -> None:
        self.started.emit(port, share_url, deadline)

    def _on_stopped(self, reason: str) -> None:
        if self._chat_client is not None:
            self._chat_client.close()
        self._chat_client = None
        self._client = None
        self._transfers.clear()
        for event in self._cancel_events.values():
            event.set()
        self._cancel_events.clear()
        self.chat_status.emit("offline")
        self.stopped.emit(reason)

    # ------------------------------------------------------------------ files
    def refresh_files(self) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            return
        try:
            self._runtime.submit(client.list_files(), callback=self._on_files)
        except RuntimeError as exc:
            self.files_failed.emit(str(exc))

    def _on_files(self, future: Future[Any]) -> None:
        try:
            files = future.result()
        except Exception as exc:
            logger.warning("刷新文件列表失败: %s", exc)
            self.files_failed.emit(str(exc))
            return
        if isinstance(files, list):
            self.files_loaded.emit(files)

    def refresh_room_info(self) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            return
        try:
            self._runtime.submit(client.room_info(), callback=self._on_room_info)
        except RuntimeError:
            return

    def _on_room_info(self, future: Future[Any]) -> None:
        try:
            info = future.result()
        except Exception:
            return
        if isinstance(info, dict):
            self.room_updated.emit(info)

    # ------------------------------------------------------------ profile/scope
    def refresh_profile(self) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            return
        try:
            self._runtime.submit(client.profile(), callback=self._on_profile)
        except RuntimeError:
            return

    def _on_profile(self, future: Future[Any]) -> None:
        try:
            profile = future.result()
        except Exception:
            return
        if isinstance(profile, dict):
            self.profile_updated.emit(profile)

    def rename_profile(self, name: str, *, quiet: bool = False) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            if not quiet:
                self.chat_error.emit("服务未运行，无法修改用户名")
            return

        def _done(future: Future[Any]) -> None:
            try:
                payload = future.result()
            except Exception as exc:
                logger.warning("修改用户名失败: %s", exc)
                if not quiet:
                    self.chat_error.emit(f"修改用户名失败：{exc}")
                return
            if isinstance(payload, dict):
                self.profile_updated.emit(payload)

        try:
            self._runtime.submit(client.rename_profile(name), callback=_done)
        except RuntimeError as exc:
            if not quiet:
                self.chat_error.emit(str(exc))

    def refresh_scope(self) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            return
        try:
            self._runtime.submit(client.network_scope(), callback=self._on_scope)
        except RuntimeError:
            return

    def _on_scope(self, future: Future[Any]) -> None:
        try:
            payload = future.result()
        except Exception:
            return
        if isinstance(payload, dict):
            self.scope_updated.emit(payload)

    def apply_network_scope(self, scope: str) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            self.operation_failed.emit("服务未运行，无法修改开放网段")
            return
        try:
            self._runtime.submit(client.set_network_scope(scope), callback=self._on_scope_applied)
        except RuntimeError as exc:
            self.operation_failed.emit(str(exc))

    def _on_scope_applied(self, future: Future[Any]) -> None:
        try:
            payload = future.result()
        except Exception as exc:
            logger.warning("修改开放网段失败: %s", exc)
            self.operation_failed.emit(f"修改开放网段失败：{exc}")
            return
        if isinstance(payload, dict):
            self.scope_updated.emit(payload)

    # ----------------------------------------------------------------- upload
    def upload_paths(self, paths: list[Path]) -> None:
        if not self._runtime.is_running or self._client is None:
            self.operation_failed.emit("服务未运行，无法上传")
            return
        files = [Path(path) for path in paths if Path(path).is_file()]
        if not files:
            self.operation_failed.emit("没有可上传的文件")
            return
        items: list[tuple[str, Path]] = []
        for path in files:
            try:
                size = path.stat().st_size
            except OSError as exc:
                self.operation_failed.emit(f"无法读取 {path.name}: {exc}")
                continue
            task_id = uuid.uuid4().hex[:10]
            self._cancel_events[task_id] = threading.Event()
            self._transfers[task_id] = "upload"
            self.upload_started.emit(task_id, path.name, int(size))
            items.append((task_id, path))
        if not items:
            return
        coroutine = self._upload_batch(items)
        try:
            self._runtime.submit(coroutine)
        except RuntimeError as exc:
            for task_id, path in items:
                self._cancel_events.pop(task_id, None)
                self._transfers.pop(task_id, None)
                self.upload_finished.emit(task_id, path.name, False, str(exc))

    async def _upload_batch(self, items: list[tuple[str, Path]]) -> None:
        client = self._client
        if client is None:
            return
        for task_id, path in items:
            cancel_event = self._cancel_events.get(task_id)

            def progress(done: int, total: int, tid: str = task_id) -> None:
                self.upload_progress.emit(tid, done, total)

            try:
                await client.upload_file(
                    path,
                    on_progress=progress,
                    cancel_event=cancel_event,
                )
            except TransferCancelled:
                self.upload_finished.emit(task_id, path.name, False, "已取消")
            except asyncio.CancelledError:
                self.upload_finished.emit(task_id, path.name, False, "已取消")
                raise
            except (LocalClientError, OSError) as exc:
                logger.warning("上传失败 %s: %s", path.name, exc)
                self.upload_finished.emit(task_id, path.name, False, str(exc))
            except Exception as exc:
                logger.exception("上传异常 %s", path.name)
                self.upload_finished.emit(task_id, path.name, False, str(exc))
            else:
                logger.info("上传完成: %s (%s 字节)", path.name, path.stat().st_size)
                self.upload_finished.emit(task_id, path.name, True, "上传完成")
            finally:
                self._cancel_events.pop(task_id, None)
                self._transfers.pop(task_id, None)
        await self._refresh_after_change()

    def cancel_transfer(self, task_id: str) -> None:
        event = self._cancel_events.get(task_id)
        if event is None:
            return
        event.set()
        kind = self._transfers.get(task_id, "upload")
        logger.info("用户取消传输任务: %s", task_id)
        if kind == "download":
            self.download_finished.emit(task_id, "", False, "已取消")
        else:
            self.upload_finished.emit(task_id, "", False, "已取消")

    # --------------------------------------------------------------- download
    def download_file(self, name: str, target: Path) -> None:
        task_id = uuid.uuid4().hex[:10]
        if not self._runtime.is_running or self._client is None:
            self.download_finished.emit(task_id, name, False, "服务未运行，无法下载")
            return
        self._cancel_events[task_id] = threading.Event()
        self._transfers[task_id] = "download"
        self.download_started.emit(task_id, name, 0)
        coroutine = self._download_one(task_id, name, Path(target))
        try:
            self._runtime.submit(coroutine)
        except RuntimeError as exc:
            self._cancel_events.pop(task_id, None)
            self._transfers.pop(task_id, None)
            self.download_finished.emit(task_id, name, False, str(exc))

    async def _download_one(self, task_id: str, name: str, target: Path) -> None:
        client = self._client
        if client is None:
            return
        try:
            written = await client.download_file(
                name,
                target,
                on_progress=lambda done, total: self.download_progress.emit(task_id, done, total),
                cancel_event=self._cancel_events.get(task_id),
            )
        except TransferCancelled:
            self.download_finished.emit(task_id, name, False, "已取消")
        except asyncio.CancelledError:
            self.download_finished.emit(task_id, name, False, "已取消")
            raise
        except (LocalClientError, OSError) as exc:
            logger.warning("下载失败 %s: %s", name, exc)
            self.download_finished.emit(task_id, name, False, str(exc))
        except Exception as exc:
            logger.exception("下载异常 %s", name)
            self.download_finished.emit(task_id, name, False, str(exc))
        else:
            logger.info("下载完成: %s -> %s (%s 字节)", name, target, written)
            self.download_finished.emit(task_id, name, True, f"已保存到 {target}")
        finally:
            self._cancel_events.pop(task_id, None)
            self._transfers.pop(task_id, None)

    def download_zip(self, names: list[str], target: Path) -> None:
        if not self._runtime.is_running or self._client is None:
            self.operation_failed.emit("服务未运行，无法下载")
            return
        if not names:
            return
        task_id = uuid.uuid4().hex[:10]
        self._cancel_events[task_id] = threading.Event()
        self._transfers[task_id] = "download"
        label = f"打包下载（{len(names)} 个文件）"
        self.download_started.emit(task_id, label, 0)
        coroutine = self._download_zip(task_id, label, names, Path(target))
        try:
            self._runtime.submit(coroutine)
        except RuntimeError as exc:
            self._cancel_events.pop(task_id, None)
            self._transfers.pop(task_id, None)
            self.download_finished.emit(task_id, label, False, str(exc))

    async def _download_zip(self, task_id: str, label: str, names: list[str], target: Path) -> None:
        client = self._client
        if client is None:
            return
        try:
            written = await client.download_zip(
                names,
                target,
                on_progress=lambda done, total: self.download_progress.emit(task_id, done, total),
                cancel_event=self._cancel_events.get(task_id),
            )
        except TransferCancelled:
            self.download_finished.emit(task_id, label, False, "已取消")
        except asyncio.CancelledError:
            self.download_finished.emit(task_id, label, False, "已取消")
            raise
        except (LocalClientError, OSError) as exc:
            logger.warning("打包下载失败: %s", exc)
            self.download_finished.emit(task_id, label, False, str(exc))
        except Exception as exc:
            logger.exception("打包下载异常")
            self.download_finished.emit(task_id, label, False, str(exc))
        else:
            logger.info("打包下载完成: %s -> %s (%s 字节)", label, target, written)
            self.download_finished.emit(task_id, label, True, f"已保存到 {target}")
        finally:
            self._cancel_events.pop(task_id, None)
            self._transfers.pop(task_id, None)

    def cancel_download(self, task_id: str) -> None:
        self.cancel_transfer(task_id)

    # ----------------------------------------------------------------- delete
    def delete_files(self, names: list[str]) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            self.operation_failed.emit("服务未运行，无法删除")
            return
        if not names:
            return
        try:
            self._runtime.submit(client.delete_files(names), callback=self._on_deleted)
        except RuntimeError as exc:
            self.operation_failed.emit(str(exc))

    def _on_deleted(self, future: Future[Any]) -> None:
        try:
            payload = future.result()
        except Exception as exc:
            logger.warning("删除失败: %s", exc)
            self.operation_failed.emit(f"删除失败: {exc}")
            return
        deleted = payload.get("deleted") if isinstance(payload, dict) else []
        failed = payload.get("failed") if isinstance(payload, dict) else []
        deleted_list = deleted if isinstance(deleted, list) else []
        failed_list = failed if isinstance(failed, list) else []
        logger.info("删除文件 %d 个，失败 %d 个", len(deleted_list), len(failed_list))
        self.delete_finished.emit(deleted_list, failed_list)
        self.refresh_files()

    # ------------------------------------------------------------------- chat
    def send_chat(self, text: str) -> None:
        """发送共享文本；HTTP 返回的消息 id 用于界面去重。"""
        client = self._client
        if client is None or not self._runtime.is_running:
            self.chat_error.emit("服务未运行，无法发送文本")
            return
        if not str(text or "").strip():
            self.chat_error.emit("消息不能为空")
            return
        try:
            self._runtime.submit(client.send_chat(text), callback=self._on_chat_sent)
        except RuntimeError as exc:
            self.chat_error.emit(str(exc))

    def _on_chat_sent(self, future: Future[Any]) -> None:
        try:
            payload = future.result()
        except Exception as exc:
            logger.warning("发送文本失败: %s", exc)
            self.chat_error.emit(f"发送失败：{exc}")
            return
        message = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(message, dict):
            self.chat_message.emit(message)

    def delete_chat(self, message_id: str) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            self.chat_error.emit("服务未运行，无法删除消息")
            return
        if not message_id:
            return

        def _done(future: Future[Any], mid: str = message_id) -> None:
            self._on_chat_deleted(future, mid)

        try:
            self._runtime.submit(client.delete_chat(message_id), callback=_done)
        except RuntimeError as exc:
            self.chat_error.emit(str(exc))

    def _on_chat_deleted(self, future: Future[Any], message_id: str) -> None:
        try:
            future.result()
        except Exception as exc:
            logger.warning("删除文本失败: %s", exc)
            self.chat_error.emit(f"删除失败：{exc}")
            return
        self.chat_deleted.emit(message_id)

    def edit_chat(self, message_id: str, text: str) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            self.chat_error.emit("服务未运行，无法编辑消息")
            return
        if not message_id:
            return

        def _done(future: Future[Any]) -> None:
            try:
                message = future.result()
            except Exception as exc:
                logger.warning("编辑文本失败: %s", exc)
                self.chat_error.emit(f"编辑失败：{exc}")
                return
            if isinstance(message, dict):
                self.chat_edited.emit(message)

        try:
            self._runtime.submit(client.edit_chat(message_id, text), callback=_done)
        except RuntimeError as exc:
            self.chat_error.emit(str(exc))

    def delete_chat_messages(self, message_ids: list[str]) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            self.chat_error.emit("服务未运行，无法删除消息")
            return

        def _done(future: Future[Any]) -> None:
            try:
                deleted = future.result()
            except Exception as exc:
                logger.warning("批量删除文本失败: %s", exc)
                self.chat_error.emit(f"批量删除失败：{exc}")
                return
            if isinstance(deleted, list):
                self.chat_bulk_deleted.emit(deleted)

        try:
            self._runtime.submit(client.delete_chat_messages(message_ids), callback=_done)
        except RuntimeError as exc:
            self.chat_error.emit(str(exc))

    def refresh_chat(self) -> None:
        client = self._client
        if client is None or not self._runtime.is_running:
            return
        try:
            self._runtime.submit(client.chat_history(), callback=self._on_chat_history)
        except RuntimeError:
            return

    def _on_chat_history(self, future: Future[Any]) -> None:
        try:
            messages = future.result()
        except Exception as exc:
            logger.debug("刷新文本历史失败: %s", exc)
            return
        if isinstance(messages, list):
            self.chat_history.emit(messages)

    async def _refresh_after_change(self) -> None:
        client = self._client
        if client is None:
            return
        try:
            files = await client.list_files()
        except Exception:
            return
        self.files_loaded.emit(files)

    # -------------------------------------------------------- auto shutdown
    def apply_auto_shutdown(self, enabled: bool, hours: float) -> None:
        if not self._runtime.is_running:
            self.auto_shutdown_changed.emit(enabled, 0.0)
            return
        self._pending_auto_enabled = enabled
        try:
            self._runtime.update_auto_shutdown(enabled, hours, callback=self._on_auto_shutdown)
        except RuntimeError as exc:
            self.operation_failed.emit(str(exc))

    def _on_auto_shutdown(self, future: Future[Any]) -> None:
        try:
            deadline = future.result()
        except Exception as exc:
            self.operation_failed.emit(f"更新自动关闭失败: {exc}")
            return
        self.auto_shutdown_changed.emit(
            bool(self._pending_auto_enabled and deadline), float(deadline or 0.0)
        )

    # ---------------------------------------------------------------- helpers
    def emit_operation_error(self, message: str) -> None:
        self.operation_failed.emit(message)

    def submit(self, coroutine: Coroutine[Any, Any, Any], callback: Any = None) -> bool:
        try:
            self._runtime.submit(coroutine, callback)
            return True
        except RuntimeError as exc:
            self.operation_failed.emit(str(exc))
            return False


__all__ = ["Backend"]
