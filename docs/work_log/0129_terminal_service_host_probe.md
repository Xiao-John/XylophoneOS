# 0129：终端服务读取宿主探针

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。检查 supervisor 启动路径时确认：现有 Xsh 仍以旧 console 的 read/write
交互；COM1 PIO 交接成功后旧内核串口访问被关闭。因此当前不能直接在常规启动路径
调用终端服务并宣称 shell 可用，必须先实现 supervisor 和应用的终端 I/O 接管及恢复。

新增 `tests/fixtures/ncursesw/terminal_service_host.cpp`，直接编译当前服务源码，
以宿主线程模拟 wait-word 和 UART 队列，检查有限时间无数据返回 timeout、等待中
输入唤醒并返回原字节，以及等待中控制请求到达返回 interrupted。
执行 `c++ -std=c++20 -Wall -Wextra -Werror -pthread -I src/shared/include
-I src/user/include tests/fixtures/ncursesw/terminal_service_host.cpp
-o ${XOS_SCRATCH}/xos_terminal_service_host && ${XOS_SCRATCH}/xos_terminal_service_host` 通过，
`git diff --check` 通过。模拟不包含 XOS 调度器、IRQ、真实通道、超时精度、完整
控制线程或用户态服务启动，不能作为客体验收；测试本身没有修改系统运行路径。

下一步实现可通过专用测试入口启动和观察的交接，并完成 shell 与应用输入输出和故障
恢复；按用户要求，所有相关更改提交后才在独立镜像与测试盘执行客体验收。W1/W2、
ncursesw、前台所有权和可靠救援均未完成。
