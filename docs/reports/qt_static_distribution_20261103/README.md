# Qt 静态分发审查（D7 · 0188 任务 C）

2026-11-03。范围：QtBase 6.8.3 静态构建的许可适用性与静态链接分发义务对照，
以及 0.0.2-1103 拟发布内容逐项核对。**本审查只读现有源码、锁定记录与 `build/` 产物，
未运行构建、未运行 `make license-audit`、未打包 0.0.2。**

## 0. 结论（先说结论）

1. **材料与义务对照已完成；静态分发资格审查未完成，不授予 Qt 静态分发资格。**
   逐成员许可映射、对应源码/可重链接对象打包、0.0.2 实际打包核验均为 **NOT_RUN**，
   见第 6 节。本报告不是法律意见，"材料检查通过"不等于"法律审查完成"。
2. 按当前 `scripts/` 发布打包脚本与 `build/sdk` 实际内容，**0.0.2-1103 拟发布物不含
   Qt 头文件、Qt 静态库或 Qt ELF**，因此在本版发行物中 Qt 静态链接分发义务
   **不触发（不适用）**；Qt 许可材料只作为第三方声明机制随包（第 5 节第 8 项），
   实际打包核验 NOT_RUN。
3. Qt 6.8 适用许可按仓库实际材料判定为 **Qt 逐文件三选一 + 商业**：
   `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`
   （锁定源码内实测 SPDX）。仓库已收录 LGPLv3/GPLv2/GPLv3 三份全文并逐文件核哈希；
   **未见任何 Qt 商业许可证据**，商业路径在本仓库内无材料支撑。
4. 一旦决定把 Qt 头/静态库/ELF 放进 0.0.2 或任何后续发行，第 4 节义务立即生效，
   第 5 节的"缺口"项必须先清零；当前状态**不满足**静态分发条件。

## 1. 审查输入（只读）

- `src/ports/qt6/`：`source_lock.json`、`prepare_source.py` / `prepare_gui_source.py` /
  `prepare_widgets_source.py`、`configure_widgets.py`、`xos_toolchain.cmake`、
  `patches/`（10 个补丁）、`qpa/`、`runtime/`、`licenses/`、`aurora/README.md`。
  该目录**没有顶层 README**，构建/锁定说明分散在上述脚本与 `docs/work_log/` 0062–0078。
- `licenses/components.json` 中 Qt 相关条目 3 条（见第 3 节）。
- `docs/licensing.md` 末节（E16 QtGui 段）：明确"功能测试、材料完整性检查不授予
  静态再分发资格；逐成员、安全审查、重链接/对应源码与完整分发材料仍 NOT_RUN"。
- `scripts/package_release.py`、`scripts/package_release_materials.py`、
  `scripts/package_release_sources.py`（发布打包脚本）。
- `build/sdk/`（SDK 实际内容与 `manifest.json`）、`build/qt6_b1_20261031/`
  （两棵既有 Qt 静态构建树，只读）、`build/releases/0.0.1-1026/`（最近一次冻结发行，
  作为 0.0.2 打包路径的参照）。
- 上游锁定源码树（本地缓存 `${XOS_XOS_ROOT}/.cache/xos_seed/qt6/qtbase-6.8.3-gui/`）
  用于读取 SPDX 与 `LICENSES/` 目录，未修改。

## 2. QtBase 6.8.3 静态构建方式确认（实测）

