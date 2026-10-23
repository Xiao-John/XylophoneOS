# 0003：异常先开口，内存有边界

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：E02 完成，交接已落盘。

## 范围与结果

按 `state.md` 的 E02 约定实现：x86-64 异常入口与可定位 panic、E820 物理页管理、
基本虚拟映射、启动自检和串口调试通路；保持固件/ISA/平台/通用内核分层，并让
现有 `make smoke` 继续作为回归门槛。

本组完成：

- GDT、TSS 与 256 项 IDT；向量 0–31 有统一栈帧，double fault 使用 8 KiB IST1，
  NMI 使用 4 KiB IST2。异常报告 vector/名称、error、RIP/CS/RFLAGS，page fault
  另报 CR2，随后 HLT。
- 物理页分配器消费规范化 E820，覆盖 4 KiB 页、上限 128 MiB；低端 1 MiB、内核
  与 BSS、页表、启动信息不会被分配。分配返回零页；释放未分配页或 double free
  返回 `invalid`。
- 4 KiB `map_page`/`unmap_page`/`query_page`，中间页表按需分配且不回收，叶子
  支持写/执行/用户位并写入 NX。首 4 MiB 保留 4 KiB identity 页，4 MiB 以上用
  2 MiB identity 页（RW+NX），使分配到的物理页可直接访问。
- 启动自检：分配 → 映射到 `0x40000000` → 写读 → 重复映射检查 → 解除映射 →
  释放；任何一步失败则启动失败，不以“最后没死机”代替通过。
- 串口调试控制台：`help`、`mem`、`alloc`、`free`、`vmtest`、
  `pf`/`gp`/`ud`/`div`/`df`、`halt`；真实触发五类异常验证 panic。

## 文件与边界

新增：

- `src/kernel/include/xos/memory.hpp`、`fault.hpp`、`format.hpp`、`console.hpp`。
- `src/kernel/core/memory.cpp`（位图分配器）、`panic.cpp`、`self_check.cpp`、
  `console.cpp`。
- `src/kernel/arch/x86_64/paging.cpp`、`exceptions.cpp`、`interrupts.asm`。

修改：

- `src/kernel/core/kernel_main.cpp`（初始化顺序与启动检查）、
  `src/kernel/include/xos/platform.hpp`、`src/kernel/platform/pc/debug_console.cpp`
  （轮询读串口）。
- `scripts/build.py`（汇编异常入口）、`tests/kernel_smoke.py`（E02 检查）。
- `docs/architecture_and_boot.md`、`docs/cpp_subset.md`、`docs/toolchain.md`、
  `README.md`、`docs/state.md`、`docs/decisions.md` 与本记录。

没有读取、扫描、修改或清理 `localpilot/`；没有对根目录做递归破坏性清理。
`build/` 由本组独占构建，没有与其他 agent 并发。

## 本组选择与原因

- 异常入口用 NASM stub + 统一 C++ 分发，寄存器/栈/IDT 格式留在 arch；通用
  `panic` 只接收规范化 `fault_info`，不直接读 CR2 或异常帧。当前所有异常都
  panic+HLT，不假装已经能恢复任务；恢复属于 E03 及后续。
- double fault 与 NMI 使用独立 IST，避免坏栈把处理器推进 triple fault。自动
  测试不仅读 IDT 的 IST 字段，还用“坏栈触发 #UD”制造真实 double fault。
- 物理页用双位图区分“保留”和“已分配”，使 free 具备可检查的失败语义；只用
  静态位图，不引入堆或 std 容器，也不把 128 MiB 之外的页当作可用。
- 4 KiB 映射接口保留明确的 `already_mapped`/`not_mapped`/`invalid`，不静默覆盖
  既有映射；2 MiB 大页暂不拆分，遇到就返回 invalid，避免隐藏的页表重建。
- 4 MiB 以上 identity 页是 bootstrap 折中：没有 higher-half 时，分配器和页表
  仍能直接访问物理页。它清楚记录为临时方案，不宣称为最终 VMM。
- 调试控制台只轮询 COM1，不加中断、环形缓冲或用户态 ABI；它是 E02 的故障
  注入与内存观察工具，后续终端服务迁往用户态时替换。
