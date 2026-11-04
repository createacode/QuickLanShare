"""``python -m quicklanshare`` 入口（薄包装）。"""

from __future__ import annotations

from quicklanshare.app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
