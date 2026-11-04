# QuickLanShare v3.4.0 - Copyright © XAF 2026.11

> 面向开发者的项目说明书：架构、模块、接口、配置与维护记录。
> 环境搭建、构建、测试与打包的逐步操作见 [develop-readme.md](develop-readme.md)。

---

## 1. 项目介绍

### 1.1 定位

QuickLanShare 是一个**局域网文件快速传输桌面工具**。桌面端（PySide6）负责启动 HTTP/WebSocket
服务、展示二维码与共享文件；局域网内的手机、平板、其他电脑通过浏览器访问同一服务，完成
上传、下载、打包下载与文字聊天。

### 1.2 背景

v2.x 是纯命令行程序：启动后弹出一个控制台窗口，用户需要自己读地址、开浏览器；关闭窗口会
误以为服务已停止。v3.0 将其改造为桌面应用：

- 主界面完成上传、下载、删除、日志查看；
- 服务在后台线程运行，关闭窗口默认最小化到托盘；
- 默认 24 小时自动关闭，可在设置中改为不关闭；
- 默认不自动打开浏览器，按需打开。

### 1.3 目标 / 非目标

**目标**

- Windows 10 1809+ / Windows 11 x64 上一键运行，目标机器无需 Python；
- 局域网内零安装使用网页端；
- 大文件可靠传输（分块续传、流式下载、流式 ZIP）；
- 配置、日志、数据均在程序目录（不可写时回退 `%LOCALAPPDATA%`）；
- 现代化浅色界面、托盘常驻、单实例、完整日志与崩溃落盘。

**非目标**

- 不做公网穿透、账号体系、云端存储；
- 不做手机原生客户端（网页即客户端）；
- 不接 MySQL 等数据库；
- 不提供 Windows 系统服务；开机自启仅使用当前用户注册表启动项。

---

## 2. 项目概况

### 2.1 当前状态

| 项 | 值 |
| --- | --- |
| 版本 | 3.4.0 |
| 状态 | 可用（本地构建与测试通过，详见 develop-readme） |
| 平台 | Windows 10 1809+ / Windows 11 x64 |
| 入口 | `QuickLanShare.exe`（PyInstaller onedir） |
| 运行环境 | 发布包自带 Python 3.13 与 Qt 6.12 |
| 测试 | 123 个自动化测试，core/services 覆盖率 80% |

### 2.2 目录结构

```text
QuickLanShare/
├─ main.py                       # 入口薄包装
├─ app.ico                       # exe / 窗口 / 托盘图标
├─ pyproject.toml                # PEP 621 + uv + ruff/mypy/pytest
├─ uv.lock / .python-version
├─ src/quicklanshare/
│  ├─ __main__.py                # python -m quicklanshare
│  ├─ app/
│  │  ├─ main.py                 # 唯一启动实现 main()
│  │  └─ single_instance.py      # QLocalServer 单实例
│  ├─ core/
│  │  └─ version.py              # 版本/作者/版权唯一真源
│  ├─ services/
│  │  ├─ config.py               # 服务端运行配置
│  │  ├─ filenames.py            # 文件名清洗、路径校验、Content-Disposition
│  │  ├─ storage.py              # 文件存储、断点续传会话、下载计数
│  │  ├─ chat.py                 # JSONL 聊天记录与旧格式迁移
│  │  ├─ chat_client.py          # 桌面端 WebSocket 文本订阅与重连
│  │  ├─ autostart.py            # 开机自启注册表项（含静默参数）
│  │  ├─ access.py               # IPv4 放通范围计算
│  │  ├─ download_registry.py    # 本地下载记录（已下载/路径）
│  │  ├─ filestream.py           # 大文件流式下载 / Range
│  │  ├─ zipstream.py            # 线程 + 队列流式 ZIP
│  │  ├─ server.py               # 路由、中间件、WebSocket、生命周期
│  │  ├─ local_client.py         # 桌面端 HTTP 客户端（文件 + 文本）
│  │  └─ runtime.py              # 后台 asyncio 线程托管
│  ├─ ui/
│  │  ├─ theme.py                # 浅色主题与 QSS
│  │  ├─ icons.py                # Windows 图标字体与 app.ico
│  │  ├─ widgets.py              # 拖拽区、骨架屏、文件表、日志面板
│  │  ├─ text_panel.py           # 文本共享消息流与输入框
│  │  ├─ connection_popup.py     # 二维码 / 连接信息弹层
│  │  ├─ qr_overlay.py           # 小二维码、悬停预览、居中遮罩
│  │  ├─ logs_drawer.py          # 底部日志抽屉
│  │  ├─ backend.py              # 服务/传输/文本的 Qt 信号桥
│  │  ├─ main_window.py          # 双栏工作台与窗口生命周期
│  │  ├─ settings_dialog.py      # 设置
│  │  └─ about_dialog.py         # 关于
│  ├─ utils/
│  │  ├─ app_config.py           # config.json 读写、校验、迁移
│  │  ├─ logging_setup.py        # 日志、崩溃落盘、faulthandler
│  │  ├─ paths.py                # 开发态/冻结态路径
│  │  ├─ downloads.py            # Windows 已知“下载”目录解析
│  │  ├─ net.py                  # 本机 IP、Host 白名单、管理员检测
│  │  ├─ qr.py                   # 二维码 data URI
│  │  └─ format.py               # 尺寸/时间格式化
│  └─ resources/
├─ client/                       # 网页客户端（HTML/CSS/JS + Font Awesome）
├─ tests/                        # pytest + pytest-qt
├─ scripts/
│  ├─ build.ps1                  # 一键构建发布包
│  ├─ run.ps1                    # 开发态启动
│  ├─ gen_version_info.py        # 生成 exe 版本资源
│  ├─ sync_version.py            # 同步版权年月、VERSION.txt、文档标题
│  └─ verify_version.py          # 版本一致性校验
├─ docs/
│  ├─ readme.md                  # 本文件
│  ├─ develop-readme.md          # 开发手册
│  └─ images/                    # 界面截图（主界面、日志抽屉、连接弹层）
├─ config/ logs/                 # 运行时目录（随 exe 同级）
├─ VERSION.txt
├─ THIRD-PARTY-NOTICES.md
└─ LICENSE
```

