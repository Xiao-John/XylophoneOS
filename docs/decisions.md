# XOS 实施决策

## 2026-10-23：第一组实模式启动原型

- 用户要求自研命名采用 snake_case；`docs/Discipline.md` 是指定例外。
- 用户要求从实模式开始，故本组采用 BIOS 双阶段 NASM 启动原型。
  计划 P01 的成熟引导器是建议，不是已确认约束。该选择满足此次启动练习，
  不承诺把自写引导器一直扩展成通用引导平台。
- 最终目标仍是 x86-64。本组不把 16 位终端称为内核或用户态 shell。
- 首个设备配置限于 QEMU PC、单核、64 MiB、TCG、只读 1.44 MiB 软盘镜像。
  使用 TCG 便于 Apple Silicon 宿主模拟 x86，暂不支持 UEFI 或真机。
  本组实际固定 `pc-i440fx-10.0`、`qemu64`；已用 QEMU 11.1.2 验证。
- 首阶段固定加载第一磁道内的 16 个后续扇区到 `0x8000`，第二阶段限制
  为 8 KiB。超过限制时构建失败，之后根据长模式布局重新设计装载。
- 本组只做 BIOS/VGA 与 COM1 的启动调试界面，不提前固化未来 IPC/终端 ABI。

## 2026-10-23：0002 完成 E01，建立架构边界

- 用户要求减少指令集耦合、便于移植。作为项目持续约束落实到目录、接口、
  构建源文件选择和通用代码的第二 ISA 编译检查；目前仍仅实现 x86-64。
- 本次“一阶段”按 E01 执行：固定初始平台/交叉工具、受限 C++ 初稿、独立镜像
  与带符号启动证据。E01 完成不等于整个 0.0-boot 或第一轮 E01–E04 已完成。
- GCC/G++ 16.2.0，交叉 target `x86_64-elf`；Binutils 2.47（工具实际报告
  2.47.20260726）；内核 C++20。当前不选择 libc，不宣称 XOS 原生工具链。
- 默认镜像通过 BIOS 引导到独立 ELF 导出的 64 位内核。原 16 位命令行改为
  单独 `real_mode.img`，避免后续内核逻辑堆进练习终端。
- 小型通用 `boot_info`/内存条目承接固件差异；指令/寄存器/链接布局归 arch，
  COM1/VGA 归 platform，core 不直接依赖二者。只有真实使用的窄接口。
- 引导期选用低地址 small code model、4 KiB 页、临时 identity map、NX/WP 和
  RX/R/RW 分段；不是长期内存管理策略。内核不生成 FP/SIMD，尚无状态保存。
- 本次确定 UEFI 引入时机：E02 基本异常和内存机制稳定后、持久化磁盘/真机扩展前。
  未来用 OVMF 与 BIOS 启动同一 kernel.elf 验证边界，优先复用成熟引导组件。
  这是可逆实施安排；当前没有 UEFI 实现，也不增加阻塞 OS 主线的预研阶段。
- 当前调试采用宿主 LLDB + QEMU GDB stub，仅 loopback；实际源码断点、参数和
  符号调用栈已经验证，不仅提供一份未运行的调试脚本。

## 2026-10-23：0003 完成 E02，异常与内存基线

- 内核安装独立 GDT（内核 code/data + TSS）与 256 项 IDT；向量 0–31 使用
  统一栈帧，double fault 走 8 KiB IST1，NMI 走 4 KiB IST2。异常一律 panic+HLT，
  当前不做恢复或任务终止；把“能打印”与“能恢复”分开记账。
- panic 输出 vector/名称、error、RIP/CS/RFLAGS，page fault 另报 CR2；真实触发
  #PF/#GP/#UD/#DE/#DF 验证，其中 double fault 用坏栈触发，证明 IST 实际生效。
- 物理内存以 E820 为准，使用 4 KiB 页双位图（保留/已分配），窗口上限 128 MiB；
  低端 1 MiB、内核镜像/BSS/栈、页表与启动信息不会被分配。分配返回零页，
  double free 与释放在未分配页上返回 invalid，不写“永远成功”的分配接口。
- 映射接口只覆盖当前内核地址空间的 4 KiB 页；中间页表按需分配且暂不回收，
  unmap 不释放物理页。首 4 MiB 保留 4 KiB 权限页，4 MiB 以上用 2 MiB
  identity 页（RW+NX）保证分配页可访问；这是 bootstrap 折中，不是最终 VMM。
- 调试控制台只轮询 COM1，命令覆盖内存统计、页分配、映射自检与异常触发；
  它是 E02 的临时诊断工具，不是用户态终端或稳定 ABI，后续迁出内核。
- 可屏蔽中断、PIC/PIT/APIC 与定时器不在 E02 内；没有它们就不宣称抢占或
  “完整中断子系统”。E03 再选择中断控制器与定时器路线，并扩展异常到任务身份。
- UEFI 时机不变：E02 的内存/异常基线已经建立，UEFI 可作为独立第二条启动路径
  推进，但不阻塞 E03；仍要求同一 kernel.elf 经 BIOS/OVMF 启动且通用内核不分叉。

