# 0125：终端服务故障唤醒

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。接收线程等待 IRQ 或处理事件失败时，记录错误并关闭两条控制通道，
唤醒等待请求的服务线程和可能等待应答的 supervisor。控制客户端在传输失败或应答
格式错误后关闭并失效通道，保留 child PID 供调用方等待；请求发出后的失败不证明
操作未执行，不能自动重试。正常停止依旧由服务线程关闭 IRQ 并 join 接收线程。

`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/services/terminal_control.cpp tests/fixtures/ncursesw/terminal_control_host.cpp
-o ${XOS_SCRATCH}/xos_terminal_control_host && ${XOS_SCRATCH}/xos_terminal_control_host` 通过；该宿主模拟
覆盖授权失败清理、正常请求、应答等待失败后的会话失效，不覆盖真实内核和 IRQ。
`python3 scripts/build.py --output-dir build/w1_terminal_failure_20261030` 通过，
构建 ID `9e2aa1443e744145`，terminal ELF SHA-256
`784c8d868b1d13e4d90f8e03d0d4c996e74cfb19fb25042b420c486f2ecf6582`；
构建早于本记录文档更新。`git diff --check` 通过。

尚未在客体验证 close 与等待登记的竞争、故障唤醒、资源回收和硬件错误；本组
不提供阻塞输入、应用会话或设备恢复。下一步实现和验证应用前台会话、读取等待与
可靠恢复策略，之后才能完成 W1，再继续 W2；所有相关更改提交后方做客体验收。
