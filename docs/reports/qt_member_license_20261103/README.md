# Qt 静态归档逐成员 → 源码 → 声明类别映射（闭 NOT_RUN ① 与 ⑧）

2026-11-03。本目录只含本叶产物：`README.md`、`findings.json`、`manifest.json`
（平铺根清单，按 [evidence_integrity](../../contracts/evidence_integrity.md) 契约）。
本叶只写 `scripts/qt_member_license_map.py` 与本目录；未运行构建、未运行
`scripts/build.py`、未做任何 git 操作，`build/` 与 `.cache/` 全程只读。

闭合 [Qt 静态分发审查](../qt_static_distribution_20261103/) 第 7 节的
**NOT_RUN ①（逐成员映射）** 与 **NOT_RUN ⑧（上游 37 份文本 ↔ 实际链接成员）**。
另见 [newlib 映射](../newlib_member_license_20261103/)、
[GCC 运行库映射](../gcc_runtime_member_license_20261103/)。

**性质与边界（必须先读）**：

- 这是**归档成员 → 源文件 → 文件头声明类别**的映射，以及**上游 37 份许可文本 ↔
  实际链接成员**的对应，**不是法律意见**，**不授予任何发行资格**。它不改变被闭合
  报告的任何结论。
- 该报告 §4/§5 的 **LGPL-3.0-only §4d0 对应源码 + 可重链接交付物、修改显著标注、
  0.0.2 实际打包核验、`make license-audit`、Qt 安全审查**仍为 NOT_RUN，本叶不关闭。
- **商业授权**：仓库内无任何 Qt 商业许可证据，本叶对商业路径的一切判定为
  **N/A（无材料，未做判断）**。`LicenseRef-Qt-Commercial` 只作为"源文件声明中出现的
  一个选项"被记录，**不代表可商用**。
- 若某树因构建产物清理而无法完全解析，本叶交付真实解析率 + 未解析清单 + 根因，
  标 NOT_RUN，**不伪造**。本次两棵树均**未**触发该情形（第 3 节）。
- 声明类别是**声明提取**，不是逐成员法律结论；`no_declaration` 不因此取得任何
  许可归属。

## 1. 方法

### 1.1 成员枚举

直接解析 GNU `!<arch>` 头（`read_archive`），处理 `//` 长名表与 `/十进制` 索引，
剔除 `/` 符号表与 `//` 名字表两个非成员条目，成员名去掉尾部 `/`（Qt 的 `ar` 写出
`qwidget.cpp.o/` 这种带尾斜杠的短名）。两棵树共 **17** 个 `.a`。

### 1.2 四级解析（实测计数见第 3 节）

| 层级 | 标签 | 依据 | 性质 |
|---|---|---|---|
| 1a | `d_record` | 保留的 AUTOMOC `.d` 依赖记录，其 target 等于该成员源文件名 | 一手（依赖记录） |
| 1b | `object_record` | 构建树保留了**被归档的同一个对象**，其 `CMakeFiles/<Target>.dir/...` 路径镜像源码目录（`__` 归一为 `..`） | 一手（字节一致性） |
| 2 | `same_name_source` / `ambiguous_stem` | 锁定源码树中同名文件；多于 1 个即报歧义，**不猜** | 推导（回退） |
| 3 | `symbol_lookup` / `ambiguous_symbol` / `unresolved_symbols` | `x86_64-elf-nm --defined-only` → `c++filt` → 源码树子串搜索；多命中报歧义，**不猜** | 推导（回退） |

按 [archive_member_provenance](../../contracts/archive_member_provenance.md) 第 3 条，
"对象与归档的字节一致性"属于**一手记录**，"同名文件/符号反查"属于**推导**。本叶的
主力层是 1b（一手），2/3 层仅作回退并可运行复核。

**为什么 1b 是主力**：实测 **1522/1522** 个归档成员都能在对应构建树里找到**字节完全
一致**的保留对象（`byte_identical_object=true`，逐字节 `==` 比较），源路径是从
"实际被编译的那一个对象"读出来的，不是名字推断。

**1a 为什么记 0**：本构建树的 **936 个 `.d` 文件全部位于 `*_autogen/`**，target 只有
`moc_*.cpp` 与 `*.moc`，而归档成员里**没有任何** `moc_*` 成员（AUTOMOC 输出被合并进
`mocs_compilation.cpp.o`）。`.d` 记录与归档成员名交集为空，该层如实记 0，不改口径。

