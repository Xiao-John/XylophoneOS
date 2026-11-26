# 48bcc2f4 — Qt E19 glibc target QtGui packages

2026-11-26 · Qt 6.8.3 · XOS glibc C/C++ 锁修复候选。静态目标 QtCore、QtGui、
FreeType 和 HarfBuzz 已构建，QtBase CMake package 和 QtBase SBOM 已安装。
同一目标 prefix 随后配置 Qt Declarative，实际在 Qt Quick 构建中运行了
[宿主 `qsb`](a95b1a20_qt_e19_host_shader_generation.md) 生成场景图 shader。

QtBase 源树首先用 [`prepare_gui_source.py`](../../src/ports/qt6/prepare_gui_source.py)
校验和准备，再应用 [glibc Core 补丁](../../src/ports/qt6/glibc/glibc_qtcore.patch)
和 [glibc QtGui 平台插件补丁](../../src/ports/qt6/quick/glibc_qtbase_platform.patch)。
首轮已编译 QtGui，默认目标继续编译的 `QtMinimal` 插件引用 XOS QtGui 未提供的
通用 Unix dispatcher 私有头文件而失败。补丁只在 XOS glibc 配置跳过上游平台插件，
该配置的应用链接仓库现有的 Interactium QPA。重配后继续既有构建并完成安装。

沿用 [E18 QtCore](8d6f3d2c_qt_e18_glibc_qtcore_target_build.md) 的
`glibc_toolchain.cmake`、`XOS_GLIBC_*` 与 `XOS_SOURCE_ROOT`，以及同一 C/C++
候选绑定。GCC、G++、as、ld、ar 和 ranlib 的实际 SHA-256 与 SDK manifest
一致。传入同版本原生 QtBase 构建树为 `QT_HOST_PATH`，安装到新的目标 prefix。

- Release、静态、Ninja；关闭示例、测试、基准和预编译头。
- 启用 `gui`、`freetype`、`harfbuzz`，选择 Qt 随带的 FreeType、HarfBuzz，
  使用 `INPUT_opengl=no`、`QT_QPA_DEFAULT_PLATFORM=xos` 和 `QT_QMAKE_TARGET_MKSPEC=xos-g++`。
- 关闭 `configure_gui.py` 的 `off` 列表及 `glib`、`system_zlib`、`system_pcre2`。
  `cmake --build` 后执行 `cmake --install`，使目标工具链和库引用一同落在新 prefix。

| 输入与产物 | SHA-256 |
| --- | --- |
| glibc C/C++ SDK manifest | `7eee04884a96ced6de12d20794af6809f544e3f15bc4e409b4197e58b1583d7a` |
| glibc SDK profile | `5dde8b7cd0a2e5fe9d0db892b81f88eeed36e2f72ba89826209acb013362b10a` |
| `libQt6Core.a` | `6572280dee0959c173828241d3eb1c53f05a2e8617c1d6e6330b99b2f1a7ac7e` |
| `libQt6Gui.a` | `17b33e879ea78ec5189567218892eba6790e01d4964fee1f459bcfbec4559b99` |
| `libQt6BundledFreetype.a` | `9552abedb8f0a4afc1c052cb692dee2bfb3cb15e28829d6e2d3c9053ad945935` |
| `libQt6BundledHarfbuzz.a` | `3fe3cb77d4d51290125574c6c26f38a69d9bfbc91a6cdacc7291d28d95849300` |
| `qtbase-6.8.3.spdx` | `444d3caf6c97edfbe80eb213c0e45738b2d909d924f14814855c164fd9a5e8ed` |

本回执确认 QtGui 目标归档、安装和 Quick 配置前置。最终 ELF 链接、客体场景与许可
分发审查分别待验。
