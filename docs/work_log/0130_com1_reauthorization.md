# 0130：COM1 显式重新授权基础

2026-10-30。COM1 首次移交后，设备独占、无 DMA，IRQ4 路由可由内核屏蔽，PIO
权限在进程切换时按所有者重装。基于此受限平台条件，sys82 增加 supervisor 独占的
`recover`：仅当 PIO/IRQ 均无持有者、COM1 已隔离且旧调试串口已脱离时，保持 IRQ4
屏蔽并解除授权/IRQ 隔离；后续 grant 可授予新的 building 子进程，不再次调用旧
调试串口脱离。内核不读取或重置 UART，不恢复旧 console；细节见
[PIO 契约](../contracts/pio_grant.md)和[IRQ 契约](../contracts/irq_event.md)。
这一机制需要实际 supervisor 进行恢复策略，旧请求和输入结果均可能未知。

用户态 UART 驱动在 bind 前先禁用 UART 中断并设置 115200 8N1、调制解调器控制，
不主动清空 FIFO；旧驱动可能留下的不完整除数、中断或设备状态仍须在真实恢复测试
检查。没有证明交接过程输入无丢失；残留 PIC 请求、硬件错误、旧 owner 撤权、
资源回收和中断风暴均未在客体验证。不得将此基础称为完整故障恢复或救援。

`python3 scripts/build.py --output-dir build/w1_com1_recovery_20261030` 通过，
build ID `331c09cdd3d42165`；terminal ELF SHA-256
`6b5e5407899703912e32076fe74f05cc48ce3a73017b8953e11342f7fe9f3403`。
宿主服务读取探针和 `git diff --check` 通过；非 supervisor 的 recover 拒绝断言已
加入 `pio_negative_probe.cpp`，尚未客体运行。构建早于本记录文档更新。

下一步补 supervisor 恢复与服务重连、专用客体故障探针和 Xsh/应用通路；所有相关更改
提交后运行客体验收。W1/W2 和 PR 均未完成。
