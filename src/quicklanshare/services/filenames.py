"""Filename and path hardening helpers.

Every path that is derived from user input goes through this module.  The
functions are intentionally strict: they reject anything that is not a single,
plain path component so that directory traversal, NTFS alternate data streams
and Windows device names cannot escape the upload directory.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from .config import APP_NAME

_METADATA_NAMES = {"download_counts.json"}
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_INVALID_CHARS = set('<>:"|?*')
_CONTROL_CHARS = {chr(i) for i in range(32)} | {"\x7f"}
_MAX_NAME_CHARS = 180


class InvalidFilename(ValueError):
    """Raised when user supplied name cannot be used safely."""


def sanitize_upload_name(raw: str | None, fallback: str = "upload") -> str:
    """Turn an arbitrary client supplied name into a safe single component.

    Browsers normally send only a basename, but some clients (and malicious
    ones) send paths.  We keep the last path segment, replace characters that
    are illegal on Windows, drop control characters and protect reserved device
    names.  Unicode is preserved.
    """
    if not isinstance(raw, str) or not raw:
        return fallback
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = []
    for ch in name:
        if ch in _CONTROL_CHARS or ch in _INVALID_CHARS:
            cleaned.append("_")
        else:
            cleaned.append(ch)
    name = "".join(cleaned).strip().rstrip(". ")
    if name in ("", ".", ".."):
        name = fallback
    stem = name.split(".", 1)[0].strip().upper()
    if stem in _WINDOWS_RESERVED:
        name = "_" + name
    if name.lower() in _METADATA_NAMES:
        name = "_" + name
    if len(name) > _MAX_NAME_CHARS:
        suffix = Path(name).suffix[:24]
        name = name[: _MAX_NAME_CHARS - len(suffix)].rstrip(". ") + suffix
    return name or fallback


def is_plain_component(name: str) -> bool:
    """True when *name* is a single path component without separators."""
    if not isinstance(name, str) or not name:
        return False
    if name in (".", ".."):
        return False
    if "/" in name or "\\" in name or "\x00" in name:
        return False
    if ":" in name:  # NTFS alternate data streams / drive prefixes
        return False
    if any(ch in _CONTROL_CHARS for ch in name):
        return False
    if name.rstrip(". ") != name:
        return False
    return Path(name).name == name


def is_reserved_name(name: str) -> bool:
    return name.lower() in _METADATA_NAMES or name.lower().endswith((".part", ".tmp"))


def resolve_upload_path(base: Path, name: str) -> Path:
    """Resolve *name* inside *base*, rejecting traversal and reserved names."""
    if not is_plain_component(name) or is_reserved_name(name):
        raise InvalidFilename(f"非法文件名: {name!r}")
    base_resolved = base.resolve()
    candidate = (base_resolved / name).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise InvalidFilename(f"非法文件名: {name!r}") from exc
    if candidate.parent != base_resolved:
        raise InvalidFilename(f"非法文件名: {name!r}")
    return candidate


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    """Build an RFC 5987 compliant ``Content-Disposition`` value."""
    cleaned: list[str] = []
    for ch in filename:
        if ch in '"\\':
            cleaned.append("_")
        elif 32 <= ord(ch) < 127:
            cleaned.append(ch)
        # Non-ASCII characters are carried by filename* only.
    safe = "".join(cleaned).replace("\r", "").replace("\n", "").strip() or "download"
    fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", safe) or "download"
    encoded = quote(filename, safe="")
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def quote_url_name(name: str) -> str:
    """Percent-encode a filename for use as a single URL path segment."""
    return quote(name, safe="")


def display_size(num: int | float) -> str:
    num = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024.0:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}TB"


def app_filename(prefix: str = APP_NAME) -> str:
    return prefix