运行时还会在上传后生成 `uploads/`、`chat/`、`state/`。

### 2.3 架构

```text
┌──────────────────────────── Qt 主线程 ────────────────────────────┐
│  MainWindow（文件面板 + 文本面板 + 日志抽屉 + 弹层） / Tray        │
│    │ Signals (queued)                                             │
│    ▼                                                              │
│  Backend (QObject)  ── ServerRuntime ── 后台线程（asyncio loop）  │
│    │  upload/download/delete     │   FileTransferServer (aiohttp) │
│    │  chat send/history/delete   │   ├─ FileStore / ChatStore     │
│    │  via LocalShareClient       │   ├─ filestream / zipstream    │
│    │  → 127.0.0.1:port           │   └─ /api/*、/ws、/client/*   │
│    │  ChatSocketClient ── /ws 订阅 ── ChatStore 广播              │
│    ▼                                                              │
│  UI 更新（进度、文件列表、文本消息、日志）                        │
└───────────────────────────────────────────────────────────────────┘
```

- **服务端**运行在独立线程的 asyncio 事件循环中；
- **界面**不直接操作服务端对象，文件与文本操作都走本机 HTTP / WebSocket；
- **文本**通过 `ChatSocketClient` 订阅 `/ws`，与网页端共用同一个聊天室；
- **日志**通过 `logging.Handler` → Qt 信号回传，跨线程自动排队；
- **传输进度**由后端协程直接发 Qt 信号，主线程只负责渲染。

### 2.4 模块职责

