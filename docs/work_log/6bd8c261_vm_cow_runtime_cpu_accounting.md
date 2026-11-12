# VM/COW 普通运行路径与真实 CPU 记账

日期：2026-11-12。基线 `158a9b99550c03b97e74e3b9e4c2fd6a288c8bf3`。
范围为本轮用户授权的 VM3/COW2/COW3 实现与进程 CPU 时间，不把未运行客体验收当作阻塞
实现的理由，也不将其标为通过。未修改工具链锁、冻结报告或既有 supported feature 位。

## 实际行为

- 普通单线程 fork 使用真实 COW 快照、引用、分批准备/发布/失败回滚及用户写保护 fault
  分离；既有 files 认证与 commit 流程保留。`scripts/build.py --eager-fork` 保留同源码
  eager 对照，COW1 隔离诊断继续使用既有 opt-in，两个控制 profile 不可混选。
- 新 `core/user_copyout.hpp` 在每线程保存最多 64 个 COW 页记录；先检查完整输出区、
  分配私有候选，再核对全部原映射并发布。后续页或第二输出区失败会释放整个未发布集合。
  已硬件可写的显式共享页不按引用数私有化；只处理有明确 COW 身份的逻辑写页。
- `user_range_ok(write)` 统一准备，首个 `copy_to_user` 提交整个输出集合；syscall
  wrapper 清理未提交记录并将 OOM 映射到原有操作错误域。process wait、join、word、
  IPC 多输出 pin 在入队前完成提交，ready 未交付窗口继续受 pin 保护；join reaper
  检查同一拥有者的 pin 与有效可写映射后才通过物理直映写回。
- `reply_receive` 的 reply 提交与 receive 分开。后继 receive 准备失败仍可写回
  `reply_consumed`，不会把已消费的 reply token 说成未消费。传统 recv/tasklist 只准备
  实际输出前缀。缩小 heap 检查逻辑写权，不会将合法 COW 堆误认为真正只读。
- 父正常退出或 fault：building 子回收，已提交子交内核收养（parent=0、完成槽释放）并
  在自身退出时自动回收。独立 cancel_parent 提升到存活祖先；显式 kill/cancel 仍按既有
  权限级联取消后代。没有增加 POSIX 信号、进程组、subreaper 或服务自动重启。
- sys89 `process_cpu_time` 为 72 字节版本化自身查询，包含进程与当前线程 user/system、
  已 wait 子进程累计、独立 monotonic elapsed 和计数粒度。进程累积所有线程；fork 子
  从零开始，exec 保留，child CPU 仅在成功消费完成记录时累计一次。
- `core/cpu_accounting.hpp` 在 syscall/IRQ user↔system、调度和 idle 边界结算；
  x86-64 的 TSC 后端在首用户态前对齐并测量至少四个既有 PIT tick。既有 monotonic、
  deadline、IRQ0 推进点和 EOI 均不改变。校准失败或计数倒退返回 unavailable(-19)。
- `_times/times` 输出实际四项 CPU 字段，返回 monotonic elapsed ticks；`clock()` 明确
  只包含本进程 user+system；`_SC_CLK_TCK` 返回相同单位。实际归档的旧 newlib clock
  对四个 tms 字段求和，因此由 XOS 提供 clock 桥以避免把已 wait 子时间加进自身 CPU。
  线程 SDK 的 process/thread CPU `clock_gettime/getres` 已接 sys89。

共享头、SDK helper、两类 SDK 生成源、ABI 登记、时间域、COW 契约与 E04 说明同步。
普通/线程 SDK 的 CPU 与匿名 VM 能力均为 `implemented_unqualified`，不手改生成产物。

## 实际宿主验证

编译器实际版本为 **G++ Debian 14.2.0-19 / 14.2.0**，Python **3.12.14**。
宿主工具不冒充固定 GCC 16.2.0 交叉链。全部下列宿主回归通过：

