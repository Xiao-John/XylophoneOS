# E04：用户态装载器与最小 SDK

实施于 0007。源码与最终证据见 `history/e01_e07.md` 和 `state.md`。
本页保留 E04 机制描述；当前文件服务、资源上限与流式装载以 e08.md 为准。
已有文件系统、newlib/FPU与E08-3原生binutils；尚无原生GCC/G++编译环境。
E08-2 的启动v2、argv/env/cwd、32页栈/4页startup、动态堆、显式driver构造权、
stdio/pipe与libc边界见 e08.md；下文v1上限保留历史，不覆盖该更新。

## 谁负责什么

`src/user/loader/elf.cpp` 在 ring3 解析 ELF；`load.cpp` 负责装载策略、BSS、
栈与 argv。GCC/G++ 构建的 supervisor 同时是用户态监督终端和装载服务，
不是新增一个必须先部署的通用服务框架。

内核不解析 ELF 或文件路径，只提供按持有者检查的创建、映射、提交、取消、
等待，以及只读启动模块的字节读取。初始 supervisor 的映射由宿主构建阶段
生成可信段清单，内核按清单启动它；这条 bootstrap 例外不用于普通程序的 ELF 解析。
其余六个旧平铺任务只作为 E03 回归夹具保留，旧 NASM supervisor 已由 C++ 程序替换。

程序来源是编进只读内核镜像的启动模块目录，`images` 显示标签和字节数。
它不是文件系统，不支持打开宿主路径；宿主只负责构建/打包，运行时所有解析、
复制、映射、执行和等待都发生在 XOS 客体内。

## 支持的 ELF 子集

ELF64、little-endian、ET_EXEC、当前目标 machine=62、版本 1，OSABI 0/3。
不因此兼容 Linux syscall 或 Linux 二进制运行环境。根据 program headers
装载，完全不靠 section 名称寻找代码/数据。

检查 ELF/PHDR 尺寸、最多 32 个 PHDR、最多 8 个非空 LOAD、文件范围与溢出、
filesz <= memsz、虚拟地址窗口、p_align 的幂与同余、页内偏移同余、段的页范围
不重叠、入口处于有实际文件字节的可执行段。非空 LOAD 必须可读，不能 W+X；
不同段共享一页也拒绝，避免合并权限产生 W+X。空 LOAD 不建立映射。

0019新增：静态PT_TLS接受有界初始化模板与零填充区；TLS布局由用户态ISA后端
完成，内核sys35仅为owned building子任务设置已映射的线程指针。AMD64 variant II
使用独立TLS arena和任务FS base；仅local-exec，无动态模块/DTV/线程。模板1MiB、
对齐64KiB上限，ELF LOAD不得覆盖TLS arena；失败abort回收。功能证据见0019。

拒绝 ET_DYN、PT_INTERP、PT_DYNAMIC、可执行 GNU_STACK 和其他未知
PHDR。NULL/NOTE/PHDR/GNU_RELRO 与非执行 GNU_STACK 只作为不参与装载的元数据，
不提供动态重定位、动态TLS 或 RELRO 后续重保护。节表不参与运行时重定位。

只读启动模块文件上限 128 KiB；E08-1 的工作盘 ELF 按段读取、不受该限制。
每程序最多 65536 个用户页（256 MiB），含 4 页栈。LOAD 地址范围为
`[0x40000000, 0x7fffb000)`，栈为 `0x7fffc000–0x80000000`，中间一页 guard 不映射。
ELF 各段逐页清零，再复制实际文件字节；BSS 与段尾保持零。实际页表按 RX/R/RW+NX
建立，所有用户页私有；内核的共享低地址映射仍为 supervisor-only。

解析器接受 machine 参数；架构特定 machine、syscall 指令和入口在
`src/user/arch/x86_64/`。解析器、装载策略、通用 SDK 和共享 memset 均通过
AArch64 编译检查；不表示系统已有 AArch64 移植。

## 生命周期与权限

create 得到 constructing 状态的子任务和父任务私有控制句柄（当前用单调 PID
表示）。map 只可操作自己尚未提交的子任务，物理页由内核分配，调用方不能传入
任意物理地址；复制源必须是父任务可读用户内存。commit 校验 RX 入口、可写栈、
对齐和启动信息映射后才进入调度。commit 后禁止继续 map 或 abort。

