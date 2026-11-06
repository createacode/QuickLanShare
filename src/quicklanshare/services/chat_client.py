"""桌面端聊天 WebSocket 客户端。

保持与网页端同一个房间：启动后连接 ``/ws``，接收历史、消息与删除事件；
断线后按退避重连。发送走 HTTP（有明确的消息 id），WebSocket 只负责订阅。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

logger = logging.getLogger("quicklanshare.chat.client")

HistoryCallback = Callable[[list[dict[str, Any]]], None]
MessageCallback = Callable[[dict[str, Any]], None]
DeletedCallback = Callable[[str], None]
BulkDeletedCallback = Callable[[list[str]], None]
EditedCallback = Callable[[dict[str, Any]], None]
ProfileCallback = Callable[[dict[str, Any]], None]
ScopeCallback = Callable[[dict[str, Any]], None]
StatusCallback = Callable[[str], None]


class ChatSocketClient:
    """订阅服务端 ``/ws`` 的只读客户端（发送使用 HTTP API）。"""

    def __init__(
        self,
        base_url: str,
        *,
        on_history: HistoryCallback,
        on_message: MessageCallback,
        on_deleted: DeletedCallback,
        on_status: StatusCallback,
        on_shutdown: Callable[[str], None] | None = None,
        on_bulk_deleted: BulkDeletedCallback | None = None,
        on_edited: EditedCallback | None = None,
        on_profile: ProfileCallback | None = None,
        on_scope: ScopeCallback | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url.startswith("https://"):
            self._ws_url = "wss://" + self.base_url[len("https://") :] + "/ws"
            self._ssl: bool = False
        else:
            self._ws_url = "ws://" + self.base_url[len("http://") :] + "/ws"
            self._ssl = True
        self._on_history = on_history
        self._on_message = on_message
        self._on_deleted = on_deleted
        self._on_status = on_status
        self._on_shutdown = on_shutdown
        self._on_bulk_deleted = on_bulk_deleted
        self._on_edited = on_edited
        self._on_profile = on_profile
        self._on_scope = on_scope
        self._closed = False

    async def run(self) -> None:
        """连接并持续接收，直到任务被取消或服务端关闭。"""
        delay = 1.5
        while not self._closed:
            self._notify("connecting")
            try:
                timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.ws_connect(
                        self._ws_url,
                        heartbeat=30,
                        ssl=self._ssl,
                        headers={"User-Agent": "QuickLanShare-Desktop"},
                    ) as ws,
                ):
                    delay = 1.5
                    self._notify("connected")
                    logger.info("文本共享已连接: %s", self._ws_url)
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            self._handle(message.data)
                        elif message.type == aiohttp.WSMsgType.ERROR:
                            break
                    if self._closed:
                        break
            except asyncio.CancelledError:
                raise
            except (TimeoutError, aiohttp.ClientError, OSError) as exc:
                logger.warning("文本共享连接断开: %s", exc)
            except Exception:
                logger.exception("文本共享订阅异常")
            if self._closed:
                break
            self._notify("reconnecting")
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            delay = min(15.0, delay * 1.8)

    def _notify(self, status: str) -> None:
        try:
            self._on_status(status)
        except Exception:
            logger.exception("文本共享状态回调失败")

    def _handle(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except ValueError:
            return
        if not isinstance(payload, dict):
            return
        event = payload.get("type")
        if event == "welcome":
            history = payload.get("chat_history")
            if isinstance(history, list):
                messages = [item for item in history if isinstance(item, dict)]
                self._on_history(messages)
        elif event == "chat_message":
            message = payload.get("message")
            if isinstance(message, dict):
                self._on_message(message)
        elif event == "delete_message":
            message_id = payload.get("message_id")
            if isinstance(message_id, str) and message_id:
                self._on_deleted(message_id)
        elif event == "delete_messages":
            ids = payload.get("message_ids")
            if isinstance(ids, list) and self._on_bulk_deleted is not None:
                deleted = [item for item in ids if isinstance(item, str) and item]
                if deleted:
                    self._on_bulk_deleted(deleted)
        elif event == "edit_message":
            message = payload.get("message")
            if isinstance(message, dict) and self._on_edited is not None:
                self._on_edited(message)
        elif event == "profile_updated":
            if self._on_profile is not None:
                self._on_profile(
                    {"ip": str(payload.get("ip") or ""), "name": str(payload.get("name") or "")}
                )
        elif event == "ip_scope_changed":
            if self._on_scope is not None:
                self._on_scope(payload)
        elif event == "server_shutdown":
            self._closed = True
            self._notify("offline")
            if self._on_shutdown is not None:
                try:
                    self._on_shutdown(str(payload.get("reason") or "shutdown"))
                except Exception:
                    logger.exception("关闭回调失败")

    def close(self) -> None:
        self._closed = True


__all__ = ["ChatSocketClient"]
