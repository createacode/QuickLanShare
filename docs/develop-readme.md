# QuickLanShare v3.5.4 - Copyright © XAF 2026.11

> 面向开发者的完整开发手册：环境、构建、测试、架构、打包、踩坑与排错。
> 项目定位与接口概览见 [readme.md](readme.md)。

---

## 1. 环境与依赖

### 1.1 开发机要求

| 项 | 本次验证环境 |
| --- | --- |
| 操作系统 | Windows（x64），构建目标 Windows 10 1809+ / 11 |
| Python | 3.13.11（`.python-version` 固定 3.13） |
| 包管理 | uv 0.13.7 |
| 虚拟环境 | 项目内 `.venv`（uv 自动创建） |
| 界面 | PySide6 6.12.0（Qt 6.12） |
| HTTP | aiohttp 3.14.5 |
| 打包 | PyInstaller 6.22.3 |
| 测试 | pytest 8.4.2、pytest-asyncio 0.26.0、pytest-qt 4.5.0、coverage 7.17.1 |
| 静态检查 | ruff 0.17.3、mypy 1.20.2 |

> 不需要 Inno Setup：本次交付形态为便携目录 + ZIP，验收前未要求生成安装包。
> 若后续需要安装包，按 `docs/develop/parts/final-release-inno.md` 另做。

### 1.2 首次安装

在项目根目录（含 `pyproject.toml`）执行：

```powershell
uv sync --frozen
```

说明：

- `--frozen` 保证严格使用 `uv.lock`，不会临时升级；
- 不要求也不允许全局 `pip install`；
- 依赖包含开发依赖（`[dependency-groups].dev`），因为构建与测试需要 PyInstaller、pytest、ruff、mypy。

### 1.3 运行

```powershell
uv run python main.py
# 或
uv run python -m quicklanshare
# 或
pwsh -File scripts/run.ps1
```

调试日志：

```powershell
uv run python main.py --debug
```

支持的启动参数只有两个（v3 起不再保留 v2 的一长串 CLI 参数）：

| 参数 | 说明 |
| --- | --- |
| `--version` | 输出名称与版本后退出 |
| `--debug` | 本次运行把日志级别设为 DEBUG（不写入配置） |
| `--config PATH` | 使用指定配置文件（排错/多环境用） |

其余行为全部通过界面「设置」或 `config/config.json` 调整。

---

## 2. 目录与架构

### 2.1 分层

```text
src/quicklanshare/
├─ app/        启动、单实例
├─ core/       版本真源
├─ services/   服务器、存储、聊天、流式传输、本地客户端、后台运行时
├─ ui/         窗口、控件、主题、Qt 信号桥
└─ utils/      配置、日志、路径、网络、二维码、格式化
```

规则：

- 依赖方向：`ui → services → utils → core`，`app` 可以依赖所有层；
- `services` 不导入 PySide6，保证可独立测试；
- `utils` 不导入界面与服务端业务对象；
- 入口只有 `app.main:main`，根 `main.py` 与 `__main__.py` 仅转发。

### 2.2 启动链路

```text
main.py
└─ quicklanshare.app.main.main()
   ├─ argparse（--version/--debug/--config）
   ├─ QGuiApplication.setHighDpiScaleFactorRoundingPolicy(PassThrough)
   ├─ QApplication + 应用名/组织名 + 退出策略(不随最后窗口退出)
   ├─ qInstallMessageHandler → logging
   ├─ theme.apply_theme()
   ├─ utils.app_config.load_config()
   ├─ utils.logging_setup.setup_logging(data/logs)
   ├─ install_crash_handlers()（excepthook / threading.excepthook / faulthandler）
   ├─ SingleInstanceGuard.acquire()
   ├─ MainWindow(...) → show()
   └─ app.exec()
```

`MainWindow` 构造完成后用 `QTimer.singleShot(80, start_server)` 启动服务，避免阻塞首帧绘制。

### 2.3 线程模型

```text
主线程（Qt）
  MainWindow / Backend(QObject) / 定时器
        │  ServerRuntime.submit(coro)
        ▼
后台线程 qls-server
  asyncio event loop
    ├─ FileTransferServer（aiohttp）
    ├─ LocalShareClient 请求（通过 127.0.0.1）
    └─ 自动关闭协程

回调路径：后台线程 emit Qt Signal → 主线程槽（AutoConnection 自动排队）
```

关键点：

- **禁止**在界面线程直接调用 `FileStore` / `ChatStore` 或 aiohttp 对象；
- `Backend` 只暴露 Qt 信号与“提交任务”的方法；
- 停止服务通过 `loop.call_soon_threadsafe(server.request_stop, reason)`，避免跨线程调用 `asyncio.Event.set`；
- 退出时 `ServerRuntime` 取消剩余任务、关闭事件循环，防止 asyncio 警告。

---

## 3. 界面实现

### 3.1 布局

```text
MainWindow
├─ Header（logo、品牌/版本、状态胶囊、地址胶囊、打开网页、电源、设置、更多）
├─ Body（QSplitter 水平）
│  ├─ 左：DropZone（紧凑）→ TransferPanel（限高）→ 文件卡片（骨架屏/表格/空状态）
│  └─ 右：TextPanel（标题/同步状态 → 消息流/空状态 → 输入框）
├─ StatusBar（数据目录 · 在线人数 · 自动关闭倒计时 · 日志）
├─ LogsDrawer（覆盖在底部，滑出/收起）
└─ ConnectionPopup（二维码 / 局域网地址 / 本机地址 / 复制 / 打开网页）
```

- 默认 1200×800，最小 900×480；高 DPI 或小屏时窗口尺寸按可用屏幕夹紧；
- 顶部只保留一条状态信息，自动关闭只在状态栏出现一次；
- 文件区占 62%，文本区占 38%（最小 330px）；`QSplitter` 可拖动调整；
- 日志默认隐藏，点击状态栏「日志」滑出，`Esc` 或「关闭」收起。

### 3.2 主题

