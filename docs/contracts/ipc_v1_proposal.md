# IPC v1：稳定接口与实现契约提案

2026-11-10，**PROPOSED，未分配 syscall、未实现、未宣称 SDK supported**。
路线见 [IPC 计划](../plans/ipc_sel4.md)；现行 [通道契约](channel.md)、
[Interactium](interactium.md)、[线程](threading.md)与[ABI 登记](abi_registry.md)
继续有效。本文的函数名、类型、限额均为评审接口，不是已有头文件或可链接 SDK。
合入本提案不等于登记新号；必要的编号、wire 布局及标志必须先经独立登记。

## 目标与约束

为应用/服务提供稳定的面向对象的 IPC 语义，使端点、请求和错误无需知道采用旧通道、
新通用路径还是快路径。所有后端须满足同一可观察语义；不能满足时明确 unsupported，
不能把单槽队列伪装成同步握手、用轮询伪装阻塞或把失败转成成功。服务发现、协议、
重试和故障恢复在用户态；内核仅处理认证、隔离、受界消息、等待及资源生命周期。

借鉴 [seL4 IPC 教程](https://docs.sel4.systems/Tutorials/ipc.html)的端点、
短消息、内核交付 badge、一次性 reply、Call/ReplyRecv 与满足条件的快路径；借鉴
[notification 教程](https://docs.sel4.systems/Tutorials/notifications.html)的信号合并。
这是 XOS 自己的契约：不声称 seL4 二进制/源接口兼容、形式化验证、优先级调度或
同样的 fastpath 条件。seL4 同步 rendezvous 与现有单槽异步端点不可互换。

首个内核资格为 x86-64、单 CPU；逻辑接口固定宽度，寄存器映射属于架构实现，
不假定每种架构同样的寄存器数量。多核、跨核唤醒和 shootdown 必须独立设计验收。
C20–C25、C28–C29 生效；不扩大设备权限、不修改现有进程与线程 ABI。

## 使用方先可依赖什么

IP0 冻结本文的**源代码层语义与协议规范**，供用户态服务并行设计和编写；不能作为
可运行 SDK 依赖，直至实现 PR 提供版本化共享头、真实后端、两套 SDK manifest 与
客体验收。应用通过 `ipc_open`、`ipc_call` 等 SDK 概念接口使用；数字 syscall、
寄存器、C 结构体的 `sizeof`/offset、错误码整数和各目标 ABI 调用约定须在 IP1 ABI
登记 PR 冻结。未登记前任何代码样例均为伪代码。新能力通过 manifest 与运行时
feature query 双重发现：编译期有声明不代表运行时可用；未知版本或缺少 feature
返回 unsupported，不静默降级。基线应用仍可明确使用旧 IPC。

能力分组：`endpoint_call_v1`（受控端点、短消息 call/receive/reply）、
`deadline_v1`（统一单调绝对期限）、`notification_v1`（通知）、`wait_set_v1`
（多源等待）、`bulk_grant_v1`（大块共享授予）；各组独立登记和报告。不存在的组
不得在 manifest 标 supported；无组时 SDK 返回 unsupported，不能报告空成功。
接口使用 `(version, size)`、固定宽度整数、保留字段必须为零，未知版本/flag 拒绝；
每项成功和失败的输出初始化规则及输入不可变规则须在 ABI 登记中逐一量化。
本提案不预占 syscall 88–95、128+ 或改用已分配号，禁止私号试验污染公共 ABI。

## 对象、权利与消息

逻辑对象为 endpoint、受权引用（handle）、一次性 reply token 和可选 notification。
引用绑定内核认证的主体及对象代际；`send/call`、`receive`、`reply`、`manage`、
`delegate`、`signal/wait` 分权。创建者显式授予，转授只能削减权利；不能用用户自报
PID、程序名、消息里的身份字段或未认证数字 handle 取得权限。badge 是**由授权者
设置、内核随消息交付的标签**，可标识授权路径，但不等于不可伪造的全球用户身份；
badge=0 合法，身份审计要同时考虑 endpoint/委派链。受控原始 endpoint 可以有多个
发送者；谁能 receive、是否允许多个 receiver 由授权与协议明确，不以持有 PID 推断。

小消息是 `(label, payload)`：label 为无权限语义的用户协议标识，payload 为有限长度
字节序列，允许零长度；大小必须在查询的 profile 限额内。接收结果包含实际长度、
认证 badge 和消息；缓冲不足时返回 `buffer_too_small`、报告所需长度、**不消费消息**，
不截断也不交付 reply token。发送端快照长度与内容；缓冲区必须完整可读，接收区必须
完整可写；无效指针、溢出和资源不足在提交前失败，不部分传输或唤醒为成功。长消息、
IPC 寄存器数量及 byte/word 的转换由每架构 ABI 明定，不能把寄存器数写入协议版本。
首版不支持消息携带普通能力、物理地址、文件描述符或 grant；无相应已验 feature
时明确 unsupported。普通 payload 为字节，协议自行定义编码和 endian。

## 同步调用及状态机

以下为语义伪 API，不是已有 ABI：

```
call(endpoint_send, request, reply_buffer, absolute_deadline) -> reply | error
receive(endpoint_receive, receive_buffer, absolute_deadline) -> (message, badge, reply_token) | error
reply(reply_token, message) -> success | error
reply_receive(reply_token, reply, endpoint_receive, buffer, deadline) -> next_message | error
```

`call` 是一个请求和至多一个响应的同步交易；发送端在接收者已接收请求之前可以排队
等待，在交付后等待其专属 reply。`receive` 完整接收后才得到当前调用专属 reply token；
该 token 不由客户端伪造，不关联用户提供的序号或通用 endpoint handle。每次成功
`reply` 恰好消费一次 token 并唤醒对应调用者；重复使用、错误持有者、过期 token 和
对已退出/取消对象回复均失败。reply 大于调用者声明的完整回复容量时，返回
`buffer_too_small`，不消费 token、不写调用者缓冲；调用者仍等待合法回复或期限到达。
接收完成但未 reply 的 token 可被服务器保存到有界槽，
服务器必须显式 reply、取消或关闭；上限、移交和 fork/exec 规则在 ABI 登记中冻结。
初版不承诺向第三方转授 reply token，不允许通过普通消息伪造。

状态：`created -> queued -> delivered -> replied`；也可在任何未完成状态进入
`cancelled/closed`，只允许一个终态。入队前资源/地址校验失败不发生交付。超时、
kill、关闭、撤销与 reply 的竞争由内核在同一序列化点裁决：未交付时取消可保证服务
未收到；**已交付后**超时/服务死亡/客户端取消只能报告结果未知，服务可能已执行，
绝不能自动重试或声称未执行。失效 token 不再能唤醒后续调用；进程、线程退出及 exec
取消等待并回收 token、pin 和引用，完成结果只交付一次。不可取消已发布的部分业务
操作，幂等键、重放、去重和事务恢复由服务协议规定。

`reply_receive` 是顺序组合：先尝试 reply；只有 reply 成功且已消费 token 才开始
下一次 receive。第二步超时、地址校验失败或关闭返回时，上一回复仍已完成，错误必须能区分两个阶段；
不得因 receive 失败而重复 reply。首版无合法 token 时不隐式跳过 reply；单独调用
`receive`。快路径和慢路径必须产生完全相同的状态、错误、身份和顺序；仅在 receiver
已等待、短消息符合 ISA 条件、无转授/复杂状态且调度安全时尝试直接交付及切换，其他
情况走普通路径。何时直接切换由调度策略决定，不承诺必然切换或 seL4 数值性能。

## 等待、通知与时间

所有阻塞期限使用[统一单调时间域](time_domains.md)的绝对纳秒；定义立即检查和无限
等待的专用值，避免与合法时间混淆；唤醒、超时、关闭、取消必须原子登记并恰好完成
一次。伪唤醒只允许明确标注的 readiness 接口，调用方以原始 deadline 重试；`call`
成功仅表示收到了对应 reply。期限不承诺实际唤醒精度，不能以 10 ms tick 当成性能
目标或另建时钟。底层阻塞中的输入输出指针只在内核快照或受生命周期管理的 pin 内
使用；解除映射、权限降低、线程退出与 VM/COW 按各自契约仲裁并释放。

通知是无 payload 的有界事件：建议内核为每个授权 signal 引用固定 badge 位，累积位
按 OR 合并；wait 原子取走当前位集合，重复 signal 可以合并，**不计数、不保证每次
事件**。队列数据和具体操作仍需独立对象；badge=0 的通知语义在登记前必须明定，
不能将其当作已发生但不可观察的事件。`wait_set` 仅在独立 feature 验收后提供；
必须明确多源授权、最大数量、快照、关闭/撤销和无丢唤醒，包括消息、通知、进程退出
和 IRQ 能否共同等待。不得声称现有 `wait_many` 已能统一这些来源。

## 大块数据与 VM 依赖

IPC0 不为追求零拷贝开放任意跨进程映射。IP4 以独立 proposal 设计页/缓冲区 grant：
页归属和引用、可转授权限、配额、读写/执行、映射身份、CPU/TLB 同步、pin、撤销、
超时、退出和故障回收，以及交付/撤销竞态必须有真实验收；DMA/MMIO 不自动纳入。
VM2 PR #102 仍独立审查；VM3/COW 和共享映射均未作为当前 IPC 的已交付依赖，不能以
私有匿名 VM 探针冒充跨进程共享机制。小消息与大块数据走不同契约，不承诺大消息
自动零拷贝；按实测选择阈值，阈值不是接口语义。

## 兼容与迁移

现有 sys4/5、81、84–86、文件/显示/终端/Interactium/音频和 pipe 行为、错误及
旧 ELF 继续可用。现有单槽异步 send 成功仅表示入槽，不表示对端接收，更不表示业务
完成；不能在这些操作上直接套上同步 call 的成功含义。`legacy_mailbox_v1` adapter
只承诺旧语义；新同步 `endpoint_call_v1` 只有在实现能够保证认证 reply、超时和关闭
完整语义时开放。纯用户态的协议适配可作为临时显式后端，但若无法保证服务崩溃、
取消及 late reply 的隔离则只支持其可证明的子集，能力发现不得宣称完整 call。

迁移顺序先新旧并行、使用方按能力显式选择，再用差分测试迁移文件、终端、显示、
Interactium、音频；旧路径退役需单独的调用清单、ABI 兼容方案和真实客体证据，
不能因为新接口存在就悄悄改变旧程序。经 shell 启动的工具按 C27 分别在 xsh/dash
验收；纯 SDK/内核探针如不适用两 shell，说明原因。

## 评审前待冻结

IP1 需逐项定稿并单独登记：句柄宽度与回收/代际、wire 布局/对齐、长度上限与错误
数值、reply 保存/额度、取消后的精确错误与阶段标志、feature query 表、队列公平性、
wait set 限额、fork/exec 与授权传播、内存压力下的不可部分提交。可预先对抽象语义
写应用，但不得以本文数字或伪代码取代已登记 ABI。安全性质与性能指标的验证矩阵见
[实施路线](../plans/ipc_sel4.md)。
