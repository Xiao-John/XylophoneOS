# `exec <image> [args]`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `sup>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

在用户态校验 ELF64，构建私有地址空间，传入 argv/标准句柄，提交后阻塞等待。
例如 exec demo hello 会验证 BSS/data、argv、句柄，并返回 kind=exited code=42。
exec slow 返回 -7；exec fault 返回 kind=faulted；fault readonly/nx/fpu 检查对应限制。
exec echo 从 stdin 读一行；exec spin 可单独按 Escape 终止，得到 kind=killed code=-27。
未知标签、损坏/不支持的 ELF、资源不足返回真实错误，不运行半成品。
无引号语法；argv 含程序名最多 8 项，每项 63 字节。程序来源是只读启动模块，
不是工作盘文件；从工作盘装载用 `exec-file`。没有原生编译。

[返回索引](../index.md)

