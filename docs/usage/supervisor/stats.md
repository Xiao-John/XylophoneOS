# `stats`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `xsh>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

显示真实物理空闲页数、当前任务数与未收集完成记录数。
适合在 exec/故障/终止前后核对回收。只读、不分配测试页，不是每任务精确配额统计。

[返回索引](../index.md)

