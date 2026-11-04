# 最终发布包规范（Inno Setup）

> **位置**：`parts/` 下第 **7** 份文档。前 6 份是 `cpp.md`、`python.md`、`java.md`、`rust.md`、`android.md`、`vue.md`；本文件是最终发布规范。本文只维护自己，**不修改前 6 份语言模板**。  
> **触发**：用户说“满意了”“可以发布”“打包最终版”“出安装包”“生成发布包”时，在 `L10` 验收通过后执行。  
> **范围**：C++/Qt6、Python/PySide6、Rust 的 Windows exe 最终安装包**只使用 Inno Setup**；Java（jar）、Android（APK）、Vue（静态站点）不使用 Inno，按各自章节交付，不能硬套 Windows 安装器。  
> **原则**：不是“装个 Inno 就完了”。每种语言的构建命令、发布目录内容、`.iss` 变量、测试重点都不同，下面按语言分别写清。

---

## 0. 先看分类：哪 3 种用 Inno，哪 3 种不用

`parts/` 下共 **7 份文档**：

| 序号 | 文档 | 最终交付 | 是否用 Inno Setup | 本文对应章节 |
| ---: | --- | --- | :---: | --- |
| 1 | `cpp.md` | Qt6 Windows x64 exe + 安装包 | **是** | 第 2 节 |
| 2 | `python.md` | PyInstaller onedir + 安装包 | **是** | 第 3 节 |
| 3 | `java.md` | 可执行 jar + `run.bat` + CentOS 部署 | 否 | 第 4 节 |
| 4 | `rust.md` | Windows x64 exe + 安装包 | **是** | 第 5 节 |
| 5 | `android.md` | 签名 APK | 否 | 第 6 节 |
| 6 | `vue.md` | `dist/` + nginx 配置 | 否 | 第 7 节 |
| 7 | 本文件 | 规范本身 | — | — |

**唯一性只约束 Windows 桌面 exe**：C++/Python/Rust 不得改用 NSIS、WiX/MSI、MSIX、QtIFW，也不得用绿色 ZIP 代替安装包。Java/Android/Vue 的最终形态不是 Windows 安装包，强行套 Inno 是错误交付。

---

## 1. 三种 Windows 语言共用的发布标准

这一节是 C++/Python/Rust 的公共底线；具体语言差异在第 2、3、5 节。

### 1.1 前置条件

- `L10` 验收清单逐项通过，未执行项已明确标注；
- 版本号在唯一真源、`VERSION.txt`、exe 属性、安装包名中一致；
- 根 `README.md`、`docs/`、`config/`、`logs/`、`VERSION.txt`、`THIRD-PARTY-NOTICES.md`、许可文件齐全；
- 发布目录无源码、`.git`、`build/`、`dist/`、缓存、测试数据、开发机配置、运行日志、密钥；
- 在全新 Windows 10/11 x64 上可独立运行，不要求预装 Python、Qt、Rust 或 VC++ 运行时；
- 默认当前用户安装，不需要管理员权限；
- 对外发布已准备受信任的 Authenticode 证书。

不满足就停，不能用安装包掩盖构建或运行问题。

### 1.2 发布目录（Inno 的输入）

先按 `L6.7` 生成便携目录，再把它作为 Inno 的 `[Files]` 来源：

```text
release/
└─ <SOFTWARE_NAME>_v<VERSION>_win-x64_<YYYYMMDD>/
   ├─ <主程序>.exe
   ├─ README.md
   ├─ docs/
   ├─ config/
   ├─ logs/                      # 空目录，或仅 .gitkeep
   ├─ VERSION.txt
   ├─ THIRD-PARTY-NOTICES.md
   └─ LICENSE
```

要求：

- 根目录就是用户安装后看到的目录，不要多套一层；
- `config/` 只放干净默认配置；`logs/` 必须存在但为空；
- `[Files]` 只指向这个目录，不直接指向 `build/`、`dist/`、`target/` 或源码目录；
- 安装包输出到 `release/installer/`，不混进便携目录。

### 1.3 命名与校验

- 便携目录：`<SOFTWARE_NAME>_v<VERSION>_win-x64_<YYYYMMDD>`
- 安装包：`<SOFTWARE_NAME>_v<VERSION>_win-x64_<YYYYMMDD>_setup.exe`
- 校验文件：`release/installer/SHA256SUMS.txt`
- 发布说明：`release/installer/RELEASE-NOTES.md`
- 安装包、`AppVersion`、`VERSION.txt`、exe 属性必须使用同一个版本号。

