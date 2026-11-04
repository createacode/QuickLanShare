"""Shared test helpers for the QuickLanShare test-suite."""

from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

import aiohttp

from quicklanshare.services.config import Config
from quicklanshare.services.server import FileTransferServer


class ServerTestCase(unittest.IsolatedAsyncioTestCase):
    config_overrides: ClassVar[dict] = {}

    async def asyncSetUp(self) -> None:
        asyncio.get_running_loop().set_debug(False)
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        kwargs = dict(
            host="127.0.0.1",
            port=0,
            data_dir=self.data_dir,
            open_browser=False,
            auto_shutdown_enabled=False,
            access_log=False,
            allow_any_host=True,
        )
        kwargs.update(self.config_overrides)
        self.config = Config(**kwargs)
        self.server = FileTransferServer(self.config)
        self.port = await self.server.start()
        self.base = f"http://127.0.0.1:{self.port}"
        self.session = aiohttp.ClientSession()
        self.uploads = self.data_dir / "uploads"

    async def asyncTearDown(self) -> None:
        await self.session.close()
        await self.server.aclose()
        self._tmp.cleanup()

    # ------------------------------------------------------------------ HTTP
    async def get_json(self, path: str) -> tuple[int, dict]:
        async with self.session.get(self.base + path) as response:
            return response.status, await response.json()

    async def post_json(self, path: str, payload: dict | None = None, **kwargs) -> tuple[int, dict]:
        async with self.session.post(self.base + path, json=payload or {}, **kwargs) as response:
            return response.status, await response.json()

    async def delete_json(self, path: str) -> tuple[int, dict]:
        async with self.session.delete(self.base + path) as response:
            return response.status, await response.json()

    async def raw_request(self, request: bytes, timeout: float = 10.0) -> bytes:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(request)
        await writer.drain()
        chunks: list[bytes] = []
        try:
            while True:
                data = await asyncio.wait_for(reader.read(65536), timeout=timeout)
                if not data:
                    break
                chunks.append(data)
        except TimeoutError:
            pass
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return b"".join(chunks)

    async def raw_get(self, path: str, host: str | None = None) -> bytes:
        host = host or f"127.0.0.1:{self.port}"
        request = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n").encode()
        return await self.raw_request(request)

    async def raw_delete(self, path: str, host: str | None = None) -> bytes:
        host = host or f"127.0.0.1:{self.port}"
        request = (f"DELETE {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n").encode()
        return await self.raw_request(request)

    def multipart_request(self, filename: str, content: bytes) -> bytes:
        boundary = "----qls-test"
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        body = head + content + f"\r\n--{boundary}--\r\n".encode()
        return (
            f"POST /api/upload HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.port}\r\n"
            f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        ).encode() + body

    # ---------------------------------------------------------------- uploads
    async def upload_chunked(
        self, filename: str, payload: bytes, chunk_size: int = 4, mtime: int = 0
    ) -> dict:
        status, init = await self.post_json(
            "/api/upload/init", {"filename": filename, "size": len(payload), "mtime": mtime}
        )
        self.assertEqual(status, 200, init)
        upload_id = init["upload_id"]
        offset = init["offset"]
        while offset < len(payload):
            block = payload[offset : offset + chunk_size]
            async with self.session.put(
                self.base + f"/api/upload/chunk/{upload_id}?offset={offset}", data=block
            ) as response:
                self.assertEqual(response.status, 200, await response.text())
                body = await response.json()
                self.assertEqual(body["offset"], offset + len(block))
            offset += len(block)
        status, done = await self.post_json(f"/api/upload/complete/{upload_id}", {})
        self.assertEqual(status, 200, done)
        return done

    @staticmethod
    def status_line(response: bytes) -> bytes:
        return response.split(b"\r\n", 1)[0]


def json_body(response: bytes) -> dict:
    _, _, body = response.partition(b"\r\n\r\n")
    return json.loads(body.decode("utf-8"))
