# XOS 当前状态

2026-10-28。远端 main 已合入 PR #5（244ac40）与 PR #8（7a7481f）。
本地整合含 C20–C26、输入编辑、DU 设计与实现；新组合定向验收见下。
发布资产仍为 0.0.1-1026，未随本地整合更新。
原则裁决见[xos_plan.md第一部分](xos_plan.md#第一部分设计原则)，本页只登记事实与占用。

## 正在进行：ncursesw W0/W1

W0 勘查和 W1 [工作契约草案](contracts/terminal_w1.md)已开始；W0 未冻结，W1 未
实现或验收。终端 ESC、输入所有权、UART 等待与 newlib 多字节缺口见
[0074](work_log/0074_ncursesw_w1_scout.md)。本组无新 ABI 或公共 build 占用；用户要求
所有相关改动提交后再验收。

前期缺口已开始：隔离多字节 newlib 的 single/threaded 候选已构建，ncurses 配置/编译
探针复现终端头缺失；均非客体验收或新 SDK 资格。终端机制分层见工作契约，具体证据与
后续见[0075](work_log/0075_ncursesw_preliminary_gaps.md)。当前无源码/文档/build 占用。

## 本次同步与提交

全部三个已登记工作区已核对。当前工作区的 DU 设计及 PR 审查保存为 928c755；
另外两个工作区干净。PR #8 源码无文本冲突；文档冲突按本地原则/设计与远端 Qt 事实分别保留。
文档、ABI与历史来源检查通过，不改绑旧验收。详见[0072](work_log/0072_remote_sync_docs.md)。
本组无剩余文件/公共 build 占用；仅本地提交，未推送或创建 PR。

## 当前分支能力与证据

| 面 | 实际状态 | 证据入口/边界 |
|---|---|---|
| 发行 | 1026已发布，源码db5b46c/build7a4668477d7323de；smoke11/11、许可材料7份 | [不可变回执](releases/release_0_0_1_1026.json) |
| 核心/工具链 | E01–E08受限功能；原生GCC/G++开发已验，post5 P1仍partial | [E01–E07](history/e01_e07.md)、[E08](e08.md)；系统重建/自举未验 |
| 线程 | T0–T2、T3-PY与PY2专项已有证据 | [线程资格](reports/threading_20261025/qualification.json)；Qt QThread受限实测，SMP未验 |
| Shell | dash C1–C3受限通过，xsh保留默认 | [C3资格](reports/dash_c3_20261026/qualification.json)，build2f7160b7d6633ee6；无完整信号/作业控制 |
| 显示/ISO | sys65/66 在 build48e5e73bcd649f44 重验 G02 19组通过 | [当前报告](reports/qt_e15_qualified_20261028/g02_report.json)、[显示历史](history/boot_display.md)；QtGui/QPA未实现 |
| CPython | PY0–PY2/T3-PY、A1–A3、B1–B4专项通过 | [用户态摘要](history/userland.md)；B2–B4系统6251d26b611a388d，Python11c39c52e451a9499450 |
| xypm | P2原生验证、事务和启动恢复已实现；限定范围内验收通过 | [包计划](plans/packages.md)、[0066](work_log/0066_xypm_p2_validation.md)；P2验收范围和局限见记录；P3未完成 |
| 审计/整合 | A01–A04修复与PR3兼容已交付PR4 | [整合摘要](history/delivery_audit.md)，组合build76a2e4380f64fb2e，7定向组通过；非旧全量重验 |
| POSIX/Qt | PX0子集文档已有；QtCore 6.8.3 静态受限客体 G01/G03 功能通过 | [PX路线](plans/posix.md)、[Qt资格](reports/qt_e15_qualified_20261028/qualification.json)；QtGui/QPA 未开始，绝对峰值/发行许可未完成 |

每项资格只对其冻结输入成立。旧源/SDK/镜像不改绑；许可材料通过不代表逐成员审计完成。
QtCore 的系统 build48e5e73bcd649f44 和本地输入编辑的 build3200de2c3b80a9d9 分别保留资格；
该日常工具组合的输入编辑已复验，QtCore 本身未在该组合重新验收。Qt 实现入口见[QtCore](implementation/qt_core.md)。

## 本地实现与组合边界

- 输入编辑 F1/F2 的原有定向证据见[0064](work_log/0064_input_edit_first_stage.md)；
  故障与复杂终端覆盖仍待补测。
- 日常工具 DU1/DU2 的 13 个候选、XPK 及 xypm P2 已在旧组合定向验证；
  与 Qt 源码/输入编辑整合后的组合已重新构建并通过定向测试，详见[0069](work_log/0069_daily_utilities.md)。
  完整逐命令资格、实际发行与空盘 ISO 安装仍未完成。
- UTF-8 文件名及 Open Adventure 各有原分支定向证据，见
  [0068](work_log/0068_utf8_filenames.md)、[0067](work_log/0067_open_adventure_xpk.md)；
  非 ASCII 大小写折叠、完整游戏与公开分发未验。
- xypm P2 限定验收范围见[0066](work_log/0066_xypm_p2_validation.md)，P3 未完成。
  分支来源和原有本地快照见[0069](work_log/0069_all_worktree_local_commit.md)。

## 接手与下一步

- 新组合已验证 SDK/profile、xypm P2、工具、UTF-8 路径与候选安装清单；
  继续补齐逐命令边界和完整发行。ISO 通用载荷与空盘安装尚未实施。
- Qt E15 已经 PR #8 合入；E16/G04 仍需完成组合等待。完整成员许可、静态分发、
  绝对峰值及图形资格未完成。
- 输入编辑按[第一档](plans/input_edit_foundation.md)、[第二档](plans/terminal_editor.md)及
  [多语言](plans/multilingual.md)继续；先设计[ncursesw 公共底座](plans/ncursesw.md)，
  再优先评估 nano，kg 为备选。尚未实施或验收；相关改动提交后再验收。
- 67–79 内存、80–95 等待/信号、96–111 显示扩展仍仅预留，具体接口先登记。
- 按 Discipline→本页→宪法→专项契约/登记接手；新开发独立分支/PR交付，
  公共 build 排他，localpilot 隔离。
