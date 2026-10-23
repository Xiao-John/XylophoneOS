# `halt`

- 控制台：实模式练习控制台（`make run_real_mode`）
- 语法：`halt`
- 实现：`src/boot/x86/stage_two.asm`

## 行为

输出：

```text
HALTED: CPU resting; close QEMU to exit.
```

关中断并进入 `hlt` 循环；QEMU 进程不退出，宿主用 `Ctrl-C` 结束。
寄存器检查应显示 `HLT=1`。

## 失败与边界

- 不是关机或 ACPI 电源操作。
- 停机后不能继续输入，需要重启 QEMU。
- 与内核控制台的 `halt` 是两套实现，行为相似但镜像不同。

## 相关

- [索引](../index.md)、内核 [halt](../kernel/halt.md)
