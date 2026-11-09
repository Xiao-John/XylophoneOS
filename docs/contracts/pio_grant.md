# 受控设备 PIO 授权：本地认领

2026-10-30。sys82 已实现，尚未客体验收。用户已明确由本任务解决 COM1 与调试
通路交接；设备 PIO 与 IRQ 是相互独立的通用机制。本接口只授予固定登记的设备
资源，不代理设备数据，也不根据应用名称或用户自报 PID 授权。单核 x86-64 首版。

拟用 sys82 `sys_pio_grant(action,target,resource)`。真实 bootstrap supervisor 是
首版唯一授权者；`target` 必须是有完成记录、处于 building 状态的直接受控子进程。
资源 1 为 PC COM1 的端口 `0x3f8..0x3ff`；其他资源遵循各自登记契约。授权前必须先完成内核
调试串口独占交接，未消费的内核缓存或 UART 输入存在时返回 busy，不丢弃字节。
授予只赋予 TSS 范围内直接 I/O 权限，不隐含 IRQ、其他端口、设备恢复或转授。

默认无权；fork 不继承，成功 exec、退出、故障及显式撤销立即清除权限，失败 exec
保持。权限在调度切换前装入 TSS，任何多字节指令跨越授权范围都被硬件拒绝。IRQ4
仍必须通过独立通用 IRQ 接口授权及屏蔽/应答；其未实现时不得把 PIO grant 宣称为
可用终端。所有权终止后，如无法证明设备及中断已停止，设备进入不可再授予的隔离
状态；不自动重启驱动、恢复内核串口或宣称救援可用。调试串口关闭后，内核串口
输出不能伪报成功。实际用户态驱动、终端服务和备用救援路径仍须另行实现。

资源 1 的 action 为 grant=0、revoke=1、query=2、controller=3、recover=4；仅当前 PIO 持有者可用
controller 查询内核认证的授权者 PID，target 必须为 0，失权后拒绝。query 仅限
supervisor，target=0，结果 0 可授权、1 已授权、
2 已隔离。grant/revoke 的 target 为直接子 PID、resource=1；busy 表示交接时存在未
消费输入，授权失败不改变资源状态。授权成功后内核 debug 不再访问串口；串口
输出返回 0（VGA 可显示），原 console 读取返回 denied。授权后终止会隔离资源。
`recover` 仅允许真实 supervisor 在没有 PIO/IRQ 持有者、调试串口已脱离时请求；内核
保持 IRQ4 屏蔽并解除 COM1 的授权和中断隔离，允许随后重新授权 building 子进程，
不会访问、重置或读取设备。此限定只适用于无 DMA 且 IRQ4 独占的 COM1，不推广到
其他设备。下一用户态驱动在绑定 IRQ 前设置 115200 8N1、禁用旧中断使能并重建配置，
并不保证旧请求结果、旧队列或电气输入保真；不可据此宣称透明恢复或救援已实现。
原 console 不重新接管，旧调试串口在首次成功脱离后不会重新附着。若 IRQ token 已耗尽
仍不能绑定。以上恢复路径尚未经过客体验证。
该语义不承诺交接间输入流未丢失：设备 FIFO 满和电气错误
须由后续驱动与真实环境验证。

## 资源 2：PC Speaker（AU1）

资源 `pio_resource_pc_speaker=2` 是单核 x86-64 PC Speaker 的固定 PIO grant，端口
集合严格为 `0x42`、`0x43`、`0x61`。TSS bitmap 分别放开 channel 2 数据端口、PIT 命令
端口和 Speaker gate；不开放 `0x40`/`0x41`、channel 0/1、它们之间的端口或任意 I/O。
该授权没有 IRQ、DMA、转授或设备重置权。资源 1 的 COM1 语义保持独立。

资源 2 的 `delegate=6` 仅允许真实 supervisor 将 **controller-only** 权限交给一个直接
building 子进程。它不给目标 PIO 权限；该 controller 不可再委派。controller 可用
`grant=0` 将唯一的活动 PIO 租约授予自己的直接 building 子进程。真实 supervisor 仍可
直接 grant 自己的 building 子进程。该两层授权保持调用主体由内核认证，service 名称和
请求内容均不授予设备权利。controller 只能启动一个活动扬声器 worker；worker 退出、
release 或租约到期后，controller 可以为下一个音符创建新的短时 worker。

每个 PIO 所有者首次进入用户态时启动单调时钟租约，最长 2,000 ms。租约不可续期，精度
受当前 100 Hz 调度 tick 限制，静音延迟上限一个 tick（10 ms）。因此 AU1 的短租约可用于
AU2 的每音符 worker，而不会给常驻服务持续 PIO。无权调用返回 denied，第二个活动所有者
返回 state error；query=0 表示可授权，1 表示已有活动所有者。真实 supervisor 或唯一
controller 可查询状态；当前 PIO 所有者可用 `controller=3` 查询其授权者。controller
或 supervisor 可撤销直接子 PIO owner；supervisor 可撤销 controller，撤销同时静音并
终止当前 worker。所有者可用 sys82 `release=5`（target=0）提前停止并放弃端口权。

租约到期时，定时入口立即调用 PC 平台 safety stop，清除当前 TSS bitmap 中的扬声器权限，
并释放所有者记录。所有者正常退出、异常退出、被杀、成功 exec 替换和 supervisor 撤权
也会立即停止并释放；所有者主动 `release` 是正常完成/取消的内核确认路径；失败 exec
保持原授权。fork 不复制权限。任何调用架构 halt 的 panic/
停机路径都先执行同一幂等 safety stop。该 hook 只在 `0x61` 上读改写，清除 bit 0/1
（PIT2 gate 与 Speaker data enable）并保留其余位。无 UART 等待或繁忙延迟。

用户态音频服务对固定设备资源负责音高与时长预校验；内核不解析音符或旋律。直接 PIO
访问本身允许 worker 选择任意 PIT2 控制字，因此安全边界是“每个 worker 最多 2 秒后强制
静音”，不是频率白名单或声学音量限制。PC Speaker stop 是 best-effort；平台/CPU 已无法执行内核代码、
硬件卡死或外部电路故障时无法保证静音。

接口要求定向测试无权 fault、边界、
子进程身份、切换、fork/exec、撤权、故障、未消费输入与调试通路独占。该认领仅本
分支可见；所有相关变更提交后才进行客体验收。不能把不完整交接标为 W1 完成。
