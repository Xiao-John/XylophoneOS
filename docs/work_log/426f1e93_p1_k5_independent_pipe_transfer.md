# P1-K5：独立 pipe 对象的有界显式传输

日期：2026-11-28。实现基线 `45865da20dd9908d69e81e0c5a5ef5f908e11cc8`。
ABI 由独立 PR #447 预登记；本次不增加 syscall 编号，不扩大 FD 或 pipe 上限。

sys34 新显式 mode 使用 144 字节 v1 批次，将 caller 持有的 private pipe
references 授予其 ordinary building child。整个请求、每个 token、容量和
输出 COW 准备全部通过后才 retain/copyout。fork/replacement pending、外部
token、重复项、非零 reserved/unused/target、已持有 token 和超额都明确拒绝，
失败不写输出也不部分授予。原对象 owner/budget_mask 不变；原域只在最后
引用消失时归还 object credit。

native loader 增加默认关闭的 `transfer_independent_pipes` option。匹配的
GNU inherited-FD bridge 显式开启，按 open description 去重后一次传输，
每个别名使用同一 child token。默认 caller 仍拒绝未路由 pipe。同 PID exec
保留旧句柄，与新批量模式不能混用；后续 map/callback 失败通过 abort 清理。
完整语义见 [契约](../contracts/independent_pipe_transfer.md)。

## 实测结果

最终 system `fed3580022aa4bb3` 配合新建 authenticated glibc 2.44 / GCC
16.2.0 SDK，通过 **16 场真实客体运行**：6 个原生场景各跑两轮，两个 GNU
探针分别通过 xsh 和从同一 SDK 重建的 dash 执行。GNU 程序只链接已经打包的
生产 `libxos_terminal.a`，没有替换 loader 对象。每场资源恢复精确基线。

原生场景覆盖 readonly 跨页输出、末项失败的整批原子性、两个 pending
状态、16 refs（含 3 stdio routes）超额与释放后重试、原域预算保持、默认
拒绝、实际 map 后 callback 失败回收、真实 child 的方向和未授予 token 拒绝。
GNU 覆盖已有 route 行为、独立别名/共享 flags/CLOEXEC、child 仍存活时
last-close EOF、EPIPE、失败和成功 exec，以及 8 objects / 16 endpoints /
32 FDs 的完整边界。每场结束后并在最终导出时重验所有绑定。

最初原生开发轮的前五场通过，第六场探针把现有无权限错误期待为 invalid；
生产内核按原契约返回 denied。修正探针并保留原失败记录后，六场开发轮和
最终完整 16 场通过。最终 system 在修正后的全部 source 冻结后重建；旧
system 的开发记录不作为最终源码验收。

公开原始串口与完整源码/SDK/工具/产物绑定见
[验收报告](../reports/p1_k5_pipe_transfer_20261128/README.md)。本轮资格为 native
SDK 和静态 GNU libc 的实际执行；共享 GNU 动态 image 的独立 pipe 场景需要
其自身 matching runtime 资格，不借用本轮静态结果。没有声明 SMP 或物理
硬件资格。
