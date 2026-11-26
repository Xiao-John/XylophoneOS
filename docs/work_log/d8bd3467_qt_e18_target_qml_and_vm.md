# d8bd3467 — Qt E18 target QML and VM

2026-11-26 · XOS 基线 `9f7a9a0f`。沿用 [QtCore glibc 复验](8d6f3d2c_qt_e18_glibc_qtcore_target_build.md)
的 6.8.3 QtBase、已绑定 glibc C/C++ sysroot 与宿主编译器。Qt Declarative 6.8.3
源包复用 [已校验的源锁](../../src/ports/qt6/qml/source_lock.json)。

## 目标适配

- QV4 堆、JS 栈及 GC 栈使用现行 XOS 匿名 VM。保留、提交、去提交和解除分别调用
  SDK 的 sys67 接口。栈两端维持未提交的 guard page。页尺寸取自 VM ABI，
  申请可执行内存会报错。VM 失败使用 QV4 的致命错误路径，带操作名和真实返回值。
- 目标禁止 QML 磁盘缓存，错误路径报告此能力缺失。首轮夹具将 QML、qmldir 静态模块
  和入口嵌入 qrc，以 QV4 解释执行。JIT、调试协议、网络和 worker script 关闭。
- QV4 通过 pthread 获取真实的栈边界。首轮客体中，128 KiB 默认安全余量用完了
  128 KiB 主栈，首次 JS 调用返回 `RangeError`。QML 加载器请求 8 MiB 栈也被 SDK
  拒绝。XOS 现在使用实际原生栈的一半或 128 KiB 中的较小值作为安全余量，加载器使用
  SDK 的默认 256 KiB 栈，AST 递归上限收紧到 64 层。
- 保留两份客体夹具。常规夹具覆盖 qrc、静态导入、JS、属性绑定重算、缺失模块诊断、
  QObject 销毁和可达/不可达 JS wrapper GC。配额夹具建立两个 4 TiB 稀疏保留，
  触发新的 QV4 保留失败，检查诊断、退出状态和系统资源恢复。

## 构建

在同一个 Linux arm64 环境先使用 QtBase 构建各自独立的宿主、目标 prefix。以
`cmake --build` 完成约束内的 QtBase 默认目标，再用 `cmake --install --prefix`
安装。QtBase 构建树直用时先后遇到缺失的 mkspec 和 CMake helper，安装后的 prefix
提供这些文件。复用 QtCore 目标构建的 `libQt6Core.a`，并绑定原 SDK。

将 Qt Declarative 锁定源包解压到一个独立源目录，依次应用
`src/ports/qt6/qml/patches/xos_qv4_vm.patch` 和 `xos_qv4_stacks.patch`。将
`src/ports/qt6/qml/runtime/os_allocator_xos.cpp` 复制到该源目录的
`src/3rdparty/masm/wtf/`。保持宿主与目标构建目录独立。

```sh
cmake -S "${QML_SOURCE}" -B "${QML_HOST_BUILD}" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="${QT_HOST_PREFIX}" \
  -DBUILD_SHARED_LIBS=OFF -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF \
  -DFEATURE_qml_jit=OFF -DFEATURE_qml_debug=OFF
cmake --build "${QML_HOST_BUILD}" --target host_tools --parallel 7
```

目标配置使用 `${QT_TARGET_PREFIX}/lib/cmake/Qt6/qt.toolchain.cmake`，传入与
`build_core.py` 相同的 `XOS_GLIBC_*` 和 `XOS_SOURCE_ROOT` 输入。指定
`QT_HOST_PATH` 为 QtBase 宿主 prefix，`QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH`
为宿主 Qt Declarative 构建目录，以及同目录下 `lib/cmake/Qt6QmlTools` 为
`Qt6QmlTools_DIR`。使用 Ninja、Release、静态库，关闭示例和测试，以及
`FEATURE_qml_jit`、`FEATURE_qml_debug`、`FEATURE_qml_worker_script`。指定
`CMAKE_INSTALL_PREFIX` 为同一目标 QtBase prefix，构建并安装 Qt Declarative。
随后复用该目标工具链与宿主工具参数配置和构建 `tests/fixtures/qt6/qml`。

宿主编译器及工具版本延续先前的 QtCore 复验。日志和产物保存于
`build/qt_glibc/`。物理主机余量有限，保留锁定归档、已验宿主 prefix 和目标证据，
清理了本轮可重建的失败构建中间文件。

## 客体验证

源码 `ee6e55ba` 的目标 Qt Declarative 与两份夹具重新构建和链接，复用在
`74eaa79a` 构建的同一 XOS 镜像。两提交间的差异属于 Qt 端适配、夹具诊断和
许可登记。两份 ELF 均为静态 x86-64 ET_EXEC。glibc 候选 manifest 仍为
`7eee04884a96ced6de12d20794af6809f544e3f15bc4e409b4197e58b1583d7a`。

- 直接 xsh 入口的常规夹具执行三个引擎周期并输出 `QML_PROBE_OK`，退出 0。
- 配额夹具输出 `QML_QUOTA_ARMED` 和 `QV4 XOS VM reserve failed (-4)`。
  xsh 报告预期 fault，vector 13。这个失败来自虚拟保留配额。
- 两次运行的资源计数前后都为 `[129714, 3, 1]`。配额复验首次在宿主测试盘导入
  阶段失败，释放旧的可重建夹具后，使用相同 ELF 重新导入并通过客体检查。

用 `tests/qt6_sdk_probe.py` 启动相同镜像、指定实际 ELF。普通夹具使用
`--marker QML_PROBE_OK`，配额夹具使用
`--outcome faulted --code 0 --marker 'QV4 XOS VM reserve failed (-4)'`。

| 产物 | SHA-256 |
| --- | --- |
| glibc QtCore 归档 | `9a6f3970166e56d3162b6870fe04d699106cc6a98ef7325c2bad978076c19a7c` |
| glibc QtQml 归档 | `b2272fbc77ff934929bffd58ace837ed59a82a2ea589c5038d18c9b41e8ad335` |
| 常规 QML ELF | `c99cb2460d95ca7ae1adeb14dcc3b184f85f7ecdfbb8924086c8311438fd5595` |
| 配额 QML ELF | `4497f63edea2fa7eba6a96f42650691054826b676adaf209ff4e1ac56122e893` |
| XOS 镜像 `5def9f26dc747cdf` | `37403494630ea1e46eefd9a1f0950c372b05cc9945045c3aedbcf0bc2e279c3c` |
| 系统构建清单 | `7786c8d3f68c0075e6f7b361dc9cb0c0c55ee78e7460b312c768ff7693c9ab07` |
| 常规客体回执 | `1a4c601fac41c39c44ba5764684b4ff270642a2ca915a40adccd33b83f55643b` |
| 配额客体回执 | `79380aa25b9ee84df99b14d0f32bcef3f16a00dfad2a1c926cbfef708781859f` |

G06 在单核 QEMU 11.1.2 TCG 的无界面、静态资源子集通过。独立物理页耗尽、极深
语法、多引擎并发、Dash 入口、完整许可审查和静态分发待验。登记的 Qt Declarative
许可文件存在性和摘要已复核。

## Quick

实际配置的 QtCore 目标 kit 未启用 QtGui，Linux 6.8.3 宿主尚无 `qsb`。
Qt Declarative 的配置要求这两项与 QML animation 才启用 Quick。G07 尚未运行。
