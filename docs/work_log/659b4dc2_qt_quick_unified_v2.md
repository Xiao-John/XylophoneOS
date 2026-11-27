# 659b4dc2 · 使用统一 glibc SDK v2 的 Qt Quick

本轮从主线 `1afc6a2c` 开始，用已由签名 glibc 与 GCC 源码构建的显式
`xos-x86_64-glibc-unified-cxx-v2` 工件重建静态 Qt 6.8.3。先核对独立
SDK 的 profile、sysroot 和六项 Linux x86-64 交叉工具，再校验 QtBase 和
Qt Declarative 的锁定原档。沿用已验可搬移套件的 Linux arm64 宿主生成器。
Qt 目标编译和安装目录是新建的 Linux 文件系统。原 v1 目标目录和回退材料
以只读方式保留。
[统一 v2 SDK](ee216d1d_glibc_file_network_unified_sdk.md)

## QtCore 先验

交叉编译数据库中的 213 项 QtCore 命令使用 v2 sysroot。刚生成的
`libQt6Core.a` 通过现有 QtCore 夹具的实际静态链接，在普通 ISO
`bc93710bc3cd1879` 经 xsh 运行 QThread 和内嵌资源，输出
`QT_CORE_SMOKE_OK` 并退出 0。空闲页、任务与完成项归还到
`129709 / 3 / 1`。
[QtCore 编译与链接绑定](../reports/qt_quick_unified_v2_20261127/core_binding.json)
[QtCore 客体](../reports/qt_quick_unified_v2_20261127/core_guest.json)

## 工具包与独立接收

构建并安装 QtBase、Qt Declarative 和静态插件。目标回执列出 14 项归档，
包括 Core、Gui、Qml、QmlMeta、QmlModels、Quick 及关联依赖。分别核对两份目标
CMake 编译数据库，配置的 601 项 QtBase 和 1,459 项 Qt Declarative 命令均使用
v2 sysroot。现场链接直接绑定安装归档。把 v1 SDK 配给 v2 目标前缀时，构建器在
创建应用输出前拒绝了输入。

生产方用完整安装前缀和锁定宿主工具链接参考应用，打包 159 MiB 的开发套件。
独立 Linux arm64 容器断网解包到新路径，重新编译和链接从 Git 导出的三个应用
源文件。接收方只挂载套件、应用源码和 XOS 构建支持。两方 ELF 的 23 个文件段中
22 个内容一致，`.rodata` 存在差异，分别记录两个 ELF 的摘要。
[完整目标回执](../reports/qt_quick_unified_v2_20261127/target_receipt.json)
[接收方链接回执](../reports/qt_quick_unified_v2_20261127/consumer_app.json)

## 图形客体与相对路径回归

首次使用相对路径传入应用回执和 ELF，验收程序在启动 QEMU 前误把相对路径
与绝对路径比较。修复 `7332d2ab` 先解析回执目录，再使用原有路径约束查找
ELF。用该提交重建普通 ISO `90b485d08e5b6f97`，以相同相对路径复跑。
验收核对源、系统清单、镜像、接收方 ELF、FAT 读回及 SDK 摘要。ABI 对照和
镜像的 10 项许可材料检查通过。

QEMU 11.1.3 TCG 分别经 xsh 和同一 v2 profile 的 Dash 运行接收方 ELF。
两次均完成两轮软件渲染，观测到文本、动画推进、PS/2 按键变色、窗口关闭与重开。
xsh 与 Dash 首帧分别耗时 16.254 秒和 15.371 秒。应用退出后恢复到图形服务运行时
的 `121633 / 5 / 3`，停止服务后恢复到 `129709 / 3 / 1`。两次均记录 QMP
像素摘要、线程回收和正常退出。
[xsh 回执](../reports/qt_quick_unified_v2_20261127/xsh.json)
[Dash 回执](../reports/qt_quick_unified_v2_20261127/dash.json)

## QML 引擎独立客体

用接收方套件提供的目标工具链和宿主生成器配置 `tests/fixtures/qt6/qml`，
构建 `qml_probe` 和 `qml_quota_probe`。核对 ELF 的实际链接命令选用了
搬移后的 QtCore、QtQml 和 v2 libc 归档。在同一修正镜像上，普通夹具完成三轮
引擎、静态资源模块、JavaScript、属性绑定、缺失模块诊断和 GC 检查。
配额夹具用完虚拟保留额度，触发预期的 QV4 保留失败和进程 fault。
两次执行前后均回到 `129709 / 3 / 1`。
[引擎链接回执](../reports/qt_quick_unified_v2_20261127/qml_engine_link.json)
[普通引擎](../reports/qt_quick_unified_v2_20261127/qml_probe.json)
[VM 配额](../reports/qt_quick_unified_v2_20261127/qml_quota_probe.json)

## 复现

按 [Qt Quick 构建指南](../../src/ports/qt6/quick/unified_sdk.md) 指向 v2
的 `sdk/` 与 `profile.json`，使用同一 Linux arm64 环境和已锁定 Qt 原档。
先用 `build_target.py` 在全新的 Linux 文件系统构建目标，再用
`build_app.py` 链接应用并通过 `quick_kit.py` 搬移套件。在无生产端构建目录的
接收环境，使用独立导出的夹具重新链接应用。普通镜像先运行
`python3 -B scripts/build.py --quiet-demos-on-launch --output-dir "$SYSTEM"`。
Dash 使用向同一 SDK 发出的构建回执。客体启动、PS/2 输入和资源回收沿用
`tests/qt6_quick_guest.py`。本轮从相对路径传参，使用显式
`--first-frame-timeout 240`，两次实测都低于默认的 60 秒。

QML 探针的 CMake 配置使用同一 Qt 目标前缀、`QT_HOST_PATH`、
`Qt6QmlTools_DIR`、链载工具链及 `XOS_GLIBC_*` 环境。通过
`cmake --build "$PROBES" --target qml_probe qml_quota_probe` 链接，再分别
运行 `tests/qt6_sdk_probe.py`。普通夹具使用 `--marker QML_PROBE_OK`；
配额夹具使用 `--outcome faulted --code 0 --marker 'QV4 XOS VM reserve failed (-4)'`。
[证据根清单](../reports/qt_quick_unified_v2_20261127/manifest.json)
