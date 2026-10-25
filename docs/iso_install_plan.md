# ISO 安装介质计划：从 no-emulation 启动到可安装镜像

2026-10-25，0037。用户要求先不上 UEFI，突破当前 ISO 的容量限制，并明确最终
ISO 应能作为唯一安装介质，dash 预装在 ISO 中是合理目标。本页记录方案和 A0
探针；不把探针结果当成完整 ISO 文件系统或安装器已完成。

## 现状与真实瓶颈

- `make run` 已改为 El Torito **no-emulation** ISO；boot sector、loader、kernel
  一起装进 boot image，约 349 KiB。
- 限制不再是 1.44 MiB 软盘，而是 BIOS 把 boot image 装进 **640 KiB 真实模式
  内存**；kernel 已 344 KiB，dash 约 991 KiB 无法放入。
- 在 no-emulation CD 上直接使用 BIOS `INT 13h AH=42h` 读 LBA 实测失败
  （SeaBIOS 返回 `ah=01`），所以不能靠 BIOS 读 ISO。
- ISO 镜像可以做大，但当前没有客体侧的 CD 读取路径，也没有 ISO9660 文件访问。

## 方案比较

| 方案 | 做法 | 容量 | 代价 | 结论 |
|---|---|---|---|---|
| A. loader 读 ISO | 自写 ATAPI PIO + 最小 ISO9660，读 kernel/dash | ISO 大小 | 新启动子系统，工作量中 | **推荐** |
| B. El Torito 硬盘仿真 + RAM disk | ISO 放 FAT 镜像，BIOS 仿真，loader 读入内存 | RAM | 需要 ramdisk 块后端 | 过渡，不先做 |
| C. 2.88 MiB 软盘仿真 | 只把 1.44 翻倍 | 2.88 MiB | 仍非安装介质 | 不采用 |

## A 阶段拆分

- **A0（已通过）**：独立探针用 ATAPI PIO 读 CD 的 PVD，证明客体侧可以不依赖
  BIOS 读 ISO。没有改现有 `xos.iso` 启动路径。
- **A1（已通过）**：最小 ISO9660 单层目录查找，读出 `KERNEL.BIN`、`DASH.ELF`；
  支持多扇区文件（测试用 2100/5000 字节）。
- **A2（已通过）**：loader 从 ISO 读 `KERNEL.BIN` 并直接装入 1 MiB；
  `xos-install.iso` 的 boot image 不含 kernel，`make run` 默认使用它。
  `tests/iso_file_kernel_smoke.py` 通过。
- A3：dash 等安装负载从 ISO 交给 files 服务/安装流程，ISO 预装。
- A4：ISO 构建器写文件清单、哈希和安装元数据；ISO 成为正式安装介质。

## A0 验收（已通过）

- 独立 `tests/fixtures/cd_probe/` 启动镜像，经 QEMU `-cdrom` 启动；
- ATAPI PIO 读取 ISO 的 PVD（LBA 16），串口打印 `CD001`；
- 失败时打印 status/error，不静默继续；
- 不修改 `xos.iso`、boot sector、loader 或 kernel 的现有路径。

证据：`tests/cd_atapi_probe.py` 构建临时 ISO 并启动，串口输出
`CDTEST ok: CD001`；报告 `build/cd_atapi_report.json`，ISO SHA256
`c5db4641…`。次要发现：no-emulation CD 上 BIOS `INT 13h AH=42h` 返回 `ah=01`，
所以 A0 走 ATAPI PIO，而不是 BIOS 读盘。

## A1 证据（已通过）

- `tests/fixtures/cd_probe/iso_stage.asm`：ATAPI 逐扇区读 PVD、根目录记录，
  匹配 `KERNEL.BIN;1` / `DASH.ELF;1`，按 extent/size 读取并校验首尾字节。
- `make_iso.py --file NAME=PATH`：在根目录写入文件记录和数据区。
- `tests/cd_iso9660_probe.py`：镜像含 2100 字节 KERNEL 和 5000 字节 DASH，
  串口输出 `A1 ok KERNEL=2100 DASH=5000`；报告 `build/cd_iso9660_report.json`。
- 限制：只支持单层根目录、`;1` 名称、单 extent、<64 KiB；未做路径表遍历、
  长名、Joliet、多 extent、文件 >64 KiB，也未把 kernel 装到 1 MiB 以上。

## 风险

- ATAPI 端口/主从盘假设：QEMU `-cdrom` 的 IDE 位置需实测，探针应明确失败。
- PIO 轮询、DRQ/ERR、2048 字节块边界和超时；不能忙等永不返回。
- 真实硬件/不同 BIOS 的 CD 行为未验证；A0 只证明当前 QEMU 基线。
- ISO9660 目录、长文件名、大小端和多 extent 在 A1 才处理。
- 分块装载到 1 MiB 以上需要 unreal mode 或保护模式复制，A2 单独验收。

## 下一步

先完成 A0 探针；通过后再决定 A1 的目录格式和 dash 在 ISO 中的路径。
