# 最终统一源的原生与标准流回归

在包含静态 stdio 与 GNU READY 修复的统一公开源
`299ea47cc991fb781e8671c41213a02c169f4130` 上完成最终原生组合回归。
本组只增加证据，不改生产源码、测试实现或 ABI。

独立执行目录由完整 Git archive 构成：8,837 文件在复制前后逐字核对；
编译源独立复制，纯 docs 作为不变输入共享硬链接以节省空间，没有文件 overlay。
实际 native build 为 `faad61f4f20be0f7`，其 2,207 项源清单全部匹配同一
revision。使用这套新 SDK 重新构建四套 fixture，然后顺序启动 QEMU。

| 检查 | 最终结果 | 资源恢复 |
|---|---|---|
| Controller 11 场 × 3 | 33/33 | 每次 129778 / 2 / 0 |
| IPC 生命周期、authority、quota 4 模式 × 3 | 12/12 | 每次同上 |
| IPC deadline 6 条件 × 3 | 3/3 套件调用 | 每次同上 |
| Static stdio 15 场 × 3 | 45/45，12 次真实 ELF 子进程 | 每轮同上 |

保留原套件全部轮数、实际 blocked 收发事件、真实同 PID exec、认证重启、
过期 ACK/ALLOW 恢复及严格资源断言。stdio 四项正例与十一项拒绝边界全部
通过，关机后的离线 Files 文件读回未变。没有失败尝试，也未降低门槛。

命令采用既有 `build_launch_control_probe.py`、`build_ipc_exec_probe.py`、
`build_ipc_deadline_probe.py`、`build_static_stdio_probe.py`，随后运行
`launch_control_guest.py --repeat 3`、`ipc_exec_guest.py --repeat 3
--serial-only --suite lifecycle`、同 runner 的 `deadline` 模式，以及
`static_stdio_compat_guest.py --repeat 3`。全部在 Preview 2 SDK 内执行，
完整参数、真实工具版本、source/SDK/ELF 摘要和串口见
[最终原生报告](../reports/p0_final_native_20261128/README.md)。

旧 c157 结果保持历史原件，不换源、不改摘要、不借用旧资源数值。GNU 公共
运行库、R2 代际切换和 R1 原始 1024 四冷启动仍由最终各自产物单独完成。
主任务负责更新 state/计划及合并 PR；本组未操作这些共享文件。
