# Xsh 桥接的应用交接入口

单线程 supervisor 的试行终端桥接现提供准备子进程时附加应用会话、取得启动句柄、
退出或启动失败后的 detach，以及无应用时停止服务的入口。附加或 detach 的结果不确定
时桥接转为 unavailable，不能假装原控制台已恢复。调用者须在成功 prepare 后，不论
后续启动或等待结果如何，执行会话回收。停止成功也不声称旧 COM1 控制台已恢复。

ncurses 专用 supervisor 已改为使用同一桥接入口运行两个应用；真实 Xsh 仍未启用该
路径，旧应用 stdio、shell 前台策略、fork/exec 和故障救援仍待完成。
`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/services/shell_terminal.cpp tests/fixtures/ncursesw/shell_terminal_host.cpp
-o /tmp/xos_shell_terminal_handoff_host_v2` 及正常/failed 两种运行通过，覆盖会话
附加、重复附加拒绝、回收和回收失败后不可用；这是宿主模拟。专用构建
`python3 scripts/build.py --ncurses-supervisor-probe --output-dir
build/w2_shell_handoff_20261101` 通过，build ID `951214ba9e4bf9ce`。
相关改动提交后需在干净快照重建并重跑客体；上述构建不能作为客体验收。
