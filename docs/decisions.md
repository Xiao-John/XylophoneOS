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
