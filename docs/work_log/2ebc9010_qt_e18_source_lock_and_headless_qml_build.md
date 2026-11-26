# 2ebc9010 — Qt E18 source lock and headless QML build

2026-11-26 · 基线 `9f7a9a0f`。本轮交付 E18 的源码、宿主构建和静态模块夹具。目标端 G06 和 Quick G07 均待验收。

## 源码与构建

- QtBase 使用现有 6.8.3 锁。Qt Declarative 6.8.3 标签提交为
  `2ec235a2235a119887683e55787b93f99dc5f12f`，上游 `dependencies.yaml` 绑定的 QtBase
  提交与仓库原锁一致。Qt 官方发布页给出的 Declarative 源包 SHA-256 为
  `1f03a2b8f5588b4face7da87926e9b2c1372b3a32157c52df07a75067a9db1af`。
  Mac 直连曾遇 TLS 失败，从官方列表中的 Constant 与 FAU 两个镜像取得的完整字节均匹配。
  [Qt 发布摘要](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/qtdeclarative-everywhere-src-6.8.3.tar.xz.mirrorlist)
- `build_host.py` 校验两份源包后分别解压，使用同一私有宿主 prefix 安装静态 QtCore 和
  QtQml。Apple arm64 复用 QtBase 的 ACLE 补丁。关闭宿主 QtGui、QtNetwork、QML JIT 和
  调试协议以验证解释执行。XML stream writer 保留以便构建 `qmlcachegen`。工具按宿主
  体系结构构建，目标头文件、目标 Qt 和 XOS SDK 均不进入此 prefix。
- `tests/fixtures/qt6/qml` 使用 Qt 原生 CMake 入口构建静态 `Xos.QmlProbe` 模块。
  从 qrc 加载入口与模块，使用 QV4 执行 JS、重算属性绑定、报告缺失模块，验证显式销毁与
  可达/不可达 JS wrapper 的回收行为。夹具要求 6.8.3 的静态 Core/Qml。
- 许可证材料登记到 `licenses/components.json`。QtBase 和 Declarative 的五份共同
  LGPL/GPL/商业/例外文件逐字节一致。新增 BSD-2/3 文本与上游 MASM 许可和 attribution，
  绑定源包及实际材料摘要。逐归档成员核对、静态重链接和分发资格未运行。

## 复现

在仓库根目录运行。QtBase 和 Qt Declarative 参数指向各自完整的上游 tar.xz。

```sh
python3 src/ports/qt6/qml/build_host.py \
  --qtbase "${QTBASE_ARCHIVE}" --qtdeclarative "${QTDECLARATIVE_ARCHIVE}" \
  --output build/qt_e18_host --jobs 5
cmake -S tests/fixtures/qt6/qml -B build/qt_e18_host_fixture -G Ninja \
  -DCMAKE_PREFIX_PATH="${PWD}/build/qt_e18_host/prefix"
cmake --build build/qt_e18_host_fixture
QML_DISABLE_DISK_CACHE=1 build/qt_e18_host_fixture/qml_probe
```

此次宿主是 macOS arm64，使用 Python 3.12.15、CMake 4.4.4、Ninja 1.13.2 和 Apple
Clang 21.0.0。只安装 Apple Command Line Tools 的环境传入 `--apple-clt`。首轮默认
macOS 27.2 SDK 报告 Qt 声明的 Xcode/SDK 支持范围警告，并在编译 `qv4sequenceobject.cpp`
时因 libc++ 排序实现要求 `QTaggedIterator::operator[]` 而失败。第二轮选择本机的
macOS 26.5 SDK 构建通过，Qt Declarative 源码保持上游原件。复现该环境时向宿主构建附加
`--apple-clt --apple-sdk "$(xcrun --sdk macosx26.5 --show-sdk-path)"`，并向夹具的
CMake 命令传入同一 `-DCMAKE_OSX_SYSROOT`。