| 模块 | 职责 |
| --- | --- |
| `app.main` | 参数解析、QApplication、配置/日志初始化、单实例、创建窗口 |
| `app.single_instance` | `QLocalServer`/`QLocalSocket` 单实例与第二次启动激活 |
| `core.version` | 版本、作者、版权年月唯一真源 |
| `services.server` | aiohttp 应用、路由、安全中间件、WebSocket、自动关闭 |
| `services.storage` | 原子上传、断点续传、重名编号、下载计数、磁盘空间检查 |
| `services.chat` | 按天 JSONL 聊天记录、删除重写、旧格式迁移 |
| `services.chat_client` | 桌面端 `/ws` 订阅、断线重连、状态回调 |
| `services.autostart` | 当前用户开机自启注册表项、静默参数 |
| `services.access` | IPv4 前几段匹配、回环地址放行 |
| `services.download_registry` | 本地下载记录、路径校验、原子写 |
| `services.runtime` | 后台事件循环线程、任务提交、启停回调 |
| `services.local_client` | 桌面端 HTTP 客户端（分块上传、流式下载、ZIP、文本） |
| `ui.backend` | Qt 信号桥、任务状态管理、文本订阅装配 |
| `ui.main_window` | 双栏布局、文件勾选/状态、交互、托盘、退出 |
| `ui.text_panel` | 文本消息流、输入框、同步状态、断线补拉 |
| `ui.qr_overlay` | 顶部小二维码、悬停放大、居中大图遮罩 |
| `ui.connection_popup` | 二维码、局域网/本机地址、复制与打开网页 |
| `ui.logs_drawer` | 底部日志抽屉的动画与定位 |
| `ui.widgets` | 可复用控件，含骨架屏、拖拽区、文件表、日志面板 |
| `utils.app_config` | `config/config.json` 原子读写、`.bak`、`.corrupt` 回退 |
| `utils.downloads` | Windows 已知“下载”目录解析、自定义目录回退 |
| `utils.logging_setup` | 时间戳日志、大小轮转、清理、异常钩子 |

### 2.5 数据流

1. **上传**：拖拽 → `Backend.upload_paths` → `LocalShareClient.upload_file` →
   `/api/upload/init` → 8 MiB 分片 `PUT` → `/api/upload/complete` → 刷新文件列表。
2. **下载**：文件行「下载」→ 默认目录取 Windows 已知“下载”或设置中的自定义目录 →
   直接生成不重复目标路径 → `/api/download/{name}` 流式写入 `.part` → 完成后原子改名 → 记录本地路径。
3. **自动关闭**：服务器协程到点 → 广播 `server_shutdown` → 停止监听 → 运行时线程退出 →
   `Backend.stopped("auto-shutdown")` → 主窗口退出程序。
4. **文本**：桌面端输入 → `POST /api/chat/send` → 服务端写入 JSONL 并广播 →
   `ChatSocketClient` 收到 `chat_message` → `TextPanel` 追加；网页端消息同理。
5. **配置变更**：设置对话框 → `AppConfig` → `save_config`（临时文件 + `os.replace`）→
   自动关闭即时应用，端口变更在重启服务后生效。

### 2.6 关键接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/` | 网页客户端 |
| GET | `/api/room-info` | 地址、二维码、统计、版本、版权 |
| GET | `/api/files` | 文件列表 |
| POST | `/api/upload` | 单体 multipart 上传 |
| POST | `/api/upload/init` | 初始化/续传会话（按名称+大小+mtime+nonce 指纹） |
| PUT | `/api/upload/chunk/{id}?offset=` | 上传分片 |
| POST | `/api/upload/complete/{id}` | 完成并原子落盘 |
| DELETE | `/api/upload/{id}` | 取消上传 |
| GET | `/api/download/{name}` | 下载（支持 Range） |
| DELETE | `/api/delete/{name}` | 删除文件 |
| POST | `/api/batch-delete` | 批量删除 |
| POST | `/api/zip-download` | 流式 ZIP 打包 |
| GET | `/api/chat/history` | 最近聊天 |
| POST | `/api/chat/send` | 发送消息 |
| DELETE | `/api/chat/message/{id}` | 删除消息 |
| GET | `/ws` | WebSocket 聊天与关闭通知 |
| GET | `/api/auto-shutdown/status` | 自动关闭状态 |
| POST | `/api/auto-shutdown/extend` | 延长时间（仅本机） |
| POST | `/api/shutdown` | 立即关闭服务（需 `confirm`，仅本机） |

> 错误响应统一为 `{"error": "..."}`；上传冲突返回 409 与当前 `offset`。
> 所有请求在 Host/Origin 校验前还会检查 IPv4 放通范围；`/api/room-info` 返回
> `local_client` 供网页决定是否显示关闭控制。

### 2.7 依赖

| 组件 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.13.11 | 运行时（发布包内置） |
| PySide6 | 6.12.0 | Qt Widgets 界面 |
| aiohttp | 3.14.5 | HTTP / WebSocket 服务 |
| aiofiles | 24.1.0 | 异步文件读写 |
| qrcode / Pillow | 8.2 / 11.3.0 | 二维码生成 |
| PyInstaller | 6.22.3 | 打包（开发依赖） |

完整锁定版本见 `uv.lock`，许可见 [THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md)。

---

## 3. 使用方法

