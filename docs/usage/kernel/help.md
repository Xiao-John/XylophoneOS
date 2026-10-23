# `help`

- 控制台：内核调试控制台（`make run`，提示符 `xos64> `）
- 需要彩蛋：否
- 语法：`help`
- 实现：`src/kernel/core/console.cpp`

## 行为

输出当前可用命令名，一行列出：

```text
help mem alloc free vmtest run pf gp ud div df halt
```

彩蛋开启时追加 `guo joke about`：

```text
help mem alloc free vmtest run pf gp ud div df halt guo joke about
```

不接受参数；`help mem` 不会被解析成对单条命令的帮助，而会作为未知命令处理。
具体命令说明请看本手册索引中的对应页面。

## 失败与边界

- 输入包含空格或多余字符：整行不匹配，返回 `ERROR: unknown_command`。
- 大小写敏感：`HELP` 不会命中。
- 本手册在宿主侧；内核控制台没有文件命令，`help` 不能打开 Markdown。

## 相关

- [索引](../index.md)
- [about](about.md)（彩蛋开启时）