- 可屏蔽中断、PIC/PIT/APIC 与定时器本组不做。没有它们就不宣抢占或完整中断
  子系统；E03 再选中断控制器与定时器路线。

## 环境与实际执行

宿主：macOS 27.0.1 / Apple Silicon。工具：GCC/G++ 16.2.0（`x86_64-elf`）、
Binutils 2.47（2.47.20260726）、NASM 3.02、QEMU 11.1.2、Python 3.12.15；
验证用 Apple clang 21.0.0、LLDB 2103.0.34.103。

本组执行：

```sh
make build
python3 tests/kernel_smoke.py
make smoke
```

最终 `make smoke` 输出：

```text
PASS: 6 checks | build 55a648baf5d41e81
PASS: 17 E02 checks | build 55a648baf5d41e81
```

构建 ID：`55a648baf5d41e81`；源码清单摘要
`55a648baf5d41e81146f50c254740f738f9a7a81d80ac6b330fadd97bb651f8a`。
连续两次 `make build` 的 build ID、源码哈希和全部产物哈希相同。

| 产物 | 字节 | SHA-256 |
|---|---|---|
| `kernel.elf` | 123784 | `48e3ff1ed60ce86fa2e10f4348b58d89f443fbe6e6f7562611f11295bf7ff011` |
| `kernel.bin` | 16392 | `0be4cf715c1a5c0717e7573019ca489466e1429349ed0b1838d8223fb5a90c26` |
| `xos.img` | 1474560 | `d3dae82b1cea4d94d06e70ad95a3b212e97429faf850380710d14f5e2e5b9b14` |
| `real_mode.img` | 1474560 | `939c4151c3661641c79bd8b0ad1910099f262a621a533c28b4aca4026a8ed069` |

内核布局：装载 `0x100000`，内存到 `0x111000`，文件 16,392 字节（33 扇区，
从 LBA 17 起）；IDT 位于 `0x10b0c0`；双位图、IDT、IST 与主栈都在内核 BSS 内。
分配窗口 `0x100000–0x3fe0000`；QEMU 64 MiB 下可用 65,023 KiB、管理 65,408 KiB、
16,352 页；自检分配两张中间页表后剩余 16,079 页。

实际启动串口摘要：

```text
[cpu] event=exceptions_ready idt=0x000000000010b0c0 vectors=32 double_fault_ist=1
[mem] event=initialized usable_kib=65023 managed_kib=65408 pages=16352 free_pages=16079 allocated_pages=0
[mem] event=window low=0x0000000000100000 high=0x0000000003fe0000
[vm] event=self_check result=pass address=0x0000000040000000 physical=0x0000000000111000
[boot] result=ready stage=E02
xos64>
```

## 验证结果

| 检查 | 结果与证据 |
|---|---|
| ELF 静态、无隐式运行库/SIMD | 通过；段权限 5/4/6，无 `.init_array/.tdata/.dynamic/.interp`，反汇编无 FP/SIMD |
| BIOS → C++ 长模式 | 通过；启动信息、BSS/data 检查、CR0/EFER、CS64、A20、HLT 均符合预期 |
| IDT 门与 IST | 通过；从客体读 256 字节 IDT，向量 8 为 present interrupt gate 且 IST=1，向量 2 IST=2 |
| E820 物理页管理 | 通过；可用/管理容量与固定 64 MiB 配置一致，窗口从 1 MiB 起，分配页对齐且不在内核范围 |
| 分配失败语义 | 通过；释放后再释放同一页返回 `invalid`，没有伪成功 |
| 4 KiB 映射往返 | 通过；分配 → 映射 `0x40000000` → 写读 → 重复映射 `already_mapped` → unmap → release |
| 页表 W^X | 通过；零页未映射，无同时可写可执行叶项；内核 entry/rodata/data/stack 权限符合链接布局 |
| 4 MiB 以上 identity 页 | 通过；存在的 2 MiB PDE 均带 NX，分配页可访问但不被当作可执行 |
| 控制台 mem/halt | 通过；`mem` 输出窗口与计数，`halt` 后 CPU HLT=1 |
| page fault | 通过；`pf` 产生 `vector=14 page_fault`，CR2=`0xdead0000`，含 RIP |
| general protection | 通过；`int 0x30` 产生 `vector=13`，错误码 `0x182` |
| invalid opcode | 通过；`ud` 产生 `vector=6 invalid_opcode` |
| divide error | 通过；`div` 产生 `vector=0 divide_error` |
| double fault | 通过；坏栈触发 `vector=8 double_fault`，走 IST 后仍能输出并 HLT |
| 无 NX CPU 拒绝 | 通过；`qemu64,-nx` 在进入内核前报 `BOOT_ERROR` 并 HLT |
| 启动信息失败边界 | 通过；宿主用例覆盖坏版本、长度/数量、溢出、重叠、内核不在可用 RAM |
| 第二 ISA 编译 | 通过；`core/*.cpp` 以 AArch64 目标编译；仅耦合检查，未链接或启动 |
| LLDB 符号调试 | 通过；源码断点停在 `kernel_main`，参数 `0x6800`/`0x6000`，符号栈含 `kernel_entry`，detach 后继续到 E02 |

