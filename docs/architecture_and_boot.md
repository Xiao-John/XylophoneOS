# 架构边界、启动契约与 UEFI 时机

E01–E08-1 实施记录，2026-10-24。当前仅实现 x86-64 / QEMU PC / BIOS。
E08-1 的资源/文件会话更新见 e08.md；下文 E03/E05 段落保留阶段历史。
E08-2 新进程布局和运行时边界见 e08.md；ELF解析仍仅在用户态。

## 依赖方向

| 位置 | 负责 | 不应渗入通用代码的内容 |
|---|---|---|
| `src/boot/x86/` | BIOS 装载、E820 整理、A20、模式切换与临时页表 | BIOS 中断、CHS、启动扇区布局 |
| `src/kernel/arch/x86_64/` | 内核入口、链接布局、CPU 操作和端口指令封装 | 寄存器、汇编、页表位与异常栈格式 |
| `src/kernel/platform/pc/` | 当前 PC 的 COM1/VGA 调试输出 | 设备地址、端口号、VGA 文本格式 |
| `src/kernel/include/xos/` | 真实使用的整型、启动信息与窄平台接口 | 不包含 BIOS/UEFI 原始结构或 x86 类型 |
| `src/kernel/core/` | 启动信息验证、通用内核行为 | 不含内联汇编，不直接访问设备 |
| `config/` | 工具版本、目标选择、调试入口 | 不把宿主 CPU 特征自动带进客体 |

目前只有 `debug_init/debug_write` 和 `arch::name/halt` 等确实有实现的窄接口，
没有空 HAL、通用驱动框架或未使用回调。构建显式选择 core、x86_64 和 pc 的源文件。

每次 `make smoke` 将全部通用 C++ 文件编译成 AArch64 ELF 对象，作为耦合检查。
没有 AArch64 引导器或平台实现；这不是第二条 OS 开发线，也不是移植成功。

## 默认 BIOS 启动通路

启动扇区仍从 `0x7c00` 将后续 16 扇区装到 `0x8000`，但默认第二阶段改为
`kernel_loader.asm`。原来的命令行只保留在 `real_mode.img`。
默认镜像从 LBA 17 起存放由 ELF 导出的原始内核，实际扇区数见 manifest。
第二阶段逐扇区 CHS 读取，越过磁道时重新计算 C/H/S，读失败最多三次。
每次读取 512 字节，避免跨磁道/64 KiB DMA 边界；不依赖通用文件系统。

引导器检查 CPUID 的 long mode、NX 与 PAE，收集最多 64 个非空 E820 条目，
忽略被禁用条目、将未知类型当作保留内存，拒绝失败/不完整/过大的内存图。
检查内核含 BSS 的目的范围被可用 RAM 覆盖，启用并探测 A20。
进入 32 位保护模式后将内核从低内存临时副本复制到 1 MiB，再建立临时页表、
启用 long mode/NX/WP，跳转到独立 ELF 的 `kernel_entry`。

这仍是限定 QEMU 机型的 bootstrap，不保证任意 BIOS/固件、硬盘或真机启动。
内核载荷为受信构建产物，尚无 BIOS 载荷运行时校验和或安全启动。
E04 的用户态 ELF 解析属于另一层机制，详见 `e04_loader_sdk.md`。
构建器从实际链接符号生成 `kernel_layout.inc`，而不是手写第二份内核尺寸。

## 当前物理布局

| 地址 / 范围 | 用途 |
|---|---|
| `0x1000–0x5fff` | PML4、PDPT、PD、两页 PT |
| `0x6000–0x65ff` | 最多 64 × 24 字节规范化内存条目 |
| `0x6800–0x683f` | 64 字节 `boot_info` |
| `0x7c00` 向下 | 引导栈 |
| `0x7c00–0x7dff` | 第一阶段 |
| `0x8000–0x9fff` | 第二阶段装载窗口 |
| `0x10000–0x8ffff` | 原始内核暂存，E04/E05 文件上限 512 KiB |
| `0x100000–0x153000` | 内核、只读启动模块、files/supervisor、libc_hello、BSS、IDT、位图和栈；总上限 1 MiB，实际见 manifest |
| `0x400000–0x1fe00000` | 4–512 MiB 的 2 MiB identity 页，RW + NX；让分配到的物理页可直接访问 |