装载失败调用 abort，回收已建页、所有层次页表和内核栈，不让半成品进入调度。
构造权仅授予初始 supervisor，不继承给普通 ELF 程序；名字和 PID 不能授予权限。
进程句柄按父任务身份查验，PID 不重用，溢出前拒绝创建，旧句柄不指向新资源。

wait 只能收集自己的已提交子任务，未完成则真正挂起父任务，由子任务完成唤醒。
每个子任务预留一个完成记录；最多 16 份未收集记录，满时拒绝创建，不淘汰旧结果。
系统最多 8 个任务（含构造中任务与启动夹具）。结果只可收集一次：
`exited`（有符号 32 位退出码）、`faulted`（vector/地址/指令）、
`killed`（-9 为监督终止，-27 为 Escape 取消）。异常不会被伪装成退出码 0。

资源回收与结果记录分开：死任务在其他任务的内核栈上回收，完成记录保留到 wait。
修复 E03 漏回收 PDPT 的问题，并让所有创建中途失败走回滚。builder 退出/故障时
取消其所属子任务并丢弃它的完成记录；没有通用 orphan/adoption 或服务重启机制。

前台 `exec` / `wait` 挂起监督任务时，单独按 Escape 可终止被等待子任务并恢复
`sup> `，所以 `exec spin` 不要求重建镜像。它是固定串口控制机制，不是 POSIX
信号或完整 TTY；不撤销程序已产生的副作用。UART 输入仍是有限轮询，取消键应
单独发送，不保证长串未读输入后的控制键及时性。Ctrl-C 仍由宿主关闭 QEMU。

## 初始 ABI 与句柄

内核/SDK 共享 `src/shared/include/xos/process_abi.hpp`；内部 ABI 版本 1，升级需
共同重建。x86-64 的 `_start` 在 RDI 收到 48 字节 startup_info；内含 argc、argv
地址、0/1/2 标准句柄。CRT 按 SysV AMD64 调用 `xos_user_main`，返回值自动 exit。
这不是 Linux 初始栈协议。argv 最多 8 项（含程序名），每项最多 63 字节；
字符串与 NULL 结尾指针表置于栈顶一页，初始 RSP 在其下方，因此可用调用栈约 12 KiB。

stdin 只读，stdout/stderr 只写，当前都指向串口控制台；错误输出与正常输出
共用设备。继承的是任务内的引用，子任务关闭 stdout 不改变父任务 stdout。
旧 E03 write/read 入口也服从对应引用的关闭状态，不能绕过 close。

- write：单次最多 256 字节，0 字节返回 0，真实返回发送字节数；可短写。
  SDK 的 print 自动分块。普通 write 不补 NUL；串口可发送零字节。
- read：非阻塞，一次最多返回 1 字节；无数据返回 -3（would_block），0 长度返回 0。
  当前控制台没有 EOF，不能把无数据当作文件 EOF。
- close：失效后不可用，重复关闭/方向不符/不存在句柄返回 -1。
- -2 为无效参数或指针；-5 为资源不足/重复映射等构造失败；-6 为生命周期状态不符。
  底层构造错误目前较粗，不承诺 errno 或 POSIX 语义。

E04 当时 SDK 无 libc、堆、异常、RTTI、TLS、动态构造、浮点/SIMD 或标准 C++ 库；
E06 已把 newlib 作为 `libc_programs` 的可选 C 库接入，并加入每任务 SSE/x87
FXSAVE/FXRSTOR。旧窄 SDK 程序仍保持整数型。实际出现的 memset 由
`src/shared/runtime/memory.cpp` 完整实现，既用于 SDK 也用于内核。
内核编译仍使用 general-regs-only；E06 的 FPU 上下文边界见 `e06_libc.md`。
中断/syscall 入口 cld，用户 DF 不影响内核 C++，返回仍恢复用户保存的标志。

## SDK 产物与示例

