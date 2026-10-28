# XOS 当前状态

2026-10-28。远端 main 已合入 PR #5（244ac40）与 PR #8（7a7481f）。
当前本地分支 `codex/daily_utilities_design` 整合该 main、本地 C20–C26、输入编辑与 DU 设计。
发布资产仍为 0.0.1-1026；本地新组合未重新构建或客体验收。
原则裁决见[xos_plan.md第一部分](xos_plan.md#第一部分设计原则)，本页只登记事实与占用。

## 本次同步与提交

- E16 QtGui/QPA：`codex/qt6-e16-qpa`，负责 Qt 端口、独立 Gui 配置/QPA、图形夹具及文档；私有 `build/qt_e16`，无新公共 ABI。G04 受限功能资格已完成，待上游审查；不是正式发行资格。见 [0066](work_log/0066_qt_e16_qualification.md)。

文档、ABI与历史来源检查通过，不改绑旧验收。详见[0072](work_log/0072_remote_sync_docs.md)。
本组无剩余文件/公共 build 占用；仅本地提交，未推送或创建 PR。

## 当前分支能力与证据

| 面 | 实际状态 | 证据入口/边界 |
|---|---|---|
| 发行 | 1026已发布，源码db5b46c/build7a4668477d7323de；smoke11/11、许可材料7份 | [不可变回执](releases/release_0_0_1_1026.json) |
| 核心/工具链 | E01–E08受限功能；原生GCC/G++开发已验，post5 P1仍partial | [E01–E07](history/e01_e07.md)、[E08](e08.md)；系统重建/自举未验 |
| 线程 | T0–T2、T3-PY与PY2专项已有证据 | [线程资格](reports/threading_20261025/qualification.json)；Qt QThread受限实测，SMP未验 |
| Shell | dash C1–C3受限通过，xsh保留默认 | [C3资格](reports/dash_c3_20261026/qualification.json)，build2f7160b7d6633ee6；无完整信号/作业控制 |
| 显示/ISO | sys65/66 在 buildef83c9fc92217380 重验 G02 19组通过 | [当前报告](reports/qt_e16_qualified_20261028/g02/report.json)、[显示历史](history/boot_display.md)；QtGui/QPA 单全屏 raster 已验 |
| CPython | PY0–PY2/T3-PY、A1–A3、B1–B4专项通过 | [用户态摘要](history/userland.md)；B2–B4系统6251d26b611a388d，Python11c39c52e451a9499450 |
| xypm | P0/P1/P2-1通过；P2-2只读verify/plan和ELF校验已实现/打包 | [包摘要](history/packages.md)；P2-2 guest/adversarial未验，P2-3/4与P3未开始 |
| 审计/整合 | A01–A04修复与PR3兼容已交付PR4 | [整合摘要](history/delivery_audit.md)，组合build76a2e4380f64fb2e，7定向组通过；非旧全量重验 |
| POSIX/Qt | PX0子集文档已有；QtCore 6.8.3 G01/G03 与 QtGui/QPA G04 受限客体功能通过 | [PX路线](plans/posix.md)、[E16资格](reports/qt_e16_qualified_20261028/qualification.json)；Widgets/QML/Quick 未验，绝对峰值/发行许可未完成 |

每项资格只对其冻结输入成立。旧源/SDK/镜像不改绑；许可材料通过不代表逐成员审计完成。
QtCore 的系统 build48e5e73bcd649f44 和本地输入编辑的 build3200de2c3b80a9d9 分别保留资格；
本次合并未运行二者的新组合。Qt 实现入口见[QtCore](implementation/qt_core.md)。

## 本地实现与尚未整合的分支

E15 已于 2026-10-28 获上游批准并合入 main，squash 后树与原 `d1e108d` 完全一致。
E16 已将独立提交重放到实际 `7a7481f`，上游差异不重复 E15。QtGui、QPA、客体图形/字体/
键鼠/重绘/退出与故障恢复、G02 和受影响回归见 [0066](work_log/0066_qt_e16_qualification.md)。
冻结报告保留失败、输入与实际测量；没有变更 Release。

## 接手与下一步

- 遵循Discipline→本页→宪法→专项契约/登记；需要原过程时用[来源索引](history/source_index.json)，
  无须从已合并工作日志猜当前状态。
- E16 使用可 join 的 SDK 输入线程与 QtCore wait_word 分发器，未新增多源等待 ABI。
  E17 Widgets 及 E18 QML 各按新 gate 推进；当前只验一个独占全屏窗口。
  67–79内存、80–95等待/信号、96–111显示扩展只预留，未分配具体新接口。
- 主端下一建议为PX4-A设计包；xypm先补P2-2共享有效/畸形输入和guest，再进入持久事务。
- 新实现按模块登记占用，ABI逐项先登记，独立分支/PR交付；公共build排他，localpilot隔离。
| 范围 | 已保存状态 | 接续/边界 |
|---|---|---|
| 当前分支输入编辑 F1/F2 | 4003511；已有定向证据，完整设计 partial | [0064](work_log/0064_input_edit_first_stage.md)；故障、复杂终端等仍待补测 |
| 当前分支 DU 设计 | 928c755；[DU路线](plans/daily_utilities.md)已落盘 | 本分支尚未包含工具实现；DU1/2 13 命令，DU3 按依赖、DU4 包/ISO交付 |
| codex/daily_utilities | 核对时 a770fc0，工作区干净 | 含 Open Adventure、UTF-8 文件名、xypm P2 和 DU 工具组合；有各自定向证据，尚未与当前 Qt/输入编辑组合整合 |
| codex/xypm-p2-p3 | d6363f8，工作区干净 | P2事务与恢复限定验收已保存；本分支的 xypm 当前登记仍按上表，P3未完成 |

独立分支实际进展不等于当前分支已交付，也不能因当前登记未合入而否认分支已有证据。
本地提交范围和各分支来源见[0069](work_log/0069_all_worktree_local_commit.md)。

## 接手与下一步

- Qt E15 已经 PR #8 合入；下一段 E16/G04 需完成显示输入与跨线程通知的组合等待，
  无新增 Qt 专属内核 ABI。完整成员许可/静态分发、绝对峰值及图形资格仍未完成。
- 日常工具实施接续 `codex/daily_utilities` 的实际交接，避免重复写 DU1/2；整合时核对
  SDK/profile、xypm P2、UTF-8 路径、安装清单及 ISO payload 的真实依赖，逐项验收新组合。
- 输入编辑按[第一档](plans/input_edit_foundation.md)、[第二档](plans/terminal_editor.md)及
  [多语言](plans/multilingual.md)继续；kg 仅移植探索对象，没有编辑器客体资格。
- 67–79 内存、80–95 等待/信号、96–111 显示扩展仍仅预留，具体接口先登记再实施。
- 按 Discipline→本页→宪法→专项契约/登记接手；历史原文由[来源索引](history/source_index.json)
  追溯。新开发独立分支/PR交付，公共 build 排他，localpilot 隔离。
