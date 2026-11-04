# AGENTS.md

本文件是 **AI 的导航入口**。用户只会看到根 [readme.md](readme.md)；你在开始写代码前，先读本文件，再按用户需求选择对应的开发模板。

## 1. 先判断用户要做什么

| 用户需求里的信号 | 读取哪份模板 | 附加文档 |
| --- | --- | --- |
| C++、Qt、Qt6、CMake、Windows 桌面、exe | [docs/cpp/template.md](docs/cpp/template.md) | — |
| Python、PySide6、PyInstaller、Windows 桌面 | [docs/python/template.md](docs/python/template.md) | — |
| Java、Java 17、Spring Boot、jar、后端、REST API、CentOS | [docs/java/template.md](docs/java/template.md) | 模板要求生成 `docs/centos-run.md` 与 `scripts/run.bat` |
| Rust、Cargo、exe | [docs/rust/template.md](docs/rust/template.md) | — |
| Android、Kotlin、APK、安卓 10、Compose | [docs/android/template.md](docs/android/template.md) | [环境搭建](docs/android/environment.md) |
| Vue、Vue 3、TypeScript、Vite、前端、npm、nginx | [docs/vue/template.md](docs/vue/template.md) | — |

规则：

- **不要猜**。用户没说语言或交付形态，且无法从上下文判断时，先问一句。
- **不要一次读六份**。只读与当前需求匹配的一到两份，避免上下文污染。
- **多端项目读多份**。例如“Java 后端 + Android + Vue 管理端”要读三份，并保证 API 契约一致。
- 用户明确要求换技术栈时，按对应模板走；没有对应模板就说明不支持，不要硬套。

## 1.1 最终发布包（开发最后一步）

- **触发**：用户说“满意了”“可以发布”“打包最终版”“出安装包”“生成发布包”。
- **先决条件**：`L10` 验收通过；`release/` 下的便携目录已按 `L6.7` 生成并通过检查。
- **唯一选择**：只按 [parts/final-release-inno.md](parts/final-release-inno.md) 使用 **Inno Setup** 生成最终安装包；不得改用 NSIS、WiX/MSI、MSIX、QtIFW，也不得用绿色 ZIP 代替安装包。
- **执行**：读完整规范，按其中的发布目录、`.iss` 硬性要求、构建脚本、签名、测试矩阵和验收清单执行。
- **失败**：Inno 缺失、编译失败、签名失败、测试失败时停下报告，不得伪造“已发布”。

## 2. 选定模板后怎么用

1. **整份读取**对应模板，不要只读 `V0 ~ V2` 或只读 `L3`。
2. 模板是固定规范，**不要修改模板文件**。
3. 需求由用户在对话里用自然语言给出，按模板的 `V0 ~ V2` 协议采集：
   - 对话里还没有需求：只回一段简短引导，不写代码；
   - 已有需求：先输出 10 行以内的“需求理解”，再按 `L7` 开始；
   - 有阻塞问题：最多问 3 个并停下；没有就直接继续。
4. 不要要求用户填表，也不要把空白 `V0 ~ V2` 回贴给用户。
5. 用户后续补充、修改、撤销需求时，以最新明确表述为准，并说明版本与交付影响。

## 3. 多端项目的硬约定

- **MySQL 8.0+ 只属于 Java 后端**；Android 通过 Java 的 HTTPS API 访问业务数据；
- **C++、Python、Rust 的 exe 不接 MySQL，Vue 前端也不接 MySQL**；
- Android 不得直连 MySQL；Vue 不得直连 MySQL 或持有数据库凭据；
- Java 模板是服务端 jar，不是 Android 依赖；
- Android 最低 API 29（Android 10），向最新稳定版本适配；
- Vue 由用户执行 `npm run serve` / `npm run build`，AI **不执行 npm**，最终用最新版 nginx 部署；
- Java / Rust / Android / Vue 的接口字段、错误码、分页、鉴权必须一致；以 Java 模板要求生成的 `docs/api.md` 为契约源（这是目标项目里的文档，不是本仓库文件）。

## 4. 文档地图

| 路径 | 用途 |
| --- | --- |
| [readme.md](readme.md) | 面向使用者的产品介绍、快速开始、FAQ |
| [docs/readme.md](docs/readme.md) | 面向开发者的文档总览与索引 |
| [docs/develop-readme.md](docs/develop-readme.md) | 开发、构建、校验、测试、发布说明 + 变更记录 |
| [docs/license.md](docs/license.md) | 许可范围说明 |
| [docs/examples/conversation.md](docs/examples/conversation.md) | 对话式需求示例 |
| [docs/android/environment.md](docs/android/environment.md) | Android 编译环境 |
| [parts/final-release-inno.md](parts/final-release-inno.md) | 最终发布包规范（Inno Setup） |
| `docs/<语言>/template.md` | 六份可直接使用的 AI 提示词 |
| `cache/screenshots/` | 界面截图 |
| `cache/images/` | 图片、图标、照片 |
| `cache/diagrams/` | 架构图、流程图、示意图 |
| `cache/videos/` | 演示视频 |

## 5. 维护本仓库时

- 模板源在 `parts/`，生成物在 `docs/<语言>/template.md`；
- **不要手改生成物**，改 `parts/` 后运行 `scripts/build-templates.ps1`；
- 运行 `scripts/check-templates.ps1` 与 `tests/run-tests.ps1`；
- 变更记录写在 [docs/develop-readme.md](docs/develop-readme.md) 的「变更记录」，不再单独维护 `CHANGELOG.md`；
- 最终发布包规范是 `parts/final-release-inno.md`，它是独立规范，不参与六份模板的 `@@include` 拼接；
- 新文档放 `docs/`，新资源放 `cache/` 对应子目录；不要把文档、代码、截图混在根目录。

## 6. 禁止事项

- 禁止把文档写到 `docs/` 之外（根 `readme.md`、`AGENTS.md`、`LICENSE` 与 `parts/` 下的规范源文件除外）；
- 禁止把截图、图片、视频直接丢在 `cache/` 根目录；
- 禁止编造模板里不存在的文件、命令或版本；
- 禁止声称执行过未执行的命令；没有环境时标注“未验证”；
- 禁止忽略用户明确提出的需求或 `V2` 覆盖项。

## 7. 最短路径

- 用户说“做个 C++ 桌面工具”：读 `docs/cpp/template.md`；
- 用户说“做个 Java 后端给安卓用”：读 `docs/java/template.md`，必要时再读 `docs/android/template.md`；
- 用户说“做个 Vue 管理后台”：读 `docs/vue/template.md`，提醒用户自行 `npm run serve` / `npm run build`；
- 用户说“做个安卓 App”：读 `docs/android/template.md`，需要配环境时再读 `docs/android/environment.md`；
- 用户说“满意了/可以发布/打包最终版”：读 `parts/final-release-inno.md`，按规范生成 Inno Setup 安装包。
