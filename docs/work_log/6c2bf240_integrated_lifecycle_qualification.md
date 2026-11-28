# 最终集成源码的原生生命周期复验

用户要求继续完成 P0 并合并相关 PR。本记录补齐 P0-L1/L2 表中要求的
final integrated source 客体验收，不改变内核或用户态生产实现。

来源固定为 `3699916df590a2fe0ea9b419836ded2d9344e6b3`，native system build
为 `c1575e2adfc6fa5d`。独立完整 Git 导出不叠加测试改动，2,196 个 system
manifest 源文件逐一一致；使用该产物的导出 SDK 重新构建 controller、IPC
exec/lifetime、deadline 三个 fixture，guest 前后复核全部来源与产物。

| 套件 | 真实调用 | 原有轮数 | 每次资源恢复 |
|---|---:|---:|---|
| launch control | 33/33 | 11 cases × 3 | 129779 pages / 2 tasks / 0 completions |
| IPC lifecycle/authority/quota | 12/12 | 4 modes × 3 | 同上 |
| IPC absolute deadline | 3/3 | 6 条件 × 3 | 同上 |

三个 QEMU 顺序运行并全部正常结束。L1 每轮覆盖实际 blocked 的收/发 worker，
包括 revoke、close、exit、fault、cancel；验证 failed-exec 权限保持、成功
exec 撤销、broken 结果、认证 restart 与 stale token 拒绝。L2 保持 owner
预算、故障原子性、peer 隔离、消息不因 timeout 丢失、全宽 deadline 及资源
收回断言。Controller 覆盖 READY/ACK、public wait pump、同 PID exec、
撤销及过期排队 ALLOW/CANCEL 恢复。

完整新 receipt、fixture SHA、system source/artifact map、实际串口与导出规则
见 [最终 native 报告](../reports/p0_integrated_lifecycle_20261128/README.md)。
本次不借用旧 guest 结果，不把 per-PID quota 解释为进程树预算；持久跨后代
撤销仍在 P1。GNU 新 capsule 的动态运行和 R2 代际资格使用各自全新产物单独
执行，不包含在本记录的 48 次原生套件调用中。
