from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from quicklanshare import __version__
from tests.helpers import ServerTestCase, json_body


class UploadTests(ServerTestCase):
    async def test_chunked_upload_roundtrip_and_resume(self):
        payload = b"0123456789" * 5
        status, init = await self.post_json(
            "/api/upload/init",
            {"filename": "测试 文件 #1.txt", "size": len(payload), "mtime": 123},
        )
        self.assertEqual(status, 200, init)
        upload_id = init["upload_id"]
        self.assertEqual(init["offset"], 0)
        self.assertEqual(init["name"], "测试 文件 #1.txt")

        async with self.session.put(
            self.base + f"/api/upload/chunk/{upload_id}?offset=0", data=payload[:20]
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())["offset"], 20)

        # Re-initialising with the same fingerprint resumes at the current offset.
        status, again = await self.post_json(
            "/api/upload/init",
            {"filename": "测试 文件 #1.txt", "size": len(payload), "mtime": 123},
        )
        self.assertEqual(again["upload_id"], upload_id)
        self.assertEqual(again["offset"], 20)

        async with self.session.put(
            self.base + f"/api/upload/chunk/{upload_id}?offset=20", data=payload[20:]
        ) as response:
            self.assertEqual(response.status, 200)
        status, done = await self.post_json(f"/api/upload/complete/{upload_id}", {})
        self.assertEqual(status, 200, done)
        self.assertEqual((self.uploads / done["name"]).read_bytes(), payload)

        status, files = await self.get_json("/api/files")
        self.assertEqual(status, 200)
        entry = next(item for item in files["files"] if item["name"] == done["name"])
        self.assertEqual(entry["size"], len(payload))
        self.assertTrue(entry["url"].startswith("/api/download/"))

    async def test_session_nonce_separates_identical_uploads(self):
        payload = b"nonce"
        _, first = await self.post_json(
            "/api/upload/init",
            {"filename": "same.bin", "size": len(payload), "mtime": 1, "nonce": "tab-a"},
        )
        _, second = await self.post_json(
            "/api/upload/init",
            {"filename": "same.bin", "size": len(payload), "mtime": 1, "nonce": "tab-b"},
        )
        self.assertNotEqual(first["upload_id"], second["upload_id"])
        _, resumed = await self.post_json(
            "/api/upload/init",
            {"filename": "same.bin", "size": len(payload), "mtime": 1, "nonce": "tab-a"},
        )
        self.assertEqual(resumed["upload_id"], first["upload_id"])

    async def test_offset_conflict_returns_current_offset(self):
        payload = b"abcdef"
        _, init = await self.post_json(
            "/api/upload/init", {"filename": "a.bin", "size": len(payload)}
        )
        upload_id = init["upload_id"]
        async with self.session.put(
            self.base + f"/api/upload/chunk/{upload_id}?offset=0", data=b"abc"
        ) as response:
            self.assertEqual(response.status, 200)
        async with self.session.put(
            self.base + f"/api/upload/chunk/{upload_id}?offset=0", data=b"xyz"
        ) as response:
            self.assertEqual(response.status, 409)
            body = await response.json()
            self.assertEqual(body["offset"], 3)

    async def test_declared_size_limit(self):
        status, body = await self.post_json(
            "/api/upload/init",
            {"filename": "huge.bin", "size": self.config.max_upload_size + 1},
        )
        self.assertEqual(status, 413, body)

    async def test_upload_reserved_metadata_name_is_mangled(self):
        status, done = await self.post_json(
            "/api/upload/init", {"filename": "download_counts.json", "size": 4}
        )
        self.assertEqual(status, 200)
        async with self.session.put(
            self.base + f"/api/upload/chunk/{done['upload_id']}?offset=0", data=b"data"
        ) as response:
            self.assertEqual(response.status, 200)
        status, result = await self.post_json(f"/api/upload/complete/{done['upload_id']}", {})
        self.assertEqual(status, 200)
        self.assertNotEqual(result["name"].lower(), "download_counts.json")

    async def test_single_shot_upload_sanitizes_traversal(self):
        outside = self.data_dir.parent / "evil_outside.txt"
        outside.unlink(missing_ok=True)
        response = await self.raw_request(self.multipart_request("../../evil_outside.txt", b"EVIL"))
        self.assertIn(b"200 OK", self.status_line(response))
        body = json_body(response)
        self.assertEqual(body["filename"], "evil_outside.txt")
        self.assertTrue((self.uploads / "evil_outside.txt").is_file())
        self.assertFalse(outside.exists())

    async def test_single_shot_upload_cannot_overwrite_web_client(self):
        response = await self.raw_request(self.multipart_request("../client/app.js", b"/*pwned*/"))
        self.assertIn(b"200 OK", self.status_line(response))
        self.assertTrue((self.uploads / "app.js").is_file())
        self.assertNotEqual(
            (self.config.client_dir / "app.js").read_text(encoding="utf-8"), "/*pwned*/"
        )

    async def test_aborted_stream_cleans_partial_file(self):
        class FailingField:
            filename = "aborted.bin"

            def __init__(self):
                self.calls = 0

            async def read_chunk(self, size):
                self.calls += 1
                if self.calls == 1:
                    return b"x" * 1024
                raise ConnectionResetError("client gone")

        with self.assertRaises(ConnectionResetError):
            await self.server.files.save_stream(FailingField())
        self.assertFalse((self.uploads / "aborted.bin").exists())
        self.assertEqual(list((self.data_dir / "state" / "tmp").glob("*.part")), [])

    async def test_abort_removes_session_files(self):
        _, init = await self.post_json("/api/upload/init", {"filename": "cancel.bin", "size": 10})
        upload_id = init["upload_id"]
        async with self.session.put(
            self.base + f"/api/upload/chunk/{upload_id}?offset=0", data=b"12345"
        ) as response:
            self.assertEqual(response.status, 200)
        async with self.session.delete(self.base + f"/api/upload/{upload_id}") as response:
            self.assertEqual(response.status, 200)
        part = self.data_dir / "state" / "tmp" / f"{upload_id}.part"
        self.assertFalse(part.exists())
        self.assertFalse((self.data_dir / "state" / "uploads" / f"{upload_id}.json").exists())


