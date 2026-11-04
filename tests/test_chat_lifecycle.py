from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import aiohttp

from quicklanshare.services.chat import ChatStore
from quicklanshare.services.config import Config
from quicklanshare.services.server import FileTransferServer


class RestartableServer:
    def __init__(self, data_dir: Path, **overrides):
        self.data_dir = data_dir
        self.overrides = overrides
        self.server: FileTransferServer | None = None
        self.session: aiohttp.ClientSession | None = None
        self.base = ""

    async def start(self):
        kwargs = dict(
            host="127.0.0.1",
            port=0,
            data_dir=self.data_dir,
            open_browser=False,
            auto_shutdown_enabled=False,
            access_log=False,
            allow_any_host=True,
        )
        kwargs.update(self.overrides)
        self.server = FileTransferServer(Config(**kwargs))
        port = await self.server.start()
        self.base = f"http://127.0.0.1:{port}"
        self.session = aiohttp.ClientSession()
        return self

    async def close(self):
        if self.session:
            await self.session.close()
        if self.server:
            await self.server.aclose()


class ChatPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.instances: list[RestartableServer] = []

    async def asyncTearDown(self):
        for instance in self.instances:
            await instance.close()
        self._tmp.cleanup()

    async def new_server(self, **overrides):
        instance = await RestartableServer(self.data_dir, **overrides).start()
        self.instances.append(instance)
        return instance

    async def test_message_survives_restart_and_can_be_deleted(self):
        first = await self.new_server()
        async with first.session.post(
            first.base + "/api/chat/send", json={"message": "hello"}
        ) as response:
            message = (await response.json())["message"]
        await first.close()

        second = await self.new_server()
        async with second.session.get(second.base + "/api/chat/history") as response:
            history = (await response.json())["messages"]
        self.assertEqual([item["id"] for item in history], [message["id"]])
        async with second.session.delete(
            second.base + f"/api/chat/message/{message['id']}"
        ) as response:
            self.assertEqual(response.status, 200)
        async with second.session.get(second.base + "/api/chat/history") as response:
            self.assertEqual((await response.json())["messages"], [])
        await second.close()

        third = await self.new_server()
        async with third.session.get(third.base + "/api/chat/history") as response:
            self.assertEqual((await response.json())["messages"], [])
        chat_files = list((self.data_dir / "chat").glob("chat_*.jsonl"))
        self.assertTrue(chat_files)
        self.assertFalse(
            any(line.strip() for line in chat_files[0].read_text(encoding="utf-8").splitlines())
        )

    async def test_download_counter_persists(self):
        first = await self.new_server()
        form = aiohttp.FormData()
        form.add_field("file", b"counter", filename="counter.txt")
        async with first.session.post(first.base + "/api/upload", data=form) as response:
            self.assertEqual(response.status, 200)
        async with first.session.get(first.base + "/api/download/counter.txt") as response:
            await response.read()
        await first.server.files.flush()
        await first.close()

        second = await self.new_server()
        async with second.session.get(second.base + "/api/files") as response:
            files = (await response.json())["files"]
        entry = next(item for item in files if item["name"] == "counter.txt")
        self.assertEqual(entry["download_count"], 1)
        await second.close()

    async def test_legacy_text_history_is_migrated(self):
        chat_dir = self.data_dir / "chat"
        chat_dir.mkdir(parents=True)
        legacy = chat_dir / "chat_20260101.txt"
        legacy.write_text(
            "1.2.3.4 2026-01-01 12:00:00\nhello\n\n5.6.7.8 2026-01-01 12:01:00\nworld\n\n",
            encoding="utf-8",
        )
        instance = await self.new_server()
        async with instance.session.get(instance.base + "/api/chat/history") as response:
            history = (await response.json())["messages"]
        self.assertEqual([item["message"] for item in history], ["hello", "world"])
        self.assertTrue((chat_dir / "chat_20260101.jsonl").exists())
        self.assertTrue((chat_dir / "chat_20260101.txt.bak").exists())
        self.assertFalse(legacy.exists())

    async def test_message_outside_memory_can_still_be_deleted(self):
        store = ChatStore(Config(data_dir=self.data_dir))
        first = await store.add("u1", "1.1.1.1", "one")
        second = await store.add("u2", "2.2.2.2", "two")
        store.memory_limit = 1
        store._messages = store._messages[-1:]
        self.assertTrue(await store.delete(first["id"]))
        self.assertEqual([item["id"] for item in store.history(10)], [second["id"]])


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)

    async def test_auto_shutdown_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(
                host="127.0.0.1",
                port=0,
                data_dir=Path(tmp),
                open_browser=False,
                auto_shutdown_enabled=True,
                auto_shutdown_hours=0.0003,
                access_log=False,
                allow_any_host=True,
            )
            server = FileTransferServer(config)
            await asyncio.wait_for(server.run(), timeout=8)
            self.assertTrue(server._closed)

    async def test_extend_and_manual_shutdown_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(
                host="127.0.0.1",
                port=0,
                data_dir=Path(tmp),
                open_browser=False,
                auto_shutdown_enabled=False,
                auto_shutdown_max_hours=24.0,
                access_log=False,
                allow_any_host=True,
            )
            server = FileTransferServer(config)
            port = await server.start()
            base = f"http://127.0.0.1:{port}"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    base + "/api/auto-shutdown/extend", json={"hours": 3}
                ) as response:
                    body = await response.json()
                    self.assertEqual(response.status, 200)
                    self.assertTrue(body["enabled"])
                    self.assertGreater(body["remain_seconds"], 10000)
                for _ in range(10):
                    async with session.post(
                        base + "/api/auto-shutdown/extend", json={"hours": 3}
                    ) as response:
                        body = await response.json()
                self.assertTrue(body["capped"])
                self.assertLessEqual(body["remain_seconds"], 24 * 3600)
                async with session.get(base + "/api/auto-shutdown/status") as response:
                    self.assertTrue((await response.json())["enabled"])
                async with session.post(
                    base + "/api/shutdown", json={"confirm": True, "force": False}
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue((await response.json())["closing"])
            await asyncio.wait_for(server._stop_event.wait(), timeout=3)
            await server.aclose()

    async def test_shutdown_requires_force_when_downloading(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(
                host="127.0.0.1",
                port=0,
                data_dir=Path(tmp),
                open_browser=False,
                auto_shutdown_enabled=False,
                access_log=False,
                allow_any_host=True,
            )
            server = FileTransferServer(config)
            port = await server.start()
            base = f"http://127.0.0.1:{port}"
            server.active_downloads = 1
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    base + "/api/shutdown", json={"confirm": True, "force": False}
                ) as response:
                    body = await response.json()
                    self.assertEqual(response.status, 409)
                    self.assertEqual(body["active_downloads"], 1)
                    self.assertTrue(body["requires_force"])
                self.assertFalse(server._stop_event.is_set())
                async with session.post(
                    base + "/api/shutdown", json={"confirm": True, "force": True}
                ) as response:
                    self.assertEqual(response.status, 200)
            await asyncio.wait_for(server._stop_event.wait(), timeout=3)
            await server.aclose()

    async def test_shutdown_broadcasts_to_all_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(
                host="127.0.0.1",
                port=0,
                data_dir=Path(tmp),
                open_browser=False,
                auto_shutdown_enabled=False,
                access_log=False,
                allow_any_host=True,
            )
            server = FileTransferServer(config)
            port = await server.start()
            base = f"http://127.0.0.1:{port}"
            async with aiohttp.ClientSession() as session:
                first = await session.ws_connect(base + "/ws")
                second = await session.ws_connect(base + "/ws")
                try:
                    await first.receive_json()
                    await second.receive_json()
                    async with session.post(
                        base + "/api/shutdown", json={"confirm": True, "force": False}
                    ) as response:
                        self.assertEqual(response.status, 200)
                    for ws in (first, second):
                        event = await asyncio.wait_for(ws.receive_json(), timeout=3)
                        self.assertEqual(event["type"], "server_shutdown")
                finally:
                    await first.close()
                    await second.close()
            await asyncio.wait_for(server._stop_event.wait(), timeout=3)
            await server.aclose()


if __name__ == "__main__":
    unittest.main()