## 2026-10-23：0004 控制台无害彩蛋

- 用户要求终端加点特色并把朋友 Guo YePeng 的名字写进内核；彩蛋默认随
  `config/x86_64_bios.json` 的 `easter_eggs` 开启，关闭后横幅、帮助项和命令
  都不注册，不做“关了还留后门”的假开关。
- 彩蛋只输出文本：启动横幅、`guo`、确定性的 `joke` 与 `about`。不引入随机数、
  延迟、额外分配、权限变化或错误拦截；诊断信息仍然先于玩笑，异常路径不经过彩蛋。
- 文案使用 ASCII，避免 VGA 代码页依赖；`about` 显示真实构建 ID，不伪装版本。
- “did not panic, yet” 作为横幅与 `guo` 的固定台词保留；这是用户点名的小幽默。
- 终端的稳定交互仍以现有 `xos64> ` 与命令语义为准；彩蛋不是 ABI，后续终端
  服务迁往用户态时可以整体搬走或关闭。

## 2026-10-23：0006 E03 第一增量，先让 ring3 真的跑起来

- E03 先做隔离/任务/抢占/IPC 的可运行基线，不等待 ELF 装载器。用户程序暂用
  嵌入内核的 NASM 平铺二进制；E04 再装载宿主交叉编译的 ELF64。这是可逆的
  实施顺序，不把 blob 当成长久程序格式。
- 每任务独立 PML4，但共享内核 0–64 MiB 页表；用户半区固定在 1 GiB，代码 RX、
  数据/栈 RW+NX。先避免为每个任务复制内核映射，也不提前做 higher-half 重构。
- 每个任务 4 KiB 内核栈，TSS rsp0 随任务切换；中断帧由异常/IRQ/syscall 共用，
  首次进入与之后切换走同一恢复路径，减少“第一次特殊”的分支。
- 抢占只在从 ring3 被 IRQ0 打断时发生，内核入口保持关中断；不宣称内核可抢占、
  可重入或支持嵌套中断。PIT 100 Hz 仅作为调度 tick，不是墙钟。
- 系统调用使用 `int 0x80`（DPL3），RAX 编号、RDI/RSI/RDX 参数、负数错误。
  用户指针必须先通过范围和页表权限检查；内核不直接解引用未验证指针。
- IPC 采用静态端点、64 字节单槽和任务级 send/recv 权限；满/空、无效句柄、
  越权、超长、内核指针都返回明确错误。阻塞、队列深度、撤销与动态端点留待后续，
  不为了“看起来完整”写永远成功的接口。
- ring3 异常杀死当前任务并继续调度，ring0 异常仍 panic+HLT；故障/退出后的
  页表、物理页和内核栈回收尚未实现，明确列为 E03 缺口。
- `run` 进入用户任务后不返回调试控制台；heartbeat 持续输出只证明抢占与故障
  隔离，不等于已实现用户态终端或监督服务。O03–O05 仍不标正式通过。

## 2026-10-23：0006 收口 E03，监督终端与延迟回收

- E03 的“故障回收”不只做 kill：退出/被杀的当前任务不能在自己的内核栈上释放
  自己，用 `reap_pending[8]` 标记，下一次调度在别的任务栈上销毁用户地址空间、
  页表、用户页与内核栈。回收走真实页表遍历，不按创建时的页数猜。
- supervisor 做成 ring3 用户任务，而不是内核线程：通过 read/tasklist/kill
  syscall 工作，`sup> ` 能在 spinner 死循环时响应 `ps` 与 `kill`。这比“内核
  控制台还在打印”更能证明终端与监督路径存在。
- `kill` 只允许 supervisor 调用，目标不能是自身或 supervisor；被杀任务立即回收。
  没有信号语义、等待父任务或退出码传递，不能伪装成完整进程管理。
- `run` 仍是单向入口，执行后不返回内核调试控制台；supervisor 是当前可交互
  路径，不是完整 shell。彩蛋 shell 留到用户态终端/装载器更成熟时再做。
- E03 在机制层收口，但 O03–O05 不整体改计划表：当前 12 项是局部证据，未覆盖
  跨任务地址访问矩阵、阻塞 IPC、配额与长时间压力。缺项写入 state/0006。

## 2026-10-23：0007 E04 用户态装载与 SDK

- ELF 解析/装载策略在 ring3 supervisor 内；内核只提供按父任务授权、状态检查的
  create/map/start/abort/wait 与只读启动模块字节访问。普通 ELF 由客体解析和执行。
- 初始 supervisor 的宿主可信段清单是 bootstrap 例外，不把 ELF 解析放进内核；
  六个旧 NASM demo 作为回归保留，旧 NASM supervisor 删除。
- 导出独立 SDK（头、CRT、libxos.a、libxos_loader.a、linker script、版本/许可），
  同一份 SDK 构建实际用户 C++ 程序。ABI 1 共同重建，不兼容 Linux/POSIX。
