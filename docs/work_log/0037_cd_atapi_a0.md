# 0037：ISO 容量路线 A0（ATAPI PVD 探针）

2026-10-25。用户要求先不上 UEFI，突破 ISO 容量，并落文档后做 A0。本组只做独立
探针，证明 XOS 启动代码可通过 ATAPI PIO 读 ISO 的 PVD；没有改现有 `xos.iso`、
boot sector、loader 或 kernel 路径。

## 实现

- `docs/iso_install_plan.md`：记录 no-emulation 的真实限制（640 KiB 真实模式
  内存，不是 1.44 MiB 软盘）、A/B/C 方案与 A0–A4 拆分。
- `tests/fixtures/cd_probe/boot.asm`：El Torito boot sector，跳到已装入的 stage。
- `tests/fixtures/cd_probe/stage.asm`：ATAPI PIO：
  - 轮询 secondary IDE（0x170/0x376）；
  - PACKET + READ(10) 读 LBA 16；
  - 缓冲区放 0x2000（避开 0x8000 的 stage 代码）；
  - 输出 PVD 的 `CD001`。
- `tests/cd_atapi_probe.py`：临时组装 boot/stage，用 `scripts/make_iso.py` 生成
  独立 probe ISO，QEMU `-cdrom` 启动并检查串口。

## 证据

- QEMU 串口：
  `CDTEST start` → `CDTEST ok: CD001`。
- 报告 `build/cd_atapi_report.json`：`passed=true`，probe ISO SHA256
  `c5db4641aa1caeeb4d2ceebae3edaff48a90fc7b2539ce4f7ef4f73f16c334d9`。
- 失败路径保留：未找到设备/超时会打印 `CDTEST fail`，不静默继续。

## 发现与限制

- no-emulation CD 上 SeaBIOS 的 `INT 13h AH=42h` 返回 `ah=01`，不能靠 BIOS 读
  ISO；A0 使用 ATAPI PIO，符合后续 loader 方案。
- 探针只读 PVD；未做 ISO9660 目录、文件查找、分块装载到 1 MiB 以上。
- 未在真实硬件/其他固件验证；A0 只覆盖当前 QEMU/SeaBIOS 基线。
- 缓冲区必须避开 stage 代码地址；这次踩到 0x8000 覆盖，已改为 0x2000。

## 下一步

A1：最小 ISO9660 根目录查找，读出 `KERNEL.BIN`/`DASH.ELF`；A2 再解决
内核分块装载到 1 MiB 以上。现有 ISO 启动路径和 `make run` 不变。
