# 1edc4a56 · CPython glibc 候选构建入口

现有 `scripts/build_cpython.py` 通过显式 `--glibc-profile` 选择静态
glibc 路径。它验证完整 SDK、源签名证据、profile 原始字节和交叉工具，
使用绑定的 CRT、头文件与静态库。可移植 SDK 的根目录包含 `sysroot/`
与核验材料。匹配的宿主 CPython 3.14.9 和原生 XOS 目标按照
[构建命令](../plans/cpython.md#glibc-静态候选构建)使用。

configure 保留真实 pthread 和原生时钟，动态模块加载选择
`dynload_stub.o`。构建用两个作业编译、链接并检查 x86-64 ET_EXEC 和
静态 TLS。构建回执记录准确 ELF 摘要、源码、profile、工具和配置。
动态扩展、Pillow、zlib、SQLite、压缩依赖、全量标准库和交互 REPL
依照现有端口分开验收。误用 newlib SDK、错配的 glibc profile、旧 zlib
扩展参数各被明确拒绝，并且未生成候选输出。

正常系统和正式命令生成的解释器通过 QEMU 11.1.3。启动读取固定源码的
124 份库文件，验证 CPython 3.14.9、进程 CPU 时钟和分辨率、单调时钟和
休眠、真实线程以及线程 CPU 时钟。进程退出 0。前后均为 129795 个空闲页、
2 个任务、0 个完成记录。[客体门禁](../../tests/cpython_glibc_guest.py)

| 输入与回执 | SHA-256 |
| --- | --- |
| glibc SDK manifest | `1a433be76f4a6193de70453f595f06298449f46ecdd4604c4a8c4e9d134028e8` |
| 候选 profile 文件 | `d9ab3cd6ed787e9a2580e88a29df6afbd47295ab40f7d52f887c5f5f6a6fa9fa` |
| 正式构建的解释器 ELF | `9b24ddb74b89be345ce0c23cafd699ee45b21c7d0965decf91edcb9c27bfe192` |
| 构建回执 | `9e01c3f5cbc257f4d8e86e526676f83fe32a803bfd068c333feef9eb106cd066` |
| 正常系统 `011216baa6e40599` ISO | `74989e97e583beab50edbae799fd46c41ba360adb7a025a0efedc88424a95eda` |
| 客体运行回执 | `0565e7fa0b51d3ada6506e9b356737ff14933e9716447a143be9c8b3b9582711` |

链接日志仍报告当前 `raise`、`clock_settime`、`execve`、`times` 和
`fchmodat` 的不可用实现。运行回执的覆盖范围为上述解释器核心切片。

## newlib 对照

旧构建驱动保持原始字节，摘要为
`9265aa9457e3c43af3b54fd302a881da48f00c9479620b7be50340d5d36713c2`。
现有入口在普通调用时执行该驱动，旧 CLI 帮助输出逐字节一致。独立候选目录
保留原有 newlib 指纹、缓存查找和产物路径。

对同一输入直接调用旧驱动，得到相同的输入集合、缓存指纹和编译诊断。
普通单线程 SDK 在 CPython
线程头文件处返回 `Require native threads`。pr147 线程 SDK 在
`getpath.c` 处缺少可见的 `lstat` 声明。本次对照的这两个输入没有产生
新的 legacy ELF。

## 评审修订复验

源码树 `a0b58ecd2b18a6a32f73545c18382f6e08c2ed1e` 从主线 `49e5d74b`
组合公开入口的修订。运行命令省略 `--build-python`，在 Linux arm64 重建宿主
解释器。调用方环境设置失效 `CC`、`CFLAGS`、`LDFLAGS`、`CONFIG_SITE` 和
`MAKEFLAGS`。五个变量均在工具发现和宿主构建前清理，宿主 configure 与
make 以及目标静态 ELF 全部构建通过。链接以 profile 决定是否加入终端归档。
旧构建驱动字节和默认入口帮助输出均通过 `cmp`。

来宾门禁将已核验的 ISO、ELF、上游归档和夹具保存到本次私有暂存目录，
构建回执、系统 manifest 和 profile 的摘要均来自校验所用的原始字节。
QEMU 11.1.3 的常规系统 `19a6d93ff83db048` 通过原先三项检查。工作线程的
CPU 时钟必须在限量计算中实际增加，线程完成仍受超时约束。进程退出 0，
资源前后为 `129795 / 2 / 0`。错误 SDK、错误 profile 和旧 zlib 参数三项
拒绝也复验通过。

| 修订工件 | SHA-256 |
| --- | --- |
| 宿主 configure 日志 | `b65c4f1ba46162772d0d365be059b5c55b80b6340fc0236a0b9e9889e7672834` |
| 解释器 ELF | `bbad2bfcc9b3ea18e958718c9a1fe8151b5e8c695bac3808c68df4f1ff78e7ad` |
| 构建回执 | `7eb18da7678da8dc9959d3f70614422d0f71c5fb695af2984b1927fabef1ff03` |
| 普通系统 ISO | `91ef7e88bfa233cc4675f66703628a7bf5fd6972bcee23c884834711167d2b79` |
| 客体运行回执 | `7a7f328f108d3aeefac9fb99d83bdb3853ba301bd0a2a15e6e839e0d9f627857` |
