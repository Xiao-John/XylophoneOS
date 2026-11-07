# work_log 编号索引

新增记录：[0209 — DU4 P2 自动安装](0209_du4_p2_autinstall.md)。

历史存在重复编号（同号多份，主题不同）；本索引消歧可追溯性。编号唯一性规则：
**0149 之后仍发生过同号占号（见下表 0144 及以后各组），因此"自 0149 起全局唯一"
的旧表述不实；现行规则为自 0188 起编号全局唯一，新工作记录不得复用任何已有编号**
（已占用编号以目录内文件名为准，主题后缀即消歧）。

重复编号实测（2026-11-03 按目录盘点，29 组；2026-11-01 曾登记 12 组，其余为
当时漏登或其后新增）：

| 编号 | 记录 |
|---|---|
| 0062 | `0062_microkernel_principles.md` / `0062_qt_e15_preflight.md` |
| 0063 | `0063_input_edit_design.md` / `0063_qt_e15_continuation.md` |
| 0064 | `0064_input_edit_first_stage.md` / `0064_qt_e15_qualification.md` |
| 0065 | `0065_qt_e15_lifecycle_recheck.md` / `0065_terminal_editor_selection.md` |
| 0066 | `0066_input_edit_local_snapshot.md` / `0066_open_adventure_package.md` / `0066_qt_e16_qualification.md` / `0066_xypm_p2_validation.md` |
| 0069 | `0069_all_worktree_local_commit.md` / `0069_daily_utilities.md` |
| 0073 | `0073_ncursesw_design.md` / `0073_xypm_p2_remote_integration.md` |
| 0081 | `0081_fb1_fb2_fault_bundle.md` / `0081_virtio_gpu_2d_qualification.md` |
| 0082 | `0082_network_device_abi_claim.md` / `0082_shell_launch_plan.md` / `0082_utf8_sdk_candidate.md` |
| 0083 | `0083_aurora_browser_offline.md` / `0083_w1_queue_and_thread_build.md` |
| 0085 | `0085_modern_app_compatibility_phase1.md` / `0085_w1_uart_overrun.md` |
| 0086 | `0086_modern2_network_handoff.md` / `0086_newlib_utf8_surrogates.md` / `0086_principle_amendment_driver_timebase.md` |
| 0087 | `0087_modern2_px4a_design.md` / `0087_ncurses_strict_sdk_probe.md` |
| 0088 | `0088_cpython_static_pillow.md` / `0088_kernel_driver_c28_debt_register.md` / `0088_ncurses_source_material.md` |
| 0090 | `0090_modern2_runtime_probes.md` / `0090_wait_acceptance_harness.md` |
| 0112 | `0112_aurora_c30_rename_and_fixes.md` / `0112_clock_irq_split.md` |
| 0144 | `0144_ncurses_guest_probe.md` / `0144_webengine_port_plan_and_c31.md` |
| 0145 | `0145_c30_rename_b1.md` / `0145_terminal_readable_wait.md` |
| 0146 | `0146_c6_guest_requalification.md` / `0146_shell_application_handoff.md` |
| 0147 | `0147_c1_requalification_verification.md` / `0147_ncurses_locale_coverage.md` |
| 0148 | `0148_c2_c3_debts_and_localpilot_rules.md` / `0148_terminal_service_recovery.md` |
| 0149 | `0149_issue37_evidence_hygiene.md` / `0149_issue37_serial_recovery.json` / `0149_terminal_handoff_and_fault.md` |
| 0154 | `0154_c4_pivot_c5_rework_evidence_contract.md` / `0154_terminal_access_probes.md` |
| 0155 | `0155_issue37_verifier_followup.md` / `0155_ncurses_main_reconciliation.md` |
| 0156 | `0156_issue37_guest_review_gate.md` / `0156_xsh_terminal_fault_admission.md` |
| 0157 | `0157_exec_channel_preservation.md` / `0157_issue37_full_migration.md` |
| 0168 | `0168_terminal_child_protocol_isolation.md` / `0168_threading_build_jobs.md` |
| 0169 | `0169_device_authorization_a2_registration.md` / `0169_terminal_fork_service_failure.md` |
| 0170 | `0170_device_authorization_step1a.md` / `0170_ncurses_subset_delivery.md` |

