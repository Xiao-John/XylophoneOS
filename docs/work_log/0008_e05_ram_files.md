# 0008：文件住进 RAM，编辑器不再吃掉空格

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：E05 本版受限实现完成。
后续：0009/E07 已把 RAM 后端替换为 FAT16 工作盘；本文保留 E05 当时的 RAM 证据，
持久化/同步/恢复见 work_log/0009_e07_persistent_disk.md。

## 范围与结果

用户要求阅读最新 docs 并实现 E05，同时把实施顺序改为 E05 → E07 → E06。
本组只做 E05：独立 RAM 文件服务、用户态终端文件命令、最小编辑器、文件装载，
并为 E07 的持久化后端留接口。E06 的 libc/编译器依赖审计未开始。

完成：

- 新增 ring3 `files` 任务，与 supervisor 一样由内核按可信 bootstrap 段清单装入；
  内核不解析 ELF、路径或文件内容。
- supervisor/files 使用请求/响应两个固定端点，单消息 4096 字节；E03 旧端点仍为
  64 字节，旧语义不变。
- 文件与打开实例分离：文件名字/大小/版本/内容槽，打开实例持有游标/方向；
  两个独立打开不共享偏移。4 文件 × 24 KiB、8 打开。
- 读支持短读与 0=EOF；写返回实际字节；无效句柄/方向/容量/满/不存在都返回真实
  错误，不做假成功。
- 原子保存：begin/chunk/commit/abort，staging 通过 owner PID 清理不同会话残留；
  commit 才替换旧文件，失败/客户端会话中断不截断旧文件。
- `edit` 原始行模式：正文不经分词器，空行/连续空格/行尾空格原样保存；只有
  `:` 开头行是命令；保存失败保留编辑缓冲。
- `exec-file` 先把完整文件读入有界缓冲，校验 stat/open 版本并保持打开到读完，
  再对同一快照做 ELF 检查/映射/启动；普通 `exec <image>` 也先复制到缓冲。
- supervisor 新增 `ls`/`cat`/`stat`/`rm`/`edit`/`filetest`/`exec-file`；启动时把
  `hello` 启动模块复制为 RAM 文件 `hello.elf`（9128 字节）。

## 文件与结构

新增：

- `src/shared/include/xos/file_abi.hpp`：请求/响应、错误、容量与操作。
- `src/user/services/files.cpp`：RAM 文件服务。
- `src/user/services/file_ui.cpp`：客户端命令、编辑器、filetest。
- `src/user/include/xos/file_client.hpp`、`src/user/sdk/file_client.cpp`：文件客户端。
- `src/user/include/xos/file_ui.hpp`。
- `src/user/programs/hello.cpp`：文件装载演示程序。
- `tests/file_smoke.py`、`docs/e05_file_service.md`。
- `docs/usage/supervisor/{ls,cat,stat,rm,edit,filetest,exec-file}.md`。

修改：

- `src/kernel/arch/x86_64/tasks.cpp`：端点容量、`ipc_handles`、files 任务 bootstrap、
  请求/响应端点。
- `src/kernel/.../tasks.cpp` 的 8 任务上限使用新 `files` 槽；旧 demo 保留。
- `src/user/loader/load.cpp`：`spawn_buffer`，装载从完整内存快照开始。
- `src/user/programs/supervisor.cpp`：文件命令、`exec-file`、初始化 hello.elf。
- `scripts/user_build.py`：files 服务、hello、bootstrap 段、SDK 文件客户端。
- `tests/task_smoke.py`（任务数 8）、`tests/process_smoke.py`（E05 横幅）。
- `Makefile` 增加 file_smoke；README/state/decisions/toolchain/usage 文档同步。
- 未修改 `localpilot/`；未创建并行 agent；未并发构建。

## 选择与原因

- 文件服务做成独立任务而非 supervisor 内部模块：客户端/服务边界、邮箱忙、
  部分失败与资源回收才有真实对象。supervisor 是当前唯一客户端，后续可加。
- 固定 4096 字节消息与端点容量：避免 64 字节下 64 KiB ELF 需要上千次往返；
  旧端点仍 64 字节，旧超长拒绝测试不被放宽。
- `files` 与 supervisor 都走可信 bootstrap 段清单：内核仍不解析 ELF；不为了
  服务发现提前做动态端点。
- 文件/打开实例分离；打开期间替换/删除 busy，避免游标指向被换掉的内容。
- 原子替换用 staging，而不是先 truncate；容量检查在 commit 前完成，old file
  在失败路径保持不变。
- 编辑器正文不经分词器；只有 `:` 命令行走解析，满足空行/连续空格/行尾空格。
- `exec-file` 先读完整文件、再校验/装载；不在校验后重新读文件，消除版本竞态。
- 文件服务协议只传名字/偏移/长度/版本/状态，不传指针/槽下标；E07 可换后端。

## 环境、命令与证据

宿主 macOS 27.0.1 / Apple Silicon；GCC/G++ 16.2.0、Binutils 2.47.20260726、
NASM 3.02、QEMU 11.1.2、Python 3.12.15；Clang 21 / LLDB 仅验证。

```sh
make build
make smoke
```

最终：