- 初始 argv/0/1/2 句柄明确归属；close 只影响自身，旧 E03 read/write 也不能绕过关闭。
  非阻塞 console read 的空状态为 -3，不伪装文件 EOF。
- 控制句柄按父任务身份与单调 PID 校验。构造中任务不可调度，提交后不可继续映射。
  失败显式 abort，最多 8 任务、64 用户页/任务、16 未收集完成记录；满时拒绝，不淘汰结果。
- wait 真实挂起/唤醒，区分 exited/faulted/killed，结果只消费一次；资源可先释放。
  Escape 可监督终止前台被等待任务；不是 POSIX 信号或副作用回滚。
- 修复 E03 destroy_address_space 漏回收 PDPT，以及任务创建中途失败回滚缺失。
  以真实空闲页计数验证，不能用 reclaimed 文案代替泄漏检查。
- 当前 SDK 整数型；CR0.EM/TS 拒绝未支持的 x87，SSE/XSAVE 未启用，不承诺状态保存。
  中断入口 cld 隔离用户 DF。memset 是实际实现的共享运行时，不是成功占位。
- 为只读 ELF 模块扩充 BIOS 暂存到 512 KiB，内核内存上限 1 MiB；仍不引入文件系统、
  UEFI、原生编译、完整 shell 或 GUO 模式。架构/固件分层要求继续执行。

## 2026-10-23：实施顺序改为 E05 → E07 → E06

- 用户确认先做 E05 RAM 文件/编辑器，再做 E07 块设备与持久化，最后做 E06
  GCC/G++ Seed 依赖审计。E06 仍依赖 E05 的 SDK/文件接口，但不阻塞 E05/E07；
  E07 依赖 E05 的文件服务语义，顺序调整不改变依赖基础。
- E07 只替换文件服务的存储后端与持久化语义，不重写终端/编辑器客户端；
  E06 再根据实际编译/运行依赖选择 libc，不把 E05 的窄 SDK 当作完整 libc。

## 2026-10-23：0008 E05 RAM 文件服务与编辑器

- 文件服务是独立 ring3 任务 `files`，由内核按与 supervisor 相同的可信 bootstrap
  段清单装入；内核仍不解析 ELF、路径或文件内容。supervisor 与 files 使用固定
  请求/响应端点，容量 4096 字节；旧 E03 端点保持 64 字节。
- 文件与打开实例分开：文件记录只有名字/大小/版本/内容槽；打开记录持有文件索引、
  游标和读写方向。两个独立打开不共享游标；替换/删除遇到打开实例返回 busy。
- 固定 RAM 上限：4 个文件、每文件 24 KiB、8 个打开；单层名字，无目录。读可短读，
  0 为 EOF；写返回实际字节，到容量短写；不做假成功或越界截断。
- 保存采用 begin/chunk/commit/abort 的 staging：先检查容量、分块写入临时区，
  commit 才替换正式文件；失败/客户端会话退出不截断旧文件。staging 记录 owner PID
  仅用于单客户端残留清理，不是安全凭证；没有内核 sender 身份证明。
- 编辑器正文行不经过 supervisor 分词器；空行、连续空格、行尾空格原样保存。
  只有 `:` 开头的行是命令；保存失败保留编辑缓冲区与旧文件。
- `exec-file` 先把整个文件读入有界缓冲，校验 stat/open 版本一致并保持打开到读完，
  再对同一快照做 ELF 检查/映射/启动；不会边读边解析或重读第二个版本。
- 文件服务存储是 E07 接缝：协议只传名字、偏移、长度、版本和状态，不传 RAM 指针/
  槽索引。E07 可以替换后端而不改客户端；当前无持久化、目录、ACL、多客户端、
  服务重启或 POSIX errno，不能把 RAM 内容冒充持久保存。
- 任务总数达到 8（六个旧夹具 + supervisor + files），启动后无空槽；需要装载
  新程序时先 kill 旧夹具。该容量限制写入文档，不静默扩容。

## 2026-10-23：0009 E07 独立工作盘与 FatFs

- 工作盘 `work_disk.img` 独立于 `build/`，由 `make disk` 显式创建/格式化；普通
  构建/启动只打开已有盘，缺盘报错，不自动格式化、不退回 RAM。测试使用临时
  FAT16 副本，`make smoke` 不写日常盘。
- 块设备选 ATA PIO：轮询、LBA28、每请求最多 8 个 512B 扇区、忙/DRQ 有界超时，
  避免首轮 DMA/中断。硬件端口只在 kernel platform；内核通过
  `block_read/write/sync/info` 暴露受限扇区机制，只允许 `files` 任务。
- FatFs R0.16 与低层 diskio 在用户态 `files` 服务；内核不解析 FAT/路径/文件。
  使用 8.3 短名、无 LFN/RTC/mkfs；挂载失败明确报错，不假装持久。
- 保存继续使用 RAM staging；磁盘提交为 temp→journal→backup→target→sync，
  因为 FatFs `f_rename` 不能覆盖已有目标。journal 记录目标名，启动挂载执行
  恢复；恢复失败进入 io，不报告成功。