引导器将低于 1 MiB 的范围整体标为保留，不让后续分配器当作空闲。
当前页表前 4 MiB 用 4 KiB 页 identity-map，再用 2 MiB 页覆盖 4 MiB–可用
上限；零页缺席，所有映射 supervisor-only。loader/text 为只读可执行，rodata
只读 NX，数据、启动栈和其他映射可写 NX。CR0.WP 与 EFER.NXE 开启，自动测试
读取客体实际页表检查 W^X，并检查 4 MiB 以上的 identity 页带 NX。
这不是完整 VMM：引导/内核栈没有 guard，内核 identity 窗口较宽。
E03 私有地址空间、E04 用户栈 guard 和回收机制另见后文与 E04 文档。

## E02 异常入口与 panic

内核安装自己的 GDT（内核 code/data + TSS）和 256 项 IDT；向量 0–31 有独立
汇编入口，CPU 不推错误码的向量补 0，保证统一栈帧。TSS 提供 `rsp0` 和两个 IST：
double fault 用 8 KiB IST1，NMI 用 4 KiB IST2。IDT 向量 8 的 IST 字段为 1，
向量 2 为 2，自动测试从客体内存读取 IDT 验证。

`exception_dispatch` 读取异常帧中的 vector/error/RIP/CS/RFLAGS，page fault
另读 CR2；ring0 交给通用 `panic` 输出后 HLT，E03 起 ring3 终止当前任务并继续调度。
内核入口保持关中断，进入 ring3 后启用 PIC/PIT，尚无 APIC。
自定义 `int 0x30` 因门不存在触发
#GP；错误码可用于定位选择子。double fault 的 IST 由真实坏栈故障验证，而非
只检查配置。

## E02 物理内存与基本映射

`memory_init` 消费规范化 E820：4 KiB 页位图覆盖到 512 MiB 上限，只把
`usable` 且不低于 1 MiB 的页标为空闲；内核镜像/BSS/栈、引导信息页、页表与
loader 低端暂存不会再次分配。每页有两张位图（保留/已分配），因此 free 未分配
页或 double free 返回 `invalid`，不会误放固件内存。分配返回零页，释放不清零。

`map_page`/`unmap_page`/`query_page` 只处理当前内核地址空间的 4 KiB 页：
按需分配并清零中间页表页，叶子支持可写/可执行/用户位，写入 NX 禁用执行；
中间表不回收，unmap 也不释放物理页；没有反向映射，释放已映射页不会自动撤映射，
调用者必须先 unmap 再 release。遇到 2 MiB 大页时不拆分，返回 `invalid`。
自检分配一页、映射到 `0x40000000`、写读校验、重复映射返回 `already_mapped`、
解除映射并释放，失败则启动失败。位图上限、identity 窗口和“不回收中间表”都是
bootstrap 限制，不是最终 VMM 策略。

## E02 调试控制台

串口提供最小同步调试命令行：`help`、`mem`、`alloc`、`free`、`vmtest`、
`pf`/`gp`/`ud`/`div`/`df`（故意触发异常）和 `halt`。它直接轮询 COM1，
没有中断、环形缓冲、流控或 VGA 键盘输入；用于 E02 的故障与内存检查，后续
终端服务应迁往用户态，不能把这套命令当成最终终端 ABI。逐条语法与边界见 `docs/usage/index.md`。诊断先输出事件/结果，
再停机，不吞掉异常。

## E03 用户任务、抢占与 IPC

GDT 增加 ring3 code/data 描述符（0x2b/0x33）；TSS 仍占两个 GDT 槽，所以用户
选择子不是 0x20/0x28。每个任务有独立的 4 KiB 内核栈，切换时更新 TSS `rsp0`。

地址空间按任务创建独立 PML4：内核 0–512 MiB 的页表共享且 supervisor-only，
用户半区在 1 GiB 处私有。用户代码映射在 `0x40000000`（RX），数据页在
`0x40010000`（RW+NX），4 页栈在 `0x4001c000–0x40020000`（RW+NX）。用户程序
在 E03 阶段是嵌入内核的 NASM 平铺二进制；E04 保留六个夹具，supervisor 与
动态程序使用 ELF/SDK，当前机制见 `e04_loader_sdk.md`。

八个静态任务是 `heartbeat`、`spinner`、`receiver`、`sender`、`probe`、`quitter`、
`supervisor`、`files`；其中 spinner 永不主动让出，probe 先试非法 IPC 再读内核页，
quitter 通过 `exit` 退出，supervisor 提供用户态 `sup> ` 终端（`ps`、`kill <pid>`、
`help`），files 是 E05 的 RAM 文件服务。调度为 round-robin，只从 ring3 被中断时
切换；内核入口保持关中断，不做内核抢占或嵌套调度。

