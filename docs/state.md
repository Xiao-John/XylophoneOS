# XOS 当前状态（全局快照）

2026-11-26 · 下一阶段里程碑。主线已合入显式 glibc C/C++ 应用打包、原生 xypm
客体维护、Qt Quick 软件渲染及外部应用工具包、Mobius glibc 会话和工作盘迁移。
Pumpkin 盘外代际由开发客体验证，ClarkE 的 LLInt 和 WTF 栈范围进入目标构建。
各模块的客体结果与组合复验分别登记。
[本阶段计划](plans/next_stage.md) · [上阶段整合记录](work_log/efc3a5ff_xos_integration_campaign.md)

按 [Discipline](Discipline.md) 在合并、发行或里程碑更新。过程与证据见
[work_log](work_log/) 和 [history](history/)，设计原则见
[xos_plan.md 第一部分](xos_plan.md#第一部分设计原则)。本线活记忆写工作区根的
`STATE_L.md`（不入 Git）。

## 基线

- **0.0.2-1103 已发布**（2026-11-04，tag `v0.0.2-1103` → `071330f3`）：
  build `8356e45af316fc93`，release_smoke **11/11**，license_audit **0 open**，
  含 **Qt 静态资产**（用户指令）。[回执](releases/release_0_0_2_1103.json)、
  [发行说明](releases/0.0.2-1103.md)、[playbook](releases/playbook.md)。
  0.0.1-1026 仍可下载（历史）。流程脚本：`scripts/release_pipeline.sh`。
- 宪法 xos_plan v1.7：C28 驱动纯洁性、C29 时间域、C30 命名归属、C31 建设基础
  而非制造已经完成的假象；v1.7 删除 localpilot 隔离表述（`localpilot/` 已移出主
  工作区）。
- ABI 有 78 个已分配 syscall（`docs_consistency` 实测）。sys67 匿名 VM 已实现，
  涵盖 VM1/VM2 和恢复后的 VM3 限定客体场景，完整资格待验。sys112 支撑用户态
  VirtIO-Net 纵切。sys20 wait-any、sys35 当前线程 TLS 和 sys51 有界退出清理
  均按各自契约和受测阶段登记。[ABI 登记](contracts/abi_registry.md)

## 各线状态（一句话，细节见 work_log）

| 线 | 状态 | 记录 |
|---|---|---|
| 应用故障包 FB0–FB2 | 受限通过；FB3/FB4、断电安全、全局收集未验 | [0080](work_log/0080_fb0_fault_bundle.md)、[0081](work_log/0081_fb1_fb2_fault_bundle.md) |
| 时钟/IRQ 统一（C29） | #33 已合，统一时基落地 | [0112](work_log/0112_clock_irq_split.md) |
| VirtIO-Net / N2–N3 | sys112 授权的用户态驱动和 lwIP v2 已合入。传输、多应用隔离、生命周期和撤销有绑定客体结果。raw 诊断保持隔离。 | [原始帧纵切](contracts/net_user_driver.md)、[v2 契约](contracts/net_service_v2.md)、[多应用复验](work_log/69b0e274_network_guest_readiness_and_window.md) |
| N4 DNS/DHCP | 配置与名称契约以及 DNS 回包收紧已合入。生产 DNS/DHCP 保持关闭。 | [N4 契约](contracts/network_n4_v1_proposal.md)、[DNS 记录](work_log/4e29c6b1_network_dns_hardening.md) |
| ClarkE 浏览器 | glibc Widgets 入口、开发包生命周期、HTML/CSS 与受控 HTTP 已在客体复验。WebKit 已生成目标 LLInt，WTF 线程栈范围通过原生辅助函数验证。完整引擎与 HTTPS 待验。 | [glibc 客体](work_log/b8adab19_clarke_glibc_widgets.md)、[LLInt](work_log/89051575_clarke_native_llint_layout_bridge.md)、[WTF](work_log/207c6644_clarke_native_wtf_thread_and_stack_slice.md) |
| Mobius 系统 UI | 正式入口和 glibc Qt Widgets 会话已合入。实际 XPK 安装后双入口启动，卸载后原 newlib 桌面可从旧入口启动，用户配置保留。 | [桌面客体](work_log/8f0020c4_mobius_glibc_widgets_guest.md)、[工作盘与回退](work_log/f38242fd_mobius_glibc_xpk_lifecycle.md) |
| Pumpkin | 身份核心、原生 IPC、私有存储区和受信客户端已合入。开发守护进程复验吊销、当前盘恢复和旧盘拒绝。普通镜像的封存对象通过两轮拥有者与跨账号授权验收。生产代际和凭据发放待验。 | [身份核心](work_log/c6198fee_pumpkin_identity_core.md)、[盘外代际](work_log/31dde03e_pumpkin_anchored_guest_snapshot_fence.md)、[封存对象](work_log/8ca1f149_pumpkin_sealed_resource_guest.md) |
| Aurora UI v2 SDK | #29 已合（含 C30 改名与评审修复） | [0102](work_log/0102_aurora_ui_v2_sdk.md)、[0112](work_log/0112_aurora_c30_rename_and_fixes.md) |
| Semantic Broker / 时间语义 / G3 复核 | #30/#31/#32 已合（勘查与限定模型） | [0108](work_log/0108_semantic_pipe_probe.md)、[0109](work_log/0109_temporal_semantics.md)、[0110](work_log/0110_aurora_g3_review.md) |
| 现代应用兼容 Phase 1 | 已合，探针级；完整浏览器/Core/HTTPS 未通过 | [0085](work_log/0085_modern_app_compatibility_phase1.md) |
| Pillow 静态成像 | 核心受限通过；线程 BLOCKED（`_malloc_r` vector14 未解） | [0088](work_log/0088_cpython_static_pillow.md) |
| PX4-A 匿名 VM | sys67、续体、公开映射子集及 fork/exec 生命周期已实现，VM3 恢复后有定向客体记录。SDK 完整资格仍为 `implemented_unqualified`。 | [VM3 恢复记录](work_log/58b24599_vm3_lifecycle_sdk.md)、[VM2](work_log/588667af_vm2_full_qualification.md) |
| 终端 / ncursesw W1 | 冻结基线 #66 通过 15 项终端交接和 12 项 ncursesw 子集。glibc 组合候选通过原 W1 locale、24×80 重入和宽屏交互。 | [冻结基线](work_log/0187_w1_final_acceptance.md)、[glibc 组合](work_log/77b48ecc_runtime_acceptance_checkpoint.md#ncursesw-串口组合) |
| 许可两叶（D7） | #67/#68 逐成员映射和分发材料保留。#169 修正 SPDX 与材料摘要，本阶段登记 0 open、1 deferred、7 N/A。 | [0188](work_log/0188_d7_license_two_leaves.md)、[0189](work_log/0189_d7_license_full_closure.md)、[登记](../licenses/open_items.json)、[整合修正](work_log/7a8d4aa9_integration_license_materials.md) |
| SSG 批次 / Aurora Dock | 2026-11-04 批次合入 #45（Dock 图标）、#40（SSG consumers 派生证据）、#44→#49（Browser/Notes SSG 栈）和 #50（P3B 双 Provider、C30 改名及全量 manifest）。 | [Dock](work_log/0190_aurora_midnight_dock.md)、[双 Provider](work_log/0196_ssg_p3b_dual_provider.md) |
| 日常工具 / UTF-8 / 游戏 | 各自有既有整合记录，游戏线沿用该批的交付范围。 | [0069](work_log/0069_daily_utilities.md)、[0068](work_log/0068_utf8_filenames.md)、[Open Adventure](work_log/0066_open_adventure_package.md) |

## 当前能力与证据（慢变量）

| 面 | 实际状态 | 证据入口/边界 |
|---|---|---|
| 发行 | **0.0.2-1103 已发布**（含 Qt 资产；smoke 11/11、audit 0 open）；1026 历史可下载 | [回执](releases/release_0_0_2_1103.json)、[playbook](releases/playbook.md) |
| 核心/工具链 | E01–E08受限功能；原生GCC/G++开发已验，post5 P1仍partial | [E01–E07](history/e01_e07.md)、[E08](e08.md)；系统重建/自举未验（D6） |
| 线程 | T0–T2、T3-PY与PY2专项已有证据 | [线程资格](reports/threading_20261025/qualification.json)；Qt QThread受限实测，SMP未验 |
| Shell / 终端 | dash C1–C3受限通过，xsh保留默认；终端服务交接与 ncursesw 宽字符客体验收通过 | [C3资格](reports/dash_c3_20261026/qualification.json)，build2f7160b7d6633ee6；无完整信号/作业控制；[0187](work_log/0187_w1_final_acceptance.md) |
| 显示/ISO | sys65/66 在 buildef83c9fc92217380 重验 G02 19组通过 | [当前报告](reports/qt_e16_qualified_20261028/g02/report.json)、[显示历史](history/boot_display.md)；QtGui/QPA 单全屏 raster 已验 |
| CPython | PY0–PY2/T3-PY、A1–A3、B1–B4专项通过 | [用户态摘要](history/userland.md)；B2–B4系统6251d26b611a388d，Python11c39c52e451a9499450 |
| xypm | P2 与 glibc C++ 客体安装、升级、卸载、重启和恢复已有实验 profile 证据，冻结 newlib 入口已复验。P3 离线仓库、锁和重启回读已合入。 | [glibc 事务](work_log/24df429a_xypm_glibc_guest_transactions.md)、[P2](work_log/0066_xypm_p2_validation.md)、[P3](work_log/7c2de8a4_xypm_p3_preview_guest.md) |
| glibc | 静态 C/C++、进程启动与等待、dash 外部 ELF 的原生管线和重定向、单终端描述符读就绪已合入。D1 通过双高地址来宾探针并构建共享 rtld 入口对象。完整 C3、解释器、后续动态链接和默认切换待验。 | [应用生命周期](work_log/82cabf5d_glibc_xpk_lifecycle.md)、[双入口管线](work_log/6d49a810_glibc_dash_child_stdio.md)、[终端就绪](work_log/0f07e824_glibc_terminal_select.md)、[共享 rtld](work_log/a1cc675f_glibc_d1_shared_rtld_entry_diagnostic.md) |
| SDK 过渡 | newlib 是现行默认。glibc C/C++ 使用隔离候选与配套验收，候选准入和激活分别登记。普通及线程 newlib 的文件能力清单已有同源阶段复验。 | [SDK profile 契约](contracts/xypm_sdk_profiles.md)、[glibc 源认证](work_log/53bc719e_glibc_source_authentication.md)、[阶段记录](work_log/efc3a5ff_xos_integration_campaign.md) |
| 审计/整合 | A01–A04修复与PR3兼容已交付PR4 | [整合摘要](history/delivery_audit.md)，组合build76a2e4380f64fb2e，7定向组通过；非旧全量重验 |
| POSIX/Qt | 静态 QtQml 通过脚本、绑定、回收和 VM 配额负向检查。Quick 软件渲染及输入在两种 Shell 通过。外部应用使用独立工具包构建后通过实际文本画面与资源回收。 | [QtQml](work_log/d8bd3467_qt_e18_target_qml_and_vm.md)、[Quick](work_log/13a6b397_qt_e19_quick_through_legacy_dash.md)、[外部应用](work_log/b9673c26_qt_e19_external_quick_application_builder.md) |
| 许可 | 材料检查通过；newlib 1053/1053、GCC 运行库 397/407 成员映射、GNU Seed 分发审查、Qt 静态分发审查与收口材料（文本/§4d0/补丁标注）已交付 | [许可证管理](licensing.md)、[0188](work_log/0188_d7_license_two_leaves.md)、[0189](work_log/0189_d7_license_full_closure.md)；均为映射/材料审查，**非法务意见**，Qt 静态交付物已按 B4/B5 门槛随 0.0.2-1103 分发（非法务意见） |

每项资格绑定各自冻结的源码、SDK、镜像和配置。逐成员许可范围按各自审查记录追溯。

## 正在进行

| 负责线 | 范围 |
| --- | --- |
| 总协调 | 阶段计划、产品标识、公共 ABI、SDK 默认和组合验收 |
| 运行库 | 旧阻塞复核、C/C++ SDK 和存量应用迁移 |
| Qt 与浏览器 | QML/Quick 构建和平台勘查，ClarkE 引擎纵切 |
| 身份 | Pumpkin 用户态协议、权限和持久化边界 |

[阶段计划](plans/next_stage.md)

## 下一步

- 后续组合候选通过 79 项常规、10 项许可材料和 50 次 glibc 客体运行。最终实际
  里程碑需重建两套 SDK 并绑定组合门禁。[组合复验](work_log/ea2d71c6_next_stage_combined_guest.md)
- N4 生产启用、glibc 默认 SDK 切换、动态链接 D1–D4、显示/ps2/ata 后续设备迁移、
  系统重建/自举（D6）与 Qt QML/Quick 各按专项计划推进。
- 按 Discipline → 本页 → 宪法 → 专项契约/登记接手；新开发独立分支/PR 交付，
  公共 build 排他。

## 历史快照补记

- 2026-11-04 的发行快照记录了 Qt B4 打包 25/25 和 B5 `PASS_WITH_LIMITS`，商业路径 N/A。
  当时 #51 按指示暂缓，记录有 9 处冲突、请求修改及 13 份缺 manifest 的报告。
  早期内核 VirtIO-Net RC #20 的拆分要求和段 1a 登记见
  [设备授权记录](work_log/0170_device_authorization_step1a.md)。
- 当时 D7 第一次阶段登记为 3 open、3 deferred、2 N/A，发行在正式收口后执行。
  [D7 记录](work_log/0189_d7_license_full_closure.md) · [发行工作记录](work_log/0204_release_publish.md)
- 线程时钟修复的原分支记录三项 review 修正及宿主 wrapper 通过，当时客体未运行。
  [原始记录](work_log/7bc4cfb8_threaded_clock_error_returns.md)
- 2026-11-13 的虚拟 `/dev` 审查记录包含 staging 拒绝、稳定身份和 null 写入边界。
  宿主验证通过，当时客体未运行。[原始记录](work_log/61f0c353_dev_null_review.md)