### 1.4 Inno 脚本硬性要求

脚本放 `installer/<软件名>.iss`；三种 Windows 语言共用同一套骨架，只改变量、图标和 payload。

| 项 | 要求 |
| --- | --- |
| Inno 版本 | 6.7+ 或 7.x；在 6.x 与 7.x 都能编译 |
| `AppId` | 稳定 GUID，首次发布后永不修改；升级靠它识别同一产品 |
| 安装范围 | `PrivilegesRequired=lowest`，装到 `{localappdata}\Programs\<软件名>` |
| 管理员 | 默认不触发 UAC；不要装到 `Program Files` |
| 架构 | `ArchitecturesAllowed=x64compatible` |
| 压缩 | `Compression=lzma2/max` + `SolidCompression=yes` |
| 界面 | `WizardStyle=modern`，中文向导；语言文件随仓库提供 |
| 升级 | `UsePreviousAppDir=yes`；同 `AppId` 覆盖安装；安装前关闭运行实例 |
| 图标 | `SetupIconFile`、`UninstallDisplayIcon` 指向 `app.ico` / 主 exe |
| 许可 | 有 `LICENSE` 时显示许可页；RTF/TXT 由构建脚本准备 |
| 静默安装 | `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=...` |
| 卸载 | 生成 `unins000.exe`；`/VERYSILENT` 可静默卸载 |
| 签名 | 对外发布必须签 setup 与卸载器；证书不得进仓库 |
| 日志 | 保留 ISCC 日志；失败退出码非 0 |

### 1.5 最小 `.iss` 骨架

```ini
#define MyAppName "<软件名>"
#define MyAppVersion "<版本>"
#define MyAppPublisher "<作者>"
#define MyAppExeName "<主程序>.exe"
#define ReleaseDir "..\release\<SOFTWARE_NAME>_v<VERSION>_win-x64_<YYYYMMDD>"
; 首次发布前替换为固定 GUID；发布后永不修改
#define MyAppId "{{00000000-0000-0000-0000-000000000000}"
#ifndef BuildDate
  #define BuildDate "<YYYYMMDD>"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=..\release\installer
OutputBaseFilename={#MyAppName}_v{#MyAppVersion}_win-x64_{#BuildDate}_setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
AllowNoIcons=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
SetupLogging=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#ReleaseDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
```

补充：

- 三种语言的 `MyAppExeName`、`ReleaseDir`、图标不同，其他可共用；
- `config/` 默认配置建议单独用 `onlyifdoesntexist` 安装，不要用 `ignoreversion` 覆盖用户修改；
- 默认不加 `[UninstallDelete]`，运行期用户数据保留；如产品要求卸载清空，必须显式配置并写进发布说明；
- 需要文件关联、服务、驱动、计划任务时单独评审，不要塞进通用骨架。

### 1.6 构建脚本

生成软件必须提供 `scripts/build-installer.ps1`：

1. 读取版本真源与 `VERSION.txt`，不一致直接失败；
2. 校验 `release/<...>/` 存在，并包含 `README.md`、`docs/`、`config/`、`logs/`、`VERSION.txt`、`THIRD-PARTY-NOTICES.md`、许可文件；
3. 按顺序找 `ISCC.exe`：`$env:INNO_SETUP_HOME\ISCC.exe`、`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`、`C:\Program Files\Inno Setup 7\ISCC.exe`；
4. 执行 `ISCC.exe /Qp installer\<软件名>.iss /DBuildDate=<YYYYMMDD>`；
5. 退出码非 0 直接失败，保留 `installer/build.log`；
6. 计算 SHA-256，写 `release/installer/SHA256SUMS.txt`；
7. 可选签名：证书路径、密码、时间戳 URL 从环境变量读取；
8. 输出最终路径、大小、SHA-256、签名状态。

脚本不得写开发机绝对路径，不得修改发布目录，必须可重复运行且不产生 `setup (1).exe`。

### 1.7 签名与校验

对外发布必须：

