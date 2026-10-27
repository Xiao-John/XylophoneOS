# XOS POSIX 子集契约 v1

2026-10-26。状态：文档契约已建立，扩展实现与新验收尚未开始。
本文件定义工程边界，不声明POSIX认证、完整POSIX或完整POSIX Shell兼容。

## 参照、决策与声明

参照POSIX.1-2024 / The Open Group Base Specifications Issue 8。`xos-posix-subset-v1`
是XOS自定义的源码兼容子集名称，不是标准组织定义的profile，也不是新的二进制ABI。
当前SDK/profile/执行标记继续按各自契约使用，不因本文改名或追认资格。

- C：用户授权建立子集契约与计划；保持微内核边界、xsh默认入口、dash可选程序定位。
- P：本文件的目标面、分期与验收方案是可逆工程建议；开工时冻结具体接口清单与资源预算。
- O：完整标准逐条对照、XSI及其他选项取舍、具体信号ABI/TTY协议/映射ABI尚待专项设计。
- D：完整POSIX合规声明与认证不进入当前阶段；SMP、Linux ABI、动态链接、GNU扩展
  各自规划，不将它们当作POSIX必需条件。COW是优化，不是fork合规的必要条件。

不得把标准基础要求降为“可选”来消除欠账。每项须分别登记标准地位（基础/选项及标签/
扩展/待核对）与XOS实现状态。选项分类未核对时保持待核对；本文没有列全所有标准条款。

## 实现状态与证据

| 状态 | 含义 |
|---|---|
| accepted_subset | 有冻结客体证据，仅对已声明范围和输入版本成立 |
| implemented_unverified | 源码已有实现，但目标行为尚无对应验收 |
| in_progress | 有已登记的专项实施，不等于通过 |
| planned | 仅有目标或设计，未启动实现 |
| unsupported | 当前契约不支持；存在头文件或占位符也不改变此状态 |
| not_audited | 未逐条核实；不能据此断言存在或不存在 |

通过某应用不等于通过其依赖的全部标准接口。历史报告不改绑当前工作树；新源码、SDK、
镜像的资格各自留回执。当前聚合状态在state.md，详细依据在下表链接。

## 当前基线与目标矩阵

本表是2026-10-26文档快照，不是完整函数目录。新增或收口能力时同步专项文档与本表。