| 命令 | 实际覆盖 |
|---|---|
| `python3 tests/cow_runtime_host_test.py` | 原 allocator + 原 paging + copyout；跨页分配失败/跨输出权限失败/元数据耗尽全回滚、映射 token 改变拒绝、父地址空间先销毁、单引用恢复、三代私有写、R/NONE 恢复、显式共享可写页保持共享、fork retain 失败与最终页/引用回基线 |
| `python3 tests/kernel_copyout_host_test.py` | 从 tasks.cpp 原样抽取真实 pipe/stdio/recv/random/检查/写回/syscall 错误翻译；memfd 实现宿主物理/用户映射；跨页 OOM 不消费管道/消息/串口，错误域正确，成功输出不污染子页，最终资源回基线 |
| `python3 tests/kernel_process_wait_race_test.py` | 原 finish_task/wait/deliver；保留 K01 ready 完成记录竞争回归，新增正常/fault 父退出、孤儿退出、building 取消、祖先显式 kill 和 child CPU 单次消费 |
| `python3 tests/cpu_time_host_test.py` | 原 CPU accumulator 的 user/system/嵌套 IRQ/idle/进程及线程归属/倒退；原 libc、pthread 时钟桥与真实 newlib 头；自身 clock 不含子时间，wall 增长不伪造 CPU，ENOTSUP/ENOMEM/EFAULT |
| `python3 tests/cow0_source_audit_test.py` | 既有源码审计工具的 3 项回归 |
| `python3 tests/kernel_runtime_compile.py --output-dir build/vm_cow_runtime/strict` | 仓库 COMMON_FLAGS+X86_FLAGS 严格宿主对象：tasks 默认/eager/VM1/COW1 四配置，paging/cpu_time/exceptions 三对象，全部通过 |
| `python3 tests/docs_consistency.py` | 本轮写日志前 897 本地链接、78 已分配 syscall、73 历史来源通过 |
| `python3 tests/abi_doc_consistency.py --output-dir build/vm_cow_runtime/abi` | 包含新增 sys89 的当前 ABI 表通过 |

`kernel_runtime_compile.py` 仅用 extern 声明替代未生成的用户镜像；不链接、不造 payload，
不绕过目标工具链审计。分页宿主测试只替换 CR3/TLB 特权操作，真实页表、分配、复制、
引用计数、COW 发布/回滚均原样编译。内核消费者测试的串口和无关 wake hook 是明确端口
替身；没有用测试中的另一份业务算法证明实现。

实际 allocator 的同输入 RW/R/NONE 对照：eager 增加 3 个唯一用户数据页，COW 增加 0，
总映射引用随子映射增加 3；各自销毁后全部恢复基线。这是宿主页后端资源观察，非客体
性能结论，不包含页表/CPU 耗时的正式对照。

额外编译：普通 libc 与 pthread 以真实 newlib 头、`-Wall -Wextra -Werror` 宿主对象通过；
线程 libc 与 pthread 使用仓库线程生成器相同语义 flags 的对象通过（pthread 开启异常）。
对线程 libc 另行加 `-Werror` 的增强检查失败于既有 `has_terminal_descriptor` 未使用；
对固定基线相同命令得到同一失败，原始失败保存在 `user_compile.json`。本轮未为清警告
修改不相关路径代码，没有将此增强检查说成通过。

新普通客体源码 `tests/fixtures/cow2_runtime_probe.c`（中间父退出后子写）与
`tests/fixtures/cpu_time_probe.cpp`（busy/user/system/sleep/times）均通过真实 newlib 头的
宿主语法检查，**尚未交叉链接或运行**。`build/vm_cow_runtime/validation.json` 保存真实
命令结果/关键源码 SHA-256；`strict/compile.json`、`user_compile.json` 和各测试日志保存
详细环境与失败。build 可重建；关键范围与未运行项在此保留。

## 边界与下一步

1. **NOT_RUN**：固定交叉链目标构建、新镜像启动、硬件 TLB/页故障、真实 PIT/TSC 校准、
   guest 父先退出、dash/Qt/IPC 完整矩阵、COW3 资源/性能资格。缺少目标工具链/NASM/QEMU
   的本轮环境未伪造镜像验收；用户授权的是继续实现，不是把这些测试当作通过。
2. CPU 域当前要求单 CPU、稳定 TSC 频率；没有迁移/挂起恢复/频率变更管理，也没有
   hypervisor steal-time 扣除。返回纳秒单位与计数粒度不表示纳秒准确度。此计时不能
   替代 monotonic/deadline；完整规则见时间域契约。
3. 全部写入口经同一事务接入，宿主定向消费者覆盖 pipe/stdio/旧 IPC/random；IPC v1
   多 buffer/reply_receive、block/display/device、join 等完整真实客体失败矩阵仍待运行，
   不能由共用机制与编译推断逐路径客体通过。
4. IPC/device 并行工作树另有 shared/MMIO/DMA 窗口与 fork 拒绝逻辑。集成应保留它的
   映射撤销与 pin 取消，并把设备 dispatch 接到新的 `dispatch_syscall`；已可写共享页
   不走 COW。带输出的撤销操作须检查其实际输出是否位于被撤销窗口内。
5. `process_stats/thread_stats` 布局与 reserved 不变；新计时只用 sys89。CPU 查询与
   COW 实现提交后可继续独立做 SSG/Python/Pillow 的源码定位，不将历史 fault 猜测
   归因为本次尚未运行的 VM 修订。
