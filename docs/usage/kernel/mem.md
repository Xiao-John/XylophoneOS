# `mem`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`mem`
- 实现：`src/kernel/core/console.cpp` 调用 `memory_status`

## 行为

输出两行：物理页统计与当前分配窗口。

示例（数字随任务创建与自检变化）：

```text
[mem] usable_kib=65023 managed_kib=65408 pages=16352 free=16077 allocated=2
[mem] window=0x0000000000100000..0x0000000003fe0000
```

字段含义：

| 字段 | 含义 |
|---|---|
| `usable_kib` | E820 报告为 usable 的总量，未经上限裁剪 |
| `managed_kib` | 位图实际管理的范围，上限 128 MiB，且不超过最高可用地址 |
| `pages` | 管理的 4 KiB 页总数 |
| `free` | 当前可分配页数 |
| `allocated` | 当前由分配器持有的页数，包含页表页、用户页与任务内核栈 |
| `window` | 可分配物理地址区间，低端从 1 MiB 起 |

`allocated` 不为 0 不一定是泄漏：启动时会创建用户任务，`vmtest` 也会保留按需分配的中间页表页。
`free` 只统计物理页，不统计页表结构本身。

## 失败与边界

- 无参数；带参数会按未知命令处理。
- 数字是启动阶段快照，不是长时间运行的内存压力结论。
- 不代表已经验证耗尽、回收或碎片行为。

## 相关

- [alloc](alloc.md)、[free](free.md)、[vmtest](vmtest.md)
- 设计说明：`docs/architecture_and_boot.md` 的 E02 内存章节
