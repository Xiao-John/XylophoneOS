# 0122：受控 IRQ 事件机制

2026-10-30。实现 sys83：COM1 PIO 持有者可绑定独占 IRQ4，内核仅屏蔽路由、向 PIC
应答、更新单个待确认事件序号并唤醒等待者；驱动负责读取/消除设备原因，按准确
序号 ack 后重新启用路由。支持非阻塞和绝对单调 deadline 等待；关闭、PIO 撤销、
成功 exec、故障及退出屏蔽并失效，未证明设备停机时线路隔离至重启。失败 exec
不应改变权利；无共享 IRQ、热插拔或设备协议处理。头、SDK、两类 manifest 与 ABI
登记已同步，状态仅 `implemented_unqualified`。

`python3 scripts/build.py --output-dir build/w1_irq_event_20261030` 成功，提交前
build ID `e7ef590bc17c44fb`。未运行 guest；未证明 IRQ 投递、超时、丢唤醒、并发
ACK、撤权、设备持续断言、单调时间及资源回收。用户态 UART、终端服务、失败恢复、
救援和 W2 ncursesw 仍未实现；全部相关改变提交后才做客体验收。
`irq_negative_probe.cpp` 的非持有者绑定/等待/确认拒绝断言已交叉编译，尚未运行；
文档一致性检查 551 链接、70 syscall、73 历史来源及 ABI 速查检查通过。
