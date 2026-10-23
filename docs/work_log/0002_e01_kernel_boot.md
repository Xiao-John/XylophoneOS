# 0002：E01 工具链、受限 C++ 与 64 位内核睁眼

日期：2026-10-23（Asia/Shanghai）。负责：0002 会话实施，主 agent 复核并补齐本记录。
状态：E01 完成，交接已落盘。

## 范围与结果

用户要求继续 E01：检查已有仓库与宿主，固定 x86-64 启动方案、QEMU、交叉 GCC/G++
与受限 C++ 初稿，得到可复现构建入口、工具版本、镜像和带符号启动日志；同时把
固件、ISA、平台与通用内核分层，减少后续移植的指令集耦合。

本组完成：

- 固定宿主交叉工具与目标，构建入口和版本检查都会拒绝不匹配的工具。
- 默认镜像从 BIOS 启动扇区经独立 `kernel_loader.asm` 进入 x86-64 长模式，
  再跳转独立链接的 `kernel_entry` / `kernel_main`，不再把内核塞进 16 位终端。
- 原 16 位命令行原样保留为 `real_mode.img`，边界检查继续作为回归。
- 受限 C++ 初稿、启动信息契约、页权限与符号调试通路建立并验证。
- 通用 C++ 代码以 AArch64 目标编译通过，作为耦合检查；没有 AArch64 引导，
  这不是移植或第二条系统线。

## 文件与边界

- 配置：`config/toolchain.json`（GCC/Binutils/NASM/QEMU 与 C++ 版本）、
  `config/x86_64_bios.json`（架构/平台/固件、内核容量、彩蛋开关）、
  `config/debug_kernel.lldb`。
- 引导：`src/boot/x86/boot_sector.asm`、`kernel_loader.asm`、`stage_two.asm`、
  `console.inc`、`layout.inc`。
- 内核：`src/kernel/core/`（`kernel_main.cpp`、`boot_info.cpp`）、
  `src/kernel/arch/x86_64/`（`entry.asm`、`cpu.cpp`、`io.hpp`、`kernel.ld`）、
  `src/kernel/platform/pc/debug_console.cpp`、`src/kernel/include/xos/`。
- 宿主工具：`scripts/toolchain.py`、`scripts/build.py`、`scripts/run_qemu.py`。
- 验证：`tests/boot_smoke.py`、`tests/kernel_smoke.py`、`tests/boot_info_cases.cpp`。
- 文档：`docs/toolchain.md`、`docs/cpp_subset.md`、`docs/architecture_and_boot.md`、
  `docs/real_mode_boot.md`、`README.md`、`docs/state.md`、`docs/decisions.md`。
- 没有读取、扫描、修改或清理 `localpilot/`；没有对根目录做递归破坏性清理。

## 本组选择与原因

- 交叉工具选 Homebrew 的 `x86_64-elf-gcc` / `x86_64-elf-binutils` bottle：
  目标为 freestanding ELF，避免把宿主 Apple clang/g++ 的 Darwin 依赖带进客体。
  实际配置含 `--target=x86_64-elf --without-headers --enable-languages=c,c++`
  与 `--without-isl`，线程模型 single。没有从源码重建 GCC/Binutils。
- 内核 C++20，禁用异常、RTTI、TLS、线程安全静态初始化与 `__cxa_atexit`；
  当前无分配器，因此不使用 new/delete，也不把“分配一定成功”写进接口。
- 链接 `-nostdlib -static`，不使用宿主 crt/libc/libgcc；构建检查未解析符号。
  受限规则只覆盖自研内核和底层组件，不约束未来移植的 GCC/libstdc++/应用。
- 引导器采用固定软盘布局和临时页表，优先得到可调试基线；没有提前做通用
  引导平台、文件系统或 UEFI。UEFI 的引入时机写入 `architecture_and_boot.md`：
  E02 的异常与基本内存机制稳定后、持久化磁盘/真机扩展前，用同一 `kernel.elf`
  经 BIOS 与 OVMF 验证。
- 日志用事件/结果/构建 ID，不在没有客体时钟时伪造时间戳；宿主测试超时用宿主
  单调时钟。启动信息是 64 字节的版本化内部契约，固件原始结构不跨边界。

## 实际执行与证据

宿主：macOS 27.0.1 / Apple Silicon。实际工具版本：

- GCC/G++ 16.2.0，target `x86_64-elf`；GNU ld (GNU Binutils) 2.47.20260726。
- NASM 3.02（Jun 29 2026 构建）；QEMU 11.1.2；Python 3.12.15。
- 验证用 Apple clang 21.0.0、LLDB 2103.0.34.103；不替代 GCC 主线。

本轮复核执行：

```sh
make smoke
```

输出：`PASS: 6 checks | build 7c6c694b678eeaf6` 与
`PASS: 7 E01 checks | build 7c6c694b678eeaf6`，退出码 0。该命令先重建再运行
两套客体测试；构建核对固定版本、target 和 GCC 实际 as/ld 路径。

构建 ID：`7c6c694b678eeaf6`；源码清单摘要
`7c6c694b678eeaf630f50ef13584355fd95b2dc28c57bbea44a1c8e2ed9980e9`。

| 产物 | 字节 | SHA-256 |
|---|---|---|
| `kernel.elf` | 41176 | `9fecbc8771a792e9036b69130c4d38871d8634eda789871743d9398f5182e7bd` |
| `kernel.bin` | 8200 | `85af17a931b816b7690d30f6aefcf6c17fecb74f3d5131403d4547947bd46f96` |
| `kernel_loader.bin` | 1253 | `18a6dbd8d495c74919b391ece7621b314922537dc5c4a39a3a5247f08b011be6` |
| `xos.img` | 1474560 | `cad6214e8d35eeb7b35fd7faa2e3004bf3231012c20183899dda21c7dbfa62a3` |
| `real_mode.img` | 1474560 | `21f7607f33f01a1f956927b50a12f956aab83f99f57d7083063abccee03edd23` |

