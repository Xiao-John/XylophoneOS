# 960fce43 · v2 与冻结 newlib 的隔离回退复验

将当前 v2 普通系统 `1f593b6ca9cd7904` 与其 2,049 项源及实物绑定。
v2 SDK、C/C++ 包和工作盘沿用[已验工作区选择](4c8a56a1_glibc_v2_workspace_default.md)。
冻结侧使用原 0.0.1-1024 启动软盘 `2c3876e640840ff5`、原 SDK、原发行工作盘及
历史回退验收中已含旧应用和旧用户文件的盘。SDK、媒体、三份原始盘和旧包的
实际字节都按既有回执核对。本次复用原生 ELF 和两个已验证的宿主 FAT 工具。

## 宿主检查

两个方向均拒绝错 profile 的包与已登记数据库。原发行无 profile 的工作盘副本
拒绝 `list`、`install` 和 `repo-install`，盘摘要保持且没有候选盘输出。
临时移走私有 v2 kit 后状态查询失败，显式切到冻结 SDK 成功。恢复 v2 后
注册文件字节与初始一致。输入预检和实际复跑各通过 11 项，共用同一套只读原件。

首次预检的 420 MiB 内存盘遇到 `ENOSPC`。原发行盘的宿主写入入口先暂存稀疏
事务副本，再检查 profile。扩大到 480 MiB 后触发并核对预期 profile 拒绝。
读取只读原件时使用支持只读打开的 xypm FAT 后端，客体使用已有工具操作临时盘。

## 三次冷启动

| 次序 | 介质和实测 | 退出前后资源 |
| --- | --- | --- |
| v2 | 当前普通 ISO。原有 C 程序读盘并核对 glibc 2.44，C++ 运行容器、线程和异常。 | 129709 / 3 / 1 |
| 冻结 newlib | 原版软盘和历史用户盘副本。运行原 ELF，读取旧文件并同步追加 `selection`。 | 130342 / 2 / 0 |
| 返回 v2 | 同一当前普通 ISO 和同一 v2 盘再次运行 C/C++，已登记文件和用户数据读回。 | 129709 / 3 / 1 |

三个 QEMU 11.1.3 客体均在断网 Linux 启动，分别有 5,632,660、4,914,620
和 3,821,516 KiB 可用内存。前一组合容器移除后才启动，三次均满足 3.5 GiB
门槛。测试盘为有界内存盘中的稀疏副本。三个原始盘在结束后再次核对完整摘要，
与开始前一致。工作盘用途和 SDK profile 始终对应各自系统。
[回执、启动条件与三份原始串口](../reports/glibc_v2_current_frozen_roundtrip_20261127/manifest.json)

复跑时以 [原回退入口](4c8a56a1_glibc_v2_workspace_default.md#重跑) 的命令和
`glibc_newlib_frozen_rollback_guest.py` 的 `guest_run` 为准。使用其已验
C/C++ 包和工作盘以复用既有构建，依次运行
`exec-file /usr/bin/kit_c`、`exec-file /usr/bin/kit_cpp`，
切到原启动软盘运行 `exec-file /usr/bin/frozen selection`，恢复 v2 后
重复前两条。两套 SDK 由 `xos_sdk.py setup` 在独立注册文件绑定，
再通过 `use newlib` 和 `use glibc` 切换。
