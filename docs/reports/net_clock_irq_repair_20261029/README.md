# PR20 时钟、IRQ与诊断边界整改

本轮有限整改已完成；PR20保持 **CHANGES_REQUESTED / NOT_MERGE_READY**。
本轮只修既有PIT单调计数、PIC/IRQ职责及启动前诊断，不实施N2、lwIP、HTTP、VMA或新syscall。
维护者要求的完整ring-3驱动/设备授权架构尚未实施，时钟/IRQ通过不替代该门槛。

整改前[只读审计](audit.md)与[先冻结的验收计划](test_plan.md)保留原问题位置和验证边界。

## 已完成的有限实现

- `core/clock.cpp`持有唯一PIT计数；IRQ0是该后端唯一写入者。sys7/sys46、sleep/word deadline、输入时间戳、RTC elapsed、N1诊断均读同源。每进程CPU记账ticks和RTC UTC锚点保留。
- PIC/PIT移至PC平台，一次初始化位于tasks_init之后、console之前，保持IF=0；run不重编程。启动前IRQ0只推进时钟并应答，不维护或启动调度。
- 单一`platform/pc::pic_eoi`仅slave/master I/O。设备IRQ分发定义从网卡文件移至PC平台；网卡只处理自身ISR/队列。独占诊断路由只改/恢复拥有的ELCR/PIC位，不覆盖其他所有者。
- 原IRQ等待指令序列抽成窄arch helper，调度idle和诊断复用；没有第二套时钟/EOI/等待管理器。
- 默认构建不链接NIC驱动、其命令及诊断路由状态；仅`--net-boot-diagnostic`可构建原N1实验诊断。`--clock-irq-probe`只链接测试控制，默认ELF不含它。此隔离不是ring-3驱动合规声明。

## 交付组合与新验收

已合入并检查main `3377dbf35bdb43d850c9a2b8e8076da3be146f3d`；新增上游没有修改
内核、共享ABI实现、原libc/线程运行库或默认user_build。保留双方state和许可证登记。
PR17/18/19/21/22/23已合入，PR20的维护者审查仍要求ring-3驱动。PR18撤回了frame-proxy
认领，不能把其合入视为syscall112可调用。运行源码和SDK没有新增syscall编号/能力。

| 真实组合 | build | 实际范围 |
|---|---|---|
| 默认 | `919bd09bb69b6e0f` | 无NIC驱动/诊断路由状态/测试命令；原floppy、inline ISO、file ISO均可用 |
| N1实验诊断 | `2ef23d2706818868` | 显式`--net-boot-diagnostic`，真实file ISO；不能作为生产网络驱动交付 |
| 内核探针 | `96c3a71ea876dbcf` | 显式`--clock-irq-probe`，默认镜像不链接此代码 |
| 连贯性组合 | `288d715bc351e2a2` | 两测试标志共同启用，连接真实IRQ0→真实Ethernet→run→旧sys7/46/47/48/64 |

[qualification.json](qualification.json)冻结全部七个profile（含网络和GPU故障配额）、每个
profile的718个源码输入与实际产物校验；[local_artifacts.json](local_artifacts.json)列出206个
实际本地大产物/工作盘/真实ELF/SDK/QEMU的路径、字节数和SHA256。原Qt消费者SDK1054个
产物与原源码树重新核验；旧ELF作为新内核的实际消费者，不冒称重新编译Qt或新版Browser。

- [36套新运行](regressions/results.json)全部通过：原21套（G02全部19组、E04、T0–T2、文件/持久化、QtCore/Gui/Widgets/Aurora Notes）、N1十项、GPU paired/failure两项、Aurora Browser离线三项。所有原行为断言保留，ROOT/输出路径和必要的真实介质适配逐项记录diff与SHA。
- [专用探针](directed/delivery_probe_run/report.json)：13个内核控制，以及两次实际用户态单调时间/sleep/word deadline/RTC调用。测试内核资源均回到`free=130278/tasks=2/completions=0`。
- [同一客体连贯性](directed/delivery_continuity/build/results/report.json)：启动前3 tick→两轮真实32帧Ethernet及34页DMA回收→run→用户态117 tick，普通MMIO/PCI IO仍fault14/13，资源回到`130269/2/0`。未重新初始化PIC/PIT或归零时间。
- [QEMU真实IRQ/EOI跟踪](directed/delivery_trace/analysis.json)：IRQ0=482、NIC IRQ10=1、IRQ1=3、IRQ12=1；487次实际OS中断逐次对应正确slave/master EOI序列，零重复/遗漏。排除BIOS阶段，未在内核EOI中增加统计或计时。
- [dash时钟/等待/RTC补验](directed/delivery_dash_clock/report.json)使用真正恢复startup-v3描述符的libc CRT，资源回到`130279/2/0`。默认内核的`net-test`/`irq-audit`均真实返回unknown command；ELF符号表也无NIC、测试探针及诊断路由状态。

Browser三项使用原冻结B1 ELF和原页面，只检验该消费者在新系统上的离线行为；不评价
维护者新合入的浏览器源码修复，不声明浏览器网络、DOM/V8或应用级兼容性。
默认构建和诊断构建资格分开，不把N1结果绑定到不含NIC的默认镜像。

## 调用链与初始化对照

