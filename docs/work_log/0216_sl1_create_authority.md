# 0216 — SL1：身份承载创建能力与客体探针

2026-11-06。分支 `codex/sl1_inherit_mech`（变基至 main `933998e4` 后实施）。
按 [shell_launch 契约](../contracts/shell_launch.md) §3/§5 完成 **SL1：通用机制**。

## 交付

### 内核（`tasks.cpp`）

- `process_record.can_create`：与 `spawn_depth` 分离的身份承载创建能力。
- **`sys_process_authority` = 84**（ABI 登记拆分 84 allocated / 85–95 reserved）：
  mode 0 clear（同时清 depth，完整削减）、1 set、2 copy-from-caller、3 query；
  仅 building 目标上 set/clear；query 允许 self/parent/supervisor。
- `sys_process_create` / `fork` 检查改为 `depth==0 && !can_create` 才拒绝；
  fork/exec（replacement stage）**复制** `can_create`。
- `sys_process_grant`/`delegate` 同步写 `can_create = (depth!=0)`（旧轨与新轨对齐）。
- **`owned_process` 增加 `current->can_create`**：否则 depth=0 的新轨父进程无法
  map/start 自己的 building 子进程（`pre_start_fail=-1` 根因，探针调试定位）。

### 探针

- `tests/fixtures/shell_launch/sl1_authority.cpp` + `tests/shell_launch_sl1.py`：
  - T1 authority set → 孙进程可创建（SPAWN=11）+ leaf 正常退出
  - T2 默认子进程不可创建（SPAWN=-1）
  - T3 set→clear 后不可创建（完整削减）
  - T4 非法 mode → invalid(-2)
  - T5 旧轨 depth=1 仍可创建（兼容表）
  - **7/7 PASS**（build `a63c9d19039207b8`）

### 回归

boot 6/6、process(E04) 13/13、task(E03) 12/12 —— owned_process 改动未破坏旧路径。

## 过程要点

- `spawn_file` 立即 start → 权限须经 `spawn_options.prepare_child` 在 start 前设置。
- `spawn` 默认不复制 depth；新轨靠 `can_create`，与 fork 复制语义对齐由探针 T1 验证。
- 调试期曾加 `[sl1]` 打印，定案后已全部移除。

## 未做

- SL2：双 Shell 接入、去名称特判（supervisor dash/make、jobs_xos gcc/make）。
- SDK 新版 `spawn_options` 布局未扩展（探针走 `spawn_file_options.prepare_child`）。
- 未发 PR（待用户指令）。
