"""Streaming ZIP writer.

Building a multi-gigabyte archive into a temporary file (the old behaviour)
blocked the event loop and needed as much temp disk as the archive itself.
Here the standard library ``zipfile`` writer runs in a worker thread and pushes
bytes through a small bounded queue into the HTTP response, so:

* memory stays around a few megabytes,
* the first byte can be sent immediately,
* the event loop is never blocked by compression or disk I/O,
* ZIP64 and UTF-8 names are handled by ``zipfile`` itself.
"""

from __future__ import annotations

import asyncio
import io
import logging
import queue
import threading
import zipfile
from pathlib import Path
from typing import Any

from aiohttp import web

logger = logging.getLogger("quicklanshare.zip")

_SENTINEL = object()


class ZipStreamAborted(Exception):
    pass


class _QueueWriter(io.RawIOBase):
    """Minimal write-only, non-seekable file object backed by a queue."""

    def __init__(self, sink: queue.Queue[Any], stop: threading.Event, chunk_size: int):
        self._sink = sink
        self._stop = stop
        self._chunk_size = chunk_size

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def write(self, data: Any) -> int:
        view = memoryview(data)
        written = 0
        while view:
            if self._stop.is_set():
                raise ZipStreamAborted()
            piece = bytes(view[: self._chunk_size])
            view = view[self._chunk_size :]
            self._put(piece)
            written += len(piece)
        return written

    def _put(self, item: Any) -> None:
        while True:
            if self._stop.is_set():
                raise ZipStreamAborted()
            try:
                self._sink.put(item, timeout=0.2)
                return
            except queue.Full:
                continue

    def flush(self) -> None:  # no-op on purpose
        return None

    def close(self) -> None:  # the queue is owned by the stream
        return None


def _produce(
    sink: queue.Queue[Any],
    stop: threading.Event,
    entries: list[tuple[Path, str]],
    compression: int,
) -> None:
    try:
        writer = _QueueWriter(sink, stop, 1024 * 1024)
        with zipfile.ZipFile(writer, "w", compression=compression, allowZip64=True) as archive:
            for path, arcname in entries:
                if stop.is_set():
                    raise ZipStreamAborted()
                archive.write(path, arcname=arcname)
        _put_blocking(sink, stop, _SENTINEL)
    except ZipStreamAborted:
        return
    except BaseException as exc:
        try:
            _put_blocking(sink, stop, ("__error__", exc))
        except ZipStreamAborted:
            return


def _put_blocking(sink: queue.Queue[Any], stop: threading.Event, item: Any) -> None:
    while True:
        if stop.is_set():
            raise ZipStreamAborted()
        try:
            sink.put(item, timeout=0.2)
            return
        except queue.Full:
            continue


def compression_code(name: str) -> int:
    return zipfile.ZIP_DEFLATED if str(name).lower() == "deflate" else zipfile.ZIP_STORED


class StreamingZip:
    def __init__(
        self,
        entries: list[tuple[Path, str]],
        download_name: str,
        compression: int = zipfile.ZIP_STORED,
        queue_size: int = 8,
    ):
        self.entries = entries
        self.download_name = download_name
        self.compression = compression
        self.queue_size = max(2, int(queue_size))

    async def stream(self, request: web.Request) -> web.StreamResponse:
        from .filenames import content_disposition

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "application/zip",
                "Content-Disposition": content_disposition(self.download_name),
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )
        response.enable_chunked_encoding()
        await response.prepare(request)

        sink: queue.Queue[Any] = queue.Queue(maxsize=self.queue_size)
        stop = threading.Event()
        thread = threading.Thread(
            target=_produce,
            args=(sink, stop, self.entries, self.compression),
            name="zip-stream",
            daemon=True,
        )
        thread.start()
        loop = asyncio.get_running_loop()
        failed = False
        cancelled = False
        try:
            while True:
                item = await loop.run_in_executor(None, sink.get)
                if item is _SENTINEL:
                    break
                if isinstance(item, tuple) and item and item[0] == "__error__":
                    error = item[1]
                    logger.error(
                        "打包失败: %s",
                        error,
                        exc_info=(type(error), error, error.__traceback__),
                    )
                    failed = True
                    break
                await response.write(item)
        except asyncio.CancelledError:
            cancelled = True
        except (ConnectionResetError, ConnectionAbortedError):
            failed = True
        finally:
            stop.set()
            while True:
                try:
                    sink.get_nowait()
                except queue.Empty:
                    break
            await loop.run_in_executor(None, thread.join, 5)
            if thread.is_alive():  # pragma: no cover - defensive
                logger.warning("ZIP 压缩线程未在预期时间内退出")
        if cancelled:
            raise asyncio.CancelledError()
        if failed:
            # Headers are already on the wire; dropping the connection makes
            # the browser report a failed download instead of a truncated ZIP.
            transport = request.transport
            if transport is not None:
                transport.close()
        return response