**回退层可运行、不是摆设**：`--no-object-record` 关掉 1b 重跑，2/3 层接管并给出
`same_name_source=1478`、`symbol_lookup=2`、`ambiguous_stem=24`、`ambiguous_symbol=3`、
`unresolved_symbols=15`（resolved 1480/1522）。这既证明回退层确实会**如实报歧义而非
猜测**，也说明"仅靠名字/符号"不够——正是本契约第 3 条要求登记一手记录的原因。

### 1.3 生成输入

`mocs_compilation.cpp`（AUTOMOC 聚合）与 `qrc_*.cpp`（RCC）在源码树中不存在，
解析到构建树内生成文件路径并标 `generated=true`（**20** 个成员）。它们**不参与**
声明类别与许可文本对应统计（生成文件本身无声明头），单列，不冒充源码映射。

### 1.4 声明类别

规则照搬 `scripts/gcc_runtime_member_license_map.py` 的顺序与正则，把不适用于 Qt 的
`gcc_runtime_exception` 换成 Qt 分支首条 `commercial_reference`（源文件 SPDX 行含
`LicenseRef-Qt-Commercial`），其余保持 `spdx → lgpl → gpl → bsd_like → mit_like →
other_copyright`，兜底 `no_declaration`。全文扫描（不只扫文件头），记录命中的声明
原文与完整 SPDX 表达式。

### 1.5 源码树选择（实测）

`CMakeCache.txt` 的 `CMAKE_HOME_DIRECTORY` 与 `.d` 记录都指向
`.cache/xos_seed/qt6/qtbase-6.8.3-gui`（widgets 树 300 个 `.d`、widgets2 树 292 个
`.d` 全部引用它；`host` 树的 344 个引用 `qtbase-6.8.3`，host 不在本叶范围）。
同目录另有 `qtbase-6.8.3`（与 -gui 差 5 个文件）与 `qtbase-6.8.3-b1`（差 2 个），
三者 `LICENSES/` 均为 37 份。本叶用 `-gui` 解析与提取声明。

## 2. 命令

```sh
cd "${XOS_XOS_ROOT}"
python3 scripts/qt_member_license_map.py \
  --out docs/reports/qt_member_license_20261103/findings.json
# 回退层复核（只打印计数，不写报告）
python3 scripts/qt_member_license_map.py --no-object-record
python3 tests/report_manifest_check.py     # 本目录应出现在 compliant 列表
```

`findings.json` 为确定性输出（`json.dumps(..., sort_keys=True)`）；连续两次运行与
落盘文件 sha256 一致。

## 3. 解析结果（实测）

| 树 | `.a` | 成员 | 解析 | 未映射 | 歧义 |
|---|---|---|---|---|---|
| `build/qt6_b1_20261031/widgets` | 10 | **766** | 766（100%） | 0 | 0 |
| `build/qt6_b1_20261031/widgets2` | 7 | **756** | 756（100%） | 0 | 0 |
| **合计** | **17** | **1522** | **1522（100%）** | **0** | **0** |

**各层级计数**：`object_record=1522`、`d_record=0`、`same_name_source=0`、
`symbol_lookup=0`（回退计数见 1.2）。
**字节一致对象 = 1522/1522**；**唯一源文件 = 774**；**生成输入成员 = 20**。
**未映射清单：空。歧义清单：空。**

逐归档：

| 归档 | 成员 | 解析 | 生成 | 声明类别分布 |
|---|---|---|---|---|
| `widgets/libQt6BundledFreetype.a` | 42 | 42 | 0 | other_copyright=42 |
| `widgets/libQt6BundledHarfbuzz.a` | 62 | 62 | 0 | other_copyright=58 / no_declaration=4 |
| `widgets/libQt6BundledPcre2.a` | 28 | 28 | 0 | bsd_like=27 / no_declaration=1 |
| `widgets/libQt6BundledZLIB.a` | 15 | 15 | 0 | other_copyright=15 |
| `widgets/libQt6Core.a` | 221 | 221 | 1 | commercial_reference=210 / bsd_like=8 / spdx=2 / no_declaration=1 |
| `widgets/libQt6DeviceDiscoverySupport.a` | 2 | 2 | 1 | commercial_reference=1 / no_declaration=1 |
| `widgets/libQt6ExampleIcons.a` | 2 | 2 | 2 | no_declaration=2 |
| `widgets/libQt6FbSupport.a` | 6 | 6 | 1 | commercial_reference=5 / no_declaration=1 |
| `widgets/libQt6Gui.a` | 216 | 216 | 2 | commercial_reference=211 / spdx=2 / other_copyright=1 / no_declaration=2 |
| `widgets/libQt6Widgets.a` | 172 | 172 | 5 | commercial_reference=167 / no_declaration=5 |
| `widgets2/libQt6BundledFreetype.a` | 42 | 42 | 0 | other_copyright=42 |
| `widgets2/libQt6BundledHarfbuzz.a` | 62 | 62 | 0 | other_copyright=58 / no_declaration=4 |
| `widgets2/libQt6BundledPcre2.a` | 28 | 28 | 0 | bsd_like=27 / no_declaration=1 |
| `widgets2/libQt6BundledZLIB.a` | 15 | 15 | 0 | other_copyright=15 |
| `widgets2/libQt6Core.a` | 221 | 221 | 1 | commercial_reference=210 / bsd_like=8 / spdx=2 / no_declaration=1 |
| `widgets2/libQt6Gui.a` | 216 | 216 | 2 | commercial_reference=211 / spdx=2 / other_copyright=1 / no_declaration=2 |
| `widgets2/libQt6Widgets.a` | 172 | 172 | 5 | commercial_reference=167 / no_declaration=5 |

