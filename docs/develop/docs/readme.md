# 开发者文档

> 面向本仓库的维护者与贡献者。产品介绍见根 [readme.md](../readme.md)，AI 导航见 [AGENTS.md](../AGENTS.md)。

## 1. 文档分工

| 文件 | 读者 | 内容 |
| --- | --- | --- |
| [readme.md](../readme.md) | 使用者 | 这是什么、有什么用、怎么开始、常见问题 |
| [AGENTS.md](../AGENTS.md) | AI | 按用户需求语言选择模板、使用规则 |
| [parts/final-release-inno.md](../parts/final-release-inno.md) | 开发者 / AI | 最终发布包规范（Inno Setup） |
| `docs/readme.md` | 开发者 | 文档总览、仓库结构（本文件） |
| [docs/develop-readme.md](develop-readme.md) | 开发者 | 环境、生成、校验、测试、发布、变更记录 |
| [docs/license.md](license.md) | 开发者 / 使用者 | 许可范围说明 |
| [docs/examples/conversation.md](examples/conversation.md) | 使用者 | 对话式需求示例 |
| [docs/android/environment.md](android/environment.md) | 开发者 / 使用者 | Android 编译环境搭建 |
| [docs/cpp/template.md](cpp/template.md) 等六份语言模板 | 使用者 / AI | 可直接复制的提示词成品 |

根 `readme.md` 只做产品介绍和上手，`AGENTS.md` 只做 AI 导航，本目录只写技术细节。三者不混写。

## 2. 仓库结构

```text
develop/
├─ AGENTS.md                    # 面向 AI：语言 → 模板映射
├─ readme.md                    # 面向使用者：产品介绍
├─ docs/
│  ├─ readme.md                 # 面向开发者：总览（本文件）
│  ├─ develop-readme.md         # 开发指南 + 变更记录
│  ├─ license.md                # 许可范围
│  ├─ examples/
│  │  └─ conversation.md        # 对话式需求示例
│  ├─ cpp/template.md
│  ├─ python/template.md
│  ├─ java/template.md
│  ├─ rust/template.md
│  ├─ android/
│  │  ├─ template.md
│  │  └─ environment.md
│  └─ vue/template.md
├─ cache/                       # 资源，按类型分子目录
│  ├─ screenshots/
│  ├─ images/
│  ├─ diagrams/
│  └─ videos/
├─ parts/                       # 6 份语言模板 + 最终发布规范
│  ├─ common/                   # 六份语言模板共用的段落
│  ├─ final-release-inno.md     # 最终发布包规范（不参与拼接）
│  └─ <语言>.md
├─ scripts/
│  ├─ build-templates.ps1       # 由 parts/ 生成 docs/<语言>/template.md
│  └─ check-templates.ps1       # 结构、引用、链接、语言特征校验
├─ tests/
│  └─ run-tests.ps1             # 本仓库自动化测试
├─ LICENSE
├─ .gitignore
└─ .gitattributes
```

## 3. 七份文档

`parts/` 下共 **7 份文档**：6 份语言模板 + 1 份最终发布规范。最终发布规范不参与模板生成，只在开发完成、准备出安装包/发布包时使用。

| 文档 | 技术栈 / 用途 | 测试标准位置 |
| --- | --- | --- |
| C++ / Qt6 | [docs/cpp/template.md](cpp/template.md) | CTest + `tests/` |
| Python / PySide6 | [docs/python/template.md](python/template.md) | `tests/` |
| Java 17 / Spring Boot | [docs/java/template.md](java/template.md) | `src/test/java` |
| Rust | [docs/rust/template.md](rust/template.md) | 模块单测 + `tests/` |
| Kotlin / Android | [docs/android/template.md](android/template.md) | `app/src/test` + `app/src/androidTest` |
| Vue 3 / TypeScript | [docs/vue/template.md](vue/template.md) | `tests/unit/` |
| 最终发布规范 | [parts/final-release-inno.md](../parts/final-release-inno.md) | 开发完成后的最后一步（不适用语言测试） |

## 4. 生成机制

- **模板源**：`parts/common/` 存六份语言模板共用的规则，`parts/<语言>.md` 存语言专属规则。
- **生成物**：`docs/<语言>/template.md` 由 `scripts/build-templates.ps1` 生成，**不要直接编辑**。
- **引用方式**：源文件里用 `@@include common/文件名.md` 引入公共片段；生成时递归展开。
- **编码约定**：生成物统一 UTF-8（无 BOM）、LF 换行，保证可重复生成、diff 干净。
- **文档分工**：根 `readme.md` 面向使用者，`AGENTS.md` 面向 AI，`docs/` 面向开发者。

改一条公共规则只需要动 `parts/common/` 一处，不会出现多份模板改了一边忘了另一边。

## 5. 常用命令

```powershell
# 生成 docs/<语言>/template.md
powershell -ExecutionPolicy Bypass -File scripts/build-templates.ps1

# 只校验生成物是否与 parts/ 同步
powershell -ExecutionPolicy Bypass -File scripts/build-templates.ps1 -Check

# 结构、引用、链接、AGENTS/cache、语言特征等完整校验
powershell -ExecutionPolicy Bypass -File scripts/check-templates.ps1

# 本仓库自动化测试
powershell -ExecutionPolicy Bypass -File tests/run-tests.ps1
```

## 6. 文档与资源规则

- 所有给人看的文档放 `docs/`，按语言或用途分目录；`parts/` 只放模板源与最终发布规范，属于例外；
- 根目录只放 `readme.md`、`AGENTS.md`、`LICENSE` 和工具目录；
- 图片放 `cache/images/`，截图放 `cache/screenshots/`，图例放 `cache/diagrams/`，视频放 `cache/videos/`；
- 不把截图、图片、临时文件混放在 `cache/` 根目录；
- `docs/*/template.md` 是生成物，修改请改 `parts/`；
- 变更历史统一记录在 [docs/develop-readme.md](develop-readme.md) 的「变更记录」，不再单独维护 `CHANGELOG.md`。

## 7. 模板产出的软件同样遵守文档分工

这条规则写进了各模板的 `L6.3`：

- 根 `README.md`：面向使用者（**生成软件**的根文档），产品介绍、功能、安装 / 启动、FAQ；
- `docs/readme.md`：面向开发者，架构、模块、数据流、接口；
- `docs/develop-readme.md`：面向开发者，环境、构建、测试、打包、部署；
- 最终发布：Windows 桌面程序统一用 **Inno Setup**，规范见 [parts/final-release-inno.md](../parts/final-release-inno.md)；安装包产物放 `release/installer/`，不混进 `docs/`；
- 测试代码按语言标准放置，不强制全部塞进根 `tests/`。

## 8. 下一步

- 想改模板或加语言：看 [开发与维护指南](develop-readme.md)；
- 想先跑一遍：看 [测试脚本](../tests/run-tests.ps1)；
- 想了解许可：看 [docs/license.md](license.md)；
- 想做最终发布包：看 [最终发布包规范](../parts/final-release-inno.md)；
- 想用 AI 开发：从 [AGENTS.md](../AGENTS.md) 开始。
