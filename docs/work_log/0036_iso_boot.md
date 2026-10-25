# 0036：El Torito ISO 启动路径

2026-10-25。用户要求先让 XOS 用上 ISO，作为软盘退役的第一步。本组保留 BIOS
路径，新增 no-emulation ISO：boot sector、loader、kernel 一起装进 El Torito
boot image，BIOS 一次装入后在真实模式内存里完成启动，不再读软盘。

## 实现

- `src/boot/x86/boot_sector_iso.asm`：不读磁盘，直接跳到已装入的 loader。
- `src/boot/x86/kernel_loader_iso.asm`：跳过磁盘读取，从 boot image 内固定偏移
  `0x9000` 复制 kernel；E820、A20、长模式、页表逻辑不变。
- `scripts/make_iso.py`：生成最小 ISO9660 + El Torito（no emulation，load
  segment 0，boot catalog 25，boot image RBA 26）。
- `scripts/build.py`：同时生成 `build/xos.iso`，加入 manifest artifacts。
- `scripts/run_qemu.py`：`--iso` 使用 `-cdrom`；`make run` 默认 ISO，
  `make run_floppy` 保留旧软盘路径，`run_vga` 也走 ISO。
- `tests/boot_smoke.py` 的 `Guest` 增加 `iso=`；新增
  `tests/iso_boot_smoke.py`。
- `scripts/package_release.py` 在有 ISO 时把它复制进发行镜像目录。

## 证据

- build `2b5f6ecc87ed6d8f`，kernel 344108 字节；`build/xos.iso`
  SHA256 `209367f7df9794aa2c729f05eeef71c2a15a6557189d6ff6046811e3dd95da21`。
- QEMU `-cdrom build/xos.iso` 启动到 `xos64>`，`run` 进入 `xsh>`；文件服务可用。
- `build/iso_boot_report.json` 2/2 passed。
- 预装 dash 的新盘 + ISO：`type dash` → `/usr/bin/dash`，`dash -i`、`echo`、`exit`
  正常。

## 边界

- 仍受真实模式 640 KiB 装入边界；boot image 目前约 349 KiB。不是 UEFI，也不是
  完整 ISO9660 文件系统启动；ISO 只承载 boot image。
- `xos.img` 软盘路径保留，历史测试仍可用。
- 没有改 UEFI、分区、任意 CHS 或 ISO 内文件读取。
