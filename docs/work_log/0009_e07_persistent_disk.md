# 0009：文件终于会在重启后还在

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：E07 本版受限实现完成。

## 范围与结果

按用户设计走“独立工作盘 → 最小块设备 → FatFs → 现有 files 服务”，目标为
正常保存、`sync`、停止 QEMU、再次启动后内容仍在。保留 E05 的编辑器/装载器
客户端接口；UEFI 不在关键路径。用户顺序为 E05 → E07 → E06，本组只做 E07。

完成：

- 根目录 `work_disk.img` 作为独立 FAT16 工作盘，`make disk` 显式创建/格式化；
  已存在时默认不覆盖，`--force` 才重建。构建/启动只打开已有盘。
- QEMU 增加 `if=ide,index=0,media=disk,cache=writeback`；`make run` 缺盘报错，
  不退回 RAM。测试用临时盘副本，`make smoke` 不写日常盘。
- 内核 ATA PIO primary master：IDENTIFY、LBA28 读写、FLUSH CACHE、每请求最多 8
  个 512B 扇区、忙/DRQ 有界超时。硬件端口在 platform/pc。
- 块系统调用 `block_read/write/sync/info` 只允许 `files` 任务；验证扇区范围与
  用户缓冲，不接受物理地址/端口。内核不解析 FAT/路径/内容。
- 用户态 FatFs R0.16（`src/third_party/fatfs`），8.3 短名、无 LFN/RTC/mkfs；
  挂载失败报错、不格式化、不退回 RAM。最多 4 文件、24 KiB/文件、8 打开。
- 保存 staging + 磁盘提交：`XOSTMP.TMP` + sync → `XOSJRNL.TMP` → 旧目标改名
  `XOSBAK.TMP` → 临时文件改名目标 → `CTRL_SYNC` 成功后才删备份/journal。
- 启动恢复：journal 存在时，目标缺失从备份恢复；目标存在清理陈旧备份；清理
  temp/journal；恢复失败进入 io，不假报可用。
- supervisor 增加 `sync`：所有写打开 `f_sync` + `CTRL_SYNC`，成功才打印
  `[files] sync=ok`。`hello.elf` 只在不存在时注入，不覆盖用户文件。
- 两次独立启动验证：第一次创建/覆盖/删除并 sync，第二次验证正文、删除、执行
  盘上的 `hello.elf`；另测文件命名空间满时保存失败，旧文件与编辑缓冲保留。

## 文件与结构

新增：

- `scripts/make_work_disk.py`：显式创建 FAT16 工作盘（16 MiB，512B 扇区，
  8 扇区/簇，2 FAT，512 root entries）。
- `src/kernel/include/xos/block.hpp`、`src/kernel/platform/pc/ata.cpp`。
- `src/third_party/fatfs/`：FatFs R0.16 的 `ff.c/ff.h/ffconf.h/diskio.h` 与
  `ff_string.h`（短名/无 LFN 配置）。
- `src/user/services/fatfs_diskio.cpp`：FatFs 到受限块系统调用的 glue。
- `tests/persist_smoke.py`、`docs/e07_persistent_work_disk.md`。

修改：

- `scripts/run_qemu.py`/`tests/boot_smoke.py`：可选工作盘；默认 run 需要已有盘。
- `scripts/make_work_disk.py`、`Makefile` 的 `disk` 目标、`.gitignore`。
- `src/kernel/arch/x86_64/tasks.cpp`：块 syscall、files 的 block_access、4 KiB
  bounce；`kernel_main.cpp` 启动时探测 ATA 并打印 device/absent。
- `src/user/services/files.cpp`：RAM 后端替换为 FatFs；保留协议、打开实例、
  原子提交与错误语义。
- `src/user/services/file_ui.cpp`：`hello.elf` 仅在缺失时注入；`sync` 命令。
- `src/user/programs/supervisor.cpp`：`sync` 命令与帮助。
- `src/shared/runtime/memory.cpp`：补 memcpy/memmove/memcmp/strchr/strlen。
- `src/user/sdk/file_client.*`：sync；`src/shared/include/xos/file_abi.hpp`：sync。
- `tests/file_smoke.py` 改用临时 FAT16 盘；Makefile 增加 persist_smoke。
- README/state/decisions/toolchain/architecture/usage/E05 文档同步。

没有修改 `localpilot/`；没有创建并行 agent；没有并发构建。

## 选择与原因

- ATA PIO 先于 DMA/中断：轮询、LBA28、8 扇区上限足以完成首轮持久化；超时和
  no-device 都返回错误，不让终端卡死。
- 内核只暴露受限扇区机制，FatFs/路径/文件内容全在用户态；硬件端口留在 platform。
  这比在 ring3 直接 in/out 更符合当前权限边界。
- FatFs 挂载失败不格式化、不切 RAM；避免“看起来持久”的假成功。
- 旧目标 → 备份 → 新目标 → 同步 → 清理的提交顺序，明确 FatFs `f_rename`
  不能覆盖目标；journal 记录目标名，启动恢复有据可查。
- `sync` 必须同时覆盖文件缓存和块设备 FLUSH；只 `f_sync` 不宣称掉电原子性。
- 工作盘在仓库根、独立 `build/`；`make disk` 显式，测试只用临时副本。
- FatFs 短名 8.3 与现有 `hello.elf`/`note.txt` 兼容；显示为大写，文档明确。

## 环境与版本

