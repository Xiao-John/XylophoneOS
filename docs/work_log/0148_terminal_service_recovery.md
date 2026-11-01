# 终端服务受限重连

桥接读写出现错误后进入 unavailable；显式 recover 要求没有应用会话，以非阻塞方式
回收旧服务完成结果，确认 COM1 状态后仅在隔离时调用 sys82 recover，重新启动终端。
服务仍在运行、通道结果未知或恢复失败时不会假装旧控制台可用，也不会重放旧 I/O。
正常 stop 的 wait 若失败保留会话信息以便后续检查；不保证断线期间输入输出。

`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/services/shell_terminal.cpp tests/fixtures/ncursesw/shell_terminal_host.cpp
-o /tmp/xos_shell_terminal_recovery_host` 及正常/failed 两种运行通过；覆盖完成记录未
就绪时拒绝恢复与隔离后的重新授权模拟。专用镜像通过构建，build ID
`b51e8833ca50017c`。客体探针新增终止终端服务、检测写失败、恢复和重新运行应用；
按要求提交后再执行，尚无客体结果。旧请求状态、前台应用故障、真实 Xsh 救援和
完整 W1/W2 仍未验证。
