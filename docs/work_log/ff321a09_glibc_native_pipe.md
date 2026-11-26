# ff321a09 · glibc 原生匿名管道

静态 glibc 候选 SDK 的 `pipe` 和 `pipe2` 复用现有 XOS 内核管道。登记前在
进程内预检两个 FD 槽和两个打开描述槽。每个端点保留一个原生有向引用，FD
别名和进行中的 I/O 通过现有引用计数维持对象寿命。关闭最后一个写端后，
读端排空缓冲区并返回 EOF。关闭最后一个读端后，写入返回 `EPIPE`。
XOS 当前在该路径交付错误码，`SIGPIPE` 投递仍是信号运行时的独立工作。

实现支持 `O_CLOEXEC`、`O_NONBLOCK` 和 4096 字节的 `PIPE_BUF`。
阻塞写入通过原生等待完成超过缓冲区的请求。非阻塞短请求保持原子性，
较大请求在有空位时可以短写。FD 配额与内核管道配额分别返回
`EMFILE` 和 `ENFILE`。

后续可用现有 `sys_process_stdio` 配置正在构建的子进程的标准管道端点。
[文件契约](../contracts/glibc_files_v1.md#原生匿名管道)记录了 glibc 启动快照
的引用保留、方向检查与生存期边界。普通文件重定向仍需 loader 的 files 句柄
转移和接收端资格。当前资格覆盖单进程管道以及额外 CLOEXEC 端点在出站
`posix_spawn` 中的处理。

## 验证

[客体套件](../../tests/glibc_static_guest.py)使用新建的静态 C SDK 与同一源码
快照的正常系统镜像。每轮检查非阻塞原子性、部分写、别名、配额恢复、
`EPIPE` 和 EOF。线程夹具单次写入 10,037 字节，另一线程分批读取并逐段比对，
另用 `fdopen` 检查缓冲输出和 `fclose` 后的 EOF。真实子进程确认 3/4
两个 CLOEXEC 描述符均关闭，父进程随后继续通过原管道传输。

| 验证输入或结果 | 实测 |
| --- | --- |
| 正常系统 `7ffcfe1ebb2da731` | ISO `caf1041988d1991ba72f520eb5cc3e1dece5a8ec36e774d48ce523c766119521` |
| glibc 2.44 上游签名通过 | C SDK manifest `bd4697ee703bd34bd5acf72ba217252b5e4bdbd87d98192dbc000fd5c4ba8ba7` |
| C SDK 压缩包 | `e8d10a94ab925d971fa41b5a6eafdb45bc8e44b562a9f8977b7d4a9d996d8287` |
| 管道夹具 ELF | `7eca6689d587efff3f5a64f03f7a1c7e7f5e97d5362cbd357ac46821eff0aed1` |
| QEMU 11.1.3 管道套件 | 3/3 通过，报告 `0656abe126438115edd344d617d15917d959297fde6c41a1a5a8852ca8b5a105` |
| 同版进程套件 | xsh 常规、xsh 拒绝和 newlib dash 共 3/3 通过，报告 `7e6c5ac05c85b871d5cc83fcdb13726725a28eb34287a25b30fb9a27a72ab273` |
| 两套客体资源基线 | 六轮均恢复至 `[129698, 3, 1]` |
| 宿主文件回归 | 48 项检查及 15 组真实 files/FatFs 集成通过 |