- 文件：`ui/theme.py`
- 风格：浅色、白卡片、10～14 px 圆角、`#F4F7FB` 背景、`#2563EB` 强调色；
- 字体：优先 `Microsoft YaHei UI`，回退 `Microsoft YaHei` / `Segoe UI`；
- 次要文字使用 `#475569` / `#8494AC`，正文对比度 ≥ 4.5:1；
- 阴影只用于文件卡片、文本卡片、弹层与抽屉，顶部/状态栏保持扁平；
- 组件状态：hover / pressed / disabled / focus 全部有样式；
- 图标：Windows 自带 `Segoe Fluent Icons` / `Segoe MDL2 Assets`，通过 `ui/icons.py` 渲染为 QIcon；电源、下载、删除等图标全部来自同一套字形。

> 不要修改 Qt 高 DPI 策略。Qt 6 默认启用高 DPI，程序只设置
> `PassThrough` 舍入策略，保证 100%～200% 缩放清晰。

### 3.3 骨架屏与状态

- `SkeletonList` 在首次加载文件时显示，形状模拟文件行；
- 数据返回后至少展示 450 ms，再平滑切换到表格/空状态（`QGraphicsOpacityEffect` 淡入）；
- 加载失败显示错误状态与「重试」；
- 服务停止/启动失败也有独立空状态与操作按钮。

### 3.4 拖拽上传

- `DropZone(compact=True)` 是 78～92px 高的横向上传条，整条可点击、可拖拽；
- 支持拖入文件与文件夹；文件夹递归展开（最多交给系统遍历）；
- 主窗口本身也接受拖拽，拖到表格/日志区域同样触发上传；
- 上传中显示每个文件的进度行，支持取消；传输面板限高 168px，可滚动；
- 全部完成后保留 6 秒再自动收起，避免长期挤占文件列表。

### 3.5 文本共享

- 组件：`ui/text_panel.py`，右侧常驻；与网页端共用服务端聊天室；
- 订阅：`services/chat_client.py` 连接 `/ws`，收到 `welcome`（历史）、`chat_message`、`edit_message`、`delete_message`、`delete_messages`、`profile_updated`、`ip_scope_changed`、`server_shutdown`；
- 发送：`POST /api/chat/send`，返回消息 id；WebSocket 广播与 HTTP 返回按 id 去重；
- 自己的消息：`client_ip` 为 `127.0.0.1` / `::1` 时靠右显示「我」，其他设备显示当前昵称；
- 改名：桌面端标题栏「改名」与网页端「改名」共用 `POST /api/profile/name`，服务端按 IP 持久化；
- 删除/编辑：右键中文菜单支持复制、编辑、单条删除；「管理」模式勾选后批量删除；
- 复制：气泡和文字区共用中文菜单；文字支持鼠标选中，`Ctrl+C` 复制选中内容，未选中时复制整条；
- 断线：状态显示「重连中」，按 1.5s→15s 退避重连；重连期间每 4 秒用 `/api/chat/history` 补拉；
- 输入：单行、500 字、Enter 发送；空内容或服务停止时禁用；发送后与新消息到达时自动滚到底部；
- 显示：日期分隔、消息气泡；向上滚动时新消息只显示「有新消息 ↓」，发送自己的消息仍强制跳底。

### 3.6 托盘与关闭

- `QSystemTrayIcon` 菜单：显示主界面 / 打开网页 / 退出程序；
- 关闭窗口：`ui.close_to_tray=true` 时隐藏到托盘，首次提示并持久化 `tray_hint_shown`；
- 托盘不可用：退化为关闭即退出；
- 退出前若有传输任务，二次确认；停止服务超过 6 秒强制退出（记录警告）。

### 3.7 自动关闭显示

- `Backend.started` 携带服务端截止时间；
- 状态栏每秒刷新「自动关闭 HH:MM:SS」，剩余 ≤5 分钟变红；关闭自动关闭时显示「不自动关闭」；
- 设置修改后 `Backend.apply_auto_shutdown` 即时调用服务端
  `configure_auto_shutdown`，返回新截止时间后刷新；
- 自动关闭信息只出现在状态栏，顶部/文件区不再重复。

### 3.8 文件勾选与下载状态

- 表格列：复选框 / 文件名 / 大小 / 修改时间 / 下载次数 / 状态 / 操作；
- 复选框使用真实 `QCheckBox` cell widget（不是 item check state），保证未选中时也有可见方框；
- 工具栏「全选」使用 `QCheckBox` 三态：全选、部分、未选；只作用于当前列表；
- 删除所选、打包下载都只读取 `FileTable.checked_names()`；未勾选时按钮禁用；
- 状态由 `services/download_registry.py` 持久化到 `state/downloads.json`：
  - 下载开始：状态「下载中」；
  - 下载完成：记录文件名与本地路径，状态「已下载」；
  - 其它：「未下载」；
  - 已下载且文件仍存在时，「操作」列删除按钮右侧显示文件夹按钮，点击 `explorer /select,"<path>"` 定位文件（路径整体加引号，兼容空格）；
- 统计显示「已下载 X · 下载中 Y · 未下载 Z」；不再提供筛选下拉框；
- 下载记录损坏时改名 `.corrupt` 并忽略；文件被移动/删除后加载时自动丢弃记录。

### 3.9 二维码交互

- 地址胶囊后是 22px 小二维码（`QrButton`，固定 30×30，不增加顶栏高度）；
- 悬停：`QrPeek` 浮层显示 180px 二维码，移出即收起；
- 点击：`QrOverlay` 覆盖整个窗口，半透明深色遮罩（`rgba(15,23,42,115)`），
  卡片居中显示 252px 二维码、地址与提示；点击卡片外任意区域或 Esc 恢复；
- 地址胶囊仍可打开完整的「连接信息」弹层；弹层设置 `WA_TranslucentBackground`，
  并在 `paintEvent` 中自绘圆角白底/描边，避免 Windows 上透明顶层出现整块黑底；
  顶层不再使用 `QGraphicsDropShadowEffect`。

### 3.10 开机自启与静默启动