PIC 重映射后只开放 IRQ0，PIT 以 100 Hz 产生 tick，处理函数发 EOI 后选择下一个
可运行任务。计时目前只是 tick 计数，不是墙钟，也不给日志伪造时间戳。

`int 0x80` 是 DPL3 系统调用门：RAX 为编号，RDI/RSI/RDX 为参数，负数返回错误。
当前支持 `write`、`exit`、`yield`、`send`、`recv`、`getpid`、`ticks`、
`read`、`tasklist`、`kill`，以及 E05 的 `ipc_handles`。用户指针
先按地址范围和页表项检查（可读/可写），再复制；内核不直接解引用未验证指针。

IPC 是 4 个端点、单槽邮箱；E03 端点容量 64 字节，E05 文件端点容量 4096 字节。
发送权和接收权按任务静态记录在 task 记录中。无效句柄、缺少发送权、超长消息、
内核指针、队列满/空都返回错误，不静默截断为成功。当前没有阻塞等待、队列深度、
撤销或多消息批处理；文件协议用请求/响应和会话号规避迟到回复与半写。

ring3 异常（含 page fault）打印任务 pid/vector/RIP/CR2 后标记该任务 dead，并
切换到下一个任务；ring0 异常仍走 panic+HLT。退出/被杀的当前任务不能在自己的
内核栈上释放自己，所以回收延迟到下一任务栈上的调度入口：销毁用户地址空间、
页表、用户页与内核栈，并打印 `[task] event=reclaimed pid=... pages=...`。
supervisor 通过 `kill <pid>` 也能终止一个挂起任务并立即回收。

`run` 命令进入用户任务后不返回内核调试控制台；supervisor 的 `sup> ` 是当前
可交互终端，`ps` 能在 spinner 占用时间片时返回任务列表，`kill 2` 能停掉
spinner 并让 heartbeat 继续。它是最小监督路径，不是完整 shell、登录或服务管理。

## E05 RAM 文件服务、终端与编辑器

`files` 是独立 ring3 任务，启动时由内核按可信 bootstrap 段清单装入（和 supervisor
一样，ELF 解析不在内核）。supervisor 与 files 各自持有两个固定端点：请求端点
（supervisor 发送、files 接收）和响应端点（files 发送、supervisor 接收），容量
4096 字节。内核只做带持有者校验的端点复制，不认识文件名、路径或文件内容。

文件服务是平铺 RAM 命名空间：最多 4 个文件、每文件 24 KiB，8 个同时打开实例。
文件内容属于 file 记录，游标/权限属于 open 记录；两个独立打开不共享偏移。
读返回短读和 0=EOF，写返回实际写入字节；无效句柄、只读/只写方向错误、
满/空、容量不足都返回明确错误。`replace_begin/chunk/commit/abort` 用 staging
缓冲区做原子替换：先检查容量并分块写入，commit 才复制到正式槽；失败或客户端
会话退出时不改动旧文件。commit 见到该文件仍有打开实例会返回 busy。

supervisor 内置最小编辑器：正文行原样追加（空行、连续空格、行尾空格都保留），
只有以 `:` 开头的行进入命令解析（`:w`、`:wq`、`:q`、`:q!`、`:p`、`:c`）。
保存走原子替换；失败时保留编辑缓冲区和旧文件，不先截断。缓冲区上限 8 KiB。

装载器不再从文件描述符边读边解析：`exec-file` 先把整个文件读入有界缓冲区，
读取时校验 stat/open 版本一致，再对这个完整快照做 ELF 检查、映射和启动；
文件服务在打开期间阻止替换，因此校验与执行不会读到两个版本。普通 `exec <image>`
仍读取只读启动模块，但同样先复制进缓冲区。

文件服务协议只暴露名字、偏移、长度、版本和状态，不传内部指针/下标。E07
已把 RAM 槽替换为 FAT16 工作盘后端，同时保留客户端接口；E05 的 RAM 后端不再是
默认路径。服务是单客户端（supervisor）；没有服务重启、并发多客户端、目录、
权限 ACL 或 POSIX errno。

## E07 工作盘、ATA PIO 与 FatFs

