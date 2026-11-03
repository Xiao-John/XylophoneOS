# 0134：单应用终端通道基础

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。supervisor 控制客户端可创建服务与一个直接受控子进程之间的两条通道，
发送 attach 并在失败时清理；detach 会关闭并清理。服务端通过 `channel_get` 核对
内核认证的控制者、对端、方向与 handle，增加一个有界应用接收线程和 mailbox。
应用只可读、写或取消；应用会话存在期间 supervisor 的直接设备读写被拒绝。
应用关闭、退出或应答槽满时关闭会话、唤醒等待者并 join 接收线程；控制端仍可
detach。结果未知、并发与单个未决应答的边界见
[终端控制契约](../contracts/terminal_control.md)。没有修改内核 ABI。

宿主服务模拟验证正确认证通道通过、不同控制者/对端/方向被拒绝，并重跑已有输入、
写等待测试；控制客户端模拟验证 attach/detach 和句柄清理。执行命令分别为：
`c++ -std=c++20 -Wall -Wextra -Werror -pthread -I src/shared/include -I src/user/include
tests/fixtures/ncursesw/terminal_service_host.cpp -o ${XOS_SCRATCH}/xos_terminal_service_host &&
${XOS_SCRATCH}/xos_terminal_service_host`，以及 0125 所记的控制客户端宿主编译运行命令。
`python3 scripts/build.py --terminal-supervisor-probe --output-dir
build/w1_terminal_app_session_v4_20261030` 通过，build ID `6a216eefb8f94595`，
terminal ELF SHA-256 `8a997ff0297a8d3b29de4f5ee7ce8a7462c76f08e69f6d1a5c21309b906b710a`；
构建早于本文档更新。`git diff --check` 通过。

应用尚不能通过 libc/stdin/stdout 使用此通道，启动接线、终端模式、fork/exec、
前台策略和恢复均未完成。宿主模拟没有运行服务的应用线程或 XOS 内核；四线程预算、
通道关闭竞争、恶意客户端、权限与真实目标行为未客体验证。不能称 W1/W2 完成。
下一步实现应用侧通道发现与 stdio/termios 接入，以及 supervisor 在子进程可运行前
完成授权并在退出时回收；全部相关改动提交后执行独立客体验收。