`make build` 导出 `build/sdk/`：自包含 include/xos、crt0.o、lib/libxos.a、
特权装载服务使用的 lib/libxos_loader.a、user.ld、LICENSE/NOTICE 与第三方声明
和版本清单，全部由主 manifest 记录哈希。`scripts/user_build.py` 用同一份 SDK
构建 supervisor、demo、fault、spin、slow、echo；完整命令可从 manifest 复现。
各程序有带 DWARF 的 `user_NAME.elf` 和打包用的 `user_NAME.image.elf`。

```cpp
#include <xos/sdk.hpp>
extern "C" int xos_user_main(const xos::startup_info*) {
    xos::sdk::print("hello from XOS\n");
    return 7;
}
```

新程序目前需加入 user_build.py 的模块名单，再在宿主重建镜像；libc 程序还要
加入 `libc_programs`。没有客体编译器，不能假装已支持在 XOS 内添加源文件或编译。E05/E07 已加入文件服务、
编辑与持久工作盘（`e05_file_service.md`/`e07_persistent_work_disk.md`）。
为了容纳真实 ELF 模块，BIOS 原始内核暂存扩为 `0x10000–0x8ffff`（512 KiB），
内核含 BSS 上限 1 MiB；仍是专用软盘镜像，不写宿主分区。

## 验证与范围

`make smoke` 运行 E04 的 13 组检查和旧 36 组回归。ELF 24 个确定性用例在宿主
ASan/UBSan 与真实用户态各跑一遍；宿主另测截断和 512 组确定性变异。
bad_magic / bad_interp / bad_overflow 是目录中的故障夹具，走完整 exec 拒绝路径。
测试读取实际子任务页表，对照 ELF flags，检查 guard 和内核页；普通 demo 验证
BSS/data/argv/句柄，fault 验证私有页、只读页、NX；E06 后 FPU 探针正常退出 99。
10 次完整装载/等待/退出后，用真实物理页与完成记录计数确认不增长。

计划 O06–O08 的本版受限子集证据见 0007；不把有限矩阵提升为完整 ELF 合规、
通用安全证明、完整 POSIX 或所有运行库兼容。当前仍单核、无 SMP、
无动态链接、无长期压力测试。UEFI 不进入本组关键路径。

