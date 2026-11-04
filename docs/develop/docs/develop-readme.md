# 开发与维护指南

> 面向本仓库的维护者。产品介绍见根 [readme.md](../readme.md)，文档总览见 [docs/readme.md](readme.md)，AI 导航见 [AGENTS.md](../AGENTS.md)。

## 1. 环境要求

- Windows 10 / 11；
- Windows PowerShell 5.1 或 PowerShell 7+；
- 不依赖任何外部模块或包；
- 执行策略允许运行本地脚本，或显式使用 `-ExecutionPolicy Bypass`。

## 2. 仓库结构

```text
develop/
├─ AGENTS.md                    # 面向 AI：按语言选择模板
├─ readme.md                    # 面向使用者：产品介绍
├─ docs/
│  ├─ readme.md                 # 面向开发者：文档总览
│  ├─ develop-readme.md         # 面向开发者：开发指南 + 变更记录（本文件）
│  ├─ license.md                # 许可范围说明
│  ├─ examples/
│  │  └─ conversation.md        # 对话式需求示例
│  ├─ cpp/template.md
│  ├─ python/template.md
│  ├─ java/template.md
│  ├─ rust/template.md
│  ├─ android/
│  │  ├─ template.md
│  │  └─ environment.md         # Android 编译环境
│  └─ vue/template.md
├─ cache/                       # 图片、截图、图例、视频等资源
│  ├─ screenshots/
│  ├─ images/
│  ├─ diagrams/
│  └─ videos/
├─ parts/                       # 模板源与最终发布规范
│  ├─ common/                   # 六份模板共用的段落
│  ├─ <语言>.md                 # 六份语言模板源
│  └─ final-release-inno.md     # 最终发布包规范（Inno Setup，不参与拼接）
├─ scripts/                     # 生成与校验脚本
├─ tests/                       # 本仓库自动化测试
├─ LICENSE
├─ .gitignore
└─ .gitattributes
```

所有给人看的文档都放在 `docs/`；根目录只保留用户向 `readme.md`、AI 导航 `AGENTS.md` 和许可证。`parts/final-release-inno.md` 是唯一放在 `parts/` 下的规范文档，它不参与六份模板的拼接。图片、截图等非文档资源统一放 `cache/` 的类型子目录，不混放。

## 3. 生成机制

`parts/cpp.md`、`parts/python.md`、`parts/java.md`、`parts/rust.md`、`parts/android.md`、`parts/vue.md` 中，单独一行写：

```text
@@include common/usage.md
```

生成时会递归展开为 `parts/common/usage.md` 的内容，输出到：

- `docs/cpp/template.md`
- `docs/python/template.md`
- `docs/java/template.md`
- `docs/rust/template.md`
- `docs/android/template.md`
- `docs/vue/template.md`

规则：

- 路径相对于 `parts/`；
- 检测循环引用与缺失片段，出错直接终止；
- 输出统一 UTF-8（无 BOM）、LF 换行；
- 生成结果与 `docs/*/template.md` 不一致时，`-Check` 返回非零；
- 只允许引用 `parts/` 下的文件。
- 另有第 7 份 `parts/final-release-inno.md`（最终发布规范），不参与上述生成与 `@@include` 拼接。

## 4. 编辑流程

1. 改公共规则：编辑 `parts/common/*.md`；
2. 改语言专属规则：编辑 `parts/<语言>.md`（现有 cpp / python / java / rust / android / vue）；
3. 生成：`scripts/build-templates.ps1`；
4. 校验：`scripts/check-templates.ps1`；
5. 测试：`tests/run-tests.ps1`；
6. 更新本文件的「变更记录」。

不要直接改 `docs/*/template.md`，下次生成会被覆盖。

## 5. 校验脚本检查什么

`scripts/check-templates.ps1` 不依赖外部工具，检查：

