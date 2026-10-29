# PX4-A 匿名虚拟内存契约提案 v1

2026-10-29，**PROPOSED / implementation BLOCKED**。本分支认领 `sys_vm` 67，
必须由维护者审查并合入[ABI登记](abi_registry.md)后另开实现PR。
没有共享头常量、dispatch、SDK supported 标记或新客体验收。依据
[xos_plan](../xos_plan.md)、[PX路线](../plans/posix.md)及[线程契约](threading.md)。
固定源码、逐调用点和审计回执见[审计报告](../reports/modern2_px4a_20261029/README.md)。

## 必要性和范围

现有 sys_process_map17 只给有构造权的父进程填充未启动子进程；heap_break29
只管理固定堆，不能保留地址、修改保护或提供部分解除映射。用户服务不能替调用进程
改页表/撤销CPU访问，IPC也不能替代地址空间机制。新接口只操作内核认证的**自身
地址空间**，不接受目标PID、物理页、CR3或服务名；ELF策略仍在用户态。

首期仅匿名私有VMA、稀疏保留、显式提交/撤回、保护与解除映射。文件/共享映射、
COW、动态链接、跨进程映射、透明缺页分配和用户故障恢复另设阶段。
V8 真实 PageAllocator/OS 路径需要独立的平台后端；本契约不承诺其POSIX后端原样工作。

## 地址图、profile和配额

旧 `.xos.exec/v3`、ELF/堆/主栈/TLS、线程arena及SDK继续按原地址图准入。
新SDK以 `xos-vm-v1` 清单能力暴露本接口，既有静态ELF入口保持原profile。
普通进程只有在主动调用已登记sys_vm后才产生新arena映射；不要求ELF标记授予
自身VM操作权，不新增constructor授权入口或按程序名准入。旧SDK未调用时行为不变。
未知wire版本严格拒绝，SDK能力清单必须绑定实际内核验收，不能仅由头文件推定。

提案匿名arena为 `[0x0000100000000000, 0x0000200000000000)`（16–32 TiB，低canonical
半区），不允许改动旧低地址窗口或supervisor映射。只为保留区建立VMA记录，不能为
数TiB guard预分配PTE或物理页。首版页粒度4096；每进程最多256个VMA片段，
累计保留上限8 TiB；一次保留最多4 TiB，alignment为4096至1 TiB的2幂。
提交页仍与ELF/堆/栈共用65536页（256 MiB）预算；页表和临时事务页另记真实物理
消耗，不能藏进保留字节。单次提交/保护/撤回/解除实际已提交页不超过4096页；
超过返回 `resources`，大稀疏保留的解除允许只遍历实际页表及至多256片段。
这些是提案工程上限，不是V8预算或POSIX最低值资格。

当前 create/copy/destroy 只枚举 PDPT[1]，user_range_ok 只接受旧窗口。
实现必须按**所属地址空间的用户页表/VMA**枚举新arena并回收所有层级，保留共享
supervisor页表；copy_to/from_user、SDK指针验证、wait结果区也须覆盖合法新arena。
单独扩大 user_limit 会开放中间地址且泄漏页，禁止这种实现。

V8源码 sandbox.h 描述1 TiB加前后32 GiB guard；本arena允许稀疏表达这些范围，
但现有ELF运行在首4 GiB内，与其低4 GiB inaccessible目标冲突。实际V8构建profile、
可执行映像重定位、cage/sandbox约束和失败策略仍独立 BLOCKED，不关闭sandbox、
不选 partially-reserved fallback 来宣布安全移植完成。

## 提议wire布局与返回

`sys_vm(first=request_ptr, second=0, third=0)`：请求只读，严格LE/x86-64 v1；64字节，
8字节对齐。输入先复制到内核快照；不写请求结构，不要求在待撤销范围内复制结果。
返回 signed i64：成功为地址或0，错误为下表负数。高arena地址小于INT64_MAX。

| offset | 字段 | 含义 |
|---:|---|---|
| 0 | u32 version | 必须1 |
| 4 | u32 size | 必须64 |
| 8 | u32 operation | 0info / 1reserve / 2commit / 3protect / 4decommit / 5unmap |
| 12 | u32 flags | reserve允许1=exact_nonreplace；其他必须0 |
| 16 | u64 address | hint或操作首地址；不接受外进程地址空间标识 |
| 24 | u64 length | 非零页倍数；info必须0 |
| 32 | u64 alignment | reserve使用；其余必须0 |
| 40 | u32 protection | 0NONE / 1R / 3RW / 5RX；其他拒绝 |
| 44 | u32 reserved0 | 必须0 |
| 48 | u64 reserved1 | 必须0 |
| 56 | u64 reserved2 | 必须0 |

