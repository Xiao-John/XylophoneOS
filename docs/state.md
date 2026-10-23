# XOS 当前状态

更新时间：2026-10-23（Asia/Shanghai）。新 agent 先读 Discipline.md、AGENTS.md，再读相关设计与工作记录。

## 当前方向

以 xos_plan.md v0.4 正文为准。持续要求：下划线命名、过程与每组交接落盘、
保持轻松；减少 ISA 耦合，固件/架构/平台/通用代码分层。localpilot/ 是独立项目，
不进入 XOS 扫描、修改、构建或清理。本组没有修改它；没有创建并行子 agent。
用户确认实施顺序为 E05 → E07 → E06，依赖基础不变。

## 正在进行

E08-0 审计、E08-pre1 设计完成；E08-1 **未开始**。0011 记录审计/设计，
本轮只新增文档与设计基线，没有改内核/文件服务/libc/测试。共享 build/ 不并发构建或清理。
根目录仍无 Git 仓库，未初始化或提交。

## 当前已实现

- 0001–0006：启动练习、E01 工具/内核、E02 异常/内存、无害彩蛋/命令手册、
  E03 ring3/抢占/IPC/监督与回收；历史记录保留在 work_log/0001–0006。
- 0007：E04 用户态 ELF64 装载器、最小 SDK、argv/初始句柄、启动/等待/退出/故障结果。
- 0008：E05 文件服务、原始行编辑器、原子保存与 `exec-file`；当时后端是 RAM。
- 0009：E07 独立 FAT16 工作盘、ATA PIO 块设备、用户态 FatFs、同步与启动恢复，
  替换 E05 的 RAM 后端；记录 work_log/0009_e07_persistent_disk.md，
  机制见 e07_persistent_work_disk.md。
- 0010：E06 newlib 4.6.0（x86_64-elf）接入 SDK、用户态 C 库适配、每任务
  SSE/x87 FXSAVE/FXRSTOR、`libc_hello` 首批工具；记录
  work_log/0010_e06_newlib.md，机制见 e06_libc.md。
- 0011：E08-0 审计、E08-pre1 设计均完成；资源/接口基线冻结在
  `config/e08_pre1_baseline.json`，设计见 `e08_pre1_design.md`，审计见
  `e08_stage0_audit.md`；E08-1 未开始。没有声称原生 GCC/G++ 可用。
- 工作盘 `work_disk.img` 独立于 `build/`；`make disk` 显式创建/格式化，构建和
  启动不创建/格式化它。`make run` 缺盘时报错并提示 `make disk`，不退回 RAM。
- QEMU 固定只读软盘启动 + `if=ide,index=0,media=disk,cache=writeback` 工作盘；
  测试用临时 FAT16 副本，`make smoke` 不写日常盘。
- 内核 `platform/pc/ata.cpp`：primary master ATA PIO、IDENTIFY、LBA28 读写、
  FLUSH CACHE、每请求最多 8 扇区、忙/DRQ 有界超时。硬件细节在 platform。
- 系统调用 `block_read/write/sync/info` 只允许 `files` 任务；内核验证扇区范围与
  用户缓冲，不接受物理地址/端口；不解析 FAT/路径/文件内容。
- `files` 链接 FatFs R0.16（第三方目录），短名 8.3、无 LFN/RTC/mkfs；挂载失败
  报错，不格式化、不退回 RAM。文件最多 4 个、单文件 24 KiB、8 打开；
  FatFs 显示大写短名（`HELLO.ELF`/`NOTE.TXT`），查找不区分大小写。
- 文件/打开实例仍分离；读短读/0=EOF，写返回实际字节；打开期间替换/删除 busy。
- 保存提交：RAM staging → `XOSTMP.TMP` + sync → `XOSJRNL.TMP` → 目标改名为
  `XOSBAK.TMP`（FatFs rename 不能覆盖）→ 临时文件改名到目标 → `CTRL_SYNC`
  成功后才删备份/journal。启动挂载执行恢复；恢复失败进入 io 状态，不假报成功。
- `sync` 对所有写打开文件 `f_sync`，再块设备 FLUSH；supervisor 只有全部成功
  才打印 `[files] sync=ok`。`hello.elf` 只在不存在时从只读模块注入，不覆盖用户文件。
