# 0007：ELF 会自己搬家，等待也真的会等

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：E04 完成（受限配置）。

## 任务与基线

用户目标：阅读最新 docs，了解现状并实现 E04。先重新读取 AGENTS、纪律、
state、计划、架构/工具链/C++ 约定、0006 与命令手册、GUO/DUAN 讨论稿。
现场状态已到 E03，不能沿用旧聊天中的 E01 状态。原树基线 4a4622bd71506890：
make smoke 的 6 + 18 + 12 组全部通过。0007 开工范围已登记，不扫描或修改 localpilot，
没有创建子 agent，没有并发构建；根目录仍无 Git 仓库。

## 完成内容与代码位置

- src/user/loader/elf.cpp：用户态 ELF64 little-endian ET_EXEC 检查与受限 LOAD 计划。
  覆盖头/PHDR、目标、文件与虚拟范围、溢出、filesz/memsz、对齐、页重叠、入口、
  W^X、段数/页数，拒绝 INTERP/DYNAMIC/TLS 等不支持特征。
- src/user/loader/load.cpp：读取客体只读模块、先完整检查再创建，逐页复制/清零，
  建栈/argv/标准句柄，提交或失败回滚；没有宿主运行时代执行。
- src/user/programs/supervisor.cpp：C++ ring3 监督/装载服务，新增 images/exec/spawn/
  wait/stats/primtest/elftest。初始 bootstrap 用宿主生成的可信段清单，普通程序的
  ELF 从头到尾在用户态解析；内核没有 ELF 解析器。
- src/user/sdk、user/arch/x86_64、user/include：CRT、syscall 封装、文本与装载库。
  scripts/user_build.py 用导出的同一 SDK 构建 supervisor/demo/fault/spin/slow/echo。
  带符号用户 ELF、打包用 image.elf 与 SDK 都纳入 manifest。
- src/shared/include：真正共享的定宽类型和内部 ABI 1；src/shared/runtime/memory.cpp
  真实实现 memset。原 kernel types.hpp 只转引共享类型。
- arch/x86_64/tasks.cpp：父任务授权的构造原语、提交/取消、标准句柄、真实阻塞 wait、
  正常/故障/终止结果、一次收集、资源上界；普通程序不能获得 builder/supervisor 权限。
- arch/x86_64/paging.cpp：inactive address-space 查询、有效权限合成和 PDPT 回收修复。
  部分构造失败释放页/各层页表/栈；任务资源与完成状态的生命周期分开。
- interrupt 入口 cld；未支持的 FP 用 EM/TS 拒绝。前台等待时单独 Escape 可终止
  被等待程序并恢复 supervisor，保留宿主 Ctrl-C 关闭 QEMU。
- 保留六个 E03 平铺夹具；删除旧 NASM supervisor，避免两份控制台实现。
  核心机制、边界、SDK 用法见 e04_loader_sdk.md；每条 supervisor 命令各有独立文档页。

## 实施中发现与修正

E03 的销毁遍历漏释放私有 PDPT，旧日志每任务回收 10 页，实际应为 11 页；
E04 连续创建会放大泄漏。本组补全该层回收，并让创建失败也完整回滚。
不改写 0006 的历史日志，以本次真实空闲页计数作为新证据。

首次用户态 C++ 链接暴露 GCC 为聚合初始化生成 memset（即使 freestanding）；
新增完整的共享实现后内核/SDK 均无未解释符号。没有写永远成功的接口。
真实 ELF 模块让原 64 KiB 内核文件容量不足，因此将低内存暂存上限扩为 512 KiB、
内核内存上限扩为 1 MiB；逐扇区 BIOS 装载本来支持跨磁道，本组实际跨过旧上限启动。

## 最终环境、命令与版本

沿用 GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02、QEMU 11.1.2；
Apple Silicon macOS，pc-i440fx-10.0 / qemu64 / TCG / 单核 / 64 MiB / 只读软盘 /
无网络。宿主 Clang 21、LLDB 用于检查，不替代 GCC 生成客体代码。

执行：make smoke；随后 make build 比较完整 manifest，再转换/查看实际 VGA 帧缓冲。
最终结果：
- 实模式 6 组通过。
- 内核 18 组通过。
- E03 12 组通过。
- E04 13 组通过（合计 49）。
- 重建前后整个 manifest、所有用户 ELF、SDK 和镜像哈希完全相同。
- 已查看 build/process_screen.png，画面中的 A 是旧 heartbeat 的输出，不是输入污染。

构建 ID：ba125e35e0ef262e。
源码摘要：ba125e35e0ef262e2818ce3dd4317a8d220b96ee463002c572e22d2ad191fb08。
内核文件 139284 字节、273 扇区；
内存范围 0x100000–0x12f000。
逐源文件、工具真实二进制、完整命令及全部 SDK 文件的哈希见 manifest。