| 项 | 实测值 | 位置 |
|---|---|---|
| 锁定版本/标签 | 6.8.3 / `v6.8.3` / commit `c07c2d5a527a644d36e7853d55132ae38921682f` | `src/ports/qt6/source_lock.json` |
| 源包 | `qtbase-everywhere-src-6.8.3.tar.xz`，sha256 实测 `56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80`，与锁一致（1/1 匹配） | 本地缓存归档 + 锁文件 |
| 锁状态 | `candidate; target configuration and licenses not yet qualified` | `source_lock.json` |
| 静态 | `BUILD_SHARED_LIBS:BOOL=OFF`、`FEATURE_static:BOOL=ON`；`config.summary` 提示静态链接禁用动态插件，需静态导入 | 构建树 `CMakeCache.txt` / `config.summary` |
| QPA | `QT_QPA_PLATFORMS:STRING=xos`、`QT_QPA_DEFAULT_PLATFORM:STRING=xos`；`qpa/xos.json` = `{"Keys": ["xos"]}`；`qpa/qxos.cpp`（300 行）编成静态 `libQXosIntegrationPlugin.a` 并链入 ELF | 构建缓存、`src/ports/qt6/qpa/`、`build_widgets_fixture.py` |
| 无 QML/Quick | 源仅 qtbase（无 qtdeclarative）；`CMakeCache.txt` 无 `FEATURE_qml`/`FEATURE_quick`；`config.summary` 仅 Qt Core/Gui/Widgets；`docs/state.md`：QML/Quick 未立项 | 只读检索 |
| 关闭特性 | `configure_widgets.py` 显式关闭 48 项（opengl/xcb/fontconfig/network/filedialog/eglfs/linuxfb/vnc 等） | `src/ports/qt6/configure_widgets.py` |
| 依赖内嵌 | bundled freetype/harfbuzz（`INPUT_freetype=qt`、`INPUT_harfbuzz=qt`），`QT_FEATURE_xcb*=OFF`、`QT_FEATURE_fontconfig=OFF`、`QT_FEATURE_opengl*=OFF` | 构建缓存 |
| 静态产物 | `build/qt6_b1_20261031/widgets2/lib/`：7 个 `.a`，归档成员合计 **756**（Core 221、Gui 216、Widgets 172、BundledPcre2 28、BundledZLIB 15、BundledFreetype 42、BundledHarfbuzz 62）；`widgets/lib/`：10 个 `.a`，成员合计 **766**（另含 FbSupport 6、DeviceDiscoverySupport 2、ExampleIcons 2） | `x86_64-elf-ar t` 实测计数 |
| 生成 SBOM | 构建树 `qt_sbom/` 共 84 个文件（Qt 自带 SPDX SBOM 生成物，**未入任何发行包**） | 构建树只读 |
| XOS 侧源 | 补丁 10 个，触及 21 个唯一上游文件；`runtime/` 5 个事件分发/互斥文件与 `mkspecs/xos-g++` 由 `prepare_source.py` 复制进源码树 | `src/ports/qt6/` |

`prepare_source.py` 校验归档 sha256 后应用补丁 0001–0007、0009、0010；
`prepare_gui_source.py` 追加 0008；`prepare_widgets_source.py` 复用 gui 链。
两条链都不覆盖/不重写既有源码树（拒绝已存在目标）。

## 3. 适用许可判定（按仓库实际材料）

### 3.1 Qt 本体

锁定源码内实测 SPDX（`src/corelib/global/qglobal.h`）：

```
SPDX-License-Identifier: LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only
```

构建工具类文件（`src/tools/rcc/rcc.cpp`）为
`LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0`；
moc/rcc/uic 属**宿主工具**，当前打包脚本不随发行分发（0.0.2 拟发布物中无）。

判定：

| 路径 | 材料状态 | 结论 |
|---|---|---|
| Qt 商业许可 | 仓库内**无**任何商业许可证据，上游 `LICENSES/LicenseRef-Qt-Commercial.txt` 未收录 | 无材料支撑，NOT_RUN（不可声称可用） |
| LGPL-3.0-only | 全文已收录且哈希核对通过 | **静态链接下的默认可用路径**，义务见第 4 节 |
| GPL-2.0-only / GPL-3.0-only | 两份全文已收录且哈希核对通过 | 备选；一旦选用，组合作品按 GPL 全套义务 |
| `Qt-GPL-exception-1.0` | 未收录 | 仅影响工具分发；本版不分发工具 → 当前不触发，分发工具前须补 |

### 3.2 内嵌/依赖组件（`licenses/components.json` Qt 条目原文）

