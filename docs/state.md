# XOS 当前状态

2026-10-27。源码基线PR #4 squash `a265061`；本轮分支`codex/docs_constitution`。
发布资产仍为0.0.1-1026，未随后续实现或本次文档整理更新。
原则裁决见[xos_plan.md第一部分](xos_plan.md#第一部分设计原则)，本页仅登记事实与占用。

## 当前能力与证据

| 面 | 实际状态 | 证据入口/边界 |
|---|---|---|
| 发行 | 1026已发布，源码db5b46c/build7a4668477d7323de；smoke11/11、许可材料7份 | [不可变回执](releases/release_0_0_1_1026.json) |
| 核心/工具链 | E01–E08受限功能；原生GCC/G++开发已验，post5 P1仍partial | [E01–E07](history/e01_e07.md)、[E08](e08.md)；系统重建/自举未验 |
| 线程 | T0–T2、T3-PY与PY2专项已有证据 | [线程资格](reports/threading_20261025/qualification.json)；T3-QT/SMP未验 |
| Shell | dash C1–C3受限通过，xsh保留默认 | [C3资格](reports/dash_c3_20261026/qualification.json)，build2f7160b7d6633ee6；无完整信号/作业控制 |
| 显示/ISO | 原分支G02、ISO容量各有受限证据；PR4显示改65/66 | [显示](history/boot_display.md)，[ABI](contracts/abi_registry.md)；未编译Qt |
| CPython | PY0–PY2/T3-PY、A1–A3、B1–B4专项通过 | [用户态摘要](history/userland.md)；B2–B4系统6251d26b611a388d，Python11c39c52e451a9499450 |
| xypm | P0/P1/P2-1通过；P2-2只读verify/plan和ELF校验已实现/打包 | [包摘要](history/packages.md)；P2-2 guest/adversarial未验，P2-3/4与P3未开始 |
| 审计/整合 | A01–A04修复与PR3兼容已交付PR4 | [整合摘要](history/delivery_audit.md)，组合build76a2e4380f64fb2e，7定向组通过；非旧全量重验 |
| POSIX/Qt | PX0子集文档已有；Qt接口/ABI预留仅契约 | [PX路线](plans/posix.md)、[Qt协作](contracts/qt_platform.md)，PX1以后/Qt实现未开始 |

每项资格只对其冻结输入成立。旧源/SDK/镜像不改绑；许可材料通过不代表逐成员审计完成。
详细哈希和未运行项保留在history/reports；当前实现说明不重复放置逐日交接叙事。

## 本轮文档交付

0061已建立宪法双部分、ABI/Qt协作登记，合并历史并优化目录；文档/ABI/来源检查通过，
冻结证据未变。实现与新系统验收未启动，源码/构建占用均无，详见
[0061交接](work_log/0061_docs_constitution.md)。本轮通过独立PR交付，其他人应待登记合入后使用。

## 接手与下一步

- 遵循Discipline→本页→宪法→专项契约/登记；需要原过程时用[来源索引](history/source_index.json)，
  无须从已合并工作日志猜当前状态。
- Qt移植先基于本登记合入后的main：复用65/66、pthread/时钟，向底座提最小缺口探针；
  67–79内存、80–95等待/信号、96–111显示扩展只预留，未分配具体新接口。
- 主端下一建议为PX4-A设计包；xypm先补P2-2共享有效/畸形输入和guest，再进入持久事务。
- 新实现按模块登记占用，ABI逐项先登记，独立分支/PR交付；公共build排他，localpilot隔离。
