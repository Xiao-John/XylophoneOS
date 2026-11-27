# 74efcc27 · Mobius Widgets v2 原生接收与三次冷启

用 #363 的确切提交 `1ed63cb2` 及统一 glibc C/C++ SDK v2 原件完成
QtBase 6.8.3 的 Widgets 目标构建。客体使用源码 `960fce43` 对应的普通镜像
和同版 SDK 构建的 Dash。系统清单、镜像、SDK、Dash、Qt 目标回执和两个 XPK
分别以实际 SHA-256 绑定。[证据索引](../reports/mobius_widgets_v2_guest_20261127/manifest.json)

## Qt 目标与独立接收

独立配置探针的 788 条编译命令都指向 v2 sysroot，其中 176 条来自 Widgets。
完整构建使用同一份输入回执，完成 866 项 Ninja 步骤，并实际安装 Core、Gui
和 Widgets 静态归档。配置为 `Widgets=ON` 和 `FileDialog=OFF`。套件打包前
核对 7 个 Qt 归档、宿主生成器和安装树。生产容器用 1 个 CPU、2 GiB tmpfs；
记录约 2568 个 CPU 秒，内存峰值约 1.62 GiB。压缩套件为 63,870,775 字节，
宿主留存版本经 `zstd -t` 和 SHA-256 复核。
[目标构建记录](../reports/mobius_widgets_v2_guest_20261127/qt-target.json)
[目标回执](../reports/mobius_widgets_v2_guest_20261127/qt-target-receipt.json)

断网 Linux arm64 接收容器将套件解到新路径，只获得已打包的 Qt 前缀、同一 SDK
和 Mobius 源码。错误套件清单摘要在创建输出前被拒绝。两个独立目录分别构建
桌面与会话并打包修订 0 和 1。两次的桌面 ELF 逐字节相同，两次的会话 ELF 也
逐字节相同。两包分别通过同一 profile 下的完整校验。
[接收及包比对](../reports/mobius_widgets_v2_guest_20261127/receiver.json)

整包首个不同字节位于偏移 605，从零开始计数，属于首成员 `manifest.json`。
唯一不同的纳管文件是 `usr/share/xos.mobius/build_receipt.json`。两份单 ELF
回执中只有 `commands` 字段不同，替换各自构建目录后命令逐项相同。这改变
包内回执的两个 `build_receipt_sha256`。其余 48 个纳管文件均逐项一致，包含
两个实际程序及 46 份声明材料。

## 三次客体冷启

使用 Linux QEMU 11.1.3 及普通镜像 `6b7c91b4…`，对专用稀疏 FAT32 工作盘
执行安装、升级、卸载和重装。三个冷启阶段均逐项读回 49 个纳管文件和两个
ELF，并由 xsh 和 Dash 启动桌面。PS/2 输入成功切换主题，两份图像摘要分别
记录。六次桌面首帧用时 14.034–16.566 秒。升级盘另从显式授权入口启动正式
会话，首帧 14.149 秒。每次应用退出都收回线程和图形资源，停止图形服务后
均回到 `129709 / 3 / 1`（空闲页、任务、完成项）。

升级和卸载重装保留了原外观文件与新增的用户文档，原工作盘摘要保持一致。
真实 `xos-x86_64-glibc-thread-locks-cxx-v1` 历史包在 v2 profile 门被拒绝。
公开记录保留三份实际串口和 14 张图像的摘要。图像原件及两个私有 XPK 的
存档已逐项校验。
[客体回执](../reports/mobius_widgets_v2_guest_20261127/guest.json)

## 分发与重现范围

发布 v2 Mobius 静态二进制前，仍需以本次两个 ELF 的实际对象、归档和链接参数
生成对应的 Qt LGPL 替换材料，独立接收复链并验证可替换的 Qt 构建，再核对相应
源码、补丁和声明的完整性。Curvive 原图和嵌入 BMP 的公开分发依据仍待确认。
现有 v1 的产品复链证据继续绑定 v1。v2 的两个复验包是不同修订，证明 ELF
重现及一次实际升级。XPK 全字节重现仍需处理回执中的目录差异，并复验同修订
在独立构建环境的整包摘要。
[Qt 分发材料清单](../../src/ports/qt6/redistribution_manifest.json)
[Curvive 来源记录](../reports/mobius_unified_widgets_20261127/curvive_audit.json)

复现使用既有 [构建及打包命令](../../src/ports/aurora_desktop/README.md#build-from-a-relocated-widgets-kit)。
客体使用 `python3 -B tests/mobius_unified_widgets_guest.py`，传入系统构建目录、
统一 profile 和 SDK、套件清单、两份 XPK 及其 ELF 构建目录、同版 Dash 回执以及
历史包。公开客体 JSON 以逻辑盘文件名保留事务记录，记录原件摘要；串口归档
解压后与原件逐字节一致。
