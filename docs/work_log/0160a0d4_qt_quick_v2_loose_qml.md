# 0160a0d4 · Qt Quick v2 从文件系统加载和渲染 QML

可搬移套件的原验收已覆盖编进 ELF 的 QML。本轮从 Git 导出独立应用，
在无网络的 Linux arm64 接收环境用冻结套件编译与链接。夹具把场景和同目录
的调色板部署到 FAT，应用通过 `QQuickView::setSource(file://…)` 读取。

## 文件元数据

普通 ISO `1f593b6ca9cd7904` 上的原版 ELF 以 `File is empty` 退出 1。
对同一个 1,073 字节文件，`stat/stat64/fstat/fstat64` 均报告常规文件
`0100644` 和正确大小，读和 seek 也确认了 1,073 字节。Qt 调用实际链接的
`statx` 时使用 `AT_NO_AUTOMOUNT`。路径、nofollow 路径和描述符三种调用
都返回 `EINVAL`，`QFileInfo` 因此得到大小 0，`QFile` 仍可顺序读取。

GNU 的通用 `statx` 将该标志转交给 `fstatat64`。两种 `fstatat` 入口
现在接受该查询位。XOS 没有自动挂载，置位仍走现有的文件元数据服务。
原配置重新编出的两个基准成员分别与冻结归档成员字节一致。用同一命令只
重编改动的对象，私有验证归档的 1,686 个顺序成员仅这两个发生变化。
用冻结套件的真实链接参数复核原 ELF 的字节一致性，再用该归档重链。

修后的同客体元数据探针中，三种 `statx` 都报告大小 1,073 和
`0100644`。Qt 文件有正确大小，可以寻址并读回全部字节。
公共文件回归的原版在新断言返回 `EINVAL`，修订版分别通过单线程
33 项和多线程 39 项查询与文件断言，包含未知标志位 `EINVAL` 以及
非 `AT_FDCWD` 相对路径 `ENOTSUP`。三次启动均归还客体资源。
[元数据串口摘录](../reports/qt_quick_v2_loose_qml_20261127/metadata.log)
[公共文件回归](../reports/qt_quick_v2_loose_qml_20261127/files.json)

## 外部 QML 客体

场景夹具使用独立名称 `ScenePalette`，避开 QtQuick 的内置 `Palette`。
最终夹具的 1,078 字节场景与冻结 SDK 的常规链接仍触发 `File is empty`。
用修订归档重链后，两次冷启使用同一个 ELF、场景文件及镜像，FAT 上仅
调色板不同。QEMU TCG 11.1.3 的像素验证观察到薄荷主题由
`#35c29d` 变为 `#f0a945`，紫色主题由 `#a070f0` 变为 `#5dd6f5`。
两种主题均经 PS/2 触发 QML 状态变化和正常退出，输入线程已归还。停止
图形服务后均恢复到 `129709 / 3 / 1`，FAT 文件逐字节读回一致。
[断网构建及输入绑定](../reports/qt_quick_v2_loose_qml_20261127/binding.json)
[冻结 SDK 的客体阴性对照](../reports/qt_quick_v2_loose_qml_20261127/frozen-negative.json)
[修订后两次冷启](../reports/qt_quick_v2_loose_qml_20261127/quick.json)
[证据根清单](../reports/qt_quick_v2_loose_qml_20261127/manifest.json)

## 复现

按照 [Qt Quick 构建指南](../../src/ports/qt6/quick/unified_sdk.md)
使用已包含修复的 v2 SDK 重建目标前缀和可搬移套件。以
`tests/qt6_quick_external_guest.py` 验证外部场景。公共 libc 断言位于
`tests/fixtures/glibc_g3/files_public_probe.c`，由既有
`tests/glibc_static_guest.py --suite files` 运行。

本轮回执绑定的是普通 ISO、冻结 Qt 和两个替换了静态归档成员的客体 ELF
验证路径。完整 SDK 重新发行、动态链接与安装镜像仍需各自的发行验收。
