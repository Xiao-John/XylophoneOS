# 许可证管理

2026-10-24 起，自研新代码采用 Apache License 2.0，SPDX 标识为 `Apache-2.0`。
用户口述的 APL-2.0 按此名称落实。根目录 LICENSE 保存标准全文，NOTICE 说明范围。
历史 MIT 授权不撤销：原文本保留在 licenses/mit_legacy.txt，历史文件及基线提交
记录在 licenses/legacy_mit_files.json。混合文件的旧内容保留 MIT，新贡献使用 Apache；
相应文件标为 `MIT AND Apache-2.0`，并随分发携带两份文本及归属说明。
第三方目录及独立 localpilot 项目不受这次自研许可证变更覆盖。

## 当前组件清单

机器可读入口是 licenses/components.json，记录来源、固定版本、用途、声明位置与缺项。

| 组件 | 当前用途 | 管理方式 |
|---|---|---|
| 自研 XOS/SDK/工具/测试 | 系统、SDK 和宿主工具 | Apache-2.0 新贡献；保留历史 MIT 基线 |
| FatFs R0.16 w/patch 2 | files 服务、显式离线安装器 | 原作者 ChaN 的原许可；保留源文件声明及 licenses/fatfs.txt；记录本地修改 |
| newlib 4.6.0.20260123 | SDK 头、libc.a/libm.a、libc_hello | 多来源、逐组件条款；保留 COPYING.NEWLIB 和头文件内声明，不能统一标成 LGPL 或 Apache |
| ncurses 6.5 | 宽字符终端库及 SDK 候选，受限客体探针 | 固定原包摘要并保留 COPYING；逐成员与静态分发审查未完成，不授予发行资格 |
| QtBase 6.8.3、PCRE2、zlib、double-conversion、SHA3 | 受限 QtCore 功能验收 | 来源锁定与许可材料见 `src/ports/qt6`；逐成员、静态重链接与分发审查尚未完成 |
| GCC/Binutils/NASM/QEMU | 构建/测试工具；GCC/Binutils Seed 另随工作盘 | NASM/QEMU 仅宿主、不随发行；GCC/Binutils Seed 与 GCC 运行库**已随 0.0.1-1024/1026 发行**（工作盘/SDK），GPL/LGPL/例外与对应源码材料登记见[分发审查](reports/gnu_seed_distribution_20261103/) |
| GNU Binutils Seed 2.47 | 已在 XOS 验收的静态工具 | 原 GNU 条款；src/ports/binutils 保留源包锁定哈希、许可、移植补丁及构建方法，实际构建清单绑定SDK和工具；已随 0.0.1-1024/1026 工作盘分发，对应源码包随发行 |
| Binutils 捆绑 zlib 1.3.1 | Seed 内部静态库 | Zlib 原许可保留，不是 XOS 自研 Apache 代码，不依赖宿主动态 zlib |
| GCC 16.2.0 C Seed、host libstdc++/libsupc++、GMP/MPFR/MPC | 本地客体工具闭包 | src/ports/gcc/upstream 与 source_lock.json 保留实际版本和声明；components.json 登记材料哈希；**公开分发审查已交付**（[O1–O10 义务清单](reports/gnu_seed_distribution_20261103/)），目标 E08-5 库逐成员追溯未完成 |
| sbase cat/cp/mkdir/mv/rm | dash B1的窄用户态工具 | 固定提交c546c3a；保留上游MIT LICENSE、源文件哈希及XOS适配文件清单；仅本地验收，未公开分发 |
| 日常工具DU1/DU2 | 13个独立候选程序 | 原五个sbase适配保留MIT，2026-10-27新修改Apache-2.0；新增八个XOS自研命令Apache-2.0，许可清单按实际包材料核对 |
| Open Adventure 1.12 | 独立用户态游戏 | 上游BSD-2-Clause声明与源码锁在src/ports/adventure；XOS自研适配为Apache-2.0；包携带SDK许可材料，逐成员审计仍未完成 |
| idna 3.20 | CPython PY3 A3离线纯Python wheel | 固定wheel与BSD-3-Clause许可哈希；本地验收，未公开分发 |
| tzdata 2026.5 | CPython PY3 B2 ZoneInfo fallback | 固定PyPI wheel与Apache-2.0全文；本地验收，未公开分发 |
| SQLite 3.54.1 | CPython PY3 B3静态模块及XOS VFS | 上游许可文本、源码锁定和移植记录保存在src/ports/cpython/sqlite；本地验收，未公开分发 |
| bzip2 1.0.8、xz/liblzma 5.8.4、zstd 1.5.7 | CPython PY3 B4静态模块 | 固定上游源码及各自许可文本，保存在src/ports/cpython/compression；本地验收，未公开分发 |