- `docs/*/template.md` 是否与 `parts/` 同步；
- `V0 ~ V2`、`L0 ~ L11` 章节是否齐全；
- `L1.1`、`L6.5` 等交叉引用是否有对应小节；
- 占位符是否只有 `{{AUTHOR}}`、`{{YYYY.M}}`、`{{SOFTWARE_NAME}}`、`{{VERSION}}`；
- 是否包含对话式需求协议：自然语言、需求理解、无需求引导；
- 是否残留"先填需求再发模板"的旧写法；
- 是否写死版权年月、是否残留 `2026.9`；
- 验收清单数量、行尾空白、超长行；
- 六份模板的语言与交付特征：Java 17 / jar / CentOS 指令、Rust exe、Android Kotlin / APK / minSdk 29、Vue `npm run serve` / `npm run build` / nginx / 不执行 npm；
- MySQL 只允许出现在 Java（后端）与 Android（通过 API）模板中；C++、Python、Rust、Vue 模板不得出现 MySQL / sqlx；
- 四个 UI 模板（C++ / Python / Android / Vue）必须包含“现代化设计、简洁大气、核心功能操作区突出、页面过渡 / 骨架屏”的要求；
- Android 环境指南的步骤总览与正文编号是否一致；
- 根 `readme.md`、`AGENTS.md`、`docs/`、`cache/` 与六份模板的必需文件是否齐全；
- 文档中的本地链接是否可打开；
- 是否残留 `templates/`、`guides/`、`examples/`、`CHANGELOG.md`、`LICENSE-SCOPE.md` 等旧路径。

校验失败时按 `[FAIL]` 行修复，不要通过删检查项来"通过"。

## 6. 自动化测试

```powershell
powershell -ExecutionPolicy Bypass -File tests/run-tests.ps1
```

测试覆盖：

1. `docs/*/template.md` 与 `parts/` 同步；
2. 完整仓库校验通过；
3. 生成物被手工改动会被拒绝；
4. 缺少 `L11` 章节会被拒绝；
5. 旧的"先填需求"写法会被拒绝；
6. `AGENTS.md`、`docs/readme.md`、`docs/develop-readme.md`、`cache/` 子目录、六份模板与源文件齐全。

调试时保留临时沙箱：

```powershell
powershell -ExecutionPolicy Bypass -File tests/run-tests.ps1 -KeepTemp
```

测试会在 `%TEMP%` 下复制一份仓库，在副本里做破坏性验证，不会改动当前工作区。

## 7. 新增一门语言模板

1. 复制现有模板（如 `parts/cpp.md`）为 `parts/<语言>.md`；
2. 改语言专属段落：L0、L2、L3、L4、L5、L6、L7~L9、L10/L11 的语言专项项；
3. 保留 `@@include common/*` 引用，公共规则不要复制粘贴；
4. 在 `scripts/build-templates.ps1` 的 `$sources` 里加一项；
5. 在 `docs/<语言>/template.md` 生成产物；
6. 在 `scripts/check-templates.ps1` 的模板列表、必需文件、语言特征里加一项；
7. 在 `AGENTS.md` 的语言映射表和根 `readme.md` 的模板表里加一行；
8. 运行生成、校验、测试。

## 8. 文档与资源约定

- 根 `readme.md`：面向使用者，产品介绍、价值、快速开始、FAQ，不写内部实现；
- `AGENTS.md`：面向 AI，按用户需求语言选择对应模板，不写产品文案；
- `docs/readme.md`：面向开发者，文档总览与索引；
- `docs/develop-readme.md`：面向开发者，环境、构建、校验、测试、发布、排错 + 变更记录；
- `docs/<语言>/template.md`：生成的 AI 提示词，不要手改；
- `docs/examples/conversation.md`：对话式需求示例；
- `docs/android/environment.md`：Android 编译环境指南；
- `docs/license.md`：许可范围说明；
- `parts/final-release-inno.md`：Windows 桌面程序最终发布包规范（Inno Setup），不参与模板拼接；
- `cache/screenshots/`：界面截图；
- `cache/images/`：图片、图标、照片；
- `cache/diagrams/`：架构图、流程图、示意图；
- `cache/videos/`：演示视频。

不同资源必须放进对应子目录，不要把文档、代码、截图混在 `cache/` 根目录。

