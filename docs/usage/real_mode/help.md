# `help`

- 控制台：实模式练习控制台（`make run_real_mode`，提示符 `xos> `）
- 语法：`help`
- 实现：`src/boot/x86/stage_two.asm`

## 行为

输出一行命令列表：

```text
help  about  clear  halt
```

命令区分大小写，只接受小写；不接受参数。

## 失败与边界

- 未知命令输出 `ERROR: unknown_command; type help`。
- 这里只有四个命令；它不控制内核控制台，也不加载内核。

## 相关

- [索引](../index.md)、[about](about.md)
