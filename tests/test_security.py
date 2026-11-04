from __future__ import annotations

import unittest
from typing import ClassVar

import aiohttp

from tests.helpers import ServerTestCase


class SecurityTests(ServerTestCase):
    async def test_sibling_directory_download_traversal_blocked(self):
        sibling = self.data_dir / "uploads2"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
        response = await self.raw_get("/api/download/..%2Fuploads2%2Fsecret.txt")
        self.assertIn(b"400", self.status_line(response))
        self.assertNotIn(b"TOP-SECRET", response)

    async def test_sibling_directory_delete_traversal_blocked(self):
        sibling = self.data_dir / "uploads2"
        sibling.mkdir()
        target = sibling / "secret.txt"
        target.write_text("keep-me", encoding="utf-8")
        response = await self.raw_delete("/api/delete/..%2Fuploads2%2Fsecret.txt")
        self.assertIn(b"400", self.status_line(response))
        self.assertTrue(target.exists())

    async def test_cross_origin_request_blocked(self):
        async with self.session.post(
            self.base + "/api/batch-delete",
            json={"files": ["x"]},
            headers={"Origin": "http://evil.example"},
        ) as response:
            self.assertEqual(response.status, 403)

    async def test_cross_site_fetch_metadata_blocked(self):
        async with self.session.post(
            self.base + "/api/batch-delete",
            json={"files": ["x"]},
            headers={"Sec-Fetch-Site": "cross-site"},
        ) as response:
            self.assertEqual(response.status, 403)

    async def test_text_plain_json_body_rejected(self):
        await self.upload_chunked("victim.txt", b"data")
        async with self.session.post(
            self.base + "/api/batch-delete",
            data=b'{"files":["victim.txt"]}',
            headers={"Content-Type": "text/plain"},
        ) as response:
            self.assertEqual(response.status, 415)
        self.assertTrue((self.uploads / "victim.txt").exists())

    async def test_cross_origin_multipart_upload_blocked(self):
        form = aiohttp.FormData()
        form.add_field("file", b"evil", filename="evil.txt")
        async with self.session.post(
            self.base + "/api/upload",
            data=form,
            headers={"Origin": "http://evil.example"},
        ) as response:
            self.assertEqual(response.status, 403)
        self.assertFalse((self.uploads / "evil.txt").exists())

    async def test_null_origin_only_allowed_for_zip(self):
        await self.upload_chunked("zip-null.txt", b"zip")
        async with self.session.post(
            self.base + "/api/zip-download",
            data={"files": ["zip-null.txt"]},
            headers={"Origin": "null"},
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"PK", await response.read())
        async with self.session.post(
            self.base + "/api/batch-delete",
            json={"files": ["zip-null.txt"]},
            headers={"Origin": "null"},
        ) as response:
            self.assertEqual(response.status, 403)

    async def test_websocket_cross_origin_blocked(self):
        with self.assertRaises(aiohttp.WSServerHandshakeError) as context:
            await self.session.ws_connect(
                self.base + "/ws", headers={"Origin": "http://evil.example"}
            )
        self.assertEqual(context.exception.status, 403)

    async def test_websocket_same_origin_allowed(self):
        async with self.session.ws_connect(self.base + "/ws", headers={"Origin": self.base}) as ws:
            welcome = await ws.receive_json()
            self.assertEqual(welcome["type"], "welcome")


class HostHeaderTests(ServerTestCase):
    config_overrides: ClassVar[dict[str, bool]] = {"allow_any_host": False}

    async def test_unknown_host_rejected(self):
        response = await self.raw_get("/api/files", host="evil.example:1234")
        self.assertIn(b"403", self.status_line(response))

    async def test_loopback_host_allowed(self):
        response = await self.raw_get("/api/files", host=f"127.0.0.1:{self.port}")
        self.assertIn(b"200", self.status_line(response))


if __name__ == "__main__":
    unittest.main()