- 默认关闭；配置 `ui.autostart` 与 `ui.autostart_silent` 初始均为 `false`；
- 设置 →「启动」：打开「开机自启」后才显示「静默自启」；
- 实现：`services/autostart.py` 写
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\QuickLanShare`：
  - 冻结态：`"<exe>" "--autostart" ["--silent"]`；
  - 开发态：`"<pythonw.exe>" "<main.py>" "--autostart" ["--silent"]`；
- 启动参数：
  - `--autostart`：由注册表启动；
  - `--silent`：不显示主界面，只保留托盘；
- 判定：`start_hidden = args.silent or (args.autostart and config.ui.autostart_silent)`；
  - 托盘可用：不调用 `window.show()`，服务照常启动，托盘气泡提示后台运行；
  - 托盘不可用：降级为显示主界面并记录警告；
- **双击 exe 不带参数，始终显示主界面**，不受静默设置影响；已有实例时第二次启动
  通过单实例激活显示窗口；
- 关闭「开机自启」会删除注册表值；注册表写入失败时设置回退为关闭并提示。

### 3.11 默认下载目录

- `utils/downloads.py`：
  - 首选 `QStandardPaths.DownloadLocation`（Windows `SHGetKnownFolderPath(FOLDERID_Downloads)`），
    能识别被重定向到 D 盘或其他位置的“下载”；
  - Qt 为空时读注册表 `User Shell Folders` / `Shell Folders` 的 Downloads GUID；
  - 最后回退 `~/Downloads`，再回退用户主目录；
- `ui.download_dir` 默认空：每次下载时动态跟随系统“下载”；
- 设置 →「下载」：显示当前实际路径，可「更改…」到其他目录，「恢复默认」清空自定义值；
- 自定义目录无效（不存在/被删除）时 `resolve_download_dir` 回退系统“下载”；
- 本机实测“下载”位于 `D:\Desktop\Downloads`，程序能正确识别；
- 下载/打包不再弹保存框：`unique_download_path` 直接生成不重复路径（`文件 (1).ext`）；
- 「选择文件」默认目录用 `QStandardPaths.DesktopLocation`，同样支持桌面重定向；
- 「数据目录」按钮打开 `data_dir/uploads`，而不是数据根目录。

### 3.12 IPv4 放通范围与本机网页控制

- `services/access.py` 使用 0-15 位图表示四段开放状态：位 0=第 1 段，位 3=第 4 段；
  只接受四档连续预设：`last1`（同段）、`last2`（后 2 段）、`last3`（后 3 段）、
  `all`（全部开放，默认）；不再接受任意段组合；
- 桌面端顶部「打开网页」左侧是 `ui/scope_control.py` 的 `NetworkScopeControl`：
  四个刻点从左到右显示本机 IPv4（例：`192/168/1/10`），依次对应
  `192.*.*.*` / `192.168.*.*` / `192.168.1.*` / 全部开放；
  最左侧就是普通 `192` 刻点，没有关闭端；最右侧默认全部开放；
  右上角实时显示当前模式；
- 拨杆支持拖动、方向键、Home/End、滚轮；拖动有 0.58 格吸附迟滞，
  必须拖动圆形小点，松手才提交；窗口宽度 `<1180px` 时自动隐藏；
- 拨杆只管理网段，不负责服务启停：服务启停始终由电源按钮控制；
  服务停止时拨杆仍显示当前选择，切换档位只保存配置，下次启动生效；
- `POST /api/network-scope` 仅本机可调用，参数只接受四个 scope 值，热更新
  `Config.ip_scope`，新请求立即生效；范围收紧时断开已不在范围内的 WebSocket，
  已开始的流式下载允许自然结束；
- 服务端中间件先查 Host，再查 IP 范围；锚点优先使用非回环 Host，否则使用真实局域网 IP，
  避免远端伪造 `Host: 127.0.0.1` 绕过限制；回环 `127.0.0.1` 始终放行；
- 配置 `server.ip_scope` 默认 `all`，设置 →「访问控制」与顶部滑块均可修改，无需重启；
- `/api/room-info` 返回 `ip_scope`（含 `mask/segments/label`）、`online_users` 与 `client_name`；
- 桌面端「打开网页」改为打开 `http://127.0.0.1:<port>`，因此本机网页保持自动关闭控制；
- `/api/shutdown` 与 `/api/auto-shutdown/extend` 服务端也仅允许本机调用，远端即使伪造请求也会 403。
- 单文件上传上限提升到 25 GiB（`max_upload_size`）；ZIP 上限仍为 20 GiB。

---

## 4. 配置

### 4.1 位置与回退

1. 首选：exe 同级 `config/config.json`；开发态为项目根 `config/config.json`；
2. 该目录不可写：`%LOCALAPPDATA%\QuickLanShare\config\config.json`，界面用 toast 与日志提示；
3. 配置损坏：改名为 `config.json.corrupt`，写回默认值，日志记录原因；
4. 每次保存前把旧文件复制为 `config.json.bak`。

### 4.2 写入策略

`utils/app_config.save_config`：

```text
config.json.tmp（写入 + fsync）
→ 旧文件复制为 config.json.bak
→ os.replace(tmp, config.json)
```

### 4.3 校验与迁移

- `schema_version` 当前为 1；
- 读取时逐字段类型校验并夹紧范围（端口 1～65535、自动关闭 0.1～720 小时、窗口最小 1024×700）；
- 非法日志级别回退 `INFO`；
- 未来升级 schema 时，在 `AppConfig.from_dict` 内按版本迁移，禁止直接丢弃用户配置。

### 4.4 与服务端配置的关系

`AppConfig` 只保存用户偏好；`MainWindow._build_server_config()` 将其转换为
`services.config.Config`（数据目录、端口、自动关闭、日志级别）。修改端口需要在设置中
确认“立即重启服务”，否则下次启动生效。

---

## 5. 日志

### 5.1 规格

| 项 | 实现 |
| --- | --- |
| 目录 | exe 同级 `logs/`；不可写回退 `%LOCALAPPDATA%\QuickLanShare\logs` |
| 命名 | `log_YYYYMMDD_HHMMSS_NN.log`（NN 为同秒序号 00～99） |
| 单文件上限 | 10 MB，超出后新开文件（不覆盖旧文件） |
| 保留 | 最近 30 天或最新 100 个文件，启动时清理 |
| 格式 | `时间 [级别] logger: 消息` |
| 崩溃 | `sys.excepthook`、`threading.excepthook`、`faulthandler.log` |
| 界面 | 附加 `_QtLogHandler`，把记录转发到底部日志抽屉；错误时状态栏日志按钮亮红点 |

### 5.2 关键实现