| 条目 | 版本 | 登记许可 | 分发状态（登记原文） |
|---|---|---|---|
| QtBase preflight | 6.8.3 | per-file Qt and bundled component terms; **member audit NOT_RUN** | `experimental host tools and target compilation only; not distributed` |
| QtGui E16 raster dependencies | QtBase 6.8.3; FreeType 2.13.3; HarfBuzz 10.4.0; DejaVu 2.37; MD4C 0.5.2 | per-file Qt terms; FTL OR GPL-2.0-only; MIT; Bitstream-Vera; X11 AND HPND; BSD-2-Clause AND Imlib2; BSD-3-Clause | 无发行声明字段（材料随 `notices` 列表） |
| Qt Widgets E17 and Xylophone Aurora Glass | QtBase 6.8.3 | Qt per-file LGPL-3.0/GPL/commercial terms; XOS theme/editor Apache-2.0 | `NOT_RUN: complete static source/relink materials, member-level license and binary distribution review; no new Release` |

### 3.3 材料核验（本任务实际执行）

- Qt 条目 `artifact_sha256` 覆盖的文件：**29 份**（顶层 11 + `licenses/gui/` 18），
  实测 **29/29 一致，0 缺失，0 不匹配**；其中 3 条通知（LGPLv3、GPLv3、aurora provenance）
  在 E17 条目只列路径不重复记哈希，其哈希由 QtBase 条目/来源登记覆盖。
- 上游 qtbase `LICENSES/` 目录共 **37 份**文本；与仓库收录同名同文者 5 份
  （GPL-2.0-only、GPL-3.0-only、LGPL-3.0-only、
  `LicenseRef-BSD-3-Clause-with-PCRE2-Binary-Like-Packages-Exception`、Zlib）；
  其余 24 份为仓库侧按组件另收（double-conversion、PCRE2×2、SHA3×2、FreeType×6、
  HarfBuzz、MD4C、DejaVu、X11/XCONSORTIUM、QIMAGETRANSFORM、AGLFN 等）。
- **与静态分发直接相关但未收录**：`LicenseRef-Qt-Commercial.txt`（商业选项全文）、
  `Qt-GPL-exception-1.0.txt`（工具例外）。是否还需上游其余文本，取决于逐成员映射 → NOT_RUN。
- 本地修改记录：10 个补丁 + `docs/licensing.md` 末节 + `aurora/README.md`；
  但补丁 hunk 内**0 处**显著修改标注（无 SPDX/Copyright 修改行），
  见第 4 节义务 6 的缺口。

## 4. 静态链接的分发义务（按仓库内许可原文，逐条对照）

依据文件：`src/ports/qt6/licenses/LGPL-3.0-only.txt`、`GPL-3.0-only.txt`、`GPL-2.0-only.txt`。

1. **LGPL-3.0-only §4a**：每份组合作品副本须显著声明"其中使用了该库且受本许可证约束"。
2. **§4b**：随组合作品附 GNU GPL（v3）与本 LGPLv3 文本两份。
3. **§4c**：若组合作品执行时显示版权声明，须把库的版权声明与"到两份文本的指引"包含进去。
4. **§4d（关键，静态链接专用）**：
   - XOS 仅支持静态链接，**§4d1（共享库机制）不可用**，必须走 **§4d0**：
     提供 **Minimal Corresponding Source**（库的对应源码，含 XOS 修改）
     与 **Corresponding Application Code**，其形式须**适合且允许用户把应用与库的修改版
     重新组合/重链接**，按 GPLv3 §6 规定的方式交付；
   - §4e：仅在 GPLv3 §6 要求的范围内提供 Installation Information。
5. **GPLv3 §6 的交付方式**（对象码形态的可选路径）：a) 随介质附对应源码；
   b) 三年有效书面要约；c) 偶发非商业地随附书面要约；d) 指定地点提供源码访问；
   e) P2P 传输并告知源码位置。**任选其一即可，但必须真实存在。**
