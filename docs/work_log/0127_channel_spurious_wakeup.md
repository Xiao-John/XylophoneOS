# 0127：通道伪唤醒处理

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。核对终端读取取消时发现 sys81 契约允许伪唤醒，而终端服务和控制客户端
原先等待一次就发送或接收，可能将 full/empty 误认成致命故障。新增 SDK 辅助循环，
使用原绝对截止时间重新等待，仅对对应 full/empty 重试，其余错误返回；终端两端改用
该循环。控制端保留真实负错误，并在失败后失效通道。未变更内核 ABI。

`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/services/terminal_control.cpp tests/fixtures/ncursesw/terminal_control_host.cpp
-o ${XOS_SCRATCH}/xos_terminal_control_host && ${XOS_SCRATCH}/xos_terminal_control_host` 通过；宿主模拟
分别注入一次 full 和 empty，验证重试及既有失败清理，不代表内核实际唤醒资格。
`python3 scripts/build.py --output-dir build/w1_terminal_channel_retry_v2_20261030`
通过，build ID `7b48d314ca07ba9f`，terminal ELF SHA-256
`1ada7dfaf0ea27de1f42d1697aeace4ad526c191de711fd36bbd8487e6922e69`。
`git diff --check` 通过；构建早于本记录文档更新。

此修正不解决等待期间取消或控制端退出：服务当前串行等待 read_until，仍需可并发
处理请求的会话结构、服务退出和资源回收设计。实际通道等待、竞争和 IRQ 仍未客体验证；
W1/W2 未完成，所有相关更改提交后才做客体验收。
