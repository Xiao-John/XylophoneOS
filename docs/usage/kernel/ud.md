# `ud`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`ud`
- 实现：`src/kernel/arch/x86_64/exceptions.cpp`（执行 `ud2`）

## 行为

执行非法指令 `ud2`，触发 invalid opcode：

```text
[panic] vector=6 invalid_opcode error=0x0000000000000000
[panic] rip=0x0000000000101bbb cs=0x0000000000000008 rflags=0x0000000000010046
[panic] result=halt
```

随后 HLT，需要重启 QEMU。

## 失败与边界

- 没有异常恢复。
- 该命令只验证 #UD 入口，不验证非法指令解码或用户态信号。

## 相关

- [pf](pf.md)、[gp](gp.md)、[div](div.md)、[df](df.md)