6. **修改标注：GPLv3 §5(a)(b)**（LGPLv3 以 GPLv3 为底层条款，见其对 GNU GPL 的
   引用与 §1 例外）：修改过的文件须**显著标注被改动与日期**，且须保持全部许可/无担保
   声明完好；**LGPL-3.0-only §2** 另规定：若修改使设施引用应用提供的函数/数据，
   须按 §2a 在应用缺位时仍保持设施可用，否则整份按 GPL 传播。
7. **GPLv3 §7 / LGPL-3.0-only §4 前言**：**不得附加任何限制性条款**
   （禁止逆向工程、禁止再分发、附加专利诉讼条款等都算限制）。
8. 若改走 **GPL-2.0-only** 路径：§3 要求对应源码（按许可证提供源码形态），
   且整个组合作品按 GPL 分发；义务比 LGPLv3 更宽，不可只交付"库的"源码。
9. **自研部分（Aurora、editor、QPA、runtime）为 Apache-2.0**：随发行附
   `LICENSE`/`NOTICE`（`package_release.py` 的 `copy_notices()` 已实现），
   修改第三方文件的新增部分按 Apache 标注、原条款保留（`docs/licensing.md` 规定）。
10. **LGPL-3.0-only §3（头文件素材）**：若随包分发 Qt 头文件且目标码吸收了头文件素材
    （内联、模板、小宏），须显著声明库及其受本许可约束，并随附 GPL 与 LGPL 文本。
    0.0.2 不发 Qt 头 → 当前不触发；SDK 一旦加入 Qt 头即触发。

## 5. 对照 0.0.2-1103 拟发布内容逐项判定

判定口径：以 `scripts/package_release.py` 等打包脚本与 `build/sdk` 实际内容为准；
0.0.2 尚未冻结打包，故以最近冻结发行 `0.0.1-1026` 的清单做同路径实测参照。
`build/sdk` 实测：`include/`（newlib/XOS 头，无 Qt 头）、`lib/` 仅
`libc.a`、`libm.a`、`libxos.a`、`libxos_loader.a`；打包时另加 `cpp/lib/`
`libstdc++.a`、`libsupc++.a`、`libgcc.a`；`licenses/` 6 项
（`components.json`、`fatfs.txt`、`legacy_mit_files.json`、`mit_legacy.txt`、
`modern_apps/`、`newlib.txt`）+ 根 `LICENSE`/`NOTICE`/`COPYING.NEWLIB`。

| # | 拟发布项 | 判定 | 依据 |
|---|---|---|---|
| 1 | SDK 头文件含 Qt 头 | **不适用** | `build/sdk/include` 无 Qt 头；`package_release.py` 不复制 Qt include |
| 2 | SDK 静态库含 `libQt6*.a` | **不适用** | `build/sdk/lib` 与打包追加的 `cpp/lib` 均无 Qt；Qt `.a` 只存在于 `build/qt6_b1_20261031/` 本地构建树 |
| 3 | 系统镜像/work disk 含 Qt ELF | **不适用** | `scripts/build.py` 无 Qt 载荷；`0.0.1-1026` 冻结 `release_manifest.json` 1778 项 guest 文件中 qt/aurora/moc/rcc 命中 **0**（同路径 0.0.2 待冻结后复核，NOT_RUN） |
| 4 | `licenses/` 材料随包 | **机制已覆盖；0.0.2 实装核验 NOT_RUN** | `copy_notices()` 会把 `components.json` 全部 `notices`（含 Qt 许可文本 29 份与 aurora provenance.json）复制进发行包 `third_party_notices/`；0.0.1-1026 包内 27 份通知、qt6 命中 0（该次冻结早于 Qt 登记，不能当作 0.0.2 结果） |
| 5 | `build/sdk/licenses/`（SDK 输入内）含 Qt 文本 | **缺口（由第 4 项补位）** | 实测 6 项均非 Qt；Qt 文本仅经打包期 `third_party_notices` 路径进入，SDK 输入本身不含 |
| 6 | LGPLv3 §4d0 对应源码 + 可重链接应用代码 | **缺口 / NOT_RUN** | 仓库有源码锁、10 补丁、构建记录，但无"随发行的 Qt 对应源码包"，也无 relink 用对象/归档交付物；`package_release_sources.py` 的归档清单不含 qtbase |
| 7 | 修改显著标注与日期（GPLv3 §5(b)、LGPLv3 §2） | **缺口** | 10 个补丁触及 21 个上游文件，补丁内 0 处修改标注；仅有补丁文件名与 `docs/licensing.md` 叙述性记录 |
| 8 | §4a/§4b/§4c 二进制随附声明与双文本 | **不适用（本版）** | 无 Qt 二进制 → 不触发；若未来发 Qt ELF，`NOTICE` 现无 Qt 段落 → 届时为缺口 |
| 9 | 不得加限制性条款 | **已满足（保持）** | 现有 `release.json` notice（`original licenses retained`）、README 与文档未附加限制；发版文案不得新增 |
| 10 | 商业许可路径 | **无材料 / NOT_RUN** | 仓库内无 Qt 商业许可证据；未做任何商业合规判断 |
| 11 | 逐成员许可映射（756/766 个归档成员） | **NOT_RUN** | `components.json` 自述 `member audit NOT_RUN`；本任务未做成员→源文件映射 |
| 12 | `make license-audit` 材料检查 | **NOT_RUN（本任务未运行）** | 任务限定只读；该检查本身也只是材料完整性检查，不等于法律审查 |

