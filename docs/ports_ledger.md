# 端口反馈账本（port ledger）

移植过程中发现的、**适合由 OS 侧改进**的问题统一登记在这里。账本只记录现象、影响和建议
动作；真正的 OS 改动另走 ABI/契约流程与独立 PR，端口目录不夹带 OS 补丁。

- 编号：`PL-0001` 起递增，永不复用。
- 状态：`open`（待处理）、`accepted`（已排期/已认领）、`fixed`（OS 侧已修）、
  `wontfix`（明确不修，需写理由）。
- 每条必须有证据：端口 ID + 客体重现命令或报告路径。
- 端口侧有临时绕过（shim）时写进 `workaround`，并在端口 README 的“已知限制”同步。

| ID | 日期 | 来源端口 | 现象与影响 | 建议动作 | 绕过 | 状态 |
|---|---|---|---|---|---|---|
| PL-0001 | 2026-11-12 | xxhash | newlib 的 `clock()` 路径解析到 `times()`，但旧 SDK 的 `libxos.a` 只导出 `_times()`；使用 `clock()` 的客体程序在链接期报 `undefined reference to 'times'` | 导出 `times()` 并加客体链接用例 | 基线已含 `times()`；`tests/libc_posix_time.py`（PR #119 `ec5d0e33`） | fixed |
| PL-0002 | 2026-11-12 | lz4 | 客体 libc 无 `utime`/`chmod`/`chown` 实现，且 newlib 的 `sys/utime.h` 只定义 `struct utimbuf`、不声明 `utime()` | 提供符号并默认 `ENOSYS`；`utime()` 补声明 | `src/user/include/utime.h` + `newlib_syscalls.cpp`；`tests/libc_posix_time.py`；PR #119 `ec5d0e33` | fixed |
| PL-0003 | 2026-11-12 | lz4 | C11 `timespec_get()` 有声明无实现，`timefn.c` 链接失败 | 用 sys64 实现 `TIME_UTC` | `newlib_syscalls.cpp`；`tests/libc_posix_time.py`；PR #119 `ec5d0e33` | fixed |
| PL-0004 | 2026-11-12 | lz4 | `clock_gettime`/`timer_*` 的声明受 `_POSIX_TIMERS` 控制，当前 newlib 特性头未开启；端口无法使用 POSIX 时钟接口 | 决定是否声明 `_POSIX_TIMERS` 并实现 `clock_gettime`（`timer_*` 仍需单独评估），或提供稳定的替代入口 | 本组未做；`timespec_get` 可覆盖墙钟需求 | open |
| PL-0005 | 2026-11-12 | lz4 | 文件服务没有时间戳/权限/所有权写操作，`utime`/`chmod`/`chown` 只能 `ENOSYS` | 评估在 file ABI 增加 `set_metadata`（FatFs `f_utime`/`AM_RDO`）并登记契约 | 端口接受 `ENOSYS` 并跳过元数据复制 | open |
| PL-0006 | 2026-11-12 | lz4 | 客体没有 `/dev/null`；`lz4 -t` 打开空输出时报 `/dev/null: No such file or directory` 并退出 1 | 文件服务内置 `/dev` 虚拟目录与 `/dev/null` 对象（open/read/write/lseek/fstat/close） | `docs/reports/dev_null_20261112/README.md`；`tests/dev_null_guest.py`；客体 `lz4 -t` 复测通过 | fixed |
| PL-0007 | 2026-11-12 | lua | `system()`/`popen()` 只有 newlib 的 ENOSYS 桩，Lua `os.execute` 返回 `nil, "Function not implemented", 88`，`io.popen` 不可用 | libc 实现 system/popen/pclose：posix_spawn + pipe + waitpid；shell 解析 `XOS_SHELL` → `/bin/sh` → `/usr/bin/dash`（双 shell 镜像自带 dash） | `src/user/libc/process_posix.cpp`；`tests/posix_shell_guest.py` | fixed |
| PL-0008 | 2026-11-12 | jq | libc 缺 `dirname`、`realpath`、`pathconf`，jq 链接失败 | 在 libc 实现三者（`realpath` 复用 `resolve_path`） | PR #119 `79183a32`；jq 端口客体用例 | fixed |
| PL-0009 | 2026-11-12 | jq | 普通 profile 无 pthread 运行时，jq 的 hash seed 与 decNumber TSD 需要 `pthread_once`/key | 由 PL-0010 解决：默认 SDK 提供单线程 pthread 子集 | jq 已删除 `compat/pthread_single_thread.c`（PR #119 `195be0aa`）；`tests/pthread_subset_guest.py` | fixed |
| PL-0010 | 2026-11-12 | jq/lz4/zstd | 普通 SDK 完全没有 pthread 符号，端口各自带桩 | 默认 SDK 加单线程安全子集（once/TSS/mutex/cond/rwlock，create 返回 ENOSYS），并让 `xos_app.py` 打开 POSIX feature 宏 | `src/user/libc/pthread_single.cpp`（PR #119 `195be0aa`）；`tests/pthread_subset_guest.py` | fixed |
| PL-0011 | 2026-11-12 | lz4/zstd | 真实多线程不可用：线程 SDK 需要 SHA 固定的 newlib 源（`6ff27e3b…`） | 从 sourceware 公开目录取回同名归档（哈希一致），重建线程 newlib 与线程 SDK；lz4 `-T2`、zstd `-T2` 客体实测通过 | 归档在 `.cache/xos_seed/threading_sources/`（不入库）；PR #119 `98700f61` | fixed |
| PL-0012 | 2026-11-12 | lz4/zstd | 线程化**打包**未打通：没有 threaded profile，xypm 的 DB/profile 仍是 b2 | 新增 `xos-x86_64-static-threaded-v1` profile（登记线程 SDK 树哈希与系统 build），用该 profile 安装线程包；线程 SDK 改为 C 模式 `-fno-exceptions` | profile 见 `config/package/`；lz4/zstd 线程包安装与 `-T2` 实测；PR #119 `930d0e2d` | fixed |
| PL-0013 | 2026-11-12 | 线程端口 | P2 常用多线程面缺失：信号量、barrier、spinlock、setname、guardsize、cond/rwlock attr | 在线程运行时与单线程子集各实现一份 | `tests/pthread_p2_guest.py`（双 SDK 探针）；PR #119 `f3baddc5` | fixed |
| PL-0014 | 2026-11-12 | 线程端口 | `pthread_tryjoin_np`/`timedjoin_np` 需要非阻塞/带 deadline 的 join；`pthread_getcpuclockid` 需要 per-thread CPU 时钟。内核 join 只有阻塞版，`thread_info` 无状态字段 | 评估新增 `sys_thread_tryjoin`/deadline join 与 CPU 时间计入；在此之前保持 `ENOTSUP` | 端口按 `ENOTSUP` 处理 | open |

## 登记规则

1. 判定标准：不是端口自己的问题（上游代码、打包、许可都排除），而是 XOS 的 libc、
   加载器、SDK、工具链、文件服务或内核 ABI 的行为让“标准做法”不可用或需要额外绕过。
2. 每条只写一个可验证的现象，附最小复现命令；不写推测性重构建议。
3. 修完后把状态改为 `fixed` 并补 PR/提交号；不要删除旧行。
4. 若同一问题在多个端口重复出现，沿用原 ID 追加“另见端口”，不新开编号。
5. 大项（需要新设备/命名空间、进程模型、ABI 或完整子系统）不在本地半实现；保持
   `open`，攒批后统一开 issue，并在汇报里列出批次。
