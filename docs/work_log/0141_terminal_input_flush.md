# 0141：终端输入清空

2026-10-30。用户态 UART 驱动在与 IRQ 处理共享的锁内，有界读取并丢弃硬件接收
FIFO；确认 FIFO 已空后清理软件接收队列。若连续输入使 256 字节限额耗尽，则
返回 busy，部分硬件数据可能已丢弃，不声称回滚。服务暴露应用会话的输入清空；
libc `tcflush(TCIFLUSH)` 使用该路径，`TCSAFLUSH` 先排空发送、再清空输入、最后
更新模式。错误时不更新模式，但已丢弃的输入可能不可恢复。`TCOFLUSH` 和
`TCIOFLUSH` 仍返回 ENOTSUP。细节见[终端契约](../contracts/terminal_control.md)。

宿主控制客户端模拟覆盖清空操作和 `TCSAFLUSH` 编码，服务原有宿主模拟通过；其
驱动由模拟替身实现，并未执行真实端口 I/O。命令见 0134/0135。专用客体应用探针
已更新成功和不支持动作的断言，尚未运行。`python3 scripts/build.py
--terminal-supervisor-probe --output-dir build/w1_terminal_flush_20261030` 通过，
build ID `95afff56f3ae884e`，terminal ELF SHA-256
`61bc071bb6a175a8bc98ca432ceeb1bd9d030087d86bf1cd26c448dd50bde2d2`。
线程配置 libc 源码单独交叉编译通过；构建早于文档更新。

尚未客体验证 FIFO 状态、持续输入、清空/IRQ 竞争、超时和故障，不能声称完整 POSIX
终端或 W1/W2 通过。下一步补严格 UTF-8 SDK 的 ncursesw 独立消费者、前台生命周期
和恢复；所有相关变更提交后执行客体验收。
