# `images`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `xsh>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

列出只读启动模块的标签与字节数：demo、fault、spin、slow、echo、hello、
libc_hello，以及 bad_magic、bad_interp、bad_overflow 三个故障夹具。这不是文件
目录；没有宿主文件访问。`libc_hello` 是 E06 newlib 示例，`exec libc_hello`
使用 `printf`/`malloc`/string 并退出 7。
模块由宿主构建打包，解析和执行均在客体内完成。

[返回索引](../index.md)

