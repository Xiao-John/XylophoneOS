# 虚拟内存与 COW fork 实施路线

2026-11-12 更新。VM0–VM3 已实现，VM3 的 SDK 能力仍为 `implemented_unqualified`，
其 V1–V7 正式资格尚未完成，见[VM3 恢复记录](../work_log/58b24599_vm3_lifecycle_sdk.md)。
COW0 已冻结[契约与失败矩阵](../contracts/cow0.md)；COW1 的真实 fork 和用户故障
路径已通过隔离探针定向验收，完整资格仍须 COW2、COW-L1/L2 和 COW3；不修改宪法，
不开放多线程 fork。下文历史基线描述仅供追溯，当前审计以 COW0 为准。
现有匿名 VM 契约仍为主依据：
[已合入的 PX4-A 提案](https://github.com/Xiao-John/XylophoneOS/blob/d57ff0e4674d297c6d4e1e20e3ba16a76dec3d57/docs/contracts/anonymous_vm.md)。
sys67 已实现但尚未资格认证；VM1 专用探针诊断不作为公共 ABI 分配。
不另分配 COW syscall，沿用既有 fork prepare/commit/abort 的用户态协议。

## 已核源码与真实缺口

基线 a2ccab1：paging.cpp::copy_user_pages_in 只遍历 PML4[0]/PDPT[1]，
立即分配并拷贝每个 present 用户页；destroy/create 同受旧地址图约束。
tasks.cpp::prepare_fork 只允许普通单线程主线程，并在准备完成及文件描述继承确认后
commit 才使子进程可运行。保留该授权/文件协议及失败回滚，不把 fork 改成隐式 spawn。
copy_to_user 当前是原始虚拟地址 copy_bytes；user_range_ok(write) 要求硬件 RW。
当时物理分配器没有共享用户页引用计数；当前 VM0 已具备用户页引用计数。直接清 PTE.RW 会使合法 copyout 被拒绝，或在
ring0 写保护故障中 panic；只添加用户 page fault 分支不足以实现 COW。

## 设计边界

core 负责地址空间对象、VMA、页对象引用/权限、配额、pin、事务和生命周期。
arch 负责页表遍历、有效权限、故障位解释、映射发布和 TLB；不要把 PTE 位布局写进
共享 SDK。ELF 和文件映射策略在用户态。内核处理自身地址空间的映射机制有实际必要：
用户服务不能替 CPU 撤销访问、处理保护故障或管理共享物理页的安全回收。
匿名 VM 不授予设备 MMIO/DMA，不把网络驱动或 Qt/V8 特例带入内核。

先保持单 CPU。只读不可变页与逻辑可写的 COW 页分别标识；PTE 只读不是 COW 的
充分条件。实际页权限、VMA 逻辑权限、是否提交、共享引用、pin 和 generation 独立。
NONE 但保留内容的已提交页不能因 PTE 不 present 被遗失。每进程逻辑提交预算与
系统真实唯一物理页/页表/暂存消耗分别计数，共享不能绕过原有进程预算。

## 分阶段交付与依赖

| 阶段 | 实施内容 | 验收出口 |
|---|---|---|
| VM0 所有权底座（受限通过） | 用户页对象/引用管理；全用户地址图遍历；core/arch边界；逻辑写权限与硬件写权限分离；统计方案 | 旧 E04/fork/exec/堆/线程定向回归，注入失败精确回收；仍使用 eager-copy |
| VM1 匿名保留（专用探针受限通过） | 按既有 sys67 wire、16–32TiB arena/256片段及预算实现 reserve/unmap；稀疏元数据，不按保留字节分配页表 | V1/V3 的保留、溢出、碰撞、分裂、洞、退出与页表计数 |
| VM2 提交与保护（专用探针受限通过） | commit/protect/NONE/decommit、W^X、跨页 copyin/out；32页有界续体；pin 与进程关闭仲裁 | V2/V4/V5；真实 fault、事务回滚、等待输出 pin、kill 清理，不能以宿主测试代替 |
| VM3 生命周期与 SDK | eager fork 复制全部 VMA及隐藏提交页；exec原子替换；两类SDK与libc子集；不提前公布 supported | V6/V7，完成既有 V1–V7 后认领受限匿名VM |
| COW0 契约冻结（已完成文档） | 页引用/逻辑权限、copyout、fork失败原子性、OOM及统计冻结；规定后续保留 eager 对照 profile | [源码路径清单与故障矩阵](../contracts/cow0.md)可独立评审，无新公共 ABI；本阶段不实现 profile |
| COW1 fork 快照（隔离探针受限通过） | 隔离探针中子页表独立；私有可写页共享并撤硬件写权；只读页共享；父TLB同步；复制VMA | 真实用户态多代、共享、权限、故障、取消和定向失败测试通过；父先退出及完整生命周期留待 COW-L2/COW3，见[工作记录](../work_log/cow1_snapshot_progress.md) |
| COW-L1 生命周期契约及任务域 | 区分父子等待关系与任务域取消；设计收养、完成记录、构造中子进程和现有监管的迁移 | 明确授权、资源和 files/通道归属；现有默认语义在迁移前不变；契约评审通过 |
| COW-L2 生命周期及任务域实现 | 构造中子进程随构造者回收；已提交进程可被收养；任务域提供显式整体取消 | 父正常/异常退出后子进程存活、收养和回收；显式取消覆盖多代；既有 shell、服务及 eager fork 回归 |
| COW2 所有写入路径 | 用户保护故障与内核copyout共用分离机制，wait_word/输出pin策略落实 | 用户写、pipe/file/read、IPC recv、random、wait/join等逐路径验证；非法写仍异常 |
| COW3 资格 | 全失败回滚、exec/退出/kill、共享映射扩展规则、受影响应用及资源性能对照 | COW-L1/L2 和 COW2 通过；真实父先退出后子写入、eager与COW内容/权限/errno等价，真实物理节省与耗时单独报告 |

VM1/2 可在同一个实现 PR 分步构建，但不能交付会让旧 fork 漏拷匿名页的组合：
公开匿名能力之前必须包含 VM3 的 eager 兼容路径。COW可在VM0后用旧窗口原型化，
主线优先完成匿名VM基线，再启用COW，降低同时改地址图和共享所有权的调试成本。
文件/共享映射为 PX4-B 独立路线；无需等待文件映射才开始匿名私有 COW。

## 进程生命周期裁决

保留 COW0 父先退出的验收要求，将其真实进程场景列为 COW-L2 和 COW3 的出口；
COW1 可先在隔离探针中验证父地址空间先销毁、引用回收和其余快照事务，但不得把这些
替代真实进程测试，也不得据此开放普通 COW。COW-L1/L2 可以与 COW2 并行；现有
`finish_task` 的递归取消在生命周期迁移完成前保持，不能在 COW1 单方面移除。

目标模型借鉴 POSIX：父子关系负责等待、退出状态和收养；已提交子进程不因父的正常
退出而自动死亡。独立任务域承担跨代的显式取消和监管；它不自动等同 POSIX 进程组、
会话或 shell job。构造中子进程仍随构造者取消，终端前台和任务域的关系须另行定义。
迁移设计必须具体规定异常退出、监管者死亡、收养者不可用、配额、完成记录、files
会话、通道及设备授权，兼容现有 shell 前台取消和服务安全边界；先提供明确迁移路径和
回归测试，再改变默认行为。完整 POSIX 信号及终端 job control 不作为 COW-L2 的隐含承诺。

## COW 的执行与失败约束

fork prepare 先校验额度、构造子页表并预留引用/回滚记录；所有可失败步骤先完成。
父映射撤RW、子映射发布及TLB失效必须在父用户线程不运行的窗口完成；子仍 building，
待既有 files/stdio/pipe 继承成功才 commit。后续服务继承失败须撤子引用，恢复父逻辑
内容与访问行为；安全残留 COW 标记也须明确契约，不允许泄漏额度或变成不可写页。
共享页 ref=1 可恢复可写而不复制；ref>1 时先分配复制、再换 PTE/失效 TLB/减旧引用。
任何失败不先释放旧页或错误授予写权；引用计数溢出、未知页归属严格拒绝。

用户写保护 fault 只接受有效用户、present保护故障、逻辑可写且已登记 COW 的私有页。
NX、真正只读、guard、内核地址与未提交页不走 COW。COW分配失败无法从普通 store
返回 errno，终止故障进程并记录 OOM 原因；其他共享者继续有效。系统调用 copyout
先准备全部目标页或按该操作既有短写契约执行，分配失败返回其定义错误，不触发内核
panic，不虚报全量成功。跨页请求检查溢出、权限与期间 generation。

等待 word 不能固定在被其他上下文更换的共享物理页：登记写/读pin前按其访问语义
处理私有化，并确保等待/唤醒仍基于同一进程逻辑地址和稳定映射。阻塞输出区在等待前
完成可写化及pin；VM降低权限/decommit/unmap按既有提案返回busy，结束/取消释放pin。
内核物理直映写用户页也必须通过拥有者校验及COW分离，不得绕过copyout。

退出/exec/unmap 释放的是映射引用，最后一个拥有者才释放页；页表独立计数。
真正 MAP_SHARED 页未来保留共享写语义，不统一转COW；MMIO、DMA、内核页、共享
supervisor映射不得混入普通私有页快照。当前不承诺SMP shootdown或多线程fork；
后续开放前另定停线程、atfork、锁与故障并发契约。

## 必须冻结的验收矩阵

- 同VA父子不同值，分别先写/不写，连续多代与父先退出，RX/R/NX/NONE/guard真实CPU行为。
- 文件/管道/IPC/random/等待结果等内核写回到COW页，跨页含只读端，失败不污染其他进程。
- 按第N个数据页/页表/引用记录注入OOM，prepare失败、files继承失败和abort均精确回收。
- fault OOM只影响故障者；exit/kill/exec/部分unmap、隐藏提交页及等待取消后引用归零。
- 单线程限制及现有spawn委派/FD共享描述语义保持；dash fork/exec和适用xsh入口分别验证。
- 记录逻辑提交、唯一物理页、页表、pin、事务、任务和完成记录基线；不把缓存/遗漏回收算节省。
- eager/COW同输入结果对比；无写fork与逐页写分别报告内存和耗时，时钟量化明确记录。

每阶段绑定提交、源码manifest、SDK树、ELF/镜像/工具哈希、QEMU命令与原始失败日志。
新实现只重跑受影响定向项，压力由专项执行者负责；编译通过不作为客体资格。

VM2续体与pin基底见[基底计划](vm2_foundation.md)；页面操作和当前验证范围见[工作记录](../work_log/2d8a0516_vm2_page_transactions.md)。补充验收见[完整验收记录](../work_log/588667af_vm2_full_qualification.md)；公开能力仍须 VM3 和 V1–V7 组合验收。