- `sync` 覆盖写打开文件的 `f_sync` 与块设备 `CTRL_SYNC`/FLUSH，只有全部成功才
  打印 `[files] sync=ok`。这不是任意掉电原子性证明；突然掉电、坏扇区、只读盘未验证；物理满盘
  用宿主填充的临时 FAT16 盘验证保存失败。
- `hello.elf` 只在缺失时从只读模块注入；已有文件不覆盖，避免启动初始化破坏
  用户内容。打开期间替换/删除仍 busy。
- 正常同步后重启保留已验证（两次独立启动），E07 本版受限完成；E06 的 libc
  审计随后完成，见下一条。

## 2026-10-23：0010 E06 选择 newlib 并启用 SSE/x87

- 选择 newlib 4.6.0.20260123 / x86_64-elf，而不是 musl：先有可配置的小型 C
  库与 x86_64 目标；musl 的 Linux syscall 绑定需要更大兼容层。newlib 只是
  本版候选落地，不等于完整 POSIX 或已证明足够承载原生 GCC/G++。
- 预构建 `libc.a`/`libm.a` 与头放入 third_party/newlib，普通 build 不联网；
  重新生成由 scripts/build_newlib.sh 记录。SDK 导出实际哈希，`make libc-audit`
  从产物生成依赖清单。
- 只用 `libc_programs` 显式链接 newlib，避免旧 SDK/内核镜像无谓膨胀；当前
  示例 `libc_hello` 使用 printf/malloc/string/exit。
- newlib x86-64 ABI 使用 SSE，不能靠 `-mno-sse` 规避（libc 的 double 路径会
  在编译期失败）。E06 清除 CR0.EM/TS、设置 CR4.OSFXSR/OSXMMEXCPT，并为每个
  任务增加 16 字节对齐的 512B FXSAVE 区，切换时 fxsave64/fxrstor64；内核仍
  使用 general-regs-only。E04 的 FPU 故障探针改为正常退出 99。
- `_sbrk` 是进程私有 64 KiB 静态堆，不是内核 brk/mmap；失败返回 ENOMEM。
  `open/stat/unlink` 返回 ENOSYS，明确不把 XOS 文件服务伪装成 POSIX 路径。
  没有 libstdc++、异常/RTTI、TLS、线程、动态链接或 C++ 静态构造。
- 用户 ELF 上限扩到 128 KiB，支持 66,664 字节的 libc_hello；内核镜像仍在
  512 KiB boot 暂存/1 MiB 内存上限内。

## 2026-10-23：E08-pre1 资源与接口基线

- E08-0 实测证明宿主 cc1/cc1plus 是 40/43 MiB 的 arm64 Mach-O，当前 16 MiB 盘、
  24 KiB 文件上限、64 用户页和 64 MiB QEMU 不可能承载原生 Seed。先冻结设计
  基线，再实现 E08-1，避免边做边改上限。
- 基线：512 MiB QEMU RAM、512 MiB 内核物理页上限、1 GiB 用户窗口、65536 用户
  页/任务、8 任务；2 GiB FAT32 专用工作盘（LFN/目录），独立于 build/。
- 文件服务 v2：per-task 文件会话，路径/目录，流式 open/read/write/lseek/close，
  4 KiB 消息、磁盘 staging，文件上限为磁盘剩余空间；不再保留 24 KiB 语义。
- 大 ELF 采用流式段装载，暂不做 demand paging；打开期间拒绝替换，失败回滚。
- 进程先做 posix_spawn + waitpid + pipe；fork/信号只有在 GCC 实际调用点证明
  必要时加入，不先造完整 POSIX。
- Seed 版本冻结 GCC 16.2.0 / Binutils 2.47 / newlib 4.6.0.20260123，Canadian
  cross，顺序 binutils → C GCC → C++ GCC；C++ 基线为前端、libstdc++ 基础容器/
  string、异常、RTTI、TLS；iostream 可选；线程/动态链接不在范围。
- 这些是规划基线，尚未实现；E08-1 第一 gate 是 >128 KiB ELF 从盘上装载、
  按路径读写、sync 后重启保留。若实测推翻基线，必须更新决定记录。

## 2026-10-23：未来图形接口优先 SDL 兼容

历史决定：优先级已由下文2026-10-24 Qt主线决定调整。

用户确认未来图形化 API 优先按 SDL 兼容方向实现，已有另一项目研究基于 SDL 兼容的 GUI 库。
实现时保留 XOS 窄显示/输入机制与用户态 SDL 适配边界；SDL 版本与兼容子集在图形阶段
根据对接库实际需求确定。当前没有 SDL/GUI 实现，不增加 E08 前置任务。

## 2026-10-24：新自研代码 Apache-2.0，许可证材料随 SDK 导出

用户要求新代码使用 APL-2.0，本项目按 Apache License 2.0 / SPDX Apache-2.0 落实。
历史 MIT 基线保留原许可及文件清单；第三方保留原条款，不统一改标。newlib 是多来源
组件集合，COPYING.NEWLIB 的 LGPL 第21/22节带 Linux target 限定，不能将整个 newlib
说成 LGPL；当前预构建 .a 的逐成员许可证追溯尚未完成。政策在 licensing.md，
组件表在 licenses/components.json；构建导出声明并记哈希，license-audit 只验证材料。

