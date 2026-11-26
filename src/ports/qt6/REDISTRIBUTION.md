# Qt 静态再分发：对应源码与可重链接交付物规格

2026-11-03 · 本文件与同目录 `redistribution_manifest.json`（机器可读，由仓库实测生成）
一起构成 **LGPLv3 §4d0/§6 与 GPLv3 §5(b)** 的工程规格与自查清单。**它不是法律意见**；
最终以适用许可原文与法律判断为准。

## Qt Quick 6.8.3 glibc 套件

Linux arm64 宿主的 Qt Quick 套件采用独立的[材料清单与重链接配方](quick/release_materials.md)。
`quick/release_materials.py` 从可验证的套件及外部示例输出生成离线材料，`quick/relink.py`
校验逐文件清单并执行示例的静态重链接。材料包含 QtBase、Qt Declarative 与 Qt Shader
Tools 对应源、XOS 修改与构建配方、应用对象及目标归档的逐成员摘要。

复核覆盖 18 份目标归档的 1,066 个成员。1,024 个直接编译源的 SPDX 声明或 Qt 组件归属
可在对应源内定位。42 个生成成员已绑定工具、输入和归档对象，早前未留存的 8 个生成源码均
通过同字节对象复演。18 个目标 rcc 对象中的 311 次资源出现均按原 `qrc` 核对路径和内容。
Qt Declarative 官方归档与 XOS 补丁可重建实际构建的源码树。

宿主 48 项文件已核对来源。其中 17 份宿主静态归档的 823 个成员均与留存对象逐字节一致。
直接编译源、JPEG 复制变体和其它生成输入均记录来源与可定位的许可声明；2 个宿主 rcc
对象内的 3 次资源出现也已验证。两份 QtBase 预编译着色器有
[已实测的字节级重生成配方与分发声明](quick/backingstore_shader_distribution.md)。
GNU 编译器 seed 的复建、成品采用的许可分支与传递许可、各发行渠道和安装信息仍需核对。

本文件下方记录的是 0.0.2-1103 的 Qt Widgets 发行范围。

## 0. 当前状态（先读）

- **XylophoneOS 0.0.2-1103 按用户指令（2026-11-04）随包分发 Qt 静态交付物**：
  静态库（`build/qt6_b1_20261031/widgets` 10 库 / `widgets2` 7 库）、头文件、构建配方、
  10 个补丁与 13 份许可文本；对应源码（qtbase 6.8.3 源包 + 补丁）同批发射。
  发版门槛已于 2026-11-04 执行：打包核验 25/25 PASS
  （`packaging_verification_20261104.json`）、安全审查 PASS_WITH_LIMITS
  （`security_review_20261104.json`，CVE 扫描 NOT_RUN 如实记录）。
- 分发资格：**本版按上述门槛结果随包**；逐成员许可映射与文本覆盖为工程记录
  （非法务意见）；商业路径仍 N/A。
- 本规格解决的是"**一旦要分发，必须给什么、怎么给**"，把该报告的缺口②成文化并落到可执行条目。

## 1. 义务 → 本仓库对应物

| 义务（条款） | 对应物 | 复核方式 |
|---|---|---|
| 对应源码：首选修改形式（§4d0） | 锁定源包 `qtbase-everywhere-src-6.8.3.tar.xz`，sha256 `56001b90…49e0b80`，URL 见 `source_lock.json`；本地树 `.cache/xos_seed/qt6/qtbase-6.8.3` | 比对 `source_lock.json` 与源包哈希 |
| 全部修改（§4d0、§2 修改通知） | `patches/` 下 **10 个补丁**，触及 **21 个上游文件**，逐个 sha256 见 manifest `patches`；修改通知见 `patches/MODIFICATIONS.md` | `sha256sum src/ports/qt6/patches/*.patch` |
| 构建信息与配方（§4d0(a)） | `configure_widgets.py` / `configure_gui.py` / `configure_target.py` / `xos_toolchain.cmake` / `mkspecs/` / `cmake/`；显式关闭 **48** 项特性（opengl/xcb/fontconfig/network/filedialog/eglfs/linuxfb/vnc 等），widgets2 树 CMakeCache `FEATURE_*=OFF` 合计 199 项 | manifest `build_recipe` |
| 可重链接能力（§4d0、§6） | 交付物必须让接收者能用自己的对象文件重新链接：提供静态 `.a`（或其成员对象）+ 上述配方 + 依赖 SDK + 本节重链接步骤 | 见第 3 节 |
| 许可文本与归属（§4d0、§6） | **13 份**已登记 Qt 文本（含本轮补入的 `LicenseRef-Qt-Commercial.txt`、`Qt-GPL-exception-1.0.txt`），哈希在 `licenses/components.json` 的 QtBase 条目 | `python3 scripts/license_audit.py` |
| 不附加限制（§6） | 交付物不添加任何限制接收者权利的条款；仅原许可文本 | 发布前人工核对 |

## 2. 实测产物（分发时必须随包）

| 树 | 根目录 | 静态库数 | 归档成员数 |
|---|---|---|---|
| widgets | `build/qt6_b1_20261031/widgets` | 10 | 766 |
| widgets2 | `build/qt6_b1_20261031/widgets2` | 7 | 756 |

逐库路径、sha256 与成员数见 `redistribution_manifest.json` 的 `static_outputs`。
**注意**：这些归档成员到源文件的逐成员许可映射在
`docs/reports/qt_member_license_20261103/`，未完成前不得声称"逐成员已审"。

## 3. 重链接步骤（接收者视角）

1. 取得随包的 qtbase 源包、10 个补丁、configure 脚本与 `xos_toolchain.cmake`。
2. 打补丁后按配方重建 Qt：
   `python3 src/ports/qt6/configure_widgets.py --source <src> --build <build> --sdk <sdk> --binutils <binutils> --host-qt <hostqt>`，
   然后 `ninja -C <build>`。
3. 用自己的应用对象文件重新链接：
   `-static -no-pie -nostdlib` + `libQt6Widgets.a libQt6Gui.a libQt6Core.a` +
   bundled 静态库（zlib/pcre2/freetype/harfbuzz）+ 依赖 SDK 的头与库；
   include 路径与库顺序以 `build_widgets_fixture.py` 的实测命令为准（那是已验收的链接形式）。
4. 随包携带第 1 节的 13 份许可文本与 `patches/MODIFICATIONS.md` 的修改通知。

## 4. 明确未完成 / 不适用（诚实清单）

| 项 | 状态 | 说明 |
|---|---|---|
| 打包核验（随包清单与哈希复核） | **PASS（2026-11-04）** | B4 25/25（`packaging_verification_20261104.json`）；随包资产哈希已入 CHECKSUMS |
| 商业许可核验 | **N/A** | 仓库无任何 Qt 商业授权材料，不作任何判断 |
| Qt 安全审查 | **PASS_WITH_LIMITS（2026-11-04）** | B5（`security_review_20261104.json`）；CVE 离线 NOT_RUN 已披露 |
| 逐成员许可映射 | **1522/1522 + 文本覆盖 262/262** | 见 `docs/reports/qt_member_license_20261103/`；工程记录，非法务意见 |
| Qt 二进制分发 | **已随 0.0.2-1103 发行** | 用户指令 + B4/B5 门槛后随包；商业路径 N/A；QML/Quick 未实现 |

## 5. 边界

本文件只描述"若分发 Qt 静态二进制，本仓库已备与未备的材料"，不构成：
许可兼容性法律结论、Qt 官方安全背书。工程门槛通过 ≠ 法律意见；
任何一步的复核结果以实际命令输出为准，不以本文件的文字代替。
