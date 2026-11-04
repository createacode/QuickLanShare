from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from quicklanshare.services.chat_client import ChatSocketClient
from quicklanshare.services.config import Config
from quicklanshare.services.local_client import LocalShareClient
from quicklanshare.services.server import FileTransferServer


async def wait_until(predicate: Any, timeout: float = 6.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("等待条件超时")


class ChatSocketUnitTests(unittest.TestCase):
    def make_client(self, base: str = "http://127.0.0.1:8888") -> ChatSocketClient:
        self.history: list[list[dict[str, Any]]] = []
        self.messages: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.statuses: list[str] = []
        self.shutdowns: list[str] = []
        return ChatSocketClient(
            base,
            on_history=self.history.append,
            on_message=self.messages.append,
            on_deleted=self.deleted.append,
            on_status=self.statuses.append,
            on_shutdown=self.shutdowns.append,
        )

    def test_https_uses_wss(self) -> None:
        client = self.make_client("https://127.0.0.1:9443")
        self.assertEqual(client._ws_url, "wss://127.0.0.1:9443/ws")

    def test_handle_ignores_bad_payloads(self) -> None:
        client = self.make_client()
        client._handle("not json")
        client._handle("[]")
        client._handle(json.dumps({"type": "welcome", "chat_history": "bad"}))
        client._handle(json.dumps({"type": "chat_message", "message": "bad"}))
        client._handle(json.dumps({"type": "delete_message", "message_id": 1}))
        self.assertEqual(self.history, [])
        self.assertEqual(self.messages, [])
        self.assertEqual(self.deleted, [])

    def test_handle_welcome_and_events(self) -> None:
        client = self.make_client()
        client._handle(
            json.dumps(
                {
                    "type": "welcome",
                    "chat_history": [{"id": "1", "message": "hi"}, {"bad": True}, 3],
                }
            )
        )
        self.assertEqual(self.history, [[{"id": "1", "message": "hi"}, {"bad": True}]])
        client._handle(json.dumps({"type": "chat_message", "message": {"id": "2"}}))
        self.assertEqual(self.messages, [{"id": "2"}])
        client._handle(json.dumps({"type": "delete_message", "message_id": "2"}))
        self.assertEqual(self.deleted, ["2"])
        client._handle(json.dumps({"type": "server_shutdown", "reason": "auto-shutdown"}))
        self.assertEqual(self.statuses[-1], "offline")
        self.assertEqual(self.shutdowns, ["auto-shutdown"])
        self.assertTrue(client._closed)

    def test_status_callback_failure_is_swallowed(self) -> None:
        def broken(_status: str) -> None:
            raise RuntimeError("boom")

        client = ChatSocketClient(
            "http://127.0.0.1:8888",
            on_history=self.history.append if hasattr(self, "history") else lambda _x: None,
            on_message=lambda _x: None,
            on_deleted=lambda _x: None,
            on_status=broken,
        )
        client._notify("connected")
        client.close()
        self.assertTrue(client._closed)


class ChatSocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = Config(
            host="127.0.0.1",
            port=0,
            data_dir=self.root,
            auto_shutdown_enabled=False,
            access_log=False,
            allow_any_host=True,
        )
        self.server = FileTransferServer(self.config)
        self.port = await self.server.start()
        self.base = f"http://127.0.0.1:{self.port}"
        self.client = LocalShareClient(self.base)
        self.task: asyncio.Task[None] | None = None

    async def asyncTearDown(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self.server.aclose()
        self._tmp.cleanup()

    async def test_socket_history_message_and_delete(self) -> None:
        first = await self.client.send_chat("先发一条，连接后应看到历史")
        statuses: list[str] = []
        history: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        deleted: list[str] = []

        socket = ChatSocketClient(
            self.base,
            on_history=history.extend,
            on_message=messages.append,
            on_deleted=deleted.append,
            on_status=statuses.append,
        )
        self.task = asyncio.create_task(socket.run())
        await wait_until(lambda: "connected" in statuses)
        await wait_until(lambda: any(item["id"] == first["id"] for item in history))

        second = await self.client.send_chat("实时消息")
        await wait_until(lambda: any(item["id"] == second["id"] for item in messages))
        await self.client.delete_chat(second["id"])
        await wait_until(lambda: second["id"] in deleted)

        socket.close()
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
        self.assertIn("connected", statuses)
        self.assertEqual(messages[0]["client_ip"] in ("127.0.0.1", "::1"), True)


if __name__ == "__main__":
    unittest.main()
