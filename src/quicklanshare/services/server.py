"""HTTP/WebSocket server for QuickLanShare."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import ssl
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web

from ..core.version import __author__, __copyright_ym__, __version__
from ..utils.net import collect_local_hosts, get_local_ip, open_browser
from ..utils.qr import qr_data_uri
from .access import (
    SCOPES,
    is_ip_allowed,
    is_loopback,
    normalize_ipv4,
    normalize_scope,
    scope_label,
    scope_mask,
    scope_segments,
)
from .chat import ChatStore, EmptyMessage, MessageTooLong
from .config import APP_NAME, Config
from .filenames import (
    InvalidFilename,
    quote_url_name,
    resolve_upload_path,
)
from .filestream import stream_download
from .storage import (
    FileBusy,
    FileStore,
    UploadConflict,
    UploadNotFound,
    UploadTooLarge,
)
from .zipstream import StreamingZip, compression_code

logger = logging.getLogger("quicklanshare.server")


class FileTransferServer:
    def __init__(self, config: Config):
        self.config = config
        self.config.ensure_dirs()
        if not self.config.allow_any_host:
            self.config.allowed_hosts |= collect_local_hosts()
        self.config.allowed_hosts = {h.lower().rstrip(".") for h in self.config.allowed_hosts}
        self.files = FileStore(self.config)
        self.chat = ChatStore(self.config)
        self.clients: dict[str, dict[str, Any]] = {}
        self.ip_to_name: dict[str, str] = {}
        self._names_file = self.config.state_dir / "names.json"
        with contextlib.suppress(OSError):
            self._names_file.parent.mkdir(parents=True, exist_ok=True)
        self.ip_to_name = self._load_names()
        self.user_counter = 1
        self._upload_state: dict[str, dict[str, Any]] = {}
        self._download_active: dict[str, int] = {}
        self._activity: dict[str, dict[str, int]] = {}
        self.port = config.port
        self.local_ip = get_local_ip()
        self.scheme = "https" if config.ssl_cert and config.ssl_key else "http"
        self.started_at = time.time()
        self.active_downloads = 0
        self.shutdown_enabled = False
        self.shutdown_start_time: float | None = None
        self.shutdown_deadline: float | None = None
        self.stop_reason = ""
        self._shutdown_task: asyncio.Task[None] | None = None
        self._manual_shutdown_task: asyncio.Task[None] | None = None
        self._qr_cache: dict[str, str] = {}
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._stop_event = asyncio.Event()
        self._closed = False
        self.app = self._build_app()
        logger.info("初始化完成: 数据目录=%s 端口=%s", self.config.data_dir, config.port)

    # ------------------------------------------------------------- app setup
    def _build_app(self) -> web.Application:
        max_body = max(32 * 1024 * 1024, self.config.max_chunk_size + 1024 * 1024)
        app = web.Application(
            middlewares=[self._error_middleware, self._security_middleware],
            client_max_size=max_body,
        )
        app.on_response_prepare.append(self._on_prepare)
        router = app.router
        router.add_static(
            "/client/", path=str(self.config.client_dir), name="client", follow_symlinks=False
        )
        router.add_get("/", self.handle_index)
        router.add_get("/index.html", self.handle_index)
        router.add_get("/favicon.ico", self.handle_favicon)
        router.add_get("/api/room-info", self.handle_room_info)
        router.add_get("/api/network-scope", self.handle_network_scope_state)
        router.add_post("/api/network-scope", self.handle_update_network_scope)
        router.add_get("/api/profile", self.handle_profile)
        router.add_post("/api/profile/name", self.handle_rename_profile)
        router.add_get("/api/files", self.handle_list_files)
        router.add_post("/api/upload", self.handle_upload)
        router.add_post("/api/upload/init", self.handle_upload_init)
        router.add_put("/api/upload/chunk/{upload_id}", self.handle_upload_chunk)
        router.add_post("/api/upload/complete/{upload_id}", self.handle_upload_complete)
        router.add_delete("/api/upload/{upload_id}", self.handle_upload_abort)
        router.add_get("/api/download/{file_id}", self.handle_download)
        router.add_delete("/api/delete/{file_id}", self.handle_delete)
        router.add_post("/api/batch-delete", self.handle_batch_delete)
        router.add_post("/api/zip-download", self.handle_zip_download)
        router.add_get("/api/chat/history", self.handle_chat_history)
        router.add_post("/api/chat/send", self.handle_chat_send)
        router.add_put("/api/chat/message/{msg_id}", self.handle_edit_chat_message)
        router.add_delete("/api/chat/message/{msg_id}", self.handle_delete_chat_message)
        router.add_post("/api/chat/messages/delete", self.handle_delete_chat_messages)
        router.add_get("/ws", self.handle_websocket)
        router.add_post("/api/auto-shutdown/extend", self.handle_extend_auto_shutdown)
        router.add_get("/api/auto-shutdown/status", self.handle_auto_shutdown_status)
        router.add_post("/api/shutdown", self.handle_shutdown)
        return app

    # -------------------------------------------------------------- middleware
    @web.middleware
    async def _error_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        try:
            return await handler(request)
        except web.HTTPException as exc:
            if exc.status < 400 or not request.path.startswith("/api/"):
                raise
            message = exc.text if exc.text and "<" not in exc.text else (exc.reason or "请求失败")
            return web.json_response({"error": message}, status=exc.status)
        except UploadTooLarge as exc:
            return self._error(str(exc), 413)
        except UploadConflict as exc:
            return web.json_response({"error": str(exc), "offset": exc.offset}, status=409)
        except UploadNotFound:
            return self._error("上传会话不存在或已过期", 404)
        except FileBusy as exc:
            return self._error(str(exc), 409)
        except InvalidFilename as exc:
            return self._error(str(exc), 400)
        except (EmptyMessage, MessageTooLong) as exc:
            return self._error(str(exc), 400)
        except FileNotFoundError:
            return self._error("文件不存在", 404)
        except (json.JSONDecodeError, ValueError) as exc:
            if request.path.startswith("/api/"):
                return self._error(f"请求无效: {exc}", 400)
            raise
        except Exception:
            logger.exception("处理请求失败: %s %s", request.method, request.path)
            return self._error("服务器内部错误", 500)

    @web.middleware
    async def _security_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        self._check_host(request)
        self._check_ip_scope(request)
        if request.method not in ("GET", "HEAD", "OPTIONS") or request.path == "/ws":
            self._check_origin(request)
        return await handler(request)

    async def _on_prepare(self, request: web.Request, response: web.StreamResponse) -> None:
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        # Same-origin (not no-referrer): Chrome sends Origin: null for form
        # POSTs from documents using no-referrer, which breaks the ZIP iframe.
        headers.setdefault("Referrer-Policy", "same-origin")
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' ws: wss:; font-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
        )
        if request.path.startswith("/api/"):
            headers.setdefault("Cache-Control", "no-store")
        if request.secure:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000")

    def _error(self, message: str, status: int) -> web.Response:
        return web.json_response({"error": message}, status=status)

    def _is_local_client(self, request: web.Request) -> bool:
        return is_loopback(request.remote)

    def _check_ip_scope(self, request: web.Request) -> None:
        # 不能信任 Host 头决定放通范围：远端可伪造 127.0.0.1。请求来自本机
        # 回环页面时，仍按真实局域网地址作为锚点。
        host_ip = normalize_ipv4(request.url.host)
        anchor = host_ip if host_ip and not is_loopback(host_ip) else self.local_ip
        if is_ip_allowed(anchor, request.remote, self.config.ip_scope):
            return
        logger.warning(
            "拒绝不在放通范围的 IP: %s（本机 %s，范围 %s）",
            request.remote,
            anchor,
            self.config.ip_scope,
        )
        raise web.HTTPForbidden(text="IP not allowed")

    def _require_local_client(self, request: web.Request) -> None:
        if not self._is_local_client(request):
            logger.warning("拒绝非本机控制请求: %s %s", request.path, request.remote)
            raise web.HTTPForbidden(text="Only local client can control shutdown")

    def _check_host(self, request: web.Request) -> None:
        if self.config.allow_any_host:
            return
        try:
            host = (request.url.host or "").lower().rstrip(".")
        except ValueError as exc:
            raise web.HTTPBadRequest(text="Invalid Host header") from exc
        if not host or host in self.config.allowed_hosts or host.startswith("127."):
            return
        logger.warning("拒绝未知 Host: %s (%s)", host, request.remote)
        raise web.HTTPForbidden(text="Host not allowed")

    def _check_origin(self, request: web.Request) -> None:
        site = request.headers.get("Sec-Fetch-Site")
        if site and site not in ("same-origin", "none"):
            raise web.HTTPForbidden(text="Cross-site request blocked")
        origin = request.headers.get("Origin")
        target = origin or request.headers.get("Referer")
        if origin and origin.lower() == "null":
            # Some browsers submit a form POST into a named iframe with an
            # opaque Origin.  ZIP export is read-only and the cross-site
            # Sec-Fetch-Site check above already ran, so allow that one path.
            if request.method == "POST" and request.path == "/api/zip-download":
                return
            raise web.HTTPForbidden(text="Origin not allowed")
        if not target:
            return
        parsed = urlsplit(target)
        if parsed.scheme not in ("http", "https"):
            raise web.HTTPForbidden(text="Origin not allowed")
        if (parsed.netloc or "").lower() != (request.host or "").lower():
            logger.warning("拒绝跨站请求: Origin=%s Host=%s", target, request.host)
            raise web.HTTPForbidden(text="Cross-origin request blocked")

    # ------------------------------------------------------------- utilities
    @staticmethod
    def _display_ip(ip: str | None) -> str:
        """统一回环 / IPv4-mapped 地址的展示形式。"""
        return normalize_ipv4(ip) or str(ip or "unknown")

    def _load_names(self) -> dict[str, str]:
        try:
            raw = json.loads(self._names_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        names: dict[str, str] = {}
        for key, value in raw.items():
            name = self._sanitize_name(value)
            if name:
                names[self._display_ip(str(key))] = name
        return names

    def _save_names(self) -> None:
        try:
            tmp = self._names_file.with_name(self._names_file.name + ".tmp")
            tmp.write_text(
                json.dumps(self.ip_to_name, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self._names_file)
        except OSError:
            logger.warning("保存用户名失败: %s", self._names_file, exc_info=True)

    @staticmethod
    def _sanitize_name(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        text = " ".join(value.replace("\r", " ").replace("\n", " ").split())
        return text.strip()[:20]

    def _name_for_ip(self, ip: str) -> str:
        if not ip:
            return "未知用户"
        key = self._display_ip(ip)
        if key not in self.ip_to_name:
            used = {
                int(name[2:])
                for name in self.ip_to_name.values()
                if name.startswith("用户") and name[2:].isdigit()
            }
            number = 1
            while number in used:
                number += 1
            self.user_counter = max(self.user_counter, number + 1)
            self.ip_to_name[key] = f"用户{number}"
            self._save_names()
            logger.info("用户命名: %s -> %s", key, self.ip_to_name[key])
        return self.ip_to_name[key]

    def _decorate(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for message in messages:
            ip = message.get("client_ip", "")
            if ip:
                message["client_name"] = self._name_for_ip(str(ip))
            elif not message.get("client_name"):
                message["client_name"] = "未知用户"
        return messages

    def _rename_client(self, ip: str, name: str) -> str:
        key = self._display_ip(ip)
        cleaned = self._sanitize_name(name)
        if not cleaned:
            raise ValueError("用户名不能为空")
        self.ip_to_name[key] = cleaned
        for client in self.clients.values():
            if self._display_ip(str(client.get("ip") or "")) == key:
                client["name"] = cleaned
        self._save_names()
        logger.info("用户改名: %s -> %s", key, cleaned)
        return cleaned

    def _client_profile(self, request: web.Request) -> dict[str, Any]:
        ip = self._display_ip(request.remote)
        return {"ip": ip, "name": self._name_for_ip(request.remote or "")}

    @staticmethod
    def _same_ip(left: str | None, right: str | None) -> bool:
        return normalize_ipv4(left) == normalize_ipv4(right)

    def _activity_enter(self, ip: str, kind: str) -> None:
        key = self._display_ip(ip)
        counters = self._activity.setdefault(key, {})
        counters[kind] = counters.get(kind, 0) + 1

    def _activity_leave(self, ip: str, kind: str) -> None:
        key = self._display_ip(ip)
        counters = self._activity.get(key)
        if not counters:
            return
        value = max(0, counters.get(kind, 0) - 1)
        if value:
            counters[kind] = value
        else:
            counters.pop(kind, None)
        if not counters:
            self._activity.pop(key, None)

    def _track_upload(self, upload_id: str, ip: str, name: str, size: int, offset: int) -> None:
        self._upload_state[upload_id] = {
            "ip": self._display_ip(ip),
            "name": name,
            "size": int(size),
            "offset": max(0, int(offset)),
            "updated": time.time(),
        }

    def _update_upload(self, upload_id: str, offset: int) -> None:
        session = self._upload_state.get(upload_id)
        if session is None:
            return
        session["offset"] = max(0, int(offset))
        session["updated"] = time.time()

    def _finish_upload(self, upload_id: str) -> None:
        self._upload_state.pop(upload_id, None)

    def _online_users(self) -> list[dict[str, Any]]:
        """合并 WebSocket、上传会话与下载请求，给界面展示在线用户。"""
        now = time.time()
        names: dict[str, str] = {}
        for client in self.clients.values():
            ip = self._display_ip(str(client.get("ip") or ""))
            name = str(client.get("name") or self.ip_to_name.get(ip) or "")
            names.setdefault(ip, name)
        uploads: dict[str, str] = {}
        for upload_id, session in list(self._upload_state.items()):
            if now - float(session.get("updated") or 0) > 60:
                self._upload_state.pop(upload_id, None)
                continue
            ip = str(session.get("ip") or "")
            name = str(session.get("name") or "")
            if ip and len(name) <= 60:
                uploads[ip] = name
        downloads = set(self._activity)
        for ip in downloads | set(uploads) | set(names):
            names.setdefault(ip, self.ip_to_name.get(ip, "访客"))

        users: list[dict[str, Any]] = []
        for ip, name in names.items():
            if ip in self._download_active or self._activity.get(ip, {}).get("download"):
                status = "下载"
            elif ip in uploads or self._activity.get(ip, {}).get("upload"):
                status = "上传"
            else:
                status = "在线"
            detail = ""
            if status == "上传":
                detail = uploads.get(ip, "")
            elif status == "下载":
                detail = "正在下载文件"
            users.append(
                {
                    "ip": ip,
                    "name": name,
                    "status": status,
                    "detail": detail,
                    "local": is_loopback(ip),
                }
            )
        users.sort(key=lambda item: (not item["local"], item["ip"]))
        return users

    def _scope_payload(self) -> dict[str, Any]:
        scope = normalize_scope(self.config.ip_scope)
        mask = scope_mask(scope)
        return {
            "scope": scope,
            "mask": mask,
            "segments": scope_segments(scope),
            "server_ip": self.local_ip,
            "label": scope_label(scope),
        }

    def _public_file(self, entry: dict[str, Any]) -> dict[str, Any]:
        data = dict(entry)
        name = entry.get("name") or entry.get("filename") or ""
        data["id"] = name
        data["name"] = name
        data["url"] = f"/api/download/{quote_url_name(name)}"
        return data

    async def _read_json(self, request: web.Request) -> dict[str, Any]:
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="Content-Type 必须为 application/json")
        raw = await request.read()
        if len(raw) > self.config.max_json_size:
            raise web.HTTPRequestEntityTooLarge(
                max_size=self.config.max_json_size, actual_size=len(raw)
            )
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise web.HTTPBadRequest(text="JSON 格式错误") from exc
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text="JSON 对象无效")
        return data

    def _remaining_shutdown(self) -> int:
        if not self.shutdown_enabled or not self.shutdown_deadline:
            return 0
        return max(0, int(self.shutdown_deadline - time.time()))

    # ---------------------------------------------------------------- static
    async def handle_index(self, request: web.Request) -> web.StreamResponse:
        index_path = self.config.client_dir / "index.html"
        if not index_path.exists():
            return web.Response(text="Index not found", status=404)
        return web.FileResponse(index_path, headers={"Cache-Control": "no-cache"})

    async def handle_favicon(self, request: web.Request) -> web.StreamResponse:
        icon = self.config.client_dir / "app.ico"
        if icon.exists():
            return web.FileResponse(icon)
        raise web.HTTPNotFound()

    # ------------------------------------------------------------- room/files
    async def handle_room_info(self, request: web.Request) -> web.Response:
        room_url = f"{self.scheme}://{self.local_ip}:{self.port}"
        qr = self._qr_cache.get(room_url)
        if qr is None:
            qr = qr_data_uri(room_url)
            self._qr_cache[room_url] = qr
            if len(self._qr_cache) > 8:
                self._qr_cache.clear()
                self._qr_cache[room_url] = qr
        files = [self._public_file(entry) for entry in self.files.list_files()]
        online_users = self._online_users()
        profile = self._client_profile(request)
        return web.json_response(
            {
                "room_url": room_url,
                "qr_code": qr,
                "total_files": len(files),
                "total_size": sum(item["size"] for item in files),
                "total_clients": len(self.clients),
                "online_users": online_users,
                "chat_messages": self.chat.total(),
                "files": files,
                "server_ip": self.local_ip,
                "ip_scope": self._scope_payload(),
                "client_ip": profile["ip"],
                "client_name": profile["name"],
                "version": __version__,
                "author": __author__,
                "copyright": f"Copyright © {__author__} {__copyright_ym__}",
                "uptime": int(time.time() - self.started_at),
                "active_downloads": self.active_downloads,
                "local_client": self._is_local_client(request),
            }
        )

    async def handle_network_scope_state(self, request: web.Request) -> web.Response:
        payload = self._scope_payload()
        payload["local_client"] = self._is_local_client(request)
        return web.json_response(payload)

    async def handle_update_network_scope(self, request: web.Request) -> web.Response:
        self._require_local_client(request)
        data = await self._read_json(request)
        scope = data.get("scope")
        if scope not in SCOPES:
            raise web.HTTPBadRequest(text="网段参数不合法，仅支持四档预设")
        self.config.ip_scope = normalize_scope(str(scope))
        payload = self._scope_payload()
        logger.info("开放网段已热更新: %s (%s)", payload["label"], scope)
        await self._broadcast(
            {
                "type": "ip_scope_changed",
                "scope": payload["scope"],
                "mask": payload["mask"],
                "segments": payload["segments"],
                "label": payload["label"],
            }
        )
        await self._disconnect_disallowed_clients()
        payload["local_client"] = True
        payload["saved"] = True
        return web.json_response(payload)

    async def _disconnect_disallowed_clients(self) -> None:
        """范围收紧后，立即断开已经不在范围内的长连接。"""
        for client_id, client in list(self.clients.items()):
            ip = str(client.get("ip") or "")
            if is_ip_allowed(self.local_ip, ip, self.config.ip_scope):
                continue
            logger.info("网段收紧，断开不在范围的连接: %s (%s)", client_id, ip)
            self.clients.pop(client_id, None)
            with contextlib.suppress(Exception):
                await client["ws"].close(code=1008, message=b"IP no longer allowed")

    async def handle_profile(self, request: web.Request) -> web.Response:
        return web.json_response(self._client_profile(request))

    async def handle_rename_profile(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        try:
            name = self._rename_client(request.remote or "", data.get("name", ""))
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        profile = {"ip": self._display_ip(request.remote), "name": name}
        await self._broadcast({"type": "profile_updated", **profile})
        return web.json_response({"success": True, **profile})

    async def handle_list_files(self, request: web.Request) -> web.Response:
        files = [self._public_file(entry) for entry in self.files.list_files()]
        return web.json_response({"files": files})

    # ---------------------------------------------------------------- upload
    async def handle_upload(self, request: web.Request) -> web.Response:
        if request.content_type != "multipart/form-data":
            raise web.HTTPUnsupportedMediaType(text="需要 multipart/form-data")
        reader = await request.multipart()
        field = await reader.next()
        if (
            field is None
            or getattr(field, "name", None) != "file"
            or not getattr(field, "filename", None)
        ):
            raise web.HTTPBadRequest(text="缺少文件字段")
        remote = request.remote or ""
        self._activity_enter(remote, "upload")
        try:
            info = await self.files.save_stream(field)
        finally:
            self._activity_leave(remote, "upload")
        return web.json_response({"success": True, **self._public_file(info)})

    async def handle_upload_init(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        filename = data.get("filename")
        size = data.get("size")
        mtime = data.get("mtime", 0)
        if isinstance(size, str) and size.isdigit():
            size = int(size)
        if not isinstance(size, int) or isinstance(size, bool):
            raise web.HTTPBadRequest(text="缺少有效的 size")
        try:
            mtime_value = float(mtime or 0)
        except (TypeError, ValueError):
            mtime_value = 0.0
        result = self.files.init_upload(filename, size, mtime_value, str(data.get("nonce", "")))
        upload_id = result.get("upload_id")
        if isinstance(upload_id, str) and upload_id:
            self._track_upload(
                upload_id,
                request.remote or "",
                str(result.get("name") or filename or ""),
                size,
                int(result.get("offset") or 0),
            )
        return web.json_response(result)

    async def handle_upload_chunk(self, request: web.Request) -> web.Response:
        upload_id = request.match_info["upload_id"]
        try:
            offset = int(request.query.get("offset", "0"))
        except ValueError as exc:
            raise web.HTTPBadRequest(text="offset 必须是整数") from exc
        declared = request.content_length
        if declared is not None and declared > self.config.max_chunk_size:
            raise UploadTooLarge("单个分片过大")
        data = await request.read()
        if len(data) > self.config.max_chunk_size:
            raise UploadTooLarge("单个分片过大")
        new_offset = await self.files.append_chunk(upload_id, offset, data)
        self._update_upload(upload_id, new_offset)
        return web.json_response({"upload_id": upload_id, "offset": new_offset})

    async def handle_upload_complete(self, request: web.Request) -> web.Response:
        upload_id = request.match_info["upload_id"]
        info = await self.files.complete_upload(upload_id)
        self._finish_upload(upload_id)
        return web.json_response({"success": True, **self._public_file(info)})

    async def handle_upload_abort(self, request: web.Request) -> web.Response:
        upload_id = request.match_info["upload_id"]
        self.files.abort_upload(upload_id)
        self._finish_upload(upload_id)
        return web.json_response({"success": True})

    # -------------------------------------------------------------- download
    async def handle_download(self, request: web.Request) -> web.StreamResponse:
        file_id = request.match_info["file_id"]
        path = self.files.get_path(file_id)
        if request.method == "GET" and not request.headers.get("Range"):
            self.files.record_download(file_id)
        logger.info(
            "下载 %s (%s) 来自 %s", file_id, self.files.counts.get(file_id, 0), request.remote
        )
        remote = self._display_ip(request.remote)
        self.active_downloads += 1
        self._download_active[remote] = self._download_active.get(remote, 0) + 1
        self._activity_enter(remote, "download")
        try:
            return await stream_download(request, path, file_id)
        finally:
            self._activity_leave(remote, "download")
            remaining = max(0, self._download_active.get(remote, 0) - 1)
            if remaining:
                self._download_active[remote] = remaining
            else:
                self._download_active.pop(remote, None)
            self.active_downloads = max(0, self.active_downloads - 1)

    async def handle_delete(self, request: web.Request) -> web.Response:
        file_id = request.match_info["file_id"]
        self.files.delete(file_id)
        logger.info("删除文件 %s 来自 %s", file_id, request.remote)
        return web.json_response({"success": True})

    async def handle_batch_delete(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        names = data.get("files")
        if not isinstance(names, list) or not names:
            raise web.HTTPBadRequest(text="files 必须是非空数组")
        if len(names) > 10000:
            raise web.HTTPBadRequest(text="单次删除文件过多")
        deleted: list[str] = []
        failed: list[dict[str, Any]] = []
        for name in names:
            if not isinstance(name, str):
                failed.append({"name": str(name), "error": "非法文件名"})
                continue
            try:
                self.files.delete(name)
                deleted.append(name)
            except FileNotFoundError:
                failed.append({"name": name, "error": "文件不存在"})
            except (InvalidFilename, FileBusy) as exc:
                failed.append({"name": name, "error": str(exc)})
        logger.info("批量删除 %d 个文件，失败 %d 个", len(deleted), len(failed))
        return web.json_response({"deleted": deleted, "failed": failed})

    async def _zip_names(self, request: web.Request) -> list[str]:
        ctype = request.content_type
        if ctype == "application/json":
            data = await self._read_json(request)
            names = data.get("files")
        elif ctype in ("application/x-www-form-urlencoded", "multipart/form-data"):
            posted = await request.post()
            names = posted.getall("files", [])
        else:
            raise web.HTTPUnsupportedMediaType(text="需要 JSON 或表单数据")
        if not isinstance(names, list) or not names:
            raise web.HTTPBadRequest(text="请至少选择一个文件")
        if len(names) > 10000:
            raise web.HTTPBadRequest(text="单次打包文件过多")
        return [name for name in names if isinstance(name, str)]

    async def handle_zip_download(self, request: web.Request) -> web.StreamResponse:
        names = await self._zip_names(request)
        entries: list[tuple[Path, str]] = []
        total_size = 0
        for name in names:
            try:
                path = resolve_upload_path(self.config.upload_dir, name)
            except InvalidFilename:
                continue
            if not path.is_file():
                continue
            entries.append((path, path.name))
            total_size += path.stat().st_size
        if not entries:
            raise web.HTTPBadRequest(text="所选文件不存在")
        if total_size > self.config.zip_size_limit:
            raise web.HTTPRequestEntityTooLarge(
                max_size=self.config.zip_size_limit, actual_size=total_size
            )
        zip_name = f"QuickLanShare_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        logger.info("打包下载 %d 个文件 (%s) 来自 %s", len(entries), total_size, request.remote)
        stream = StreamingZip(
            entries, zip_name, compression=compression_code(self.config.zip_compression)
        )
        remote = self._display_ip(request.remote)
        self.active_downloads += 1
        self._download_active[remote] = self._download_active.get(remote, 0) + 1
        self._activity_enter(remote, "download")
        try:
            return await stream.stream(request)
        finally:
            self._activity_leave(remote, "download")
            remaining = max(0, self._download_active.get(remote, 0) - 1)
            if remaining:
                self._download_active[remote] = remaining
            else:
                self._download_active.pop(remote, None)
            self.active_downloads = max(0, self.active_downloads - 1)

    # ------------------------------------------------------------------ chat
    async def handle_chat_history(self, request: web.Request) -> web.Response:
        return web.json_response({"messages": self._decorate(self.chat.history(50))})

    async def handle_chat_send(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        remote = request.remote or "unknown"
        ip = self._display_ip(remote)
        message = await self.chat.add(self._name_for_ip(remote), ip, data.get("message", ""))
        await self._broadcast({"type": "chat_message", "message": message})
        return web.json_response({"success": True, "message": message})

    async def handle_edit_chat_message(self, request: web.Request) -> web.Response:
        message_id = request.match_info["msg_id"]
        existing = self.chat.get(message_id)
        if existing is None:
            raise web.HTTPNotFound(text="消息不存在")
        if not self._is_local_client(request) and not self._same_ip(
            existing.get("client_ip"), request.remote
        ):
            raise web.HTTPForbidden(text="只能编辑自己发送的消息")
        data = await self._read_json(request)
        message = await self.chat.edit(message_id, data.get("message", ""))
        if message is None:
            raise web.HTTPNotFound(text="消息不存在")
        message["client_name"] = self._name_for_ip(str(message.get("client_ip") or ""))
        await self._broadcast({"type": "edit_message", "message": message})
        return web.json_response({"success": True, "message": message})

    async def handle_delete_chat_message(self, request: web.Request) -> web.Response:
        message_id = request.match_info["msg_id"]
        if not await self.chat.delete(message_id):
            raise web.HTTPNotFound(text="消息不存在")
        await self._broadcast({"type": "delete_message", "message_id": message_id})
        return web.json_response({"success": True})

    async def handle_delete_chat_messages(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        ids = data.get("ids")
        if not isinstance(ids, list) or not ids:
            raise web.HTTPBadRequest(text="ids 必须是非空数组")
        if len(ids) > 200:
            raise web.HTTPBadRequest(text="单次最多删除 200 条消息")
        deleted: list[str] = []
        for raw in ids:
            if not isinstance(raw, str) or not raw:
                continue
            if await self.chat.delete(raw):
                deleted.append(raw)
        if deleted:
            await self._broadcast({"type": "delete_messages", "message_ids": deleted})
        return web.json_response({"success": True, "deleted": deleted})

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        targets = list(self.clients.items())
        if not targets:
            return

        async def send(client: dict[str, Any]) -> None:
            await asyncio.wait_for(client["ws"].send_json(payload), timeout=5)

        results = await asyncio.gather(
            *(send(client) for _, client in targets),
            return_exceptions=True,
        )
        for (client_id, _), result in zip(targets, results, strict=False):
            if isinstance(result, Exception):
                self.clients.pop(client_id, None)

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30.0, max_msg_size=64 * 1024, compress=False)
        await ws.prepare(request)
        client_id = f"client_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        remote = request.remote or "unknown"
        client_ip = self._display_ip(remote)
        name = self._name_for_ip(remote)
        self.clients[client_id] = {"ws": ws, "ip": client_ip, "name": name}
        logger.info("WebSocket 连接: %s (%s)", client_id, remote)
        try:
            await ws.send_json(
                {
                    "type": "welcome",
                    "client_id": client_id,
                    "client_name": name,
                    "chat_history": self._decorate(self.chat.history(50)),
                }
            )
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    if msg.type == WSMsgType.ERROR:
                        break
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                if not isinstance(data, dict) or data.get("type") != "chat_message":
                    continue
                try:
                    chat_message = await self.chat.add(name, client_ip, data.get("message", ""))
                except (EmptyMessage, MessageTooLong) as exc:
                    await ws.send_json({"type": "error", "error": str(exc)})
                    continue
                await self._broadcast({"type": "chat_message", "message": chat_message})
        except TimeoutError:
            logger.warning("WebSocket 心跳超时: %s", client_id)
        except Exception:
            logger.exception("WebSocket 异常: %s", client_id)
        finally:
            self.clients.pop(client_id, None)
            logger.info("WebSocket 断开: %s, 在线 %d", client_id, len(self.clients))
        return ws

    # --------------------------------------------------------- auto shutdown
    def _shutdown_status(self, capped: bool = False) -> dict[str, Any]:
        return {
            "enabled": self.shutdown_enabled,
            "remain_seconds": self._remaining_shutdown(),
            "max_seconds": int(self.config.auto_shutdown_max_hours * 3600),
            "extend_seconds": int(self.config.auto_shutdown_extend_hours * 3600),
            "capped": capped,
        }

    async def handle_auto_shutdown_status(self, request: web.Request) -> web.Response:
        return web.json_response(self._shutdown_status())

    async def handle_extend_auto_shutdown(self, request: web.Request) -> web.Response:
        self._require_local_client(request)
        data = await self._read_json(request)
        hours = data.get("hours", self.config.auto_shutdown_extend_hours)
        try:
            hours = float(hours)
        except (TypeError, ValueError) as exc:
            raise web.HTTPBadRequest(text="hours 必须是数字") from exc
        if hours <= 0 or hours > self.config.auto_shutdown_max_hours:
            raise web.HTTPBadRequest(text="延长时长不合法")
        capped, added_hours = self.extend_auto_shutdown(hours)
        status = self._shutdown_status(capped)
        status["added_seconds"] = int(added_hours * 3600)
        logger.info("自动关闭延长 %.1f 小时，剩余 %d 秒", added_hours, status["remain_seconds"])
        return web.json_response(status)

    def enable_auto_shutdown(self, hours: float | None = None) -> None:
        now = time.time()
        total = float(self.config.auto_shutdown_hours if hours is None else hours)
        total = max(0.001, min(total, self.config.auto_shutdown_max_hours))
        self.shutdown_enabled = True
        self.shutdown_start_time = now
        self.shutdown_deadline = now + total * 3600
        if self._shutdown_task is None or self._shutdown_task.done():
            self._shutdown_task = asyncio.create_task(self._auto_shutdown_worker())
        logger.info("自动关闭已开启: %.1f 小时", total)

    def disable_auto_shutdown(self) -> None:
        """关闭自动关闭计时，服务将一直运行到用户手动退出。"""
        self.shutdown_enabled = False
        self.shutdown_start_time = None
        self.shutdown_deadline = None
        task = self._shutdown_task
        self._shutdown_task = None
        if task is not None and not task.done():
            task.cancel()
        logger.info("自动关闭已关闭，服务将保持运行")

    def configure_auto_shutdown(self, enabled: bool, hours: float | None = None) -> None:
        """按界面设置即时应用自动关闭策略。"""
        if enabled:
            self.enable_auto_shutdown(hours)
        else:
            self.disable_auto_shutdown()

    def shutdown_status(self) -> dict[str, Any]:
        """当前自动关闭状态，供桌面界面轮询 / 刷新。"""
        return self._shutdown_status()

    def share_url(self, host: str | None = None) -> str:
        """局域网访问地址。"""
        return f"{self.scheme}://{host or self.local_ip}:{self.port}"

    def extend_auto_shutdown(self, hours: float | None = None) -> tuple[bool, float]:
        now = time.time()
        hours = float(self.config.auto_shutdown_extend_hours if hours is None else hours)
        if self.shutdown_start_time is None:
            self.shutdown_start_time = now
        if self.shutdown_deadline is None or self.shutdown_deadline < now:
            self.shutdown_deadline = now
        max_deadline = self.shutdown_start_time + self.config.auto_shutdown_max_hours * 3600
        requested = self.shutdown_deadline + hours * 3600
        new_deadline = min(requested, max_deadline)
        added_hours = max(0.0, (new_deadline - self.shutdown_deadline) / 3600)
        capped = added_hours < hours - 0.001
        self.shutdown_deadline = new_deadline
        self.shutdown_enabled = True
        if self._shutdown_task is None or self._shutdown_task.done():
            self._shutdown_task = asyncio.create_task(self._auto_shutdown_worker())
        return capped, added_hours

    async def _auto_shutdown_worker(self) -> None:
        while self.shutdown_enabled:
            if not self.shutdown_deadline:
                return
            remaining = self.shutdown_deadline - time.time()
            if remaining <= 0:
                logger.warning("自动关闭计时到达，正在停止服务器")
                await self._shutdown_sequence("auto-shutdown")
                return
            await asyncio.sleep(min(remaining, 30))

    async def _notify_shutdown(self, reason: str) -> None:
        try:
            await self._broadcast({"type": "server_shutdown", "reason": reason})
        except Exception:
            logger.exception("广播关闭通知失败")

    async def _shutdown_sequence(self, reason: str) -> None:
        await self._notify_shutdown(reason)
        await asyncio.sleep(0.25)
        self.request_stop(reason)

    async def handle_shutdown(self, request: web.Request) -> web.Response:
        self._require_local_client(request)
        data = await self._read_json(request)
        if data.get("confirm") is not True:
            raise web.HTTPBadRequest(text="必须确认关闭")
        active = self.active_downloads
        if active and data.get("force") is not True:
            return web.json_response(
                {
                    "error": f"当前有 {active} 个文件正在下载，关闭会中断下载",
                    "active_downloads": active,
                    "requires_force": True,
                },
                status=409,
            )
        logger.warning(
            "收到关闭服务器请求: active_downloads=%d force=%s 来自 %s",
            active,
            bool(data.get("force")),
            request.remote,
        )
        self._manual_shutdown_task = asyncio.create_task(self._shutdown_sequence("manual-shutdown"))
        return web.json_response({"success": True, "closing": True, "active_downloads": active})

    # -------------------------------------------------------------- lifecycle
    def _ssl_context(self) -> ssl.SSLContext | None:
        cert = self.config.ssl_cert
        key = self.config.ssl_key
        if not cert or not key:
            return None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            context.load_cert_chain(certfile=str(cert), keyfile=str(key))
        except (OSError, ssl.SSLError) as exc:
            raise RuntimeError(f"加载 HTTPS 证书失败（{cert}, {key}）: {exc}") from exc
        return context

    async def start(self) -> int:
        ssl_context = self._ssl_context()
        self._runner = web.AppRunner(
            self.app,
            access_log=(
                logging.getLogger("quicklanshare.access") if self.config.access_log else None
            ),
        )
        await self._runner.setup()
        attempts = max(1, int(self.config.port_attempts))
        last_error: Exception | None = None
        for attempt in range(attempts):
            candidate = self.config.port + attempt
            try:
                site = web.TCPSite(
                    self._runner, self.config.host, candidate, ssl_context=ssl_context
                )
                await site.start()
                self._site = site
                if candidate == 0:
                    sockets = getattr(getattr(site, "_server", None), "sockets", None) or []
                    if sockets:
                        candidate = int(sockets[0].getsockname()[1])
                self.port = candidate
                self.config.port = candidate
                logger.info("监听 %s:%s", self.config.host, candidate)
                return candidate
            except OSError as exc:
                last_error = exc
                message = str(exc).lower()
                if "address already in use" not in message and "10048" not in message:
                    await self._runner.cleanup()
                    self._runner = None
                    raise
                logger.warning("端口 %s 被占用，尝试 %s", candidate, candidate + 1)
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        raise RuntimeError(
            f"无法绑定端口 {self.config.port}-{self.config.port + attempts - 1}: {last_error}"
        )

    async def run(self) -> None:
        port = await self.start()
        assert self._site is not None
        if self.config.auto_shutdown_enabled:
            self.enable_auto_shutdown()
        self._log_banner(port)
        if self.config.open_browser:
            open_browser(f"{self.scheme}://localhost:{port}")
        try:
            await self.wait_stopped()
        finally:
            await self.aclose()

    async def wait_stopped(self) -> None:
        """等待停止事件；界面运行时用它把服务器挂在后台线程。"""
        await self._stop_event.wait()

    def request_stop(self, reason: str = "") -> None:
        if reason:
            self.stop_reason = reason
            logger.info("请求关闭: %s", reason)
        self._stop_event.set()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._shutdown_task and not self._shutdown_task.done():
            self._shutdown_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._shutdown_task
        self._shutdown_task = None
        for client in list(self.clients.values()):
            with contextlib.suppress(Exception):
                await client["ws"].close()
        self.clients.clear()
        await self.files.close()
        if self._site is not None:
            await self._site.stop()
            self._site = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("服务器已关闭")

    def _log_banner(self, port: int) -> None:
        logger.info("%s v%s 已启动", APP_NAME, __version__)
        logger.info("本机访问: %s://localhost:%s", self.scheme, port)
        logger.info("局域网访问: %s://%s:%s", self.scheme, self.local_ip, port)
        logger.info("数据目录: %s", self.config.data_dir)
        if self.config.auto_shutdown_enabled:
            logger.info("自动关闭: %.1f 小时后", self.config.auto_shutdown_hours)
        else:
            logger.info("自动关闭: 已关闭（服务保持运行）")