class DownloadTests(ServerTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.done = await self.upload_chunked("hello.txt", b"hello world")

    async def test_count_only_on_full_get(self):
        url = self.done["url"]
        async with self.session.get(self.base + url) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.read(), b"hello world")
        async with self.session.head(self.base + url) as response:
            self.assertEqual(response.status, 200)
        async with self.session.get(self.base + url, headers={"Range": "bytes=0-3"}) as response:
            self.assertEqual(response.status, 206)
            await response.read()
        _status, files = await self.get_json("/api/files")
        entry = next(item for item in files["files"] if item["name"] == "hello.txt")
        self.assertEqual(entry["download_count"], 1)

        async with self.session.get(self.base + url) as response:
            await response.read()
        _status, files = await self.get_json("/api/files")
        entry = next(item for item in files["files"] if item["name"] == "hello.txt")
        self.assertEqual(entry["download_count"], 2)

    async def test_content_disposition_is_rfc5987(self):
        done = await self.upload_chunked("中文 文件 #1.txt", b"cn")
        encoded = quote(done["name"])
        async with self.session.get(self.base + "/api/download/" + encoded) as response:
            self.assertEqual(response.status, 200)
            header = response.headers["Content-Disposition"]
            self.assertIn("filename*=UTF-8''", header)
            self.assertIn("%E4%B8%AD%E6%96%87", header)
            self.assertEqual(await response.read(), b"cn")
        _status, files = await self.get_json("/api/files")
        entry = next(item for item in files["files"] if item["name"] == done["name"])
        self.assertIn("%23", entry["url"])
        async with self.session.get(self.base + entry["url"]) as response:
            self.assertEqual(response.status, 200)

    async def test_head_and_range_headers(self):
        payload = b"0123456789" * 10
        done = await self.upload_chunked("range.bin", payload)
        async with self.session.head(self.base + done["url"]) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Length"], str(len(payload)))
            self.assertEqual(response.headers["Accept-Ranges"], "bytes")
        async with self.session.get(
            self.base + done["url"], headers={"Range": "bytes=10-19"}
        ) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], f"bytes 10-19/{len(payload)}")
            self.assertEqual(await response.read(), payload[10:20])
        async with self.session.get(
            self.base + done["url"], headers={"Range": "bytes=999-"}
        ) as response:
            self.assertEqual(response.status, 416)
            self.assertEqual(response.headers["Content-Range"], f"bytes */{len(payload)}")

    async def test_missing_file_404(self):
        async with self.session.get(self.base + "/api/download/nope.bin") as response:
            self.assertEqual(response.status, 404)

    async def test_delete_busy_file_returns_409(self):
        with mock.patch.object(Path, "unlink", side_effect=PermissionError(32, "in use")):
            status, body = await self.delete_json("/api/delete/hello.txt")
        self.assertEqual(status, 409, body)
        self.assertTrue((self.uploads / "hello.txt").exists())

    async def test_delete_missing_404(self):
        status, _ = await self.delete_json("/api/delete/nope.bin")
        self.assertEqual(status, 404)


