#### L6.7 发布包

- 命名：`{{SOFTWARE_NAME}}_v{{VERSION}}_win-x64_YYYYMMDD`。
- 根目录必须包含：可执行文件、`README.md`、`docs/`、`config/`、`logs/`、`VERSION.txt`、`THIRD-PARTY-NOTICES.md`、许可文件。
- 同时生成 `SHA256SUMS.txt`，并在发布说明中给出校验命令。
- 包内不得包含源码、构建中间产物、`.git`、开发机路径、密钥或测试数据。
