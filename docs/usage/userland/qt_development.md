<!-- SPDX-License-Identifier: Apache-2.0 -->
# Qt 图形界面开发（宿主交叉编译）

XOS 的 Qt 路线是 **宿主交叉编译静态应用 → 导入工作盘运行**；客体内没有 Qt
运行库与编译栈。资格为受限功能级（E16/E17），不是完整发行分发资格。

## 前提

- 宿主 `x86_64-elf-g++`、`nasm`；已完成 `make build`（SDK）。
- **Qt 6.8.3 静态交付物**：发行资产 `xylophoneos_revival_<版本>_qt6_static.tar.gz`
  （17 个 `.a`、头文件、构建配方、补丁、许可文本、qtbase 源包），或本地
  `build/qt6_b1_*/widgets` 构建树。库不在 `build/sdk` 内。

## 构建 Qt 应用（实测入口）

1. **配置/构建 Qt 本体**（若用源码树；发行包已带编好的库可跳过）：
   `python3 src/ports/qt6/configure_widgets.py --source <qtbase> --build <out> --sdk <sdk> --binutils <bin> --host-qt <hostqt>`，再 `ninja -C <build>`。
   mkspec：`xos-g++`；48 项特性显式关闭（无网络/OpenGL/fontconfig 等）。
2. **链接应用**：以 `src/ports/qt6/build_widgets_fixture.py` 的实测命令为准，静态链
   `libQt6Widgets.a libQt6Gui.a libQt6Core.a` + bundled（pcre2/zlib/freetype/harfbuzz）
   + SDK 头与 `libxos*`/libc。参数细节以该脚本 `--help`/源码为准。
3. **导入与运行**：ELF 用 `scripts/work_disk.py import` 放入盘，在 `xsh>` 下
   `exec-file /out/app.elf`（与普通用户态程序相同，见 [getting_started](getting_started.md)）。

## 能力边界（资格口径）

| 项 | 状态 |
|---|---|
| E16 QtGui/QPA | `SCOPED_FUNCTIONAL_PASS`：G01/G03/G04 PASSED；单全屏 raster 已验 |
| E17 Widgets/Aurora | `PASSED_RESTRICTED_FUNCTIONAL`（G05） |
| QPA | `QT_QPA_PLATFORM=xos`（Aurora static QPA）；非桌面窗口系统 |
| distribution（随包分发核验） | 发行 `qt6_static` 资产已做 B4 打包核验；逐成员许可映射为工程记录，非法务意见 |
| QML/Quick | 未实现，不在范围 |
| 客体内编译 Qt | **不可用**：发行 SDK/`compile.py` 不含 Qt 库与头 |

## 相关

- 交付物规格与重链接步骤：`src/ports/qt6/REDISTRIBUTION.md`
- 资格报告：`docs/reports/qt_e16_qualified_20261028/`、`qt_e17_qualified_20261029/`
- 客体显示原生路径（无 Qt）：见索引「显示/ gfxdemo」与 `docs/state.md` 能力表
