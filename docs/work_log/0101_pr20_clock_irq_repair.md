# 0101 PR20：PIT时钟、IRQ与启动前诊断职责整改

2026-10-29。用户暂停功能扩张，要求先只读审计再修PR20。独立工作区
`XylophoneOS-net-clock-irq-repair`，分支`codex/net-clock-irq-repair`，从PR20
`9b832fa`开始；原网络/其他协作者工作区不修改。先同步main `169f51e`，交付前
重新核对PR17–23与review后整合main `3377dbf`，保留双方state/许可证与真实作者。

## 范围与实现

只读审计先锁定tasks与PIC的两个PIT计数、EOI副作用、Net/tasks重复PIC/PIT初始化、
通用device_irq定义绑Net，以及Net直接操作/全字节恢复ELCR/PIC。审计、先冻结的
断言、原始失败和[完整报告](../reports/net_clock_irq_repair_20261029/README.md)均保留。

权威计数迁到core clock；IRQ0显式推进并交PC纯EOI，boot阶段不运行调度维护；
系统在tasks_init之后、console之前一次配置PIC/PIT但不隐式开启IF，run不重置。
设备分发及单一独占诊断route归PC平台，只恢复拥有的位；Net仅处理自身ISR/队列。
已有HLT序列抽成窄arch helper供scheduler与诊断复用。每进程CPU ticks、RTC UTC锚点、
PCI映射/DMA配额与reset/quarantine机制保留；无新syscall/SDK能力。

为缩小C28范围，默认构建不链接Net诊断、命令及诊断route状态；现有硬件实验仅在
显式`--net-boot-diagnostic`构建中保留，测试控制仅`--clock-irq-probe`。这不是ring-3
驱动移植，不能替代维护者对PR20的CHANGES_REQUESTED，也不自行批准/合并。

## 实际验证

最终默认/诊断/探针build为`919bd09bb69b6e0f` / `2ef23d2706818868` /
`96c3a71ea876dbcf`；联合连贯性build `288d715bc351e2a2`，故障profile另列。
每个profile重新构建并核对718个源码输入、SDK/所有产物。QEMU11.1.2、TCG、
pc-i440fx-10.0、单CPU、512MiB；完整命令与工具/镜像/ELF SHA在报告。

- 36套新运行通过：原21套、N1十项、GPU两项、原Browser离线三项。原G02全部19组
  及三种原媒体实际重跑；旧报告从未改绑。原Qt SDK1054项产物/原来源逐字节重核。
- 内核13个控制和两次真实clock/sleep/word deadline/RTC调用通过；probe资源精确回到
  `130278/2/0`。相同客体真实Net两轮32帧后由boot3 tick到用户态117 tick，回到`130269/2/0`。
- QEMU侧实际IRQ/EOI trace487组全部匹配，含IRQ0/10/1/12，EOI内无新增时间或统计。
- dash使用真实startup-v3 libc CRT补验，回到`130279/2/0`；未授权fork、原始非exec CRT拒绝
  与初次whole-archive链接错误保留。未伪造marker或放松权限/装载检查。
- 默认ELF无Net/诊断route/探针符号，默认console测试命令真实unknown。真实截图已查看。

初期完整实验镜像超出旧legacy窗口、QMP长路径、Browser fixture源路径、缺头等原始
失败保留；修的是输入/环境/真正CRT选择，未改变原行为断言。最终默认剔除诊断代码后
恢复原legacy容量，全部原媒体重跑；诊断file ISO资格独立。最终工作盘保留本地并摘要。

## 尚未完成

PR20完整用户态驱动/通用设备授权验收仍BLOCKED；修订PR18撤回旧112 frame-proxy，
不能视作已实现可调用。共享IRQ、SMP、真机/IOMMU、wedged-reset故障注入、长压力、
完整发行均NOT_RUN。Browser输入只是旧冻结消费者在新系统的回归，不是新应用修复资格。
本轮未推进N2/lwIP/HTTP/Chromium/VMA、新syscall或LocalPilot，未改宿主代理/连接/日常包。
默认与诊断范围的后续合入裁定由维护者review决定；测试通过不替代架构审查。