- `SessionFileHandler` 继承 `logging.Handler`，在 `emit` 内检查大小并切换文件；
- `logging.Handler` 自带锁，多线程写入安全；
- 写日志失败只设置 `last_error`，不影响业务；
- 访问日志 `quicklanshare.access` 默认 WARNING，避免刷屏；
- `faulthandler.enable(stream, all_threads=True)`，退出时关闭。

### 5.3 排错用法

```powershell
# 查看最新日志
Get-ChildItem logs\log_*.log | Sort-Object Name -Descending | Select-Object -First 3

# 跟踪日志
Get-Content (Get-ChildItem logs\log_*.log | Sort-Object Name -Descending | Select-Object -First 1).FullName -Wait
```

---

## 6. 自动关闭与浏览器行为

### 6.1 需求

- 默认：启动后 24 小时自动关闭（停止服务并退出程序）；
- 可配置：关闭自动关闭后，服务一直运行，直到用户退出；
- 需要保留 v2 网页端的延长按钮，但上限提升为 720 小时（30 天）；
- 默认不自动打开网页。

### 6.2 服务端

- `Config.auto_shutdown_enabled=True`、`auto_shutdown_hours=24.0`、`auto_shutdown_max_hours=720.0`；
- `enable_auto_shutdown()` 设置截止时间并启动 `_auto_shutdown_worker`；
- 到期调用 `_shutdown_sequence("auto-shutdown")`：广播 WebSocket 通知 → 设置停止事件；
- `disable_auto_shutdown()` 取消任务并清空截止时间；
- `configure_auto_shutdown(enabled, hours)` 供界面即时切换。

### 6.3 界面

- `MainWindow` 收到 `stopped("auto-shutdown")` 时：
  - 不弹“服务已停止”空状态；
  - 提示“已到自动关闭时间，程序即将退出”；
  - 600 ms 后 `QApplication.quit()`。
- 手动停止则保留窗口，按钮变为「启动服务」。

### 6.4 浏览器

- `Config.open_browser=False`；
- 界面设置 `server.open_browser` 控制启动后是否 `QDesktopServices.openUrl`；
- 网页横幅/二维码不受影响。

---

## 7. 传输实现

### 7.1 上传

- 分片 8 MiB（`LocalShareClient.chunk_size`，最小 64 KiB）；
- 指纹：文件名 + 大小 + mtime + `nonce="desktop"`；
- `/api/upload/init` 幂等，返回当前偏移；
- 分片失败重试最多 3 次，重试前重新 init 获取真实偏移；
- 完成后 `/api/upload/complete` 原子改名；
- 0 字节文件走 init + complete，不发送分片。

### 7.2 下载

- 通过 `/api/download/{quote(name)}`，以 1 MiB 块写 `.part`；
- 完成 `os.replace`，取消/失败删除 `.part`；
- 下载计数只在完整 GET（无 Range）时 +1，由服务端负责。

### 7.3 打包下载

- 桌面端调用 `/api/zip-download`，把流写入 `.part`；
- 服务端使用线程 + 有界队列 + `zipfile` 流式压缩，不占用等量临时磁盘；
- 压缩方式默认 `stored`（速度优先），可配置为 `deflate`。

### 7.4 大文件注意事项

- 服务端不使用 `FileResponse`（Windows 下 `TransmitFile` 单次 >2 GiB 会失败），
  改用 1 MiB 手动流式发送；
- 下载与上传都不把整文件读入内存；
- ZIP 使用 ZIP64，支持中文文件名。

---

## 8. 服务端与安全

### 8.1 中间件

1. `_security_middleware`：Host 白名单、Origin/Referer、`Sec-Fetch-Site` 校验；
2. `_error_middleware`：把业务异常映射为 `{"error": ...}` 与合适状态码。

### 8.2 路径安全

`services/filenames.py`：

- 取最后一个路径片段，替换 Windows 非法字符；
- 拒绝 `.`、`..`、NTFS 数据流、设备名（CON/PRN/COM1…）；
- `resolve_upload_path` 再次确认解析结果位于上传目录；
- `Content-Disposition` 使用 RFC 5987，中文文件名兼容。

### 8.3 上传限制

- 单文件 25 GiB（`max_upload_size`）；
- 单分片 32 MiB（`max_chunk_size`）；
- JSON 请求 2 MiB；
- 打包 20 GiB；
- 磁盘剩余空间不足时返回 413。

### 8.4 运行在不可信网络时

- 不要把端口暴露到公网；
- 如需 HTTPS，可在代码中为 `Config` 传入 `ssl_cert` / `ssl_key`（界面暂未暴露）；
- Host 校验默认开启，反向代理需在 `Config.allowed_hosts` 中加域名。

---

## 9. 测试

### 9.1 命令

```powershell
# 全部测试
uv run pytest -q

# 覆盖率（core + services）
uv run pytest --cov=quicklanshare.services --cov=quicklanshare.core --cov-report=term-missing

# 单个文件
uv run pytest -q tests/test_ui.py
```

### 9.2 覆盖范围

| 文件 | 覆盖内容 |
| --- | --- |
| `test_api.py` | 上传/续传/下载/Range/ZIP/聊天/安全头/WebSocket |
| `test_security.py` | 跨站、Host、Origin、路径穿越 |
| `test_paths.py` | 文件名清洗、路径解析、Content-Disposition |
| `test_chat_lifecycle.py` | 聊天持久化、旧格式迁移、自动关闭、手动关闭 |
| `test_lifecycle_extra.py` | 端口占用顺延 |
| `test_filestream.py` | Range 解析 |
| `test_app_config.py` | 默认值、往返保存、备份、损坏回退、范围夹紧 |
| `test_logging_setup.py` | 命名、轮转、清理、非匹配文件 |
| `test_local_client.py` | 上传/下载/ZIP/删除/取消/0 字节/文本收发 |
| `test_chat_client.py` | WebSocket 历史、消息、删除、关闭、异常载荷、重连状态 |
| `test_download_registry.py` | 下载记录持久化、缺失文件清理、损坏回退 |
| `test_downloads.py` | 已知“下载”目录、D 盘自定义目录、目录缺失回退、重名编号 |
| `test_access.py` | IPv4 四种放通范围、回环、IPv4-mapped、配置校验 |
| `test_autostart.py` | 自启命令、注册表写入/删除/失败、静默参数 |
| `test_runtime.py` | 后台启动停止、自动关闭开关、计时到期 |
| `test_ui.py` | 双栏状态、文本发送、文件勾选/状态、二维码、下载目录/直接下载、表格对齐、设置 |

