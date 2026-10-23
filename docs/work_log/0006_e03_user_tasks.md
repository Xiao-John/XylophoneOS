# 0006：ring3 下线，任务真的会跑，坏任务也真的会被收掉

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：E03 在机制层面完成。

## 范围与结果

按 `state.md` 的 E03 约定推进用户隔离、任务、抢占、受保护 IPC、故障回收与
最小监督终端。本组没有把“能打印”当成“有任务”，最终实际跑通：

- ring3 用户程序与独立内核栈；GDT 用户 code/data 选择子 0x2b/0x33。
- 每任务独立 PML4：内核 0–64 MiB 共享 supervisor-only，用户半区 1 GiB 私有；
  代码 RX、数据页与 4 页栈 RW+NX。
- 七个嵌入内核的 NASM 平铺程序：heartbeat、spinner、receiver、sender、probe、
  quitter、supervisor；不是 ELF 装载器或文件系统产物。
- PIC 重映射、PIT 100 Hz IRQ0、round-robin 抢占；只在 ring3 被中断时切换，
  内核入口保持关中断。
- `int 0x80` DPL3 系统调用：write、exit、yield、send、recv、getpid、ticks、
  read、tasklist、kill；用户指针先按范围与页表权限检查，错误返回负数。
- 4 个端点、64 字节单槽邮箱的 IPC；send/recv 权限记录在任务上；无效句柄、
  缺少发送权、超长消息、内核指针、队列满/空都拒绝。
- ring3 异常打印任务 pid/vector/RIP/CR2 后杀死该任务并继续调度；ring0 异常仍 panic。
- 退出/被杀的当前任务延迟到下一任务栈上回收：用户地址空间、页表、用户页与
  内核栈，打印 `[task] event=reclaimed pid=... pages=...`（当前每个任务 10 页）。
- supervisor 用户任务提供 `sup> ` 终端：`ps` 在 spinner 死循环旁返回任务列表，
  `kill <pid>` 终止并回收任务，`help` 列出三条命令；heartbeat 在 kill 后继续。
- 调试控制台新增 `run`；执行后不返回内核控制台。

## 文件

新增：

- `src/kernel/arch/x86_64/frame.hpp`、`interrupt_entry.hpp`、`pic.hpp`、`pic.cpp`、
  `tasks.cpp`。
- `src/kernel/arch/x86_64/interrupts.asm` 重写：IRQ0/0x80 stub、统一中断帧、
  `enter_frame` 与 `interrupt_dispatch` 返回值切换。
- `src/kernel/include/xos/task.hpp`、`syscall.hpp`。
- `src/user/demo/{heartbeat,spinner,receiver,sender,probe,quitter,supervisor}.asm`。
- `tests/task_smoke.py`、`build/task_smoke_report.json`（运行时生成）。

修改：

- GDT/TSS/IDT 与异常分发：`exceptions.cpp`；用户故障不再走内核 panic。
- 地址空间：`paging.cpp` 增加 `create_address_space`、`map_page_in` 与
  `destroy_address_space`。
- 构建：`scripts/build.py` 汇编用户程序并生成 `build/user_blobs.hpp`。
- 控制台与启动：`console.cpp` 的 `run`，`kernel_main.cpp` 的 `tasks_init`。
- 测试：`tests/kernel_smoke.py` 的 stage 更新；`Makefile` 增加 task_smoke。
- 文档：`README.md`、`architecture_and_boot.md`、`toolchain.md`、`usage/`、
  `state.md`、`decisions.md` 与本记录。

没有修改或扫描 `localpilot/`；没有并发构建。

## 选择与原因

- 用户程序先用嵌入的 NASM 平铺二进制，而不是提前做 ELF 装载器。E03 的目标是
  隔离/任务/IPC，E04 才装载宿主交叉编译的 ELF；这样能先验证 ring3 与调度。
- 地址空间复用内核 0–64 MiB 页表、私有用户半区，避免为每个任务复制内核映射；
  用户半区固定在 1 GiB，避开 low identity map。
- 每个任务一个 4 KiB 内核栈，TSS rsp0 在切换时更新；中断帧固定 176 字节，
  由同一套汇编入口在异常、IRQ、syscall 与首次进入之间复用。
- 抢占只在从 ring3 进入时发生；内核入口保持关中断。这样先得到可解释的
  单 CPU 调度，不伪装内核可重入或支持嵌套中断。
- IPC 用静态端点、单槽邮箱和任务级 send/recv 权限，先把句柄、长度、用户指针
  与权限的失败路径做真；阻塞等待、队列深度与撤销留到后续。
- 用户故障只杀当前任务，不 panic 整个系统；当前任务不能在自己的内核栈上释放
  自己，所以用 `reap_pending[8]` 标记，下一次调度在别的任务栈上回收。
- supervisor 是用户任务而不是内核线程：它通过 `read`/`tasklist`/`kill` 系统调用
  工作，证明 ring3 终端能在 spinner 占用时间片时继续响应。

## 环境与实际执行