### 3.1 安装 / 启动

```powershell
# 开发态
uv sync --frozen
uv run python main.py

# 或使用脚本
pwsh -File scripts/run.ps1
```

发布包解压后直接双击 `QuickLanShare.exe`，无需安装。

### 3.2 配置

配置文件位于 **exe 同级** `config/config.json`；目录不可写时回退到
`%LOCALAPPDATA%\QuickLanShare\config\config.json`，界面会显示提示。

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `schema_version` | 1 | 配置结构版本，用于迁移 |
| `window.width/height/x/y/maximized` | 1200×800 | 窗口几何 |
| `server.host` | `0.0.0.0` | 监听地址 |
| `server.port` | 8888 | 监听端口，占用时自动顺延 |
| `server.auto_shutdown_enabled` | `true` | 是否启用自动关闭 |
| `server.auto_shutdown_hours` | 24.0 | 自动关闭时长（0.1～720） |
| `server.open_browser` | `false` | 启动后是否自动打开网页 |
| `ui.close_to_tray` | `true` | 关闭窗口是否最小化到托盘 |
| `ui.tray_hint_shown` | `false` | 是否已展示首次托盘提示 |
| `ui.log_level` | `INFO` | 日志级别 |
| `ui.column_widths` | `[76,108,48,72,104]` | 文件表固定列宽 |
| `ui.autostart` | `false` | 是否开机自启 |
| `ui.autostart_silent` | `false` | 开机自启时是否静默（只在托盘） |
| `ui.download_dir` | 空 | 自定义默认下载目录；空表示自动跟随系统“下载” |
| `server.ip_scope` | `last1` | IPv4 放通范围：last1/last2/last3/all |

损坏的配置会被改名为 `config.json.corrupt` 并回退默认值；每次保存前保留 `config.json.bak`。

### 3.3 常见任务

| 任务 | 入口 |
| --- | --- |
| 上传文件 | 拖拽到窗口 / 点击上传区 / 「选择文件」（默认打开桌面） |
| 勾选文件 | 文件前复选框；工具栏「全选」选择当前列表全部 |
| 下载文件 | 文件行下载图标，或双击行；直接保存到默认目录 |
| 打包下载 | 勾选文件后「打包下载」；直接保存到默认目录 |
| 删除文件 | 文件行删除图标 /「删除所选」（作用于勾选项） |
| 查看下载状态 | 「状态」列 / 工具栏统计 |
| 打开下载位置 | 「操作」列删除图标右侧的文件夹图标 |
| 改默认下载位置 | 设置 →「下载」→「默认下载位置」；「恢复默认」跟随系统 |
| IP 放通范围 | 设置 →「访问控制」；默认同一网段，修改后重启服务 |
| 发送文本 | 右侧输入框，Enter 或「发送」 |
| 复制/删除文本 | 消息右键菜单，或双击复制 |
| 打开网页 | 右上角「打开网页」 |
| 查看二维码 | 点击地址旁小二维码（悬停放大、点击居中） |
| 查看日志 | 底部状态栏「日志」打开抽屉；「打开目录」定位文件 |
| 开机自启 | 设置 →「启动」→「开机自启」；可再开「静默自启」 |
| 改设置 | 右上角齿轮 |
| 退出 | 托盘菜单或「⋯」菜单「退出程序」；关闭窗口（未启用托盘时） |

### 3.4 开发与构建入口

详见 [develop-readme.md](develop-readme.md)：`uv sync`、`pytest`、`ruff`、`mypy`、
`scripts/build.ps1`、发布目录与校验。

---

## 4. 更新记录