### 9.3 当前结果

- `pytest`：**123 passed**；
- core + services 覆盖率：**80%**（`autostart` 88%、`download_registry` 85%、`chat_client` 85%，其余模块均 ≥73%）；
- GUI 测试使用 `QT_QPA_PLATFORM=offscreen`（`tests/conftest.py`），不弹真实窗口。

> offscreen 平台在 Windows 上可能打印
> `QFontDatabase: Cannot find font directory ...`，这是测试环境的字体告警，
> 不影响断言；真实运行使用系统字体。

### 9.4 测试注意事项

- 使用 `unittest.IsolatedAsyncioTestCase` 的用例与 pytest 共存；
- 服务端测试端口用 0，避免占用；
- 涉及文件系统的用例写在 `tests/` 下临时目录，结束后清理；
- 不再使用 `qls.*` 旧包名。

---

## 10. 代码质量

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

当前基线：

- ruff：通过（`E/F/I/W/B/UP/SIM/RUF`，行宽 100）；
- ruff format：通过；
- mypy：`strict = true`，42 个源文件通过。

类型约定：

- 公共函数/方法必须有注解；
- 使用 `from __future__ import annotations` 与 PEP 604（`str | None`）；
- Qt 回调参数在事件重写中遵循 PySide6 签名；
- `tests/` 不参与 mypy。

---

## 11. 构建与打包

### 11.1 一键构建

```powershell
pwsh -File scripts/build.ps1
```

`build.ps1` 顺序：

1. 检查 `uv` 与 `app.ico`；
2. `uv sync --frozen`；
3. `ruff check`、`ruff format --check`、`mypy`；
4. `pytest` + core/services 覆盖率；
5. `sync_version.py`（版权年月、`VERSION.txt`、文档标题）；
6. `gen_version_info.py`（`scripts/version_info.txt`）；
7. `verify_version.py`（不一致立即失败）；
8. PyInstaller 打包；
9. 检查 `dist/QuickLanShare/QuickLanShare.exe` 与 `qwindows.dll`；
10. 整理 `release/<发布包名>/`，拷贝 README、docs、VERSION、第三方声明、许可；
11. 生成 `SHA256SUMS.txt`；
12. 生成 ZIP（`-NoZip` 可跳过）。

快速出包（不推荐用于发布）：

```powershell
pwsh -File scripts/build.ps1 -SkipTests
```

### 11.2 PyInstaller 参数

```powershell
uv run pyinstaller --noconfirm --clean --windowed --onedir `
  --name QuickLanShare --icon app.ico `
  --version-file scripts/version_info.txt `
  --add-data "app.ico;." --add-data "client;client" `
  --hidden-import aiohttp --hidden-import aiofiles `
  --hidden-import qrcode --hidden-import PIL.Image `
  main.py
```

说明：

- `--windowed` 去掉控制台窗口；
- `--onedir` 便于热替换 Qt DLL，也符合模板要求；
- `--add-data` 的资源会进入 `_internal/`，程序通过 `sys._MEIPASS` 解析；
- PyInstaller 的 PySide6 hook 会收集 Qt 插件，不需要 `windeployqt`；
- Qt 插件检查失败时用 `--collect-all PySide6` 重打（脚本会直接报错并提示）。

### 11.3 发布目录

```text
release/QuickLanShare_v3.4.0_win-x64_YYYYMMDD/
├─ QuickLanShare.exe
├─ _internal/                 # Python、Qt、依赖
├─ README.md
├─ VERSION.txt
├─ THIRD-PARTY-NOTICES.md
├─ LICENSE
├─ SHA256SUMS.txt
├─ docs/readme.md
├─ docs/develop-readme.md
├─ docs/images/               # 界面截图
├─ config/
└─ logs/
```

- 包内不含源码、`.git`、构建中间产物与测试数据；
- `QuickLanShare_v3.4.0_win-x64_YYYYMMDD.zip` 与目录同级。

### 11.4 校验

```powershell
Get-FileHash -Algorithm SHA256 .\QuickLanShare.exe
# 与 SHA256SUMS.txt 中对应行比较
```

全量校验：

```powershell
Get-Content SHA256SUMS.txt | ForEach-Object {
    $hash, $path = $_ -split '  ', 2
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actual -ne $hash) { Write-Host "FAIL $path" } else { Write-Host "OK   $path" }
}
```

### 11.5 未签名说明

- 发布包默认**未做代码签名**；
- SmartScreen 可能提示“未知发布者”，杀毒软件可能误报；
- 对外正式发布前应使用代码签名证书签名 exe 及安装包；
- 本次构建与运行验证结果记录在文末「构建验证记录」。

---

## 12. 版本管理

### 12.1 唯一真源

`src/quicklanshare/core/version.py`：

```python
__software_name__ = "QuickLanShare"
__version__ = "3.5.4"
__author__ = "XAF"
__copyright_ym__ = "2026.11"
```

`pyproject.toml` 通过 hatch 动态读取，禁止再写第二份版本号。

### 12.2 脚本

| 脚本 | 作用 |
| --- | --- |
| `gen_version_info.py` | 生成 `scripts/version_info.txt`（四段文件版本 + 产品版本 + 版权） |
| `sync_version.py` | 更新版权年月、`VERSION.txt`、三份文档一级标题、输出发布包名 |
| `verify_version.py` | 校验 `version.py` / `version_info.txt` / `VERSION.txt` / 三份文档一致 |

手动执行：

```powershell
uv run python scripts/sync_version.py --build-date 2026-11-04
uv run python scripts/gen_version_info.py
uv run python scripts/verify_version.py
```

版本递增规则（模板 L1.2）：

- 修复：PATCH +1；
- 新增功能：MINOR +1，PATCH 归零；
- 不兼容：MAJOR +1，其余归零。

v3.0.0 属于不兼容变更（CLI → GUI、目录与配置布局变化）。

v3.1.0 属于新增功能 + 界面重构（MINOR）：新增文本共享、双栏布局、日志抽屉；
配置字段未变，v3.0 的 `config.json` 可直接沿用。

