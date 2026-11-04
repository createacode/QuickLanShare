"""同步版本派生文件：版权年月、VERSION.txt、文档标题与发布包名。"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PY = ROOT / "src" / "quicklanshare" / "core" / "version.py"
VERSION_TXT = ROOT / "VERSION.txt"
DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "readme.md",
    ROOT / "docs" / "develop-readme.md",
)
_PATTERN = re.compile(r'^(__\w+__)\s*=\s*"([^"]*)"', re.MULTILINE)


def read_source(path: Path = VERSION_PY) -> dict[str, str]:
    values = dict(_PATTERN.findall(path.read_text(encoding="utf-8")))
    for key in ("__software_name__", "__version__", "__author__", "__copyright_ym__"):
        if key not in values:
            raise SystemExit(f"version.py 缺少字段: {key}")
    return values


def write_copyright_ym(ym: str) -> None:
    text = VERSION_PY.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'^__copyright_ym__\s*=\s*"[^"]*"',
        f'__copyright_ym__ = "{ym}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit("无法更新 __copyright_ym__")
    VERSION_PY.write_text(updated, encoding="utf-8", newline="\n")


def write_version_txt(values: dict[str, str], build_date: str) -> None:
    content = (
        f"软件名称：{values['__software_name__']}\n"
        f"版本号：{values['__version__']}\n"
        f"作者：{values['__author__']}\n"
        f"版权：Copyright © {values['__author__']} {values['__copyright_ym__']}\n"
        f"构建日期：{build_date}\n"
        "目标平台：Windows 10 / 11 x64\n"
        "许可：生成物归使用者所有；第三方组件许可见 THIRD-PARTY-NOTICES.md\n"
    )
    VERSION_TXT.write_text(content, encoding="utf-8", newline="\n")


def update_doc_titles(values: dict[str, str]) -> None:
    title = (
        f"# {values['__software_name__']} v{values['__version__']} "
        f"- Copyright © {values['__author__']} {values['__copyright_ym__']}"
    )
    for path in DOCS:
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.startswith("# "):
                lines[index] = title
                break
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def build_date_from(value: str | None) -> str:
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError as exc:
            raise SystemExit(f"--build-date 格式应为 YYYY-MM-DD: {exc}") from exc
    return date.today().strftime("%Y-%m-%d")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步 QuickLanShare 版本派生文件")
    parser.add_argument("--copyright-ym", default=datetime.now().strftime("%Y.%m"))
    parser.add_argument("--build-date", default=None)
    parser.add_argument("--print-release-name", action="store_true")
    args = parser.parse_args(argv)

    write_copyright_ym(args.copyright_ym)
    values = read_source()
    build_date = build_date_from(args.build_date)
    write_version_txt(values, build_date)
    update_doc_titles(values)
    release_name = (
        f"{values['__software_name__']}_v{values['__version__']}_win-x64_"
        f"{build_date.replace('-', '')}"
    )
    print(f"版本：{values['__version__']}  版权：{args.copyright_ym}  构建日期：{build_date}")
    print(f"发布包名：{release_name}")
    if args.print_release_name:
        print(release_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