```text
整改前 IRQ0: arch timer_entry → pic_eoi(0)[PIC ticks++] → tasks tick_count++ → waits/schedule
整改后 IRQ0: arch timer_entry → platform timer_interrupt → core clock[一次递增] + PC pic_eoi[纯I/O]
                         → 已有current时才维护waits/schedule；boot阶段直接回原ring0现场

整改前 设备IRQ: arch exceptions → platform::device_irq[定义在virtio_net.cpp] → Net ISR → arch EOI
整改后 设备IRQ: arch exceptions → PC平台分发 → 已认领的独占诊断callback[Net仅自身ISR/队列]
                                         → 同一PC pic_eoi一次应答

整改前 boot: tasks_init → console → Net重设PIC/PIT → HLT → run再重设PIC/PIT/PS2/RTC
整改后 boot: tasks_init → PC PIC/PIT一次配置[IF仍0] → console/受限HLT → run仅PS2/RTC/进入用户态
```

[core clock](../../../src/kernel/core/clock.cpp)是**当前周期PIT后端**的唯一计数状态，
不是把未来时源强制限定为中断。依照[时间域契约](../../contracts/time_domains.md)：
sys_ticks是自本次boot BSS起算、按实际递送IRQ0计数的兼容域；单调ns按现有10ms比例
饱和换算（保留原ABI），线程deadline属于同一单调域；N1 tick时长是该域的明确导数。
IF=0的console忙等期间不承诺测量宿主经过时间；不新增高精度/校准/暂停恢复资格。
RTC保留原UTC快照加monotonic锚点，在run采样后同源计算elapsed；CPU使用记账与设备
完成计数是其他语义，不得拿它们代替系统deadline。墙钟未被删除或伪装成uptime。

实际删除PIC `ticks`/`pic_ticks`、无归属的`pic_line_enable`、网卡全字节mask/ELCR快照、
网卡和tasks_enter的重复全局初始化、网卡文件中的通用分发定义及arch设备分支的EOI。
原tasks权威计数只迁移一次到core，RTC锚点/每进程CPU ticks/PCI发现映射/DMA配额及
reset-before-reclaim保留。PC硬件I/O保留原MIT来源与新增Apache归属。

## 边界与仍未完成的审查

本PR仍为实验分支。测试构建隔离和公共时钟/IRQ修复不能代替维护者要求的用户态驱动。
通用设备授权/MMIO/DMA/IRQ通知与撤销的公共机制、真实ring-3 VirtIO初始化/队列/收发、
共享IRQ、SMP、真机/IOMMU、自然wedged-reset quarantine注入均未取得本轮资格。
用户已明确禁止本轮扩展新syscall，故这些保持BLOCKED/NOT_RUN，不自行批准或合并。
最小缺口证据是本轮在真实BAR映射/收发后重复的普通用户MMIO和PCI IO拒绝；不是失败
后放开权限。下一阶段应复核已合入的修订PR18设计并另行完成登记/实现，本轮不实施。

当前实验路由只支持一个启动前、此前masked的IRQ5/9/10/11消费者；实际配置验证IRQ10，
不宣称共享活动设备路由。当前时钟为单CPU、现有10ms量化语义；未做长压力或发行资格。
材料审计仅核许可证/SDK副本，不是静态产品逐成员发行审核。

## 复现

```sh
python3 scripts/build.py --output-dir build/clock_irq/NEW_DEFAULT
python3 scripts/build.py --output-dir build/clock_irq/NEW_DIAGNOSTIC --net-boot-diagnostic
python3 scripts/build.py --output-dir build/clock_irq/NEW_PROBE --clock-irq-probe
QEMU=/absolute/path/to/qemu-system-x86_64 python3 tests/clock_irq_guest.py \
  --system build/clock_irq/NEW_PROBE --output build/clock_irq/NEW_PROBE_RUN
```

[原回归执行表](regressions/inputs.json)列出真实ELF、runner、参数和输出；
[执行编排](tools/run_delivery_matrix.py)和各case的adapter.json/diff/实际executed_runner保留路径
适配。原消费者输入和SDK留在既有只读工作区；不得覆盖旧产物。原始QEMU/串口/host帧与
截图在regressions/directed，文本/PPM/帧按原字节无损gzip。最终FAT工作盘留本地并记录摘要；
QMP短临时目录只装控制socket，不冒充保留的工作盘。默认介质保持原样，只有超出旧容量
的诊断ISO显式optical启动。原始generic runner描述标签保留，真实介质以adapter和QEMU命令为准。

## 已测候选（后续主线整合不改绑）

首次完整验收基于main `169f51e`整合后的固定代码：默认build `586fa106452724be`，
N1诊断`5556afe482d03b80`，专用探针`72515af57b2ac4d5`。
36套原行为输入回归通过：原21套（含G02全部19组及原三种媒体）、N1十项、GPU paired/failure两项、Aurora Browser离线三项。
另有13项测试内核控制、两次真实用户态clock/wait/RTC、QEMU IRQ/EOI实际跟踪505组全部匹配。
默认镜像下的dash补充采用真实恢复startup-v3的libc CRT；未授权fork和未opt-in原始CRT均先真实拒绝，失败保留，未伪造marker或放宽检查。

所有大镜像、SDK、ELF和最终工作盘保存在本工作区忽略build目录。最终资格必须单独绑定
交付时实际源码、镜像、实际ELF、SDK、QEMU命令/日志、截图及资源计数；本段旧候选不改绑。
原PR20冻结报告不改；初始介质、fixture路径、QMP socket过长、缺头/链接和权限/CRT失败均保留。