内核布局：装载地址 `0x100000`，文件 8,200 字节（17 个扇区，从 LBA 17 起），
内存范围到 `0x109000`；固定上限为文件 64 KiB、内存 128 KiB。低端页表
`0x1000–0x5fff`、规范化内存条目 `0x6000–0x65ff`、`boot_info` `0x6800`、
原始内核暂存 `0x10000–0x1ffff`、16 KiB 内核栈在 BSS 内。

启动链路：BIOS 扇区把后 16 扇区装到 `0x8000`；loader 检查 long mode/NX/PAE，
收集最多 64 条非空 E820 条目（未知类型按保留），启用并探测 A20，进入 32 位
保护模式后把内核复制到 1 MiB，建立 4 MiB identity map（零页缺席、supervisor-only、
RX/R/RW 分段、WP/NX 开启），跳转 64 位入口；入口清 BSS、设栈、按 SysV AMD64
调用 `kernel_main`。

## 验证结果

| 检查 | 结果与证据 |
|---|---|
| ELF 静态、无隐式运行库/SIMD | 通过；ELF64 x86-64 ET_EXEC，段权限 5/4/6，无 `.init_array/.fini_array/.tdata/.tbss/.dynamic/.interp`，反汇编无 FP/SIMD 寄存器 |
| BIOS → C++ 长模式 | 通过；串口出现 `arch=x86_64 build=...`、`memory_map=complete`、`bss=zero data=valid`、`result=ready stage=E01`；寄存器 CR0/EFER、CS64、A20、HLT 检查通过 |
| 实际页表与 W^X | 通过；从客体读回页表，零页未映射，无同时可写可执行 PTE，entry/rodata/data/stack 权限符合预期 |
| 无 NX CPU 拒绝 | 通过；`qemu64,-nx` 在进入内核前打印 `BOOT_ERROR: cpu_requires_long_mode_nx_pae` 并 HLT |
| 启动信息失败边界 | 通过；宿主 `boot_info_cases` 覆盖坏版本、长度/数量、溢出、重叠、内核不在可用 RAM 等 |
| 第二 ISA 编译 | 通过；`core/*.cpp` 以 `aarch64-none-elf` 编译为对象；仅耦合检查，未链接或启动 |
| LLDB 符号调试 | 通过；源码断点停在 `kernel_main.cpp:11`，查看 `info=0x6800`、`regions=0x6000`，符号栈含 `kernel_entry`，完成后 detach |

原始证据：`build/manifest.json`、`build/smoke_report.json`、
`build/kernel_smoke_report.json`、`build/kernel_smoke_serial.log`、
`build/kernel_registers.log`、`build/symbol_debug.log`、`build/kernel.map`、
`build/kernel_elf.log`、`build/kernel_disassembly.log`、
`build/bootstrap_page_tables.bin`、`build/kernel_screen.ppm` / `kernel_screen.png`。
同环境重复 `make build` 的完整 manifest 与产物哈希相同；VGA 截图已人工查看。
清单记录实际命令、工具可执行文件哈希与逐源文件哈希，不只依赖版本字符串。

## 未运行、失败与限制

本轮复核未出现失败检查；0002 的实施过程中没有留下未解释的失败（此前 0001 的
NASM `reloc-abs-word` 处理已记录）。以下检查未运行或未实现：

- 真机、其他 QEMU 机型/CPU、UEFI/OVMF 启动。
- 从源码构建 GCC/Binutils；当前只验证了 bottle 安装的工具与配置。
- 跨宿主逐字节可复现；只验证同宿主同工具重建相同。
- Cocoa 可见窗口启动入口的实际打开检查（测试全程无窗口，避免抢焦点）。
- 磁盘读失败重试分支的故障注入（标识损坏拒绝已有验证）。
- AArch64 链接或启动；第二 ISA 只有编译检查。
- FP/SIMD 寄存器保存；当前内核不生成相应指令，也没有上下文保存机制。

当前系统限制：没有 IDT/异常接管、panic 回收、物理页分配器、通用 VMM、
定时器、用户态、任务/抢占、IPC、ELF 装载、文件系统、UEFI 或原生 GCC。
中断保持关闭，内核打印启动检查后直接 HLT；调试串口/VGA 是临时内核输出，
不是用户态终端服务。启动载荷是受信构建产物，无运行时校验；固定布局、
64 KiB/128 KiB 上限和 4 MiB identity map 都是 bootstrap 临时方案，不是
长期内存管理策略。O01–O22 仍全部为 `not_run`，E01 的局部检查不冒充阶段验收。

## 下一步

进入 E02：建立 IDT 与异常入口（至少 page fault、GP、double fault），panic
输出可定位 vector/错误码/RIP/CR2 并保留符号栈；基于 E820 建立物理页管理，
提供可失败的分配接口与基本映射/解除映射，替换固定 4 MiB identity map 的
临时做法；确保 low-reserved、内核、BSS、启动栈、页表和启动信息所占内存
不会被分配器再次分配。补客体单调计时或明确记录仍缺。

保持 `make smoke` 的实模式与 E01 检查为回归门槛；异常/内存边界稳定后再引入
UEFI 第二条启动路径。不要先把用户态、文件系统或原生 GCC 当作 E02 的前置。
