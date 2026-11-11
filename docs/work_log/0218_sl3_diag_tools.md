# 0218 — SL3：xos-diag 普通调用与深度包装器退役

2026-11-08。分支 `codex/sl1_inherit_mech`（SL1+SL2+SL3 同支）。
按 [shell_launch 契约](../contracts/shell_launch.md) 推进 **SL3：诊断与工具迁移**
（部分交付；Make 真实 C 工程见「未做」）。

## 交付

### xos-diag 普通调用

- `xos_diag.cpp`：目标子进程经 `prepare_child` **inherit-create**
  （`sys_process_authority` copy_from_caller），与共同契约一致。
- `supervisor.cpp` `diag` builtin：改为 `inherit_create=true`
  （诊断目标可再启动工具链子进程）。
- 使用说明更新：`docs/usage/userland/dash.md`、`docs/implementation/fb12_fault_bundle.md`
  —— xsh/dash **裸调用** `xos-diag` 即可，无需 `(exec …)` / `exec-driver`。

### 深度专用包装器退役

- 从 `newlib_syscalls.cpp` 移除：
  `xos_posix_spawn_driver`、`xos_posix_spawn_make`、
  `xos_execve_driver`、`xos_execve_make`。
- 从 `src/ports/dash/xos_profile.h` 删除对应声明
  （SL2 起 `jobs_xos` 已无调用方；`nm libxos.a` 确认符号已消失）。
- 文档：`docs/e04_loader_sdk.md`、`docs/implementation/make.md` 改为
  inherit-create 口径；旧轨 `grant`/`delegate`/`spawn_options` 深度字段仍保留。

### 探针

`tests/shell_launch_sl3.py` **8/8 PASS**：

| 检查 | 结果 |
|---|---|
| xsh 裸 `xos-diag /bin/hello.elf` → 0、回 Shell、无包 | PASS |
| xsh 裸 `xos-diag /bin/fault.elf` → 128 + bundle | PASS |
| xsh 裸 `xos-diag /bin/missing` → 127 | PASS |
| xsh `diag` builtin fault | PASS |
| dash 脚本裸调用 normal/fault/missing | PASS×3 |
| `exec-file xos-diag` → 126（历史受限，无创建权） | PASS |

`tests/shell_launch_sl2.py` 增补 **exec-driver 旧轨仍授予权** → **5/5 PASS**。

`tests/shell_launch_sl3_make.py`（真实最小 C 工程经 Make）：
**not_run** —— GCC seed 缓存 164 个 `install_files` 均不在盘
（`build/shell_launch_sl3_make/report.json`）。

## 回归（build `0f55e3bdb38c542f`）

- boot 6/6、process(E04) 13/13、task(E03) 12/12
- SL1 7/7、SL2 5/5、SL3 diag 8/8
- docs_consistency 822 links passed；path scan **PUBLIC_READY 0 findings**

## 选择与原因

- **保留** `spawn_options.grant_spawn`/`delegate_spawn_depth`/`exec_depth_mode`
  与 `sys_process_grant/delegate`：契约 §3 旧轨 SL1–SL3 过渡期原样运行；
  移除的仅是双 Shell 已不用的**深度专用包装函数**。
- **xos-diag 目标 inherit-create**：普通诊断启动默认继承父进程可继承部分
  （计划 §拟定契约 1）；exec-file 入口仍不给创建权（探针 126）。
- **Make not_run 不冒充通过**：seed 缓存被清后 host libstdc++（x86_64-unknown-elf）
  无法从 Homebrew Darwin 头文件复原，完整 GCC seed 重建未完成。

## 未做（SL3 收尾 / SL4）

- 真实最小 C 工程经 Make 构建运行（需恢复 `.cache/xos_seed/gcc/` seed 或重建）。
- 验收矩阵中环境/相对路径/工作目录/FD 全量两列、至少四层 spawn 链等 SL4 项。
- 未发 PR（待用户指令）。

## 下一步命令

```sh
# seed 恢复后：
python3 tests/shell_launch_sl3_make.py \
  --seed-manifest src/ports/gcc/seed_manifest.json --seed-root . \
  --sysroot-manifest <sysroot_manifest> --sysroot-root .
# 或完整：scripts/build_gcc.py --expected-sdk-manifest-sha256 <sha>
```
