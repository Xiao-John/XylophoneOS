# 0208 — SL0：双 Shell 启动与权限继承契约冻结

2026-11-05。分支 `codex/sl0_shell_launch`（基于 main `8d186fd8`）。
按 [shell_launch 计划](../plans/shell_launch.md) 完成 **SL0：冻结契约**。

## 范围

核对 fork/spawn/exec、服务与维护启动的权限与资源现状；产出专项契约与双轨兼容表；
约定 SL1 新接口登记方式。**不含**内核机制实现（SL1）、Shell 接入（SL2）。

## 交付

- **[docs/contracts/shell_launch.md](../contracts/shell_launch.md)**：
  - §2 现状表：xsh/dash 全部启动入口 → 授权映射；内核 16/28/37/57–62 深度语义；
    `spawn_options` 字段与二进制兼容注意；资源与失败约束。
  - §3 双轨兼容表：旧轨（`spawn_depth`+按名特判）原样保留；新轨六条硬规则冻结
    （身份承载创建权、spawn≡fork+exec、exec 不复权、名称/PATH/ELF 不授予权利等）。
  - §4 名称特判退役清单（supervisor dash/make、jobs_xos gcc/make、exec-driver）。
  - §5 ABI：SL0 **不占号**；SL1 走 reserved 段 84–95 登记流程。
- 计划状态行更新为「SL0 已冻结」。

## 关键实测依据（main `8d186fd8`）

- `process_max_spawn_depth = 3`（`process_abi.hpp:124`）。
- `sys_process_grant`（28）置深度 0/1；`sys_process_delegate`（37）须深度≥2 且更小。
- fork 复制深度；exec `depth_mode` 只收不增。
- supervisor 普通命令 grant 1，`dash`/`make` 委派 3；dash 侧 gcc/make 名称分支在
  `jobs_xos.c`/`newlib_syscalls.cpp`。
- `spawn_buffer` 128 KiB 与大映像 `spawn_file` 流式正交（非本契约范围）。

## 未做 / 下一步

- SL1：内核最小继承机制 + 版本化 SDK 接口（新字段不静默扩 `spawn_options`）。
- SL2：双 Shell 接入、去名称特判。
- 本组未改内核/SDK 源码；无 ABI 号分配。

## 验证

```text
docs_consistency.py（契约新增链接后）
git grep 关键符号与契约表逐项对照（本 work_log §关键实测依据）
```