生成软件的文档同样分工：根 `README.md` 面向使用者，`docs/readme.md` 与 `docs/develop-readme.md` 面向开发者；测试按语言标准放置（Java `src/test/java`、Rust `tests/`、Android `app/src/test` 与 `app/src/androidTest`、Vue `tests/unit/`）。

## 9. 版本与发布

版本格式 `YYYY.MM.N`，与 git tag 一致。

1. 更新本文件的「变更记录」，写清破坏性变更、修复、改进；
2. 运行生成、校验、测试；
3. 提交；
4. 打 tag：

```powershell
git add -A
git commit -m "docs: <变更摘要> (YYYY.MM.N)"
git tag -a vYYYY.MM.N -m "vYYYY.MM.N"
```

未发布的改动不要提前打 tag；变更记录顶部的版本号应与最新 tag 对应。

### 9.1 最终发布包（Inno Setup）

生成软件开发完成、`L10` 验收通过后，最终发布包统一使用 Inno Setup：

1. 按 `L6.7` 生成 `release/<SOFTWARE_NAME>_v<VERSION>_win-x64_<YYYYMMDD>/` 便携目录；
2. 在生成的软件中提供 `installer/<软件名>.iss` 与 `scripts/build-installer.ps1`；
3. 默认当前用户安装（`PrivilegesRequired=lowest`），安装到 `{localappdata}\Programs\<软件名>`；
4. 输出 `release/installer/<SOFTWARE_NAME>_v<VERSION>_win-x64_<YYYYMMDD>_setup.exe`；
5. 生成 `SHA256SUMS.txt` 与 `RELEASE-NOTES.md`；
6. 对外发布必须代码签名，并通过安装/启动/卸载/升级测试。

完整要求、`.iss` 骨架、签名、测试矩阵与验收清单见 [parts/final-release-inno.md](../parts/final-release-inno.md)。这是 Windows 桌面程序的唯一最终安装器选择，不要改用 NSIS、WiX/MSIX、QtIFW 或绿色 ZIP。

## 10. 编码与格式约定

- `.ps1` 脚本保持 **纯 ASCII**：Windows PowerShell 5.1 会按 ANSI 解析无 BOM 脚本，中文字符串会导致语法错误或乱码；需要中文时放在 `.md` 里。
- `.md` 使用 UTF-8（无 BOM）、LF 换行；`.gitattributes` 已统一。
- 不在模板里写死当前年月；用 `{{YYYY.M}}`，由生成或发布时取值。
- 不直接改 `docs/*/template.md`；所有修改先进 `parts/`。
- 本仓库的测试代码统一放 `tests/`；生成软件的测试按语言标准放置。
- 不在脚本里写开发机绝对路径。
- 所有文档放 `docs/`，所有资源放 `cache/` 的类型子目录；`parts/final-release-inno.md` 是唯一例外。

## 11. 常见排错

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `Missing ')'` / 花括号报错 | `.ps1` 里有中文，5.1 按 ANSI 解析 | 把脚本改回纯 ASCII，中文放 `.md` |
| `Get-Content` 读中文乱码 | 5.1 默认按 ANSI 读取 | 加 `-Encoding UTF8`，或用 .NET `ReadAllText(..., UTF8)` |
| 生成物首行有奇怪字符 | 源文件带 BOM | 保存为 UTF-8 无 BOM |
| `-Check` 提示 out of date | 改了 `parts/` 没重新生成 | 运行 `scripts/build-templates.ps1` |
| 校验报链接不存在 | 相对路径写错 | 按文件所在目录解析，修正链接 |
| 测试留下临时目录 | 用了 `-KeepTemp` | 手动删除 `%TEMP%\develop-tests-*` |
| 脚本无法执行 | 执行策略限制 | 加 `-ExecutionPolicy Bypass` |

## 12. 维护清单

- [ ] 只改 `parts/`，不直接改 `docs/*/template.md`
- [ ] 已运行 `build-templates.ps1`
- [ ] 已运行 `check-templates.ps1`
- [ ] 已运行 `tests/run-tests.ps1`
- [ ] 已更新本文件的「变更记录」
- [ ] 根 `readme.md` 仍是产品介绍，技术细节在 `docs/`
- [ ] `AGENTS.md` 的语言映射仍准确
- [ ] 文档在 `docs/`，资源在 `cache/` 子目录
- [ ] 最终发布包规范 `parts/final-release-inno.md` 未被误改，桌面程序发布已按它执行
- [ ] 本仓库测试仍在 `tests/`；生成软件按语言标准

