#### L6.6 VERSION.txt

发布包根目录必须包含 `VERSION.txt`，由构建或版本脚本从唯一真源生成，至少包含：

```text
软件名称：{{SOFTWARE_NAME}}
版本号：{{VERSION}}
作者：{{AUTHOR}}
版权：Copyright © {{AUTHOR}} {{YYYY.M}}
构建日期：YYYY-MM-DD
目标平台：Windows 10 / 11 x64
许可：<生成物许可>
```

- 构建日期取打包当天，不得写死。
- `VERSION.txt` 禁止手写；一致性校验脚本必须校验其版本号与真源一致。
