"""Persistent chat history stored as daily JSON Lines files.

The old implementation stored messages in a fragile two-line text format,
which could be corrupted by a message containing a newline and lost message
IDs across restarts.  JSONL keeps the id, author, timestamp and text together,
supports atomic deletion and can be migrated from the legacy format.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles

from .config import Config


class ChatError(Exception):
    pass


class EmptyMessage(ChatError):
    pass


class MessageTooLong(ChatError):
    pass


class ChatStore:
    def __init__(self, config: Config):
        self.config = config
        self.directory = config.chat_dir
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_length = config.max_chat_message
        self.memory_limit = config.chat_memory_limit
        self._messages: list[dict[str, Any]] = []
        self._migrate_legacy_files()
        self._load_recent()

    # ---------------------------------------------------------------- loading
    @staticmethod
    def _day_file(directory: Path, timestamp: float) -> Path:
        day = datetime.fromtimestamp(timestamp).strftime("%Y%m%d")
        return directory / f"chat_{day}.jsonl"

    def _migrate_legacy_files(self) -> None:
        for txt in sorted(self.directory.glob("chat_*.txt")):
            target = txt.with_suffix(".jsonl")
            backup = txt.with_name(txt.name + ".bak")
            try:
                if not target.exists():
                    messages = self._parse_legacy(txt)
                    if messages:
                        with open(target, "w", encoding="utf-8") as handle:
                            for message in messages:
                                handle.write(json.dumps(message, ensure_ascii=False) + "\n")
                os.replace(txt, backup)
            except OSError:
                continue

    def _parse_legacy(self, path: Path) -> list[dict[str, Any]]:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            fallback_ts = path.stat().st_mtime
        except OSError:
            return []
        messages: list[dict[str, Any]] = []
        index = 0
        while index < len(lines):
            header = lines[index].strip()
            if not header:
                index += 1
                continue
            text = lines[index + 1].strip() if index + 1 < len(lines) else ""
            parts = header.split(" ", 1)
            if len(parts) != 2 or not text:
                index += 2
                continue
            ip, time_str = parts
            try:
                stamp = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").timestamp()
            except ValueError:
                stamp = fallback_ts
            digest = hashlib.sha1(f"{ip}\0{time_str}\0{text}".encode()).hexdigest()[:16]
            messages.append(
                {
                    "id": f"hist_{digest}",
                    "message": text,
                    "client_name": "",
                    "client_ip": ip,
                    "timestamp": stamp,
                    "time_str": time_str,
                }
            )
            index += 2
        return messages

    def _load_recent(self) -> None:
        paths = sorted(self.directory.glob("chat_*.jsonl"), reverse=True)
        loaded: list[dict[str, Any]] = []
        for path in paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    lines = list(deque(handle, maxlen=self.memory_limit))
            except OSError:
                continue
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                message = self._normalize_row(raw)
                if message is None:
                    continue
                loaded.append(message)
                if len(loaded) >= self.memory_limit:
                    break
            if len(loaded) >= self.memory_limit:
                break
        loaded.reverse()
        self._messages = loaded

    @staticmethod
    def _normalize_row(raw: object) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        text = raw.get("message")
        if not isinstance(text, str) or not text.strip():
            return None
        try:
            stamp = float(raw.get("timestamp") or 0)
        except (TypeError, ValueError):
            stamp = 0.0
        time_str = raw.get("time_str")
        if not isinstance(time_str, str) or not time_str:
            time_str = datetime.fromtimestamp(stamp or time.time()).strftime("%Y-%m-%d %H:%M:%S")
        return {
            "id": str(raw.get("id") or secrets.token_hex(8)),
            "message": text,
            "client_name": str(raw.get("client_name") or ""),
            "client_ip": str(raw.get("client_ip") or ""),
            "timestamp": stamp,
            "time_str": time_str,
        }

    # ------------------------------------------------------------------ reads
    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return [dict(item) for item in self._messages[-limit:]]

    def total(self) -> int:
        return len(self._messages)

    # ----------------------------------------------------------------- writes
    def _normalize_text(self, text: str) -> str:
        if not isinstance(text, str):
            raise EmptyMessage("消息不能为空")
        cleaned = text.replace("\r", " ").replace("\n", " ").strip()
        if not cleaned:
            raise EmptyMessage("消息不能为空")
        if len(cleaned) > self.max_length:
            raise MessageTooLong(f"消息不能超过 {self.max_length} 个字符")
        return cleaned

    async def add(self, client_name: str, client_ip: str, text: str) -> dict[str, Any]:
        cleaned = self._normalize_text(text)
        stamp = time.time()
        message = {
            "id": secrets.token_hex(8),
            "message": cleaned,
            "client_name": client_name,
            "client_ip": client_ip,
            "timestamp": stamp,
            "time_str": datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M:%S"),
        }
        path = self._day_file(self.directory, stamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "a", encoding="utf-8") as handle:
            await handle.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._messages.append(message)
        if len(self._messages) > self.memory_limit:
            del self._messages[: len(self._messages) - self.memory_limit]
        return dict(message)

    async def delete(self, message_id: str) -> bool:
        if not message_id or len(message_id) > 128:
            return False
        target: dict[str, Any] | None = None
        for message in self._messages:
            if message["id"] == message_id:
                target = message
                break
        path: Path | None = None
        if target is not None:
            for message in self._messages:
                if message["id"] == message_id:
                    path = self._day_file(self.directory, float(message.get("timestamp") or 0))
                    break
        else:
            target, path = self._find_on_disk(message_id)
        if target is None:
            return False
        self._messages = [item for item in self._messages if item["id"] != message_id]
        if path is not None and path.exists():
            await asyncio.to_thread(self._rewrite_without, path, message_id)
        return True

    def _find_on_disk(self, message_id: str) -> tuple[dict[str, Any] | None, Path | None]:
        for path in sorted(self.directory.glob("chat_*.jsonl"), reverse=True)[:90]:
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                if isinstance(raw, dict) and str(raw.get("id")) == message_id:
                    message = self._normalize_row(raw)
                    if message is not None:
                        return message, path
        return None, None

    def _rewrite_without(self, path: Path, message_id: str) -> None:
        tmp = path.with_name(path.name + ".tmp")
        try:
            with (
                open(path, encoding="utf-8", errors="replace") as source,
                open(tmp, "w", encoding="utf-8") as target,
            ):
                for line in source:
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                    except ValueError:
                        target.write(line)
                        continue
                    if isinstance(raw, dict) and str(raw.get("id")) == message_id:
                        continue
                    target.write(line)
            os.replace(tmp, path)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
