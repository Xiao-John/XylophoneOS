# `df`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`df`
- 实现：`src/kernel/arch/x86_64/exceptions.cpp`（坏栈 + `ud2`）

## 行为

故意把 RSP 设为未映射的 `0xdead0000`，再执行 `ud2`：

- `#UD` 投递需要往坏栈压帧，触发第二次异常；
- 处理器改用 TSS 的 IST1（8 KiB double-fault 栈）投递 `#DF`；
- 内核输出 `vector=8 double_fault`，随后 HLT。

输出示例：

```text
[panic] vector=8 double_fault error=0x0000000000000000
[panic] rip=0x0000000000101c42 cs=0x0000000000000008 rflags=0x0000000000000046
[panic] result=halt
```

这条命令实际验证 IST 配置，而不只是读取 IDT 字段。

## 失败与边界

- 如果 IST/TSS 配置错误，可能触发 triple fault 或 QEMU 退出；这是测试的价值。
- 没有异常恢复；panic 后需要重启 QEMU。
- 只覆盖 double fault 路径，不覆盖 NMI 的真实硬件投递。

## 相关

- [pf](pf.md)、[gp](gp.md)、[ud](ud.md)、[div](div.md)