info仅接受address=0、其余字段0，返回v1能力位：bit0匿名保留、1显式commit、2protect、
3decommit、4unmap、5strict_WX、6NX、7sparse；只有已通过该组合验收的位才可置1。
页大小、arena及限额由版本化profile常量冻结；统计复用扩展后的独立版本资源查询，
具体统计ABI尚未认领，不能向旧stats结构追加字段。

| 值 | 逻辑错误 / SDK errno | 情况 |
|---:|---|---|
| -1 | invalid / EINVAL | version/size/保留位/flag、对齐、零长、溢出、越arena、非法保护 |
| -2 | address / EFAULT | 请求指针不完整可读，含跨页/已撤销；无副作用 |
| -3 | denied / EACCES | W+X、改变非匿名VMA |
| -4 | resources / ENOMEM | 物理页/页表/片段/虚拟配额/工作量上限不足 |
| -5 | busy / EBUSY | 内核固定的等待word/输出区与撤销或保护降低相交 |
| -6 | unmapped / ENOMEM | commit/protect/decommit范围含无保留洞 |
| -7 | collision / EEXIST | exact_nonreplace范围已占用 |
| -8 | closing / ESRCH | 本进程关闭，拒绝新事务 |

这些数值仅属于提议sys_vm返回域，不改变现有 process_error/thread_error 数值。
错误优先级：请求可读性→wire/算术→保护→closing→VMA/碰撞→pin→资源。
SDK直接采用该域的独立映射表，不套现有错误转换。

## 操作与POSIX适配

reserve：创建NONE保留，返回实际地址，物理提交为0。hint碰撞可另选，exact_nonreplace
碰撞整次失败；不得覆盖ELF/栈/其他VMA。commit：对完整保留范围提交清零页并设R/RW/RX；
已提交页只允许相同保护的幂等调用，不改变内容；混合提交预先计划，失败整次不变。
RX新提交页仅有零内容，不凭空生成代码。
protect：完整范围须保留；对已提交页改变权限，NONE撤销全部用户读/写/执行但**保留
原内容及物理页**。对未提交页改为R/RW/RX时等价commit；任何失败原状保留。
decommit：完整保留范围变NONE并释放已提交页；再次commit保证零；保留虚拟所有权。
unmap：移除相交的匿名VMA片段并释放页；洞允许无操作成功；只触及arena。局部范围
按边界分裂，邻接同所有权/状态/保护片段合并；预留分裂槽失败不得先释放页面。

| SDK接口 | v1候选子集与明确限制 |
|---|---|
| mmap | MAP_PRIVATE\|MAP_ANONYMOUS，fd=-1、offset=0，长度向上取页且检查溢出；PROT_NONE先reserve，R/RW/RX须reserve+commit同一内核事务扩展后才开放；当前wire需两步，SDK失败必须unmap私有新保留且不得提前返回指针 |
| mmap flags | MAP_FIXED、MAP_SHARED、文件fd/offset、未知标志 ENOTSUP；XOS独立nonreplace选项只映射exact_nonreplace，不谎称MAP_FIXED |
| munmap | 地址页对齐、len>0、向上取页；局部释放/洞规则按上述定义；EBUSY为XOS偏差，不能称完整POSIX |
| mprotect | 地址页对齐、长度向上取页；NONE/R/RW/RX；W-only和X-only显式ENOTSUP，RWX EACCES；非匿名范围ENOTSUP |
| V8 | XOS平台后端显式reserve/commit/decommit；不得用其POSIX MAP_FIXED decommit路径替代安全实现；Recommit/Discard/Seal另行实现或返回不支持，不能空成功 |

