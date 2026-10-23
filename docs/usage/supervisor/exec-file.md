# `exec-file <file> [args]`

- 控制台：用户态 supervisor
- 语法：`exec-file <file> [args]`
- 实现：`src/user/programs/supervisor.cpp`、`src/user/loader/load.cpp`

先从 FAT16 工作盘读取完整文件到有界缓冲，再做 ELF 检查和装载：

1. `stat`/`open` 取得大小与版本，并保持打开实例直到读取完成；
2. 分块读入缓冲，短读/版本变化视为错误；
3. 关闭文件后调用 `spawn_buffer`，ELF 检查、段映射、启动都使用同一份快照。

因此不会出现“校验时读到版本 A、执行时读版本 B”。文件服务在打开期间拒绝
替换；读取完成后才关闭。文件来自 `work_disk.img`，不是只读启动模块。

成功输出包含 `[loader] started pid=... file=...` 和 `kind=exited ...`；
hello.elf 返回 `hello from file` 与退出码 0。文件不存在、超过 24 KiB、ELF
不合法、资源不足都返回真实错误，不启动半成品。

限制：只装载本 SDK 的静态 ELF；不是动态链接或 Linux 二进制兼容。