| 产物 | 字节 | SHA-256 |
|---|---|---|
| kernel.elf | 463864 | b76bb65bdfac9c3d3bb30ea0738f3d6679e388b30a5e5115282ff7d13c375dc9 |
| kernel.bin | 139284 | 99e4d581f87376a9b4df426162ab344e8585dca2905310c4432041c13406498a |
| xos.img | 1474560 | 8b3206a3d0e8671420fbf22543c236bcc4fcb8ffcac12e5df2ced6c9b9958f37 |
| real_mode.img | 1474560 | 909092d546813a3f419effeb8623c0e03cd881d162c65015ad87f8f996e46847 |
| user_supervisor.elf | 84008 | 6f4548a7c7d7800c434e8b851a06873abbee9976768302b5a7f90f40657cd8d7 |
| user_demo.elf | 40800 | 18f8d6a9c4556ceb2891ea3c1c8988c365567e5ae271c09706989526e2a09f41 |
| sdk/lib/libxos.a | 100250 | cfdc52d2aefbbb8e3b1b2c490e31826e858de67eb5108e53a2ce246c1bcd3406 |
| sdk/lib/libxos_loader.a | 135570 | ededb0ec3f8e6960f349684326284ab6399c3ae7dfa1da3127cfb3ae6ca60a97 |

## 完成审计：要求与实际证据

| 要求 | 证据与结果 |
|---|---|
| 用户态装载器 | ring3 supervisor 链接 elf/load 库；实际 exec 的 ELF 段在客体解析后映射。内核只处理机制请求 |
| SDK 与宿主交叉 ELF | 导出 SDK/CRT/两静态库/linker script；同一 SDK 编译并实际运行 C++ 程序，nm/链接无未解释符号 |
| 段/BSS/栈/argv/初始句柄 | demo 实际检查 1024 个 BSS 字、data 标记、argv[0..2]、stderr、关闭/坏句柄和不可继承构造权，正常退出 42 |
| ELF 拒绝边界 | guest exec bad_magic/bad_interp/bad_overflow 拒绝且未启动；24 项 guest self-check；宿主同组 + 截断 + 512 次 ASan/UBSan 确定性变异 |
| 映射权限 | 读取实际子任务四层页表，对照 ELF flags，检查用户栈 RW+NX/guard 和内核 supervisor-only；readonly/NX 实际 #PF |
| 启动/等待/退出 | slow 的 wait_blocked 与 -7 退出；期间 heartbeat 继续。echo 通过继承 stdin/stdout 完成输入；wait 一次消费，非子任务/重复等待拒绝 |
| 故障与终止状态 | fault 私有页/readonly/NX 为 vector 14；手写 x87 为 vector 7；kind=faulted 独立于 exited。后台 kill=-9、前台 Escape=-27 |
| 创建失败与资源 | primtest 测越界/W+X/内核源/重复页/坏入口/旧句柄/任务槽/64 页上界，abort 后计数恢复 |
| 退出回收 | 10 次 exec demo + wait，每次真实空闲页/任务/记录均等于基线，无 PDPT 增长 |
| 可移植边界 | 全部 user/loader、user/sdk 与共享运行时通过 AArch64 对象编译；没有移植成功的运行声明 |
| 保留基线 | 旧 36 组回归全部通过，包括 ring3/抢占/IPC/异常隔离与符号调试 |

资源基线为 15993 个空闲物理页、3 个任务、
0 个未收集结果（测试为降噪终止旧 receiver/sender，保留 heartbeat/spinner）。
10 轮均为 [15993,3,0]，原始数组保存在 process_smoke_report。
这是有限的实际循环，不是无限时间泄漏证明或完整 ELF 合规/安全证明。

## 原始证据

build/manifest.json、smoke_report.json、kernel_smoke_report.json、task_smoke_report.json、
process_smoke_report.json、process_smoke_serial.log、elf_cases_build.log、elf_cases.log、
各 *_portable.log、user_*_disassembly.log、process_screen.ppm/png。
测试报告均绑定本次构建 ID；E04 报告另外绑定镜像哈希和被观察子任务 CR3。
只读目录中的三个坏 ELF 是故障夹具，不是构建失败产物。

## 限制与下一步

- 文件来源仍是只读启动模块；无文件系统、客体源代码编辑、原生 GCC、自举或完整 libc。
- ELF 文件上限 64 KiB、最多 8 非空 LOAD / 32 PHDR / 64 用户页（含 4 页栈）；
  当前最多 8 任务、16 未收集结果。只支持本版整数型静态 ABI，不支持动态链接、TLS、FP/SIMD。
- 主 supervisor 是受信 bootstrap 服务。没有通用用户身份/服务重启、fork、信号、
  真正 TTY 前后台控制；后台 stdin 会竞争。Escape 是有限串口监督机制，不回滚副作用。
- 内核部分进程逻辑仍在 x86 后端，与中断帧结合；本组把 ELF/策略留在用户态，
  不声称已把整个调度内核抽成跨 ISA 框架。
- 没有真机、UEFI、SMP 或长期压力验证；BIOS 磁盘读失败重试分支未故障注入。
- 原计划 O01–O22 不整体改成通过；O06–O08 的本版受限子集由上表给出证据。

下一组 E05：RAM 文件服务、用户态终端和最小编辑工具、必要 libc 接口；先提供
真实的文件短读/短写/EOF/定位/失败语义，再把模块输入适配为文件服务读取。
保留当前用户态解析器与构造机制，不把文件路径或 ELF 解析移进内核。
E06 再按实际 GCC 依赖选择/扩展 libc。UEFI 可作为独立第二启动路径推进，不阻塞 E05。
GUO/DUAN 讨论稿未自动激活，本组没有新增模式或不真实的 ls/cat。