## 2026-10-24：0012 完成 E08-1 存储与会话 gate

- 512 MiB 物理窗口/65536 用户页与2 GiB FAT32 基线落地，512 MiB/2 GiB 测量支持继续
  保留流式读取+预载；这不证明真实 GCC Seed 尺寸/峰值。原日常 FAT16 盘不迁移覆盖。
- 内核 PID 绑定的每任务文件会话、单调不复用端点 token；生命周期清理；文件服务v2
  路径/目录/ASCII LFN、磁盘 staging。全局一笔保存 busy，不允许另一活客户端抢占。
- 持有只读打开锁后校验/逐页读取 ELF，失败关闭/abort；原128KiB仅限制启动模块。
- 74组验证、双容量双启动、256KiB逐字节回读、65536页回收通过；E08未整体完成。
  下一步E08-2，未进入binutils/GCC；限制与证据见0012及e08.md。

## 2026-10-24：E08-2 受限工具运行时

保留用户态ELF策略与内核窄机制边界；startup v1前缀兼容，v2承载env/cwd与stdio。
64项argv/每串255字节，4页startup、32页可用栈与guard；堆区独立保留，sys29真实
按页分配与缩回。构造权由supervisor通过sys28显式授予直接子任务，不继承。
pipe有界、引用计数管理；libc暂保留EAGAIN，不承诺任意阻塞流水线或完整POSIX。
文件适配按真实FatFs能力实现；复用newlib mkstemp而非重复定义。无墙钟/符号链接/
POSIX mode，明确失败或在GNU移植边界记录可选行为限制，不造成功stub。
首次受限gate与实际问题见0013/0015；不据此提前标原生binutils/GCC完成。

## 2026-10-24：E08-3 真正GNU工具通过客体验收

GNU Binutils 2.47 Canadian cross的as/ld/ar/ranlib/strip在XOS内产出目标文件、
归档索引和可执行ELF，strip后及sync重启后均执行退出42；E08-3受限gate通过。
实际构建、输入哈希、错误过程和最终证据以state/0015为准，不将此扩大为GCC/G++完成。

编译器能生成TLS不代表XOS支持TLS，所有递归configure共享真实cache并关闭TLS；
Seed静态检查拒绝TLS/动态链接。无dlfcn时CLI显式拒绝动态插件；修复上游无realpath
路径漏返回值，保留same-file保护。FatFs以真实SFN位置映射有界16位inode，
不以碰撞hash或跳过GNU检查掩盖身份缺项。Qt评估仅供下一轮讨论，不改变E08-4顺序。

## 2026-10-24：Qt 为 GUI 主线，分阶段移植与验收

用户确认Qt为GUI主线、SDL为次选，并要求写入plan、扩展阶段与验收。
xos_plan.md v0.5新增E13–E20与G01–G10，分别覆盖运行基底、显示输入、QtCore、
QtGui/QPA、Widgets、无界面QML、软件Quick和集成交付；QML不依赖Widgets。
Qt版本/feature、线程方案与资源预算尚未冻结，按实际模块需求验证，不造成功stub。
首轮允许交叉构建及宿主生成器；原生构建Qt应用和重建Qt本体单独验收。
Qt平台适配在用户态，对接XOS窄服务，不以SDL、UEFI、GPU或编译器自举为首窗前置。
本轮仅更新文档，GUI gate全部not_run；下一开发阶段仍E08-4。

## 2026-10-24：E08-4/5 运行基底与 host C++ 闭包

0019已验证POSIX C++ CRT（含当前交叉GCC使用的legacy ctors）、正常退出析构与
静态.eh_frame注册；复用实际GNU libgcc.a展开器，真实回溯通过，不另造unwind。
静态TLS在用户态ELF/ISA后端装载，AMD64 variant II，内核arch仅切换FS base；
sys35限制owned building子任务、映射/RW/arena，失败回滚。模板1MiB、align64KiB
为当前有界子集，无动态TLS/线程。普通文件X_OK复用ELF校验，不虚构FAT执行位。

从端GCC本体<algorithm>失败证明C Seed也需要host C++头/运行库。由同GCC版本
源码构建真实静态libstdc++/libsupc++作为工具自身的依赖闭包，仍归从端构建范围；
主端交不可变SDK/ABI并处理真实运行缺项，不扩大临时new/delete shim成伪STL。
host闭包可先完成，不等同target应用的E08-5；目标异常/RTTI/TLS基线不降级。
本次8组运行基底功能与12例解析通过不替代C/C++ Seed gate，后续压力由专人负责。

## 2026-10-24：0020 C Seed集成采用独立派生与直接GNU ld