| 日期 | 版本 | 新增 | 修复 | 破坏性变更 / 迁移 |
| --- | --- | --- | --- | --- |
| 2026-11-04 | 3.4.0 | 下载直接保存、25 GB 单文件、IPv4 放通范围、本机网页保留关闭控制、数据目录打开 uploads、选择文件默认桌面 | 含空格文件名定位、数值列对齐 | 新增 `server.ip_scope`，默认 last1；下载不再弹保存框 |
| 2026-11-04 | 3.3.0 | 默认下载位置跟随当前用户“下载”，支持重定向到 D 盘等；设置中可修改/恢复默认 | — | 新增 `ui.download_dir`，默认空自动跟随系统 |
| 2026-11-04 | 3.2.2 | — | 状态列文字与表头居中对齐 | 无 |
| 2026-11-04 | 3.2.1 | — | 二维码 tooltip 遮挡、连接弹层黑底、文件夹图标位置调整 | 无 |
| 2026-11-04 | 3.2.0 | 文件复选框/全选、下载状态与筛选、打开下载文件夹、下载记录持久化；地址旁小二维码与居中遮罩；开机自启/静默自启 | 二维码弹层四角黑点、表格时间截断、设置对话框超出屏幕 | 新增 `ui.autostart`/`autostart_silent` 配置；默认关闭，旧配置沿用 |
| 2026-11-04 | 3.1.0 | 双栏工作台、桌面文本共享（与网页端实时同步）、底部日志抽屉、连接信息弹层、文件操作图标化 | 标题重复、自动关闭信息多处重复、传输任务挤压文件列表 | 布局与操作位置变化；配置字段不变，旧配置可直接沿用 |
| 2026-11-04 | 3.0.0 | PySide6 桌面 UI、拖拽上传、应用内下载、日志面板、托盘、单实例、24 小时自动关闭（可关闭）、启动打开网页开关 | 访问日志刷屏、自动关闭默认时长、网页版权显示 | 移除命令行参数；目录改为 `src` 布局；日志目录改为 `logs/`；配置升级为 `config/config.json`（v2 无配置，首次启动自动生成） |

---

## 5. 项目日志

### 5.1 里程碑

- 2026-10：v2.2 安全与可靠性重构（大文件下载、流式 ZIP、聊天持久化）。
- 2026-11-04：v3.0 完成桌面化改造，首次提供 GUI 发布包。
- 2026-11-04：v3.1 重构为「文件 + 文本」双栏工作台，桌面端补齐文本共享。
- 2026-11-04：v3.2 补齐文件勾选/下载状态、二维码交互与开机自启。

### 5.2 重要决策

- 保留原有 aiohttp 服务与网页客户端，新增桌面壳，避免重写传输核心；
- 桌面端文件操作统一走本机 HTTP API，不跨线程直接操作服务端对象；
- 服务端跑在独立线程的事件循环中，界面只通过 Qt 信号接收结果；
- 默认 24 小时自动关闭，符合“临时共享”主场景；长期共享由用户显式关闭；
- 默认不自动打开浏览器，避免打断用户；
- 日志仍按文件落盘，UI 日志是 `logging` 的镜像，不另建一套；
- v3.1 采用「左侧文件 + 右侧文本」双栏：文本是高频协作功能，常驻比二级页面更合适；
- 文本复用服务端 `ChatStore` 与 `/ws`：桌面端只做订阅，发送走 HTTP，避免两套数据；
- 运行状态、自动关闭、地址只保留一处（状态栏/顶部胶囊），减少重复信息；
- 下载状态独立保存到 `state/downloads.json`，不影响服务端共享文件；
- 开机自启只写当前用户 Run 键，默认关闭；静默参数只影响注册表启动，不影响双击。

### 5.3 风险与待办

- 未签名 exe 可能触发 SmartScreen / 杀毒误报；
- 多网卡环境下自动选择的局域网 IP 可能不是用户期望的那张网卡；
- 1080p 以下小屏（如 1366×768）下界面较紧凑，需进一步验证 125%/150% 缩放；
- 托盘在部分精简系统不可用，程序会退化为“关闭即退出”；
- 后续可增加：传输速度限制、文件预览、深色主题、文本附件。

---

## 6. 问题与踩坑