- supervisor 文件命令：`ls`/`cat`/`stat`/`rm`/`edit`/`filetest`/`sync`/`exec-file`。
- supervisor 出现后约 1 秒无输入会自动停止旧演示任务 1/2/3/4；`demo keep`
  可保留，供 E03/E04 回归使用。
- `edit` 正文行不经分词器；空行、连续空格、行尾空格原样保存；只有 `:` 开头行是
  命令；保存失败保留编辑缓冲和旧文件。
- `exec-file` 先读完整文件到有界缓冲，校验 stat/open 版本并保持打开到读完，
  再对同一快照做 ELF 检查/映射/启动；普通 `exec <image>` 也先复制到缓冲。
- 内核仍不解析 ELF/文件路径；构造原语按父任务身份/单调 PID 授权；普通 ELF 不继承
  supervisor/builder 权限。最大 8 任务、64 用户页/任务、16 未收集结果。
- wait 真正阻塞/唤醒，结果只收集一次；close 只影响本任务；console read 空为 -3。
- 六个旧平铺 demo 保留 E03 回归；旧 NASM supervisor 已删除。
- E06 的 newlib 只链接 `libc_programs`（当前 `libc_hello`）；旧 SDK 程序保持
  窄 ABI。`build/sdk` 导出 newlib 头、libc.a、libm.a 与 COPYING.NEWLIB；
  SDK manifest 记录版本/哈希。
- `libc_hello` 用 `printf`/`malloc`/`strcpy`/`puts`，退出 7；控制台 I/O、
  静态 64 KiB `sbrk` 堆、errno 基本映射。`open/stat/unlink` 返回 ENOSYS，
  尚未把 POSIX 路径映射到 XOS 文件服务。
- E06 增加每任务 512B、16 字节对齐 FXSAVE 区：CR0.EM/TS 清除，
  CR4.OSFXSR/OSXMMEXCPT 置位，任务切换 fxsave64/fxrstor64；内核仍
  `-mgeneral-regs-only`。E04 的 `fault fpu` 因此改为正常退出 99。
- 用户 ELF 上限由 64 KiB 扩到 128 KiB（libc_hello 66,664 字节），内核
  `sys_image_read` 与装载缓冲同步扩到 131072。
- 结构：boot/x86、kernel/arch/x86_64、kernel/platform/pc、kernel/core、shared、
  user/loader、user/sdk、user/services、user/arch/x86_64、user/programs、
  third_party/fatfs、third_party/newlib 分开。通用内核/装载/SDK 经过第二 ISA
  编译检查，没有 AArch64 可启动系统。

## 版本与实际验证

- 构建 ID：b22ab24c090981b2；源码摘要
  b22ab24c090981b273de502e106dfc40c9ae0a9b94be2d155928d9f1dcf7d973。
- kernel.elf SHA-256：85f5a3d68e2af5375ceb88e97708bb8061c240b6d56ea6cf26021bf43bab2b45。
- kernel.bin SHA-256：da8c8ead758dcf6af6f56d14c00a045bdbbbe2ca51116246b6b46636ef906a98。
- xos.img SHA-256：93ce8fb6c6ef6b28dce6a6f758d7854588d707159c2374dfcb5be7e5f9825e43。
- real_mode.img SHA-256：8b7268b771158dc41f21e5928ad4b33067cf4a5b1de439d9554852b2ac769c72。
- 内核文件 262164 字节 / 513 扇区，内存范围 0x100000–0x153000（约 331 KiB）。
- `sdk/lib/libc.a` 6,720,094 字节，SHA-256
  283fa07ad205c80af92e955a91da027435d8a8a90cb7e27933f57925cc5baa22；
  newlib 4.6.0.20260123。
- GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02、QEMU 11.1.2。
- pc-i440fx-10.0 / qemu64 / TCG / 单核 / 64 MiB / 只读软盘 + 16 MiB IDE 工作盘 /
  无网络。
- make smoke：实模式 6 + 内核 18 + E03 12 + E04 13 + E05 8 + E07 5 + E06 3 = 65 组全部通过。
- E07：第一次启动创建/覆盖/删除并 sync；第二次启动验证正文与删除结果；执行盘上
  hello.elf；文件命名空间满及物理满盘时保存失败，旧文件/编辑缓冲保留（满盘用
  宿主填充的 FAT16 临时盘验证）。
- E06：`libc_hello` 进入 image catalog，`printf`/`malloc`/`string` 输出正确、退出 7；
  第二次运行可复用 stdio/heap；旧 62 项回归通过。E04 FPU 探针改为正常退出。
