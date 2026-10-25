# E07：独立工作盘、ATA PIO 与 FatFs

实施于 0009。目标范围是“正常保存、`sync`、停止 QEMU，再次启动后内容仍在”；
突然掉电下的事务原子性不是本组验收项。源码与证据见
`history/e01_e07.md`、`state.md`。

## 工作盘

- 默认路径：仓库根 `work_disk.img`；不属于 `build/`，构建和启动不会创建/格式化它。
- 创建：`make disk` 或 `python3 scripts/make_work_disk.py`；已存在时拒绝覆盖，
  `--force` 才显式重建并格式化。镜像 16 MiB、FAT16、512 字节扇区、8 扇区/簇。
- QEMU：只读软盘启动 + `if=ide,index=0,media=disk,cache=writeback` 工作盘。
  `make run` 找不到工作盘会失败并提示 `make disk`，不会退回 RAM。
- 测试：`file_smoke`/`persist_smoke`/`full_disk_smoke` 使用临时 FAT16 副本；
  `make smoke` 不写日常 `work_disk.img`，也不把工作盘当耗材。

## 块设备与内核边界

内核 `platform/pc/ata.cpp` 实现 primary master 的 ATA PIO 轮询：IDENTIFY 取容量、
LBA28 读写、FLUSH CACHE、每次最多 8 个 512 字节扇区、忙/DRQ 等待有界超时。
硬件端口留在 platform，通用接口只有 `read/write/sync` 和错误。

系统调用 `block_read/write/sync/info` 只允许 `files` 任务（`block_access` 标志）。
内核验证扇区范围与用户缓冲，不接受物理地址/端口；其他任务得到 denied。
内核不解析 FAT、路径或文件内容，也不需要为大文件把缓冲放在小内核栈上：块
bounce 是内核 BSS 的 4 KiB，FAT 缓冲在 files 用户空间。

## FatFs 与 files 服务

- 用户态 `files` 链接 FatFs R0.16（`src/third_party/fatfs/`），配置 8.3 短名、
  code page 437、无 LFN/RTC/TLS、禁用 mkfs；挂载失败不格式化、不退回 RAM。
- 低层 `diskio` 把 FatFs 的 512 字节扇区请求映射到受限块系统调用，单次超过 8
  扇区时循环；`CTRL_SYNC` 走块设备 FLUSH。
- 文件/打开实例语义沿用 E05：`FIL` 保存游标，两个打开不共享偏移；
  最多 8 个打开、4 个文件、单文件 24 KiB。FatFs 短名显示为大写（如
  `HELLO.ELF`、`NOTE.TXT`），查找不区分大小写；没有目录/LFN/时间戳/ACL。
- `stat` 返回大小；version 当前固定为 0，锁语义由“打开期间禁止替换/删除”保证。
- `sync`：对所有以写方式打开的文件 `f_sync`，再 `disk_ioctl(CTRL_SYNC)`；
  只有全部成功才返回 ok。supervisor `sync` 打印 `[files] sync=ok`。

## 保存提交与恢复

RAM staging 仍负责收集新内容；commit 才碰磁盘：

1. 写 `XOSTMP.TMP` 并 `f_sync`；失败则删除临时文件，旧文件不变。
2. 写 `XOSJRNL.TMP`（目标短名）并同步；这是恢复锚点。
3. 目标存在时先 `f_rename(target, XOSBAK.TMP)`；FatFs 的 rename 不能覆盖，
   所以不能直接 rename 覆盖目标。
4. `f_rename(XOSTMP.TMP, target)`；失败则尝试把备份 rename 回目标。
5. `CTRL_SYNC` 成功后删除备份和 journal；同步失败保留 journal，标记恢复失败，
   不报告保存成功。
6. 启动挂载后执行恢复：journal 存在时，目标缺失且备份存在则恢复备份；目标
   存在则删除陈旧备份；清理临时文件和 journal；恢复失败则 `files` 以 io 状态
   报告，不假装可用。

这覆盖“正常同步后重启”的保存；突然掉电时最多可能留下 journal/backup/temp，
下次挂载按上述顺序处理。没有 fsck、事务日志冗余或对任意扇区损坏的保证。

## 启动行为

- `files` 启动时 `f_mount`；失败则服务进入不可用状态，所有文件操作返回错误，
  不格式化、不切 RAM。supervisor 会显示 `[files] ... error=...`，不会假装持久。
- `hello.elf` 只在 `stat` 返回不存在时从只读启动模块复制；已存在则打印
  `[files] hello.elf present bytes=...`，不覆盖用户文件。

## 验证与边界

E07 5 项：第一次启动创建/覆盖/删除并 `sync`；第二次启动验证正文与删除结果；
执行盘上的 `hello.elf`；文件命名空间满时保存失败；物理满盘时保存失败且旧
文件/编辑缓冲保留。旧 57 项 E01–E05 回归保持通过（合计 62）。

未验证/不声称：突然掉电、坏扇区、只读工作盘、FAT 表损坏、目录/LFN、
多客户端并发、服务重启、ACPI 关机。物理满盘已用宿主填充的临时 FAT16 盘
验证保存失败；这不是对真实坏介质/掉电的保证。`sync` 成功只表示本实现路径的缓存/FLUSH
完成，不是对任意硬件掉电的原子性证明。
