# COW0：私有页写时复制契约

状态：**COW0 契约冻结；COW1–COW3 未实现、未资格认证**。审计基线为
`9c51eb46e321e0f2aee7837b00e90d5733ad9cfb`（VM3 与 IPC v1 IP2 均已合入）。
本文件是后续实现的约束和验收门槛，不宣称当前内核已经具备 COW。匿名映射、IPC、
线程及时间语义分别以[匿名 VM](anonymous_vm.md)、[IPC v1](ipc_v1.md)、
[线程](threading.md)和[时间域](time_domains.md)契约为准；本文件不得缩减它们。
COW 不新增 syscall、公开结构、errno、feature 位或 SDK supported 声明。
文件/共享映射、MMIO、DMA、内核页和共享内核映射不在私有页 COW 范围；以后支持
MAP_SHARED 时须另定共享写/撤销语义。单 CPU，现有线程 profile 的 fork/exec 拒绝、
files 认证、spawn 授权和完成记录协议不变；不承诺多线程 fork 或 SMP shootdown。

## 不变量和页面状态

1. 用户数据物理页由分配器拥有，合法映射各持一个引用；未安装的暂存引用必须有唯一
   事务所有者。分配时清零并取得首引用，retain 仅接受已分配用户页且检查引用及全局
   计数溢出；release 最后引用才释放，页表/内核页不走用户数据页引用。映射、回滚、
   退出、exec、unmap 和线程栈/TLS 回收均只释放自己的引用，不得重复释放或借用设备页。
2. 逻辑 R/W/X、硬件有效 U/RW/NX（含全部上级页表）、私有 COW 身份、提交状态、
   引用、pin 和映射世代是不同事实。只读 PTE 或 ref>1 本身不足以识别 COW；真实 R、
   RX、guard、未提交保留及 NONE 均不能因 fork 被提升为可写。上级权限受限、huge、
   非法所有权及未知软件位必须拒绝；不得把架构 PTE 布局暴露给 SDK。
3. 对逻辑可写的私有已提交页，fork 后父子各有独立页表及逻辑配额，各持同一用户页
   引用，COW 身份明确且所有有效硬件映射均不写。R/RX 只读页可共享，但不设置可
   写 COW 身份。NONE 已提交页保持内容、持引用且不可访问；其后提升保护必须根据
   届时的逻辑权限和共享状态建立正确 COW 映射，不得清零或直接授予共享写。未提交
   预留只复制 VMA，不分配数据页。VMA、堆、栈、TLS 和 ELF 页均按实际所有权遍历。
4. 物理页引用为 1 时，合法 COW 写可原地移除 COW 状态并恢复硬件写权；大于 1 时先
   分配私有页并复制完整原内容，校验映射世代及权限，原子替换本映射、使本 CPU TLB
   失效，最后释放旧映射引用。失败不得先丢旧引用、改变内容、提高权限或影响其他
   地址空间。所有写入口使用同一所有权检查和分离语义，不得依赖内核态缺页兜底。

## fork、发布、撤销和 eager 对照

`fork_prepare` 在既有单线程/授权/配额检查后构造独立子页表和 VMA 快照，保留每个
共享页引用、准备撤销记录；任何失败均可分批回滚。父用户线程不能在部分快照上运行。
在受保护窗口发布父/子映射并同步父 TLB，子进程保持 building；只有 files 会话认证、
FD/stdio/pipe 继承和既有 fork_commit 全部成功后才可运行。prepare 返回前失败时，
父内容、逻辑权限、配额与可观察行为不变，子页表、引用、句柄和完成记录均回收。

prepare 成功后 files 失败或 abort 时，撤销子所有引用和临时资源。此时父进程可能已
写入并分离，回滚不能用旧 PTE 覆盖父的新映射；父可安全保留逻辑可写、硬件只读的
COW 标记。剩余引用为 1 的页下次写可无分配恢复；父不得变成真正只读，不能泄漏
配额或引用。父退出/取消时，子构造和父续体的所有权明确，取消遵循发布前回滚、发布后
完成清理；每个阶段无半发布可见。exec 成功原子替换整个 VMA/地址空间并释放旧引用，
失败保留原图；exit/kill、部分 unmap 和 NONE 均逐映射释放。

