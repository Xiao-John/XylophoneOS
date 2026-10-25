# 0040：ISO 安装介质 A3/A4（dash 与清单）

2026-10-25。A2 完成后继续 A3/A4：dash 从 ISO 安装到工作盘，并为安装 ISO
生成文件清单/哈希。目标是把 ISO 作为唯一安装介质，而不是把 dash 塞进内核。

## A3：dash 从 ISO 安装

- loader 在 KERNEL.BIN 之后读取可选的 `DASH.ELF`，放到 `0x300000`，在
  `0x2FFFF8` 写长度；boot_info 的 `reserved` 字段传 payload 头地址。
- kernel 在 `memory_init` 前把 payload 复制到静态 `boot_payload[1 MiB]`；
  `boot_payload_size` 供新 syscall `sys_boot_payload`（38）使用。
- syscall 仅允许 supervisor，支持查询长度和分块复制。
- `file_ui::install_boot_dash()` 在 `/usr/bin/dash` 不存在时创建
  `/usr`、`/usr/bin` 并写入 payload；已有文件不覆盖。
- 内核 BSS 增加 1 MiB，链接窗口从 1 MiB 提到 3 MiB，页表仍映射前 4 MiB。

## A4：ISO 清单

- 新增 `scripts/build_install_iso.py`：把 `KERNEL.BIN`、`DASH.ELF` 和
  `MANIFEST.TXT` 放进 ISO，并写 `build/install_manifest.json`（format、版本、
  build id、kernel/dash SHA256）。
- `make install-iso` 构建该 ISO；`make run` 默认用它，`make run_file` 保留
  无 dash 的 file-backed ISO，`make run_iso` 保留嵌入 kernel 的旧 ISO。

## 证据

- build `26eb667dd8318997`，kernel 344108 字节。
- `build/xos-install-dash.iso` SHA256
  `c29db082152913cf53829b8ea2e8598d60be5c9771dedf0a6001651d782c5720`。
- `tests/iso_dash_install.py` 4/4：dash 从 ISO 安装、`type dash`、
  `dash -i` + `echo`、ISO 内 KERNEL/DASH/MANIFEST 哈希匹配。
  报告 `build/iso_dash_install_report.json`。
- A2 回归 `tests/iso_file_kernel_smoke.py` 2/2，报告
  `build/iso_file_kernel_report.json`。

## 限制

- 安装器是启动时自动安装 dash，不是交互式分区/安装程序；不处理已有
  `/usr/bin/dash`（保留现值）。
- payload 上限 1 MiB；kernel 仍受 512 KiB 构建上限和 4 MiB 页表映射限制。
- ISO 清单是 `MANIFEST.TXT` 纯文本 + 宿主 JSON，未做签名。
- 现有 `xos.img` 软盘路径保留为兼容。

## 下一步

后续可做交互安装器、签名、完整文件清单和更大 kernel 的容量 gate；不属于
本次 A2–A4。
