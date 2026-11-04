from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from quicklanshare.services.config import Config
from quicklanshare.services.local_client import (
    LocalClientError,
    LocalShareClient,
    TransferCancelled,
)
from quicklanshare.services.server import FileTransferServer


class LocalClientTests(unittest.IsolatedAsyncioTestCase):
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
        self.client = LocalShareClient(f"http://127.0.0.1:{self.port}", chunk_size=64 * 1024)

    async def asyncTearDown(self) -> None:
        await self.server.aclose()
        self._tmp.cleanup()

    async def test_upload_list_download_delete(self) -> None:
        source = self.root / "报告 2026.txt"
        source.write_bytes("局域网传输".encode() * 1000)
        progress: list[tuple[int, int]] = []
        result = await self.client.upload_file(
            source, on_progress=lambda done, total: progress.append((done, total))
        )
        self.assertEqual(result.name, "报告 2026.txt")
        self.assertEqual(result.size, source.stat().st_size)
        self.assertTrue(progress)
        self.assertEqual(progress[-1][0], result.size)

        files = await self.client.list_files()
        entry = next(item for item in files if item["name"] == "报告 2026.txt")
        self.assertEqual(entry["size"], source.stat().st_size)

        target = self.root / "downloaded.txt"
        await self.client.download_file(
            "报告 2026.txt", target, on_progress=lambda done, total: None
        )
        self.assertEqual(target.read_bytes(), source.read_bytes())

        payload = await self.client.delete_files(["报告 2026.txt"])
        self.assertEqual(payload["deleted"], ["报告 2026.txt"])
        self.assertEqual(await self.client.list_files(), [])

    async def test_zero_byte_upload(self) -> None:
        source = self.root / "empty.bin"
        source.write_bytes(b"")
        result = await self.client.upload_file(source)
        self.assertEqual(result.size, 0)
        files = await self.client.list_files()
        self.assertEqual(files[0]["size"], 0)

    async def test_cancel_before_upload(self) -> None:
        import threading

        source = self.root / "cancel.bin"
        source.write_bytes(b"x" * 1024)
        event = threading.Event()
        event.set()
        with self.assertRaises(TransferCancelled):
            await self.client.upload_file(source, cancel_event=event)

    async def test_zip_download(self) -> None:
        first = self.root / "a.txt"
        first.write_text("AAA", encoding="utf-8")
        second = self.root / "b.txt"
        second.write_text("BBB", encoding="utf-8")
        await self.client.upload_file(first)
        await self.client.upload_file(second)
        archive_path = self.root / "bundle.zip"
        await self.client.download_zip(["a.txt", "b.txt"], archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(sorted(archive.namelist()), ["a.txt", "b.txt"])
            self.assertEqual(archive.read("a.txt"), b"AAA")

    async def test_missing_download_raises(self) -> None:
        with self.assertRaises(LocalClientError):
            await self.client.download_file("不存在.bin", self.root / "x.bin")

    async def test_chat_send_history_delete(self) -> None:
        created = await self.client.send_chat("你好，局域网")
        self.assertEqual(created["message"], "你好，局域网")
        history = await self.client.chat_history()
        self.assertEqual([item["id"] for item in history], [created["id"]])
        await self.client.delete_chat(created["id"])
        self.assertEqual(await self.client.chat_history(), [])


if __name__ == "__main__":
    unittest.main()