保留同源码版本的 eager 对照构建 profile：沿用现有 `copy_user_pages_batch` 深拷贝，
独立页表、内容、权限、错误和资源回收语义不变；对照与 COW profile 只通过内核构建/
探针配置选择，不增加用户 ABI。COW1 的快照只能在隔离探针中启用，直到 COW2 的全部
内核写回、pin、取消和故障矩阵通过，才允许向普通 fork 路径发布；不能仅支持用户 store。
COW0 不新增构建开关，也不将尚不存在的 profile 说成已运行。

## 故障、copyout 与 pin

仅用户态页保护故障、present=1、write=1、user=1，且映射是当前进程有效、已提交、
逻辑可写的私有 COW 页时尝试分离；reserved-bit、instruction fetch、NX、真实只读、
guard、内核地址、未知映射和 non-present 均沿原有异常路径。fault 途中 OOM 不可从
store 返回 errno：只终止故障进程，以现有 `faulted`、vector 14、地址和指令报告，
内核诊断明确 `cow_oom`；不修改 `process_status` 结构或枚举。其他共享者和内核继续。
未知所有权、引用下溢等内部不变量错误不能伪装成普通用户 OOM。

所有输出在任何用户可见数据、队列消费、句柄/回复 token 发布、硬件读或完成记录消费
之前验证完整范围、溢出和逻辑写权限，并为将写的页准备私有化。固定结构、多缓冲 IPC
和随机数请求全量准备、全量提交；失败不写部分用户数据，也不消费队列或虚报成功。
允许短读的 pipe/文件路径先确定实际交付量，再一次准备该前缀；仅完成的前缀可消费，
不得将失败页计入已读。资源失败用该操作已有资源/内存错误；随机数使用既有
`random_error_io`，block read 使用既有 `block_error_io`，传统 sys_recv 使用既有
`sys_error_full`，display 使用 `display_resources`，IPC v1 使用 `resources`，线程
输出使用 `thread_error_memory`，进程类输出使用 `process_error_resources`。既有 API
不具备专用资源错误的旧 `sys_tasklist` 使用 `sys_error_full`；pipe/handle/stdio
读取使用 `process_error_resources`，对应 libc `ENOMEM`；`sys_read` 沿用同一内核
结果，传统 `sys_recv` 的 `sys_error_full` 表示本次无法准备接收而非成功。设备
操作将来如写回则使用 `device_resources`。SDK 的现有错误映射不得悄然扩展：random
的 `random_error_io` 在 libc 是 `EIO`，block 的 `block_error_io` 仍是其既有 I/O
错误，旧接口无单独 OOM 码时这一区别必须在测试和文档中保留。不得把合法 COW 指针
误报地址错误、以成功掩盖失败、改变已经定义的 IPC phase 或 reply_consumed 语义。

等待 word 在比较并登记前取得本进程稳定的逻辑地址映射：需要可写访问时先分离；
唤醒按进程身份及逻辑 VA，不按可被更换的物理页匹配。所有阻塞输出（process wait、
join、IPC v1 请求结构和载荷等）在入队前按整个输出集合完成私有化和 pin；pin 持续
到完成写回、取消或进程关闭，包括 ready 但尚未 copyout 的窗口。pin 期间权限降低、
decommit、unmap/线程栈回收须沿现有 busy/等待规则；若世代不符则禁止对旧物理页写。
不同地址空间的同一物理页分离不会改变本进程稳定 pin。join reaper 的非当前 CR3
物理直映写必须通过同一拥有者/世代/可写化检查。IPC v1 的多个 pin、reply token、
超时和 `reply_receive` 已提交 reply 须遵守 IPC 契约：不能丢 phase、重复 reply 或把
已交付请求误称未交付。无法在入队前保证上述不变量的路径不得启用普通 COW fork。
基线 IP2 实现本身尚未完成真实客体资格，仍按其工作记录和 SDK 状态处理；本次源码
盘点及宿主参考模型不能替代 IPC 自身的客体验收，也不能将其声明为 supported。

