# 0085：串口硬件溢出观测

2026-10-29。FIFO 软件丢弃计数之外，COM1 输入层增加饱和的硬件 overrun 观测计数。
读取 UART line-status 会清除此标志，因此输入轮询、IRQ 接收以及输出等待读取状态
均经同一函数计数；一次观测不等于恰好一个丢失字节。计数目前只供内核使用，没有
用户 ABI，也未定义如何向终端服务报告或清除；framing/parity/break 仍未实现语义。

`python3 scripts/build.py --output-dir build/w1_uart_overrun_build_20261029` 通过，
build ID `0b6de5f9ad6fe51a`。这是提交前构建检查，未在客体注入 UART 溢出，也未验证
IRQ、计数、恢复或交互行为。W1/W2 全部相关更改提交后才做客体验收。
将状态读取函数改为平台内部链接后再次构建：`python3 scripts/build.py --output-dir
build/w1_uart_overrun_final_20261029`，build ID `7d6522965cb30360`，仍是提交前构建。

`sys_pipe_wait` 当前 console 分支明确返回 would-block，libc 据此保留 EAGAIN；不得
直接改成阻塞。真正的设备等待应先冻结调用者权限、原子检查/睡眠、超时、关闭唤醒和
多源等待，并按 ABI 登记流程实施；前台所有权与旧直通读取也必须一起处理。