宿主 macOS 27.0.1 / Apple Silicon；GCC/G++ 16.2.0、Binutils 2.47
（2.47.20260726）、NASM 3.02、QEMU 11.1.2、Python 3.12.15；Clang 21、
LLDB 2103.0.34.103。

```sh
make build
make smoke
```

最终：

```text
PASS: 6 checks | build 4a4622bd71506890
PASS: 18 E02 checks | build 4a4622bd71506890
PASS: 12 E03 checks | build 4a4622bd71506890
```

构建 ID：`4a4622bd71506890`；源码摘要
`4a4622bd715068904fea07478cc2303139a6dd09b5f65957deea2e6a76889a0d`。
连续两次 `make build` 的 build ID、源码与产物哈希相同。

| 产物 | 字节 | SHA-256 |
|---|---|---|
| `kernel.elf` | 202872 | `570d9612e362877f85ab87d1eaed03a37e53afce35a19ad34582f858416811e6` |
| `kernel.bin` | 28688 | `4ceac87fe241ee941d7c3aeab1ba7db9d7ac083851e49b05d969d6331ffc9fd3` |
| `xos.img` | 1474560 | `49ad6638bff3c1e0ac57c35cbb250a2a1c3657a7790c3505d88a760dcb7cfa14` |
| `real_mode.img` | 1474560 | `c4505871c91a34e934c988a10653766de90a38ff227f37b8564b8689ce6e770e` |

内核内存范围 0x100000–0x114000（81,920 字节），文件 57 扇区；仍在 128 KiB /
64 KiB 的 bootstrap 上限内。

实际收口输出摘要：

```text
[task] event=fault pid=5 vector=14 ... cr2=0x0000000000100000 result=killed
[task] event=reclaimed pid=5 pages=10
bye
[task] event=reclaimed pid=6 pages=10
sup> ps
pid=1 name=heartbeat state=r ticks=...
pid=2 name=spinner state=r ticks=...
...
sup> kill 2
[task] event=killed_by_supervisor pid=2
[task] event=reclaimed pid=2 pages=10
kill: accepted
sup> ps
（不再出现 pid=2，heartbeat 继续输出 A）
```

## 验证结果

| 检查 | 结果与证据 |
|---|---|
| ring3 与定时器 | 通过；`[sched] event=start tasks=7`，采样到 CPL=3 |
| 定时抢占 | 通过；spinner 死循环时 heartbeat 持续输出 A |
| IPC 送达 | 通过；receiver 收到 `ping`，sender 输出 `tx` |
| 无效句柄/越权 | 通过；`bad handle rejected`、`no send right` |
| 参数校验 | 通过；`bad length`、`bad pointer` 被拒绝 |
| 用户故障隔离 | 通过；probe 读内核页 #PF，CR2=0x100000，仅 pid=5 被杀 |
| 故障后继续 | 通过；probe 死后 heartbeat 继续输出 |
| 退出 | 通过；quitter 输出 `bye` 后 exit，不再占用时间片 |
| 死任务回收 | 通过；probe/quitter 均打印 `reclaimed ... pages=10` |
| supervisor 终端 | 通过；spinner 运行时 `ps` 返回存活任务列表与 `sup>` |
| supervisor kill | 通过；`kill 2` 回收 spinner，heartbeat 继续；后续 `ps` 不再列出 pid=2 |
| 地址空间 | 通过；采样到多个不同 CR3，且当前 CPL=3 |
| 回归 | 通过；实模式 6 项、E02 18 项继续全绿 |

证据：`build/task_smoke_report.json`（含 CR3 值）、`build/task_smoke_serial.log`、
`build/supervisor_screen.ppm/png`、`build/task_screen.ppm/png`、
`build/manifest.json`、`build/smoke_report.json`、`build/kernel_smoke_report.json`。

## 未运行、失败与限制

- IPC 是单槽、非阻塞，没有多消息队列、等待/唤醒、撤销、超时或动态端点。
- 没有每任务资源上界、用户栈 guard、优先级或时间片配额。
- supervisor 只有 `ps`/`kill`/`help`，不是完整 shell、登录或服务管理；
  `run` 后不能回到内核调试控制台。
- 没有 ELF 装载（E04）；用户程序是嵌入内核的固定 blob。
- 没有用户态 libc/C++ 运行库；用户程序用 NASM 和手写 syscall ABI。
- `sys_exit` 只标记 dead，不向父任务返回退出码；没有 wait。
- 未运行：真机、UEFI、不同机型/CPU、SMP、长时间压力与泄漏统计。
- 计划 O01–O22 仍全部 not_run；E03 的 12 项检查是局部证据，不冒充 O03–O05
  的完整验收矩阵。

## 下一步

进入 E04：用户态 ELF64 装载器与最小 SDK，装载宿主交叉编译的静态程序，
建立启动/等待/退出与初始句柄；保留 E03 的隔离、抢占、IPC、supervisor 与回收回归。
之后再补 E03 剩下的非阻塞限制（多消息/等待、每任务配额）和用户态终端/服务。
UEFI 仍作为独立第二启动路径，不阻塞 E04。
