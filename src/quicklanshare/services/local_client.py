"""桌面界面使用的本地 HTTP 客户端。

界面与服务器同进程但运行在不同线程 / 事件循环中，所有文件操作都通过
本机 HTTP API 完成，既复用真实链路（分块续传、Range、流式 ZIP），也避免
跨线程直接操作服务端对象。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiofiles
import aiohttp

logger = logging.getLogger("quicklanshare.client")

ProgressCallback = Callable[[int, int], None]


class LocalClientError(RuntimeError):
    """本地 API 返回非 2xx 或响应不可解析。"""


class TransferCancelled(RuntimeError):
    """用户取消了传输任务。"""


@dataclass
class UploadResult:
    name: str
    size: int
    upload_id: str


class LocalShareClient:
    """对 ``FileTransferServer`` 的轻量客户端封装。"""

    def __init__(
        self,
        base_url: str,
        *,
        chunk_size: int = 8 * 1024 * 1024,
        retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.chunk_size = max(64 * 1024, int(chunk_size))
        self.retries = max(1, int(retries))
        # 本机 HTTPS 使用自签名证书时跳过校验；HTTP 请求忽略该参数。
        self._ssl: bool = not self.base_url.startswith("https://")

    # ----------------------------------------------------------------- helpers
    def _timeout(self, *, total: float | None = None) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=total, connect=10, sock_read=180)

    @staticmethod
    async def _json(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            payload = await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError) as exc:
            text = await response.text()
            raise LocalClientError(
                f"接口返回无法解析（HTTP {response.status}）: {text[:200]}"
            ) from exc
        if response.status >= 400:
            message = payload.get("error") if isinstance(payload, dict) else None
            raise LocalClientError(str(message or f"HTTP {response.status}"))
        if not isinstance(payload, dict):
            raise LocalClientError("接口返回格式错误")
        return payload

    @staticmethod
    def _check_cancel(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise TransferCancelled("传输已取消")

    # ------------------------------------------------------------------- reads
    async def room_info(self) -> dict[str, Any]:
        async with (
            aiohttp.ClientSession(timeout=self._timeout()) as session,
            session.get(
                f"{self.base_url}/api/room-info",
                ssl=self._ssl,
                headers={"Accept": "application/json"},
            ) as response,
        ):
            return await self._json(response)

    async def list_files(self) -> list[dict[str, Any]]:
        async with (
            aiohttp.ClientSession(timeout=self._timeout()) as session,
            session.get(
                f"{self.base_url}/api/files",
                ssl=self._ssl,
                headers={"Accept": "application/json"},
            ) as response,
        ):
            payload = await self._json(response)
        files = payload.get("files")
        if not isinstance(files, list):
            raise LocalClientError("文件列表格式错误")
        return [item for item in files if isinstance(item, dict)]

    # ------------------------------------------------------------------ upload
    async def upload_file(
        self,
        path: Path,
        *,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> UploadResult:
        path = Path(path)
        stat = path.stat()
        size = int(stat.st_size)
        name = path.name
        async with aiohttp.ClientSession(timeout=self._timeout()) as session:
            if size == 0:
                upload_id, _ = await self._init_upload(
                    session, name, 0, stat.st_mtime, cancel_event
                )
                await self._complete(session, upload_id, cancel_event)
                if on_progress:
                    on_progress(0, 0)
                return UploadResult(name=name, size=0, upload_id=upload_id)

            upload_id, offset = await self._init_upload(
                session, name, size, stat.st_mtime, cancel_event
            )
            if on_progress:
                on_progress(offset, size)
            attempt = 0
            async with aiofiles.open(path, "rb") as handle:
                while offset < size:
                    self._check_cancel(cancel_event)
                    await handle.seek(offset)
                    chunk = await handle.read(min(self.chunk_size, size - offset))
                    if not chunk:
                        raise LocalClientError(f"读取文件失败（偏移 {offset}）")
                    try:
                        offset = await self._put_chunk(
                            session, upload_id, offset, chunk, cancel_event
                        )
                    except (TimeoutError, aiohttp.ClientError) as exc:
                        attempt += 1
                        if attempt > self.retries:
                            raise LocalClientError(f"上传中断: {exc}") from exc
                        logger.warning("上传分片失败（%s），重试 %d/%d", exc, attempt, self.retries)
                        await asyncio.sleep(min(5.0, 0.5 * attempt))
                        upload_id, offset = await self._init_upload(
                            session, name, size, stat.st_mtime, cancel_event
                        )
                        continue
                    attempt = 0
                    if on_progress:
                        on_progress(offset, size)
            self._check_cancel(cancel_event)
            await self._complete(session, upload_id, cancel_event)
        return UploadResult(name=name, size=size, upload_id=upload_id)

    async def _init_upload(
        self,
        session: aiohttp.ClientSession,
        name: str,
        size: int,
        mtime: float,
        cancel_event: threading.Event | None,
    ) -> tuple[str, int]:
        self._check_cancel(cancel_event)
        payload = {"filename": name, "size": size, "mtime": int(mtime or 0), "nonce": "desktop"}
        async with session.post(
            f"{self.base_url}/api/upload/init", json=payload, ssl=self._ssl
        ) as response:
            data = await self._json(response)
        upload_id = data.get("upload_id")
        if not isinstance(upload_id, str) or not upload_id:
            raise LocalClientError("上传初始化失败")
        raw_offset = data.get("offset", 0)
        offset = int(raw_offset) if isinstance(raw_offset, (int, float)) else 0
        return upload_id, max(0, offset)

    async def _put_chunk(
        self,
        session: aiohttp.ClientSession,
        upload_id: str,
        offset: int,
        chunk: bytes,
        cancel_event: threading.Event | None,
    ) -> int:
        self._check_cancel(cancel_event)
        async with session.put(
            f"{self.base_url}/api/upload/chunk/{upload_id}?offset={offset}",
            data=chunk,
            ssl=self._ssl,
            headers={"Content-Type": "application/octet-stream"},
        ) as response:
            if response.status == 409:
                payload = await response.json(content_type=None)
                current = payload.get("offset") if isinstance(payload, dict) else None
                if isinstance(current, (int, float)):
                    return int(current)
                raise LocalClientError("上传偏移冲突")
            data = await self._json(response)
        value = data.get("offset", offset + len(chunk))
        return int(value) if isinstance(value, (int, float)) else offset + len(chunk)

    async def _complete(
        self,
        session: aiohttp.ClientSession,
        upload_id: str,
        cancel_event: threading.Event | None,
    ) -> None:
        self._check_cancel(cancel_event)
        async with session.post(
            f"{self.base_url}/api/upload/complete/{upload_id}", ssl=self._ssl
        ) as response:
            await self._json(response)

    # ---------------------------------------------------------------- download
    async def download_file(
        self,
        name: str,
        target: Path,
        *,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> int:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        part_path = target.with_name(target.name + ".part")
        url = f"{self.base_url}/api/download/{quote(name, safe='')}"
        written = 0
        try:
            async with (
                aiohttp.ClientSession(timeout=self._timeout()) as session,
                session.get(url, ssl=self._ssl) as response,
            ):
                if response.status >= 400:
                    await self._json(response)
                    raise LocalClientError(f"下载失败（HTTP {response.status}）")
                total = int(response.headers.get("Content-Length") or 0)
                async with aiofiles.open(part_path, "wb") as handle:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        self._check_cancel(cancel_event)
                        await handle.write(chunk)
                        written += len(chunk)
                        if on_progress:
                            on_progress(written, total)
            self._check_cancel(cancel_event)
            os.replace(part_path, target)
            return written
        except (TransferCancelled, LocalClientError):
            part_path.unlink(missing_ok=True)
            raise
        except (TimeoutError, aiohttp.ClientError, OSError) as exc:
            part_path.unlink(missing_ok=True)
            raise LocalClientError(f"下载失败: {exc}") from exc

    async def download_zip(
        self,
        names: list[str],
        target: Path,
        *,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> int:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        part_path = target.with_name(target.name + ".part")
        written = 0
        try:
            async with (
                aiohttp.ClientSession(timeout=self._timeout()) as session,
                session.post(
                    f"{self.base_url}/api/zip-download",
                    json={"files": names},
                    ssl=self._ssl,
                ) as response,
            ):
                if response.status >= 400:
                    await self._json(response)
                    raise LocalClientError(f"打包下载失败（HTTP {response.status}）")
                total = int(response.headers.get("Content-Length") or 0)
                async with aiofiles.open(part_path, "wb") as handle:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        self._check_cancel(cancel_event)
                        await handle.write(chunk)
                        written += len(chunk)
                        if on_progress:
                            on_progress(written, total)
            self._check_cancel(cancel_event)
            os.replace(part_path, target)
            return written
        except (TransferCancelled, LocalClientError):
            part_path.unlink(missing_ok=True)
            raise
        except (TimeoutError, aiohttp.ClientError, OSError) as exc:
            part_path.unlink(missing_ok=True)
            raise LocalClientError(f"打包下载失败: {exc}") from exc

    # ------------------------------------------------------------------ delete
    async def delete_files(self, names: list[str]) -> dict[str, Any]:
        if not names:
            return {"deleted": [], "failed": []}
        async with (
            aiohttp.ClientSession(timeout=self._timeout()) as session,
            session.post(
                f"{self.base_url}/api/batch-delete",
                json={"files": names},
                ssl=self._ssl,
            ) as response,
        ):
            return await self._json(response)

    # -------------------------------------------------------------------- chat
    async def chat_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """读取最近聊天记录（网页端与桌面端共用）。"""
        async with (
            aiohttp.ClientSession(timeout=self._timeout()) as session,
            session.get(
                f"{self.base_url}/api/chat/history",
                params={"limit": max(1, min(200, int(limit)))},
                ssl=self._ssl,
                headers={"Accept": "application/json"},
            ) as response,
        ):
            payload = await self._json(response)
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise LocalClientError("聊天记录格式错误")
        return [item for item in messages if isinstance(item, dict)]

    async def send_chat(self, message: str) -> dict[str, Any]:
        """发送文本，返回服务端创建的消息对象。"""
        text = str(message or "").strip()
        if not text:
            raise LocalClientError("消息不能为空")
        async with (
            aiohttp.ClientSession(timeout=self._timeout()) as session,
            session.post(
                f"{self.base_url}/api/chat/send",
                json={"message": text},
                ssl=self._ssl,
            ) as response,
        ):
            payload = await self._json(response)
        created = payload.get("message")
        if not isinstance(created, dict):
            raise LocalClientError("服务端未返回消息")
        return created

    async def delete_chat(self, message_id: str) -> None:
        """删除一条聊天消息。"""
        if not message_id:
            raise LocalClientError("消息 ID 为空")
        async with (
            aiohttp.ClientSession(timeout=self._timeout()) as session,
            session.delete(
                f"{self.base_url}/api/chat/message/{quote(message_id, safe='')}",
                ssl=self._ssl,
            ) as response,
        ):
            await self._json(response)
