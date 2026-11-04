"""File storage: safe paths, atomic uploads, resumable sessions, counters."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiofiles

from .config import Config
from .filenames import (
    InvalidFilename,
    is_reserved_name,
    resolve_upload_path,
    sanitize_upload_name,
)

SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class StorageError(Exception):
    pass


class UploadTooLarge(StorageError):
    pass


class UploadNotFound(StorageError):
    pass


class FileBusy(StorageError):
    pass


class UploadConflict(StorageError):
    def __init__(self, offset: int, message: str = "上传偏移不一致"):
        super().__init__(message)
        self.offset = offset


@dataclass
class UploadSession:
    upload_id: str
    name: str
    size: int
    mtime: float
    part_path: Path
    meta_path: Path
    created: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class FileStore:
    def __init__(self, config: Config):
        self.config = config
        self.data_dir = config.data_dir
        self.upload_dir = config.upload_dir
        self.tmp_dir = config.tmp_dir
        self.session_dir = config.session_dir
        self.counts_file = config.counts_file
        self._counts: dict[str, int] = {}
        self._count_dirty = False
        self._flush_task: asyncio.Task[None] | None = None
        self._sessions: dict[str, UploadSession] = {}
        self._secret: bytes | None = None
        self._migrate_legacy_counts()
        self._counts = self._load_counts()
        self.cleanup_stale_uploads()

    # ------------------------------------------------------------- counters
    def _load_counts(self) -> dict[str, int]:
        data: dict[str, int] = {}
        for candidate in (self.counts_file, self.upload_dir / "download_counts.json"):
            if not candidate.exists():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = {str(k): int(v) for k, v in raw.items() if isinstance(v, (int, float))}
                break
            except (OSError, ValueError):
                continue
        try:
            existing = {p.name for p in self.upload_dir.iterdir() if p.is_file()}
        except OSError:
            existing = set()
        data = {k: v for k, v in data.items() if k in existing}
        return data

    def _migrate_legacy_counts(self) -> None:
        legacy = self.upload_dir / "download_counts.json"
        if not legacy.exists():
            return
        try:
            if not self.counts_file.exists():
                os.replace(legacy, self.counts_file)
            else:
                os.replace(legacy, self.counts_file.with_name("download_counts.legacy.json"))
        except OSError:
            # Leave it in place; listing already ignores the reserved name.
            pass

    @property
    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def record_download(self, name: str) -> int:
        self._counts[name] = self._counts.get(name, 0) + 1
        self._count_dirty = True
        if self._flush_task is None or self._flush_task.done():
            try:
                self._flush_task = asyncio.create_task(self._flush_later())
            except RuntimeError:
                self._write_counts(dict(self._counts))
                self._count_dirty = False
        return self._counts[name]

    async def _flush_later(self) -> None:
        try:
            await asyncio.sleep(2.0)
            await self.flush()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def flush(self) -> None:
        if not self._count_dirty:
            return
        self._count_dirty = False
        snapshot = dict(self._counts)
        try:
            await asyncio.to_thread(self._write_counts, snapshot)
        except Exception:
            self._count_dirty = True
            raise

    def _write_counts(self, snapshot: dict[str, int]) -> None:
        self.counts_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.counts_file.with_name(self.counts_file.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False)
        os.replace(tmp, self.counts_file)

    # ---------------------------------------------------------------- listing
    def list_files(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        try:
            entries = list(self.upload_dir.iterdir())
        except OSError:
            return items
        for path in entries:
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                if is_reserved_name(path.name):
                    continue
                stat = path.stat()
            except OSError:
                continue
            items.append(
                {
                    "id": path.name,
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "download_count": self._counts.get(path.name, 0),
                }
            )
        items.sort(key=lambda item: item["modified"], reverse=True)
        return items

    def get_path(self, name: str) -> Path:
        path = resolve_upload_path(self.upload_dir, name)
        if not path.is_file():
            raise FileNotFoundError(name)
        return path

    def free_space(self) -> int:
        try:
            return shutil.disk_usage(self.data_dir).free
        except OSError:
            return 0

    # ---------------------------------------------------------------- delete
    def delete(self, name: str) -> None:
        path = resolve_upload_path(self.upload_dir, name)
        try:
            path.unlink()
        except FileNotFoundError:
            raise
        except PermissionError as exc:
            raise FileBusy(f"文件正在被使用: {name}") from exc
        except OSError as exc:
            raise FileBusy(f"删除失败: {exc}") from exc
        if self._counts.pop(name, None) is not None:
            self._count_dirty = True
            try:
                self._flush_task = asyncio.create_task(self.flush())
            except RuntimeError:
                self._write_counts(dict(self._counts))
                self._count_dirty = False

    # ------------------------------------------------------------ new uploads
    def _reserve_target(self, name: str) -> tuple[Path, str]:
        base, ext = os.path.splitext(name)
        for attempt in range(1000):
            candidate = name if attempt == 0 else f"{base}_{attempt}{ext}"
            path = self.upload_dir / candidate
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                continue
            os.close(descriptor)
            return path, candidate
        candidate = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
        path = self.upload_dir / candidate
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(descriptor)
        return path, candidate

    def _check_capacity(self, needed: int) -> None:
        if needed <= 0:
            return
        free = self.free_space()
        reserve = 64 * 1024 * 1024
        if free and free < needed + reserve:
            raise UploadTooLarge("磁盘空间不足")

    async def save_stream(self, field: Any, max_size: int | None = None) -> dict[str, Any]:
        """Persist a single multipart field atomically."""
        limit = max_size if max_size is not None else self.config.max_upload_size
        name = sanitize_upload_name(getattr(field, "filename", None))
        self._check_capacity(min(limit, 1024 * 1024 * 1024))
        part_path = self.tmp_dir / f"legacy_{uuid.uuid4().hex}.part"
        total = 0
        finalized = False
        try:
            async with aiofiles.open(part_path, "wb") as handle:
                while True:
                    chunk = await field.read_chunk(self.config.upload_chunk_size)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise UploadTooLarge("文件大小超过上传上限")
                    await handle.write(chunk)
            target, final_name = self._reserve_target(name)
            try:
                os.replace(part_path, target)
                finalized = True
            except OSError:
                with contextlib.suppress(OSError):
                    target.unlink()
                raise
        finally:
            if not finalized:
                with contextlib.suppress(OSError):
                    part_path.unlink()
        return {
            "filename": final_name,
            "size": total,
            "download_count": self._counts.get(final_name, 0),
        }

    # ------------------------------------------------------- resumable session
    def _upload_secret(self) -> bytes:
        if self._secret is not None:
            return self._secret
        secret_path = self.config.state_dir / "upload_secret"
        with contextlib.suppress(OSError):
            self._secret = secret_path.read_bytes()
        if not self._secret:
            self._secret = os.urandom(32)
            try:
                secret_path.parent.mkdir(parents=True, exist_ok=True)
                secret_path.write_bytes(self._secret)
            except OSError:
                pass
        return self._secret

    def _session_key(self, name: str, size: int, mtime: float, nonce: str = "") -> str:
        digest = hashlib.sha256()
        digest.update(self._upload_secret())
        digest.update(b"\0")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(int(size)).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(int(mtime or 0)).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(nonce).encode("utf-8")[:64])
        return digest.hexdigest()[:32]

    def _meta_for(self, upload_id: str) -> Path:
        return self.session_dir / f"{upload_id}.json"

    def _part_for(self, upload_id: str) -> Path:
        return self.tmp_dir / f"{upload_id}.part"

    def init_upload(
        self, filename: str | None, size: int, mtime: float = 0, nonce: str = ""
    ) -> dict[str, Any]:
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise InvalidFilename("非法文件大小")
        if not isinstance(nonce, str):
            nonce = ""
        nonce = nonce[:64]
        name = sanitize_upload_name(filename)
        if size > self.config.max_upload_size:
            raise UploadTooLarge("文件大小超过上传上限")
        upload_id = self._session_key(name, size, mtime, nonce)
        part_path = self._part_for(upload_id)
        meta_path = self._meta_for(upload_id)
        offset = 0
        if meta_path.exists() and part_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = None
            if (
                isinstance(meta, dict)
                and meta.get("name") == name
                and meta.get("size") == size
                and int(meta.get("mtime", 0)) == int(mtime or 0)
                and str(meta.get("nonce", "")) == nonce
            ):
                offset = part_path.stat().st_size
                if offset > size:
                    part_path.unlink(missing_ok=True)
                    offset = 0
        self._check_capacity(size - offset)
        if offset == 0:
            part_path.parent.mkdir(parents=True, exist_ok=True)
            part_path.write_bytes(b"")
            meta = {
                "upload_id": upload_id,
                "name": name,
                "size": size,
                "mtime": int(mtime or 0),
                "nonce": nonce,
                "created": time.time(),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        session = UploadSession(
            upload_id=upload_id,
            name=name,
            size=size,
            mtime=float(mtime or 0),
            part_path=part_path,
            meta_path=meta_path,
            created=float(
                meta.get("created", time.time()) if isinstance(meta, dict) else time.time()
            ),
        )
        self._sessions[upload_id] = session
        return {
            "upload_id": upload_id,
            "offset": offset,
            "size": size,
            "name": name,
        }

    def _get_session(self, upload_id: str) -> UploadSession:
        if not SESSION_ID_RE.match(upload_id or ""):
            raise UploadNotFound(upload_id)
        existing = self._sessions.get(upload_id)
        if existing is not None:
            return existing
        meta_path = self._meta_for(upload_id)
        part_path = self._part_for(upload_id)
        if not meta_path.exists() or not part_path.exists():
            raise UploadNotFound(upload_id)
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            session = UploadSession(
                upload_id=upload_id,
                name=str(meta["name"]),
                size=int(meta["size"]),
                mtime=float(meta.get("mtime", 0)),
                part_path=part_path,
                meta_path=meta_path,
                created=float(meta.get("created", time.time())),
            )
        except (OSError, ValueError, KeyError) as exc:
            raise UploadNotFound(upload_id) from exc
        self._sessions[upload_id] = session
        return session

    def session_offset(self, upload_id: str) -> int:
        session = self._get_session(upload_id)
        try:
            return session.part_path.stat().st_size
        except OSError:
            return 0

    async def append_chunk(self, upload_id: str, offset: int, data: bytes) -> int:
        session = self._get_session(upload_id)
        async with session.lock:
            try:
                current = session.part_path.stat().st_size
            except OSError:
                current = 0
            if offset != current:
                raise UploadConflict(current)
            if current + len(data) > session.size:
                raise UploadTooLarge("上传数据超过声明的文件大小")
            async with aiofiles.open(session.part_path, "ab") as handle:
                await handle.write(data)
            return current + len(data)

    async def complete_upload(self, upload_id: str) -> dict[str, Any]:
        session = self._get_session(upload_id)
        async with session.lock:
            try:
                current = session.part_path.stat().st_size
            except OSError:
                current = 0
            if current != session.size:
                raise UploadConflict(current, "文件尚未上传完成")
            target, final_name = self._reserve_target(session.name)
            try:
                os.replace(session.part_path, target)
            except OSError:
                with contextlib.suppress(OSError):
                    target.unlink()
                raise
            self._cleanup_session_files(session)
            return {
                "filename": final_name,
                "size": session.size,
                "download_count": self._counts.get(final_name, 0),
            }

    def abort_upload(self, upload_id: str) -> None:
        session = self._get_session(upload_id)
        self._cleanup_session_files(session)
        self._sessions.pop(upload_id, None)

    def _cleanup_session_files(self, session: UploadSession) -> None:
        for path in (session.part_path, session.meta_path):
            with contextlib.suppress(OSError):
                path.unlink()

    def cleanup_stale_uploads(self) -> None:
        cutoff = time.time() - self.config.stale_upload_max_age
        for directory, pattern in ((self.tmp_dir, "*.part"), (self.session_dir, "*.json")):
            try:
                for path in directory.glob(pattern):
                    try:
                        if path.stat().st_mtime < cutoff:
                            path.unlink()
                    except OSError:
                        continue
            except OSError:
                continue

    async def close(self) -> None:
        task = self._flush_task
        self._flush_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        with contextlib.suppress(Exception):
            await self.flush()
