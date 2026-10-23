# `div`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`div`
- 实现：`src/kernel/arch/x86_64/exceptions.cpp`（`div` 除数为 0）

## 行为

执行一条除数为零的除法，触发 divide error：

```text
[panic] vector=0 divide_error error=0x0000000000000000
[panic] rip=0x0000000000101bb9 cs=0x0000000000000008 rflags=0x0000000000010046
[panic] result=halt
```

随后 HLT，需要重启 QEMU。

## 失败与边界

- 不模拟用户态 SIGFPE；当前没有用户态。
- 只验证 #DE 入口与 panic 输出。

## 相关

- [pf](pf.md)、[gp](gp.md)、[ud](ud.md)、[df](df.md)
