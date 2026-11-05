# 双 Shell 普通命令启动与权限继承契约（SL0 冻结）

2026-11-05 · 状态：**SL0 冻结**（契约与兼容表生效；机制实现属 SL1+，未实现）。
来源计划：[shell_launch](../plans/shell_launch.md)。勘查基线：main `8d186fd8`
（含 DU4 #82）。本契约不修订宪法、不分配新 ABI 号；按 C20/C22/C27 审查。
实现前先读 [ABI 登记](abi_registry.md) 与 [进程 ABI](../implementation) 相关源码。

## 1. 范围与非目标

**范围**：xsh 与 dash 普通命令的启动授权、spawn/fork/exec 继承与削减、失败回收、
新旧入口兼容。  
**非目标**：完整 POSIX、作业控制/信号/TTY、多线程 fork、COW、动态链接、第二 ISA、
新安全沙箱、工具专属内核 ABI。普通调用可运行 ≠ 任意进程数/嵌套深度。

## 2. 现状：权限来源与资源表（SL0 实测）

### 2.1 入口 → 授权映射

| 入口 | 位置 | 子进程获得 | 备注 |
|---|---|---|---|
| xsh 普通命令 | `supervisor.cpp` `launch_file` | **一级**（`grant_spawn=true` → 内核 `spawn_depth=1`） | 裸命令历史能力 |
| xsh `dash` / `make` | 同上 `development_tool` 分支 | **三级委派**（`delegate_spawn_depth=3`） | **按名称特判**（SL2 要拆除） |
| xsh `exec-file` / `spawn-file` | 同上 | **无创建权** | 显式文件入口，兼容保留 |
| xsh `exec-driver` / `exd` | 同上 | **一级**（同普通命令） | 诊断/驱动入口 |
| dash 普通命令 | `jobs_xos.c` `xos_spawn` → `posix_spawn` | **默认无创建权**（newlib 约定） | 与 xsh 不一致（缺陷） |
| dash → gcc/g++ | `xos_posix_spawn_driver`（`newlib_syscalls.cpp`） | 按驱动委派接口 | **按名称特判** |
| dash → make | `xos_posix_spawn_make` | 按 make 委派接口 | **按名称特判** |
| dash 脚本 `#!/bin/dash` | `jobs_xos.c` fork+`execve(/usr/bin/dash,…)` | 继承 fork 语义 | shebang 白名单 `/bin/sh` `/bin/dash` `/usr/bin/dash` |
| dash `exec prog` | 替换当前 shell 映像 | 保留既有替换语义 | 不与 xsh 历史 `exec` 混同 |
| 服务/维护启动 | `sys_process_guard` + 明确清单 | 独立于普通会话 | 见 §2.3 |

### 2.2 内核机制（`tasks.cpp`，ABI 见登记表）

| 原语 | 编号 | 行为摘要 |
|---|---:|---|
| `sys_process_create` | 16 | 非 supervisor 须 `spawn_depth != 0`；创建子进程 |
| `sys_process_fork_prepare/commit` | 57/58 | 须 `spawn_depth != 0`；**子进程复制父 `spawn_depth`** |
| `sys_process_exec_prepare/commit` | 61/60 | `exec_depth_mode`：`depth_mode-1 ≤ 3` 且 **`< 当前 spawn_depth`** 才可设定；exec **不增加**深度 |
| `sys_process_grant` | 28 | 仅 supervisor；目标 `spawn_depth = (second!=0) ? 1 : 0`（直接子建造权） |
| `sys_process_delegate` | 37 | 非 supervisor 须 `spawn_depth ≥ 2` 且 `second < 自身深度`；目标深度 = `second`；上限 `process_max_spawn_depth = 3` |
| `sys_process_guard` | 62 | 维护准入屏障：begin 要求无其他存活任务（files 除外）；end/rearm 归 owner |

**深度语义（现状）**：深度同时表达「能否创建后代」与「还能委派几级」；max=3；
fork 复制、exec 按 mode 收紧、grant 置 1、delegate 置更小正数；0=无创建权。

### 2.3 SDK `spawn_options`（`src/user/include/xos/spawn.hpp`）

| 字段 | 语义 | 兼容注意 |
|---|---|---|
| `grant_spawn` | 旧式「直接子建造权」→ 等价 grant 1 | 与深度耦合 |
| `delegate_spawn_depth` | 显式委派更深（非 supervisor 只能更小） | 与深度耦合 |
| `exec_depth_mode` | 替换时收紧深度 | 不恢复被削减权利 |
| 其余（stdio/env/paths/handles/descriptors） | 与授权正交 | SL0 不改布局 |

**二进制布局**：SL1 新字段**不得静默扩展**本结构；须独立接口或带版本/大小请求
（先核对调用模式）。

