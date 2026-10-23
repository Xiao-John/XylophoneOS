# `vmtest`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`vmtest`
- 实现：`src/kernel/core/console.cpp` 调用 `memory_self_check`

## 行为

执行一次真实的内存自检：

1. 分配一个物理页；
2. 以可写、不可执行权限映射到虚拟地址 `0x40000000`；
3. 写入并读回 `0x1122334455667788`；
4. `query_page` 检查物理地址与权限；
5. 再次映射，确认返回 `already_mapped`；
6. 解除映射并释放物理页。

通过时输出：

```text
[vm] event=self_check result=pass address=0x0000000040000000 physical=0x0000000000111000
vmtest result=pass
```

失败时输出 `[vm] event=self_check result=fail reason=...` 与 `vmtest result=fail`。
失败表示实现或页表状态异常，不是用户输入错误。

## 失败与边界

- 自检使用固定虚拟地址 `0x40000000`；如果该地址被别的映射占用，会失败。
- 第一次运行需要分配两层中间页表，这些页表页不会回收；之后重复运行复用它们。
- 不验证用户态权限、并发、页表拆分或内存耗尽。
- 启动阶段也会自动执行同一自检；失败则启动失败。

## 相关

- [mem](mem.md)、[alloc](alloc.md)、[free](free.md)