---

## 变更记录

> 历史条目中的旧路径与旧规则仅作记录；当前规则以本文件上半部分和最新 `2026.11.0` 条目为准。

### 2026.11.0 — 2026-11-01

#### 最终发布包规范

- 新增 [parts/final-release-inno.md](../parts/final-release-inno.md)：Windows 桌面程序最终发布包**只使用 Inno Setup**；明确发布目录、`.iss` 硬性要求、构建脚本、签名、安装/卸载/升级行为、测试矩阵与验收清单。
- 根 `readme.md`、`AGENTS.md`、`docs/readme.md`、`docs/develop-readme.md` 增加“开发完成后最终打包”的入口与链接。
- 该规范是独立文档，**不参与六份模板的 `@@include` 拼接**；未修改 `parts/` 下已有的其他文档。

### 2026.10.7 — 2026-10-28

#### 页面加载过渡

- C++ / Qt6、Python / PySide6、Kotlin / Android、Vue 四份 UI 模板新增统一要求：
  “页面加载时必须有过渡，推荐使用骨架屏（Skeleton）占位。”
- 明确骨架贴近最终布局、数据返回后平滑切换、避免白屏/闪烁/布局跳动，超时或失败切换错误/重试。
- L10 验收清单新增“页面加载过渡/骨架屏”检查项。
- 校验脚本新增“骨架 / 过渡”关键词检查。
- Java 后端、Rust exe 不涉及 UI，不添加该要求。

### 2026.10.6 — 2026-10-28

#### UI 设计标准

- C++ / Qt6、Python / PySide6、Kotlin / Android、Vue 四份模板新增统一要求：
  “绘制 UI 界面时，采用现代化设计风格，整体简洁大气；核心功能操作区域应重点突出、清晰明朗，便于用户操作。”
- 同步补充主次分明、视觉统一、状态完整、可操作性等落地要求，并写入 L10 验收清单。
- 校验脚本新增 UI 设计关键词检查，防止四个 UI 模板回退。
- Java 后端、Rust exe 不涉及 UI，不添加该要求。

### 2026.10.5 — 2026-10-28

#### 数据库范围修正

- 明确 MySQL 8.0+ **只用于 Java 后端**；Android 通过 Java 的 HTTPS API 访问业务数据，不直连数据库。
- **C++、Python、Rust 的 exe 不接 MySQL；Vue 前端也不接 MySQL。**
- Rust 模板移除 sqlx、MySQL、迁移脚本、数据库表设计；需要持久化时改用本地 JSON/TOML 文件 + 原子写。
- Vue 模板移除 MySQL 相关描述，只说明数据通过 Java API 获取。
- 根 `readme.md`、`AGENTS.md`、`docs/readme.md`、校验脚本同步更新。
- 校验脚本新增：Java / Android 必须包含 MySQL 8.0+；C++ / Python / Rust / Vue 模板不得出现 MySQL / sqlx。

### 2026.10.4 — 2026-10-28

#### 结构调整

- 根目录新增 `AGENTS.md`：告诉 AI 按用户需求语言选择对应模板。
- 根 `README.md` 改为 `readme.md`，只保留面向使用者的产品介绍。
- 所有文档收进 `docs/`，按语言分目录：`docs/cpp/`、`docs/python/`、`docs/java/`、`docs/rust/`、`docs/android/`、`docs/vue/`。
- `templates/*.md` 迁移为 `docs/<语言>/template.md`。
- `guides/android.md` 迁移为 `docs/android/environment.md`。
- `examples/conversation-example.md` 迁移为 `docs/examples/conversation.md`。
- `LICENSE-SCOPE.md` 迁移为 `docs/license.md`。
- `CHANGELOG.md` 合并进 `docs/develop-readme.md` 的「变更记录」，删除根文件。
- 新增 `cache/`，按 `screenshots/`、`images/`、`diagrams/`、`videos/` 分类存放截图与资源。
- 删除空目录 `templates/`、`guides/`、`examples/`。