### 3.1 声明类别分布（1522 成员）

| 类别 | 成员数 | 说明 |
|---|---|---|
| `commercial_reference` | **1182** | SPDX 首项含 `LicenseRef-Qt-Commercial`，即 `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` 这条 Qt 逐文件四选一表达式。**仅表示声明中出现该选项** |
| `other_copyright` | **232** | 仅版权行、无 SPDX：HarfBuzz 116、FreeType 84、zlib 30、md4c 2 |
| `bsd_like` | **70** | 含 "Redistribution and use in source and binary forms"：PCRE2 54 + double-conversion 16 |
| `no_declaration` | **30** | **20** 是生成输入，**10** 是真实源文件无声明头（3.2） |
| `spdx` | **8** | 有 SPDX 但不含商业项：`Apache-2.0` 4、`BSD-2-Clause AND Imlib2` 2、`FTL OR GPL-2.0-only` 2 |
| `lgpl` / `gpl` | **0** | 被更靠前的 `commercial_reference`/`spdx` 吸收；LGPL/GPL 的存在由下表独立佐证 |

**SPDX 表达式分布**（独立于规则顺序，直接取自源文件）：

| 表达式 | 成员数 |
|---|---|
| `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | 1182 |
| `Apache-2.0` | 4 |
| `BSD-2-Clause AND Imlib2` | 2 |
| `FTL OR GPL-2.0-only` | 2 |

即 **1182 个成员（77.7%）的源文件声明里同时出现 LGPL-3.0-only 与两条 GPL**，与被
闭合报告第 3.1 节的四选一判定一致。

### 3.2 `no_declaration` 的 10 个真实源文件（逐个列出，不猜）

`src/3rdparty/harfbuzz-ng/hb-dummy.cc`、
`src/3rdparty/harfbuzz-ng/src/OT/Var/VARC/VARC.cc`、
`src/3rdparty/harfbuzz-ng/src/hb-ot-shaper-indic-table.cc`、
`src/3rdparty/harfbuzz-ng/src/hb-ot-shaper-vowel-constraints.cc`、
`src/3rdparty/pcre2/src/pcre2_chartables.c`
（各在两棵树出现，共 10 个成员）。

这 5 个文件本身无版权/许可行，但**所属组件**在 `qt_attribution.json` 中登记了许可
（HarfBuzz=MIT、PCRE2=PCRE2 例外条款），故组件级对应仍成立（第 4 节）。
**这不等于"这些文件无许可"**，只是"文件头无可提取的声明"。

## 4. 上游 37 份许可文本 ↔ 实际链接成员（NOT_RUN ⑧ 的答案）

三种信号，作用域不同，`findings.json` 逐份记录计数与示例源文件：

1. **`matched_by_spdx_expression`**（文件级）：成员源文件自己的
   `SPDX-License-Identifier:` 行含该 id。
2. **`matched_by_declaration_header`**（文件级）：源文件声明窗口内（前 64 行中含
   copyright/licence/SPDX/redistribution 等关键词的行）以整词出现该 id。
3. **`matched_by_component_attribution`**（组件级）：成员来自
   `src/3rdparty/<name>/`，其 `qt_attribution.json` 的**主** `LicenseId` 即该 id。
   只取"Id 与目录同名"的那一条（或唯一一条），因此 FreeType 自带的 zlib/BDF/PCF
   子件、PCRE2 自带的 sljit **不会**被记到全组件头上；完整候选集另记于
   `component_license_candidates`。

> **诚实记录（试错）**：曾实现第四种信号"把许可文本切成词窗口在源文件里搜"，它把
> **HPND 匹配到 HarfBuzz**、把 **BSD-4-Clause 匹配到 double-conversion**（BSD 开头句
> 各文本雷同），属误报，已整体移除，未用于下表。本目录上一版 README 记的
> **9/37 含 HPND** 即该误报，本版更正为 **12/37**。

### 4.1 对应上的 12 / 37

| 上游文本 | 链接成员源文件数 | expr | hdr | attr | 主要来源 |
|---|---|---|---|---|---|
| `GPL-2.0-only.txt` | 637 | 595 | 0 | 42 | Qt 逐文件 + FreeType（`FTL OR GPL-2.0-only`） |
| `LicenseRef-Qt-Commercial.txt` | 594 | 594 | 0 | 0 | Qt 逐文件四选一 |
| `LGPL-3.0-only.txt` | 594 | 594 | 0 | 0 | 同上 |
| `GPL-3.0-only.txt` | 594 | 594 | 0 | 0 | 同上 |
| `MIT.txt` | 63 | 0 | 0 | 63 | HarfBuzz 62 + md4c 1 |
| `FTL.txt` | 43 | 1 | 0 | 42 | FreeType 42 + `qgrayraster.c` |
| `LicenseRef-BSD-3-Clause-with-PCRE2-Binary-Like-Packages-Exception.txt` | 28 | 0 | 0 | 28 | PCRE2 全部 28 成员 |
| `BSD-3-Clause.txt` | 8 | 0 | 0 | 8 | double-conversion |
| `Zlib.txt` | 15 | 0 | 0 | 15 | bundled zlib 全部 15 成员 |
| `Apache-2.0.txt` | 2 | 2 | 0 | 0 | XOS 侧 `qeventdispatcher_xos.cpp`、`qxos_unsupported.cpp` |
| `BSD-2-Clause.txt` | 1 | 1 | 0 | 0 | `qimagescale.cpp` |
| `Imlib2.txt` | 1 | 1 | 0 | 0 | `qimagescale.cpp`（`BSD-2-Clause AND Imlib2`） |

`LicenseRef-Qt-Commercial` 经 SPDX 表达式命中，**不代表取得商业授权**（边界见文首）。

### 4.2 未对应上的 25 / 37（如实列出）

`AFL-2.1`、`BSD-4-Clause`、`BSL-1.0`、`Bitstream-Vera`、`CC0-1.0`、
`GFDL-1.3-no-invariants-only`、`GPL-2.0-or-later`、`HPND`、`IJG`、`IPL-1.0`、
`Libpng`、`LicenseRef-ICC-License`、`LicenseRef-Lcs-Telegraphics`、
`LicenseRef-SHA1-Public-Domain`、`Linux-syscall-note`、`MIT-Khronos-old`、
`MIT-open-group`、`MPL-2.0`、`Qt-GPL-exception-1.0`、`SPL-1.0`、`Unicode-3.0`、
`X11`、`Xerox`、`blessing`、`libpng-2.0`。

原因均为"这些文本对应的组件/文件**没有进入这 17 个归档**"，而非解析失败：

- **组件未链接**：libjpeg、libpng、sqlite(`blessing`)、sha1、wintab、icc、pixman、
  tinycbor、md4/md5/siphash/rfc6234 等 Qt 可选 3rdparty 在本配置下不参与这两棵树
  （`configure_widgets.py` 关闭 48 项特性），故 `IJG`/`Libpng`/`libpng-2.0`/`blessing`/
  `LicenseRef-SHA1-Public-Domain`/`LicenseRef-Lcs-Telegraphics`/`LicenseRef-ICC-License`/
  `CC0-1.0`/`SPL-1.0`/`MPL-2.0`/`AFL-2.1` 无对应成员。
- **属于文档/工具/字体，不在 target 归档内**：`GFDL-1.3-no-invariants-only`（文档）、
  `Qt-GPL-exception-1.0`（moc/rcc/uic 宿主工具例外；本叶范围是 target 归档，工具不在
  其中，且该文本已补入 `src/ports/qt6/licenses/`）、`Bitstream-Vera`（DejaVu 字体数据
  未链入）、`X11`/`HPND`/`Xerox`（xcb 等 X11 平台代码已关闭）。
- **文本存在但本配置未取用**：`BSD-4-Clause`、`BSL-1.0`、`GPL-2.0-or-later`、`IPL-1.0`、
  `Linux-syscall-note`、`MIT-Khronos-old`、`MIT-open-group`、`Unicode-3.0` 在源码树里
  有声明，但对应文件不在这 17 个归档的 774 个源文件内。

**"文本被收录" ≠ "有成员链接它"**：`Qt-GPL-exception-1.0` 与 `LicenseRef-Qt-Commercial`
的文本已在 `src/ports/qt6/licenses/`，前者是材料完整性，后者才是本叶回答的问题，表中
分开陈述。

## 5. 与既有登记的关系（留给汇总者，本叶未改登记文件）

- **已闭**：被闭合报告 §7 的 **NOT_RUN ①**（1522/1522、0 未映射、0 歧义）与
  **NOT_RUN ⑧**（37 份文本 12 对应 / 25 未对应 + 逐条原因）。
- **登记处待更新**（本叶无权写 `licenses/open_items.json`，如实报出）：
  - `qt_license_text_member_coverage` 记的"9 命中、28 未命中"已被本叶更正为
    **12 命中 / 25 未命中**（移除 HPND 误报、补入组件级归因）；其"262 个仅版权/
    无声明成员未逐一枚举"的缺口仍在，退出条件不变。
  - [archive_member_provenance](../../contracts/archive_member_provenance.md) 老人老办法
    表中 Qt 一行记 **1480/1522**，那是 `--no-object-record` 回退口径；按该契约第 3 条
    "字节一致性属一手记录"，本叶主力层已达 **1522/1522 且字节一致**，该行可据此更新，
    但本叶不改契约文件。
- **仍未闭**（该报告 §7 的 ②③④⑤⑥⑦）：§4d0 对应源码与可重链接交付物、修改显著标注、
  0.0.2 实际打包核验、`make license-audit`、Qt 商业核验（N/A）、Qt 安全审查。
  本叶也不改变"0.0.2 不含 Qt 二进制故义务不触发"的判定。
- 本叶未修改 `docs/licensing.md`、`scripts/license_audit.py`、`licenses/components.json`
  及任何登记文件。

## 6. 局限

1. **不是法律意见**，不授予发行资格（见文首边界）。
2. **组件级信号是组件级的**：`qt_attribution.json` 主 `LicenseId` 归因到组件全体成员，
   未做文件级再细分（FreeType 内 zlib/BDF/PCF 子许可只作候选记录）。
3. **声明提取是文本匹配**：类别取决于规则顺序，`commercial_reference` 排最前会吸收
   本可归入 `lgpl`/`gpl` 的成员；权威分布请看 3.1 的 SPDX 表达式表。
4. **生成输入无声明**：20 个 AUTOMOC/RCC 成员不参与声明与许可统计，其许可取决于被
   moc 的头文件与被打包的资源，本叶未逐个展开。
5. **依赖本地构建产物**：`build/` 不入库，换机复算需重建 Qt 或保留同样命名的对象与
   `.d`；若构建树被清理，1b 层退化到 2/3 层，届时解析率下降并按文首边界如实标
   NOT_RUN（本次未发生）。
6. **未做字节级溯源到发行物**：本叶证明"归档成员 == 构建树保留对象"，未证明发行包里的
   `.a` 与这两棵树相同（0.0.2 当前不含 Qt）。
7. **25 份未对应文本不是"不需要"**：它们对应未链接的组件；一旦启用相应特性或分发宿主
   工具，必须重跑本脚本并重新登记。

## 7. 关键数字速查

| 指标 | 值 |
|---|---|
| 归档树 / `.a` | 2 棵 / 17 个 |
| 归档成员 | **1522**（widgets 766 + widgets2 756） |
| 解析 / 未映射 / 歧义 | **1522 / 0 / 0（100%）** |
| 主力层级 | `object_record` 1522（一手：字节一致） |
| 字节一致的保留对象 | 1522 |
| 唯一源文件 | 774 |
| 生成输入成员 | 20 |
| 声明类别 | commercial_reference 1182 / other_copyright 232 / bsd_like 70 / no_declaration 30 / spdx 8 |
| SPDX 表达式（Qt 四选一） | 1182（77.7%） |
| 上游 `LICENSES/` 文本 | 37（对应 **12** / 未对应 **25**） |
| 回退层（`--no-object-record`） | resolved 1480、ambiguous_stem 24、ambiguous_symbol 3、unresolved_symbols 15 |
| 构建树 `.d` 文件 | 936（全在 `*_autogen`，与归档成员名交集 0） |
| 商业许可判定 | **N/A（无材料）** |
| 未运行 | 打包核验、安全审查、商业核验（N/A）、法律意见 |
