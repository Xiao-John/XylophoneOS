# 0217 — SL2：双 Shell 接入与名称特判退役

2026-11-07。分支 `codex/sl1_inherit_mech`（SL1+SL2 同支连续交付）。
按 [shell_launch 契约](../contracts/shell_launch.md) §4 完成 **SL2：两个 Shell 接入**。

## 交付

### xsh（`supervisor.cpp`）

- `launch_file` 增加 `inherit_create`：经 `prepare_child` 调
  `sys_process_authority(copy_from_caller)`；与既有 terminal prepare 串联。
- **普通裸命令**：去掉 `dash`/`make` → depth 3 名称特判，统一
  `spawn_depth=0 + inherit_create=true`。
- **tty-run**：改为 inherit + terminal prepare（不再 grant depth 1）。
- **历史入口保留**：`exec-file`/`spawn-file` 无创建权；`exec-driver`/`exd`
  仍 grant depth 1；`diag` 不变。

### dash（`jobs_xos.c`）

- 去掉 `xos_is_gnu_driver`/`xos_is_make` 分支与调用；`xos_spawn` 一律
  `posix_spawn`；`xos_shell_execve` 一律 `execve`。
- `xos_posix_spawn_driver/make`、`xos_execve_driver/make` **保留导出**（兼容，
  本文件不再调用；SL3 可移除）。

### newlib（`newlib_syscalls.cpp`）

- `posix_spawn_with_depth` 设置 `prepare_child=inherit_create_prepare`
  （copy_from_caller）：普通 spawn 与 fork 的创建权继承一致。

## 探针

`tests/shell_launch_sl2.py`（复用 `sl1_authority.cpp` 新增 `query` 模式）：

| 检查 | 结果 |
|---|---|
| xsh 裸命令 `sl2_probe query` → `OWN=1` | PASS |
| 改名 `fauxtool query` → `OWN=1`（同权） | PASS |
| `exec-file … query` → `OWN=0`（历史受限） | PASS |
| `dash /out/q.sh` → `OWN=1`（posix_spawn 继承） | PASS |

**4/4 PASS**。SL1 探针 7/7 仍过。

## 回归

- boot 6/6、process(E04) 13/13、task(E03) 12/12（build `283a96a3aaad6dac`）。
- jobs_xos 改动由 SL2 的 dash 腿直接覆盖。
- dash_c1/c3 smoke 为资格工具（需 `--system/--dash-manifest` 等参数），本轮未跑。

## 未做（SL3+）

- xos-diag 普通调用、Make/编译驱动完整迁移、旧深度包装器删除。
- 未发 PR（待用户指令）。
