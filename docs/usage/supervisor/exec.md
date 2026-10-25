# `exec <image> [args]`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `xsh>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

在用户态校验 ELF64，构建私有地址空间，传入 argv/标准句柄，提交后阻塞等待。
例如exec demo hello验证BSS/data、argv、句柄，显示退出状态42。exec slow返回-7，
exec fault显示故障；trace on时额外显示PID与kind/code/vector等详细结果。
exec echo从stdin读一行；exec spin可单独按Escape终止，显示取消状态。
未知标签、损坏/不支持的 ELF、资源不足返回真实错误，不运行半成品。
无引号语法；argv含程序名最多64项，每项最多255字节，总启动数据仍有界。
这里的exec是Xsh启动模块命令，不是POSIX替换进程。工作盘程序可直接输入名字、
路径或使用exec-file；原生GCC/G++的现有使用范围见E08文档。

[返回索引](../index.md)