## 6. 发布前检查清单（可执行；未执行项即为 NOT_RUN）

以下命令在 `${XOS_XOS_ROOT}` 下执行；路径模板：`${XOS_XOS_ROOT}`（仓库根）、
`${XOS_TOOLCHAIN}`（工具链目录）、`${XOS_TMPDIR}`（临时目录）。

- [ ] **A0（0.0.2 冻结后必做）** 确认发行清单无 Qt 载荷：
      `grep -iE 'qt|aurora|libQt' "${XOS_XOS_ROOT}/build/releases/0.0.2-1103/release_manifest.json"`
      → 应为 0 命中；命中即回到本表第 6、7 项清缺口。**NOT_RUN**
- [ ] **A1** 核 Qt 许可材料哈希（29 份）：对 `licenses/components.json` 中 3 条 Qt 条目
      的 `artifact_sha256` 逐项重算比对 → 本任务已跑：29/29 一致。**DONE（2026-11-03）**
- [ ] **A2** 核源包锁定：`shasum -a 256 "${XOS_XOS_ROOT}/.cache/xos_seed/qt6/qtbase-everywhere-src-6.8.3.tar.xz"`
      应等于 `src/ports/qt6/source_lock.json` 的 `sha256` → 本任务已跑：一致。**DONE**
- [ ] **A3** 运行材料完整性审计：`make license-audit`（在 `${XOS_XOS_ROOT}`）。
      结果只记为材料检查，不改写本报告结论。**NOT_RUN**
- [ ] **B1（仅当决定分发 Qt 二进制时）** 选定许可路径并写入发行 manifest：
      LGPLv3（推荐路径）或 GPL 全套；商业路径须先补商业许可证据，否则禁用。**NOT_RUN**
- [ ] **B2** 生成 Qt 对应源码包：锁定归档 + `src/ports/qt6/patches/` 10 补丁 +
      `runtime/`、`mkspecs/`、配置命令与构建记录，输出到发行 `sources/`，
      并在 manifest 中逐文件记 sha256。**NOT_RUN**
- [ ] **B3** 生成可重链接交付物（LGPLv3 §4d0）：为每个随包 Qt 静态库提供
      对象码/归档 + 重链接说明（编译器、flags、归档顺序参照
      `src/ports/qt6/build_widgets_fixture.py` 的实际命令），或按 GPLv3 §6 任一
      方式提供对应源码访问。**NOT_RUN**