工作盘 `work_disk.img` 独立于 `build/`，由 `make disk` 显式创建/格式化；构建和
启动只打开已有盘。`make run` 默认用带 dash payload 的 install ISO（`build/xos-install-dash.iso`），
`make run_file` 用 file-backed ISO，`make run_iso` 用嵌入 kernel 的旧 ISO，
`make run_floppy` 保留 1.44 MiB 软盘路径；工作盘仍是 `if=ide,index=0,media=disk`。
file-backed ISO 的 no-emulation boot image 只有 boot sector + loader，
`KERNEL.BIN`/`DASH.ELF` 由 loader 经 ATAPI/ISO9660 读入；boot image 不再承载
kernel。旧 `xos.iso` 仍把 boot sector、loader 和 kernel 一起装进初始映像，
受真实模式 640 KiB 边界约束。
测试使用临时 FAT16 副本，`make smoke` 不写日常盘。

内核 `platform/pc/ata.cpp` 做 primary master ATA PIO：IDENTIFY、LBA28 读写、
FLUSH CACHE、每请求最多 8 个 512 字节扇区、忙/DRQ 有界超时。系统调用
`block_read/write/sync/info` 只允许 `files` 任务，验证扇区与用户缓冲；FatFs、
路径和文件内容仍全在用户态，内核不解析。

`files` 链接 FatFs R0.16，短名 8.3、无 LFN/RTC/mkfs。挂载失败返回错误，不格式化、
不退回 RAM。保存仍用 RAM staging，提交时写 `XOSTMP.TMP`、写并同步
`XOSJRNL.TMP`、目标先改名为 `XOSBAK.TMP`（FatFs rename 不能覆盖），再把临时
文件改名到目标；同步成功后才删备份/journal。启动挂载执行恢复：目标缺失则从
备份恢复，目标存在则清理陈旧备份；恢复失败进入 io 状态，不假报成功。
`sync` 对写打开文件 `f_sync` 并 `CTRL_SYNC`，supervisor 只有成功才打印
`[files] sync=ok`。`hello.elf` 仅在不存在时注入。

正常同步后重启保留已由两次独立启动验证；突然掉电、坏扇区、满盘、目录/LFN、
ACPI 关机不在本组保证内。工作盘是单一 FAT 卷，无分区表、fsck 或多客户端并发。

## E06 newlib 与 SSE/FPU 上下文

E06 把 newlib 4.6.0（x86_64-elf）作为可选 C 库接入 SDK；当前只有
`libc_programs` 中的 `libc_hello` 链接它，旧 SDK 程序保持窄 ABI。控制台
`read/write`、64 KiB 静态 `sbrk` 堆和 errno 由用户态适配层提供；
`open/stat/unlink` 返回 ENOSYS，POSIX 路径没有映射到 XOS 文件服务。

newlib 的 x86-64 ABI 使用 SSE 寄存器。E06 清除 CR0.EM/TS、设置
CR4.OSFXSR/OSXMMEXCPT，并为每个任务保存 512 字节 FXSAVE 区；任务切换
`fxsave64`/`fxrstor64`。内核仍以 general-regs-only 编译，不依赖 XMM。
E04 的“FPU 故障”探针因此改为正常退出；这不是放宽异常隔离，而是正式支持
FPU 上下文。用户 ELF 文件上限随 libc 程序扩到 128 KiB。

## 启动信息与生命周期

E04 将 supervisor 替换为 C++ 用户态装载服务，六个旧平铺 demo 保留作回归。
新增静态 ELF 装载、argv/初始句柄、构造回滚、阻塞等待、结果保留与 Escape 取消；
完整职责、地址空间和机制边界见 `e04_loader_sdk.md`，以该文和 state 为当前状态。
E03 的固定 supervisor 与“没有 wait”限制已被覆盖，其他 IPC 限制仍然存在。

`xos::boot_info` 是内部版本化数据契约：magic、version、size、内存条目数量/步长、
低端保留范围、内核占用范围、固件来源和完整性标志。当前结构 64 字节，条目 24 字节；
关键尺寸与字段偏移由 C++ static_assert 检查，主线启动测试检验实际汇编输出。
当前字节序为 little-endian；不承诺未来大端架构直接复用二进制布局。

架构入口接收两个地址，在 SysV AMD64 下分别为 RDI=header、RSI=regions；
它整理寄存器/栈后调用通用 `kernel_main`。将来其他 ISA 的入口负责转换其调用约定，
通用 C++ 不处理寄存器。指向的数据属于引导器，在内核复制之前不得回收对应内存。
当前 `memory_init` 在启动阶段直接消费该内存图并完成保留标记；低端范围仍未回收，
所以尚未实现“内核复制后释放引导器内存”，也不声称已能安全解析任意坏指针。
通用验证器拒绝坏版本、无效长度/数量、溢出、条目重叠和内核不在可用 RAM 等情况。
当前调用方是可信引导器，不把它当作可安全解析任意坏指针的用户边界。