## newlib 与 LGPL

本仓库 COPYING.NEWLIB 开头明确说明：newlib 来自多个来源，单文件内的声明可能
优先适用。包含 BSD 类、其他许可声明，也包含 LGPL 条款。
其中第 21 节标为 `*-linux* targets only`，第 22 节标为 `i[3456]86-*-linux* targets only`；
当前库构建 target 是 x86_64-elf，不能据此把整个 newlib 都说成 LGPL。
同样，没有逐成员追溯就不能声称某个预构建库“已全部审计、只有某一种许可”。

本轮完成声明收集与分发清单；**libc.a/libm.a 每个成员到源文件的映射已于 2026-11-03
补齐**（1053/1053 成员、0 未映射、0 歧义，依赖三棵构建树 `.Po` 记录一致 1028/1028），
声明类别分布见
[newlib 成员许可映射](reports/newlib_member_license_20261103/)。该映射是"成员→源文件→
声明类别"的提取，**不是逐成员法律意见**；其中 323 个成员的源文件本身没有版权/许可声明，
其条款仍以 COPYING.NEWLIB 为准。目标构建的 1028 个唯一源文件中，含 LGPL/GPL 文本者为
0（独立正则复核；同一正则在整树可命中未编译端口的 11 个 LGPL 文件，证明抓取有效）——
这不改变"不能把整个 newlib 说成 LGPL"的结论。licenses/components.json 的
`newlib_archive_member_to_source_license_mapping` 缺项随之关闭；**字节级逐成员溯源仍
NOT_RUN**（SDK 归档成员与本地构建树对象字节不一致，见报告第 3 节）。后续重新构建/
升级预构建包时，应保存源码包实际哈希、配置、必要的单文件版权声明和成员来源；
不能只看项目名。

官方入口：[newlib COPYING.NEWLIB](https://sourceware.org/newlib/COPYING.NEWLIB)、
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)。
版本绑定以本仓库文件为准，官网当前文本不代替实际发布包。

## 每次引入、修改与分发

1. 引入依赖时同时记录固定版本/来源/实际哈希、原始 LICENSE/COPYING/NOTICE，
   区分运行时链接、SDK 携带和仅宿主使用。没有声明不能填“已审计”。
2. 新自研源码加 `SPDX-License-Identifier: Apache-2.0`；修改历史 MIT 文件保留
   原归属并标明新增部分/日期；修改第三方代码保留上游原条款，显式记录修改。
3. 升级依赖时比较许可文本和范围；静态链接、复制头文件、分发编译器及运行库
   各自记录，不能认为“进程隔离/静态链接/只是一个 .a”自动消除义务。
4. SDK 与发布材料必须携带 LICENSE、NOTICE、历史 MIT 和所含第三方声明。
   make build 实际复制这些材料，并在 SDK manifest 中逐文件记哈希。
5. `make license-audit` 检查登记文件/SDK 副本/新源码标识并生成清单；它是材料
   完整性检查，不是逐文件法律兼容性或预构建库全部成员的认证。
6. GNU Seed、libgcc、libstdc++ **已随 0.0.1-1024/1026 分发**（工作盘/SDK），义务清单
   O1–O10 与缺口按 [GNU Seed 分发审查](reports/gnu_seed_distribution_20261103/) 执行；
   后续每次分发按实际构建及例外收集所需源码、补丁、构建说明和许可。编译器的许可与
   它生成程序的许可分开登记。