## 统计和证据

`process_max_pages` 和 `process_record::user_pages` 是每进程逻辑已提交页预算，隐藏
NONE 已提交页计入、未提交 VMA 不计入；fork 子进程按自身逻辑页数收费，即使共享
物理页也不得绕过预算。`memory_status` 的 free/allocated 为全局物理分配页，包含数据、
页表和内核页；`user_pages_status` 的 unique 是唯一用户数据物理页、references 是
持有的用户页总引用（含事务暂存），不能将两者误认为每进程逻辑页或页表页。
`process_stats`/`thread_stats` 已有布局和语义不变，不借 reserved 字段发布新 ABI。
页表、暂存引用、pin 和续体/完成记录须用私有诊断或冻结窗口内的可审计遍历分别计数；
若基线没有指标就标 `NOT_MEASURED`，不得从 free 页差推断每一类。测量包括共享前后、
发布和回滚中间点及最终静止基线；检查溢出和重复释放。性能报告区分每进程逻辑页、
唯一数据物理页、页表、暂存、pin、时间及其时钟量化，不把未完成回收当节省。

## COW0 源码路径清单

基线逐调用点和文件 SHA-256 见[可复核的扫描清单](../reports/cow0_20261112/source_audit.json)；
扫描是检索辅助，不证明所有别名/汇编/未来代码已分类。每次更改须重新扫描并人工审查：

| 范围 | 基线具体入口与必须处理的责任 |
|---|---|
| 数据页与统计 | [memory.cpp](../../src/kernel/core/memory.cpp)：`allocate_user_page`、`retain_user_page`、`release_user_page`、`user_pages_status`；[memory.hpp](../../src/kernel/include/xos/memory.hpp) 的对象和页表接口。当前已有引用，不是旧路线所说的“无引用计数”。 |
| 页表/隐藏页 | [paging.cpp](../../src/kernel/arch/x86_64/paging.cpp)：`map_page_in`、`query_page_in`、`query_logical_write_in`、`vm_lookup/prepare/install/protect/remove/scan`、`copy_user_pages_batch`、`release_user_pages_batch`、`destroy_address_space`、TLB 失效；`vm_entry` 当前重建 leaf 会覆盖软件状态。 |
| fork/关闭 | [tasks.cpp](../../src/kernel/arch/x86_64/tasks.cpp)：`prepare_fork`、`fork_copy_step`、`finish_fork_copy`、`sys_process_fork_*`、`finish_task`、`destroy_task`、`sys_process_exec_*`、`set_heap_break`；[vm_continuation.hpp](../../src/kernel/core/vm_continuation.hpp) 的代次、分批和取消。 |
| 检查、故障及直映 | `tasks.cpp::user_range_ok` 当前使用硬件 RW；`copy_to_user` 当前是裸 `copy_bytes`；`user_fault` 当前杀死用户 fault；[exceptions.cpp](../../src/kernel/arch/x86_64/exceptions.cpp) 区分用户与内核异常。`reap_threads` 物理直映写 join 输出；`add_user_page`、`paging.cpp` 的 eager 复制和 `memory.cpp::allocate_page` 清零写新分配页；[self_check.cpp](../../src/kernel/core/self_check.cpp) 写测试页，均须按所有者分类。清零所用的 `volatile`/`address` 别名不在该扫描器的物理指针模式中。 |
| 同步输出 | `tasks.cpp` 的 `random_bytes`、`ipc_recv`、`pipe_read_from`、`stdio_read`、`thread_syscall`、`sys_channel`、`sys_process_guard`、`sys_boot_payload`、`sys_image_info/read`、`sys_pipe_create`、`sys_file_session`、`sys_process_wait/stats`、`sys_ipc_handles/endpoint/name`、`sys_block_read/info`、`sys_tasklist`；[display_tasks.inc](../../src/kernel/arch/x86_64/display_tasks.inc) 的 mode/connect/accept/input。必须审查每个先消费、后写回的副作用。 |
| 异步 IPC 和 pin | `tasks.cpp::deliver_wait`、`ipc_v1_syscall`、`ipc_v1_pin/unpin`、`ipc_v1_deliver_to_waiter`、`ipc_v1_reply_token`、`pinned_range`、`ready_with`、`reap_threads`；[vm_pin.hpp](../../src/kernel/core/vm_pin.hpp) 仅记录区间，当前无物理页引用或世代。IPC v1 的请求、payload 与 reply 是不同输出及 pin。 |
| 其他路径 | `device_authorize_syscall` 当前仅校验输出范围；将来设备操作必须重新审计。`display_tasks.inc::present` 通过物理直映读取客户端像素，不能把它误判为用户写回。`copy_from_user`、文件服务客户端及未来 DMA/grant 使用者仍须随新增写路径重新审计。 |

