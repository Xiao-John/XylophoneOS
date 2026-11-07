# 0212 文件服务 found_bug 修复：POSIX 语义、路径解析与句柄转移授权

## 范围与结果

输入是第三方在 `CONTEST/bug-hutting-contest-3/found_bug.md` 提交的 15 项静态/宿主
发现。本轮在主工作区逐项修复，并补宿主探针与客体验收。全部 15 项都有对应改动；
其中 14 项有可执行证据，1 项（满盘）以故障注入代替真实满盘介质。

主要行为变化：

1. `O_TRUNC`/`O_APPEND` 不带 `O_CREAT` 时不再创建文件；返回 `not_found`。
2. 每个打开实例维护逻辑偏移；`ftruncate` 不改变偏移，`lseek` 越过 EOF 不扩展文件。
3. 写越界和 `ftruncate` 扩大改为显式写零；短扩展回滚到原长度并返回 `no_space`。
4. `rename` 可替换已存在的普通文件：journal + 备份改名，成功清理，崩溃可由
   启动恢复还原。
5. 目录移入自身后代按目录项身份拒绝，避免 FatFs 部分移动后丢失入口。
6. 服务在 `f_read`/`f_write` 部分完成后出错时返回已完成字节数，不再丢弃进展。
7. `file_session_info` 增加内核填写的 `parent_pid`；`transfer` 只允许父进程向
   子进程转移，调用方自报 PID 不再构成授权。
8. libc 路径解析改为逐分量 `stat`：空路径 ENOENT，中间分量必须存在且为目录，
   尾斜杠要求目录；`unlink("file/")` 不再删除普通文件。
9. `open`/`pipe` 从 0 开始分配最低空闲描述符。
10. `posix_spawn` 的高号 `addclose` 会记录为有序动作；`addopen` 保存原始路径，
    在执行时按 spawn 时刻的工作目录解析。

## 修改文件

- `src/user/services/files.cpp`：逻辑偏移、零填充、截断回滚、rename 替换与
  后代检查、部分读写、transfer 父进程检查。
- `src/user/libc/newlib_syscalls.cpp`：`resolve_path_from`/`resolve_path`、尾斜杠、
  空路径、fd 分配、spawn 动作、exec/stat/chdir/opendir 等调用点。
- `src/shared/include/xos/process_abi.hpp`、`src/kernel/arch/x86_64/tasks.cpp`：
  `file_session_info.parent_pid`（16→24 字节，内核与 SDK 必须一起重建）。
- `src/user/services/file_ui.cpp`：`filetest` 的 seek 越过 EOF 期望改为 POSIX
  语义（返回请求偏移、长度不变）。
- `tests/fixtures/file_semantics/file_semantics.cpp`、`tests/file_semantics.py`：
  宿主文件服务 11 组探针（含短读写/短扩展注入）。
- `tests/fixtures/file_posix/file_posix.c`、`tests/file_posix_guest.py`：客体
  10 组验收（路径、偏移、截断、rename、fd 复用、spawn 动作）。
- `docs/e04_loader_sdk.md`、`docs/e05_file_service.md`、`docs/tech_debt.md`。

## 选择与原因

- 偏移放在 `open_description` 而不是 `FIL.fptr`：FatFs 的 `f_lseek` 越过 EOF 会
  分配簇且不清零，无法安全表达 POSIX 的“定位不改变文件”。
- 扩大文件用真实零字节写入而不是 `f_lseek` + `f_truncate`：复用簇会泄露旧内容；
  写入还能自然获得满盘短写错误。
- rename 替换复用现有 journal/backup 恢复材料，而不是先删目标：崩溃时启动恢复
  可以把旧目标改名回来；`staging_active` 时直接 `busy` 避免共用备份名。
- 转移授权放在内核：服务无法自行证明“目标是我的子进程”，由
  `sys_file_session` 提供认证过的 `parent_pid` 才不依赖调用方自报。
- 路径解析放在 libc 并逐分量 `stat`：服务端只接受已规约路径且拒绝 `.`/`..`，
  客户端必须先验证中间分量的存在性和目录类型。

## 证据（2026-11-07）

构建：

```text
python3 scripts/build.py
Built xos-install.iso + real_mode.img | 49519693a72623c3 | kernel 520272 bytes
```

宿主探针（真实 `files.cpp` + 真实 FatFs + 私有内存镜像）：

```text
python3 tests/file_semantics.py      -> FILE_SEMANTICS_CASES_PASSED=11
python3 tests/file_recovery_faults.py -> RECOVERY_CASES_PASSED=21
```

客体验收（QEMU，私有 FAT 工作盘）：

```text
python3 tests/file_posix_guest.py    -> PASS: 10 file posix checks | build 49519693a72623c3
python3 tests/file_smoke.py          -> PASS: 8 E05 checks
python3 tests/runtime_smoke.py       -> PASS: 5 E08-2 groups
python3 tests/libc_smoke.py          -> PASS: 3 E06 checks
python3 tests/file_recovery_guest.py -> 4/4 模式通过
```

报告：`build/file_semantics/report.json`、`build/file_posix_report.json`；
串口日志在对应 `build/*_serial.log`。

## 未运行 / 限制

- 未在真实近满 FAT 介质上复现 `ftruncate` 扩大失败；仅用注入短写验证
  “返回 no_space 且长度回滚”。
- 未跑完整 `make smoke`、dash 验收和 binutils 系列；本轮只跑与文件/路径/
  进程相关的门。
- 未重建 guest g++/SDK 发行资产（BT-07），本次只重建系统镜像与 SDK 静态库。
- 同一文件已有写打开时再次 `open` 仍返回 `busy`（FatFs `FF_FS_LOCK`），
  删除/重命名有打开实例的文件仍 `busy`；已登记 FS-01/FS-04。
- `rename` 尚不支持目录替换（FS-02）；回滚是 best effort，失败会置 recovery gate。
- 路径逐分量 `stat` 增加 IPC 次数（FS-05），本轮未做性能测量。

## 下一步

- 若接受 ABI 变更，合并时同步重建 kernel/SDK/发行资产；`file_session_info`
  旧二进制不能与新内核混用。
- 需要真实满盘证据时，用专用近满镜像补 FS-03。
- 需要并发多打开时，按 FS-01 设计共享描述或目录项协调，而不是简单关掉
  `FF_FS_LOCK`。

## Git 来源

分支 `codex/bug_hunting_contest_3_fixes`，rebase 到 `ba3d36f3`（main，含 PR #86/#87）。
本记录随修复提交进入 PR。
