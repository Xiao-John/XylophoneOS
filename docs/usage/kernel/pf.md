# `pf`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`pf`
- 实现：`src/kernel/arch/x86_64/exceptions.cpp`（故意读 `0xdead0000`）

## 行为

读取未映射地址 `0xdead0000`，触发真实 page fault。内核异常入口输出：

```text
[panic] vector=14 page_fault error=0x0000000000000000
[panic] rip=0x0000000000101bc2 cs=0x0000000000000008 rflags=0x0000000000010046
[panic] cr2=0x00000000dead0000
[panic] result=halt
```

然后 HLT。`cr2` 是实际故障地址，`rip` 指向触发指令。

## 失败与边界

- 当前没有异常恢复：panic 后只能重启 QEMU。
- 该地址位于 low identity map 之外，故意制造故障；不是内存泄漏测试。
- 输出依赖异常入口和符号；若 RIP 缺失或 CR2 不对，说明异常路径有问题。

## 相关

- [gp](gp.md)、[ud](ud.md)、[div](div.md)、[df](df.md)
- 设计说明：`docs/architecture_and_boot.md` 的 E02 异常章节
