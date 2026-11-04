"""校验版本号与版权串是否处处一致；不一致时返回非零退出码。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PY = ROOT / "src" / "quicklanshare" / "core" / "version.py"
VERSION_INFO = ROOT / "scripts" / "version_info.txt"
VERSION_TXT = ROOT / "VERSION.txt"
PYPROJECT = ROOT / "pyproject.toml"
DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "readme.md",
    ROOT / "docs" / "develop-readme.md",
)
_PATTERN = re.compile(r'^(__\w+__)\s*=\s*"([^"]*)"', re.MULTILINE)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        # 旧版 Windows 控制台默认 GBK，无法编码 “©”，用替换字符避免脚本崩溃。
        _stream.reconfigure(errors="replace")


def read_source() -> dict[str, str]:
    values = dict(_PATTERN.findall(VERSION_PY.read_text(encoding="utf-8")))
    for key in ("__software_name__", "__version__", "__author__", "__copyright_ym__"):
        if key not in values:
            raise SystemExit(f"[FAIL] version.py 缺少字段 {key}")
    return values


def check(condition: bool, message: str, failures: list[str]) -> None:
    print(f"[{'OK' if condition else 'FAIL'}] {message}")
    if not condition:
        failures.append(message)


def main() -> int:
    values = read_source()
    name = values["__software_name__"]
    version = values["__version__"]
    author = values["__author__"]
    ym = values["__copyright_ym__"]
    suffix = f"- Copyright © {author} {ym}"
    failures: list[str] = []

    if VERSION_INFO.exists():
        info = VERSION_INFO.read_text(encoding="utf-8")
        check(f"u'{version}'" in info, "version_info.txt 版本号一致", failures)
        check(f"u'Copyright © {author} {ym}'" in info, "version_info.txt 版权一致", failures)
        check(f"u'{name}'" in info, "version_info.txt 产品名一致", failures)
    else:
        check(False, "scripts/version_info.txt 已生成（运行 gen_version_info.py）", failures)

    if VERSION_TXT.exists():
        text = VERSION_TXT.read_text(encoding="utf-8")
        check(f"版本号：{version}" in text, "VERSION.txt 版本号一致", failures)
        check(f"版权：Copyright © {author} {ym}" in text, "VERSION.txt 版权一致", failures)
        check(f"软件名称：{name}" in text, "VERSION.txt 软件名一致", failures)
    else:
        check(False, "VERSION.txt 存在（运行 sync_version.py）", failures)

    pyproject = PYPROJECT.read_text(encoding="utf-8")
    check('dynamic = ["version"]' in pyproject, "pyproject.toml 版本动态读取", failures)
    check(
        "[tool.hatch.version]" in pyproject
        and 'path = "src/quicklanshare/core/version.py"' in pyproject,
        "pyproject.toml 指向唯一真源",
        failures,
    )
    check(
        re.search(r'^version\s*=\s*"', pyproject, re.MULTILINE) is None,
        "pyproject.toml 未写死第二份版本号",
        failures,
    )

    for path in DOCS:
        if not path.exists():
            check(False, f"{path.relative_to(ROOT)} 存在", failures)
            continue
        first = path.read_text(encoding="utf-8").splitlines()[0]
        expected = f"# {name} v{version} {suffix}"
        check(first == expected, f"{path.relative_to(ROOT)} 标题一致", failures)

    if failures:
        print(f"\n版本校验失败：{len(failures)} 项不一致")
        return 1
    print(f"\n版本校验通过：{name} v{version} {suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
