# 0039：ISO 容量 A2（已通过）

2026-10-25。A1 通过后继续 A2：让 loader 从 ISO 读 `KERNEL.BIN` 并直接装入
1 MiB，解除 boot image 对 kernel 的容量绑定。A2 已通过；A3/A4 未开始。

## 已实现

- loader 在 32-bit protected mode 下用 ATAPI PIO 读 PVD 和根目录，按
  `KERNEL.BIN;1` 的 extent/size 逐扇区读取。
- 文件先读到低内存 `0x10000`，再 `rep movsb` 到 `0x100000`；kernel 344108
  字节已能完整读出（QEMU ATAPI trace 读到最后一个 LBA）。
- 调试串口可见：`X12R<root_lba>34<file_lba><size>C`，说明根目录、文件
  查找、读取和复制都执行到了。

补充定位：把一个 4 KiB 的 64-bit stub 作为 `KERNEL.BIN` 放进 ISO，loader
能复制到 1 MiB、切换长模式并跳到 stub，串口输出 `K!`；说明 ATAPI/ISO/复制/
页表/长模式路径本身可用。真实 `build/kernel.bin` 在同一路径下复制完成却不
进入内核，问题集中在真实 kernel 的入口/启动信息/内容绑定，而不是 ATAPI 或
长模式。

## 修复与通过

最初 32-bit loader 在 `rep insw` 之后又 `add edi, 2048`，实际每个扇区之间
多留了 2048 字节空洞；stub 只有 4 KiB 所以看起来正常，真实 kernel 校验和
不符。删除多余 `add edi,2048` 后，`0x100000` 的 344108 字节校验和与
`build/kernel.bin` 一致，内核进入：

```text
[boot] event=kernel_enter arch=x86_64 build=8a17a3127dc2ae32
[boot] result=ready stage=E04
```

loader 直接把 ISO 文件读入 `0x100000`，不再经过低内存 staging，因此 boot
image 只有 boot sector + loader，kernel 不再占 640 KiB 空间。

## 集成与证据

- 新增 `build/xos-install.iso`：boot image 只含 boot sector + loader，
  `KERNEL.BIN` 作为 ISO 文件；`make run` 默认使用它，`make run_iso` 保留
  嵌入 kernel 的 `xos.iso`。
- build `8a17a3127dc2ae32`，`xos-install.iso` SHA256
  `1c6107643af8c91ac176adb40affa98be8d4690c2c6c35c13ea1baabaa92d341`。
- `tests/iso_file_kernel_smoke.py` 2/2 通过：从 ISO 文件加载 kernel、进入
  `xsh>`、文件服务可用；报告 `build/iso_file_kernel_report.json`。

## 现有边界
- loader 直接写 1 MiB，页表当前只映射前 4 MiB；kernel 文件大小仍受
  `config/x86_64_bios.json` 的 512 KiB 构建上限约束，尚未用 >640 KiB 的真实
  kernel 做 gate。
- dash 尚未从 ISO 安装（A3）；ISO 构建元数据/安装器（A4）未做。
- `xos.iso` 嵌入路径保留为 fallback。
