"""从版本唯一真源生成 PyInstaller 的 VSVersionInfo 文件。

输出 ``scripts/version_info.txt``，供 ``pyinstaller --version-file`` 使用。
脚本可重复执行，相同版本输入产生相同输出。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PY = ROOT / "src" / "quicklanshare" / "core" / "version.py"
OUTPUT = ROOT / "scripts" / "version_info.txt"

_PATTERN = re.compile(r'^(__\w+__)\s*=\s*"([^"]*)"', re.MULTILINE)


def read_source(path: Path = VERSION_PY) -> dict[str, str]:
    """读取 ``version.py`` 中的真源常量。"""
    text = path.read_text(encoding="utf-8")
    values = dict(_PATTERN.findall(text))
    required = {"__software_name__", "__version__", "__author__", "__copyright_ym__"}
    missing = required - set(values)
    if missing:
        raise SystemExit(f"version.py 缺少字段: {', '.join(sorted(missing))}")
    return values


def four_part(version: str) -> tuple[int, int, int, int]:
    """把 ``MAJOR.MINOR.PATCH[-pre]`` 转成 exe 使用的四段版本号。"""
    core = version.split("-", 1)[0]
    parts = [int(part) for part in core.split(".") if part.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    parts = [*parts[:3], 0]
    return parts[0], parts[1], parts[2], parts[3]


def build_content(values: dict[str, str]) -> str:
    name = values["__software_name__"]
    version = values["__version__"]
    author = values["__author__"]
    ym = values["__copyright_ym__"]
    major, minor, patch, build = four_part(version)
    copyright_text = f"Copyright © {author} {ym}"
    return (
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers=({major}, {minor}, {patch}, {build}),\n"
        f"    prodvers=({major}, {minor}, {patch}, {build}),\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable(u'080404B0', [\n"
        f"        StringStruct(u'CompanyName', u'{author}'),\n"
        f"        StringStruct(u'FileDescription', u'{name} - 局域网文件快速传输工具'),\n"
        f"        StringStruct(u'FileVersion', u'{version}'),\n"
        f"        StringStruct(u'InternalName', u'{name}'),\n"
        f"        StringStruct(u'LegalCopyright', u'{copyright_text}'),\n"
        f"        StringStruct(u'OriginalFilename', u'{name}.exe'),\n"
        f"        StringStruct(u'ProductName', u'{name}'),\n"
        f"        StringStruct(u'ProductVersion', u'{version}')\n"
        "      ])\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])\n"
        "  ]\n"
        ")\n"
    )


def main() -> int:
    values = read_source()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_content(values), encoding="utf-8", newline="\n")
    print(f"已生成 {OUTPUT.relative_to(ROOT)}（{values['__version__']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
