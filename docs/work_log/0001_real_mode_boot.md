# 0001：下划线获胜，XOS 睁眼

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：本组完成。

## 范围与结果

用户要求将轻松开发与多 agent 交接准则落盘，注意文件结构，并开始实模式代码。
本组建立开发入口、纪律、当前状态、实施决定和设计文档；实现 BIOS 16 位
双阶段启动、串口/VGA 输出与串口/BIOS 键盘输入的最小调试命令行。
最终目标依旧为 x86-64；本组不宣称完成微内核、E01 或 E02。

## 文件与边界

- 根目录：`AGENTS.md`、`README.md`、`LICENSE`、`Makefile` 与 `.gitignore`。
- 规范与交接：`docs/Discipline.md`、`state.md`、`decisions.md`、
  `real_mode_boot.md` 和本记录。
- 启动代码：`src/boot/x86/{boot_sector.asm,stage_two.asm,console.inc,layout.inc}`。
- 宿主工具：`scripts/build.py`、`scripts/run_qemu.py`。
- 客体验证：`tests/boot_smoke.py`。
- 构建产物与日志只在 `build/`；没有读取或改动 `localpilot/` 内的文件。
- 保留 `docs/xos_plan.md` 原样，路径与用户最初给出的 `XosPlan.md` 不同。

本组使用自写 BIOS 启动练习，是对用户实模式要求的实施选择；未把它扩展为
通用引导平台。固定装载、命令行轮询等限制见 `real_mode_boot.md`，后续可以替换。

## 环境与实际操作

宿主 macOS 27.0.1 / Apple Silicon。工具实际输出：

- NASM：`NASM version 3.02 compiled on Jun 29 2026`。
- QEMU：`QEMU emulator version 11.1.2`。
- Python：3.12.15，构建和测试仅用标准库。
- QEMU：`pc-i440fx-10.0`、`qemu64`、TCG、单核、64 MiB、无网络，
  只读 raw 软盘，BIOS 启动。完整参数在 `scripts/run_qemu.py` 与 smoke 报告。

安装 NASM 与 QEMU 时，默认镜像缺部分资源并回退到 ghcr.io，连接失败。
NASM 单独重试安装成功；QEMU 改用中科大镜像安装成功。镜像环境变量仅用于
该次安装命令，没有修改用户的全局 Homebrew 配置或授权其他 tap。

第一次 `make smoke` 在构建阶段失败：NASM 3.02 的 `-Wall -Werror` 把
`16-bit absolute section-crossing relocation [-w+error=reloc-abs-word]`
提升为错误。核对 NASM 警告说明与 fixed-ORG flat bin 的地址需求后，显式仅关闭
`reloc-abs-word`；其余全部警告仍作为错误。修正后重建和运行通过。

最终执行：

```sh
make smoke
sips -s format png build/boot_screen.ppm --out build/boot_screen.png
make build
```

最后一次 `make build` 前后由独立 Python 检查比较整个 manifest，结果完全相同，
包括全部产物的 SHA-256。VGA PNG 来自 QEMU 实际帧缓冲，已人工查看，文字、
构建 ID 与提示符显示正常。

## 版本与产物绑定

- 构建 ID：`474989cc7f7d2b68`。
- 源码清单摘要：`474989cc7f7d2b682af50cf0c6702804f6520c9d1db5885071e58f750802fd78`。
- `boot_sector.bin`：512 字节；SHA-256
  `b0f1a71bad28d36e73f1015222f69ea3297df26e46f768b6b334421873582620`。
- `stage_two.bin`：950 字节，限制为 8192 字节；SHA-256
  `13d7abc783a13ea640125ddc4a172096ded9e417eeca2706b8874a0e20f657fb`。
- `xos.img`：1,474,560 字节；SHA-256
  `b9f5c588b3accd60bddfdc676a631f4fe77f83db37d1097b6d7c3c5698e7cd82`。

根目录无 Git 仓库，因此没有 commit ID；完整逐源文件哈希在 manifest 中。

## 验证结果

`make smoke` 最终输出：`PASS: 6 checks | build 474989cc7f7d2b68`。

| 检查 | 结果与证据 |
|---|---|
| BIOS 启动与版本 | 通过；串口出现第二阶段、正确 build ID 和 `xos> ` |
| 串口命令与边界 | 通过；help/about、未知命令、CR/LF/CRLF、Backspace/DEL、空行、63 字节边界、64 字节拒绝及拒绝后恢复 |
| BIOS 键盘命令 | 通过；QMP 注入 h/e/l/p/Enter，客体实际返回帮助信息 |
| 清屏命令 | 通过；串口清屏序列与完成信息，VGA 路径调用 BIOS 文本模式；清屏后像素未单独验收 |
| 停机 | 通过；命令输出后寄存器 `HLT=1`；快照中 CR0=0x10、EFER=0，仍在实模式 |
| 第二阶段损坏 | 通过；仅修改测试副本的标识，打印 `BOOT_ERROR: stage_two_magic` 并 HLT，不进入命令行 |
| 同环境重建 | 通过；manifest 与产物哈希完全相同 |
| VGA 启动画面 | 已查看实际截图；欢迎文字与提示符正常 |
| 磁盘错误重试 | 未运行故障注入；不将标识损坏测试视为读错误测试 |
| 可见 Cocoa 窗口 | 未运行；测试全程无窗口，避免抢焦点 |

原始日志：`build/boot_smoke_serial.log`、`bad_stage_serial.log`、
`boot_smoke_qemu.log`、`bad_stage_qemu.log`、`halted_registers.log`。
`build/smoke_report.json` 记录检查名称、QEMU 版本、命令与镜像哈希。
测试结束后 QEMU 的 signal 15 退出日志是测试驱动的正常收尾。

## 尚未实现与下一步

没有保护模式、长模式、C++ 内核、异常接管、内存管理、隔离、IPC 或文件系统。
命令直接在同一实模式地址空间执行，镜像上没有可写工作文件。BIOS 服务仍是
启动原型依赖，不能拿它冒充 XOS 自己的文件/终端服务。O01–O22 均未完成正式验收。

下一组先继续 E01 的 x86-64 GCC/G++ 交叉工具链、受限 C++ 初稿和符号调试；
随后处理 E820/A20、引导信息与内核装载布局、GDT/页表/长模式过渡。
不要直接把 C++ 或整个内核拼进当前第二阶段终端。