- 用受信任的 Authenticode 证书签名安装包，SHA-256 + RFC 3161 时间戳；
- 用 Inno 的 `SignTool` + `SignedUninstaller=yes` 配置签 setup 与卸载器；
- `signtool verify /pa /v` 通过；
- 在 `RELEASE-NOTES.md` 给出 SHA-256 与校验命令；
- 无证书的内部验收包必须标注“未签名，仅内部测试”，不能叫最终发布包。

### 1.8 安装/卸载/升级行为

- 中文向导完整：许可页、目录页、进度页、完成页；
- 默认当前用户安装，不触发 UAC；
- 开始菜单入口正常，桌面快捷方式为可选任务；
- 设置 → 应用 中有正确名称、版本、发布者、卸载入口；
- 安装后可启动，程序能写 `config/`、`logs/`；
- 同版本重复安装不产生两份 ARP 项；升级保留用户 `config/`、`logs/`（默认配置覆盖策略固定并写进发布说明）；
- 卸载移除程序文件、快捷方式、ARP 项；用户数据策略固定；
- 静默安装/卸载退出码 0，失败非 0 且有日志。

### 1.9 通用测试矩阵

| 场景 | 通过标准 |
| --- | --- |
| 全新 Windows 10/11 x64 | 无需预装运行时，安装/启动/卸载成功 |
| 普通用户 | 安装不弹 UAC，程序可写 config/logs |
| 中文用户名 + 含空格路径 | 安装、启动、卸载正常 |
| 静默安装 `/VERYSILENT` | 退出码 0，文件齐全 |
| 静默卸载 `/VERYSILENT` | 退出码 0，程序文件移除 |
| 升级安装 | 同 AppId 覆盖，用户数据保留 |
| 签名 | `signtool verify /pa /v` 通过 |
| SHA-256 | 与 `SHA256SUMS.txt` 一致 |
| 受管环境（SAC/AppLocker/WDAC） | 已签名包可运行；未签名包标注风险 |

---

## 2. C++ / Qt6 的最终发布

### 2.1 构建

在项目根执行：

```powershell
cmake --preset windows-x64-release
cmake --build --preset windows-x64-release
ctest --preset windows-x64-release --output-on-failure
```

要求：

- Release x64，MSVC 2022，C++20；
- `app.manifest` 已声明 Per-Monitor V2 DPI；
- `app.ico` 已嵌入 exe；
- `/W4` + `/WX` 通过；
- 动态链接 Qt，保留 LGPL 合规材料。

### 2.2 生成发布目录

```powershell
$rel = "release\MyApp_v1.0.0_win-x64_20261101"
New-Item -ItemType Directory -Force $rel | Out-Null
Copy-Item "build\windows-x64-release\MyApp.exe" $rel
windeployqt --release --compiler-runtime --dir $rel "$rel\MyApp.exe"
Copy-Item README.md, THIRD-PARTY-NOTICES.md, LICENSE, VERSION.txt $rel
Copy-Item docs $rel -Recurse
New-Item -ItemType Directory -Force "$rel\config","$rel\logs" | Out-Null
```

必须检查：

- `platforms\qwindows.dll` 存在；
- `styles\qmodernwindowsstyle.dll`、`imageformats\*.dll` 等实际用到的插件存在；
- `Qt6Core.dll`、`Qt6Gui.dll`、`Qt6Widgets.dll` 等与程序一起分发；
- MSVC 运行库已由 `--compiler-runtime` 收集，或按需求改用静态 CRT；
- 发布目录不含 `CMakeFiles/`、`.obj`、`.pdb`（除非单独提供符号包）、源码、`.git`。

### 2.3 本语言 `.iss` 差异

| 变量 | 值 |
| --- | --- |
| `MyAppExeName` | `MyApp.exe` |
| `ReleaseDir` | `..\release\MyApp_v1.0.0_win-x64_20261101` |
| 图标 | 项目根 `app.ico` |

其余使用第 1.5 节骨架。`[Files]` 必须递归包含 `platforms/`、`styles/`、`imageformats/`、`translations/`，不能只装 exe 和几个 DLL。

### 2.4 验收重点

- 在未安装 Qt 的干净 Win10/11 上启动；
- Qt 插件加载失败时能在日志中看到具体缺哪个 DLL；
- 包内含 Qt LGPL-3.0 文本、版权声明、可替换说明；
- 安装后 `config/`、`logs/` 可写；
- 安装/卸载/升级按第 1.8 节通过。

