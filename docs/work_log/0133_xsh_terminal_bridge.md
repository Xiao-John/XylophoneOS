# 0133：Xsh 终端桥接入口

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。SDK 控制台 read/write 增加可选的进程内弱符号入口；普通可执行文件没有
定义时仍调用原 syscall。supervisor 链入试验桥接，默认走原路径；显式 `start` 成功
后将 SDK stdin/stdout/stderr 接到终端控制服务的读取与短写等待。Xsh 的闲置输入
仍以一个时钟 tick 的有限等待转换成原有零长度轮询语义，输出保留实际短写。
启动交接尝试失败时桥接进入 unavailable，不擅自退回可能已脱离的旧控制台。

桥接仅供单线程 supervisor 自身使用，不是应用前台会话，不改变子进程的内核 stdio，
也没有恢复重连入口；当前没有常规启动调用 `start`，因此不声称 Xsh 已切换。现有
Xsh 对负输入结果仍会继续轮询，故障后的用户可见处理需在启用之前解决。

`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/services/shell_terminal.cpp tests/fixtures/ncursesw/shell_terminal_host.cpp
-o ${XOS_SCRATCH}/xos_shell_terminal_host && ${XOS_SCRATCH}/xos_shell_terminal_host &&
${XOS_SCRATCH}/xos_shell_terminal_host failed` 通过；模拟覆盖默认旧路径、显式切换、短写、
输入超时和交接失败不回退。`python3 scripts/build.py --output-dir
build/w1_shell_bridge_v2_20261030` 通过，build ID `dde23288b5c74d9e`。
构建早于本记录的文档更新；以上均非客体验收。

下一步完成应用前台授权、继承/退出和 stdio 服务适配，再接入 Xsh 实际启动及故障
恢复；完成 W2 后从提交源码进行客体验收。旧应用、dash、终端服务及 bridge 的客体
兼容性尚未验证，不能据此宣称 W1/W2 完成。
