# XOS 当前状态（全局快照）

2026-11-27 · 下一阶段里程碑。主线已合入可显式选择的 glibc C/C++ 应用 SDK、
原生 xypm 客体维护、Qt Quick 软件渲染及外部应用工具包、Mobius glibc 会话和
工作盘迁移。Pumpkin 开发配置已验跨重启登录、持久多账户和独立资源 broker。
Pumpkin 的持久身份已在显式镜像中启动并收回真实 Mobius 桌面。ClarkE 已验受控
HTTPS、JavaScriptCore 静态 shell、真实 HTML 分词和 Skia 软件栅格。`d7c56292`
已合入 glibc dash 命令替换、GNU rtld 首线程 TLS、可搬移 Qt Quick 工具包和 glibc
stock 安装及应用组合。签名 C/C++ 候选 `3bbbf73984b95c20` 通过冷装、重启和卸载，
同盘应用组合两次启动均覆盖命令替换。普通镜像的 79 项、10 项许可材料和 ABI 通过。
主线 `6bd530bf` 随后纳入 ClarkE 的 FAT 字体流修复，以及 Pumpkin 正在使用的 Mobius
会话的管理员撤销。前者实测应用从 FAT 加载字形并恢复资源，后者通过 8 项桌面和
13 项无桌面检查。Pumpkin 首次账户发放、完整 WebCore 页面和 SDK 默认切换继续按各自门验收。
`bbf38ffb` 记录冻结 newlib 的三次冷启动回退。原发行盘在 glibc 运行期间完整摘要保持一致，
回退后原 ELF 和用户数据可读回。[冻结回退](work_log/4ffa226d_glibc_stock_fork_frozen_rollback.md)

主线 `645ba017` 已复验应用 SDK 的 v2 安装配置。独立普通预设及候选系统各通过
79 项常规客体检查、10 项许可材料检查和 ABI 核对。候选安装验证五项、空盘安装 13 个
工具、重启和卸载保留用户数据均通过。随后主线合入 Qt Quick v2 的断网接收及双
Shell 验收，和发行安装组件的对应源码包。整套发行资产的同源验收继续按发行门推进。
[安装候选组合](work_log/645ba017_next_stage_glibc_v2_installer.md) ·
[Qt Quick v2](work_log/659b4dc2_qt_quick_unified_v2.md) ·
[组件源码](work_log/9c747f60_glibc_v2_component_sources.md)
冻结 v2 候选的原归档、补充源码与 xypm 复链包已通过十份资产的离线校验。
[发行资产暂存](work_log/cc50f79b_glibc_v2_distribution_supplements.md)
主线 `960fce43` 的 v2 发行候选从对应归档重开。包生命周期四项与
原生 GNU 工具 20 项通过，接收方 SDK 可在仓库外构建和打包 C/C++。
发行盘 IDNA 升级实测通过中断恢复和冷启重试。同一系统的冻结 newlib 回退
通过三次冷启。整套静态程序的替换材料仍待补齐。
[发行组合](work_log/960fce43_glibc_v2_current_release.md) ·
[冻结回退](work_log/960fce43_glibc_v2_frozen_newlib_roundtrip.md)
同一候选的外层暂存现可纳入 glibc 2.44 上游源码，已重开 11 项资产并离线验签。
[上游源码暂存](work_log/960fce43_glibc_release_upstream_source.md)
Dash 已由离线接收方逐字节重链。同一安装盘的替换版返回预期的 `$$`，两版均
运行外部 ELF 并回收资源。Dash 对应对象和配方已加入同候选暂存，12 项资产核对通过。
[Dash 重链接](work_log/960fce43_glibc_v2_dash_relink.md) ·
[归档暂存](work_log/960fce43_glibc_v2_dash_material_delivery.md)
日用 XPK 的 13 个程序已逐字节复链，同一盘上通过替换对照。日用程序归档随
同版候选完成暂存。GNU Make 已从两种 Shell 通过客体替换，xypm 也在同版
安装器和普通介质复跑。CPython 也已逐字节复链并通过替换版客体。该候选的 17 个
glibc 静态程序均已完成对应替换验收，外层留存档案校验覆盖 15 项。
[日用程序重链接](work_log/960fce43_glibc_v2_daily_relink.md) ·
[日用程序暂存](work_log/960fce43_glibc_v2_daily_material_delivery.md) ·
[GNU Make 暂存与 xypm](work_log/960fce43_glibc_v2_gnu_make_material_delivery.md) ·
[CPython 暂存](work_log/960fce43_glibc_v2_cpython_material_delivery.md)
[当前普通组合复验](work_log/515a2e65_next_stage_combined.md)
[网络组合复验](work_log/3d21f4e4_next_stage_network_replay.md)
[复验记录](work_log/1c7f9abb_next_stage_mainline_replay.md)
[本阶段计划](plans/next_stage.md) · [上阶段整合记录](work_log/efc3a5ff_xos_integration_campaign.md)