| 面 | 当前状态和范围 | 下一目标与依据 |
|---|---|---|
| 进程/执行 | accepted_subset：单线程eager-copy fork、同PID exec、同步spawn；线程SDK的fork/exec不支持 | 补继承/等待/信号和多线程生命周期；[Shell范围](../implementation/shell.md)、[SDK](../e04_loader_sdk.md) |
| Shell | accepted_subset：前台管道、子Shell、命令替换、HereDoc；后台/trap/jobs/wait/kill内建拒绝，用户重定向仅FD0–2 | 按底层能力逐项开放；[C3记录](../history/shell.md#log-0049_dash_c3_script_exec_make) |
| FD/管道 | accepted_subset：共享打开描述、32FD执行转交/CLOEXEC、阻塞管道；不推出完整fcntl/所有标志支持 | 完整逐项清单、非阻塞/中断/就绪等待；Issue 8的CLOFORK另行核对 |
| 文件/身份 | accepted_subset：有界读写/目录/持久化；stat使用合成模式等属性 | 路径、权限/UID/GID、时间戳、链接与打开后删除；[文件服务](../e05_file_service.md) |
| 线程 | accepted_subset：T0–T2声明的创建/退出、TLS、mutex/cond/once/TSS；cancel/atfork等仍unsupported | 补线程接口缺口与进程交互；[线程契约](threading.md) |
| 时间 | accepted_subset：单调时钟与等待；墙钟/时区PY3 B2 accepted_subset（0058），仅其声明范围 | 复用0058冻结证据，另核CPU时间、信号定时器与时钟跳变；[PY3](../plans/cpython_extensions.md) |
| 映射 | unsupported：mmap/munmap为ENOSYS；mprotect/共享映射无资格 | VMA、匿名映射与保护、文件与共享映射分期 |
| TTY/信号 | unsupported：没有已验的异步POSIX信号/控制终端/作业控制契约 | 监督Escape取消不冒称SIGINT；先补内核机制和用户态终端服务 |
| 网络/IPC | socket族无已验兼容契约；现有能力IPC不等于POSIX IPC | Unix域/网络socket、命名共享内存、sem/MQ分别列清单和标准选项，不互相替代 |
| 文本/locale | accepted_subset：UTF-8文本与argv通道；路径U2未完成，完整locale未审计 | 先核字节路径和C/POSIX locale，再按应用需要扩展；UTF-8显示不等于locale合规 |
| 工具/构建 | accepted_subset：若干基础工具和受限Make | 逐命令核选项/输出/退出状态；[Make范围](../implementation/make.md)，GNU扩展不充当POSIX要求 |
| 能力查询 | not_audited：头文件宏/sysconf/pathconf等未做整套对照 | 逐项核版本、选项、运行时能力与标准最低限额，禁止根据库自带宏推断已合规 |

当前Shell资源边界：全局8进程、最多4段前台管道、fork深度3、32FD、argc/env各64、
startup总16KiB、命令替换stdout上限1MiB；spawn与exec单串限制不同，见shell_subset.md。
这些是工程上限，不代表满足标准最低值；必须逐项对照后才能作合规声明。

## 对外语义约束

1. **错误真实。** 未实现接口按其包装约定报错，不永远成功或偷偷换语义。errno型接口、
   直接返回错误号的pthread接口分别处理；ENOSYS/ENOTSUP/EINVAL等必须逐接口核对，
   不用统一错误掩盖无效参数、权限和资源失败。已有占位报错不等于标准允许该桩。
2. **FD不是路径。** dup/fork继承同一打开描述的偏移与状态；描述符标志另属FD。
   明确close、exec、退出时的所有权、CLOEXEC及文件/管道引用回收，不靠重开路径模拟继承。
3. **阻塞可解释。** 短读写、EOF、EPIPE/SIGPIPE、EAGAIN、EINTR、SA_RESTART、部分完成、
   超时和关闭并发逐项定义；信号与pselect类原子等待不能靠先改掩码再睡眠拼接。
4. **进程不是线程组复制。** 多线程fork子进程只保留调用线程；锁、atfork及exec前的
   async-signal-safe边界按标准设计。exec失败保留原进程可用状态，成功后按标准重置状态。
   原有线程SDK拒绝边界在专项验收通过前保持不变。
5. **路径与文本分开。** 不把UTF-8字符数当路径字节长度；NUL和分隔符按路径规则处理。
   FAT大小写/名称/链接/权限差异必须显式披露；需要元数据层或新后端时先设计一致性。
6. **查询不夸大。** 未来发布前审计feature-test宏、能力宏、sysconf/pathconf/confstr及
   limits；编译期声明、运行时支持、实际限制与失败方式应一致。不得仅定义_POSIX_VERSION
   或链接到newlib就宣称合规；也不未经审计机械删除应用所需的头文件声明。

## 架构与文件责任

内核提供线程/进程身份、受保护对象、地址空间、等待和必要信号递送机制；权限边界和
生命周期必须可验证。POSIX号码/包装、Shell PATH和脚本策略、文件系统策略、TTY行规程
原则上由SDK/用户态服务承担；ELF解析继续留用户态，不把dash或Qt名字写入内核策略。

- `src/kernel/core/`：通用机制；ISA上下文/页表/信号现场放`arch/<isa>/`。
- `src/kernel/platform/<platform>/`：时钟硬件、设备后端；公共接口不依赖PC寄存器。
- `src/shared/include/xos/`：版本化协议；`src/user/sdk/`、`libc/`、`threading/`：适配。
- `src/user/services/`：文件/终端等策略服务；具体新目录在实施时按实际职责建立。
- `tests/`：guest语义探针、共享夹具；`docs/reports/`和work_log保留冻结证据。

新ABI先读架构/SDK/工具链相关入口并登记，不在本文预占syscall/op编号。
现有显示backend、CPython、xypm保持各自所有权；本契约不是并发派工指令。

## 验收与接口台账

实施每一子阶段时补一份具体台账，字段至少为：接口/标准页与条款、标准地位、SDK/profile、
支持参数与限制、错误及并发语义、实现状态、测试ID、冻结报告与已知偏差。函数存在、编译
通过、应用运行、逐条语义通过分别记录；不计算没有完整分母的“POSIX兼容百分比”。

报告绑定源码manifest、工具链、SDK树、系统镜像、夹具和环境；记录pass/fail/not_run与
资源回收。日常验收只跑本次语义和受影响回归，不重复已经做过的无关测试；压力测试由专人
负责，其报告单独接入。旧冻结结果可引用，但不能作为新组合产物的重验。

## 官方参照

查证2026-10-26。标准规则与XOS工程取舍分开；具体条款以链接原文为准。

- [Issue 8介绍](https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/V1_chap01.html)
- [通用系统接口规则](https://pubs.opengroup.org/onlinepubs/9799919799/functions/V2_chap02.html)
- [Shell语言](https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html)
- [fork](https://pubs.opengroup.org/onlinepubs/9799919799/functions/fork.html)、[exec](https://pubs.opengroup.org/onlinepubs/9799919799/functions/exec.html)
- [pthread_sigmask](https://pubs.opengroup.org/onlinepubs/9799919799/functions/pthread_sigmask.html)
- [unistd能力声明](https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/unistd.h.html)

执行顺序与验收入口见[posix_roadmap.md](../plans/posix.md)。
