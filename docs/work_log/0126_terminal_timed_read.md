# 0126：终端有限截止时间读取

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。内部终端控制协议升级到 version 2，在非阻塞 read 之外增加 read_until，
使用绝对单调纳秒截止时间；空队列等到输入或返回线程 timeout，零长度立即返回，
无限截止时间当前明确拒绝。收包线程在驱动锁内入队并设置等待字，读取端在同一锁
内检查队列、重置等待字，随后用 wait-word 比较并等待；接收故障同样在锁内设置等待
字并唤醒。这个顺序旨在覆盖检查与登记之间的输入/故障竞态，并非客体验证结论。

`python3 scripts/build.py --output-dir build/w1_terminal_read_until_20261030` 通过，
build ID `b19bfd0774d94a09`，terminal ELF SHA-256
`a4b38a2b3c0765e3100f3e273e20059c66a7d98a8054f9783b3683e4db216d1c`。
`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/services/terminal_control.cpp tests/fixtures/ncursesw/terminal_control_host.cpp
-o ${XOS_SCRATCH}/xos_terminal_control_host && ${XOS_SCRATCH}/xos_terminal_control_host` 和
`git diff --check` 通过；宿主模拟只覆盖控制客户端，未运行读取线程或真实设备。

服务仍串行处理控制请求，等待期间不能处理下一请求，控制端失效不直接中断该读取，
只能等有限截止时间或设备故障；不支持无限阻塞、独立应用会话、前台移交及恢复。
时限精度、输入/超时竞争和故障唤醒尚无客体验证；不可将构建结果当成 W1 验收。
下一步解决服务会话与取消、设备恢复及旧 console 接管，再完成提交后客体测试。