v3.2.0 属于新增功能（MINOR）：文件勾选/下载状态、二维码交互、开机自启；
新增 `ui.autostart` / `ui.autostart_silent`，默认关闭。

v3.2.1 属于修复（PATCH）：二维码按钮 tooltip 遮挡、连接弹层黑底、文件夹图标位置。

v3.2.2 属于修复（PATCH）：状态列文字改为居中，与表头对齐。

v3.3.0 属于新增功能（MINOR）：默认下载目录跟随 Windows 已知“下载”，
支持 D 盘重定向，设置中可修改/恢复默认；新增 `ui.download_dir`（默认空）。

v3.4.0 属于新增功能（MINOR）：直接下载、25 GiB 单文件、IPv4 放通范围、
本机网页保留关闭控制、数据目录/桌面默认路径与表格对齐。

---

## 13. 开发过程记录

### 13.1 需求拆解

| 需求 | 落点 |
| --- | --- |
| 命令行 → 带 UI 的 exe，仍用 Python | PySide6 + PyInstaller `--windowed --onedir` |
| 打开 exe 后仍可打开网页，可不打开，默认不打开 | `open_browser` 配置默认 false，设置可开，界面可随时打开 |
| UI 内可下载、可拖拽上传 | `DropZone` + `FileTable` + `LocalShareClient` |
| 文本输入与显示 | `TextPanel` + `/api/chat/*` + `ChatSocketClient`（与网页端同一房间） |
| 显示日志 | 文件日志 + `LogPanel` 镜像 + 日志抽屉 + 级别过滤 |
| 现代界面、浅色 | `ui/theme.py` 卡片化浅色 QSS，对比度与状态色 |
| 适配 Win10/11 | Qt6、系统图标字体、无 Win11 专属 API |
| 默认 24 小时自动关闭，可配置不关闭 | `auto_shutdown_hours=24`，设置开关即时生效 |

### 13.2 关键决策

1. **保留原服务端**：传输、聊天、ZIP、Range 逻辑经过 v2 验证，重写风险大；只做包结构迁移。
2. **桌面端走 HTTP API**：避免跨线程共享可变对象；缺点是多一次本机回环，但实现简单可靠。
3. **服务端独立线程**：Qt 与 asyncio 事件循环互不阻塞；界面通过信号通信。
4. **日志双通道**：文件日志是真相，界面只是镜像，避免 UI 日志丢失或格式分叉。
5. **配置与运行配置分离**：`AppConfig`（持久化偏好）与 `Config`（一次运行参数）职责清晰。
6. **自动关闭即时生效**：设置保存后直接改服务端计时，无需重启。
7. **骨架屏最短展示 450 ms**：防止本地极快加载导致闪烁。
8. **文本共享复用聊天室**：桌面端不新建存储，只通过 `/ws` 订阅、HTTP 发送，保证与网页端同一份记录。
9. **文本发送走 HTTP、接收走 WebSocket**：HTTP 有明确消息 id，WebSocket 只做实时广播；界面按 id 去重。

### 13.3 失败尝试 / 放弃方案

| 尝试 | 结果 | 原因 |
| --- | --- | --- |
| 界面线程直接调用 `FileStore.list_files` | 放弃 | 删除/计数会跨线程修改状态，容易竞态 |
| 使用 `QtAsyncio` 合并事件循环 | 放弃 | 与 aiohttp、Qt 定时器集成复杂，异常排查困难 |
| 使用 `QSettings` 保存配置 | 放弃 | 模板要求显式文件、原子写与损坏回退 |
| 单窗口内嵌 `QWebEngineView` 作为主界面 | 放弃 | 体积大、启动慢，且桌面端文件管理仍需原生控件 |
| 关闭窗口直接退出 | 放弃 | 托盘常驻更符合共享服务场景；已提供设置关闭 |

---

## 14. 踩坑记录

每条按「现象 → 原因 → 解决 → 验证 → 避免」记录。

### 14.1 迁移后测试仍导入 `qls`

- **现象**：`pytest` 收集失败 `ModuleNotFoundError: qls`。
- **原因**：包从 `qls/` 迁移到 `src/quicklanshare/services/`，测试未同步。
- **解决**：统一改为 `quicklanshare.services.*`；`filenames.py` 替代旧 `paths.py`。
- **验证**：123 个测试全部通过。
- **避免**：重构时用全仓搜索旧包名，并先跑一次测试。

### 14.2 界面日志被 HTTP 访问日志刷屏

- **现象**：每上传一个分片，日志面板出现一行 `127.0.0.1 ... "PUT /api/upload/chunk"`。
- **原因**：`AppRunner(access_log=logger)` 使用包级 logger，记录冒泡到 UI handler。
- **解决**：`quicklanshare.access` 默认级别设为 WARNING；需要排查时调 DEBUG。
- **验证**：面板只显示启动、上传完成、下载等业务行。
- **避免**：访问日志与业务日志使用独立 logger，并显式设定级别。

### 14.3 自动关闭默认值变化导致旧测试失败

- **现象**：延长测试断言 `remain_seconds <= 24h` 失败。
- **原因**：产品默认从 6 小时改为 24 小时，且上限从 24 小时放宽到 720 小时。
- **解决**：该用例显式传 `auto_shutdown_max_hours=24.0`，继续验证“延长会封顶”。
- **验证**：生命周期测试通过。
- **避免**：测试不要依赖产品默认值；需要边界时显式传入。

### 14.4 offscreen 截图文字全是方框

- **现象**：`QT_QPA_PLATFORM=offscreen` 下 `widget.grab()` 的文字显示为 □□□。
- **原因**：offscreen 平台在 Windows 上找不到字体目录，Qt 不回退系统字体。
- **解决**：截图改用 `WA_DontShowOnScreen` + 正常 `windows` 平台；测试仍用 offscreen（只验证逻辑）。
- **验证**：`docs/images/main-window.png` 中文正常。
- **避免**：视觉验证与自动化测试使用不同平台策略。

### 14.5 传输任务卡片长期占用空间