每组交接记录许可证变化、检查结果和待办。项目仍保持轻量：一份策略、一份组件表、
实际声明文件及自动导出；不为了许可证管理建立另一个操作系统。

## GNU Seed 的当前边界

普通宿主工具与准备运行于XOS的Seed分开登记。**事实更正（2026-11-03，依据发行审查）：
Seed 已经公开分发**——0.0.1-1024 与 0.0.1-1026 的 images 工作盘携带 GCC/Binutils Seed
可执行件与 `/sysroot/lib` 下的 libgcc/libstdc++/libsupc++/libc.a/libm.a（1026 起 SDK
`cpp/lib/` 亦携带三件套），对应源码包（原包+补丁+覆盖层+构建记录）作为发行资产发布；
1026 包内另带 `third_party_notices` 27 份。`licenses/components.json` 原先把这些组件
标为 `local_only`，已随之更正。完整盘点、逐项分发判定与义务清单 O1–O10 见
[GNU Seed 分发审查](reports/gnu_seed_distribution_20261103/)。

因此分发义务**已被触发且大部分履行**，残余缺口按该报告跟踪：1024 包内无
`third_party_notices`；客体 `/usr/share/licenses/` 无 GNU 条目；根 `NOTICE` 缺 GNU
组件条目；GFDL 手册页随工具分发但未登记为组件。静态归档逐成员追溯已于 2026-11-03
交付：newlib **1053/1053**（[newlib 映射](reports/newlib_member_license_20261103/)）、
GCC 运行库 **397/407**（10 个真歧义未解析，见
[GCC 运行库映射](reports/gcc_runtime_member_license_20261103/)），均为声明提取而非法律意见。

上游原包、XOS补丁和构建脚本共同定义对应源码，工具manifest保留实际输入/输出哈希。
自研移植新增内容Apache-2.0，补丁引用的GNU上下文及修改后的上游文件保留适用GNU条款。
不能用材料检查代替逐成员核对，也不能把工具的GPL许可自动套到仅由工具生成的普通
用户程序上（此原则已写入本节与发行文案要求 O6）。

0020接收C Seed时补收GMP/MPFR/MPC实际源码内的LGPL/GPL声明，登记GCC运行库例外。
原始C Seed与修复派生Seed分别保留manifest，不覆盖历史证据。仓库内并存两份运行库
manifest（`src/ports/gcc/e08_5_target_runtime_manifest.json` 与
`.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/`，后者绑定实际分发件），引用时
不可混用，见审查报告 2.4 节。

## dash可选移植（0025）

固定dash 0.5.13.5，登记于components.json；完整上游COPYING保存于
src/ports/dash/upstream。该文本另列mksignames.c的GPL-2.0-or-later；当前no-signals
profile不构建或链接该生成器/信号表。上游逐文件条款保留，本地独立后端为Apache-2.0。
只在隔离缓存构建测试，未改已发布SDK/附件；下一次分发要随附原包、补丁、后端和
实际配置，不把“主要是BSD类”简化为整包单一声明。

## sbase窄工具集（0028）

sbase固定提交`c546c3a5724c81cee9a11d816a38ccdf17472129`及tree
`a58d176568a1b33d435a7628740b68289ea5c07a`。原始MIT文本逐字保存于
`src/ports/sbase/upstream/LICENSE`，`source_lock.json`记录上游五个对应源文件与
许可文件哈希；components.json将五个XOS适配文件显式登记为MIT，不按自研Apache
默认项误判。当前只在隔离盘验收cat/cp/mkdir/mv/rm，不含递归、符号链接、权限
保留、跨卷fallback或覆盖保证，也没有改公开发行附件。材料检查通过不替代未来
公开分发时对实际源码包、修改说明和二进制清单的复核。

## CPython PY0源码材料（0036）

CPython3.14.9原始LICENSE与Doc/license.rst从source_lock所绑定、实际SHA256
核验的源码包复制到src/ports/cpython/upstream/，components.json记录材料摘要。
公开端口源码/补丁时随附原声明；未创建新二进制发行。静态内建模块的逐成员
许可映射仍须按实际构建清单复核，不能将整包简化为XOS Apache许可。

