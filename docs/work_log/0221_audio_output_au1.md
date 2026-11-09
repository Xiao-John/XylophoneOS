# Audio output AU1：受限 PC Speaker PIO 与强制静音

## 范围与实现

在 `codex/audio-output-au0` 实现 AU1 的单所有者 PC Speaker 机制，不增加 syscall 编号，
不实现音频服务、旋律队列或 SDK。资源登记在 sys82：资源 2 仅允许 `0x42`、`0x43`、
`0x61`，授权链复用真实 supervisor 到直接 building 子进程。TSS 端口图按具体端口设置，
没有放宽成覆盖中间端口的连续大窗口；COM1 resource 1 保持原规则。

子进程首次进入用户态时启动最长 2,000 ms 的系统单调时钟租约。IRQ0 每 tick 检查截止
时间；100 Hz tick 下超时执行误差上限为一个 tick（10 ms）。sys82 resource 2 的 `release`
让所有者提前静音并放弃端口权；授权者可撤销。到期、正常/故障/强杀退出、成功 exec
替换和撤权均停止硬件、清除权限并释放唯一所有者。架构 halt（包括 panic 停机）调用
PC 平台幂等 safety stop，只清 `0x61` bit 0/1，保留其他位。fork 不复制权限。

## 选择与限制

- 按 C20/C28/C29 将音符策略留在用户态；内核只做固定资源授权、截止时间和必要 safety stop。
- 不开放 IOPL、其他 PIT 端口或 IRQ。权限范围不证明 channel 0 的运行时没有漂移；本阶段还没有客体测量。
- 当前是直接 PIO grant，授权程序必须自己校验音高与时长。内核租约保证任何未响应所有者最多约 2 秒后静音，但不强制频率白名单或声学音量。
- 资源 2 租约不可续期；AU1 只覆盖短单音机制。多音轮转和服务连接失效语义留待 AU2 设计。
- `docs/state.md` 不改：纪律限定该文件只由整体合入/发布/里程碑时更新。AU0 报告冻结不改写。

## 修改文件

- `src/shared/include/xos/process_abi.hpp`：登记资源 2 与 owner `release=5` action。
- `src/kernel/arch/x86_64/io_bitmap.hpp`、`exceptions.cpp`、`interrupt_entry.hpp`：建立精确
  TSS speaker port set，并和现有 COM1 窗口共存。
- `src/kernel/arch/x86_64/tasks.cpp`：speaker 所有者、首次用户态租约、到期检查、release、
  revoke 和进程生命周期清理。
- `src/kernel/platform/pc/speaker.cpp`、`src/kernel/include/xos/platform.hpp`、
  `src/kernel/arch/x86_64/cpu.cpp`：PC gate safety stop 与 halt/panic 清理。
- `docs/contracts/pio_grant.md`、`docs/contracts/abi_registry.md`、`docs/e04_loader_sdk.md`、
  `docs/plans/audio_output.md`：更新资源接口、状态和边界。

## 检查与证据

- `git diff --check`：通过。
- `python3 tests/report_manifest_check.py`：通过；所有报告目录合规/祖父规则检查均无失败。
- 用宿主 GCC 14.2.0、项目 freestanding 警告选项编译 5 个变更 translation unit：通过。
  `tasks.cpp` 的两个 build-generated header 使用宿主临时目录中的最小结构占位，
  所以这是语法检查，不是正式目标构建；对象仅写入宿主临时目录。
- 临时 bitmap 检查逐一遍历 65,536 个端口：只允许 `0x42`、`0x43`、`0x61`，通过。
- 正式 `python3 scripts/build.py`：未能开始，宿主没有 NASM。通过 AU0 留存的 Docker QEMU
  11.1.3 镜像尝试构建后，构建因缺少规定的 `x86_64-elf-as` 停止。没有临时伪装工具链版本。
- 客体启动、无权 #GP、切换隔离、到期、进程 fault/kill/exec/revoke、频道 0 漂移及实际 WAV
  捕获：未运行，正式 x86_64-elf 构建工具链不可用；AU1 不能标记为客体验收完成。

## 后续

补齐与 `config/toolchain.json` 一致的 x86_64-elf GCC/Binutils 和 NASM 后，先构建私有镜像，
对资源 2 做真实 supervisor grant、精确端口边界、release、到期、owner exit/fault、revoke
与调度时钟测试。通过前不要开始 AU2 服务，也不要宣称已在 XOS 客体发声。
