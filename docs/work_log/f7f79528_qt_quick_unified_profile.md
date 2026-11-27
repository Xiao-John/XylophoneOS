# f7f79528 · Qt Quick 的统一 glibc profile

基于 `abf0fc0a`。既有 Qt Quick 安装、替换和回退使用
`xos-x86_64-glibc-thread-locks-cxx-v1`。统一 SDK 的 pthread、C++ 配置头、CRT、
libc、libstdc++ 和展开器字节均不同。本轮的目标 QtBase、Qt Declarative 和静态插件
从锁定 Qt 6.8.3 原档重建。宿主工具从此前验收的可搬移 Linux arm64 工具包复用。
[构建与客体命令](../../src/ports/qt6/quick/unified_sdk.md)

旧诊断目录的 CMake 导出仍引用 `syncqt` 的历史位置，第一次目标构建在启动
头文件生成前停止。采用已通过搬移验收的最终压缩包后，实际目标构建进入 C/C++
编译。Linux 容器内的独立 ext4 输出避免了共享目录的 `syncqt` 文件操作问题。
QtBase 编译曾在三并发时终止时区对象，随后在两并发时终止 HarfBuzz 的
`hb-subset.cc`。容器记录了两次内存终止。大型 HarfBuzz 文件按原命令独立串行
完成，再继续同一 Ninja 树。

## QtCore 客体先验

使用目标树刚构建的 `libQt6Core.a` 和统一 SDK 实际链接旧有 QtCore 夹具。
普通 ISO `882ef9cd9a2a47e1`、QEMU 11.1.2 TCG 的 xsh 入口输出
`QT_CORE_SMOKE_OK` 并退出 0。嵌入资源和 QThread 路径通过，空闲页、任务和完成项
恢复至 `129696 / 3 / 1`。静态 ELF 含 RX、R、RW 与 TLS 段。ABI 文档对照通过。

该回执范围为 QtCore 及其统一 SDK 启动。QtGui、Qt Quick 外部应用和图形生命周期
按各自回执验收。
[证据索引](../reports/qt_quick_unified_profile_20261127/manifest.json)

## 安装目标与独立接收方

保留的 Linux ext4 构建盘通过只读文件系统检查。完成的目标安装包含静态 QtCore、
QtGui、QtQml、QtQuick 和相应静态插件。构建回执记录每项归档、Qt 6.8.3 原档及
统一 glibc C/C++ profile 的摘要。旧 profile 的实际输入被拒绝，构建器未创建输出
目录。

完整套件归档 SHA-256 为
`e764fa7034b63203cf2acca413f7b074b819a849a32657d77e438ebda2f1e4ff`。
独立 Linux arm64 容器在禁网、根文件系统只读的条件下解包到新前缀，接收方看不到
原目标树或原 SDK 挂载。接收方从 Git 导出的场景源文件重新编译和链接，其 ELF
摘要为 `276ef5bd5fb163b0c500ffdcd527e681d85c82829a19bdb282a80aa65a5d41c9`。
[目标安装回执](../reports/qt_quick_unified_profile_20261127/target-receipt.json)
[接收方链接回执](../reports/qt_quick_unified_profile_20261127/consumer-app.json)

## 普通客体与首帧测量

在合并检出 `2be8ba8f` 构建的普通 ISO `81c419d562a3731e` 中，QEMU 11.1.2
TCG 分别从 xsh 和同 profile 的 Dash 启动接收方 ELF。入口各完成两轮
真实图形验收。每轮都显示文字并推进矩形动画，PS/2 的 A 键切换矩形颜色，
B 键关闭窗口，应用重新打开场景后完成第二轮。两条输入线程均已回收，应用和入口
正常退出。应用退出后资源恢复到图形服务启动后的 `121620 / 5 / 3`，服务停止后
恢复到启动前的 `129696 / 3 / 1`（空闲页、任务、完成项）。
[xsh 回执](../reports/qt_quick_unified_profile_20261127/xsh.json)
[Dash 回执](../reports/qt_quick_unified_profile_20261127/dash.json)
[合并检出和 ISO 绑定](../reports/qt_quick_unified_profile_20261127/replay-binding.json)

xsh 首帧耗时 5.664 秒。Dash 首帧耗时 137.281 秒，测量显式使用
`--first-frame-timeout 240`。默认 60 秒门槛保留。同一接收方 ELF 的早先 Dash
验证在 60 秒无首帧，独立的 Dash 脚本在 90 秒无首帧。该脚本诊断同时验证了
`dash -c true`（0.213 秒）和经 Dash 启动的静态 QtCore 夹具（33.001 秒）。
已测图形生命周期通过，Dash 的大型静态程序冷启动性能仍待改善。
[早先 60 秒回执](../reports/qt_quick_unified_profile_20261127/dash-60s.json)
[90 秒诊断回执](../reports/qt_quick_unified_profile_20261127/dash-script-90s.json)

同一镜像用固定 FAT 文件复测 glibc 文件会话。三段各定位读取 192 KiB，发出
96 个请求并收到相同字节。正常计时等待的两段各耗时 960 ms，每次空收后恰好等待
一个 10 ms 内核时钟周期，吞吐均为 0.195 MiB/s。中间一段仅在诊断程序内把该等待
换成调度让步，耗时 30 ms，吞吐 6.25 MiB/s。正式 glibc 文件会话不变。

Qt Quick 可载入段按 4 KiB 页和单条消息 3,798 字节的上限需要 13,619 次读，
若每次等一拍则为 136.190 秒。QtCore 同样有 3,258 次读，对应 32.580 秒。
两项分别与 137.281 和 33.001 秒的实测一致到约一秒。已定位正式 glibc 接收空消息
后主动休眠，以及载入器将每个完整页拆成两次读共同放大了冷启动耗时。
[吞吐及请求时序](../reports/qt_quick_unified_profile_20261127/file-exchange-timing.json)
[原始逐请求串口](../reports/qt_quick_unified_profile_20261127/file-exchange.serial.log.gz)

## 源码准备中断与续跑

构建器在与最终源码目录同一个文件系统上分别暂存 QtBase 和 Qt Declarative。
锁定归档和整条补丁链完成后，才将暂存树原子改名为最终源码目录。
用真实归档运行 [中断回归](../../tests/qt6_quick_source_resume.py)，在 QtBase 首条
glibc 补丁完成后强制终止，随后在 Qt Declarative 第一个归档文件解出后再次强制
终止。修复前的构建器在第一次终止后已暴露半成品正式目录，回归按预期失败。
修复后两次续跑都重做未完成的阶段，两个最终目录的文件路径及内容摘要与原先已
完成编译的对应树完全相同。

该回归止于配置前，替代了实际 CMake 操作。此前的源、构建、ELF 与客体回执仍
绑定到原配方，新配方单独保存源树对照与中断结果。
[续跑回执](../reports/qt_quick_unified_profile_20261127/source-resume.json)

当前验收涵盖软件渲染与 Interactium 图形集成。发行载体的接收者重链接、
安装替换与回退照常走其独立的验收门。
