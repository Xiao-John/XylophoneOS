# 0120：COM1 调试通路脱离与 PIO 授权

2026-10-30。sys82 在本分支实现固定 COM1 PIO 资源授权：仅真实 bootstrap supervisor
可向其有构造权、building 的直接子进程授予 `0x3f8..0x3ff`，不是任意端口/进程授权。
内核调试输入缓存或 UART 已有待接收字节时返回 busy；成功后先断开内核对串口的
后续访问并屏蔽 IRQ4，再赋予目标进程的 TSS 窗口。内核调试输出仍可写 VGA，但
返回 0 表示未写串口；旧 console 输入返回 denied。授权后 fork 不继承，成功 exec、
exit/fault 和 supervisor 撤销清除窗口并屏蔽 IRQ；未证明设备停机时资源隔离至重启。
失败 exec 不改变授权。没有 IRQ 交付、UART 用户驱动、终端客户端、自动恢复或救援。
设备 FIFO 硬件丢失和交接瞬间外部字节行为均尚未验证。

`python3 scripts/build.py --output-dir build/w1_pio_grant_20261030` 成功，提交前 build
ID `80dadfb991b3885f`。新增 `pio_negative_probe.cpp`：测试非 supervisor 请求拒绝，
并以独立模式触发未授权 `inb` 以待客体检查；已用本次 SDK 交叉编译/链接，未运行。
没有实际 guest、PIO 隔离/跨界、目标进程授权、竞态、关闭、故障、COM1 交接或资源
恢复证据。sys82 在本分支 allocated、manifest 标记 implemented_unqualified，尚未跨
分支核冲突或客体验收；W1/W2 和本地 main 整合/PR 均未完成。