POSIX接口属于目标子集设计，标准选项和所有errno仍须逐条审计；[Issue8 mmap](https://pubs.opengroup.org/onlinepubs/9799919799/functions/mmap.html)、
[munmap](https://pubs.opengroup.org/onlinepubs/9799919799/functions/munmap.html)、
[mprotect](https://pubs.opengroup.org/onlinepubs/9799919799/functions/mprotect.html)。
本轮官方页面读取403，未凭本设计宣称完成标准条款核对。

## 权限、并发和失败原子性

W^X是每个用户可达物理页的属性，非仅当前VA：不提供物理别名或共享页，fork eager-copy
得到不同页。NONE在x86必须清present并在内核持有原页所有权，不能只设NX（那仍可读）。
RW设置NX，RX清RW；内核临时物理直映为supervisor访问，不可映射给用户。
RW→RX、RX→RW修改必须先撤销旧访问、同步TLB，再发布新权限；全进程所有线程不能
在中间状态执行用户代码。拒绝RWX；不授予“JIT特权”，并发执行代码页改写由应用同步。
NX缺失平台拒绝该能力，不以软件检查替代CPU保护。

VMA元数据/等待pin/关闭仲裁属于通用core；PTE、NX、TLB和页表遍历属arch。
首期单CPU，每进程一个VM事务，进入时在调度临界区登记generation及所有权；同进程
后续VM调用阻塞排队，禁止持锁yield忙轮询。锁序：进程lifecycle→VM元数据/pin→
物理分配器；不得持有此序中的锁等待用户服务或其他用户线程。

请求已复制后可撤销其所在匿名页；syscall返回RIP/当前RSP所在页和所有线程栈/TLS
仍按既有专用区域保护，不在匿名arena。线程可主动在匿名arena运行代码，需调用方
同步；不能承诺unmap正在执行的任意应用代码后仍存活。内核不保存稍后要读的匿名指针。
所有会在阻塞完成时写用户内存的路径都要纳入pin：不止word，还含process_wait、
thread_join及显示等实际等待缓冲。pin登记/检查/撤销与VM事务使用同一生命周期锁。
撤销、decommit和降低写权限相交返回EBUSY；纯增权也不得在NONE后偷越pin。
进程退出先取消等待/事务并停止全部上下文，再销毁VMA和页表。

先预检所有VMA、pin、预算和分裂记录；分配新页和页表记录在事务owner的回滚链，
未提交前用户不可见。所有可失败步骤在发布前完成。4096页不能在一个关中断路径
逐页清零；分配/清零/扫描以最多32页批次通过**内核续体**让其他进程调度。
发布期间本进程用户线程暂停，其他进程仍可调度；PTE更新也分批，最终TLB同步后
一次提交VMA generation再恢复线程。续体记录在固定配额的内核事务对象，不塞1KiB+
数组到当前4KiB内核栈；暂存页/页表分配全部计数。

失败回滚删除本事务新增页表、释放新页/槽并恢复旧权限及计数；不将ensure_table
留下的中间页当可忽略缓存。发布后不得返回可恢复失败；内部不变量破坏按故障处理，
不能返回成功或留下半映射。退出/kill可取消未发布事务；发布中必须安全完成或恢复
后才销毁空间。SMP/TLB shootdown尚未设计/验收，profile明确拒绝SMP资格。

## fork、exec、线程和装载

单线程普通SDK的现有fork应复制保留VMA、保护状态、物理内容和配额；NONE但仍提交
的页不能因不present而漏拷。未提交保留不消耗子进程物理页。copy失败销毁完整子空间，
父空间内容/保护/计数不变。旧线程SDK继续拒绝fork/exec，不顺便开放多线程fork。
exec使用既有prepare/commit事务：先验证映像和地址图，再原子替换VMA owner；
失败保留旧VM，成功撤销旧generation、取消旧等待后从其他安全上下文回收所有层级。
旧ELF装载和线程prepare栈/TLS/guard布局保持专用所有权；匿名请求不允许重保护它们。

## 实现出口与文件责任

登记PR仅改本文、ABI认领、PX路线/state、源码审计工具与报告；不修改运行代码。
维护者合入后由VM负责人独占公共memory/task头、paging/tasks、SDK生成器和libc映射；
拆core VMA生命周期及arch页表适配，遵循原MIT与新Apache归属。实现PR同步两类SDK
manifest、错误、接口台账和[e04 SDK](../e04_loader_sdk.md)。

| Gate | 必须是真实新镜像/ELF行为，当前均 NOT_RUN |
|---|---|
| V1 | 大NONE保留无按页物理消耗；零页commit；同VA不同进程互不读写；地址溢出/冲突/跨界拒绝 |
| V2 | R写故障、RW执行NX故障、RX实际执行及写故障、NONE读/写/执行故障；RWX拒绝；guard实际异常及正常监督回收 |
| V3 | 中间/首尾partial unmap；洞/重用；NONE保留内容与decommit清零区分；所有片段/页表计数回基线 |
| V4 | 每一页/页表/片段注入耗尽；多阶段回滚内容/权限/计数完全不变；中断和kill清理续体 |
| V5 | 真实线程并发reserve/commit/unmap、word/process/join等pin busy、超时/wake/关闭竞态，无丢唤醒、无空闲轮询 |
| V6 | 正常/异常/kill/exec退出、未提交事务退出；单线程fork子拷贝隔离/失败；未知wire拒绝与旧ELF装载 |
| V7 | 同新组合E04、dash fork/exec/FD、T0–T3、QtCore/Gui/Widgets定向回归；新镜像独立截图、无损串口与资源收据 |

每项绑定源码SHA/SDK树与工具版本/系统与真实ELF SHA/QEMU命令/内存页、VMA/页表/任务/
等待/事务基线与终值；预期异常和原始失败保留。旧Qt/线程报告仅追溯，不能改绑重验。
通过V1–V7才认领“受限匿名VM公共能力”；V8语言、Web/DOM和应用/发行资格另验。
