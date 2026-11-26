# ClarkE 的 WebCore CPU 共享页

在锁定的 WPE WebKit 2.54.2 上，应用 `software_context.patch`、
`software_buffers.patch`、`software_graph.patch` 后应用 `shared_memory_xos.patch`。
沿用软件 WebCore 目标的配置。交叉工具链的 `XOS_NATIVE_ABI_INCLUDE` 须包含
原生 SDK 的 `xos/ipc_v1.hpp`、`xos/ipc_v1_abi.hpp` 及已有的 VM、syscall 头。
静态最终链接须包含对应目标的原生 SDK syscall 实现。

## 现有语义

此处的 WebCore `SharedMemory` 使用 sys88 的 [IP4 grant](../../../../docs/contracts/ipc_v1.md#大块数据与-vm-依赖)。
内核为每个分配保有同一组清零页。各映射有不同地址；CPU 写者与只读读者观察同组页。
句柄和映射分别持有存储引用；关闭单个映射不会撤销其它映射，最后一个本地引用销毁
底层 grant。映射失败时返回原有的空结果。写转读会缩减 WebCore 句柄的保护上界，
读者无法提升为写者。只读别名由内核 R 映射，WebCore 不提供其可写 span 或绘制上下文。

IP4 单 grant 现最多 64 页，XOS 当前为 256 KiB。空分配、大于单 grant 的对象、COW
以及不匹配的权限请求返回失败。 `createCopy` 仍是上游明确请求的快照操作；
`createVMShare` 与 `createVMCopy` 沿用上游未支持返回。现有匿名 VM 与 files 匿名
对象保留原语义。此路径不依赖 FAT、GL、Ganesh 或显示服务。

## 跨进程后续

本端口的 WebCore 句柄只在本进程持有同一个 grant 引用，创建时不持委派权。
真正跨进程共享可以在已有 IP4 机制上实现明确的借用生命周期。需要认证收件进程，
按 R 或 RW 交付权利，并定义接收确认、在途释放以及生产者退出时的收回。现有内核
要求管理权才可主动关闭整个 grant，不能由只有映射权的收件人单独释放句柄。
在为该协议单独验收之前，WebKit2 的编解码器不应传输这个本进程类型。整页大缓冲、
跨进程画面交付与进程崩溃恢复另行验收。