从端交付原始C Seed后，实际gcc --version暴露libiberty无realpath分支漏返回值，
主端新增0007补丁，在独立目录只编译lrealpath并重放三条已记录最终链接；原始
Seed/manifest保留。当前profile显式使用真正GNU ld，XOS CRT负责构造/frame，
不为未使用collect2扩大子任务构造权，也不把未重链接的collect2列为已验收。

真实cc1读源码要求O_NOCTTY；文件打开本来不获取控制终端，libc接受该标志。
当前newlib不暴露O_BINARY，GCC将其定义为0，无需虚构公开标志。实际链接再暴露
8-open会话上限低于BFD至少10项缓存；据调用链将每会话调至16、FatFs全局锁32，
保留配额、真实失败和退出清理。文件消息ABI布局不变，限额不是完整POSIX承诺。
工具默认as安装为显式字节相同别名，sysroot/搜索/specs绑定安装白名单，无宿主代编。

提前准备C++ ABI探针，但host工具闭包的-fno-exceptions/-fno-rtti不能替代target
应用运行库；manifest不就绪时直接not_ready，不构建/启动客体假报通过。

## 2026-10-24：0021正常exit先清理单线程TLS

真实GCC对象需要__cxa_thread_atexit；XOS按静态单映像、每进程一个用户线程提供
私有LIFO注册列表，不为无动态模块增加DSO卸载，也不推导多线程支持。仅main返回
前挂钩会漏掉显式exit，因此用强exit统一TLS析构与真实newlib退出处理/stdio/_exit。
正常两路径及析构时新增TLS注册已在客体通过；递归exit按异常路径直接_exit，
kill/_exit不保证析构。此用户库补缺发SDK v5，旧SDK/工具输入分别保留；新应用
sysroot可显式选v5，工具自身旧SDK通过原manifest与tool_runtime_sdks分别记录。
E08-6 C编辑持久化证据可提前收集，单语言部分通过不替代E08-5/E08整体结论。

## 2026-10-24：0022 GNU目标TLS配置与E08受限功能收口

目标库原配置含GNU atexit_thread回退，实际链接与SDK v5重复定义；按GNU已有
_GLIBCXX_HAVE___CXA_THREAD_ATEXIT=1配置派生头与归档，libc负责真实TLS退出，
原始A/B不修改，保留完整hash与工具命令。新g++同样暴露lrealpath漏返回，复用
0007补丁、仅重放两条真实最终链接，不完整重建GNU。collect2仍未验收，直接GNU ld。
六项ABI、原生G++设施与C++编辑重启通过，合并先前C增量判定E08当前受限功能
范围完成，O11/O12/O13按静态配置通过。原始单语言partial报告不改标，由主端
综合报告记录合并判断及版本差异，不冒称同一最终版本的全量旧回归或压力全绿。
下一阶段E09交付/试用尚未开始；压力、完整标准库/线程、系统重建和自举另验。

## 2026-10-25：0025 xsh原生入口与可选dash

用户明确保留Xshell/xsh的原生Shell定义权；dash仅为从Xshell启动的独立程序，
不替换默认入口，不自动安装为/bin/sh。用户未来自行选择Shell；xsh交互可独立
发展历史搜索、补全、提示符等体验，不受dash或POSIX脚本语法限制。
采用固定dash 0.5.13.5，A先用同步posix_spawn/指定PID等待，保留上游解析/展开；
B/C另补描述符/编译器授权和管道/隔离环境。不为Shell先做全局fork或信号假实现。
E09发行交付收口，朋友试用与备份恢复/升级记录保持待补。16项A客体gate及根路径
修复证据见shell_subset.md、work_log/0025_dash_a.md；并发Xshell PATH修改未冒认已验。

## 2026-10-25：0027 查找与可运行性分层

Xsh对外部命令先用户态查找/检查，再由用户态装载器持有同一文件锁校验并装载，
内核只验证任务/页/句柄/授权机制。ELF识别不依赖扩展名；预检不等于最终资源或
授权保证。PATH可跳过目录、普通数据和不兼容候选，显式路径不fallback，读取/
资源错误中止搜索。首次有效候选最终启动失败，不改跑后面的同名程序。
默认正常执行简洁、真实错误可见，显式trace启用原诊断；窄sys36只给bootstrap
supervisor，不随driver构造权继承。xsh仍是原生入口，dash继续可选。

## 2026-10-25：0028 dash B0+B1采用有界构造权委派

- 进程构造权改为显式深度，最大3层。supervisor可为building子任务设置深度；
  普通持权任务只能给自己的直接building子任务设置严格更小的深度。旧sys28
  一层grant保持兼容，拒绝委派使用独立错误码，不与文件not-found混淆。
- Xsh仅对裸`dash`配置深度2；dash的用户态profile仅识别固定GCC/G++ driver并
  委派深度1。内核不检查路径、文件名或工具身份，cc1/cc1plus/as/ld不能继续委派。
  `exec-driver dash`仍是旧一层权限，尝试再委派明确EPERM、退126并回滚构造中任务。
- B1开放case、函数、dot/source和已有参数展开；递归admission仍拒绝管道、重定向、
  子Shell、后台和命令替换。开放语法不等于完整POSIX Shell。
