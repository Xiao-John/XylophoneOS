# XOS 当前状态

2026-10-29。本次GPU后端整合同步的远端 main 为 `85120a7`；E17/Aurora PR #13
已由维护者合入，FB0故障包勘查与音频计划也已保留。当前组合继续保留日常工具、
UTF-8文件名、游戏及ncursesw前期探针。新增整合资格限于0081的21套定向检查；
其他旧资格仍绑定原输入，不构成全系统重验。发布资产仍为0.0.1-1026，未更新Release。
原则裁决见[xos_plan.md第一部分](xos_plan.md#第一部分设计原则)，本页只登记事实与占用。

## 正在进行：Modern Platform Phase 2，独立并行范围

2026-10-29，已fetch upstream `aaec2e9`（PR #17合入）。PR #18–#21仍draft/open，
没有维护者review，N2保持BLOCKED。网络交接、PX4-A认领、Pillow静态集成及本分支
运行时缺口探针各自独立worktree/build/PR；公共ABI不跨线实施。
本分支`codex/modern2-runtime-probes`只占用`scripts/modern2_*`、QuickJS probe builder/
fixtures、`tests/modern2_runtime_guest.py`、自身reports/state/work_log0090与许可登记。
不改内核/SDK/文件服务或原LocalPilot。阶段事实见[运行时报告](reports/modern2_runtime_20261029/README.md)。

## FB1/FB2 应用故障包（受限通过）

2026-10-29，`codex/fb2-offline-symbols` 基于已合入FB0和VirtIO-GPU的主线 `39083f9`。
受限 FB1/FB2 已在 build `32fe73250f191e04` 完成真实客体生成、sync/重启、导出
和宿主符号定位；正常退出、无熵、配额、满盘、真实块写失败和路径替换各有定向证据。
格式与使用见[FB1/FB2实施](implementation/fb12_fault_bundle.md)，验证见
[0081](work_log/0081_fb1_fb2_fault_bundle.md)。更新后的组合 build `f87bebabb97dc166`
在xsh和dash完成定向验收；无新增内核ABI。
当前覆盖xsh及dash经显式诊断入口启动并等待的文件ELF；并发配额原子性、全局收集、寄存器/栈、
任意断电安全和完整压力未验，不将受限结果扩大到FB3/FB4。

## FB0 应用故障包勘查（受限通过）

2026-10-29，`codex/fb0-scout` 完成单一wait、装载/文件链路勘查、[v1格式冻结](implementation/fb0_fault_bundle_contract.md)
与真实客体探针。正常系统build `6c2e83dfaa2737bb` 中，装载器同一读句柄ELF SHA-256、
wait单次消费、满盘和真实块写错误已验证；独立故障注入build `084024c841126499`
验证文件服务进程退出时在途/后续请求分别返回-8/-7。详细范围与证据见[0080](work_log/0080_fb0_fault_bundle.md)。
生产报告器/解析器、全局收集、寄存器/栈快照、断电安全均未实现/未验；无新ABI或
公共build占用。下一步是FB1，不把FB0探针冒称生产功能。

## 应用故障包与音频计划（仅文档）

2026-10-29，用户要求的[应用故障包](plans/app_fault_bundle.md)与
[音频输出](plans/audio_output.md)两份计划已编写，分别定义 FB0–FB4 与 AU0–AU5。
故障包首版复用父进程单一wait结果；音频先PC Speaker单音，PCM独立后续。
音频仅文档；故障包进度以本页FB0节为准。无新ABI，不改变既有主线排期。
范围、验证与接续见[0079](work_log/0079_fault_bundle_audio_plans.md)。

## E17 / G05 Qt Widgets 与 Aurora Glass

2026-10-29，从 upstream `c39cef1` 的独立 `codex/qt6-e17-widgets` 完成真实 Qt
Widgets 6.8.3、可复用 `libXosAurora.a` 与单全屏图形编辑器。G05 **PASSED（受限功能）**；
实际打开、PS/2 编辑/选择/滚动、保存/sync/重启字节比对、错误与回收有独立客体证据。
来源计划 PR #12 开工时 Draft/open，未合并；实现不重带其规划文件。
冻结输入、失败、许可边界和性能见 [0078](work_log/0078_qt_e17_aurora_qualification.md)。
私有 worktree/build；不改通用 ABI、内核、文件服务、libc 或终端/xypm。
保存提交错误为 UNKNOWN，不承诺任意失败/断电事务安全；不发布 Qt 静态产品/新 Release。
本轮因上游无写权限，按用户最新指令通过独立功能 PR 交付，不自行合并。

## VirtIO-GPU 2D 可选后端：受限客体资格通过

2026-10-29，独立 `codex/virtio-gpu2d` 已同步 upstream `85120a7`；
在最终整合镜像 `c8bdc86d5bbc2629` 重建并通过21套定向检查。
FB0计划/测试与原E17事实均保留，运行时和公共ABI没有跨线修改。
真实 modern VirtIO PCI、split queue、内核自有 scatter DMA、2D资源/scanout/
transfer/flush、dirty region、设备reset及VBE回退；同Qt帧的1,440,000个RGB字节
与VBE及客体QImage完全一致。证据与边界见[0081](work_log/0081_virtio_gpu_2d_qualification.md)。
不新增 syscall/display wire，不授予用户MMIO/PCI IO/DMA，不改Qt/libc/文件/终端/xypm。
固定473个DMA页属平台显示生命周期；不是逐客户端分配，也不是3D/Qt绘制加速。
仅QEMU/单核/800×600受限通过，运行期设备失效后透明恢复、热插拔、SMP/真机未验。
私有 worktree/build；通过独立功能PR交付，不自行合并main或改旧Release。

## 正在进行：ncursesw W0/W1

W0 勘查和 W1 [工作契约草案](contracts/terminal_w1.md)已开始；W0 未冻结，W1 未
实现或验收。终端 ESC、输入所有权、UART 等待与 newlib 多字节缺口见
[0074](work_log/0074_ncursesw_w1_scout.md)。本组无新 ABI 或公共 build 占用；用户要求
所有相关改动提交后再验收。

前期缺口已开始：隔离多字节 newlib 的 single/threaded 候选已构建，ncurses 配置/编译
探针复现终端头缺失；均非客体验收或新 SDK 资格。终端机制分层见工作契约，具体证据与
后续见[0075](work_log/0075_ncursesw_preliminary_gaps.md)。当前无源码/文档/build 占用。

多字节候选配合重新编译的 XOS libc 适配层已在隔离目录交叉链接 locale 探针；
仅为构建证据，运行及线程 profile 尚未验证，详情见[0076](work_log/0076_utf8_link_probe.md)。

## 2026-10-28 历史整合与交付（保留记录）

本轮用户明确要求解决冲突后直接 push main，作为此次整合的交付例外，后续仍按 PR 流程。
四个工作区均检查；本地未提交 ncursesw 契约/探针先保存为 6403fb9，同期新增链接探针一并
保存。远端 main 合并后解决六处冲突：五处文档、一处 xsh 测试预期。保留真实 UTF-8 路径
行为和 ncursesw/nano 方向，同时接入 Qt G04 与 P2 事实；未覆盖一侧来消除冲突。
检查及交接见[0077](work_log/0077_full_remote_integration.md)。公共 build 未占用。

## 当前分支能力与证据

| 面 | 实际状态 | 证据入口/边界 |
|---|---|---|
| 发行 | 1026已发布，源码db5b46c/build7a4668477d7323de；smoke11/11、许可材料7份 | [不可变回执](releases/release_0_0_1_1026.json) |
| 核心/工具链 | E01–E08受限功能；原生GCC/G++开发已验，post5 P1仍partial | [E01–E07](history/e01_e07.md)、[E08](e08.md)；系统重建/自举未验 |
| 线程 | T0–T2、T3-PY与PY2专项已有证据 | [线程资格](reports/threading_20261025/qualification.json)；Qt QThread受限实测，SMP未验 |
| Shell | dash C1–C3受限通过，xsh保留默认 | [C3资格](reports/dash_c3_20261026/qualification.json)，build2f7160b7d6633ee6；无完整信号/作业控制 |
| 显示/ISO | sys65/66 在 buildef83c9fc92217380 重验 G02 19组通过 | [当前报告](reports/qt_e16_qualified_20261028/g02/report.json)、[显示历史](history/boot_display.md)；QtGui/QPA 单全屏 raster 已验 |
| CPython | PY0–PY2/T3-PY、A1–A3、B1–B4专项通过 | [用户态摘要](history/userland.md)；B2–B4系统6251d26b611a388d，Python11c39c52e451a9499450 |
| xypm | P2原生验证、事务和启动恢复已实现；限定范围内验收通过 | [包计划](plans/packages.md)、[0066](work_log/0066_xypm_p2_validation.md)；P2验收范围和局限见记录；P3未完成 |
| 审计/整合 | A01–A04修复与PR3兼容已交付PR4 | [整合摘要](history/delivery_audit.md)，组合build76a2e4380f64fb2e，7定向组通过；非旧全量重验 |
| POSIX/Qt | PX0子集文档已有；QtCore 6.8.3 G01/G03 与 QtGui/QPA G04 受限客体功能通过 | [PX路线](plans/posix.md)、[E16资格](reports/qt_e16_qualified_20261028/qualification.json)；Widgets/G05 已受限客体验证，见0078；QML/Quick、绝对峰值/发行许可未完成 |

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
- Qt E16/G04 已经 PR #9 合入，使用可 join 的输入线程与 QtCore wait-word 分发器；
  只验单独占全屏 raster。E17 Widgets/G05 已受限通过，E18 QML 独立推进；完整成员许可、静态分发、
  绝对峰值和本次新组合客体资格尚未完成。
- 输入编辑按[第一档](plans/input_edit_foundation.md)、[第二档](plans/terminal_editor.md)及
  [多语言](plans/multilingual.md)继续；先设计[ncursesw 公共底座](plans/ncursesw.md)，
  再优先评估 nano，kg 为备选。尚未实施或验收；相关改动提交后再验收。
- 67–79 内存、80–95 等待/信号、96–111 显示扩展仍仅预留，具体接口先登记。
- 按 Discipline→本页→宪法→专项契约/登记接手；新开发独立分支/PR交付，
  公共 build 排他，localpilot 隔离。