---

## 3. Python / PySide6 的最终发布

### 3.1 构建

```powershell
uv sync --frozen
uv run ruff check
uv run ruff format --check
uv run mypy .
uv run pytest
```

### 3.2 PyInstaller 打包

推荐用仓库内 `.spec` 固定参数：

```powershell
uv run pyinstaller --noconfirm --clean MyApp.spec
```

`.spec` 必须明确：

- `--onedir`，不要用 `onefile` 再套安装包；
- `--windowed`，无控制台窗口；
- `icon="app.ico"`；
- `version="version_info.txt"`（由 `gen_version_info.py` 生成）；
- PySide6 的 Qt 插件、translations 由 hook 收集；缺失时显式 `collect_data_files` / `hiddenimports`；
- 输出目录为 `dist\MyApp\`，包含 `MyApp.exe` 与 `_internal\`。

### 3.3 生成发布目录

```powershell
$rel = "release\MyApp_v1.0.0_win-x64_20261101"
New-Item -ItemType Directory -Force $rel | Out-Null
Copy-Item "dist\MyApp\*" $rel -Recurse -Force
Copy-Item README.md, THIRD-PARTY-NOTICES.md, LICENSE, VERSION.txt $rel
Copy-Item docs $rel -Recurse
New-Item -ItemType Directory -Force "$rel\config","$rel\logs" | Out-Null
```

要求：

- 保留 `_internal\` 完整目录，不能把 PySide6/Qt DLL 拍平；
- 如程序依赖 `platform-tools\adb.exe` 等外部工具，单独放根目录并保留其 NOTICE；
- `config\config.json` 重置为干净默认值，不带开发机上次连接信息；
- `logs\` 为空；不把 `__pycache__`、`.venv`、`build\`、`dist\` 的其他内容带进去；
- exe 属性中的产品名、版本、版权与 `VERSION.txt` 一致。

### 3.4 本语言 `.iss` 差异

| 变量 | 值 |
| --- | --- |
| `MyAppExeName` | `MyApp.exe` |
| `ReleaseDir` | `..\release\MyApp_v1.0.0_win-x64_20261101` |
| 图标 | 项目根 `app.ico` |

其余使用第 1.5 节骨架。安装后用户目录下必须同时存在 `MyApp.exe` 和 `_internal\`；不要只装 exe。

### 3.5 验收重点

- 干净机器没有 Python、没有 PySide6，程序仍能启动；
- 冷启动时间可接受（`onedir` 不应出现 `onefile` 的解压等待）；
- Qt 插件、图标、翻译资源齐全；
- 日志/配置写入安装目录成功（per-user 安装已保证可写）；
- 包内 PySide6 / Qt 的 LGPL 声明与可替换说明完整；
- 安装/卸载/升级按第 1.8 节通过。

---

## 4. Java / Spring Boot 的最终发布

Java 模板的最终交付是 **可执行 jar + Windows `run.bat` + CentOS 部署说明**，不是 Windows 安装包。**不要用 Inno 包 jar**；如用户要求“做成 exe 安装包”，先停下确认是否改变交付形态。

### 4.1 构建

```powershell
.\mvnw.cmd clean verify
```

要求：

- Java 17，Spring Boot 3.2+；
- `mvnw`、`mvnw.cmd`、`.mvn/wrapper/` 齐全；
- JUnit 5 测试通过；
- jar 可执行（`java -jar` 可启动）；
- Flyway 迁移、Actuator health/info 正常。

### 4.2 生成发布目录

```text
release/
└─ MyService_v1.0.0_jar_20261101/
   ├─ MyService-1.0.0.jar
   ├─ scripts/run.bat
   ├─ config/application-prod.yml
   ├─ logs/
   ├─ docs/centos-run.md
   ├─ README.md
   ├─ VERSION.txt
   ├─ THIRD-PARTY-NOTICES.md
   ├─ LICENSE
   └─ SHA256SUMS.txt
