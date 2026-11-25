# G3：glibc 授权终端、termios/ioctl 与 startup 接收

2026-11-25。独立终端里程碑，基于 PR157 的共享 files API 和 op17 回复校验
修正 `36d5b03`；本地对应提交 `b1774d8`，基础树均为
`76b6aa0de9f7766c66df6f5b48d91a41c7f43fc6`。目录/定位 I/O 已独立交付 PR160，
本轮不重复其实现。全局 state 由主线程汇总，网络/IPC 原任务保持暂停。

## 实现与接口边界

glibc 现在通过真实 native terminal v2 客户端访问已授权会话，支持
`read/write/isatty/fstat`、`tcgetattr/tcsetattr/tcdrain/tcflush` 及六项有限 ioctl。
没有增加 syscall 或改动 terminal wire；具体布局、编号和错误见
[glibc_terminal_v1](../contracts/glibc_terminal_v1.md)。

- `xos_file_runtime.c/h` 正式接入既有 startup kind5，CRT capability bit1 表示真实
  终端后端。v2 只接收已关闭原 stdio 且无其他重定向的授权终端启动；v3 先验证
  完整描述表、唯一对象、flag、扩展和非零序号，再绑定通道及执行 cleanup。
  伪造 controller、peer 或方向不能从 startup 参数取得权限。
- FD aliases 引用同一终端对象；进行中的 I/O 保留固定对象 lease。阻塞前释放
  files 表锁，其他文件操作可以推进，close 后复用 FD 不会重定向原读操作。
  最后一个引用关闭两个通道。每个终端会话由私有 wait/wake 锁串行化。
- glibc generic `termios` 为 44 字节，NCCS=20、VMIN=16、VTIME=17、speed 偏移
  36/40。桥接层逐字段转换到 native 32 字节 mode；不导入 newlib 私有布局。
  接受固定 115200、8N1、无回显/非规范和 `(VMIN,VTIME)` 的 `(1,0)`、`(0,0)`、
  `(0,1..255)`。unsupported 配置保持模式不变并返回明确错误。
- `TCGETS/TCSETS/TCSETSW/TCSETSF` 是 libc 本地编号，调用实际模式服务；
  `FIOCLEX/FIONCLEX` 只修改当前 FD 的 CLOEXEC。无参数或未知 ioctl 不读取
  不存在的 vararg；未知操作区分有效 FD 的 ENOTTY 与无效 FD 的 EBADF。
- native `terminal_client.cpp` 补查保留字段及已知错误值，零序号/无通道和畸形
  回复关闭会话；不自动重连或重放。非空写的零成功回复作为错误处理。
- `libxos_terminal.a` 使用完整 glibc sysroot 重新编译现有 native client 和原生
  syscall 入口。源码、公开头、许可证和输入哈希随 SDK 归档。对象只有静态/零
  初始化，无 `.init_array`、`__cxa` 或 newlib 私有依赖，可在应用构造函数前恢复。

出站 glibc spawn/exec/fork 的终端继承由并行进程模块协调；该模块须在任何
transfer/create 前拒绝 kind5，待序号静默和失败事务完整实现后再开放。此次实际
继承验收是 native 父镜像 exec 到 glibc 接收端。终端库与进程库在同一静态链接
group 内解析，公开 native 头仍由进程 SDK helper 统一归档；终端 helper 使用自己的
私有 include 目录。

## 实际检查

