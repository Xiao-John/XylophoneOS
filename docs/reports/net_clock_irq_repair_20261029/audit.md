# PR20整改前只读审计

2026-10-29。输入PR20 `9b832fa06061b6905d00529a2e0a8445ea389a2a`，其原工作区clean。
开工main为`169f51e6b410863b8d8c9707b7ea84a6f649d59c`；17已合入，18–23为draft/open，
reviews/threads均为空。停止N2/lwIP/HTTP/VMA/新syscall和其他功能扩张。
整改仅在`codex/net-clock-irq-repair`独立工作区；原网络和其他协作者工作区不修改。

| 机制 | 唯一负责人 | 整改前实际状态/位置 | 不合理耦合 | 最小修正 |
|---|---|---|---|---|
| PIT单调计数 | 公共clock模块，IRQ0唯一写入 | tasks.cpp:134 tick_count；:1072 monotonic_ns；:2236 timer_entry；:2286 sys_ticks；pic.cpp:8 ticks与:55 pic_ticks | 同一PIT事件两份真值；EOI顺带更新第二份 | 从tasks迁移原计数/饱和换算到core clock；所有时间读者同源；删除pic_ticks与PIC ticks |
| 每进程ticks | 调度器CPU记账 | tasks.cpp process_record::ticks，timer_entry中仅running进程加一 | 不属于重复时钟，不能误删 | 保留CPU使用统计，不能供网络deadline使用 |
| PIC/PIT初始化 | PC平台一次性系统初始化 | tasks_enter:2433/2435，virtio_net::self_test:176重复调用 | 驱动重编程全局PIC/PIT，盲删又导致pre-run无时基 | tasks_init完成后、boot console前，在IF=0时一次初始化；不隐式sti；tasks_enter不重置；诊断HLT临时接IRQ0 |
| IRQ0与调度 | arch现场/调度，platform硬件应答，clock计数 | exception vector32→timer_entry→pic_eoi→两个计数→expire/cancel→ring3 schedule | pre-run也进入调度器维护；计数依赖EOI | IRQ0明确推进clock并纯EOI；current为空的boot阶段直接返回原ring0现场，无scheduler消费者 |
| RTC墙钟 | platform/pc/rtc.cpp | RTC快照base_epoch_ns和base_monotonic_ns；tasks_enter采样，sys64计算elapsed | 语义独立，不能删除或把UTC当单调时间 | 保留原RTC采样/无RTC失败；锚定统一monotonic，run前后不重置PIT计数 |
| EOI | 单一PC PIC机制 | pic.cpp:66；timer_entry、PS2::input_irq:106、exceptions设备分支:198 | EOI内计时；不同层直接管理平台应答 | 移动现有PIC实现到PC平台，复用同一pic_eoi；纯slave/master确认，不增时间/统计 |
| 设备IRQ | PC平台固定独占诊断路由 | exceptions:197→platform::device_irq；该函数却在virtio_net.cpp:206 | 通用分发定义绑网卡文件 | 平台保存一个真实消费者的boot-only独占路由；驱动只处理自身ISR/队列，平台统一EOI；不造共享PCI框架 |
| ELCR/mask | PC平台诊断路由生命周期 | virtio_net:24保存全字节，:53恢复，:121–125设置 | 网卡拥有全局PIC/ELCR端口，整字节恢复可能覆盖别设备 | 平台只改所认领IRQ位和必要cascade位，释放只恢复所拥有位；其他设备变化保留 |
| PCI/BAR/DMA | 现有PCI映射与物理页归属 | virtio_net复用pci::find/map_bar_range和allocate/release_page | 无需新机制；reset失败仍可能DMA写 | 保留源验证、内核隔离、reset-before-reclaim/quarantine；不因本整改新建第二套PCI/DMA管理 |

所有登记工作区的src/kernel均未发现`pci_eoi`，只有已有`pic_eoi`。
全源检索未发现其他设备调用pic_init/timer_init。PS2拥有0x60/0x64设备端口，但其PIC
unmask应通过PC机制；NIC MMIO寄存器仍属设备，PIC/ELCR端口不属设备。

初始执行顺序：entry.asm CLI/BSS清零→IDT→分页/内存/显示/块设备→tasks_init创建8任务，
current/current_thread仍null→boot console(IF=0)→net-test自行PIC/PIT、sti;hlt;cli→
timer_entry ring0返回→NIC reset→run/tasks_enter再次PIC/PIT、PS2、RTC→用户IRET IF=1。
原两个计数都不在pic_init中清零；重复源及重复硬件初始化本身已是缺陷，不能以恰好同步抵消。

拟定顺序：任务结构准备完成→平台PIC/PIT一次配置(IF仍0)→console；boot诊断只认领/归还
自己IRQ并在明确HLT窗口启用中断，统一时间按实际递送IRQ0推进；console忙等IF=0期间不
承诺测量宿主经过时间。run不重编程/重置时基，PS2与RTC保留各自初始化，用户态开始
正常IRQ0抢占与deadline。RTC在run时重新采样当前UTC并绑定既有单调值，语义不变。

C28/C29已在当前main。用户本轮只授权已有诊断的职责整改，不授权新增用户驱动机制。
因此本轮不会把内核NIC改称符合C28的生产驱动；即使以下回归通过，PR20保持draft，
完整可合并裁定仍须维护者处理C28诊断范围/退出条件，绝不自行批准或合并。