```

`run.bat` 要求：

- 检查 `JAVA_HOME` 或 `java -version` 是否为 17；
- 设置 `-Dspring.profiles.active=prod`；
- 设置日志目录、JVM 内存参数；
- 失败时暂停并打印可读错误，不闪退。

### 4.3 服务器部署

`docs/centos-run.md` 必须给出可复制命令：

- 安装 JDK 17；
- MySQL 8.0+ 建库、建用户、授权、`utf8mb4`；
- 上传 jar 与 `config/`；
- systemd 服务文件、`systemctl daemon-reload`、`enable --now`；
- nginx 反向代理与 HTTPS；
- 日志位置、滚动、排错；
- 升级与回滚步骤。

### 4.4 验收重点

- `java -jar` 在干净 JDK 17 上启动；
- `run.bat` 双击可启动并检查 Java 版本；
- `/actuator/health` 返回 UP；
- Flyway 迁移成功，数据库字符集/时区正确；
- 不把 `target/`、源码、密钥、数据库密码打进发布包；
- `SHA256SUMS.txt` 覆盖 jar 与关键脚本。

---

## 5. Rust / exe 的最终发布

### 5.1 构建

```powershell
cargo fmt --check
cargo clippy -- -D warnings
cargo test --locked
cargo build --release --locked
```

要求：

- MSVC 工具链，Windows 10/11 x64；
- 生产路径无 `unwrap` / `expect` / 裸 `panic!`；
- GUI 程序设置 `#![windows_subsystem = "windows"]`，避免黑色控制台；
- 版本资源由 `winres` / `embed-resource` 写入 exe；
- 需要持久化时使用本地文件，损坏可回退。

### 5.2 生成发布目录

```powershell
$rel = "release\MyApp_v1.0.0_win-x64_20261101"
New-Item -ItemType Directory -Force $rel | Out-Null
Copy-Item "target\release\myapp.exe" "$rel\MyApp.exe"
Copy-Item README.md, THIRD-PARTY-NOTICES.md, LICENSE, VERSION.txt $rel
Copy-Item docs $rel -Recurse
New-Item -ItemType Directory -Force "$rel\config","$rel\logs" | Out-Null
```

要求：

- 只带 Release exe，不带 `target/`、`.pdb`（除非单独符号包）、源码、`.git`；
- 使用静态 CRT（`+crt-static`）或随包提供 VC++ 运行库，并在 README 写明；
- 配置默认值干净，日志目录为空；
- exe 属性含产品名、版本、版权、公司名。

### 5.3 本语言 `.iss` 差异

| 变量 | 值 |
| --- | --- |
| `MyAppExeName` | `MyApp.exe` |
| `ReleaseDir` | `..\release\MyApp_v1.0.0_win-x64_20261101` |
| 图标 | 项目根 `app.ico` |

其余使用第 1.5 节骨架。Rust 的 payload 通常只有 exe + 配置 + 文档，但仍要保留 `config/`、`logs/`、`VERSION.txt`、许可文件。

### 5.4 验收重点

- 干净机器没有 Rust、没有 VC++ 运行库（若静态 CRT）也能启动；
- 无控制台窗口（GUI 形态）；
- 配置损坏可回退，日志写入 `logs/`；
- `cargo audit` 无已知高危漏洞；
- 安装/卸载/升级按第 1.8 节通过。

---

## 6. Android / APK 的最终发布

Android 不用 Inno。最终交付是**签名 APK**，按 `android.md` 的 `L6.7` 执行。

### 6.1 构建与签名

```powershell
.\gradlew.bat clean test lint assembleRelease
```

要求：

- `minSdk = 29`，`targetSdk` 最新稳定；
- `versionCode` 单调递增，`versionName` 与 `VERSION.txt` 一致；
- 签名配置从 `keystore.properties` 或环境变量读取，keystore 与密码不进仓库；
- 用 `apksigner verify --verbose` 验证签名；
- 产物：`app\build\outputs\apk\release\app-release.apk`。

### 6.2 发布目录

```text
release/
└─ MyApp_v1.0.0_apk_20261101/
   ├─ MyApp_v1.0.0.apk
   ├─ README.md
   ├─ docs/
   ├─ VERSION.txt
   ├─ THIRD-PARTY-NOTICES.md
   ├─ LICENSE
   └─ SHA256SUMS.txt
```

不得包含源码、keystore、`local.properties`、`.git`、测试数据。

### 6.3 验收重点

- Android 10 ~ 最新版本安装/启动；
- 覆盖安装保留数据，`versionCode` 递增；
- 权限最小化，Android 13+ 通知、14+ 前台服务、15+ edge-to-edge 已处理；
- `apksigner verify` 通过；
- `SHA256SUMS.txt` 覆盖 APK；
- 不上架时也提供安装说明与已知问题。