| 检查 | 结果 | 证据 |
|---|---|---|
| 生产 libc FD/termios/native client，模拟内核和 files peer | 23/23 PASS | `host.json` |
| 同上 ASan + UBSan，错误即退出 | 23/23 PASS | `host_sanitized.json` |
| 既有 files 状态机及真实 files.cpp/FatFs | 41 组 + 12 组 PASS | `files_regression.json` |
| 完整 glibc SDK、CRT、终端 archive 构建 | PASS | `build_inputs.json`、`support_build.json` |
| 实际 tty-run 终端程序，三轮 | 3/3 PASS，均 exit(0) | `guest.json`、`guest_serial.log` |
| native exec → glibc 终端接收，三轮 | 3/3 PASS，均 exit(0) | 同上 |
| 既有 files single / threads / native exec，限定复跑 | 3/3 PASS，均 exit(0) | `legacy_guest.json`、`legacy_serial.log` |
| 既有 files 首次启动 | BIOS `BOOT_ERROR: iso_read`，尚未执行用户态 | `legacy_first_boot_failure.json`、对应串口 |
| 当前 ABI 文档检查 | PASS | `abi.json` |

host 用真实客户端检查 v2/v3 绑定、错误 peer/权限/controller、重复通道、错误
序号/保留字段/状态码/模式/长度、服务死亡、超时、中断、零写、短回复和锁存失败。
四 worker 共 400 次 write 验证串行序号；另一个用例让真实客户端阻塞在模拟内核
等待中，主线程关闭全部旧 FD、复用 FD0 为普通文件并完成 I/O，随后原读返回终端
数据并释放最后引用。无效完整 v3 表在连接/cleanup 前失败。

真实客体通过 `tty-run` 创建 terminal 服务并授予 v2 应用通道。程序验证模式/ioctl、
100ms 限时空读、阻塞原始 ESC 序列；阻塞读时另一线程完成真实 files I/O。
600 字节输出经过有界短写与实际 drain。两次握手分别排入 Q/X，再执行 TCIFLUSH
和 TCSAFLUSH，确认丢弃旧输入后仅收到新 F/N 字节。关闭 stdio 后保留 alias，
复用 FD0 为文件，再释放最后终端引用。native 父进程推进真实序号并设定限时模式，
接收端恢复 FD9/FD2、过滤 FD1 CLOEXEC，继续使用原序号和模式。

终端服务启动前资源 `[129717,3,1]`；warmup 后稳态为 `[129533,4,2]`。六次终端
应用结束后均精确回到该稳态。三个既有 files 用例在独立客体中均回到
`[129717,3,1]`。这里的三个数依次为 free pages、tasks、completions。

首轮 files 启动失败与通过的终端测试使用同一 ISO；校验哈希后，仅在新输出目录
做了一次独立私有磁盘复跑，三项均通过。两次报告及串口全部保留，未改引导器、
未加入自动重试策略；该次 BIOS 失败原因尚未定位。

## 来源与构建身份

使用 release `xos-glibc-sdk-preview` 的交叉工具链及独立 glibc sysroot：GCC/G++
16.2.0、Binutils 2.47.20260726、NASM 3.02。QEMU 实际为 Debian 11.1.3，TCG、
单 CPU、512 MiB、私有 FAT32 磁盘、serial-only；AF_UNIX 限制下未启用 QMP。
glibc 2.44 在解包前按 PR154 的锁定签名身份运行 gpgv，通过记录在
`upstream_signature.json`。预览包中工具链与新编译的 glibc/CRT/archive 成套使用。

| 产物 | SHA-256 / 标识 |
|---|---|
| glibc 2.44 archive | `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667` |
| 原始 SDK manifest | `ade36f38cd935c9638bd91515208920ccc97a238edec66386cdb2ab49fbb8add` |
| libc.a | `9a0ad178e62980185bdcf3fcc63bc82957b7296cd8f76d58e8b991de0fcfcf9e` |
| libm.a | `cf250493a856c1ee99f1dea1d4d7987ea6ba39d826fae2f18cdec60a90bdfbd5` |
| libxos_terminal.a | `561877231819474a524482d5a837d42cd53caf48e0912dee9324b6c167e3ecc8` |
| system build ID | `3db4c94136eca727` |
| 原始 system manifest | `b36317576ea158812056bb2fb6dda72bdbfbfdb68ae4d21adcaac5530fc94d99` |
| ISO | `62247edb8a182217935c9694c077c0680666dc10a9a47c92a4a67fc1f2f1d97d` |