0049增加zlib 1.3.2静态模块。官方tar.xz摘要与官网公布值一致，原始Zlib许可
复制到`src/ports/cpython/upstream/zlib-LICENSE`并登记；XOS补丁只在`gzguts.h`
显式引入`errno.h`，保留上游声明。PY3 stage另携带
`/usr/share/licenses/zlib/LICENSE`。本地构建/客体验收不等于发布；对应源码包与
补丁须在未来任何二进制分发时一并提供。

0049 A3 增加 idna 3.20 纯 Python wheel：官方 wheel SHA256、wheel 内 BSD-3-Clause
`LICENSE.md` SHA256与锁定文件一并登记，许可原文保存在
`src/ports/cpython/upstream/idna-LICENSE.md`，生成的 XPK 携带到
`/usr/share/licenses/python_idna/LICENSE.md`。本地 guest gate 不代表公开发布；未来
二进制分发还须提供匹配 wheel/源码材料。

## CPython PY3 B2–B4（0058）

B2固定tzdata 2026.5 wheel并随本地stage携带Apache-2.0声明；RTC墙钟及POSIX时区规则
属于XOS系统实现。B3固定SQLite 3.54.1，保留上游许可、源码与补丁材料；XOS VFS及适配
补丁不改变SQLite原许可。B4固定bzip2 1.0.8、xz/liblzma 5.8.4和zstd 1.5.7，各自保留
上游许可材料。源包、补丁、wheel及构建记录均在本地端口目录或锁文件中。

这些组件目前只用于本地隔离stage和客体验收，没有公开发行。若随二进制发布，须提供
对应源码/补丁、声明文本和实际构建清单；本地`license_audit.py`检查登记及材料哈希，
不替代逐成员法律审查或发布包复核。

## sbase Make C3

固定sbase c546c3a的make五个C文件、make.h与根MIT LICENSE原样保存在
src/ports/make/upstream，source_lock.json与components.json逐文件记SHA256。
补丁保留原MIT适用条款，独立XOS backend/build/test为Apache-2.0。实际产物
manifest保存源码/补丁/SDK/工具摘要；没有创建或替换正式Release附件，材料检查
不扩大成运行库逐成员法律审计。SDK/本机交付材料附对应声明及原始来源。

E16 新增 QtGui、FreeType 2.13.3、HarfBuzz 10.4.0、DejaVu 2.37、MD4C 0.5.2 及
Qt raster/region 的上游声明，原文与来源路径保留在 `src/ports/qt6/licenses/gui`，哈希在
`licenses/components.json`。原版 DejaVuSans.ttf 从锁定 QtBase archive 提取并嵌入资源。
0008 还补入 HarfBuzz 静态符号闭包遗漏的上游 graph 源文件。功能测试、材料完整性检查
不授予静态再分发资格；逐成员许可映射、对应源码/重链接材料与补丁修改标注已于
2026-11-03 交付（见下节），**Qt 安全审查与打包后清单核验仍 NOT_RUN**。

## Qt 静态分发审查（2026-11-03）

D7 两叶之一，报告与逐项对照表见
[qt_static_distribution_20261103](reports/qt_static_distribution_20261103/)。本节只记
结论与边界，细节以报告为准。

- **材料核验**：Qt 相关组件条目 3（QtBase preflight / QtGui E16 / Qt Widgets E17+Aurora），
  已收许可文本 29 份（顶层 11 + `licenses/gui` 18），哈希 29/29 一致；源包归档 sha256
  与 `source_lock.json` 匹配。
- **适用许可（锁定源码实测 SPDX）**：`LicenseRef-Qt-Commercial OR LGPL-3.0-only OR
  GPL-2.0-only OR GPL-3.0-only`。三份全文已收录；**商业授权材料仓库无**，未作任何判断。
  上游 `LICENSES/` 共 37 份，其中与分发直接相关且本仓未收录 2 份
  （`LicenseRef-Qt-Commercial.txt`、`Qt-GPL-exception-1.0.txt`）。