- 引入固定sbase提交的cat/cp/mkdir/mv/rm窄子集，只承诺本次客体验证的普通文件、
  mkdir -p、同卷rename及非递归删除。保留MIT声明；不承诺递归、符号链接、权限位、
  跨卷fallback或覆盖目标。
- 最终7项B gate、16项A回归和许可材料检查通过；未重跑旧全量压力。B2描述符/
  重定向与前台取消、C阶段管道和隔离执行仍未开始，证据见0028工作日志。

## 2026-10-25：0031 公共线程契约与E13-T提前

用户确认落盘契约和计划。采用1:1内核线程、单核抢占；进程持有地址空间/权限/
会话/预算，线程持有独立上下文/栈/TLS/FPU与等待。PID/TID分开；线程创建不增加
构造权，正常线程退出不释放共享进程资源；进程exit/故障/监督取消统一全组终止。
E13-T提前服务CPython/C++/Qt，T0生命周期→T1进程私有比较等待/单调时间→T2
线程安全pthread/newlib/C++ SDK→T3各应用gate，不等待Qt显示/SMP/fork。
CPython可继续单线程bootstrap，T2后立即接真实pthread，不再等PY3其余功能。
细节及首版限制见threading_contract.md v1；原子等待防丢唤醒、退出仲裁、资源
回收与真实运行库锁是验收内容，不以空桩代替。全部实现/gate仍not_run；syscall
编号/字节布局/虚拟地址图在T0与ABI头同步冻结，旧发行/SDK回执不改变。

## 2026-10-25：0032 独立应用开发与包管理规划

用户要求规划包管理并改进第三方用户态开发/安装。普通程序以独立项目+版本化
SDK开发，不修改系统源码/启动清单；保留本地ELF直接运行。安装与执行/权限授予
分开，包名或manifest不增加内核构造权。主计划v0.8/C16记录该方向。
首版工程方案见package_management.md：P0 profile/schema/工具、P1宿主候选盘、
P2客体维护事务、P3仓库分发。xos_app/xpkg/.xpk/ustar-JSON与预算是P0待核验
方案，不冒认用户逐字段批准或已经实现。线程公共底座仍优先；包管理不等线程。
用户补充PY0已完成、Shell有UTF-8接口，已据0030/0033核对并纳入包样本；Open
Adventure由用户移植线负责，Python生成依赖与最终游戏运行依赖分开。仅更新
文档/开发入口，无新代码/构建/安装/客体测试，不重跑旧gate。

## 2026-10-25：0035 包管理优先与P0首版

用户已把多线程实施交朋友、后续PR交付，本线优先包管理；主端保留契约/接收
整合责任，不并行改线程实现。0035交P0：独立C/C++项目、宿主xos_app与xpkg、
普通文件ustar/JSON及schema、冻结SDK profile，拒绝未知线程库/混合SDK。
P0包目录隐含，显式目录/链接/PAX等拒绝，FAT短名含~的显式路径拒绝；实际盘
冲突/归属留给P1，不能以静态校验替代。构建回执与源码/SDK/构建器/产物绑定，
包不执行脚本或授予构造权。16组宿主与两项新payload客体执行通过，主计划v0.9。
P1安装/数据库、P2客体事务、P3仓库未实现，现有桥传入新盘不叫安装器通过。
证据work_log/0035_package_p0.md和build/package_p0/；旧回归/压力未重跑。

## 2026-10-25：0042 dash B2完成

- files服务以引用计数的打开实例作为共享状态，跨进程transfer转交同一FIL/偏移/
  O_APPEND语义；会话close、退出与kill只在最后引用释放时关闭。文件wire保持v2，
  新操作append，避免打断已有静态工具。
- posix_spawn文件动作按调用顺序作用于私有FD快照；成功时把最终0–2映射的真实
  文件handle转交给child，失败恢复父描述符表且不留下可运行孩子。SEEK_CUR等由
  files服务真实游标计算，不再用libc本地偏移模拟。
- dash仅开放0–2上的`<`、`>`、`>>`、`2>`及dup/close类顺序重定向；builtin用
  上游栈恢复。管道、子Shell、后台、命令替换和here-document仍拒绝，属于C阶段。
- build `911184be3f3c99f6`上B2 6项、B0/B1 7项、进程/SDK 13项及许可检查通过；
  资源均回到`[129833,2,0]`。未提交、未推送，证据见0042工作日志。

## 2026-10-25：0037 公共线程候选实现

按 0031/0036 契约实现 T0–T2，保持 8 个进程、每进程 4 个线程槽的预算。
旧 ABI 及旧 ELF LOAD 范围保留；新增线程 profile 显式确认 0x70000000–0x71000000
为空，按 4 MiB slot 预留栈/TLS，旧布局冲突返回 ENOTSUP。主线程和旧 SDK 不扩栈。
join 结果由内核保留，死线程页先回收；结果输出不能放在目标即将回收的栈/TLS。
最后线程先关创建入口，再等其他已 begin_exit 上下文安全停止；之后才运行进程收尾。