class ZipTests(ServerTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.upload_chunked("hello.txt", b"hello " * 100)
        await self.upload_chunked("中文 #1.txt", "世界".encode() * 50)

    async def test_json_zip_is_valid(self):
        async with self.session.post(
            self.base + "/api/zip-download",
            json={"files": ["hello.txt", "中文 #1.txt"]},
        ) as response:
            self.assertEqual(response.status, 200)
            data = await response.read()
            self.assertIn("attachment", response.headers["Content-Disposition"])
        archive = zipfile.ZipFile(io.BytesIO(data))
        self.assertIsNone(archive.testzip())
        self.assertEqual(sorted(archive.namelist()), sorted(["hello.txt", "中文 #1.txt"]))
        self.assertEqual(archive.read("hello.txt"), b"hello " * 100)

    async def test_form_zip_for_native_browser_download(self):
        async with self.session.post(
            self.base + "/api/zip-download", data={"files": ["hello.txt"]}
        ) as response:
            self.assertEqual(response.status, 200)
            data = await response.read()
        self.assertEqual(zipfile.ZipFile(io.BytesIO(data)).namelist(), ["hello.txt"])

    async def test_zip_requires_existing_files(self):
        async with self.session.post(
            self.base + "/api/zip-download", json={"files": ["missing.bin"]}
        ) as response:
            self.assertEqual(response.status, 400)
            self.assertIn("error", await response.json())

    async def test_zip64_archive_roundtrip(self):
        payload = b"Z" * 4096
        await self.upload_chunked("zip64.bin", payload)
        with mock.patch.object(zipfile, "ZIP64_LIMIT", 512):
            async with self.session.post(
                self.base + "/api/zip-download", json={"files": ["zip64.bin"]}
            ) as response:
                self.assertEqual(response.status, 200)
                data = await response.read()
            archive = zipfile.ZipFile(io.BytesIO(data), allowZip64=True)
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("zip64.bin"), payload)


