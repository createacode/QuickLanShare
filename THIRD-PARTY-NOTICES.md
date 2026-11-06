# 第三方组件与许可声明

本项目（QuickLanShare v3.5.4）在开发、构建与运行中使用了以下第三方组件。
发布包仅包含运行所需的组件；开发工具（pytest、ruff、mypy 等）不随发布包分发。

> 本文件不构成法律意见。对外分发前请结合自身场景核对各许可证原文。

---

## 1. 运行时组件

### 1.1 Qt for Python（PySide6 / shiboken6 / Qt 6.12）

| 项 | 内容 |
| --- | --- |
| 组件 | PySide6 6.12.0、shiboken6 6.12.0、Qt 6.12 运行库 |
| 用途 | 桌面界面（窗口、控件、绘图、系统托盘、网络） |
| 许可 | LGPL-3.0-only（另有 GPL-2.0 / GPL-3.0 双许可选项） |
| 分发方式 | **动态链接**：随包提供未修改的 Qt DLL；不把 Qt 静态链接进 exe |
| 获取源码 | <https://download.qt.io/official_releases/QtForPython/>、<https://code.qt.io/cgit/pyside/pyside-setup.git/> |
| 许可原文 | <https://www.gnu.org/licenses/lgpl-3.0.html> |

**LGPL 合规说明（可替换性）**

- 发布目录 `_internal/PySide6/` 下的 `Qt6*.dll`、`pyside6*.pyd` 与 `plugins/` 保持独立文件，
  未与 `QuickLanShare.exe` 合并；
- 用户可以用兼容版本的 Qt / PySide6 库替换这些文件，无需修改或重新编译 `QuickLanShare.exe`；
- 程序未对 Qt 库做逆向、修改或封装限制；
- Qt 的版权与许可文本可随 Qt 官方安装包获取；如需书面副本，请从上述链接下载对应版本。

### 1.2 aiohttp 3.14.5

- 用途：HTTP / WebSocket 服务器与桌面端本机客户端；
- 许可：Apache-2.0 AND MIT；
- 项目主页：<https://github.com/aio-libs/aiohttp>；
- 许可原文：<https://github.com/aio-libs/aiohttp/blob/master/LICENSE.txt>。

### 1.3 aiofiles 24.1.0

- 用途：异步文件读写；
- 许可：Apache-2.0；
- 项目主页：<https://github.com/Tinche/aiofiles>；
- 许可原文：<https://github.com/Tinche/aiofiles/blob/master/LICENSE>。

### 1.4 qrcode 8.2

- 用途：生成局域网访问二维码；
- 许可：BSD-3-Clause；
- 项目主页：<https://github.com/lincolnloop/python-qrcode>；
- 许可原文：<https://github.com/lincolnloop/python-qrcode/blob/main/LICENSE>。

### 1.5 Pillow 11.3.0

- 用途：二维码 PNG 编码；
- 许可：MIT-CMU（Pillow 许可证）；
- 项目主页：<https://python-pillow.org/>；
- 许可原文：<https://github.com/python-pillow/Pillow/blob/main/LICENSE>。

### 1.6 Python 3.13

- 用途：解释器，由 PyInstaller 一并打包；
- 许可：Python Software Foundation License 2.0；
- 许可原文：<https://docs.python.org/3/license.html>。

### 1.7 PyInstaller 6.22.3（构建期 + 引导器）

- 用途：生成 Windows exe；
- 许可：GPL-2.0-or-later，附带特殊例外，允许用其构建并分发非自由/商业程序；
- 项目主页：<https://pyinstaller.org/>；
- 许可原文：<https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt>。

### 1.8 Font Awesome Free 6.4.0（网页客户端）

- 用途：网页端图标与字体（`client/all.min.css`、`client/webfonts/`）；
- 许可：图标 CC BY 4.0，字体 SIL OFL 1.1，代码 MIT；
- 项目主页：<https://fontawesome.com/>；
- 许可说明：<https://fontawesome.com/license/free>；
- 版权：Copyright 2023 Fonticons, Inc.

---

## 2. 系统组件

| 组件 | 说明 |
| --- | --- |
| Windows 图标字体 | `Segoe Fluent Icons` / `Segoe MDL2 Assets` 为 Windows 系统自带字体，不随包分发 |
| Microsoft Visual C++ 运行库 | PySide6 / Python 官方构建依赖的系统运行库，按微软许可随系统或安装包提供 |

---

## 3. 开发与构建工具（不随发布包分发）

| 工具 | 版本 | 许可 |
| --- | --- | --- |
| pytest | 8.4.2 | MIT |
| pytest-asyncio | 0.26.0 | Apache-2.0 |
| pytest-qt | 4.5.0 | MIT |
| pytest-cov / coverage | 6.3.0 / 7.17.1 | MIT / Apache-2.0 |
| ruff | 0.17.3 | MIT |
| mypy | 1.20.2 | MIT |
| uv | 0.13.7 | MIT / Apache-2.0 |

---

## 4. 生成物许可

QuickLanShare 的生成物（exe、发布目录、文档）归使用者所有，可自由使用与分发。
分发时请：

1. 保留本文件与 `LICENSE`；
2. 保留 Qt / PySide6 的 LGPL 声明与可替换性说明（见 1.1）；
3. 遵守所用第三方组件的许可条款。

---

## 5. 联系与更新

若发现遗漏的第三方组件，请附上组件名称、版本与所在文件，项目维护者会补充到本文件。

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-11-06 | 3.5.4 | 随拨杆移除关闭端更新声明版本 |
| 2026-11-06 | 3.5.3 | 随拨杆小圆点视觉调整更新声明版本 |
| 2026-11-06 | 3.5.2 | 随“关闭 + 四个 IP 刻点”拨杆更新声明版本 |
| 2026-11-06 | 3.5.1 | 随四档开放网段滑块调整更新声明版本 |
| 2026-11-06 | 3.5.0 | 随网段热更新、在线用户、文本编辑与改名更新声明版本 |
| 2026-11-04 | 3.4.0 | 随直接下载、IP 放通与网页控制更新声明版本 |