---

## 7. Vue / 静态站点的最终发布

Vue 不用 Inno。最终交付是 `dist/` + nginx 配置；AI **不执行 npm**，由用户构建，AI 负责给命令和校验产物。

### 7.1 构建

由用户执行：

```powershell
npm ci
npm run build
```

要求：

- Node.js 20 LTS+；
- `npm run build` = `vue-tsc` 类型检查 + `vite build`；
- 输出 `dist/`；
- `.env.production` 的 `VITE_API_BASE_URL` 正确；
- 不把 `node_modules/`、`.env.local`、源码缓存打进发布目录。

### 7.2 发布目录

```text
release/
└─ MyWeb_v1.0.0_web_20261101/
   ├─ dist/                      # 用户 npm run build 的产物
   ├─ deploy/nginx.conf
   ├─ docs/nginx.md
   ├─ README.md
   ├─ VERSION.txt
   ├─ THIRD-PARTY-NOTICES.md
   └─ SHA256SUMS.txt
```

`docs/nginx.md` 必须包含：

- 上传 `dist/`；
- `try_files $uri $uri/ /index.html;`；
- gzip / brotli；
- 静态资源长缓存、`index.html` 不缓存；
- `/api/` 反向代理到 Java 后端；
- 安全响应头；
- `nginx -t`、`systemctl reload nginx`、回滚、HTTPS 证书配置。

### 7.3 验收重点

- 构建产物可部署，刷新非根路由不 404；
- API 代理、登录态、权限守卫正常；
- 小屏可用，加载/空/错误状态完整；
- 安全头生效；
- 不声称 AI 执行过 npm 构建，未验证项明确标注。

---

## 8. 三种 Windows 语言的 `.iss` 对照

| 项 | C++ / Qt6 | Python / PySide6 | Rust |
| --- | --- | --- | --- |
| 主 exe | `MyApp.exe` | `MyApp.exe` | `MyApp.exe` |
| payload 关键目录 | Qt DLL + `platforms/` + `styles/` + `imageformats/` | `_internal/` + PySide6/Qt 插件 | 仅 exe + config/docs |
| 运行时 | MSVC + Qt | PyInstaller 内置 Python/Qt | 静态 CRT 或 VC++ |
| 图标 | `app.ico` | `app.ico` | `app.ico` |
| 额外检查 | Qt 插件加载、LGPL | 无 Python 环境启动、`_internal` 完整 | 无控制台、无 Rust 环境 |
| 安装器 | Inno | Inno | Inno |

三者的 `AppId` 各自独立，不能共用一个 GUID；`ReleaseDir`、`MyAppExeName`、`SetupIconFile` 按项目替换。

---

## 9. 构建脚本分工

| 语言 | 构建脚本 | 安装器脚本 | 最终产物 |
| --- | --- | --- | --- |
| C++/Qt6 | `scripts/build.ps1`：CMake + ctest + windeployqt + 便携目录 + SHA256 | `scripts/build-installer.ps1` | `_setup.exe` |
| Python | `scripts/build.ps1`：uv + PyInstaller + 便携目录 + SHA256 | `scripts/build-installer.ps1` | `_setup.exe` |
| Rust | `scripts/build.ps1`：cargo + 便携目录 + SHA256 | `scripts/build-installer.ps1` | `_setup.exe` |
| Java | `mvnw clean verify` + 发布目录 | 无 | jar + `run.bat` |
| Android | Gradle `assembleRelease` | 无 | 签名 APK |
| Vue | 用户 `npm run build` | 无 | `dist/` + nginx |

`build-installer.ps1` 只负责调用 Inno、校验、签名、算哈希；不要在安装器脚本里重新编译程序。

---

## 10. 最终验收清单

### 10.1 三种 Windows 语言通用

