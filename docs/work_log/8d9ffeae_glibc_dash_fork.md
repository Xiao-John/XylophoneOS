# 8d9ffeae · glibc dash 命令替换

日用包客体用 `$(cat …)` 核对持久化文件时遇到 glibc dash 的预览拒绝。现在 `$()`
和反引号沿用上游 dash 的解析、管道收集、尾换行去除与退出状态处理，保留 1 MiB
原始输出上限。父进程在捕获失败后取消并回收子进程。newlib 仍走原来的实现。

静态单线程 glibc 经既有 `fork_prepare`、files `clone_session`、`fork_commit`
交付独立子进程。COW 地址空间保留 Shell 变量、函数与 TLS，FD 保留共享打开描述及
pipe。带终端时父进程先派生并登记子通道。子进程用自己的认证文件、终端会话和 TID
继续运行。`fork` 执行 atfork 回调，`_Fork` 只执行原生事务。内核创建权和深度约束
保持有效。失败事务回收未启动子进程。本组沿用既有系统调用及文件协议。

## 验收

源码 `8a53567d` 与 [客体及构建回执](../reports/glibc_dash_fork_20261126/manifest.json)
对应 QEMU 11.1.3 的普通镜像 `b5cbf1ddf65e6b36`。glibc 2.44 归档验签，独立构建
C SDK、glibc dash 及 newlib dash。运行 `scripts/build_glibc_sdk.py`、
`scripts/build.py`、`scripts/create_xypm_profile.py`、`scripts/build_dash.py` 和
`tests/dash_glibc_preview_guest.py`。回执绑定完整源码、SDK、profile、两个 dash ELF、
QEMU、镜像和夹具。实现和 SDK 输入相同，最终一轮重新构建的普通镜像同时绑定更新的测试脚本。

经 xsh 和 newlib dash 分别启动 glibc dash，各通过 25 项。覆盖两种替换语法、嵌套、
引号和换行、状态隔离、真实文件、10,037 字节的多段流和 pipefail、关闭描述符、无创建权
拒绝，以及直接 C 探针的真实文件共享偏移、TLS 与 atfork。交互和终端服务各通过一次独立
替换检查。普通入口每次回到 `129709 / 3 / 1`，带终端服务回到 `129525 / 4 / 2`。
FAT 读回 7 个文件。另一个客体运行了相同的原生 newlib 替换脚本，并证实 glibc
交互越过 1 MiB 上限后可继续下一次替换和退出。宿主 ASan/UBSan 通过 49 项句柄适配、
15 项 files/FatFs、24 项终端及 8 项文件扩展检查。

首轮独立 C 探针误用带 const 属性的 `pthread_self`，编译器消掉了部分调用。
保留最初客体诊断。最终探针通过 volatile 函数指针实际调用该 API。
此范围尚未覆盖启用线程后的 fork、共享 libc、glibc 出站 exec 或完整 POSIX Shell。
同一改动进入安装候选后还须重建 C/C++ SDK 和日用包，再复验空盘安装及重启。

## 复审与 #286 组合验收

`ef15eb8f` 基于 #286 合入后的 `acbefa2b`。XOS 安装头为 `pthread_self` 保留正常函数
声明。子进程以实际 TID 接管复制的名称和栈记录，并清除继承的父 TID。直接 C 探针
通过普通函数调用读取 TID，并通过公开 pthread 接口核对两种 fork 入口的名称、栈范围和
旧 TID 拒绝。

创建快照之前取 5 秒绝对单调期限。终端登记的锁和双向等待与 files 克隆共享这个期限，
提交前再次检查。超时撤销暂存子进程。原 `terminal::register_fork` 符号及默认行为保留，
增加显式带期限的 `register_fork_until`。已同步的晚到应答可保留父终端会话，传输超时
按原故障路径关闭。Linux ASan/UBSan 的 27 项终端检查包括正常提交、终端超时撤销，
以及终端已耗去四秒后的 files 超时撤销。

从签名 glibc 归档重新构建 C SDK 和两个 dash。实际普通系统 `9562fa4ec72cfd7a` 通过
两种 Shell 入口的 50 项检查，另有 12 项 pthread 和 7 项真实终端检查。普通系统和终端
服务的资源分别回到 `129709 / 3 / 1`、`129525 / 4 / 2`。同镜像再次通过原生 newlib
替换、交互捕获超限与恢复。 [组合回执](../reports/glibc_dash_fork_review_20261126/manifest.json)

## #284 合入后重放

在 `7a3ebcf1` 同时包含 #284 的早期堆与 #286 的安装网络后，从签名归档重新构建
glibc C SDK 和两套 dash。普通系统 `bec24eea8c3ee683` 在 QEMU 再次通过双 Shell
50 项、pthread 12 项、终端 7 项、交互与终端服务替换。独立回放通过旧 newlib 替换及
glibc 捕获超限的后续恢复，宿主合并前后回执均覆盖终端与 files 的共享期限。
[最新合成回执](../reports/glibc_dash_fork_post284_20261126/manifest.json)