宿主 macOS 27.0.1 / Apple Silicon；GCC/G++ 16.2.0、Binutils 2.47.20260726、
NASM 3.02、QEMU 11.1.2、Python 3.12.15；Clang 21/LLDB 仅验证。
FatFs R0.16 源码来自官方/镜像，保留版权头；配置为短名、code page 437、
`FF_FS_NORTC=1`、`FF_USE_MKFS=0`。

执行：

```sh
make build
make smoke
```

最终：

```text
PASS: 6 checks | build 0721c6135aab9f59
PASS: 18 E02 checks | build 0721c6135aab9f59
PASS: 12 E03 checks | build 0721c6135aab9f59
PASS: 13 E04 checks | build 0721c6135aab9f59
PASS: 8 E05 checks | build 0721c6135aab9f59
PASS: 4 E07 checks | build 0721c6135aab9f59
PASS: 1 E07-full check | build 0721c6135aab9f59
```

构建 ID：`0721c6135aab9f59`；源码摘要
`0721c6135aab9f59bc73ebe9d34c0d6e2f05f573a09f26cced2167e61c7452e5`。

| 产物 | 字节 | SHA-256 |
|---|---|---|
| `kernel.elf` | 600792 | `44c4f4b24c8c01bff86d9792d73fa93605559afdff62962818f66f77db9fb75d` |
| `kernel.bin` | 196628 | `ac48b5822de8c8483b0493899830fd765520c5c115b632427db52bf40bc51e75` |
| `xos.img` | 1474560 | `648d5715a4e764edeffea08efb93e3688c13f40932db62266e0ade03a65193e8` |
| `real_mode.img` | 1474560 | `40c6180ffc534ae0e2ddd89b8053f81c2059e363ce09be7750e551a494df6b0f` |
| `user_files.image.elf` | 28416 | `9b1384a6f72bbd5789db89a859123f7adbb7bf10c6944cec9281d56c76e342b2` |
| `user_supervisor.image.elf` | 30936 | `b52efb148aae0dbbf5b4af28e27caa469c5c99b3a0eb044fdd69796e5b99b01e` |

内核文件 385 扇区，内存范围 0x100000–0x142000（约 257 KiB），在 1 MiB 内核
内存上限内；工作盘 16 MiB，格式 FAT16。

## E07 验证

| 检查 | 结果与证据 |
|---|---|
| 第一次启动创建/覆盖/删除/sync | 通过；note.txt 34→41 字节，del.txt 删除，`[files] sync=ok` |
| 第二次启动正文/删除 | 通过；同一临时盘重启后 note 内容含空行/连续空格/fourth，DEL.TXT 不存在 |
| 盘上 ELF | 通过；`exec-file hello.elf` 输出 `hello from file`，exited 0 |
| 保存失败（命名空间） | 通过；4 文件命名空间满，`edit c.txt` 保存返回 `-3`，缓冲区与旧 a.txt 保留 |
| 保存失败（物理满盘） | 通过；宿主填充 FAT16 临时盘无空闲簇，编辑旧 note 保存返回负错误，旧内容保留 |
| 旧回归 | 通过；E01–E05 57 项全绿，合计 62 |

证据：`build/persist_smoke_report.json`、`build/persist_smoke_serial.log`、
`build/persist_boot1_serial.log`、`build/persist_boot2_serial.log`、
`build/file_smoke_report.json`、`build/full_disk_smoke_report.json`、`build/manifest.json`、
`build/persist_boot1_screen.png`、`build/persist_boot2_screen.png`（实际 VGA，已查看）。

## 实施中发现与修正

- `disk_read`/`read` 响应先 `reply()` 清零再 `f_read` 会把数据抹掉；改为先
  reply 再读。
- 文件服务的 `write` 未限制单文件 24 KiB，FatFs 会扩展到媒体容量；已按
  `max_file_bytes` 截断返回实际字节。
- `file_exists(name, info)` 误读局部 FILINFO；已改为使用调用者指针。
- 提交失败时若备份恢复也失败，原实现会删 journal/backup；已改为保留恢复信息
  并标记 recovery_failed。
- 旧 E05 `hello.elf` 每次启动覆盖；已改为只在不存在时注入。
- 工作盘缺失时早期会尝试挂载失败；现明确报错，不格式化/不退回 RAM。

## 未运行与限制

- 突然掉电/坏扇区/只读盘未验证；物理满盘已用宿主填充的临时 FAT16 盘
  验证保存失败（无空闲簇），不是真实坏介质/掉电注入。
- 没有目录/LFN/时间戳/ACL、fsck、分区表、ACPI 关机；工作盘由宿主格式化，
  XOS 内没有 mkfs。
- 单客户端 supervisor；无多客户端并发、服务重启、崩溃恢复证明。
- `sync` 成功只表示本实现路径的 f_sync + FLUSH 完成，不是任意硬件掉电的原子性。
- 未运行真机/UEFI/SMP/长期压力；任务槽固定 8，运行 files 后无空槽。
- O01–O22 不整体标通过；O15 只有正常同步重启的局部证据，O16 只覆盖命名/容量/
  缺失/删除/满盘保存失败的部分行为，未覆盖目录或只读盘。

## 下一步

按用户顺序进入 **E06**：审计 GCC/G++ Seed 实际配置、构建/运行依赖与 SDK 使用，
选择 libc/兼容层；不把 E05 窄 SDK 当完整 libc。E08 才移植原生 GCC/G++。
UEFI 仍是独立可选路径，不阻塞 E06。
