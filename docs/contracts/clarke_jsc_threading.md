# ClarkE 静态 JSCOnly 线程边界

基线是 [锁定的 WPE WebKit 2.54.2](../../src/ports/webkit/source_lock.json) 和 XOS glibc 静态 C/C++ profile。初次 `jsc` 构建在开启 `USE_SYSTEM_MALLOC` 后到达 WTF，`ThreadingPrimitives.h:70` 和 `ThreadSpecific.h:169` 拒绝平台。`LLIntSettingsExtractor.cpp` 使用同一组头文件。独立客体栈适配器覆盖当前线程和存活工作线程的区间查询。 [验证记录](../work_log/eb674281_clarke_jsc_static_threading_boundary.md)

## 可接入的线程操作

| 上游位置 | XOS glibc 的候选接入 |
| --- | --- |
| `Source/WTF/wtf/PlatformUse.h:122`、`ThreadingPrimitives.h:43–71`、`ThreadSpecific.h:110–169` | `USE(PTHREADS)` 的现有来源是 `OS(UNIX)`。XOS 应按实际线程能力在 `OS(XOS)` 选择 pthread 句柄、私有 mutex/cond、once 和 TSD，保留 `pthread_t` 的不透明全宽身份。上游 `ThreadIdentifier` 的 Linux `pid_t` 表示及 `gettid` 路径单独评估。 |
| `Source/WTF/wtf/posix/ThreadingPOSIX.cpp:352–382,513–543,690–816` | 选用系统分配栈的 `pthread_create`、join/detach、TSD 析构、mutex、cond wait/timedwait/signal/broadcast。保留绝对实时时钟期限和谓词循环。上游允许调用者提供栈地址和选择调度策略，XOS 静态 glibc 只接受内核栈和继承调度。创建失败和有限线程额度必须向上游真实调用点传递。 |
| `Source/WTF/wtf/StackBounds.cpp:113–177` | `pthread_getattr_np` 与 `pthread_attr_getstack` 提供当前及存活工作线程的实际区间。候选适配器返回可访问的半开区间，WTF 栈的 `origin` 取高界、`bound` 取低界。失败保留输出。观察对端时需保持线程存活。主线程采用同一原生查询，其来源是 sys41，不需要 Linux 的增长栈、`getrlimit` 或 `SYS_gettid` 调整。 |
| `ParkingLot.cpp`、`WordLock.cpp`、`generic/RunLoopGeneric.cpp`、`generic/WorkQueueGeneric.cpp` | `WordLock` 通过 C++ condition variable 停放，`ParkingLot` 用时间域和每线程状态协调唤醒，Generic RunLoop/WorkQueue 仍涉及线程和定时。用真实 glibc/libstdc++ 私有等待接入，并在四线程限制下测实际 JSC 并发、等待和回收。 |

`xos_stack_bounds.cpp` 只依赖目标 SDK 的公开 glibc 头和函数，对空范围及地址溢出明确报错。独立客体探针覆盖主线程、工作线程的自身和外部查询、join 后的过期句柄，以及真实 pthread 唤醒、条件超时和两次 TSD 析构。其他线程操作的实测证据见 [glibc 静态线程契约](glibc_static_threads.md)。

## 跨线程栈扫描与协作挂起

不能将整个 `ThreadingPOSIX.cpp` 当作可用的 XOS 后端。`signalHandlerSuspendResume`、`initializePlatformThreading`、`suspend` 和 `resume` 组合了 `sigaction`、`pthread_sigmask`、`pthread_kill`、`sigsuspend`、信号上下文及 semaphore。XOS 当前支持进程私有 semaphore。glibc 的 `pthread_kill` 对实际非零信号和 `pthread_sigmask` 对信号掩码明确拒绝。`HAVE(MACHINE_CONTEXT)` 关闭时上游依然需要信号停车与唤醒。

`Source/JavaScriptCore/heap/MachineStackMarker.cpp:119–200,213–219` 在同线程采集之外，会挂起注册的其他线程并复制寄存器和活动栈。解释器关闭 JIT 和使用 polling traps 可去除信号陷阱依赖，跨线程 GC 的根扫描仍须明确成立。首个受限解释器可选择严格单一的 VM mutator，用现有当前线程根采集路径。必须在接纳额外 mutator 前显式拒绝，验证当前栈和寄存器的根及后台线程注册边界。当前代码尚未建立这个限制。SamplingProfiler 依赖指令指针和帧寄存器，先用上游构建选项关闭，再单独资格验证。

跨线程阶段需要协作安全点。协调方发布请求代际，参加的线程在无互等锁的可达安全点确认，发布稳定的栈指针和完整可扫描根状态，停放至该代际释放。离开运行区、进入可能阻塞的等待、退出或加入线程组都要参加该协议。保存普通 ABI 下 `setjmp` 的少数寄存器不足以证明活跃根完整，需要有意的编译器安全点溢出规则或实际寄存器保存。采集失败、线程退出或超时须释放已确认的 peers，并在任何扫除前终止该次收集。缺少活线程根时不能沿用上游对已死亡线程的跳过策略。客体验收至少覆盖仅寄存器持有根、仅栈持有根、等待中线程、请求竞争与退出，且验证不丢根和不挂住。

## 宿主生成器与目标二进制分工

`Source/JavaScriptCore/CMakeLists.txt:338–350,418–479` 的两阶段 offlineasm 由宿主 Ruby 执行。读入的 `$<TARGET_FILE:LLIntSettingsExtractor>` 和 `$<TARGET_FILE:LLIntOffsetsExtractor>` 是目标编译器和目标配置产生的 ELF。`offlineasm/offsets.rb` 用二进制读取并按字节序搜索表标记，过程不启动这两个 ELF。持续保留目标字段布局、生成头和标记内容，禁止用宿主 `sizeof` 或宿主布局替换目标记录。Ruby/Python 与生成脚本走宿主工具路径，链接器、归档器及 ranlib 走目标 GNU 工具路径。

本轮真实日志还在 `libbmalloc.a` 阶段记录宿主 ranlib 的 Mach-O 警告。下一次构建显式绑定已验的目标 GNU binutils，检查实际 Ninja 命令与 archive 成员。静态配置明确选择上游 `ENABLE_STATIC_JSC`，先验证两个目标提取器及生成的目标头，再构建静态 WTF/JavaScriptCore、链接 JSC shell 并进入客体。当前没有引擎运行或测试覆盖率数据。

[原生布局生成](../../src/ports/webkit/README.md#原生-llint-布局生成) 现已完成两个
提取器及 `LLIntAssembly.h`。XOS 选择真实 glibc pthread 类型，使同一套目标配置可
供提取器使用。宿主 Ruby 解析两个目标 ELF，输出 `vmEntryToJavaScript` 的 x86-64
汇编。

[原生 WTF 栈边界阶段](../work_log/207c6644_clarke_native_wtf_thread_and_stack_slice.md)
编译了 `StackBounds.cpp`、`Threading.cpp` 和复用的原生栈边界辅助对象。线程自身初始化
使用实际的可访问栈范围。创建线程在入口握手锁内查询新线程的栈。`posix/ThreadingPOSIX.cpp`
仍依赖信号挂起。WTF 链接、
单 mutator 准入、GC 根保留和客体解释器执行仍待验收。
