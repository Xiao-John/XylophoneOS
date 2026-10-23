# `spawn <image> [args]`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `sup>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

与 exec 使用同一个用户态装载器，但提交后立即打印子任务 PID 并返回终端。
例如 spawn spin 后可 ps、kill <pid>、wait <pid>。不会自动收集结果；未收集记录
达到 16 份时拒绝新建任务，需 wait 释放记录。当前最多 8 个任务（含启动演示任务）。
stdin 也会继承；没有前后台 TTY 控制，后台读取输入的程序可能与 supervisor 竞争。

[返回索引](../index.md)