### 2.4 资源与失败（现状约束）

| 资源 | 现状 | SL0 结论 |
|---|---|---|
| 进程槽/完成记录/页/端点 | 全局既有预算 | SL1 **不抬高上限掩盖**不足 |
| 创建权耗尽 | 深度用尽即 denied | 授权**不按代递减耗尽**（现状 fork 复制深度，嵌套深度受限——单独登记，不宣称任意嵌套） |
| 启动失败 | loader 已有 fail_before_create 类回收 | SL1 继续：不留半成品；正常/fault/kill/取消语义分列 |
| `spawn_buffer` | `image_buffer[131072]` | 与本契约正交；大映像走 `spawn_file` 流式 |

## 3. 双轨兼容表（SL0 冻结）

**原则**：旧请求保留原限制；新 SDK 用新契约；未知版本**明确拒绝**；不静默重解释
`sys_process_grant`/`delegate`/深度接口。

| 轨 | 授权载体 | 入口 | 保留期 |
|---|---|---|---|
| **旧轨（现网）** | `spawn_depth` + `grant_spawn`/`delegate_spawn_depth` + 按名特判 | 上表全部现状入口 | SL1–SL3 过渡期**原样运行**；不等于继续推荐 |
| **新轨（SL1 目标）** | 内核认证的**可继承创建能力**（与深度账目分离） | 普通 `posix_spawn`/fork/exec 统一继承规则 | SL1 引入后新 SDK 默认走新轨 |

新轨硬规则（冻结设计，SL1 实现）：

1. 创建能力由**进程身份**承载，记录可用与可继承范围；子不能增权，父可主动削减。
2. 同一父、同一授权配置下，**普通 spawn 与 fork 后 exec 结果一致**；exec 不恢复被削减权；
   更名/PATH/ELF 标记/自报环境**不授予权利**（ELF/CRT 标记仅格式与 FD 恢复准入）。
3. 无创建能力者不能 spawn/fork，也不能借 exec 获得。
4. 维护模式、受限进程、服务启动清单**单独选择**权限；普通创建权 ≠ 设备/内存/维护/IPC 权。
5. 资源不足真实失败；不新增不必要的配额框架；若需进程树预算，后代**共享**归属，
   父退出后归属保持到引用释放。

## 4. 用户态统一与名称特判退役（SL2 输入）

| 现状特判 | 位置 | 退役方向 |
|---|---|---|
| supervisor：`dash`/`make` → depth 3 | `supervisor.cpp` | 改为通用可继承创建能力后删除名称分支 |
| dash：`gcc`/`g++` → `xos_posix_spawn_driver` | `jobs_xos.c` | 同上 |
| dash：`make` → `xos_posix_spawn_make` | `jobs_xos.c` | 同上 |
| `exec-driver` 一级 vs `exec-file` 零 | `supervisor.cpp` | 保留为兼容/受限入口，日常工具不再依赖 |

搜索 PATH、工作目录、环境快照、stdio、共享打开描述、CLOEXEC、失败回滚沿用现有
loader/文件契约；xsh 无对应 Shell 功能的项标 **N/A**，不伪造 POSIX 语法。

## 5. ABI 登记约定

- **SL0 不占用任何新号。**
- SL1 若需新 syscall：在 [abi_registry](abi_registry.md) **reserved 段 84–95（系统底座线：
  通用等待/信号/进程控制）** 按「claim → 登记 PR → 实现 PR 再 allocated」流程办理；
  不抢其他线预留号，不生成假常量/桩。
- 优先复用既有 16–21、28、37、57–62；仅当既有原语无法表达「与深度分离的可继承能力」
  时才申请新号，并在登记 PR 写明与 28/37 的差异。

## 6. SL0 退出自检（可逐项判断）

| 判据 | 状态 |
|---|---|
| 授权来源可追溯（§2.1/2.2 表） | ✅ 本契约 |
| 削减/继承规则可判断（§2.2 + §3 新轨硬规则） | ✅ 设计冻结；实现=SL1 |
| 失败与资源语义可判断（§2.4） | ✅ |
| 旧接口行为与双轨边界（§3） | ✅ |
| 新接口先登记、不抢号（§5） | ✅ |

## 7. 验收与文档指针

验收矩阵见计划 [shell_launch](../plans/shell_launch.md)（双 Shell 两列、C27）。
实现分阶段 SL1 通用机制 → SL2 双 Shell 接入 → SL3 诊断/工具 → SL4 组合验收；
每阶段更新 state、ABI 登记与本契约的「状态」行。

相关：[dash 路线](../plans/dash.md)、[POSIX 子集](posix_subset.md)、
[FB1/FB2](../implementation/fb12_fault_bundle.md)、[ABI 登记](abi_registry.md)。
