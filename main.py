"""QuickLanShare 启动入口（薄包装）。

真正的启动逻辑只存在于 ``quicklanshare.app.main:main``，本文件仅转发。
"""

from __future__ import annotations

from quicklanshare.app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
