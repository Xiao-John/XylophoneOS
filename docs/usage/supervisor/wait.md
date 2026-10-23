# `wait <pid>`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `sup>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

只收集本 supervisor 创建的子任务，尚未结束就阻塞。按 Escape 可监督终止
被等待子任务并恢复终端。结果区分 exited（有符号 32 位退出码）、faulted（vector/
地址/指令）和 killed（-9 监督终止，-27 Escape）。结果只可收集一次；重复 wait、
非子任务或不存在的 PID 返回 error=-1。它不是等待任意全局 PID 的权限。
结果与资源分开保存：任务页可以先回收，状态保留到 wait。

[返回索引](../index.md)