- **现象**：上传 3 个文件后，文件列表只剩 1 行可见。
- **原因**：每个完成任务仍保留 56 px 进度行。
- **解决**：完成行压缩为 36 px 并隐藏进度条；全部完成后 6 秒自动收起。
- **验证**：截图与手动操作确认文件表恢复高度。
- **避免**：长生命周期面板要有自动收纳策略。

### 14.6 PyInstaller 打包后 Qt 平台插件缺失

- **现象**：exe 双击无反应或报 `could not find or load the Qt platform plugin "windows"`。
- **原因**：PySide6 插件未收集，或 `--add-data` 放错层级。
- **解决**：`build.ps1` 检查 `_internal/PySide6/plugins/platforms/qwindows.dll`；缺失直接失败并提示 `--collect-all PySide6`。
- **验证**：发布包内插件存在，exe 可启动（见构建验证记录）。
- **避免**：把插件检查写进构建脚本，而不是靠人工。

### 14.7 单实例与开发态冲突

- **现象**：开发时新启动的进程直接退出。
- **原因**：已有实例占用同名 QLocalServer，第二个实例发送激活消息后退出。
- **解决**：这是预期行为；调试时先退出托盘中的旧实例；服务名包含当前用户哈希，避免多用户冲突。
- **验证**：重复启动只保留一个进程并激活窗口。
- **避免**：不要用全局固定名，不要忘了 `QLocalServer.removeServer` 清理残留。

### 14.8 关闭窗口后测试进程不退

- **现象**：GUI 测试调用 `window.close()` 后 `QApplication` 退出，后续用例失败。
- **原因**：`closeEvent` 在无托盘时走 `request_quit` → `QApplication.quit()`。
- **解决**：测试只构造/隐藏窗口，不触发关闭；退出流程由手动与打包验证覆盖。
- **验证**：`test_ui.py` 稳定通过。
- **避免**：测试不要调用会触发应用级退出的事件。

### 14.9 文本消息重复显示

- **现象**：发送一条文本后，右侧出现两条相同消息。
- **原因**：HTTP 返回消息与 WebSocket 广播各触发一次 `chat_message`。
- **解决**：`TextPanel` 按消息 `id` 去重；HTTP 返回先到或广播先到都只保留一条。
- **验证**：`test_ui.py::test_text_panel_send_and_display` 发送两条后计数为 2。
- **避免**：实时通道与请求响应同时存在时，必须约定唯一 id 去重。

### 14.10 文本气泡过窄 / 日志抽屉遮住状态栏

- **现象**：中文短句频繁换行；打开日志后底部状态栏被遮住。
- **原因**：气泡最大宽度在布局完成前按窗口宽度计算；抽屉按窗口底边定位。
- **解决**：布局完成后按滚动区宽度重算气泡 min/max 宽度；抽屉目标位置预留 42px 状态栏。
- **验证**：截图确认气泡宽度和状态栏可见。
- **避免**：涉及实际可用宽高的布局计算放到 `QTimer.singleShot(0, ...)` 或 resize 后执行。

---

## 15. 运维与排错

### 15.1 启动失败

1. 查看 `logs/log_*.log` 最新文件；
2. 检查是否已有实例在托盘运行；
3. 检查端口是否被占用（界面会显示实际端口）；
4. 检查 `config/config.json` 是否损坏（应已自动改名）；
5. 检查 exe 同级是否可写（否则看 `%LOCALAPPDATA%\QuickLanShare`）。

### 15.2 手机打不开网页

- 确认同一网段、未开启 AP 隔离；
- 确认 Windows 防火墙允许该 exe 的专用网络访问；
- 多网卡时换一个 IP 试试；
- 确认服务状态为「运行中」，倒计时正常。

### 15.3 上传中断 / 卡住

- 界面传输行会显示失败原因；
- 网络恢复后重新选择同一文件会续传；
- 未完成分片 24 小时后清理；
- 磁盘空间不足会直接失败并提示。

### 15.4 删除失败

- 文件正在被下载/占用时返回 409；
- 关闭占用程序后重试；
- 只读目录会导致失败，检查 `uploads/` 权限。

### 15.5 日志目录

- 默认：exe 同级 `logs/`；
- 回退：`%LOCALAPPDATA%\QuickLanShare\logs`；
- 面板「打开目录」可直接定位。

### 15.6 文本不同步 / 发送失败

- 右侧状态显示「重连中」：服务器可能重启过，等待自动重连；重连期间每 4 秒补拉历史；
- 显示「已停止」：先启动服务；
- 发送失败：检查消息是否为空或超过 500 字；
- 仍不恢复：查看日志抽屉中 `quicklanshare.chat.client` 与 `quicklanshare.backend` 的警告。

### 15.7 完全重置

1. 退出程序；
2. 备份 `uploads/`；
3. 删除 `config/config.json` 与 `logs/`；
4. 重新启动，程序生成默认配置。

> 不要删除 `uploads/`，那是共享文件本体。

---

## 16. 性能与资源

- 空闲内存：Qt + aiohttp 约 120～180 MB（随文件数量与日志量变化）；
- 启动时间：本机约 1～2 秒（含 Qt 初始化）；
- 上传/下载：局域网千兆环境可跑满链路，单分片 8 MiB 兼顾速度与重试粒度；
- 文件列表每 15 秒自动刷新（有传输任务时跳过），在线统计每 5 秒刷新；
- 日志面板最多保留 3000 行，文件日志按 10 MB 轮转。

> 以上为开发机观察值，不是基准测试承诺。

---

## 17. 安全注意事项

1. 默认监听 `0.0.0.0`，但只放通与本机同前三段的 IPv4；公共 Wi-Fi 下仍建议关闭服务。
   若改为「全部放通」，请确认网络环境可信。
2. 服务端已做 Host/Origin/Sec-Fetch-Site 校验，但仍不应暴露到公网。
3. 上传文件保存在 `uploads/`，请定期清理敏感文件。
4. 不要把含令牌/密码的文件拖入共享。
5. 发布包未签名，分发前建议校验 SHA256 或自行签名。
6. 依赖漏洞：升级时执行 `uv lock --upgrade` 并重跑测试。

---

## 18. 遗留项与后续计划