#### 同步更新

- `scripts/build-templates.ps1` 输出改为 `docs/<语言>/template.md`。
- `scripts/check-templates.ps1` 更新模板、文档、AGENTS、cache 路径与旧路径检查。
- `tests/run-tests.ps1` 更新沙箱与模板路径断言。
- 根 `readme.md`、`docs/readme.md`、`docs/develop-readme.md` 同步新结构。
版本规则：`YYYY.MM.N`，与 git tag 一致（如 `v2026.10.3`）。最新记录在上。

## 2026.10.3 — 2026-10-28

### 新增模板

- [Java 17 / Spring Boot / MySQL](java/template.md)：可执行 jar，Maven 标准结构，`scripts/run.bat`，`docs/centos-run.md`，API 面向 Android 10 ~ 最新版本客户端。
- [Rust / Windows exe / MySQL](rust/template.md)：Cargo 标准结构，Release exe，sqlx + MySQL 8.0+，`tests/` 集成测试。
- [Kotlin / Android 10+](android/template.md)：Compose + MVVM，最低 API 29，签名 APK，数据库只通过后端 API 访问。
- [Vue 3 / TypeScript / Vite](vue/template.md)：SPA，`npm run serve` / `npm run build` 由用户执行，AI 不编译、不打包，nginx 配置随源码交付。

### 通用规则

- 新增 `usage-generic`、`v0-v1-v2-generic`、`l1-version-generic`、`l6-3-docs-generic`、`l6-6-version-txt-generic`、`l11-items-generic` 公共片段，四份新模板复用，避免复制粘贴。
- 数据库统一 MySQL 8.0+：Java / Rust 直连，Android / Vue 只能通过后端 HTTPS API。
- Java 明确为服务端 jar，不能直接作为 Android 依赖；Android 10+ 通过 API 兼容。
- Vue 明确 AI 不执行 `npm install`、`npm run serve`、`npm run build`，由用户构建后用最新版 nginx 部署。

### 生成与校验

- `scripts/build-templates.ps1` 的 `$sources` 扩展到六份模板。
- `scripts/check-templates.ps1` 扩展到六份模板，新增语言 / 交付特征检查：
  - Java：Java 17、jar、centos-run.md、MySQL 8.0+；
  - Rust：Cargo、exe、MySQL 8.0+；
  - Android：Kotlin、apk、minSdk = 29、MySQL 8.0+；
  - Vue：npm run serve、npm run build、nginx、MySQL 8.0+、不执行 npm。
- `tests/run-tests.ps1` 增加六份模板与源文件的存在性检查。
- 根 README 改为六份模板的产品介绍，docs/ 同步更新仓库结构。

## 2026.10.2 — 2026-10-28

### 文档

- 根 `README.md` 改为面向使用者的产品介绍：这是什么、解决什么问题、怎么开始、FAQ，不再写仓库内部实现。
- 新增 `docs/readme.md`（开发者总览：仓库结构、生成机制、文档索引）。
- 新增 `docs/develop-readme.md`（开发与维护：环境、构建、校验、测试、发布、排错）。
- 模板同步文档分工：生成的软件根 `README.md` 面向使用者，`docs/readme.md` 与 `docs/develop-readme.md` 面向开发者，测试统一放 `tests/`。

### 测试

- 新增 `tests/run-tests.ps1`：验证生成物同步、仓库校验通过，并用临时沙箱验证模板漂移、缺少 L11、旧填表文案会被拒绝。
- 校验脚本新增 `docs/` 与 `tests/` 必需文件检查，以及 docs 文档的本地链接检查。

## 2026.10.1 — 2026-10-28

### 破坏性变更

- 需求区改为**对话式输入**：模板不再要求用户填写 `V0 ~ V2`，也不需要修改模板；`V0 ~ V2` 改为需求采集协议，由 AI 从对话中的自然语言提取。
- 示例由填写式 `examples/requirement-example.md` 改为对话式 `docs/examples/conversation.md`。

