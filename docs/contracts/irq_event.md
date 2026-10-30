# 受控 IRQ 事件：本地认领

2026-10-30。sys83 本分支已实现，尚未客体验收；供受信设备驱动等待内核认证的
中断事件，不读取设备状态或解释设备协议。首版仅单核 PC 的独占 IRQ4，绑定者必须
是实际 COM1 PIO 持有者；不支持共享 IRQ、热插拔或其他中断路由，不隐含 PIO 权。

`sys_irq_event(action,second,third)`：bind 的 second=设备资源 1、third=0，成功
返回不可复用 token；wait 的 second=token、third=绝对单调 ns deadline（0 立即、
UINT64_MAX 无限），返回正序号、would-block、timeout 或失效；ack 的 second=token、
third=当前待处理序号，错误/重复确认拒绝；close 的 second=token、third=0。
进程身份由内核认证，不能通过自报 PID 获权。IRQ 到达时仅屏蔽路由、记录事件、
应答中断控制器并唤醒；设备原因由用户驱动消除，ack 后再使能。单个未确认事件
不累计为多个；序号耗尽、异常关闭和未证明停机时 fail closed，线路隔离。
仅无 DMA 的独占 COM1 可由 supervisor 按 [PIO 契约](pio_grant.md)显式解除隔离，
随后由用户态驱动重新初始化设备；其他设备不可据此推论。token 耗尽不能恢复。
退出、故障、成功 exec 和撤权取消等待并屏蔽/失效；失败 exec 不改变。原子检查与
登记在单核不可抢占区间完成，超时使用系统单调时间，允许伪唤醒后重试。

实现须同步共享头、SDK、manifest、定向客体探针；本地认领不等于全项目登记。全部
相关更改提交后才做客体验收。PIO/IRQ 不等于用户态 UART、终端、救援或 W1 完成。
