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