日志使用事件、结果、构建 ID；没有墙钟时不伪造时间戳。E03 的 PIT tick 只是
调度计数，不是可展示时间；宿主测试超时仍使用宿主单调时钟。

## UEFI 什么时候引入

本次选择：E01 先固定这条可调试的 BIOS 基线；E02/E03 的异常入口、内存边界、
任务与地址空间机制稳定后，引入 UEFI 第二条启动路径，放在扩展持久化磁盘/真机支持之前。
用户若更想提前玩 UEFI，可调整该顺序；这是可逆实施安排，不是计划中新加的前置关卡。

届时优先评估成熟引导工具或窄 UEFI loader，不从头重建整套固件基础设施。
UEFI 路径负责获取/整理 memory map、装载同一个 kernel.elf、正确完成
ExitBootServices，再经 x86-64 架构入口交给同一个通用内核。
固件入口的调用约定与内核约定在适配边界转换；不能直接假定两者相同。
Boot Services 结束后不再调用固件控制台/文件服务。

UEFI 的 PC 输出可能需要串口或 GOP framebuffer 适配，不能假设 VGA 文本模式存在。
`platform/pc` 当前的 VGA 依赖已隔离，将来换输出后端，不改通用启动验证器。
不提前引入 Runtime Services、Secure Boot 或固件变量写入。

UEFI 接入验收：BIOS 与 OVMF 启动同一份 kernel.elf 哈希，走相同的启动信息验证，
内核核心源文件不因固件不同出现分支；验证内存保留、错误报告和调试符号。
当前 `firmware_kind::uefi` 的宿主输入测试只验证规范化契约，不表示已有 UEFI loader。

上游依据：[UEFI System Table / ExitBootServices 生命周期](https://uefi.org/specs/UEFI/2.11/04_EFI_System_Table.html)、
[ACPI 地址图接口](https://uefi.org/specs/ACPI/6.6/15_System_Address_Map_Interfaces.html)、
[Intel 架构手册入口](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)。
引入时机、目录划分与当前内存布局是 XOS 的实施选择，不是上游规定。

## 未来图形接口

用户确认Qt为GUI主线、SDL为次选，阶段与验收见xos_plan.md的E13–E20/G系列。
XOS窄显示/输入服务与用户态QPA/SDL适配分开，Qt不直接调用固件或绑定ISA；
优先QPA对接XOS服务，SDL兼容不是Qt的前置。当前未实现，不作为E08前置。

## E08-4/5 静态 TLS 增量（0019进行中）

ELF PT_TLS解析/模板校验仍在用户态loader；通用load_plan只描述文件偏移、地址、
初始化/零填长度与对齐。AMD64 variant II的TCB/TP布置在user/arch/x86_64/tls.cpp，
内核arch/x86_64/tasks.cpp为任务保存并恢复FS base；其他ISA需自己的后端与验证，
不能把现有通用代码编译检查称为TLS移植。sys35仅对owned building子任务设置TP，
验证已映射RW用户范围，内核不读ELF或库设施。
仅静态local-exec，任务有独立TLS arena；不承诺动态模块、线程或动态TLS。
实际功能与版本证据以0019和state.md更新为准，不因接口存在就提前标阶段通过。

## E13-T 进程与执行上下文

本分支将 PID/地址空间/权限/文件会话归 process_record，寄存器/内核栈/FS/FPU、
等待和 join 状态归 thread_record；通用生命周期标记在 core/thread_lifecycle.hpp。
仍是单核、内核不可抢占；所有线程阻塞时可中断睡眠，IRQ 推进等待截止时间。
工作线程退出只回收自己的执行资源；全组停止后才由其他安全上下文销毁地址空间。
内核文件身份仍为 PID，files 服务继续按进程枚举会话，不增加 TID 客户端。
地址图、预算与客体证据见 [线程实现](threading_implementation.md)。

## 0054：单文件恢复错误语义修正

journal/target/backup/temp的存在性检查仅FR_NO_FILE/FR_NO_PATH表示缺失；其他读取错误
在修改恢复材料前锁定为io。读取journal也检查close，清理检查删除/重命名/同步。
恢复成功路径保持原提交/回滚语义，journal在清理及其flush后最后删除。若删除之后的
最终flush失败，尽力重建marker且仍拒绝服务；持续介质错误下不保证重建成功，也不
承诺任意掉电原子性。0054的宿主API故障注入和真实客体恢复证据分别报告，不互代。
