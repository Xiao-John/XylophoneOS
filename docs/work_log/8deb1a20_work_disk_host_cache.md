# 8deb1a20 · FAT 工具的宿主缓存

从 Linux 容器构建 glibc 安装候选，再在 macOS 复验同一工作目录时，旧 FAT
工具缓存命中 Linux arm64 ELF。源码和二进制摘要均一致，macOS 执行仍以
`Exec format error` 失败。文件系统操作尚未进入客体。

缓存现在按宿主系统和架构分目录，保留源码和实际二进制校验。两个同宿主的
构建者使用同一把锁，编译成功才写入工具及摘要。发行打包及已有验收继续
只使用已准备的本机工具，可以先执行 `PYTHONPATH=scripts python3 -c
'from work_disk import host_tool; print(host_tool())'` 完成准备。

在同一构建目录，Linux 容器和 macOS 各用两个并发调用准备工具。生成独立
Linux aarch64 ELF 和 macOS arm64 Mach-O。Linux 写入一次 FAT 文件，两套
工具分别读回同一字节。QEMU 11.1.2 的 XOS `8530ecb637372dac` 也读到此文件，
资源回到 `129696 / 3 / 1`。先前的历史缓存和破损摘要在宿主回归中覆盖。
