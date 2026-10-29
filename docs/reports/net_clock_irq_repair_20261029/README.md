# PR20 时钟、IRQ与诊断边界整改

本报告仍在交付收口；PR20保持 **CHANGES_REQUESTED / NOT_MERGE_READY**。
本轮只修既有PIT单调计数、PIC/IRQ职责及启动前诊断，不实施N2、lwIP、HTTP、VMA或新syscall。
维护者要求的完整ring-3驱动/设备授权架构尚未实施，时钟/IRQ通过不替代该门槛。

整改前[只读审计](audit.md)与[先冻结的验收计划](test_plan.md)保留原问题位置和验证边界。

## 已完成的有限实现

- `core/clock.cpp`持有唯一PIT计数；IRQ0是该后端唯一写入者。sys7/sys46、sleep/word deadline、输入时间戳、RTC elapsed、N1诊断均读同源。每进程CPU记账ticks和RTC UTC锚点保留。
- PIC/PIT移至PC平台，一次初始化位于tasks_init之后、console之前，保持IF=0；run不重编程。启动前IRQ0只推进时钟并应答，不维护或启动调度。
- 单一`platform/pc::pic_eoi`仅slave/master I/O。设备IRQ分发定义从网卡文件移至PC平台；网卡只处理自身ISR/队列。独占诊断路由只改/恢复拥有的ELCR/PIC位，不覆盖其他所有者。
- 原IRQ等待指令序列抽成窄arch helper，调度idle和诊断复用；没有第二套时钟/EOI/等待管理器。
- 默认构建不链接NIC驱动、其命令及诊断路由状态；仅`--net-boot-diagnostic`可构建原N1实验诊断。`--clock-irq-probe`只链接测试控制，默认ELF不含它。此隔离不是ring-3驱动合规声明。

## 已测候选（后续主线整合不改绑）

首次完整验收基于main `169f51e`整合后的固定代码：默认build `586fa106452724be`，
N1诊断`5556afe482d03b80`，专用探针`72515af57b2ac4d5`。
36套原行为输入回归通过：原21套（含G02全部19组及原三种媒体）、N1十项、GPU paired/failure两项、Aurora Browser离线三项。
另有13项测试内核控制、两次真实用户态clock/wait/RTC、QEMU IRQ/EOI实际跟踪505组全部匹配。
默认镜像下的dash补充采用真实恢复startup-v3的libc CRT；未授权fork和未opt-in原始CRT均先真实拒绝，失败保留，未伪造marker或放宽检查。

所有大镜像、SDK、ELF和最终工作盘保存在本工作区忽略build目录。最终资格必须单独绑定
交付时实际源码、镜像、实际ELF、SDK、QEMU命令/日志、截图及资源计数；本段旧候选不改绑。
原PR20冻结报告不改；初始介质、fixture路径、QMP socket过长、缺头/链接和权限/CRT失败均保留。