Qt Quick 外部示例已用普通 xypm 离线工作盘完成原包安装、重编库替换和原包回退。
三次冷启渲染相同画面，回退保留替换后新增的用户文件。
[接收者安装验证](work_log/4d6f124f_qt_quick_receiver_install.md)
同版 Mobius Widgets v2 套件已完整构建并由独立接收方打包。真实客体通过安装、
升级、卸载后重装的三次冷启，覆盖两种 Shell、会话、渲染、用户数据与资源回收。
同修订 XPK 已在两个路径逐字节复现。接收方还用实际修改的 QtGui 归档重链桌面，
普通客体两次冷启证实桌面执行了替换代码。对应源码材料与 Curvive 分发授权仍待关闭。
[Mobius Widgets v2](work_log/74efcc27_mobius_widgets_v2.md) ·
[单修订 XPK](work_log/af0f64ef_mobius_v2_xpk.md) ·
[QtGui 替换](work_log/05dfb2b9_mobius_qt_v2.md)

glibc 原生共享固定闭包已在公开 `dlopen`、`dlmopen` 和 `dlclose` 入口拒绝运行期装卸。
四组客体分别覆盖原样、修复、普通 C 启动和启动依赖缺 pin，资源均已回收。
`515a2e65` 的普通配置另通过 79 项客体、10 项许可材料和 ABI 核对。
[固定闭包实测](work_log/glibc_d2_fixed_runtime_loading_policy.md) ·
[普通组合](work_log/515a2e65_next_stage_combined.md)

主线 `d3da83dd` 已合入 ClarkE 的组件栈、完整 WebCore 软件归档、glibc 固定闭包
工作线程和可移植 GCC Seed。独立普通候选 `91b139f2cb7b0408` 通过 79 项客体检查、
10 项许可材料检查、ABI 登记核对及 4 项 Dash 安装器检查。共享工作线程通过 6 次
冷启，运行期公开装卸仍会拒绝。Linux arm64 新建的 GCC Seed 在冻结 glibc 盘的
独立副本通过 18 项客体验收。ClarkE 全页仍需补齐平台入口并通过静态链接、DOM、
CSS 与绘制验收。[收口记录](work_log/d3da83dd_branch_closeout.md)

