# XOS 当前状态（全局快照）

2026-11-03 · 快照。按 [Discipline](Discipline.md) 的 state.md 规则，本文件只在整体变动
时刻（功能 PR 合入 main、Release、里程碑）由当时的合并者更新；行级细节与证据见各
[work_log](work_log/)，本线活记忆写工作区根的 `STATE_L.md`（不入 git）。历史明细见
[work_log](work_log/) 与 [history](history/)，原则裁决见
[xos_plan.md 第一部分](xos_plan.md#第一部分设计原则)。

## 基线

- 已发布资产仍是 0.0.1-1026（源码 db5b46c / build 7a4668477d7323de），
  smoke 11/11、许可材料 7 份。[回执](releases/release_0_0_1_1026.json)
  下一版号已定为 **0.0.2-1103**（`VERSION` 已更新，未发布：冻结/打包/上传
  按 [发行准备](releases/next_release.md) 执行）。
- 宪法 xos_plan v1.7：C28 驱动纯洁性、C29 时间域、C30 命名归属、C31 建设基础
  而非制造已经完成的假象；v1.7 删除 localpilot 隔离表述（`localpilot/` 已移出主
  工作区）。
- ABI：71 个已分配 syscall（`docs_consistency` 实测）；67 仅匿名 VM 认领未实施；
  `sys_device`=112 已登记（[device_authorization_v1](contracts/device_authorization_v1.md)）
  并完成实施段 1a。

## 各线状态（一句话，细节见 work_log）

| 线 | 状态 | 记录 |
|---|---|---|
| 应用故障包 FB0–FB2 | 受限通过；FB3/FB4、断电安全、全局收集未验 | [0080](work_log/0080_fb0_fault_bundle.md)、[0081](work_log/0081_fb1_fb2_fault_bundle.md) |
| 时钟/IRQ 统一（C29） | #33 已合，统一时基落地 | [0112](work_log/0112_clock_irq_split.md) |
| VirtIO-Net N1 / PR #20 | 保持 RC 未合并：要求拆分，驱动留实验分支 | PR #20 分支内记录（0084/0101） |
| N2 用户态网络 | BLOCKED；设备授权原语已登记且段 1a 合入（#64/#65），待段 1b grant 表 | [0097](work_log/0097_network_time_domains.md)、[0170](work_log/0170_device_authorization_step1a.md) |
| 浏览器 B0/B1 | 已合（本地 HTML/CSS 子集）；B2 网络 BLOCKED | [0083](work_log/0083_aurora_browser_offline.md)、[0096](work_log/0096_browser_review_fixes.md) |
| Aurora UI v2 SDK | #29 已合（含 C30 改名与评审修复） | [0102](work_log/0102_aurora_ui_v2_sdk.md)、[0112](work_log/0112_aurora_c30_rename_and_fixes.md) |
| Semantic Broker / 时间语义 / G3 复核 | #30/#31/#32 已合（勘查与限定模型） | [0108](work_log/0108_semantic_pipe_probe.md)、[0109](work_log/0109_temporal_semantics.md)、[0110](work_log/0110_aurora_g3_review.md) |
| 现代应用兼容 Phase 1 | 已合，探针级；完整浏览器/Core/HTTPS 未通过 | [0085](work_log/0085_modern_app_compatibility_phase1.md) |
| Pillow 静态成像 | 核心受限通过；线程 BLOCKED（`_malloc_r` vector14 未解） | [0088](work_log/0088_cpython_static_pillow.md) |
| PX4-A 匿名 VM | 仅设计认领，未实施 | [0098](work_log/0098_vm_time_domains.md) |
| 终端 / ncursesw W1 | 最终验收全 gate 通过并合入（#66）：W0 冻结、4 系统、15 项交接探针、`freeze_ncursesw_subset` 12 项 | [0187](work_log/0187_w1_final_acceptance.md)、[0074](work_log/0074_ncursesw_w1_scout.md) |
| 许可两叶（D7） | 许可面收口进行中（0188 交付 newlib 1053/1053、GNU Seed、Qt 静态分发审查；0189 补 Qt 文本/§4d0 材料/补丁标注、GCC 运行库 397/407、Qt 逐成员映射）；发版流程中止 | [0188](work_log/0188_d7_license_two_leaves.md)、[0189](work_log/0189_d7_license_full_closure.md) |
| 日常工具 / UTF-8 / xypm / 游戏 | 已整合；xypm P3 未完成；游戏线工作区已建未开工 | [0069](work_log/0069_daily_utilities.md)、[0068](work_log/0068_utf8_filenames.md)、[0066](work_log/0066_xypm_p2_validation.md) |

## 当前能力与证据（慢变量）

| 面 | 实际状态 | 证据入口/边界 |
|---|---|---|
| 发行 | 1026已发布，源码db5b46c/build7a4668477d7323de；smoke11/11、许可材料7份；0.0.2-1103 已定版待发 | [不可变回执](releases/release_0_0_1_1026.json)、[发行准备](releases/next_release.md) |
| 核心/工具链 | E01–E08受限功能；原生GCC/G++开发已验，post5 P1仍partial | [E01–E07](history/e01_e07.md)、[E08](e08.md)；系统重建/自举未验（D6） |
| 线程 | T0–T2、T3-PY与PY2专项已有证据 | [线程资格](reports/threading_20261025/qualification.json)；Qt QThread受限实测，SMP未验 |
| Shell / 终端 | dash C1–C3受限通过，xsh保留默认；终端服务交接与 ncursesw 宽字符客体验收通过 | [C3资格](reports/dash_c3_20261026/qualification.json)，build2f7160b7d6633ee6；无完整信号/作业控制；[0187](work_log/0187_w1_final_acceptance.md) |
| 显示/ISO | sys65/66 在 buildef83c9fc92217380 重验 G02 19组通过 | [当前报告](reports/qt_e16_qualified_20261028/g02/report.json)、[显示历史](history/boot_display.md)；QtGui/QPA 单全屏 raster 已验 |
| CPython | PY0–PY2/T3-PY、A1–A3、B1–B4专项通过 | [用户态摘要](history/userland.md)；B2–B4系统6251d26b611a388d，Python11c39c52e451a9499450 |
| xypm | P2原生验证、事务和启动恢复已实现；限定范围内验收通过 | [包计划](plans/packages.md)、[0066](work_log/0066_xypm_p2_validation.md)；P2验收范围和局限见记录；P3未完成 |
| 审计/整合 | A01–A04修复与PR3兼容已交付PR4 | [整合摘要](history/delivery_audit.md)，组合build76a2e4380f64fb2e，7定向组通过；非旧全量重验 |
| POSIX/Qt | PX0子集文档已有；QtCore 6.8.3 G01/G03 与 QtGui/QPA G04 受限客体功能通过 | [PX路线](plans/posix.md)、[E16资格](reports/qt_e16_qualified_20261028/qualification.json)；Widgets/G05 已受限客体验证，见0078；QML/Quick 未实现，绝对峰值未验 |
| 许可 | 材料检查通过；newlib 1053/1053、GCC 运行库 397/407 成员映射、GNU Seed 分发审查、Qt 静态分发审查与收口材料（文本/§4d0/补丁标注）已交付 | [许可证管理](licensing.md)、[0188](work_log/0188_d7_license_two_leaves.md)、[0189](work_log/0189_d7_license_full_closure.md)；均为映射/材料审查，**非法务意见**，Qt 静态再分发资格未授予 |

每项资格只对其冻结输入成立。旧源/SDK/镜像不改绑；许可材料通过不代表逐成员审计完成。

## 下一步

- **0.0.2-1103 发版流程已中止**（2026-11-03 用户裁定：先完成 D7 收口再发）：版本号已定、
  dash/install ISO 已按新版重建，但未冻结打包、未打 tag、未传资产；1026 仍是唯一可下载
  发行。收口后按 [发行准备](releases/next_release.md) 重新走完四步再发。
- 设备授权原语段 1b（grant 表）→ 显示迁移纵向切片 → ps2/ata（依赖 sys82 对齐）；
  N2 网络接其后。PR #20 按 RC 拆分要求仍挂账。
- 系统重建/自举（D6）尚未开始；QML/Quick 移植为独立功能线，未立项。
- 按 Discipline → 本页 → 宪法 → 专项契约/登记接手；新开发独立分支/PR 交付，
  公共 build 排他。
