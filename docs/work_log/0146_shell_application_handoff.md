# Xsh 桥接的应用交接入口

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

单线程 supervisor 的试行终端桥接现提供准备子进程时附加应用会话、取得启动句柄、
退出或启动失败后的 detach，以及无应用时停止服务的入口。附加或 detach 的结果不确定
时桥接转为 unavailable，不能假装原控制台已恢复。调用者须在成功 prepare 后，不论
后续启动或等待结果如何，执行会话回收。停止成功也不声称旧 COM1 控制台已恢复。

ncurses 专用 supervisor 已改为使用同一桥接入口运行两个应用；真实 Xsh 仍未启用该
路径，旧应用 stdio、shell 前台策略、fork/exec 和故障救援仍待完成。
`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/services/shell_terminal.cpp tests/fixtures/ncursesw/shell_terminal_host.cpp
-o ${XOS_SCRATCH}/xos_shell_terminal_handoff_host_v2` 及正常/failed 两种运行通过，覆盖会话
附加、重复附加拒绝、回收和回收失败后不可用；这是宿主模拟。专用构建
`python3 scripts/build.py --ncurses-supervisor-probe --output-dir
build/w2_shell_handoff_20261101` 通过，build ID `951214ba9e4bf9ce`。
相关改动提交后需在干净快照重建并重跑客体；上述构建不能作为客体验收。

提交 `17c6b26` 后从干净快照重建相同 build，并以 0145 的 SDK、ncurses 和 terminfo
运行双消费者客体探针，两个检查通过。ISO SHA-256
`890dcb9bfefe2bfb240aa66e8ac556f26eea984e4a1bec43abaecb83efda0d21`，
串口 SHA-256 `66269a14832c9912e776a5e0d9d98038b6c9536cf5197d55f6e5c56e3a6ff6d5`；
回执在隔离工作区 `build/w2_shell_handoff_17c6b26/ncurses_guest_probe_report.json`。
探针证明桥接路径下两次正常附加、应用运行和回收；测试在第二个成功标记后结束，
不证明服务停止、失败回收、救援或真实 Xsh 的客体行为。
