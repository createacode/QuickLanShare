"""本地下载记录：记录“已下载”的文件及其本地路径。

保存在数据目录的 ``state/downloads.json``，与服务器共享文件列表分开。
只记录文件名与本地路径；文件被移动或删除后，加载时会自动丢弃该记录。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("quicklanshare.downloads")


class DownloadRegistry:
    """文件名 → 本地路径的轻量持久化记录。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._files: dict[str, Path] = {}
        self.load()

    def load(self) -> None:
        self._files = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            logger.warning("下载记录损坏，已忽略: %s", exc)
            with contextlib.suppress(OSError):
                self.path.replace(self.path.with_name(self.path.name + ".corrupt"))
            return
        files = raw.get("files") if isinstance(raw, dict) else None
        if not isinstance(files, dict):
            return
        for name, value in files.items():
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            path = Path(value)
            if path.exists():
                self._files[name] = path

    def save(self) -> None:
        payload = {
            "version": 1,
            "files": {name: str(path) for name, path in self._files.items()},
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.warning("保存下载记录失败: %s", exc)

    def get(self, name: str) -> Path | None:
        path = self._files.get(name)
        if path is not None and not path.exists():
            self._files.pop(name, None)
            self.save()
            return None
        return path

    def record(self, name: str, path: Path) -> None:
        self._files[name] = path
        self.save()

    def remove(self, names: list[str]) -> None:
        changed = False
        for name in names:
            if self._files.pop(name, None) is not None:
                changed = True
        if changed:
            self.save()

    def all(self) -> dict[str, Path]:
        return dict(self._files)

    def count(self) -> int:
        return len(self._files)


__all__ = ["DownloadRegistry"]