newlib 重建为动态 __getreent/真实 retarget locks，C++ 运行库使用 pthread gthread。
同一文件会话整次 RPC 串行；FD 表只做短暂查找/引用操作，I/O 用对象 pin 和独立锁，
不持 FD 表锁等服务。GNU patch 0008 将无墙钟的 noexcept system_clock 查询显式
终止；steady_clock 和 monotonic cond 使用真实 PIT 等待。没有给墙钟/熵填成功桩。
具体 ABI、回执、失败与未运行范围见 threading_implementation.md 和 0037 工作记录。

## 2026-10-25：0040 ISO 安装 payload 与 sys38

A2 的 file-backed ISO 已把 kernel 从 boot image 移到 `KERNEL.BIN`；A3/A4 继续
把 `DASH.ELF` 作为 ISO payload。loader 在 `0x2FFFF8` 写长度、`0x300000` 起放
数据，boot_info.reserved 指向长度头。kernel 在 `memory_init` 前复制到 1 MiB
静态 `boot_payload`，新增 `sys_boot_payload=38` 仅给真实 bootstrap supervisor：
first=offset、second=目标用户地址、third=长度；长度 0 查询总大小。
supervisor/files 初始化时若 `/usr/bin/dash` 不存在则安装，已有文件不覆盖。
ISO 加 `MANIFEST.TXT` 与宿主 `install_manifest.json`，但未签名、不是交互
分区安装器；payload 上限 1 MiB。现有 syscall 编号/旧 ISO 路径保持兼容。

整合0037线程PR时本地ISO的sys38与已合并线程38–52冲突；本地未发布的
sys_boot_payload统一改为53，线程ABI保持远端定义。旧0040的38只描述合并前的
实验镜像，不是当前数值；ISO源码保留，用户计划的回滚/新发行本轮不执行。

## 2026-10-25：0044包管理器正式命名xypm与P1边界

用户因撞名决定将包管理器定名xypm（C17）。当前命令、脚本/模块、原生程序、
包ID和数据库目录统一改名，不保留xpm/xpkg可执行别名。`.xpk`与v1容器/schema
不变；历史工作记录、冻结SDK和已发布附件保留原名与哈希。没有据此声称完成
商标或全球名称唯一性检索。旧名数据库存在时拒绝自动建立第二份归属库，无静默迁移。

P1采用全会话锁+独立候选镜像：宿主校验、精确依赖/归属、安装/升级/移除、回读后
发布，源盘不写。客体xypm先提供同一list/info程序给xsh与dash；完整客体维护事务
留给P2。B2 stdio转交需要新的单线程CRT/profile，旧发行SDK不冒称兼容重定向；
本轮冻结组合SDK并实测，未注册线程SDK，也不修改dash/内核/CPython。证据见0044。

## 2026-10-26：0048 xypm P2先交维护门控

本地工程选择：将P2拆为维护准入/写租约→原生校验/计划→持久日志恢复→用户写命令。
内核sys54仅提供单worker进程准入屏障，包策略留用户态；files根据真实kernel
owner/worker限制写入，路径和程序名不授予维护权。worker失败不自动释放。
Xsh提供显式maint-run/recover/status，dash保留普通应用身份，退出dash后才能满足
无其他应用的维护前提；两个Shell的普通xypm查询契约保持一致。P2-1不开放
install/upgrade/remove，也不承诺内存屏障能跨重启；P2-2以后补持久恢复门禁。

## 2026-10-26：0047 ISO扩容而不引入UEFI

继续BIOS/ATAPI/file-backed ISO，kernel预算8 MiB文件/16 MiB内存，前18 MiB
以4 KiB页保留W^X映射；payload在32 MiB处、上限32 MiB。loader交规范化descriptor，
kernel验证范围并为实际载荷预留页，不额外拷贝到固定1 MiB缓冲；sys53仍仅监督
可读，文件服务分块staging安装。大kernel无法安全用旧低内存loader时不生成兼容
镜像，避免发布名义成功的坏启动文件。真实5.6 MiB kernel/2.1 MiB payload与
正常兼容gate见0047；真机、UEFI、任意断电不从这些QEMU结果推出。

## 2026-10-26：0051 E14 BIOS VBE、单surface与窄服务

保持BIOS主线，VBE在16位loader探测/设置XRGB8888，800×600优先、640×480次选。
boot_info v2追加显示扩展，不借用payload字段。显存在512MiB RAM管理之外以
supervisor RW/NX UC aperture映射，普通用户不获MMIO权，图形模式禁止VGA文本写，
串口保留。sys63/64与既有0–62不冲突，现有IPC认证单surface/焦点，用户RAM批量
提交，PS/2 IRQ1/12有界事件FIFO/丢失重同步。服务无文件/块设备/构造权，退出撤销
channel并唤醒。单核内核不可抢占保证buffer预检和复制无同进程解除映射竞争；
SMP若引入必须先重做pin/锁。Qt QPA仍留E16，E14不编译Qt，不引入GPU/桌面。
正式结果与未验边界见display_backend.md、0051工作记录和reports/display_e14_20261026/。
