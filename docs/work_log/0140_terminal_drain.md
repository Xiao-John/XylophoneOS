# 0140：终端发送排空

2026-10-30。用户态 16550 驱动检查 LSR 的 TEMT 位，区别于仅表示发送缓冲为空的
THRE；终端服务在确认发送缓冲及移位寄存器都空后才应答 drain。由于此设备没有
TEMT 中断，未空时按单调时钟 tick 睡眠后重查；控制请求、应用退出或服务失败可
中断，最迟在下一次检查时观察。`tcdrain` 通过该路径运行，`tcsetattr(TCSADRAIN)`
先验证请求、确认排空，再更新服务模式；失败或中断不提交模式。输入清空及
`TCSAFLUSH` 仍明确不支持。细节见[终端契约](../contracts/terminal_control.md)。
排空、写入和 IRQ 处理遇到可能表示设备不存在的 LSR 全 1 时返回错误；若此前已写入
部分字节则保留真实短写，不把后续不确定状态计为成功。

宿主服务模拟覆盖非空后睡眠、空后完成和待处理控制请求中断；客户端模拟覆盖
drain 与排空后设置编码，命令见 0134/0135。专用客体应用探针增加 `TCSADRAIN`
与发送后 `tcdrain` 断言，但尚未运行。`python3 scripts/build.py
--terminal-supervisor-probe --output-dir build/w1_termios_drain_v2_20261030` 通过，
build ID `4fde0d3ae6567640`，terminal ELF SHA-256
`1db2e366e99361d0b69128986d41e36311569854aa10f5f4fc4afa3888d112ff`；
构建早于文档更新。`git diff --check` 通过。

硬件 TEMT、虚拟机串口、输出速度、跨任务竞争和中断路径均未客体验证；poll 是
针对无 TEMT 中断的输出排空，并非输入事件等待或完整 POSIX TTY。下一步实现真实
输入清空、W2 严格 UTF-8 SDK 和 ncurses 独立消费者，并完成应用前台/exec/故障恢复；
所有相关变更提交后再客体验收，W1/W2 尚未完成。