- 重建整个 manifest 与全部产物哈希一致；实际串口/VGA 证据见 build/。
- 未运行突然掉电、坏扇区、只读盘、16 MiB 媒体写满、目录/LFN、真机/UEFI/SMP。

原始证据：build/manifest.json、smoke_report.json、kernel_smoke_report.json、
task_smoke_report.json、process_smoke_report.json、file_smoke_report.json、
persist_smoke_report.json、full_disk_smoke_report.json、libc_smoke_report.json、
libc_audit.json、*_serial.log、elf_cases*.log、*_portable.log、
user_*_disassembly.log、process_screen.ppm/png、file_screen.ppm/png、
persist_boot1_screen.png、persist_boot2_screen.png（已查看第二次启动 cat 与 sync）、
libc_screen.png（已查看 libc_hello 输出与 exited 7）。关键结论写入 0007/0008/0009/0010。

## 使用与文档

- 首次使用：`make disk` 创建 `work_disk.img`（显式、不覆盖已有盘）。
- `make run`：进入 xos64>；输入 run 后由 sup> supervisor 接管。
- sup> `exec demo hello`、`exec libc_hello`、`ls`、`edit note.txt`、`cat note.txt`、
  `sync`、`exec-file hello.elf`、`ps`/`kill`/`stats` 等。
- 运行文件/装载命令前可能需要 kill 1/3/4 降噪并腾出任务槽。
- `make run_real_mode`：独立 16 位练习；`make debug` 配合 config/debug_kernel.lldb。
- docs/usage/index.md 为每命令一页的索引；supervisor 独立成组。
- e04_loader_sdk.md：ELF 子集/ABI/句柄/生命周期；e05_file_service.md：文件协议、
  打开实例、原子保存、编辑器；e07_persistent_work_disk.md：工作盘、ATA/FatFs、
  同步、恢复与掉电边界；e06_libc.md：newlib、SSE 上下文、适配层与依赖边界；
  e08_native_toolchain_plan.md / e08_stage0_audit.md / e08_pre1_design.md：
  E08 分阶段、审计与 pre1 资源/接口设计。
- architecture_and_boot.md / cpp_subset.md / toolchain.md：架构、语言与工具约定。
- 彩蛋仍可配置关闭；GUO/DUAN 讨论稿未激活新模式或虚假文件命令。

## 状态边界

E01–E07 的本版受限实现完成；E08–E12 未完成。没有原生编译、完整 POSIX、
libstdc++/C++ 标准库、动态链接、TLS、系统重建或原生 GCC；不等于完整 0.0-dev。
原计划 O01–O22 不整体标通过；O09/O10 的 E05 局部证据、O15 的正常同步重启
局部证据见 0008/0009；不把有限检查升级为 POSIX、任意掉电或完整文件系统验收。

E06 明确限制：newlib 只覆盖常用 C 库；`open/stat/unlink` 返回 ENOSYS，没有
POSIX 路径/`fopen`、目录、完整文件服务映射；没有 libstdc++、C++ 异常/RTTI、
TLS、线程、动态链接或 C++ 静态构造。堆是进程私有静态 64 KiB，不是 brk/mmap。
newlib 预构建包约 10 MiB；普通 build 不联网，重建需 `scripts/build_newlib.sh`。
E07 的掉电/坏扇区/只读盘、无目录/LFN、ACPI、单客户端等限制不变。
任务槽固定 8，运行 files 后无空槽。
仍是单 CPU、固定 QEMU/BIOS、内核低地址 identity map、内核栈无 guard；
物理页上限 128 MiB；BIOS 载荷无运行时完整性校验；Cocoa 窗口入口未实测。

## 下一组：E08-1（未开始）

E08-0 审计与 E08-pre1 设计已完成，基线见
[config/e08_pre1_baseline.json](../config/e08_pre1_baseline.json)、
[e08_pre1_design.md](e08_pre1_design.md)、[e08_stage0_audit.md](e08_stage0_audit.md)。
E08-1：先测 512 MiB/2 GiB 盘上的 ATA 吞吐与页表压力，再实现更大工作盘、
流式文件、per-process 文件会话、宿主安装与 >128 KiB ELF 装载 gate。
未通过该 gate 不进入 binutils/GCC。E08 未完成，O11–O13 不标通过；
E09 才做完整编辑—保存—编译—运行试用。UEFI 仍是独立可选路径。