新目录构建夹具并清空 QML 插件路径覆盖后得到 `QML_PROBE_OK`。一次启动完成三个
引擎周期，每个周期测试静态模块、资源加载、JS、属性重算、缺失模块、对象销毁与 GC。
`otool -L` 只列出 macOS 系统库。安装后的私有 prefix 含 `moc`、`rcc`、`qlalr`、
`qmlimportscanner`、`qmltyperegistrar` 与 `qmlcachegen`。

| 本次宿主产物 | SHA-256 |
| --- | --- |
| `receipt.json` | `7d134fd450f8d08bbb3221c3da80ff255ff304cc10d4e6435b07660b000eb071` |
| `libQt6Core.a` | `7f663fd1e5adb575c077c15b34919f8376661817006d6d1487750f5e4edb7c7d` |
| `libQt6Qml.a` | `bf282deddaefd6a41812889d9466146c02928e840722e5db427a8facd5e8a5f2` |
| `qml_probe` | `3f6027499bd6aad3934b3515b16c381a7a30a01511de0fa58859aac68de1620f` |

错误 QtBase 源包摘要和已存在的构建目录分别被拒绝，错误摘要未创建输出。夹具 CMake
拒绝本机 Qt 6.12.0。独立 XOS 构建 `54bc521c6550e90b` 的 `license_audit.py` 通过
10 份 SDK 许可材料与登记校验。宿主构建、夹具和许可日志位于此工作树的
`build/qt_e18_inputs/`。

## XOS 目标路线与缺口

| 上游调用或构建条件 | 当前输入与下一步 |
| --- | --- |
| `qtdeclarative/CMakeLists.txt` 要求匹配的目标 QtBase Core、BuildInternals、命令行解析及临时文件。启用 QML cachegen 还需要 XML stream writer。 | 已有 6.8.3 发行 QtBase QtCore/Gui/Widgets 属于旧 newlib SDK。目标端先用合格的独立 glibc C/C++ SDK 重建 QtBase，验证 QtCore 线程、计时、静态对象、文件及临时文件，再以 `QT_HOST_PATH` 指向本轮的同版本宿主工具，配置独立的目标 Qt Declarative。 |
| `src/qml/memory/qv4mm.cpp` 的 GC 堆通过 `PageReservation` 保留、提交、去提交和释放。普通段含 64 个 64 KiB chunk，保留地址与实际页消耗需分别记录。 | 关闭 JIT 后仍需这些操作。现有 XOS glibc `mmap` 仅接收私有匿名 `PROT_NONE`，`mprotect` 可提交写页，`madvise` 在盘点的候选 SDK 中仍列为 stub。上游 MASM 在非 Linux 的 Unix 分支从 R/RW mmap 起步，在 Linux 分支用 `MAP_NORESERVE`，两者与当前 XOS 子集不匹配。目标实现需使用 [sys67 保留/提交/去提交/释放](../contracts/anonymous_vm.md) 并测试零填充、地址对齐、内存耗尽与回收。 |
| `qv4compilationunitmapper_unix.cpp` 映射基于磁盘的编译单元。 | XOS 现有匿名 VM 不提供文件 `MAP_SHARED`。G06 首轮使用 qrc 与静态模块，关闭磁盘缓存，并确认禁用路径与目标链接依赖。 |
| `qtdeclarative/src/CMakeLists.txt` 的 Quick 构建条件包含 QtGui、目标 QML animation 和宿主 `qsb`。 | E19 另锁定 Qt Shader Tools 源包。此上游 Declarative tag 中的相容 Qt Shader Tools ref 为 `75786914936b73212ae342f83c9a27ae4a69f406`。软件场景合并到目标 QPA/显示服务之后独立验证文本、输入、帧时、窗口重开和资源回收。 |

用于核对 stub 登记的 glibc C++ 候选 manifest SHA-256 为
`f40aef3f27a7b731bbf77bb1a2615f57d3b6c6e484f27e775c5cff3e72dd44a8`。

本轮不动公共 ABI、QtBase 历史发行产物及默认 SDK。宿主阶段不能代替客体 G06 的耗尽、
退出与资源回收，也不能推导 G07 的显示、输入或帧时结果。
