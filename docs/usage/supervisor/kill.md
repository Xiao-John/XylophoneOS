# `kill <pid>`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `xsh>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

请求监督终止任务，并回收用户页、页表和内核栈。不能终止自己或 supervisor。
新 ELF 子任务留下 kind=killed、code=-9 的完成结果，需用 wait 收集；旧演示任务不是
supervisor 的子任务，没有可收集结果。非法 PID 返回 kill: invalid pid。
普通 ELF 程序没有该监督权限。

[返回索引](../index.md)


E08-1 起 files 块设备服务与 supervisor 同为受保护 bootstrap 服务，kill 拒绝终止它们；
不提供文件服务自动重启。普通子任务仍可终止并 wait。
