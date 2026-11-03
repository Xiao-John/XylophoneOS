# 终端 fork 容量回滚重复验证

2026-11-02。现有 `terminal_exec_probe.cpp` 的 `capacity` 模式在两个终端子进程占用
通道额度时，检查原始 fork-pair 的资源不足、预留子进程中止和资源快照恢复；随后检查
libc `fork()` 失败、父进程终端仍可用、子进程退出后新的 fork 成功。单次通过不能
说明反复打开关闭后资源持续可用。

本次在真实 Xsh 客体同一会话内，先获取 `stats` 基线，再重复八次完整的 capacity
场景；每次要求正常退出，并检查空闲页、任务数和未领取结果数回到基线。回执保留每次
快照。该测试覆盖有界的顺序额度耗尽与恢复，不声称任意负载、所有竞争时序、线程 profile
或全量 W1 已通过。提交后必须基于该提交重建系统与 SDK，再运行客体探针；历史报告
不能代替新场景的验证。

提交 `df750cedd10eed0e46558a82670f223e577c1227` 的重建系统 build ID
`17e72b043275ff21`；客体八轮均通过，基线和每轮结束的 `(free_pages, tasks,
completions)` 都为 `(130091, 3, 1)`。报告 SHA-256
`0a2a1deb2ec0c14342d36bb157c717fe3199c6e1e061ca3f71cbf9be1cb4d5ef`，串口
SHA-256 `2887d2a06a2b70f910c776499c9330fc4eea9f725b6123539b1313b188cb67f9`，
均位于 `build/w1_capacity_guest_df750ce/`。复核发现原报告未自动绑定探针脚本与串口
哈希，现补充这两个字段并在测试结束前重验探针输入；更改后仍需提交并重新运行。

提交 `72d616557ffb36bd8052163afe82eaac30dd6490` 后重新构建，系统 build ID
`b3b160bc351f3928`；八轮仍全部通过，基线及每轮快照均为 `(130091, 3, 1)`。
报告位于 `build/w1_capacity_guest_72d6165/report.json`，其中绑定探针脚本、fixture、
系统、SDK 和串口；串口 SHA-256
`246fa304acb51af081366088a030ddb68be2fd56d549508eccda0754bc948c3e`。此结果仍为
`passed_subset`，不覆盖线程及 exec 在途竞争等未运行范围。