```text
PASS: 6 checks | build 0914a4def600913f
PASS: 18 E02 checks | build 0914a4def600913f
PASS: 12 E03 checks | build 0914a4def600913f
PASS: 13 E04 checks | build 0914a4def600913f
PASS: 8 E05 checks | build 0914a4def600913f
```

构建 ID：`0914a4def600913f`；源码摘要
`0914a4def600913f9481bbd45eb7db5548473af1ee70282a3204cac433c7333f`。

| 产物 | 字节 | SHA-256 |
|---|---|---|
| `kernel.elf` | 532240 | `7e766e8775735de1201ffc03045bdb9c9763ddbd6a640a55c1bed39418a39ecc` |
| `kernel.bin` | 172052 | `4ec00c0114c4985e4cbfd1e0e846bbccf9990bfdd80ec7ba04e79cffec149345` |
| `xos.img` | 1474560 | `169439d7ceed8bf846358b9ac97492edd66974ef389f7399c94c6d6a864e5fb7` |
| `real_mode.img` | 1474560 | `0f168b8192a5d0c144866aab659168bb1fbcdf1a856935b5ff5f002ad48baff6` |
| `user_files.image.elf` | 9680 | `ad15adef2c79fc805e9653b4e2cfcbbbea6f8eb024ef2ac3183742fe50ebbd22` |
| `user_supervisor.image.elf` | 25776 | `9356606a297b3737f054fdf630664608fbb37b24283f82ab0bcde2269b6a54b8` |
| `user_hello.image.elf` | 9128 | `89d1c1f564714a949ddbed524975bdb7e055a83fc9307a868320474174d0896f` |

内核文件 337 扇区，内存范围 0x100000–0x13b000（约 236 KiB），仍在 1 MiB
内核内存上限内。任务总数为 8（六个旧夹具 + supervisor + files）；启动后无空槽，
测试通过 kill 1/3/4 降噪/腾槽后执行文件与装载命令，不把槽位上限藏起来。

## E05 验证

| 检查 | 结果与证据 |
|---|---|
| 文件服务启动/列表 | 通过；`[files] ready hello.elf bytes=9128`，`ls` 显示 hello.elf |
| 短读/EOF/独立打开 | 通过；`filetest` 两打开各自游标，读到 5 字节后下一次 0 |
| 容量/旧文件保留 | 通过；超容量 begin 返回 no_space，旧文件 size 不变 |
| 部分写入 | 通过；写到文件尾只返回实际 2 字节，size 到上限 |
| 无效句柄 | 通过；read(99) 返回负错误 |
| 编辑器空格/空行 | 通过；`first line`、空行、`  two  spaces  `、`third` 原样 cat |
| 修改既有文件 | 通过；加载 34 字节，追加 `fourth` 后 41 字节，旧行保留 |
| 文件错误 | 通过；missing 的 cat/stat 返回 `error=-1`，不伪造空内容 |
| 删除 | 通过；rm 后 ls 不再列出，打开实例会 busy（filetest/协议） |
| 文件装载 | 通过；`exec-file hello.elf` 读到完整快照，hello 输出、exited 0 |
| 回归 | 通过；实模式 6、内核 18、E03 12、E04 13 全绿（合计 57） |

原始证据：`build/manifest.json`、`build/file_smoke_report.json`、
`build/file_smoke_serial.log`、`build/file_smoke_qemu.log`、`build/smoke_report.json`、
`build/kernel_smoke_report.json`、`build/task_smoke_report.json`、
`build/process_smoke_report.json`、`build/user_*_disassembly.log`、
`build/file_screen.ppm/png`（实际 VGA 帧缓冲，已查看）。
编辑器/文件服务交互以真实串口输入和客体文件内容验证，不是宿主侧模拟。

## 已知限制与失败边界

- 重启后文件全部丢失；没有持久化、同步或掉电语义，E07 才做。
- 单层名字，无目录、无时间戳、无权限 ACL；最多 4 文件、24 KiB/文件、8 打开。
- 单客户端（supervisor）；没有多客户端并发、阻塞锁、撤销或服务重启。
- staging owner PID 只用于单客户端残留清理，不是可信 sender 身份；客户端在
  分块中途退出时，下一次不同 owner 的 begin 会丢弃旧 staging。
- 客户端超时返回 would_block，不自动重放写；commit 是唯一提交点。没有完整
  故障恢复/事务日志。
- 编辑器正文不能以 `:` 开头（无转义），不是全屏编辑器，没有撤销/搜索。
- 没有 libc/POSIX open/read/write 语义；SDK 文件接口是 XOS 内部 ABI，E06 才选
  libc。没有原生编译或系统重建。
- 任务槽固定为 8，运行文件服务后无空槽；这是容量限制，不是崩溃。
- 未运行：重启持久化、掉电、长时间压力、并发文件服务客户端、真机/UEFI/SMP。

## 下一步

按用户确认的顺序进入 **E07**：块设备与持久文件系统适配，替换 RAM 后端并明确
同步/掉电保证；保留 E05 的客户端协议、打开实例和原子替换语义。之后再进 E06
做 GCC/G++ Seed 依赖审计与 libc 选择。UEFI 保持独立可选路径。
