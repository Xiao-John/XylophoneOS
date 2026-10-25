# `ps`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `xsh>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

列出存活/构造中的任务、PID、名字、状态和 tick。N=未首次运行，B=构造中，r=就绪，R=运行，W=等待。
死任务不列出；内部上限 8 个任务。不是完整的进程属性或资源监控。

[返回索引](../index.md)