Pumpkin 的显式 Linux 配置已接入独立 UID 的代际提供者，实测首户签发、重启认证和
只回退客体盘时拒绝。硬件代际与物理启动仍待验收。
[独立提供者部署](work_log/f1d2a697_pumpkin_provider_deployment.md)
同域安装已具备由两个独立角色执行的持久镜像维护工具。ext4 和真实 QEMU 已验
错配拒绝、换版、提交新代际和回切。宿主已验进程中断恢复；物理断电及自动部署
待验。[持久镜像维护](work_log/c4c7bf97_pumpkin_durable_image_maintenance.md)
普通部署登录也可通过已封存的继承描述符提交现有钱包。双 UID 客体通过 22 项检查，
包括可信部署配置、错误密钥和跨 UID 拒绝，以及 QEMU 的描述符隔离。开发配置的
原文件登录亦通过回归。[封存凭据](work_log/pumpkin_sealed_credential_input.md)

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
| N4 DNS/DHCP | 配置、名称契约和私有 DNS 诊断已合入。普通配置的旧网络操作已复验。生产 DNS/DHCP 保持关闭。 | [N4 契约](contracts/network_n4_v1_proposal.md)、[DNS 诊断 PR #269](https://github.com/Xiao-John/XylophoneOS/pull/269) |
| ClarkE 浏览器 | glibc Widgets 安装包已验证受控 TLS 1.3、HTML/CSS/图像及不受信任 CA 拒绝。原生 TLS 客体读取的已验证叶证书与实际对端一致。真实 JavaScriptCore 静态 shell 已合入，锁定的 Test262 同步子集通过 16 次执行。WebCore、完整测试套件和生产网络继续验收。 | [安装包 HTTPS](work_log/7e05f732_clarke_installed_https.md)、[TLS 叶证书](work_log/514a40f2_clarke_verified_peer_leaf.md)、[JSC 客体](work_log/3eba7c25_clarke_jsc_guest.md)、[Test262 子集](work_log/aca430b2_clarke_test262_guest.md) |
| Mobius 系统 UI | 正式入口和 glibc Qt Widgets 会话已合入。统一 glibc SDK v1 套件通过独立接收、静态复链、双入口和 XPK 升级回退。原 newlib 桌面的旧入口仍可恢复。Mobius v2 Widgets 构建和 Curvive 分发许可继续验收。 | [v1 Widgets 套件](work_log/2d4bde25_mobius_unified_widgets.md)、[旧版工作盘与回退](work_log/f38242fd_mobius_glibc_xpk_lifecycle.md) |
| Pumpkin | 身份核心、原生 IPC、私有存储区和受信客户端已合入。开发配置通过跨重启多账户登录、具名资源 FAT 导入、独立 broker 授权、注销、单账户吊销和旧盘拒绝。生产代际及凭据交付继续验收。 | [持久登录和 broker](work_log/7ce64487_pumpkin_durable_account_resource_login.md)、[FAT 导入](work_log/a64d215d_pumpkin_fat_import_integrated.md)、[多账户 PR #272](https://github.com/Xiao-John/XylophoneOS/pull/272) |
| Aurora UI v2 SDK | #29 已合（含 C30 改名与评审修复） | [0102](work_log/0102_aurora_ui_v2_sdk.md)、[0112](work_log/0112_aurora_c30_rename_and_fixes.md) |
| Semantic Broker / 时间语义 / G3 复核 | #30/#31/#32 已合（勘查与限定模型） | [0108](work_log/0108_semantic_pipe_probe.md)、[0109](work_log/0109_temporal_semantics.md)、[0110](work_log/0110_aurora_g3_review.md) |
| 现代应用兼容 Phase 1 | 已合，探针级；完整浏览器/Core/HTTPS 未通过 | [0085](work_log/0085_modern_app_compatibility_phase1.md) |
| Pillow 静态成像 | 核心受限通过；线程 BLOCKED（`_malloc_r` vector14 未解） | [0088](work_log/0088_cpython_static_pillow.md) |
| PX4-A 匿名 VM | sys67、续体、公开映射子集及 fork/exec 生命周期已实现，VM3 恢复后有定向客体记录。SDK 完整资格仍为 `implemented_unqualified`。 | [VM3 恢复记录](work_log/58b24599_vm3_lifecycle_sdk.md)、[VM2](work_log/588667af_vm2_full_qualification.md) |
| 终端 / ncursesw W1 | 冻结基线 #66 通过 15 项终端交接和 12 项 ncursesw 子集。主线 `f9d6384d` 的显式 glibc SDK 通过原 W1 locale、24×80 重入和宽屏交互。 | [冻结基线](work_log/0187_w1_final_acceptance.md)、[glibc 主线复跑](work_log/77b48ecc_runtime_acceptance_checkpoint.md#glibc-sdk-与-ncursesw-串口组合) |
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
| CPython | PY0–PY2/T3-PY、A1–A3、B1–B4 有原 profile 专项证据。统一 glibc SDK 的静态核心已验证实际 stock 安装、重启、旧包拒绝及卸载保留数据。静态 zlib 通过 gzip、压缩 ZIP/导入与卸载。可选静态 `_hashlib` 在普通 CLI 客体验证 OpenSSL 已知向量。发行 IDNA 组合、`_hashlib` 安装包及 `_ssl` 各自验收。 | [用户态摘要](history/userland.md)、[统一 SDK 实测](work_log/4d321863_glibc_cpython_unified_stock.md)、[zlib 实测](work_log/9739fdaa_glibc_cpython_zlib.md)、[OpenSSL hashlib](work_log/c1c3d3d7_cpython_static_openssl_hashlib.md) |
| OpenSSL | 统一 glibc SDK 的 OpenSSL 3.5.9 静态归档已通过普通离线客体的 SHA-256、熵、TLS 1.3 内存通道和主机名校验。WebCore WebCrypto、CPython `_ssl` 及网络 TLS 独立验收。 | [构建与实测](work_log/e832a3fc_openssl_static_glibc_foundation.md) |
| glibc 网络 | 静态 SDK 的 IPv4/IPv6 结构及字节序已验。受信静态配置通过阻塞 IPv4 TCP、描述符和服务回收，GNU 共享 libc 重链和 D1 C 入口通过。动态 TCP、就绪等待和 IPv6 联网仍待验收。 | [地址布局](work_log/9f63f328_glibc_network_address_headers.md)、[TCP 专项](work_log/61202e5f_glibc_net2_tcp.md) |
| 统一 glibc v2 候选 | 搬移后的工具包通过 C/C++、线程、地址与文件等待。独立发行候选通过四份归档接收和 GNU Seed、CPython/zlib、IDNA 组合客体。保留 v1 回退，最终候选的升级和中断恢复仍待验收。 | [C/C++ 工具包](work_log/ee216d1d_glibc_file_network_unified_sdk.md)、[发行候选](work_log/9f6b0349_glibc_v2_release_inputs.md) |
| xypm | P2 与 glibc C++ 客体安装、升级、卸载、重启和恢复已有实验 profile 证据，冻结 newlib 入口已复验。P3 离线仓库、锁和重启回读已合入。同 glibc profile 已验证历史 P2 重放升级至 P3、冷启和中断恢复，旧 newlib 盘复制品拒绝跨 profile 升级后仍能由 P2 正常读取。 | [glibc 事务](work_log/24df429a_xypm_glibc_guest_transactions.md)、[P2](work_log/0066_xypm_p2_validation.md)、[P3](work_log/7c2de8a4_xypm_p3_preview_guest.md)、[跨版本](work_log/3ce98ac7_glibc_g4_xypm_p2_p3.md) |
| glibc | 静态 C/C++、双 Shell 管线和重定向、单终端描述符读就绪已合入。D1 验证了双高地址布局、私有入口栈和可跨 8,196 页的原生依赖映射器。glibc 已产出 1,645 成员的 PIC 归档和部分链接对象，完整解释器仍受启动门禁限制。完整 C3、动态链接和默认切换仍在验收范围。 | [双入口管线](work_log/6d49a810_glibc_dash_child_stdio.md)、[私有入口栈](work_log/51852664_glibc_d1_private_entry_stack.md)、[共享归档](work_log/8e477872_glibc_shared_io_and_pic_archive.md) |
| SDK 过渡 | 已在独立工作区将统一 glibc C/C++ SDK v2 选为应用默认，验证 C/C++ 构建、xypm profile 拒绝、v0.0.1-1024 原发行介质回退及恢复 glibc 的三次冷启。发行默认切换和 newlib 退役仍依赖最终资产清单与组合验收。 | [SDK profile 契约](contracts/xypm_sdk_profiles.md)、[v2 默认与原发行回退](work_log/4c8a56a1_glibc_v2_workspace_default.md)、[发行默认门](releases/glibc_default_gate.md) |
| 审计/整合 | A01–A04修复与PR3兼容已交付PR4 | [整合摘要](history/delivery_audit.md)，组合build76a2e4380f64fb2e，7定向组通过；非旧全量重验 |
| POSIX/Qt | 静态 QtQml 通过脚本、绑定、回收和 VM 配额负向检查。Quick 软件渲染及输入在两种 Shell 通过。独立工具包构建的外部应用已在 Mobius 与 ClarkE 共存的工作盘上验证文本、退出和资源回收。 | [QtQml](work_log/d8bd3467_qt_e18_target_qml_and_vm.md)、[Quick](work_log/13a6b397_qt_e19_quick_through_legacy_dash.md)、[同盘组合](work_log/dcbbd42a_desktop_products_combined_guest.md) |
| 许可 | 材料检查通过；newlib 1053/1053、GCC 运行库 397/407 成员映射、GNU Seed 分发审查、Qt 静态分发审查与收口材料（文本/§4d0/补丁标注）已交付 | [许可证管理](licensing.md)、[0188](work_log/0188_d7_license_two_leaves.md)、[0189](work_log/0189_d7_license_full_closure.md)；均为映射/材料审查，**非法务意见**，Qt 静态交付物已按 B4/B5 门槛随 0.0.2-1103 分发（非法务意见） |

每项资格绑定各自冻结的源码、SDK、镜像和配置。逐成员许可范围按各自审查记录追溯。

## 正在进行

| 负责线 | 范围 |
| --- | --- |
| 总协调 | 阶段计划、产品标识、公共 ABI、SDK 默认和组合验收 |
| 运行库 | GNU rtld 独立堆、首线程 TLS 与文件状态交接，范围为 glibc sysdeps 和 D1 私有 loader。另行推进 glibc dash 命令替换与 stock 安装，覆盖 shell、候选构建和应用组合。 |
| Qt 与浏览器 | Qt Quick v2 已验断网接收与双 Shell，推进 Mobius v2 Widgets 和 Curvive 分发材料。ClarkE 已构建 WebCore 软件归档，先补平台静态链接，再验收页面、CSS 布局与 Qt 视口。 |
| 身份 | Pumpkin 私有客户端、监督器与操作者工具负责在线撤销及 Mobius 会话回收。生产凭据、独立代际来源和长期资源归属继续验收。 |

[阶段计划](plans/next_stage.md)

## 下一步

- 组合候选通过 79 项常规、10 项许可材料和 50 次 glibc 客体运行。收口须从最终
  主线提交重建系统和两套 SDK，实际运行组合门禁，并将结果绑定到该源码与产物。
  [组合复验](work_log/ea2d71c6_next_stage_combined_guest.md)
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