| 现象 | 影响 | 根因 | 处理 | 验证 |
| --- | --- | --- | --- | --- |
| 网页端刷新时日志面板被访问日志刷屏 | 难以看到业务日志 | `AppRunner` 访问日志经包级 logger 冒泡到 UI | 将 `quicklanshare.access` 默认级别设为 WARNING | 界面日志只显示启动/上传/下载等业务行 |
| 关闭窗口后误以为程序退出 | 服务仍在运行 | 托盘常驻设计 | 首次关闭时托盘气泡提示，并写入 `tray_hint_shown` | 手动关闭窗口验证 |
| 打包后 Qt 平台插件缺失 | exe 无法启动 | PyInstaller 未收集插件 | `build.ps1` 检查 `_internal/PySide6/plugins/platforms/qwindows.dll`，失败即报错 | 构建时检查 |
| 旧命令行参数无法使用 | 老用户脚本失效 | v3 改为 GUI 优先 | 文档标注破坏性变更；需要自动化时用 HTTP API | 阅读接口文档 |
| 配置写坏后程序崩溃 | 无法启动 | 直接 `json.load` | 原子写 + `.bak` + `.corrupt` 回退 | 单元测试覆盖 |
| 自动关闭时间修改后不生效 | 用户困惑 | 只在启动时读取配置 | 保存设置后即时调用 `update_auto_shutdown` | UI 测试与手动验证 |
| 文本气泡过窄、长句频繁换行 | 阅读体验差 | 气泡最大宽度在布局完成前按 0 宽度计算 | 布局完成后按滚动区宽度重算 min/max 宽度 | 新截图与手动查看 |
| 日志抽屉遮住底部状态栏 | 无法边看日志边操作 | 抽屉定位按窗口底边计算 | 目标位置预留状态栏高度（42px） | 截图确认 |
| 消息重复显示 | 同一条出现两次 | HTTP 返回与 WebSocket 广播都会送回消息 | 界面按消息 id 去重 | 单元/集成测试 |
| 文件勾选后批量操作不生效 | 无法删除/打包 | 表格行选择与复选框是两套状态 | 批量操作统一读取复选框集合，全选同步可见行 | UI 测试 |
| 二维码弹层四角出现黑点 | 视觉瑕疵 | 顶层 QFrame 圆角外区域未透明 | 弹层设置 `WA_TranslucentBackground`，圆角外透明 | 截图确认 |
| 设置对话框超过屏幕高度 | 底部按钮够不到 | 新增启动设置后固定高度过高 | 内容放入滚动区，底部按钮固定 | 580×680 截图确认 |

---

## 7. 注意事项

- **兼容性**：仅支持 Windows 10 1809+ / 11 x64；Qt6 不支持 Windows 7。
- **权限**：普通用户即可；不要安装到需要管理员写入的目录，否则配置/日志会回退到 `%LOCALAPPDATA%`。
- **数据存储**：`uploads/` 为共享文件；删除文件不可恢复；`state/` 保存断点与下载计数。
- **安全**：服务监听 `0.0.0.0`，同一局域网内可访问；不要在不可信公共网络长期开启。
- **升级**：覆盖 exe 与 `_internal/` 即可；`config/`、`uploads/`、`chat/`、`state/`、`logs/` 保留。
- **回滚**：保留上一版本整个目录；配置 schema 目前只有 v1。

---

## 8. 重要说明

### 8.1 已知限制

- 未实现 HTTPS 的界面配置项（服务端仍支持通过 `Config` 传入证书，供二次开发）；
- 文本共享为单行、最多 500 字，不支持富文本/附件；与网页端限制一致；
- 桌面端不提供拖拽“下载到指定文件夹”的批量队列，逐个下载或 ZIP 打包；
- 单实例按当前 Windows 用户隔离，多用户同时登录会各自运行。

### 8.2 免责声明

本软件按现状提供，使用前请自行评估局域网安全与数据重要性；因误删、网络中断或未签名
可执行文件导致的问题，作者不承担直接或间接责任。

### 8.3 参考资料

- aiohttp 文档：<https://docs.aiohttp.org/>
- PySide6 文档：<https://doc.qt.io/qtforpython-6/>
- PyInstaller 文档：<https://pyinstaller.org/>
- Qt 许可：<https://www.qt.io/licensing>

---

## 修订记录

| 日期 | 版本号 | 说明 |
| --- | --- | --- |
| 2026-11-04 | 3.4.0 | 直接下载、25 GB、IP 放通范围、本机网页控制、文件定位与表格对齐 |
| 2026-11-04 | 3.3.0 | 默认下载目录改为跟随 Windows 已知“下载”，支持 D 盘重定向并可配置 |
| 2026-11-04 | 3.2.2 | 状态列文字居中 |
| 2026-11-04 | 3.2.1 | 修复二维码 tooltip 遮挡、连接弹层黑底，调整文件夹图标位置 |
| 2026-11-04 | 3.2.0 | 补充文件勾选/下载状态、二维码交互、开机自启的设计与踩坑 |
| 2026-11-04 | 3.1.0 | 重构为双栏工作台，补充文本共享、连接弹层、日志抽屉与相应接口/踩坑记录 |
| 2026-11-04 | 3.0.0 | 新建项目说明书，记录桌面化架构、接口、配置与踩坑 |
