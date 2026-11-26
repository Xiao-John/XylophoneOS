# bbf38ffb · 新安装、Pumpkin 与 ClarkE 整合后的常规客体回归

从独立检出的 `bbf38ffb` 重建普通镜像 `e8b6babe05cb7a3e`，使用锁定的 GCC、
binutils、NASM、lwIP 归档和 QEMU 11.1.2。`make -o build smoke` 通过 79 项常规
客体检查和 10 项许可材料核对，未登记开放许可项。ABI 对照通过。
[源码、镜像、SDK 和运行回执](../reports/next_stage_bbf38ffb_20261126/manifest.json)

普通配置覆盖启动、内核、任务、进程、文件、持久状态、满盘、libc、存储和运行时。
glibc 安装与存量应用、冻结 newlib 回退、Pumpkin 桌面撤销、ClarkE FAT 字体流
沿用各自配置的独立源码与客体回执。
[安装](843260b2_glibc_stock_installer.md) ·
[应用](cc71c241_glibc_stock_apps.md) ·
[回退](4ffa226d_glibc_stock_fork_frozen_rollback.md) ·
[会话](7d205c98_pumpkin_verified_desktop_snapshot.md) ·
[字体](e55d60c9_clarke_skia_file_stream.md)
