# XOS 当前状态

2026-10-28。上游基线 `244ac40`；本轮分支 `codex/qt6-e15`、Draft PR #8。
发布资产仍为0.0.1-1026，未随后续实现或本次文档整理更新。
原则裁决见[xos_plan.md第一部分](xos_plan.md#第一部分设计原则)，本页仅登记事实与占用。

## 正在进行

- E15 Qt 移植：`codex/qt6-e15`；Qt 端口、私有构建、夹具及线程 SDK 编译入口修复（需整合者审查）。QtCore 6.8.3 的 G01/G03 已完成受限客体功能资格；不占用公共 ABI。详见 [实施记录](plans/qt_e15_execution.md) 与 [0064](work_log/0064_qt_e15_qualification.md)。

## 当前能力与证据

| 面 | 实际状态 | 证据入口/边界 |
|---|---|---|
| 发行 | 1026已发布，源码db5b46c/build7a4668477d7323de；smoke11/11、许可材料7份 | [不可变回执](releases/release_0_0_1_1026.json) |
| 核心/工具链 | E01–E08受限功能；原生GCC/G++开发已验，post5 P1仍partial | [E01–E07](history/e01_e07.md)、[E08](e08.md)；系统重建/自举未验 |
| 线程 | T0–T2、T3-PY与PY2专项已有证据 | [线程资格](reports/threading_20261025/qualification.json)；Qt QThread受限实测，SMP未验 |
| Shell | dash C1–C3受限通过，xsh保留默认 | [C3资格](reports/dash_c3_20261026/qualification.json)，build2f7160b7d6633ee6；无完整信号/作业控制 |
| 显示/ISO | sys65/66 在 build48e5e73bcd649f44 重验 G02 19组通过 | [当前报告](reports/qt_e15_qualified_20261028/g02_report.json)、[显示历史](history/boot_display.md)；QtGui/QPA未实现 |
| CPython | PY0–PY2/T3-PY、A1–A3、B1–B4专项通过 | [用户态摘要](history/userland.md)；B2–B4系统6251d26b611a388d，Python11c39c52e451a9499450 |
| xypm | P0/P1/P2-1通过；P2-2只读verify/plan和ELF校验已实现/打包 | [包摘要](history/packages.md)；P2-2 guest/adversarial未验，P2-3/4与P3未开始 |
| 审计/整合 | A01–A04修复与PR3兼容已交付PR4 | [整合摘要](history/delivery_audit.md)，组合build76a2e4380f64fb2e，7定向组通过；非旧全量重验 |
| POSIX/Qt | PX0子集文档已有；QtCore 6.8.3 静态受限客体 G01/G03 功能通过 | [PX路线](plans/posix.md)、[Qt资格](reports/qt_e15_qualified_20261028/qualification.json)；QtGui/QPA 未开始，绝对峰值/发行许可未完成 |

每项资格只对其冻结输入成立。旧源/SDK/镜像不改绑；许可材料通过不代表逐成员审计完成。
详细哈希和未运行项保留在history/reports；当前实现说明不重复放置逐日交接叙事。

## 本轮文档交付

0061宪法与登记已通过 PR #5 合入；本轮 E15 的受限功能资格和未支持项见
[0064交接](work_log/0064_qt_e15_qualification.md)，Draft PR #8 尚待审查。
同一冻结产物已完成16项Qt客体重跑及阻塞/定时器退出补验，并重跑G02、线程、文件与持久化，
见[0065](work_log/0065_qt_e15_lifecycle_recheck.md)；发行资格仍未完成。

## 接手与下一步

- 遵循Discipline→本页→宪法→专项契约/登记；需要原过程时用[来源索引](history/source_index.json)，
  无须从已合并工作日志猜当前状态。
- E16 从 E15 审查后的基线继续；QPA 显示输入和跨线程唤醒的组合等待需另行验证。
  67–79内存、80–95等待/信号、96–111显示扩展只预留，未分配具体新接口。
- 主端下一建议为PX4-A设计包；xypm先补P2-2共享有效/畸形输入和guest，再进入持久事务。
- 新实现按模块登记占用，ABI逐项先登记，独立分支/PR交付；公共build排他，localpilot隔离。
