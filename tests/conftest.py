"""pytest 全局配置：GUI 测试使用 offscreen 平台，避免弹出真实窗口。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")
