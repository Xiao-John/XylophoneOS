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

## 复现

按 [Qt Quick 构建指南](../../src/ports/qt6/quick/unified_sdk.md) 指向 v2
的 `sdk/` 与 `profile.json`，使用同一 Linux arm64 环境和已锁定 Qt 原档。
先用 `build_target.py` 在全新的 Linux 文件系统构建目标，再用
`build_app.py` 链接应用并通过 `quick_kit.py` 搬移套件。在无生产端构建目录的
接收环境，使用独立导出的夹具重新链接应用。普通镜像先运行
`python3 -B scripts/build.py --quiet-demos-on-launch --output-dir "$SYSTEM"`。
Dash 使用向同一 SDK 发出的构建回执。客体启动、PS/2 输入和资源回收沿用
`tests/qt6_quick_guest.py`，首次帧的期限以实测回执为准。
[证据根清单](../reports/qt_quick_unified_v2_20261127/manifest.json)