### 改进

- 新增"收到模板后的第一件事"：没有需求时只做简短引导，不写代码、不回贴空白表格；已有需求时先输出需求理解。
- 新增需求理解摘要格式（功能、系统能力、交付、覆盖、假设、待确认），无阻塞问题时摘要后直接开始，不空转等确认。
- 新增增量需求规则：后续补充覆盖先前说法；用户说"其他不变"时已确认需求继续有效；需求变更按 `L1.1` 说明版本影响。
- 新增自然语言到 `V2` 覆盖项的映射，例如"不要托盘，关闭直接退出"对应覆盖 `L4.3`。
- `L7` 开发步骤、`L8` 输出顺序、`L10` 验收清单、`L11` 禁止事项同步调整：没有需求不开工，需求理解先行，禁止要求用户填表。
- 校验脚本新增对话式需求检查：自然语言、需求理解、无需求引导，以及旧的"先填需求"写法。

## 2026.10.0 — 2026-10-28

### 破坏性变更

- 模板路径调整：`软件开发通用模板_c++.md` → `docs/cpp/template.md`，`软件开发通用模板_python.md` → `docs/python/template.md`，`Android编译环境搭建指南.md` → `docs/android/environment.md`。
- 版权串拼写由 `CopyRight` 统一为 `Copyright`；已生成的历史软件如需保持一致，请自行决定是否同步。
- 新增 `V0 身份参数`，作者与版权年月改为占位符 `{{AUTHOR}}`、`{{YYYY.M}}`，不再写死在固定区。
- 标题层级统一：`L0 ~ L11` 改为二级/三级标题，`L1.1`、`L4.1` 等改为子标题，所有交叉引用可解析。
- 版本真源位置调整：C++ 改为 `cmake/Version.cmake`，Python 保持 `core/version.py`。

### 修复

- 移除正文中写死的 `2026.9`，版权年月改为生成或发布时取系统当前年月。
- 修正 Android 指南"10 步"与实际 11 步不一致的问题，总览表与正文编号现已逐项对应。
- 删除对不存在的 `test\set-user-path.cmd`、`test\verify-android-env.cmd` 的引用，自检改为内联命令。
- 修正 `L1.1` 空引用：`L1` 增加 `L1.1 ~ L1.4` 子节。
- 替换从 Flash Builder 项目沿用的 `.gitignore`，改为文档仓库实际需要的规则。
- Android 指南：`setx VAR ""` 改为 `reg delete`；`curl` 增加 `-f`；解压前清理临时目录；重装 cmdline-tools 时使用带随机后缀的备份目录，避免 `move` 嵌套；镜像示例注明必须替换版本号。

### 改进

- 抽出 `parts/common/` 公共片段，`templates/` 由 `scripts/build-templates.ps1` 生成，消除两份模板约 80% 的逐行重复。
- 新增 `scripts/check-templates.ps1`：校验生成物同步、章节与交叉引用、占位符、过期年月、验收清单数量、指南步骤编号、本地链接与旧路径。
- 模板新增条款：Qt / PySide6 的 LGPL 合规与第三方许可清单、依赖锁定与可复现构建、单实例实现方式、未处理异常落盘、高 DPI manifest、日志轮转与保留、配置原子写与损坏回退、版本同步与一致性校验脚本、`SHA256SUMS.txt`、代码签名与 SmartScreen 提示。
- 需求区 `V1` 改为结构化表单，新增 `examples/requirement-example.md`。
- 输出规则新增：禁止编造 API / 版本 / 测试结果，未实际执行的验证必须注明，分批输出需标注批次。
- Python 入口统一：`app/main.py:main()` 为唯一实现，根 `main.py`、`__main__.py`、`gui-scripts` 只做薄包装。
- 新增 `.gitattributes`，统一 Markdown 为 LF、脚本为 CRLF。
- README 重写：增加目录、模板选择表、定制与校验流程、许可范围、常见问题。

### 文档

- 新增 `docs/license.md`，明确模板文本与生成物的许可边界。
- 新增 `docs/develop-readme.md`（本文件）。
