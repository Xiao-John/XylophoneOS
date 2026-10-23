# `halt`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`halt`
- 实现：`src/kernel/core/console.cpp` 调用 `arch::halt`

## 行为

先输出：

```text
HALTED: CPU resting; close QEMU to exit.
```

随后关中断并进入 `hlt` 循环。QEMU 进程不会自行退出，宿主终端用 `Ctrl-C` 结束。
QEMU monitor 的 `info registers` 应显示 `HLT=1`。

## 失败与边界

- 停机后控制台不再接收命令，必须重启 QEMU。
- 不是关机、不是 ACPI 电源管理，也不保存任何状态。
- 不影响宿主文件；镜像只读。

## 相关

- [索引](../index.md)
- 实模式 [halt](../real_mode/halt.md) 行为相同