## 失败与资格矩阵

以下每行均为后续真实新镜像和真实用户态行为的通过条件；COW0 不将任何行记作已通过。

| 场景/注入点 | 必须观察到的结果 |
|---|---|
| 父/子/孙写、跨页、父先退出 | 同 VA 双向隔离，栈/TLS/堆/匿名页内容正确；读页无需复制；最终引用、页表、任务和完成记录回基线。 |
| R、RX、RW/NX、NONE、guard、未提交和 RWX | 真实 CPU 读/写/执行及 errno 按现有合同；NONE 保留内容且 fork 后提升保护安全，真正只读不能被 COW 恢复写。 |
| 第 N 个数据页、页表、retain、撤销记录、VMA/FD/session/completion 耗尽；prepare 每一批取消 | 父内容/逻辑权限、errno 和授权不变，子所有资源精确回收；引用溢出和未知物理页拒绝，不得用 allocator 全局注入跨调度污染其他进程。 |
| 子 building 时父先写，再 files 失败或 abort | 不覆盖父的新页；安全残留 COW 可在 ref=1 时恢复，父/其他共享者数据和计数正确。 |
| COW fault OOM、copyout 首/中/末页 OOM 和只读跨页端 | fault 仅杀故障者并诊断；固定输出无部分数据/副作用，短读只提交已准备前缀；原页、其他进程及计数不变。 |
| pipe/stdio、block/file、旧 IPC、IPC v1、random、display、统计、process wait 和 join | 每条实际写回路径含跨页、引用=1/>1、权限错误和 OOM；入队/完成/超时/kill/exec 的输出、队列、token 和资源满足各自合同。 |
| word/process/join/IPC 多 pin，ready 未送达，timeout/wake/close/kill 竞争 | 地址空间与世代稳定、无失唤醒/重复交付/脏写，pin 精确释放；统一单调时间不因页工作、IRQ 或 EOI 推进。 |
| fork/exec/abort/退出/unmap 与隐藏页，三代共享 | 最后引用才释放，独立页表和保留区正确，失败 exec 不改变旧图；不把设备、MMIO 或未来共享页混入。 |
| eager 对照与 COW，同镜像来源、真实 ELF | 比较内容、权限、错误、FD 会话和生命周期；无写 fork、逐页写和重复回收分别记录逻辑页、唯一物理页、页表、pin、事务、时间。原始失败不覆盖。 |
| 应用和兼容性 | E04、dash fork/exec/FD、T0–T3、IPC v1、QtCore/Gui/Widgets 定向回归；记录 commit、工具/SDK/镜像/ELF 摘要、QEMU 命令、串口、资源基线及未运行项。 |

COW3 必须对每行提供逐项证据，而非以编译、宿主模型、单个总 free 页或旧镜像报告
替代。先前 VM3 的 `implemented_unqualified` 与本 COW0 文档均不构成 COW 资格。