- **构建事实**：`BUILD_SHARED_LIBS=OFF` 静态、`QT_QPA_PLATFORMS=xos`、关闭特性 48 项、
  源仅 qtbase、无 qml/quick；widgets 静态归档 17 个 `.a`（766 + 756 成员）。
- **对 0.0.2 的判定**：`build/sdk` 无 Qt 头/库，1026 冻结清单 Qt 命中 0，包内
  `third_party_notices` 无 qt6 条目 → **Qt 二进制不随本版分发，静态分发义务本版不触发**；
  `copy_notices()` 机制会把 29 份文本带入 0.0.2，但实际打包核验 **NOT_RUN**。
- **结论：审查已交付，发行资格未取得。** 已满足 1 项（无限制性条款）、缺口 3 项、
  不适用 3 项、**NOT_RUN 8 项**：①逐成员许可映射（766/756 成员）②LGPLv3 §4d0 对应源码与
  可重链接对象打包 ③GPLv3 §5(b)/LGPLv3 §2 修改显著标注 ④0.0.2 冻结打包后清单核验
  ⑤`make license-audit` ⑥商业许可核验 ⑦Qt 安全审查 ⑧上游 37 份文本与实际链接成员的完整
  对应。未授予"可随包分发 Qt 静态库"资格；上述任一项仍为 NOT_RUN 时不得声称完成。

## 开放项登记与归档成员来源契约（2026-11-03）

**单一开放项登记处**：`licenses/open_items.json`。许可范围内任何未闭合项必须带状态
（`open` / `deferred` / `not_applicable`）、证据、退出条件登记在此；
`scripts/license_audit.py` 从它**派生** `not_completed` 并硬校验——证据缺失、状态非法、
`open` 却无退出条件、或证据报告目录缺平铺 `manifest.json`，审计直接失败。
审计输出的未闭合项与登记处逐字一致，**不会再出现"报告里还有 NOT_RUN、审计却打印全绿"**。

**归档成员来源契约**：[archive_member_provenance](contracts/archive_member_provenance.md)。
从下一次各组件重建起，进入"已验收/拟分发"状态的静态归档必须在创建它的同一次构建里
产出 `member_manifest.json`（成员 → 源文件 sha → 声明类别，一手记录、禁用推导冒充）；
届时逐成员审计改为"读清单 + 跑校验器"，三份考古脚本合并为一个共享实现。
本契约**不追溯**既有归档：newlib 1053/1053、GCC 397/407 为**推导映射**；Qt 1522/1522
属对象字节一致的一手记录（但非契约产出的 `member_manifest.json`）。三者残余缺口均在
开放项登记处逐条挂账。

### Qt 收口补记（2026-11-03 第二轮）

上节 8 项 NOT_RUN 中本轮已闭：**①逐成员许可映射**（[qt_member_license_20261103](reports/qt_member_license_20261103/)：
1522/1522 全解、字节同一 100%、0 未映射 0 歧义）、**②§4d0 对应源码与可重链接交付物**
（`src/ports/qt6/REDISTRIBUTION.md` + `redistribution_manifest.json`）、**③补丁修改显著标注**
（`src/ports/qt6/patches/MODIFICATIONS.md`，10 补丁/21 上游文件）、**⑤license-audit**（本轮
重跑 PASS）、**⑧上游 37 份文本对应表**（12 命中/25 未命中逐份注明；上一版 9/28 含 HPND
误报，已随词窗口搜索移除而更正）；**缺口①**（SDK 输入内
无 Qt 文本）由补入 `LicenseRef-Qt-Commercial.txt` 与 `Qt-GPL-exception-1.0.txt` 关闭
（QtBase notices 11→13，`copy_notices()` 随包携带）。

仍**未闭**：④打包核验（deferred 至真正打包 Qt 时）、⑥商业核验（N/A，无材料）、
⑦安全审查（deferred，不属 D7）、以及新登记的"262 个仅版权/无声明成员的成员→文本覆盖"
（open）。全部逐条见 `licenses/open_items.json`；**发行资格仍 NOT_GRANTED**。