原始证据：`build/manifest.json`、`build/kernel_smoke_report.json`、
`build/kernel_smoke_serial.log`、`build/kernel_registers.log`、
`build/kernel_idt.bin`、`build/bootstrap_page_tables.bin`、`build/fault_page.log`、
`build/fault_gp.log`、`build/fault_ud.log`、`build/fault_div.log`、
`build/fault_df.log`、`build/symbol_debug.log`、`build/kernel.map`、
`build/kernel_elf.log`、`build/kernel_disassembly.log`、`build/kernel_screen.png`。

## 未运行、失败与限制

本组最终检查全部通过；实现过程中修正了 NASM 对异常表绝对地址和外部调用的
警告设置，只关闭确有需要的 `reloc-abs-qword`/`reloc-rel-dword`，其余警告仍为错误。

未运行或未实现：

- 可屏蔽中断投递、PIC/PIT/APIC、定时器与抢占。
- NMI 的真实硬件投递；只验证了 IDT/IST 配置，没有 NMI 注入。
- 用户态、任务切换、每任务地址空间、IPC、ELF 装载。
- 页表中间层回收、2 MiB 大页拆分、栈 guard、内存热插拔或 NUMA。
- 通用堆/new、分配压力下的耗尽与恢复、长时间运行泄漏测试。
- UEFI/OVMF、真机、不同 QEMU 机型/CPU、SMP。
- 从源码重建 GCC/Binutils、跨宿主逐字节可复现；只验证同宿主同工具重建相同。
- Cocoa 可见窗口的实际打开检查、磁盘读失败重试注入。
- 客体单调时钟；事件仍不带客体时间戳，宿主测试超时使用宿主单调时钟。

当前异常一律停机，控制台是临时调试工具；不能把这套行为当成任务级故障隔离、
用户态崩溃回收或稳定终端 ABI。O01–O22 仍全部为 `not_run`，E02 的自检不冒充
阶段验收。

## 下一步

进入 E03：ring3 入口、每任务地址空间、内核/用户页权限、固定或最小 ELF 用户
程序、任务切换与故障回收；再选择 PIC/PIT 或 APIC 路线补定时抢占与最小 IPC。
异常报告需要带上任务身份，panic 与控制台仍需保留可定位的符号路径。

UEFI 可在 E02 基线稳定后作为独立第二条启动路径推进，复用同一 `kernel.elf` 与
启动信息验证器；不阻塞 E03，也不让通用内核出现固件分支。

## 追加（0004，2026-10-23）

用户随后要求控制台加无害特色并把朋友 Guo YePeng 的名字放进去。0004 只改
`console.cpp` 的横幅与 `guo`/`joke`/`about` 只读命令，由 `easter_eggs` 开关
控制，不修改本记录的异常、内存或映射实现。E02 的构建 ID 与产物哈希以
`work_log/0004_easter_egg.md` 为准；本记录前面的 `55a648baf5d41e81` 是加彩蛋
之前的 E02 构建。
