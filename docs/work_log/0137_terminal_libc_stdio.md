# 0137：单线程 libc 初始终端描述符

2026-10-30。显式 opt-in 的 startup2 终端应用在 libc 启动时连接已认证通道，建立
一个共享的终端对象供 fd 0/1/2 使用；复制描述符共享对象，最后引用关闭通道。
read/write 通过终端客户端传递原始字节、真实短结果及错误；isatty 和 fstat 报告
字符终端。当前不提供 termios、非阻塞设置、可恢复前台状态或完整终端权限语义。
带终端对象的 fork 和 exec 显式返回 ENOTSUP；多线程 libc 拒绝终端启动扩展，以免
把未实现的继承或并发当成成功。现有普通文件/管道路径不作为终端处理。

专用应用探针改用 libc read/write、isatty、dup/close，并安排 fork/exec 拒绝断言；
它尚未在客体运行。`python3 scripts/build.py --terminal-supervisor-probe --output-dir
build/w1_libc_terminal_v2_20261030` 通过，build ID `dd43cbe49029d626`；应用 ELF
SHA-256 `83970ee9722926c03a01fa09827b033bfddd39b5a8d563b6c29267bd535d8b9c`。
目标 `readelf` 确认应用同时保留只读 `.xos.exec` 和 `.xos.tty` 标记。线程配置下的
`newlib_syscalls.cpp` 已单独交叉编译；线程 SDK、UTF-8 SDK 构建器和 UTF-8 链接探针
的源码列表补入 terminal 客户端，未重新构建或验收那些 profile。构建早于文档更新。

下一步完成 supervisor 实际前台授权和回收、终端模式/超时、正确的 fork/exec 与
故障恢复，再完成 ncursesw 和提交后客体验收。现有目标构建和宿主客户端模拟不能
证明 libc 或硬件运行通过，也不能宣布 W1/W2 完成。