class ServerBehaviourTests(ServerTestCase):
    async def test_room_info_and_version(self):
        status, data = await self.get_json("/api/room-info")
        self.assertEqual(status, 200)
        self.assertEqual(data["version"], __version__)
        self.assertIn("qr_code", data)
        self.assertTrue(data["qr_code"].startswith("data:image/png;base64,"))
        self.assertIs(data["local_client"], True)

    async def test_index_and_security_headers(self):
        async with self.session.get(self.base + "/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("局域网文件快速传输工具", await response.text())
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
            self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
            self.assertIn("frame-ancestors 'self'", response.headers["Content-Security-Policy"])

    async def test_api_responses_are_not_cached(self):
        async with self.session.get(self.base + "/api/files") as response:
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_reserved_files_are_hidden_and_rejected(self):
        (self.uploads / "download_counts.json").write_text("{}", encoding="utf-8")
        (self.uploads / "x.part").write_bytes(b"partial")
        _status, data = await self.get_json("/api/files")
        names = [item["name"] for item in data["files"]]
        self.assertNotIn("download_counts.json", names)
        self.assertNotIn("x.part", names)
        async with self.session.get(self.base + "/api/download/download_counts.json") as response:
            self.assertEqual(response.status, 400)
        async with self.session.delete(self.base + "/api/delete/download_counts.json") as response:
            self.assertEqual(response.status, 400)

    async def test_local_copy_endpoint_is_removed(self):
        async with self.session.post(
            self.base + "/api/local-copy", json={"file_path": "C:/Windows/win.ini"}
        ) as response:
            self.assertEqual(response.status, 404)

    async def test_chat_send_normalises_newlines_and_limits_length(self):
        status, data = await self.post_json("/api/chat/send", {"message": "line1\nline2\r\nline3"})
        self.assertEqual(status, 200)
        self.assertEqual(data["message"]["message"], "line1 line2  line3")
        status, _ = await self.post_json("/api/chat/send", {"message": "x" * 501})
        self.assertEqual(status, 400)
        status, history = await self.get_json("/api/chat/history")
        self.assertEqual(len(history["messages"]), 1)

    async def test_room_info_contains_online_users_and_scope(self):
        status, data = await self.get_json("/api/room-info")
        self.assertEqual(status, 200)
        self.assertIn("online_users", data)
        self.assertEqual(data["ip_scope"]["scope"], "all")
        self.assertEqual(data["ip_scope"]["mask"], 0b1111)
        self.assertEqual(data["ip_scope"]["segments"], [True, True, True, True])
        self.assertEqual(data["client_name"], "用户1")
        _status, profile = await self.get_json("/api/profile")
        self.assertEqual(profile["ip"], "127.0.0.1")
        self.assertEqual(profile["name"], "用户1")

    async def test_network_scope_hot_update(self):
        async with self.session.post(
            self.base + "/api/network-scope", json={"scope": "last2"}
        ) as response:
            self.assertEqual(response.status, 200)
            data = await response.json()
        self.assertEqual(data["scope"], "last2")
        self.assertEqual(data["segments"], [False, False, True, True])
        _status, room = await self.get_json("/api/room-info")
        self.assertEqual(room["ip_scope"]["scope"], "last2")
        self.assertEqual(room["ip_scope"]["mask"], 0b1100)
        async with self.session.post(
            self.base + "/api/network-scope", json={"scope": "mask:5"}
        ) as response:
            self.assertEqual(response.status, 400)

    async def test_rename_profile_refreshes_chat_author(self):
        _status, created = await self.post_json("/api/chat/send", {"message": "旧名字"})
        old_id = created["message"]["id"]
        async with self.session.post(
            self.base + "/api/profile/name", json={"name": "会议室平板"}
        ) as response:
            self.assertEqual(response.status, 200)
            profile = await response.json()
        self.assertEqual(profile["name"], "会议室平板")
        _status, history = await self.get_json("/api/chat/history")
        message = next(item for item in history["messages"] if item["id"] == old_id)
        self.assertEqual(message["client_name"], "会议室平板")
        _status, room = await self.get_json("/api/room-info")
        self.assertEqual(room["client_name"], "会议室平板")

    async def test_edit_and_batch_delete_chat_messages(self):
        _status, first = await self.post_json("/api/chat/send", {"message": "第一条"})
        _status, second = await self.post_json("/api/chat/send", {"message": "第二条"})
        message_id = first["message"]["id"]
        async with self.session.put(
            self.base + f"/api/chat/message/{message_id}", json={"message": "已编辑"}
        ) as response:
            self.assertEqual(response.status, 200)
            edited = (await response.json())["message"]
        self.assertEqual(edited["message"], "已编辑")
        _status, history = await self.get_json("/api/chat/history")
        self.assertEqual(history["messages"][0]["message"], "已编辑")
        async with self.session.post(
            self.base + "/api/chat/messages/delete",
            json={"ids": [message_id, second["message"]["id"]]},
        ) as response:
            self.assertEqual(response.status, 200)
            deleted = (await response.json())["deleted"]
        self.assertEqual(len(deleted), 2)
        _status, history = await self.get_json("/api/chat/history")
        self.assertEqual(history["messages"], [])

    async def test_online_users_shows_upload_activity(self):
        payload = b"x" * 16
        _status, init = await self.post_json(
            "/api/upload/init", {"filename": "active.bin", "size": len(payload)}
        )
        self.assertIn("upload_id", init)
        _status, room = await self.get_json("/api/room-info")
        user = next(item for item in room["online_users"] if item["ip"] == "127.0.0.1")
        self.assertEqual(user["status"], "上传")
        self.assertEqual(user["detail"], "active.bin")
        async with self.session.delete(self.base + f"/api/upload/{init['upload_id']}") as response:
            self.assertEqual(response.status, 200)

    async def test_websocket_chat_and_delete_broadcast(self):
        async with self.session.ws_connect(
            self.base + "/ws", headers={"Origin": self.base}
        ) as first:
            welcome = await first.receive_json()
            self.assertEqual(welcome["type"], "welcome")
            async with self.session.ws_connect(
                self.base + "/ws", headers={"Origin": self.base}
            ) as second:
                await second.receive_json()
                await first.send_json({"type": "chat_message", "message": "hello ws"})
                for socket in (first, second):
                    event = await socket.receive_json()
                    self.assertEqual(event["type"], "chat_message")
                    message_id = event["message"]["id"]
                status, _ = await self.delete_json(f"/api/chat/message/{message_id}")
                self.assertEqual(status, 200)
                for socket in (first, second):
                    event = await socket.receive_json()
                    self.assertEqual(event["type"], "delete_message")
                    self.assertEqual(event["message_id"], message_id)


if __name__ == "__main__":
    unittest.main()