- [ ] **B4** 给 21 个被修改的上游文件补显著修改标注与日期（GPLv3 §5(b)、LGPLv3 §2），
      或在对应源码包内提供等价的逐文件修改清单。**NOT_RUN**
- [ ] **B5** 若分发 Qt ELF：在 `NOTICE` 增加 Qt 段落（库、版本、所选许可、
      到 LGPLv3/GPLv3 文本与对应源码的指引），并核 `copy_notices()` 输出包含
      29 份 Qt 文本。**NOT_RUN**
- [ ] **B6** 若分发宿主工具（moc/rcc/uic）：补收录 `Qt-GPL-exception-1.0.txt`
      与 `LicenseRef-Qt-Commercial.txt`，并单独登记工具许可。**NOT_RUN（当前不分发）**
- [ ] **C1** 逐成员许可映射：对实际随包的每个 `.a` 做成员→源文件→SPDX 映射
      （widgets 树 766 成员 / widgets2 树 756 成员），产出映射表并登记未映射项。**NOT_RUN**
- [ ] **C2** 分发文案复核：确认无附加限制条款（GPLv3 §7 / LGPLv3 §4 前言），
      且不把"材料检查通过"写成"法律审查完成"。**NOT_RUN**

## 7. NOT_RUN 明细（诚实清单）

1. 逐成员许可映射（Qt 静态归档 756/766 成员）——NOT_RUN。
2. LGPLv3 §4d0 对应源码 + 可重链接对象打包——NOT_RUN。
3. 修改显著标注（GPLv3 §5(b)，补丁内 0 处）——NOT_RUN。
4. 0.0.2-1103 实际打包后的通知/清单核验（第 5 节第 3、4 项）——NOT_RUN（版本未冻结打包）。
5. `make license-audit` 材料检查——NOT_RUN（本任务限定只读）。
6. Qt 商业许可核验——NOT_RUN（无材料，未做任何判断）。
7. Qt 相关安全审查——NOT_RUN（不在本任务范围，`docs/licensing.md` 末节仍列未完成）。
8. 上游 37 份许可文本与实际链接成员的完整对应——未映射，NOT_RUN。

## 8. 关键数字

| 指标 | 值 |
|---|---|
| components.json 中 Qt 相关条目 | 3 |
| 已收录 Qt 许可/声明文件 | 29（顶层 11 + gui 树 18），哈希核验 29/29 一致 |
| 上游 qtbase `LICENSES/` 文本 | 37（同名收录 5；未收录含商业与工具例外 2） |
| Qt 适用许可选项 | 4（LGPL-3.0-only / GPL-2.0-only / GPL-3.0-only / 商业[无材料]） |
| XOS 侧补丁 | 10 个，触及 21 个上游文件，补丁内显著修改标注 0 处 |
| 静态归档成员 | widgets 树 10 个 `.a` / 766 成员；widgets2 树 7 个 `.a` / 756 成员 |
| 关闭的配置特性 | 48 |
| 构建树 SBOM 文件 | 84（未入发行包） |
| 0.0.1-1026 冻结 guest 文件 | 1778，Qt/Aurora/moc/rcc 命中 0 |
| 0.0.1-1026 包内 `third_party_notices` | 27，qt6 命中 0（早于 Qt 登记） |
| 本报告判定"缺口"项 | 3（第 5 节第 5、6、7 项） |
| 本报告 NOT_RUN 项 | 8 |

## 9. 边界与后续

- 本报告只写 `docs/reports/qt_static_distribution_20261103/`；未修改
  `docs/licensing.md`、`scripts/license_audit.py`、`licenses/components.json`
  及任何其它文件，登记更新留给汇总者。
- 本报告不改变任何既有资格结论：Qt 线仍是"受限客体功能通过、静态分发 NOT_RUN"；
  D7 的 QML/Quick 仍为未立项功能线。
- 结论一句话：**静态分发审查未完成；0.0.2 按当前打包路径不含 Qt 二进制故义务不触发，
  但"可随包分发 Qt 静态库"的资格尚不具备，缺口与 NOT_RUN 见第 5、6、7 节。**