冻结目录 [glibc_terminal_20261125](../reports/glibc_terminal_20261125/)
使用平铺 `manifest.json`。发布件为路径规范化派生证据，`derivation.json` 保留原始
相对位置、哈希及转换规则；串口转换 CRLF、去行尾空白，原始日志仍保留在 build。
`build_inputs.json` 收录完整系统与 SDK 输入表；冻结时重新比较所有 SDK、系统、
helper、host 源码和产物身份，源码无漂移。早期 op17 修正前的 23 组 host 结果只作
过程记录，最终资格使用 op17 修正后的完整构建和测试。

## 复现命令

以下在仓库根运行。`PREVIEW_RUN` 指向 release SDK 的运行包装器，
`GLIBC_ARCHIVE` 指向已锁定的 glibc archive；构建脚本自行验证来源签名。
输出目录必须不存在，复跑改用新的目录名；本轮使用下列目录。

```sh
python3 tests/glibc_terminal_host.py --output build/terminal_host_final
python3 tests/glibc_terminal_host.py --sanitize --output build/terminal_host_sanitized
python3 tests/glibc_g3_files_host.py --output build/terminal_files_regression
"${PREVIEW_RUN}" python3 scripts/build_glibc_sdk.py \
  --archive "${GLIBC_ARCHIVE}" --output build/terminal_sdk_initial --jobs 6
"${PREVIEW_RUN}" python3 scripts/build.py --output-dir build/terminal_system_initial
"${PREVIEW_RUN}" python3 tests/glibc_terminal_guest.py \
  --system-build build/terminal_system_initial --glibc-build build/terminal_sdk_initial \
  --output build/terminal_guest_initial --repetitions 3
"${PREVIEW_RUN}" python3 tests/glibc_static_guest.py \
  --system-build build/terminal_system_initial --glibc-build build/terminal_sdk_initial \
  --output build/terminal_legacy_guest --suite files --repetitions 1
"${PREVIEW_RUN}" python3 tests/glibc_static_guest.py \
  --system-build build/terminal_system_initial --glibc-build build/terminal_sdk_initial \
  --output build/terminal_legacy_guest_retry --suite files --repetitions 1
python3 tests/abi_doc_consistency.py --output-dir build/terminal_abi_final
python3 scripts/verify_evidence_index.py docs/reports/glibc_terminal_20261125/manifest.json
python3 tests/report_manifest_check.py
python3 tests/check_public_evidence_paths.py --index --base b1774d8
```

## 缺口与接续

尚未执行 LeakSanitizer（ptrace 环境限制）、完整上游 glibc testsuite、真实硬件
UART/QEMU 11.1.2、连续输入 flush 竞争、客体终端服务死亡、dash 启动、glibc
出站终端 spawn/exec/fork，以及组合 PR160/出站进程模块后的重建验收。
同会话全双工和 pthread cancellation 不在当前串行客户端范围。正常 exit 的
终端 guest 已 join 工作线程；活跃阻塞终端读线程下的 callback/flush/退出回收
须与进程退出模块独立联验，不能把本轮六次结果用于该路径。

后续合并时保留公共 FD/lease/exchange 单一实现，终端只增加 kind5 路由。PR160
`glibc_files_extra_host.py` 须像本轮 `glibc_g3_files_host.py` 一样链接实际
`terminal_support.cpp` 和 `terminal_client.cpp`，再执行八组真实 files/FatFs
回归。进程模块若把唯一 `.xos.exec` 标记加入真实 receiver 对象，应移除
`terminal_public_probe.c` 的条件 fixture 标记，并重新构建/检查单一只读 16 字节
section；`terminal_exec_parent.c` 仍使用独立 native SDK。合并后的 SDK、ELF、镜像
和证据都需重新按组合源绑定，单模块旧产物保留原身份。