本索引不改变任何历史记录内容与文件名，仅登记编号归属；历史上曾有"晚合入方改号"
方案，因会牵动被冻结清单的哈希级联而按"老人老办法"否决，过程见
[0154](0154_c4_pivot_c5_rework_evidence_contract.md)。

## 新占号登记（自 0156 起）

新工作记录取号后在此登记一行，编号全局唯一、不得复用：

| 编号 | 记录 | 说明 |
|---|---|---|
| 0156 | `0156_issue37_guest_review_gate.md` | Issue #37 客体证据复核守门（PR #59，2026-11-01 占号；同号另一份见上表） |
| 0157 | `0157_issue37_full_migration.md` | Issue #37 历史路径全量脱敏迁移（PR，2026-11-01 占号，原 0150 改号；同号另一份见上表） |
| 0158 | `0158_terminal_exec_handoff.md` | 单线程终端 exec 交接（2026-11-03 入库） |
| 0159 | `0159_channel_wait_many.md` | 通用多通道等待基础（2026-11-03 入库） |
| 0160 | `0160_w1_w2_execution_plan.md` | W1–W2 缺口核对与执行顺序（2026-11-03 入库） |
| 0161 | `0161_channel_wait_many_close.md` | 多通道等待中的对端关闭探针（2026-11-03 入库） |
| 0162 | `0162_channel_fork_pair.md` | fork 子进程的通道对派生（2026-11-03 入库） |
| 0163 | `0163_channel_fork_provenance.md` | fork 通道来源核验（2026-11-03 入库） |
| 0164 | `0164_terminal_fork_admission_plan.md` | 终端子会话登记与接收方案（2026-11-03 入库） |
| 0165 | `0165_terminal_fork_admission.md` | 试行终端 fork 子会话登记（2026-11-03 入库） |
| 0166 | `0166_terminal_libc_fork.md` | 单线程 libc 的终端 fork 交接（2026-11-03 入库） |
| 0167 | `0167_ncurses_guest_coverage.md` | ncursesw 分片输入与窗口边界探针（2026-11-03 入库） |
| 0168 | `0168_threading_build_jobs.md` | Threading build 并行度（2026-11-01 入库；同号另一份见上表） |
| 0169 | `0169_device_authorization_a2_registration.md` | 设备授权原语 A2 登记（2026-11-01 占号；同号另一份见上表） |
| 0170 | `0170_device_authorization_step1a.md` | 设备授权实施段 1a（2026-11-01 占号；同号另一份见上表） |
| 0171 | `0171_authorized_pio_boundaries.md` | COM1 授权后的 PIO 边界探针（2026-11-03 入库） |
| 0172 | `0172_w1_w2_main_reconciliation.md` | W1–W2 与主线设备授权登记整合（2026-11-03 入库） |
| 0173 | `0173_authorized_irq_wait.md` | 授权 IRQ 空队列与关闭探针（2026-11-03 入库） |
| 0174 | `0174_terminal_width_alignment.md` | 终端字符宽度对齐探查及验证计划（2026-11-02） |
| 0175 | `0175_ncurses_member_provenance.md` | ncursesw 目标归档成员来源筛查（2026-11-02） |
| 0176 | `0176_terminfo_lineage.md` | xterm terminfo 来源链与交付说明（2026-11-02） |
| 0177 | `0177_terminal_capacity_repetition.md` | 终端 fork 容量回滚重复验证（2026-11-02） |
| 0178 | `0178_channel_single_wait_close.md` | 单通道等待中的对端关闭（2026-11-02） |
| 0179 | `0179_screen_host_probe.md` | GNU Screen 宿主终端探针（2026-11-03） |
| 0180 | `0180_ncurses_invalid_input.md` | ncurses 宽字符非法输入及恢复（2026-11-03） |
| 0181 | `0181_terminfo_missing_recovery.md` | 缺失 xterm 数据与恢复（2026-11-03） |
| 0182 | `0182_combining_input.md` | 组合字符输入探针（2026-11-03） |
| 0183 | `0183_screen_evidence_freeze.md` | 宿主终端证据进入受限交付（2026-11-03） |
| 0184 | `0184_terminal_contract_reconciliation.md` | 终端契约与客体证据对齐（2026-11-03） |
| 0185 | `0185_terminal_select_contract.md` | 单终端 select 的直接客体检查（2026-11-03） |
| 0186 | `0186_terminal_input_flush_guest.md` | 已排队输入的清空与新输入（2026-11-03） |
| 0187 | `0187_w1_final_acceptance.md` | W1/ncurses 最终验收（组合源码重建 + 全量客体门槛，PR #66，2026-11-03） |
| 0188 | `0188_d7_license_two_leaves.md` | D7 许可两叶 + 发版前小更改与 README/版本更新（2026-11-03 占号） |
| 0189 | `0189_d7_license_full_closure.md` | D7 许可面收口（Qt 文本/§4d0 材料/补丁标注、GCC 运行库映射、发版中止）（2026-11-03 占号） |
| 0190 | [Midnight Dock refinement](0190_aurora_midnight_dock.md) | Dock guest qualification (PR #45) |
| 0191 | `0191_browser_ssg_fragments.md` | Browser SSG fragment integrity（PR #44） |
| 0192 | `0192_ssg_p1_cross_process.md` | SSG-P1 cross-process prototype（PR #46） |
| 0193 | `0193_ssg_p2_diagnostic.md` | SSG-P2 Browser diagnostic（PR #47） |
| 0194 | `0194_ssg_notes_range_review.md` | Notes range review（PR #48） |
| 0195 | `0195_ssg_p2f_structure_oracle.md` | SSG P2F structure Oracle（PR #49） |
| 0196 | `0196_ssg_p3b_dual_provider.md` | SSG P3B 双 Provider 聚合与隔离（PR #50） |
| 0197 | `0197_ssg_p3c_engine_neutral_watch.md` | SSG P3C engine-neutral watch（PR #51） |
| 0198 | `0198_tech_debt_c30_c7_c4.md` | 技术债清偿：file_client 改名、C7 去重、C4 放掉 |
| 0199 | `0199_gnu_notice_gfdl.md` | GNU NOTICE/GFDL 组件登记与客体许可装盘（关闭 gnu_notice_coverage_gaps） |
| 0200 | `0200_gcc_member_manual_rulings.md` | GCC 运行库 10 未映射成员人工裁定（关闭 gcc_runtime_member_mapping_unresolved） |
| 0201 | `0201_qt_text_coverage.md` | Qt 262 成员文本覆盖核对（关闭 qt_license_text_member_coverage） |
| 0202 | `0202_release_prep_ab.md` | 发版前置 A/B：清障构建 + Qt 打包核验与安全审查 |
| 0203 | `0203_release_packaging.md` | 0.0.2-1103 打包：cpython/daily/idna/make/xypm 装配与 release_smoke 11/11 |
| 0204 | `0204_release_publish.md` | 0.0.2-1103 发布（tag/release/回执）+ playbook + release_pipeline.sh |
| 0207 | `0207_du4_bundle_foundation.md` | DU4 前期：XOSBND1 契约/生成器/客体识别 |
| 0208 | `0208_sl0_shell_launch_contract.md` | SL0：双 Shell 启动/权限继承契约与双轨兼容表冻结 |
| 0209 | `0209_xypm_sdk_host_backend.md` | XYPm SDK host backend 随包、缓存移出 SDK、profile 哈希稳定与 release smoke 门 |
| 0210 | `0210_xypm_profile_alignment.md` | XYPm b2 profile 对齐；local profile 对发行盘明确拒绝 |
| 0211 | `0211_cpp_link_clock_harness.md` | C++ 链接误判、guest `_times` 修复、串口驱动 partial flush、盲测技术债 |
| 0212 | `0212_file_service_found_bug_fixes.md` | 文件服务 found_bug 15 项修复：逻辑偏移、零填充、rename 替换、路径解析、spawn 动作、transfer 授权 |
| 0213 | `0213_second_bug_hunt_fixes.md` | 第二轮 bug-hunting：spawnp/路径 255 字符边界、JSON INT64_MIN、diskio 64 位回绕、erase_last 注释 |
| 0214 | `0214_bundle_installer_hardening.md` | 第三轮 bug-hunting：XOSBND1 填充/类型/名称校验、客体安装器魔法与目标摘要、host 工具缓存加固 |
| 0215 | `0215_s2_bug_hunt_fixes.md` | Season-2：安装预检/marker 身份/幂等 ensure、rename 恢复、readdir 点项、ISO/缓存加固 |