规范入口：[ELF gABI Program Header](https://refspecs.linuxfoundation.org/elf/gabi4%2B/ch5.pheader.html)。
受限子集与上界是 XOS 实施选择，gABI 不替代本轮实际运行证据。

## E08-1 会话补充

sys_file_session=27 是 files 专属的可信会话枚举；普通程序通过 ipc_handles 获得
自己的文件端点对。任务结束清理端点，服务按真实 PID 清理文件句柄/staging。
端点 token 单调不复用。文件协议升级为 v2；细节及界限见 e08.md。

0021用户库增量：SDK v5的__cxa_thread_atexit/强exit提供单用户线程的正常TLS析构，
不改ELF装载/内核ABI；main-return/显式exit的LIFO、TLS先于global/fini已客体验证。
无动态TLS/线程/DSO卸载。详情见e08.md与e08.md。

## 0027：用户态执行候选与诊断

新增execution.hpp及loader/command.cpp：候选检查/有序PATH搜索保留在用户态，
不看扩展名，分missing/directory/executable/not_executable/incompatible/unreadable。
最终装载仍保持同一打开文件跨校验/映射的锁定，不以预检代替最终保证。
spawn_file_diagnosed返回open/inspect/prepare/create/map/start阶段、错误码与ELF
原因；旧spawn接口行为保留。完整策略见xsh.md；不是任意ABI或完整脚本执行支持。

新增sys_debug_trace=36：first为0/1，second/third必须0；仅真实bootstrap supervisor
可改变正常进程生命周期日志，driver构造权不包含该权限。错误输出不受其影响。
这是增量调用，没有改动既有启动结构/调用编号或赋予普通任务新权限。

## 0028：受限构造权委派

`sys_process_grant=28`保留旧语义：仅bootstrap supervisor可给自己的building直接
子任务一层构造权。`sys_process_delegate=37`是新的显式扩展，深度上限3；非supervisor
调用者必须自身至少有2层，只能修改自己尚未启动的直接子任务，且委派值必须
严格小于自身。委派拒绝使用独立`process_error_delegation=-10`，避免与文件服务
`not_found=-1`混淆；libc映射为EPERM。

新增`sys_boot_payload=38`：仅真实bootstrap supervisor可调用；first=offset，
second=目标用户地址，third=长度；third=0且second=0时返回payload总大小。
payload来自ISO的`DASH.ELF`，上限1 MiB，不授予普通任务；`/usr/bin/dash`已存在
时安装器不覆盖。旧syscall编号不变。

`spawn_options.delegate_spawn_depth`由用户态启动策略显式设置。Xsh对裸`dash`设为2，dash的
固定GNU driver profile经xos_posix_spawn_driver给gcc/g++设为1。内核仍只检查调用者、
直接子任务归属、building状态和深度，不识别文件名、PATH、ELF工具身份或GCC。
最终客体验收覆盖旧一层兼容、无权委派回滚、dash→GCC/G++→子工具链和资源复原；
不因此声称任意进程树、fork、collect2或完整POSIX授权。

## 0031：待实施的公共线程契约

E13-T语义已确定，见[threading_contract.md](threading_contract.md)。这是后续ABI/
SDK计划，尚未新增thread syscall或修改本页已实现接口。T0须同步版本化请求、
线程栈/TLS保留区及ELF布局兼容策略；内核只提供映射/线程/等待机制，TLS模板
解析与复制仍在用户态。进程PID/权限/会话/地址空间与线程TID/上下文分开；
现有进程wait/kill/委派保留进程语义，T2前不声明线程安全SDK。

## E13-T 线程 ABI v1

本分支新增 sys38–52，保留 sys0–37、startup v1/v2、process_status 和
process_stats 的布局及进程权限含义。共享 ABI 见 `thread_abi.hpp`，具体布局、
地址保留与兼容策略见 [线程实现](threading_implementation.md)。
新 SDK 是独立 profile；旧 ELF 继续装载，若占用新线程 arena，显式 opt-in
返回 ENOTSUP，不能静默覆盖映射。用户态 ELF 策略仍在 loader，内核不解析 TLS 模板。

## 0041本地整合补充

已拉取d89d1a3线程PR；本地未发布ISO sys_boot_payload避开线程38–52改为53。
文件wire仍v2布局，B2追加操作保留旧工具入口；私有spawn FD快照与有锁的seek/
transfer共同整合。7组整合gate见work_log/0041_threading_local_merge.md；B2随后由
0042以新SDK正式收口，证据绑定build `911184be3f3c99f6`，不借用旧回执。

## 0048：P2-1通用进程准入与文件写租约

2026-10-26追加`sys_process_guard=54`，53仍为ISO payload，38–52线程ABI不变。
first为process_guard_action（query0/begin1/end2/rearm3），third必须0；query的
second指向16字节process_guard_info（owner_pid/worker_pid），其他动作second为0。
begin/end/rearm仅真实supervisor可用，普通应用返回denied；begin拒绝其他存活或
构造中应用（files服务除外），busy为process_error_busy=-11。屏障内仅owner能
创建一次worker；不授予构造权，不接受grant/delegate。end/rearm要求旧worker已死，
不重用PID。内核只管理生命周期与准入，不处理路径、包、数据库或journal。

file v2 wire布局保持不变，追加op20 maintenance_acquire、op21 maintenance_release，
Client增加对应方法。files对每个请求读取kernel guard状态：仅指定worker可取
写租约，取租约前所有打开实例和单文件staging必须为空；普通应用不能按伪造PID取权。
屏障或租约有效时，写/有写选项的open/replace/remove/mkdir/rename/sync均要求
该worker持租约；其他只读操作可用。只有真实owner session能释放，释放前要求
打开实例和staging清空，并同步块设备。worker退出不会自动解除全局写门禁。

Xsh入口见usage/supervisor/maintenance.md，定向证据见0048。这不是新线程SDK
profile，也不是P2完整包事务；旧静态程序的已有操作布局保持，SDK/服务/内核新操作
需要对应实现。持久恢复策略留用户态xypm P2-2，当前不开放客体安装/升级/卸载。

## 0047：C1 管道等待与前台流水线（实验分支）

保持 sys0–53 与 startup v1/v2 布局。sys54 `sys_pipe_wait(token,0,0)` 接受本进程
pipe token 或 0–2 的有效内核 stdio route；console 返回 would_block，不睡眠。
可读为有数据/最后 writer 已关闭；可写为有空间/最后 reader 已关闭。
校验、检查、登记 blocked 在单核不可抢占内核中原子完成；允许伪唤醒，调用方
必须重试 I/O 并重新验证 token。每次 close 和数据流动唤醒等待者，slot 回收前
广播；token 单调不复用。底层 read/write 仍可短读写并返回 EAGAIN，新增 libc
在管道 EAGAIN 后阻塞重试，不把 console 的旧非阻塞语义改成 EOF。

sys55 `sys_process_foreground(&request,active,0)`：request 为48字节固定宽度
`process_foreground{version=1,size=48,count,reserved=0,pids[4]}`；未使用 PID 必须0。
每个 PID 必须有属于调用者的 completion，且不重复。active=1 从开始构造流水线
起登记（count=0合法），每段启动后更新；Escape 取消全组并锁存 cancelled，后续
active 更新返回 state，调用者停止构造并清理本地已启动列表。active=0/count=0
撤销登记并清锁存。它是有界前台取消机制，不是 POSIX process group/作业控制。

sys56 `sys_process_cancel(pid,0,0)` 仅接受调用者有构造权的直接、已启动子任务，
不接收任意 PID/信号；停止子任务及其后代，保留 completion 待 wait 消费。
sys20 第三个参数现接受0（阻塞）/1（完成查询）；未完成时查询返回 would_block，
libc waitpid(WNOHANG)返回0，不消费记录。其他位拒绝。
sys34 的 PID=0 分支只查询自己的 stdio route，第二参数fd、第三参数0，返回
1 console/0 pipe/负错误；libc isatty据此区分继承的pipe与console。

libc FD表锁不跨管道等待；在途 I/O pin住对象，普通 close 不中断该在途 I/O；
直接raw close唤醒后，raw等待者再次I/O必须重新验证权限。F_SETFL对未实现的
O_NONBLOCK等位明确ENOTSUP，writer F_GETFL报告O_WRONLY。未增加异步信号递送。


## 0048：C2单线程完整复制fork（实验分支）

sys57 prepare(0,0,0)为具构造权的普通、未启用线程profile的主线程复制完整用户
页（有效RW/X）、heap、TLS/FPU、stdio/pipe引用与raw token。新PID/TID/内核栈/
文件端点/完成记录独立，child保持building，复制帧在child返回0。fork继承同一
principal的构造权限，不增加权限，独立fork depth限3。无COW，无多线程atfork。

sys58 commit(child,0,0)限源父且要求files已ACK，才允许复制帧运行；普通sys18
不能启动fork_pending。sys59 files(child,source,0/1)只允许files服务调用，每次
重新验证活源父与其building fork child；0只查询授权，1仅在克隆完后置ACK。
文件op20 clone_session保持v2 wire、以会话实际PID为源、offset为目标PID，逐
打开实例保号retain并提升目标generation高水位；不克隆staging事务。ACK失败
回滚本次引用。任意被复制Client首次call按当前PID重绑自身端点。

libc fork按prepare→有界克隆RPC重试→commit执行，失败abort；线程SDK与线程
profile明确ENOTSUP，普通无权EPERM，深度/配额/物理页不足返回真实资源错误。
进程数仍8，用户页限仍256MiB，fork代价为全部已映射用户页+页表+内核栈。
完整SDK必须和当前头/库共同重建；旧静态工具的sys0–56与文件v2行为保留。


## 0049：C3 exec v3与匿名输入实例

sys61 exec_prepare(0,name_ptr,name_len)允许普通无构造权任务准备自己的唯一replacement
事务（重复EBUSY），保护supervisor/files，拒绝线程profile/非唯一main。stage占全局8
进程配额但不运行，无完成记录、文件会话或stdio/pipe引用，只允许父map/tls/abort，
普通start/grant/delegate/stdio不能把它变成可运行子任务。

sys60 exec_commit(stage,&entry,depth_mode)在同一不可抢占提交前完整验证stage所有权、
RX入口/栈/startup、源文件会话和新endpoint token配额。mode0保留构造深度，n>0
请求n-1且必须严格小于源深度。成功保留原PID/TID、父/完成记录、子任务、stdio/raw
pipe引用；切新CR3/TLS/FPU/栈，重置heap，再在新CR3下回收旧映像与stage内核栈，
直接返回新入口。原2个文件IPC slot在同PID下换新opaque token并清旧队列；服务
保留同PID打开实例，新Client获取新token，不重用旧响应命名空间。

startup v3保留v2前缀，offset152追加24字节exec extension；descriptor记录24字节，
最多32项，按object id恢复共享别名，省略CLOEXEC FD；仅余CLOEXEC的对象由新CRT
在main之前关闭。文件handle仍属于同一PID，不按路径重新打开；file/pipe/kernel
routes都保留实际打开实例与偏移。成功替换后若底层关闭I/O失败，FD表已关闭，
诊断deferred cleanup且服务重试；它不是返回旧程序的exec失败，不声称I/O故障下
所有清理已完成。缺文件/格式/旧ABI/权限/配额/映射ENOMEM等提交前失败保留旧映像
和FD表，实际场景见C3 exec专项。

完整exec要求目标ELF保留只读ALLOC `.xos.exec` PROGBITS节，16字节为
magic `0x3349424143455858`、version3、size16。当前匹配的CRT/linker/libxos共同
生成和消费它；旧静态程序不理解v3，显式exec返回ENOTSUP。普通spawn继续v1/v2
兼容旧GCC/G++/CPython；绝不以spawn+wait冒充exec。新SDK不可与旧CRT/库混搭。
execv3每参数/环境串最多4095字节；普通spawn仍255。argc/env各64、总startup16KiB。

file wire v2追加op21 anonymous、op22 anonymous_seal。服务用保留8.3名字
XOS00000.TMP…XOS99999.TMP排他创建，不能覆盖碰撞文件，普通路径操作不能访问，
listing隐藏；seal不可逆地撤销共享实例写权限且保留偏移。Here-doc填充/seek0/seal
后才交stdin，正文不会卡在4KiB pipe里。最后close或退出/kill回收引用时删除，
I/O失败保留待清理实例并重试；不扫描删除崩溃遗留，无法证明跨崩溃文件所有者。
单会话16/global32打开实例等既有配额保持。普通Client也使用跨实例单调request ID，
init不重置、溢出拒绝；不宣称任意超时/迟到事务的完整重放或恢复。

C3收口另补小pipe write原子性：当前SDK对<=4096字节的pipe write等待完整空间，
不能以可用的少量字节短写后和另一writer交错。sys54的second新增writer最小空间
1..4096（0保留旧any-space语义），read仍必须0，第三参数0；检查/入睡仍原子。
继承stdio的pipe不再错误套console的256字节上限，console仍限单次256；大于4096
的write仍允许短写。新SDK与支持该readiness扩展的内核共同使用，旧有效second0
调用保持兼容；不承诺writer公平性、信号SIGPIPE或完整POSIX。

为保留原raw sys11/32的短写ABI，小写原子性采用handle bit63显式opt-in；无flag
完全保留原非阻塞短写行为，旧C1等待者second0不会因语义改变忙重试。当前newlib
对pipe小write自动置flag并以sys54 minimum等待，console不置flag；带flag大于4096
明确EINVAL，非flag大write仍可短写。SDK header/manifest公开该位与matching需求。

普通spawn若继承files服务stdio，同样要求目标声明当前CRT能力。冻结的旧GNU版本
不仅不懂v3，也不识别B2 file_handles；此前会忽略继承信息，stdout写失败但工具仍可返回0（本次实际导出为空）。现在
未知/旧目标的文件stdio继承明确ENOTSUP，不以path重开冒充共享实例；旧console
启动及实测native编译保留，阻塞pipe/文件stdio完整保证限匹配的当前SDK。旧B2
无能力标记的二进制需要用新SDK重建；xypm旧profile也须独立登记/迁移，不能推断
它能接受新继承形式。这是显式ABI admission，不能声称所有旧静态stdio都兼容。
