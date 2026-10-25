# 16 位启动原型

本文记录保留的 `build/real_mode.img` 实模式输入输出练习，使用 `make run_real_mode`。
0002 起，默认 `build/xos.img` 已通过独立的 `kernel_loader.asm` 进入 x86-64 C++ 内核；
该主线见 `architecture_and_boot.md`，不要将本文的旧练习限制当作整个系统的状态。

## 启动与地址布局

| 范围 / 位置 | 用途 |
|---|---|
| `0x00000` 起 | BIOS 中断向量和低端固件数据，不覆盖 |
| `0x07c00` 向下 | 原型栈，仅小规模调用；没有栈保护或溢出检测 |
| `0x07c00–0x07dff` | 第一阶段，512 字节，末尾 `55 aa` |
| `0x08000–0x09fff` | 第二阶段的固定 8 KiB 装载窗口 |
| 镜像扇区 0 | 第一阶段 |
| 镜像扇区 1–16 | 第二阶段与零填充，CHS 的 C=0/H=0/S=2..17 |
| 镜像其余部分 | 零填充；没有文件系统 |

固件装入启动扇区后，第一阶段远跳转到 `0000:boot_start`，归一化 CS；
关闭中断建立 DS/ES/SS/SP、清方向标志，保存 BIOS 的启动盘号 DL。
恢复中断后初始化 COM1，使用 BIOS INT 13h 从固定软盘位置读第二阶段。
读失败时重置磁盘，最多尝试三次；仍失败则打印 `BOOT_ERROR: disk_read`
并关中断 HLT。成功后核对第二阶段偏移 2 的 `XOS2` 标识，再远跳转。

第二阶段重新建立栈与段寄存器，切换 BIOS 文本模式 3，输出构建 ID 并进入
轮询输入。COM1 使用 115200/8N1；BIOS INT 16h 提供键盘输入，INT 10h
提供 VGA 文本输出。所有命令仍在同一个实模式地址空间内执行。

`XOS2` 只防止明显装载错误，不是校验和、签名、安全启动或完整格式验证。
磁盘布局与地址仅适用于当前固定镜像；不支持分区、任意 CHS、硬盘启动或 UEFI。
没有 A20 设置、E820 内存图、GDT、页表、异常接管、保护隔离或用户态。
当前 BIOS/QEMU 的 A20 状态不是 XOS 已实现的机制。

## 文件职责

| 文件 | 职责 |
|---|---|
| `boot_sector.asm` | 段/栈初始化、BIOS 装载、失败停机 |
| `stage_two.asm` | 16 位调试命令行、串口/键盘输入、长度边界 |
| `console.inc` | 两阶段共用的串口初始化、串口输出和 BIOS 输出 |
| `layout.inc` | 当前装载地址、扇区数、标识与串口端口 |
| `scripts/build.py` | NASM 构建、容量检查、镜像打包与哈希清单 |
| `scripts/run_qemu.py` | 唯一的 QEMU 配置入口 |
| `tests/boot_smoke.py` | 真实客体输入、键盘注入、损坏镜像与寄存器检查 |

构建生成 `.lst` 地址列表，便于定位 16 位机器码；不是带 DWARF 的内核符号文件。
构建 ID 是 `src/`、`scripts/`、`tests/` 中代码、`config/` 与 Makefile 的哈希摘要前 16 位，
完整摘要和各文件 SHA-256 在 `build/manifest.json`。文档不计入代码 ID。
清单绑定的是代码输入，不承诺不同 NASM 版本生成完全一致的产物。

NASM 开启全部警告并视作错误，flat bin 关闭 `reloc-abs-word` / `reloc-abs-dword`：
固定 ORG 的引导代码确实需要 16/32 位绝对地址，由 NASM 的 bin 后端解析。
内核 ELF 入口另允许经链接器解析的 `reloc-rel-dword`，其余警告仍然报错。
当前已用 NASM 3.02 验证；未验证其他版本。

## 交互与限制

支持 `help`、`about`、`clear`、`halt`，大小写敏感且不做参数解析。接受 CR、LF
与 CRLF，支持 ASCII Backspace/DEL。缓冲区 64 字节，最多 63 字节内容与一个
NUL。输入过长锁定为整行拒绝，直到 Enter；不能靠退格解除溢出状态。
清屏重设 VGA 文本模式，ANSI 清屏序列只送串口。

输入采用忙轮询，UART 没有中断环形缓冲区和流控；输出等待有界，不能因
UART 不响应永远卡住，但不保证串口字符一定送达。暂不保证高速粘贴。
这些是 bring-up 工具，后续迁往用户态终端服务时可以替换。

## 实际验证与待验证

首组证据见 `history/e01_e07.md`。自动验证使用无窗口显示设备，
通过 QMP 注入 BIOS 键盘事件并截取实际 VGA 帧缓冲，不依赖 Cocoa 窗口抢焦点。
验证用的 QMP 只是宿主测试控制，不参与客体启动和命令执行。

磁盘错误的三次重试分支尚未注入故障验证；标识损坏拒绝分支已经验证。
Cocoa 可见窗口启动入口已提供，但尚未实际打开验证。真机、UEFI 和不同虚拟
机配置均未测试。不把本组的局部启动检查升级为计划 O01–O22 已通过。

## 上游资料

实施中核对过以下官方资料；它们说明工具行为，不代替 XOS 的运行证据：

- [NASM BITS](https://www.nasm.us/doc/nasm08.html)
- [NASM bin / ORG](https://www.nasm.us/doc/nasm09.html)
- [NASM relocation warnings](https://www.nasm.us/doc/nasmaa.html)
- [QEMU invocation](https://www.qemu.org/docs/master/system/invocation.html)
- [QEMU PC model](https://www.qemu.org/docs/master/system/i386/pc.html)