- [ ] `L10` 全部通过，未执行项已标注
- [ ] 版本号在真源、`VERSION.txt`、exe 属性、安装包名中一致
- [ ] 发布目录按 `L6.7` 生成，根结构正确
- [ ] 发布目录无源码、`.git`、`build/`、`dist/`、`target/`、缓存、日志、密钥、开发机路径
- [ ] `installer/<软件名>.iss` 已提交，`AppId` 稳定
- [ ] 默认 per-user 安装，`PrivilegesRequired=lowest`
- [ ] 中文向导正常，语言文件随仓库提供
- [ ] 安装包命名符合 `<SOFTWARE_NAME>_v<VERSION>_win-x64_<YYYYMMDD>_setup.exe`
- [ ] `scripts/build-installer.ps1` 可重复运行，失败返回非 0
- [ ] 安装包已签名并通过 `signtool verify /pa /v`
- [ ] `SHA256SUMS.txt` 已生成且值一致
- [ ] `RELEASE-NOTES.md` 包含版本、变更、系统要求、校验值、已知问题
- [ ] 普通用户安装/启动/卸载通过，不触发 UAC
- [ ] 中文用户名、含空格路径测试通过
- [ ] 升级安装保留用户数据，ARP 不重复
- [ ] 卸载后程序文件、快捷方式、ARP 项移除
- [ ] 安装后程序能写 `config/`、`logs/`
- [ ] 静默安装/卸载退出码为 0

### 10.2 分语言附加项

- [ ] C++：`windeployqt` 插件齐全，干净机器无 Qt 可启动，LGPL 材料完整
- [ ] Python：`_internal/` 完整，干净机器无 Python 可启动，未使用 `onefile`
- [ ] Rust：静态 CRT 或 VC++ 运行库已处理，GUI 无控制台，`cargo audit` 通过
- [ ] Java：`run.bat` 检查 Java 17，jar 可启动，CentOS 部署步骤可执行
- [ ] Android：`apksigner verify` 通过，`versionCode` 递增，Android 10+ 安装
- [ ] Vue：`dist/` 可部署，刷新路由不 404，nginx 配置与回滚步骤完整

---

## 11. 禁止事项

- 禁止把 Inno 套到 Java jar、Android APK、Vue 静态站点上；
- 禁止 C++/Python/Rust 最终包改用 NSIS、WiX/MSI、MSIX、QtIFW 或绿色 ZIP；
- 禁止只装主 exe，漏掉 Qt 插件、`_internal/`、运行库；
- 禁止把源码、构建中间产物、`.git`、测试数据、开发机配置打进安装包；
- 禁止修改已发布的 `AppId`；
- 禁止把证书、密码、时间戳凭据提交到仓库；
- 禁止对外发布未签名安装包并称为“最终版”；
- 禁止手改发布目录后不复核 SHA-256；
- 禁止使用绝对路径、`setup (1).exe`、占位符或 `TODO` 交付；
- 禁止声称执行过未执行的签名、安装、卸载或干净机测试；
- 禁止用“绿色版解压即用”替代用户要求的安装包交付。

---

## 12. 交付物

### 12.1 C++ / Python / Rust

1. `release/installer/<SOFTWARE_NAME>_v<VERSION>_win-x64_<YYYYMMDD>_setup.exe`
2. `release/installer/SHA256SUMS.txt`
3. `release/installer/RELEASE-NOTES.md`
4. `installer/<软件名>.iss`
5. `scripts/build-installer.ps1`
6. 安装/卸载/升级测试记录

### 12.2 Java

1. `release/<SOFTWARE_NAME>_v<VERSION>_jar_<YYYYMMDD>/`
2. jar、`scripts/run.bat`、`config/`、`docs/centos-run.md`
3. `VERSION.txt`、`SHA256SUMS.txt`、`RELEASE-NOTES.md`

### 12.3 Android

1. `release/<SOFTWARE_NAME>_v<VERSION>_apk_<YYYYMMDD>/`
2. 签名 APK
3. `VERSION.txt`、`SHA256SUMS.txt`、`RELEASE-NOTES.md`

### 12.4 Vue

1. `release/<SOFTWARE_NAME>_v<VERSION>_web_<YYYYMMDD>/`
2. `dist/`、`deploy/nginx.conf`、`docs/nginx.md`
3. `VERSION.txt`、`SHA256SUMS.txt`、`RELEASE-NOTES.md`

---

## 修订记录

- 2026.11.0 — 2026-11-01：新增最终发布包规范；明确 `parts/` 下 7 份文档的分工，按 C++/Python/Rust/Java/Android/Vue 六种语言分别给出构建、发布目录、安装/部署、验收差异。
