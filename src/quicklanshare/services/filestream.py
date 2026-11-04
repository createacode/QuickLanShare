"""Large-file download streaming.

``aiohttp.web.FileResponse`` delegates to ``loop.sendfile``; on Windows the
underlying ``TransmitFile`` call rejects a single transfer larger than 2 GiB
with ``WinError 87`` and closes the connection.  That made any download above
2 GiB fail (Chrome retried the URL repeatedly and eventually showed
"download failed").

This module streams the file with ordinary reads/writes instead, which has no
2 GiB limit, while still supporting single-range requests for browser resume.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

import aiofiles
from aiohttp import web

from .filenames import content_disposition

logger = logging.getLogger("quicklanshare.download")

CHUNK_SIZE = 1024 * 1024


class RangeNotSatisfiable(Exception):
    def __init__(self, size: int):
        self.size = size


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Parse a single HTTP Range header.

    Multiple ranges are intentionally not supported; browsers use one range per
    request and returning the whole file for a multi-range request is safe.
    """
    if not header:
        return None
    header = header.strip()
    if not header.lower().startswith("bytes="):
        return None
    spec = header[6:].split(",", 1)[0].strip()
    if "-" not in spec:
        raise RangeNotSatisfiable(size)
    start_text, end_text = spec.split("-", 1)
    try:
        if start_text == "":
            suffix = int(end_text)
            if suffix <= 0:
                raise ValueError
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
    except ValueError as exc:
        raise RangeNotSatisfiable(size) from exc
    if start < 0 or start >= size or end < start:
        raise RangeNotSatisfiable(size)
    return start, min(end, size - 1)


def _headers(
    path: Path, size: int, download_name: str, start: int, end: int, partial: bool
) -> dict[str, str]:
    stat = path.stat()
    modified = format_datetime(datetime.fromtimestamp(stat.st_mtime, UTC), usegmt=True)
    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": content_disposition(download_name),
        "Accept-Ranges": "bytes",
        "Last-Modified": modified,
        "ETag": f'"{int(stat.st_mtime)}-{size}"',
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
    else:
        headers["Content-Length"] = str(size)
    return headers


async def stream_download(
    request: web.Request,
    path: Path,
    download_name: str,
) -> web.StreamResponse:
    size = path.stat().st_size
    start, end = 0, size - 1
    partial = False
    try:
        parsed = parse_range(request.headers.get("Range"), size)
    except RangeNotSatisfiable:
        return web.Response(
            status=416,
            headers={
                "Content-Range": f"bytes */{size}",
                "Accept-Ranges": "bytes",
            },
            text="Range Not Satisfiable",
        )
    if parsed is not None:
        start, end = parsed
        partial = True

    status = 206 if partial else 200
    headers = _headers(path, size, download_name, start, end, partial)

    if request.method == "HEAD":
        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)
        await response.write_eof()
        return response

    response = web.StreamResponse(status=status, headers=headers)
    await response.prepare(request)
    remaining = (end - start + 1) if size else 0
    if remaining <= 0:
        await response.write_eof()
        return response

    try:
        async with aiofiles.open(path, "rb") as handle:
            await handle.seek(start)
            while remaining > 0:
                chunk = await handle.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    logger.warning("下载文件提前结束: %s, 剩余 %d 字节", download_name, remaining)
                    break
                await response.write(chunk)
                remaining -= len(chunk)
        await response.write_eof()
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
        # Client canceled / navigated away; this is normal for large downloads.
        logger.debug("客户端中断下载: %s", download_name)
    return response
