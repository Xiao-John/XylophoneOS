# 0128：终端读取的控制中断

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。服务增加独立控制接收线程与一个有界 mailbox，主线程在等待输入时也能
观察到新请求或控制端退出；新请求中断当前读取并按请求顺序返回应答。控制失败唤醒
读取，正常停止时关闭控制通道、唤醒 mailbox 等待者，并 join 控制与 IRQ 线程。
客户端新增至多两个未决请求的 submit/receive，保持有序序号与传输失败后会话失效；
细节和边界见 [内部控制契约](../contracts/terminal_control.md)。

`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/services/terminal_control.cpp tests/fixtures/ncursesw/terminal_control_host.cpp
-o ${XOS_SCRATCH}/xos_terminal_control_host && ${XOS_SCRATCH}/xos_terminal_control_host` 通过。宿主模拟
覆盖两个未决请求、顺序应答和额度，未运行服务线程或设备。一次中间运行发现失效会话
被误报 busy，已修正并重跑通过。
`python3 scripts/build.py --output-dir build/w1_terminal_cancel_v2_20261030` 通过，
build ID `2afeaf397abd8ce5`，terminal ELF SHA-256
`340730d404d534aac98aa50d178a2f9b982a018f949d40cc6dc181a840ccc1bd`。
构建早于本记录文档更新，`git diff --check` 通过。

尚未客体验证多线程唤醒、请求/输入/超时竞态、对端退出、错误处理、内存和线程预算。
此工作不等于应用会话、设备恢复、W1 或 W2。下一步创建专用客体探针并完成应用端
前台所有权与 stdio 接入；所有相关修改提交后再做客体验收。
