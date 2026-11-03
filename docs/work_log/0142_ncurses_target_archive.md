# 0142：ncurses 目标归档修正与严格 UTF-8 链接探针

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。复核发现 0139 的 make 虽退出 0，宿主 `ar/ranlib` 却把目标 ELF
归档处理成 96 字节的空索引；其中没有 ncurses 成员。0139 已更正，不再把该结果当作
有效库。`probe_ncursesw.py` 现显式使用 `x86_64-elf-ar`、`x86_64-elf-ranlib`，
并要求归档包含成员、`initscr` 和 `wget_wch`，记录归档哈希；make 退出 0 但验证失败
也会令探针失败。

以锁定 newlib 源包及代理码点补丁重新建立隔离候选，命令为
`python3 scripts/build_utf8_newlib.py --archive .cache/xos_seed/threading_sources/newlib-4.6.0.20260123.tar.gz
--output ${XOS_SCRATCH}/xos_utf8_newlib_20261030b --jobs 8`；single libc SHA-256
`72d0b3edb95065bd14ae465f4192185dc22046ce8e7d6a779a98e64a55194400`，threaded libc
SHA-256 `866f73a97e529311e7fe2fac337a269d3601b194ce491c17f5ce46817d72d112`。
`python3 scripts/build_utf8_sdk_candidate.py --newlib-prefix
${XOS_SCRATCH}/xos_utf8_newlib_20261030b/single/prefix --output ${XOS_SCRATCH}/xos_utf8_sdk_20261030b`
通过，SDK 树 SHA-256 `a49320f272ad4f15e86e4f2566ba5b05d43e63a82d92500dcf755d0c6ca7e9b8`，
标记 built_unverified；线程候选没有在本组构建成 SDK 或运行。

`python3 scripts/probe_ncursesw.py --archive .cache/xos_seed/ncurses_sources/ncurses-6.5.tar.gz
--sdk ${XOS_SCRATCH}/xos_utf8_sdk_20261030b/sdk --output ${XOS_SCRATCH}/xos_ncurses_strict_target_ar_v2_20261030
--xopen-source 700 --no-sigwinch --build` 通过，目标 `libncursesw.a` 含 162 个成员，
两个必需符号存在，SHA-256 `9b9be4270344e47f48f5314ee97481e3cd7757a7faf493e5b3b08c1c87f2c2de`。
`python3 scripts/probe_ncursesw_consumers.py --probe ${XOS_SCRATCH}/xos_ncurses_strict_target_ar_v2_20261030
--sdk ${XOS_SCRATCH}/xos_utf8_sdk_20261030b/sdk --output ${XOS_SCRATCH}/xos_ncurses_consumers_v5_20261030`
交叉链接两个独立应用：窗格、颜色、方向键和中文输入输出探针 ELF SHA-256
`26725590372fd6238b135e8964a40a1eecbc3d7e178a295aabd24d59356c539f`；未知终端、尺寸和
重复进入退出探针 ELF SHA-256 `749ac7860f6117bd5ff234e7bb62946d78c32161b1096a2a932ec85e0ba1bc31`。
两者都保留终端 opt-in 标记；ELF 各约 1.6 MiB，目标内存各约 0.75 MB，实际资源预算
尚未测量。探针构建器核对 SDK 树、源锁、配置、目标归档哈希及源码快照。

以上均为构建/链接证据，不是客体验收：terminfo 尚未用匹配 6.5 的宿主工具生成，
应用尚未运行，UTF-8 转换、终端交互、内存、故障、尺寸与许可分发仍未验证。必须
完成前台与进程生命周期，再从全部提交源码重建并运行客体测试；W1/W2、main 合并和
PR 均未完成。
