# XOS 当前状态

2026-10-29。本次GPU后端整合同步的远端 main 为 `85120a7`；E17/Aurora PR #13
已由维护者合入，FB0故障包勘查与音频计划也已保留。当前组合继续保留日常工具、
UTF-8文件名、游戏及ncursesw前期探针。新增整合资格限于0081的21套定向检查；
其他旧资格仍绑定原输入，不构成全系统重验。发布资产仍为0.0.1-1026，未更新Release。
原则裁决见[xos_plan.md第一部分](xos_plan.md#第一部分设计原则)，本页只登记事实与占用。

## PR批次整合交付（2026-10-29）

#18/#21/#22/#23/#25/#27已合入，#19修复随本次PR交付；#20保持RC且未合并。
旧112网卡帧代理认领撤回，设备授权仍未登记/实现；67仅VM提案认领。
当前浏览器修复的宿主检查通过，Qt目标编译/新客体导航和新探针组合guest尚未运行。
Pillow线程故障根因仍未解，不授予线程/LocalPilot/发行资格。详见[0100](work_log/0100_pr_batch_delivery.md)。
本组无公共build占用，旧冻结证据保持原样；以下任务/历史节保留其各自时点和输入。

## Aurora Browser PR #19 审查修复（待客体验证）

同步 main `3e5ccd0` 后修复 HTTP host 分量校验及浏览器失败导航状态；宿主 parser
ASan/UBSan 定向检查通过。新增图形交互回归尚未运行，不能沿用旧镜像资格；
具体冻结输入、执行情况和后续见[0096](work_log/0096_browser_review_fixes.md)。
临时视图加载期间同时保留新旧页面，峰值内存未测；不占公共 build。

## Aurora Browser B0/B1：受限本地 HTML/CSS

2026-10-29，独立 `codex/aurora-browser-b1` 从 upstream `39083f9` 实施真实 liteHTML0.9/
Gumbo + Qt6.8.3 QPainter/Aurora 浏览器；B0目标交叉编译/链接通过，B1受限客体本地页面、
PS/2链接、地址/历史/刷新/滚动、单窗口标签及书签、坏输入与资源回收通过。
新系统build `3fb1bb7d6b9e7bf9`；来源、失败和边界见[0083](work_log/0083_aurora_browser_offline.md)。
无新内核/ABI/Qt底座变更。网络尚未接入，B2 BLOCKED；HTTPS/JavaScript/互联网及完整
现代浏览器均未通过。仅本地32KiB有界HTML/CSS/BMP子集，不发布Qt静态产品或Release。

## Modern Platform运行时探针（PR #25）

本分支保留Promise完成/pending/rejection等冻结探针结果，Web/应用能力仍BLOCKED。
已同步当前main；已整合PR #21共用的QuickJS构建/runner与许可，保留phase2 Promise语义及phase1入口兼容；
旧结果不改绑新组合。范围和未验项见[0099](work_log/0099_probe_branch_reconciliation.md)。

## N2用户态网络接续（当前规范）

2026-10-29。旧frame-proxy路线已废止；当前接续以[网络交接](plans/network_handoff.md)为准，
按C28用户态驱动、C29统一管理的时间域实施。旧冻结审查包保留原时点，N2继续BLOCKED。
本轮同步main并修改活文档，无新ABI/实现或客体资格；见[0097](work_log/0097_network_time_domains.md)。
本组无源码/公共build占用。

## PR #23时间域契约同步

匿名VM提案已同步当前C29；不再要求时间中断唯一写入，V1–V7仍NOT_RUN。
无新实现或追加ABI，见[0098](work_log/0098_vm_time_domains.md)。文档占用解除。

## 时间域与驱动边界修订（文档PR）

2026-10-29，`codex/time_domains_docs` 基于远端0ec0ad6：C28澄清内核基础设施和存量整改，
C29约束统一时间管理、显式时间域及EOI职责；专项契约给出禁止/允许案例和审查清单。
仅文档，无新ABI、实现或客体资格，见[修订交接](work_log/0095_time_domain_amendment.md)。
本组文档占用解除，不占公共build；其他分支未合入本PR。

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

## Modern Platform Phase 2 / Python 静态 Pillow：受限核心通过，并发阻塞

2026-10-29，`codex/python-static-imaging`，独立工作区/build/cache。
原始Pillow11.3.0核心静态注册和原包stage；最终系统ec4b7ffa0c53f5a4，
xsh/dash单线程像素/PNG/BMP、防护拒绝、错误/恢复与精确回收通过。
**Pillow线程使用UNSUPPORTED/BLOCKED**：保留真实dash worker newlib `_malloc_r`
vector14；最终有限对照未复现，未修复或建立线程资格。
无ABI/内核/libc修改；LocalPilot原API/安全主体/Operator/UNKNOWN及N2仍未验收。
范围、原始失败/来源/命令和证据见[0088](work_log/0088_cpython_static_pillow.md)。
公共文件由Python兼容线维护，独立PR交维护者审查；未修改其他工作区或正式安装。

## PX4-A 匿名虚拟内存：独立设计认领（未实施）

2026-10-29，`codex/px4a-vma-claim` 从 fetched upstream `aaec2e9` 建立。
本组负责 `docs/contracts/anonymous_vm.md`、ABI 67 的 claimed 提案、PX 路线和
`docs/reports/modern2_px4a_20261029/`；共享头、dispatch、SDK、内核和旧证据不改。
具体认领须由维护者审查合入后才能实施；本分支不是全项目登记，运行资格仍 **BLOCKED**。
后续已同步PR #28的受管理时间域契约，禁止VM私建时基替代系统deadline；
未改原aaec2e9源码审计或回执，未重绑旧测试，未实施公共时基/VM。
独立 `build/modern2_px4a/` 仅作源码审计，不构建/运行新客体。旧网络112认领已由 PR #18 撤回，设备授权另登记。

## 正在进行：Browser Foundation 的独立网络/浏览器工作

2026-10-29，旧 `sys_net_device` 112 帧代理认领已撤回；[通用设备授权设计](contracts/network_device_v1_proposal.md)
仅供审查，不认领编号或实现。C28要求VirtIO初始化、队列和收发在用户态，内核仅提供受控
MMIO、DMA、IRQ、撤权等通用机制；停止不可确认时隔离DMA页。未来登记和真实guest验收前
网络接入仍BLOCKED；旧N1及隔离探针只属于原冻结输入，不是新架构资格。历史与修正见
[0082](work_log/0082_network_device_abi_claim.md)。

## 正在进行：ncursesw W0/W1

2026-10-30：本分支正整合本地 main `3377dbf`。C28 要求设备数据通路在用户态；
本分支新增的内核 UART IRQ 接收与队列不符合该原则，必须迁移到受控用户态驱动，
不能以调试例外作为交付依据。设备端口授权、IRQ 交付和撤销还需补齐；不得以当前
构建或既有主线调试串口证据宣称 W1/W2 通过。详见[0114](work_log/0114_w1_main_reconciliation.md)。
新增内核 UART IRQ 数据通路已撤回，sys80 claim 暂时不可用，见[0115](work_log/0115_w1_c28_irq_withdrawal.md)。
x86 TSS 已准备默认全拒绝的 I/O bitmap，尚无授权/撤权或 guest 资格；详见
[0116](work_log/0116_x86_io_bitmap_foundation.md)。
进程切换和成功 exec 的位图重装基础见[0118](work_log/0118_pio_context_foundation.md)。
sys82 COM1 窄 PIO 授权及调试串口脱离已在本分支实现，边界见[pio_grant](contracts/pio_grant.md)，
构建及限制见[0120](work_log/0120_com1_pio_handoff.md)；尚无救援或客体验收。
sys83 的受控 IRQ4 事件已在本分支实现，契约见[irq_event](contracts/irq_event.md)，
构建和未验范围见[0122](work_log/0122_irq_event_mechanism.md)；尚无客体验收。
用户态 COM1 驱动类的初始实现见[0123](work_log/0123_user_uart_driver.md)。
用户态终端服务、控制客户端及加载器启动前回调的基础已构建，尚未实际启动或接入
应用会话；限制和证据见[0124](work_log/0124_terminal_handoff_foundation.md)。
服务接收线程故障现会关闭控制通道以唤醒等待者；仅宿主模拟和构建验证，见
[0125](work_log/0125_terminal_failure_wakeup.md)。
控制协议现有有限截止时间读取的初始实现，尚无应用会话或客体验证；见
[0126](work_log/0126_terminal_timed_read.md)。
终端通道现对允许的伪唤醒重新检查和等待，仅宿主模拟验证，见
[0127](work_log/0127_channel_spurious_wakeup.md)。
控制接收线程与有界 mailbox 支持读取等待期间接收新请求，试行协议及限制见
[0128](work_log/0128_terminal_control_interrupt.md)；尚无客体验证。
读取/中断的服务源码已获得有限宿主线程模拟覆盖；常规 Xsh 仍未切换，见
[0129](work_log/0129_terminal_service_host_probe.md)。
COM1 显式解除隔离并重新授权的基础已实现，尚无完整服务重启或客体验证，见
[0130](work_log/0130_com1_reauthorization.md)。
独立 supervisor 交接探针与测试镜像已能构建，尚未运行客体，见
[0131](work_log/0131_terminal_guest_probe.md)。
用户态驱动已有发送就绪中断等待的初始实现，尚未客体验证；见
[0132](work_log/0132_terminal_write_wait.md)。
Xsh 所需的 supervisor 进程内终端桥接入口已构建但默认未启用，不包括子进程 stdio；
宿主模拟及限制见[0133](work_log/0133_xsh_terminal_bridge.md)。
终端服务已有单应用受认证通道的初始接入，尚未完成应用 stdio/termios 或客体验证；
见[0134](work_log/0134_terminal_application_channel.md)。
应用侧已具备内核通道身份核对与有界读写客户端；见
[0135](work_log/0135_terminal_application_client.md)。
试行 startup2 扩展现可为显式 opt-in 的应用传递受认证通道句柄；
构建与未验边界见[0136](work_log/0136_terminal_startup_handoff.md)。
单线程 libc 的初始终端 fd 已试行接入，fork/exec 和多线程 profile 仍明确拒绝；
构建与未验边界见[0137](work_log/0137_terminal_libc_stdio.md)。
终端服务已试行原始模式及有限 VMIN/VTIME 读取；
见[0138](work_log/0138_terminal_mode_foundation.md)。
单线程 libc 现有受限原始 termios 映射；0139 中的 ncurses 归档为空，已更正，见
[0139](work_log/0139_termios_raw_ncurses_probe.md)及[0142](work_log/0142_ncurses_target_archive.md)。
严格 UTF-8 候选与有效 ncursesw 库、两个消费者已交叉链接，客体和发行资格仍未完成。
已用同源 ncurses 6.5 宿主工具生成匹配目标目录布局的单一 xterm terminfo 候选；
目标读取和宿主交互尚未验证，见[0143](work_log/0143_ncurses_xterm_terminfo.md)。
隔离的双消费者客体探针已运行：宽字符输出到达输入阶段，首次方向键读取失败；
重入探针未运行。输入绑定、检查范围和未完成项见[0144](work_log/0144_ncurses_guest_probe.md)。
试行终端可读等待和单终端读取 `select` 已在提交后通过两个受限 ncurses 客体探针；
范围和剩余验收见[0145](work_log/0145_terminal_readable_wait.md)。
Xsh 桥接已增加应用建进程时的附加、回收及停止入口，专用 supervisor 经该入口运行
两个 ncurses 探针通过；真实 Xsh 尚未切换，见[0146](work_log/0146_shell_application_handoff.md)。
扩展的 UTF-8、组合字符、功能键和限时读取探针已在提交后客体通过；
见[0147](work_log/0147_ncurses_locale_coverage.md)。
桥接已实现受限显式服务重连，无应用附加时的故障注入客体检查通过，见
[0148](work_log/0148_terminal_service_recovery.md)。
独立 W1 交接客体探针四组通过；应用持有会话时的服务故障限定探针通过，
见[0149](work_log/0149_terminal_handoff_and_fault.md)。
真实 Xsh 新增显式 `tty-run` 前台入口，保持默认旧启动路径；三个受限应用的客体运行已通过，
见[0150](work_log/0150_xsh_tty_run.md)。
Xsh 空闲时的终端失效重连及桥接短写处理已实现，受限真实故障注入通过，
见[0151](work_log/0151_xsh_terminal_recovery.md)。
ncursesw 组合 SDK 与 xterm 数据候选已生成，独立消费者经真实 Xsh 的受限客体检查通过；
见[0152](work_log/0152_ncurses_sdk_candidate.md)。
用户态驱动已试行按 TEMT 确认发送排空，尚未客体验证；见
[0140](work_log/0140_terminal_drain.md)。
输入清空和 `TCSAFLUSH` 已试行实现，连续输入失败可能已丢弃部分硬件字节，尚未客体验证；
见[0141](work_log/0141_terminal_input_flush.md)。
用户态 UART 的 PIO、IRQ 与 COM1 调试通路交接提案见
[uart_user_driver_proposal](contracts/uart_user_driver_proposal.md)，为早期设计提案，具体
现状以 PIO/IRQ 契约及上述工作记录为准。

W0 勘查和 W1 [工作契约草案](contracts/terminal_w1.md)已开始；W0 未冻结，W1 未
实现或验收。终端 ESC、输入所有权、UART 等待与 newlib 多字节缺口见
[0074](work_log/0074_ncursesw_w1_scout.md)。本组无新 ABI 或公共 build 占用；用户要求
所有相关改动提交后再验收。

前期缺口已开始：隔离多字节 newlib 的 single/threaded 候选已构建，ncurses 配置/编译
探针复现终端头缺失；均非客体验收或新 SDK 资格。终端机制分层见工作契约，具体证据与
后续见[0075](work_log/0075_ncursesw_preliminary_gaps.md)。当前无源码/文档/build 占用。

多字节候选配合重新编译的 XOS libc 适配层已在隔离目录交叉链接 locale 探针；
仅为构建证据，运行及线程 profile 尚未验证，详情见[0076](work_log/0076_utf8_link_probe.md)。

2026-10-29 在最新 main 基础上生成了隔离的单线程多字节 SDK 候选并交叉链接独立
locale 探针；它仍未在客体运行，线程 SDK 和终端服务/等待机制仍待实现。
构建输入及边界见[0082](work_log/0082_utf8_sdk_candidate.md)。
输入队列的实现及宿主、交叉编译检查见[0083](work_log/0083_w1_queue_and_thread_build.md)；
它尚未连接 UART、中断或终端服务，不是 W1 客体验收。
匹配线程 C++/unwind 的多字节候选已构建并交叉链接探针，同样尚未进行客体验证。
原串口 IRQ4 接收、有界队列及硬件 overrun 内核观测尝试见[0084](work_log/0084_w1_uart_irq.md)
和[0085](work_log/0085_w1_uart_overrun.md)；新增内核数据通路已因 C28 撤回，用户态
驱动和丢失观测仍未实现。
newlib UTF-8 代理码点输入与 UCS-4 输出的源码缺口已在隔离候选中修补，探针仅交叉
链接，尚未运行；来源、许可与边界见[0086](work_log/0086_newlib_utf8_surrogates.md)。
ncurses 6.5 锁定源码已重新取得；使用该新 SDK 的探针仍因终端头缺失而失败，见
[0087](work_log/0087_ncurses_strict_sdk_probe.md)。
ncurses 候选源码锁和上游许可材料已登记，探针现在核整个 SDK 树及锁文件；目标库仍
未构建，详见[0088](work_log/0088_ncurses_source_material.md)。
sys54 管道显式截止时间已实现但未客体验证，console IRQ 等待已撤回；前台独占及
模式仍未实现，详见[0089](work_log/0089_explicit_input_wait.md)。
相关的受限客体测试入口已准备但未运行，范围与未覆盖项见[0090](work_log/0090_wait_acceptance_harness.md)。
W1 的 sys80 独占字节流读取权尝试见[0092](work_log/0092_stream_lease_mechanism.md)；
因 C28 迁移，claim 暂时返回 unsupported，不能启用。用户态终端服务、模式恢复和
救援入口仍未实现，目标契约见[stream_lease](contracts/stream_lease.md)。
通用 IPC 通道 sys81 已在本分支实现，会话、等待契约见[channel](contracts/channel.md)，
构建与未验范围见[0094](work_log/0094_generic_channel.md)；尚未跨分支同步或客体验收。

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
- 67–79 内存、84–95 等待/信号、96–111 显示扩展仍仅预留，具体接口先登记；
  本分支 sys80–83 尚未验，合并前须核验其他分支分配。
- 按 Discipline→本页→宪法→专项契约/登记接手；新开发独立分支/PR交付，
  公共 build 排他，localpilot 隔离。

## 正在进行：通道定向验收入口

2026-10-30，主 agent 独占 tests/w1_wait_smoke.py、channel_probe.cpp 与本组文档；
补齐通道负向探针和可执行入口，无新 ABI、无内核修改。不占用公共 build。

通道入口和负向断言已补齐并交叉链接，见[0113](work_log/0113_channel_acceptance_entry.md)。
客体未运行；需先完成 W1 相关提交/宪法与 ABI 整合，再新构建并运行。
本组源码占用已结束，无公共 build 占用。
## 现代应用兼容平台第一阶段：受限探针交付，N2阻塞

2026-10-29，Codex 在独立 `codex/modern-app-phase1` / worktree
`XylophoneOS-modern-app-phase1`，基线 upstream `39083f9`。占用
`scripts/modern_apps_*`、`tests/modern_apps_*`、`tests/fixtures/modern_apps/`、
`docs/reports/modern_apps_20261029/`、独立兼容报告及工作记录0085；私有build。
本轮只由本负责人汇总本分支state；未修改其他工作区、内核、ABI、Qt/Aurora或N1驱动。
PR #18/#19/#20 当前Draft/open且无review；#18未审查合入，N2公共设备桥接
实施BLOCKED。已交付真实SDK/客体依赖探针、固定源码审计和独立QuickJS解释器试验；
最终build `a538733bd3b8e43f`，11项测试器断言通过（含正确复现应用失败），Python16项中4通过/12失败，
资源均回到free130290/tasks2/completions0。完整现代浏览器、Core/API、Code与HTTPS未通过。
三份独立报告、N2门槛、原始失败和接续见[0085](work_log/0085_modern_app_compatibility_phase1.md)。
不合并上游，不改发行版，不引入第二套LocalPilot Runtime；本组公共文件/build占用释放。
