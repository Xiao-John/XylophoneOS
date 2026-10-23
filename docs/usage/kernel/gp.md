# `gp`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`gp`
- 实现：`src/kernel/arch/x86_64/exceptions.cpp`（执行 `int $0x30`）

## 行为

IDT 只为向量 0–31 安装了门；软件中断 `int 0x30` 命中不存在的门，触发
general protection。输出包含选择子错误码：

```text
[panic] vector=13 general_protection error=0x0000000000000182
[panic] rip=0x0000000000101bae cs=0x0000000000000008 rflags=0x0000000000010002
[panic] result=halt
```

错误码 `0x182` = `(0x30 << 3) | 2`，用于定位缺失的 IDT 索引。

## 失败与边界

- 不验证用户态越权；当前没有 ring3。
- panic 后停机，需要重启 QEMU。
- 只覆盖“门不存在”这一种 #GP，不代表其他 #GP 原因已验证。

## 相关

- [pf](pf.md)、[ud](ud.md)、[div](div.md)、[df](df.md)
