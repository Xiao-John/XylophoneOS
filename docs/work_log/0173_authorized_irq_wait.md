# 授权 IRQ 空队列与关闭探针

现有 IRQ 负向探针只覆盖无授权调用；终端驱动的真实输入测试覆盖实际中断送达，
但未单独覆盖授权后的空等待和 token 状态。专用 COM1 授权探针现先在用户态禁用
UART 中断原因，再绑定 IRQ4，检查重复绑定、立即空等待、未产生事件时错误 ACK、
错误 token、单调截止超时、关闭后旧 token 失效及隔离期间拒绝重绑。随后 supervisor
回收授权并启动终端，验证交接未被破坏。

提交 `bee7deaabdd2388b4bc631e87f9df8606494677a` 后重建的专用客体通过上述空队列
与关闭检查，build ID `aa0563378fe25368`，系统 manifest SHA-256
`cba50fba01ef6088d03a627d05fc9789161678fce0ca2d4ec23cb916d548cb94`，镜像 SHA-256
`10e78a5dde870277249a848b8ab92eb9c2a5825e548c9a984011785fc4f17926`，SDK 树 SHA-256
`2ea535a61d5962ca24c92cbbb2c6921359c83ecf594512027dbe3141291cd138`，串口 SHA-256
`4263082b362d1634c8579b5b02c6e9a13168790892bee278fa5c6477ff3fbd8c`；报告位于
`build/w1_irq_empty_bee7dea/`。

新增一组真实事件探针：用户态驱动启用 UART THRE 中断，核对正序号在 ACK 前保持、
错误序号被拒绝，驱动先禁用设备中断原因再 ACK，重复 ACK 被拒绝且等待恢复为空。
提交 `83919fe5615a09f331bca4d47206340878c0bc76` 后，专用客体通过此中断和 ACK
状态检查，build ID `f020e17e6e0bf27c`，系统 manifest SHA-256
`0374acb7fd0d0cc5804bc59b71f1513a3085c2d4b64a2bf520d56c18c6475d11`，镜像 SHA-256
`ae7dd3362177fecfe45cf8630bc91b8c2990216ffa1248cfd4926c4b959b8519`，SDK 树 SHA-256
`3fb66c236a33e975267fd2ceb64962f407b20d0f3f8e6339980f5ec599cdc461`，串口 SHA-256
`e0269f058afb9f9a32f5f2b2c6032719b592f03fa043d3b70fc924b5a33b5f65`；报告位于
`build/w1_irq_delivery_83919fe/`。这只覆盖一次受控中断，不推断所有到达/撤权竞争。

进一步增加阻塞等待者关闭检查：工作线程进入 IRQ wait 后，主线程通过线程统计确认
其确实已阻塞，再关闭 token 并 join，要求等待者收到 denied。提交
`9b2ee279dca9bd45bf2ed4f78d980a5548cf7daf` 后重建的专用客体通过此项及既有 IRQ、
PIO 和终端交接子集。build ID `d0ac4b8288b53334`，系统 manifest SHA-256
`2ee28c96290e1c6c036264f64ea67808855c259dad15063bc81b9f02974156d0`，镜像 SHA-256
`0b66948ab770b3ac5917fa8b83742d31163fc5fd032d23d167514fd6cca83b57`，SDK 树 SHA-256
`19fc9a369a9b80887b5b9d72687ac75809ae78459f13d626b6ef67daad9673f4`，串口 SHA-256
`8ead76e4a016e7ce0986e91cc7437f940aa496fad40581ca6babebaa1c82f43e`；报告位于
`build/w1_irq_wait_close_9b2ee27/`。不将关闭单一等待者外推到所有撤权竞争。