- [x] 开机自启（当前用户注册表 Run，支持静默）；
- [ ] 深色主题与主题跟随系统；
- [ ] 传输限速与并发上限设置；
- [ ] 文本消息附件 / 富文本（需服务端协议扩展）；
- [ ] HTTPS 证书选择界面；
- [ ] 安装包（Inno Setup）与代码签名；
- [ ] 高 DPI 125%/150% 实机截图回归。

---

## 19. 构建验证记录

> 本节记录实际执行结果，未执行的项不得写成已通过。

| 检查项 | 命令 | 结果 |
| --- | --- | --- |
| 依赖同步 | `uv sync --frozen` | 通过 |
| 代码风格 | `uv run ruff check .` | 通过 |
| 格式化 | `uv run ruff format --check .` | 通过 |
| 类型检查 | `uv run mypy`（strict） | 通过，42 个源文件 |
| 单元/集成/GUI 测试 | `uv run pytest -q` | 通过，123 passed |
| 覆盖率 | `--cov=quicklanshare.services --cov=quicklanshare.core` | 80%（各模块 ≥73%） |
| 版本一致性 | `uv run python scripts/verify_version.py` | 通过（退出码 0） |
| PyInstaller 构建 | `pwsh -File scripts/build.ps1` | 通过 |
| exe 启动验证 | 双击发布包 exe / 进程与日志检查 | 通过 |
| 单实例 | 第二次启动 exe | 通过：第二进程退出，主窗口保持 |
| 优雅退出 | 关闭主窗口（`close_to_tray=false`） | 通过：服务停止、进程退出码 0 |
| HTTP 服务 | `GET /api/room-info` | 通过：返回当前版本 / 文件数 / 版权 |
| 24 小时自动关闭 | 单元测试压缩时长为毫秒级 | 通过：到期停止服务并以 `auto-shutdown` 退出 |
| 文本共享 | 桌面端发送 / 网页端消息 / 删除 / 重连状态 | 通过：`test_ui` 与 `test_chat_client` |
| 文件勾选/下载状态 | 全选、已下载状态、打开文件夹 | 通过：`test_ui` 与 `test_download_registry` |
| 默认下载/直接保存 | 自定义下载目录、重名编号、无保存对话框 | 通过：`test_ui` 与 `test_downloads` |
| IP 放通范围 | 四种范围、回环、配置校验 | 通过：`test_access` |
| 本机网页控制 | `/api/room-info` 返回 `local_client` | 通过：`test_api`；远端关闭接口由服务端限制 |
| 数据目录/桌面路径 | 打开 uploads、选择文件默认桌面 | 通过：`test_ui` 与 `test_downloads` |
| 静默自启 | `QuickLanShare.exe --silent`，再次普通启动 | 通过：首个进程无主窗口，第二次启动激活窗口 |
| 开机自启注册表 | `apply_autostart(True/False)` | 通过：写入/删除 HKCU Run 值 |

构建产物（2026-11-04）：

| 项 | 值 |
| --- | --- |
| 发布目录 | `release/QuickLanShare_v3.4.0_win-x64_20261104/` |
| 发布目录大小 | 131.0 MB |
| exe | `QuickLanShare.exe`（4,673,995 字节） |
| exe 属性 | ProductName/FileVersion/ProductVersion/LegalCopyright 均正确（3.4.0 / XAF 2026.11） |
| 打包资源 | `_internal/client/index.html`、`_internal/app.ico`、`qwindows.dll`、`docs/images/` 均存在 |
| ZIP | `QuickLanShare_v3.4.0_win-x64_20261104.zip`（包含完整发布目录） |
| 校验 | `SHA256SUMS.txt` 已生成，全量校验通过 |
| exe 文本接口 | 启动 exe 后 `POST /api/chat/send` 成功，桌面端 WebSocket 已连接 |

**未验证 / 未执行**

- 未在“全新安装的 Windows 10 / Windows 11 实机”上做最终验收（当前为开发机运行验证）；
- 未做代码签名，未测试 SmartScreen 正式分发流程；
- 未生成 Inno Setup 安装包（本次交付为便携目录 + ZIP）；
- 未重启系统验证“登录 Windows 自动启动”真实流程（已用 `--silent` 启动、注册表读写与二次启动激活分别验证）；
- 未在 125% / 150% 缩放的实机屏幕上逐项截图回归（窗口已做可用区域夹紧与滚动兜底）。

---

## 修订记录

| 日期 | 版本号 | 说明 |
| --- | --- | --- |
| 2026-11-06 | 3.5.4 | 移除拨杆关闭服务端、红色竖线与关闭标签；最左侧改为普通 `192` 刻点 |
| 2026-11-06 | 3.5.3 | 拨杆手柄改为 10px 实心圆点 + 白色隔离环，移除大圆环、防滑纹与阴影 |
| 2026-11-06 | 3.5.2 | 拨杆改为“关闭服务 + 四个 IP 刻点”，刻点显示真实 IPv4；增加右侧开放方向、拖动阻力、关闭确认与服务状态联动 |
| 2026-11-06 | 3.5.1 | 开放网段改为四档滑动选择（同段/后2段/后3段/全部），默认全部开放；移除任意段组合 |
| 2026-11-06 | 3.5.0 | 一键重启、开放网段热更新、在线用户 IP/状态、文本编辑/批量删除/改名、自动滚动、中文右键与 Ctrl+C 复制 |
| 2026-11-04 | 3.4.0 | 直接下载、25 GiB、IPv4 放通范围、本机网页关闭控制、数据目录与桌面默认路径 |
| 2026-11-04 | 3.3.0 | 默认下载目录跟随系统“下载”（支持 D 盘重定向），设置可修改/恢复 |
| 2026-11-04 | 3.2.2 | 状态列文字居中，与表头对齐 |
| 2026-11-04 | 3.2.1 | 二维码 tooltip 遮挡、连接弹层黑底、文件夹图标位置调整 |
| 2026-11-04 | 3.2.0 | 文件勾选/下载状态/筛选、二维码小图与居中遮罩、开机自启/静默自启与相关测试/踩坑 |
| 2026-11-04 | 3.1.0 | 双栏工作台、桌面文本共享（WebSocket 订阅 + HTTP 发送）、日志抽屉、连接弹层与相关测试/踩坑 |
| 2026-11-04 | 3.0.0 | 新建开发手册：环境、架构、线程模型、配置、日志、自动关闭、测试、打包与踩坑 |
