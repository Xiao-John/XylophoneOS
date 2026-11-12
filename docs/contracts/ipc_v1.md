# IPC v1：稳定接口与实现契约

2026-11-12，**IP2/IP3 功能已完成 guest qualification；endpoint_call、deadline、notification 与 wait_set 已支持（query 与两 manifest = 0x0f）。bulk_grant 仍待 IP4 qualification：grant 后端与 owner guest 验收脚本已实现（PR #112），验收进行中。**
路线见 [IPC 计划](../plans/ipc_sel4.md)；现行 [通道契约](channel.md)、
[Interactium](interactium.md)、[线程](threading.md)与[ABI 登记](abi_registry.md)
继续有效。IP1 的固定 ABI 位于 `src/shared/include/xos/ipc_v1_abi.hpp`，syscall 88
列入 ABI 登记；sys88 feature query 报告 supported mask `0x0f`。普通与线程 SDK manifest
登记 `endpoint_call_v1`、`deadline_v1`、`notification_v1`、`wait_set_v1` 为 supported；
`bulk_grant_v1` 在 IP4 客体验收前保持关闭。

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

IP0 冻结逻辑语义；IP1 冻结下列 x86-64 v1 ABI 数字、结构布局、限额、错误和 feature
命名。注册不提供已验的运行时能力。`ipc_open` 等逻辑名仍是概念接口，
不得当作当前头文件符号。普通与线程 SDK manifest 仅声明经真实客体验收的 feature；
编译期有 ABI 头不代表运行时可用。IP2/IP3 通过客体验收后，四个位按本契约登记为 supported；
IP4 的 bulk grant 仍保持关闭，直到真实 guest qualification。

能力分组：`endpoint_call_v1`（受控端点、短消息 call/receive/reply）、
`deadline_v1`（统一单调绝对期限）、`notification_v1`（通知）、`wait_set_v1`
（多源等待）、`bulk_grant_v1`（大块共享授予）；各组独立登记和报告。不存在的组
不得在 manifest 标 supported；经真实客体验收的 endpoint_call/deadline/notification/wait_set 四组按本契约登记为 supported（0x0f），bulk_grant_v1 保持关闭直至 IP4 验收。
接口使用 `(version, size)`、固定宽度整数、保留字段必须为零，未知版本/flag 拒绝；`ipc_v1_feature_query.direct_switch_count` 为内核输出的短消息直切累计（输入仍须为零），供客体独立验证直切路径确实发生；
每项成功和失败的输出初始化规则在 IP1 冻结如下。syscall 88 已登记；89–95 与 128+
仍未分配，禁止私号试验污染公共 ABI。

## IP1 ABI v1 登记

`sys_ipc_v1=88` 使用既有 x86-64 syscall 调用约定：arg1 为 action 数值，arg2 为对应请求
结构的用户指针，arg3 必须为 0。请求结构自然对齐、固定宽度、little-endian；
`header.version=1`、`header.size` 必须等于对应结构的精确大小，header 与结构保留字段
必须为零。所有输出字段入参必须为零。除用户结构地址不可写导致无法回写外，失败路径将
输出字段清零；`buffer_too_small` 例外地在对应长度输出字段写入所需完整字节数，且不消费
消息、token 或队列项。输入结构与发送 payload 先完整快照，提交点前的参数/地址失败无部分
入队；成功或失败都不修改输入字段。未知版本、操作、feature、非零 flag 返回
`unsupported`；长度、保留字段、范围或非零 arg3 错误返回 `invalid_argument`。

| 操作 | 值 | 请求结构 | 字节数 | 用途 |
|---|---:|---|---:|---|
| `query_features` | 0 | `ipc_v1_feature_query` | 72 | 返回 known/supported mask 与固定资源上限 |
| `endpoint_create` | 1 | `ipc_v1_endpoint_create` | 48 | 创建 endpoint，调用者指定非零初始权利子集 |
| `endpoint_delegate` | 2 | `ipc_v1_endpoint_delegate` | 72 | 向存活目标 PID 派生新 handle，权利只能缩减并设置 badge |
| `endpoint_close` | 3 | `ipc_v1_endpoint_close` | 40 | manage 权利持有者关闭 endpoint |
| `call` | 4 | `ipc_v1_call` | 88 | 快照请求 payload 并同步等待 reply，返回 reply label |
| `receive` | 5 | `ipc_v1_receive` | 88 | 接收请求并返回内核生成的一次性 reply token |
| `reply` | 6 | `ipc_v1_reply` | 64 | 使用接收端持有的 token 回复一次 |
| `reply_receive` | 7 | `ipc_v1_reply_receive` | 120 | 先 reply 后 receive，输出部分成功标志 |

每个请求以 16 字节 `ipc_v1_header {u32 version, u32 size, u64 reserved}` 起始。字段顺序、
宽度、大小断言由 `ipc_v1_abi.hpp` 固定；SDK manifest 只登记 feature，不复制结构布局。
`ipc_v1_call` 的 offset 72 是 `reply_label_out`，offset 80 为单个零保留字；该 IP1 ABI
澄清保持 88 字节请求大小不变，修复了逻辑 reply label 与线布局之间的遗漏。
用户 buffer 为 64 位地址；null 只允许用于长度为零的 payload。Call 的输入区和 reply 输出区
完整验证后才可排队；receive 的输出区完整验证后才可交付。结构输出区不得与对应 payload 输出区重叠。
receive 缓冲不足返回所需长度，
保留请求且不产生 badge/token。Call 的 reply buffer 在等待开始前完整验证；reply 大于其
capacity 时，`buffer_too_small` 返回 server，token 仍归 server 持有以便同一 holder 重试较短回复。

| ABI 项 | 冻结值 |
|---|---|
| 权利位 | `call=0x1`, `receive=0x2`, `manage=0x4`, `delegate=0x8` |
| feature 位 | `endpoint_call_v1=0x1`, `deadline_v1=0x2`, `notification_v1=0x4`, `wait_set_v1=0x8`, `bulk_grant_v1=0x10`；known mask `0x1f` |
| message label / badge / handle / reply token | 独立 `u64`；label/badge 是数据，handle/token 是 opaque 值 |
| payload | 0–256 字节；label 不计入 payload 上限；空 payload 合法，不携带 cap/fd/pointer |
| quota | 系统 32 个 open endpoint、16 个 grant、64 个 grant mapping；每进程 8 个有效 IPC handle、65536 个用户页；系统 32 个 queued/delivered call；每 endpoint 最多 8 个 queued call；每 receiver 8 个未消费 reply token；单 grant 最多 64 页 |
| handle/token | 内核在一次启动期间分别单调递增、不回绕、不复用；编号耗尽返回 `resources` |
| deadline | 单调绝对纳秒；0=只尝试当前可配对路径，不排队（无配对则 `would_block`）；`UINT64_MAX`=无限；就绪先于超时判定 |
| FIFO | endpoint 内按成功入队次序交付；不承诺跨 endpoint 顺序、优先级或跨 endpoint 公平性 |

`query_features.known_features` 固定为 `0x1f`，`supported_features` 必须是其子集。IP2
目标 mask 为 `0x3`（endpoint call 与 deadline）；当前两个实际 SDK manifest 的 supported
set 为空。通知、wait set 与 bulk grant 属于 IP3/IP4，不改变 IP2 mask；这些后续 action 已有内核路径，
但未完成 owner qualification 时不能宣告 supported。尚未实现或未知的 action 返回 `unsupported`，
不得返回全零成功结果。

以下负值只属于 sys88，并非 errno：

| 名称 | 数值 | 意义 |
|---|---:|---|
| `invalid_handle` | -101 | handle 不存在或不属于当前主体 |
| `denied` | -102 | 缺少权利，或 delegate 试图增加权利 |
| `invalid_argument` | -103 | 尺寸、地址、flag、保留字段、长度或参数无效 |
| `unsupported` | -104 | 未实现操作/feature/ABI 版本 |
| `would_block` | -105 | poll 没有立即可配对的请求/接收者 |
| `queue_full` | -106 | endpoint 排队额度耗尽 |
| `resources` | -107 | 系统/进程配额或单调编号耗尽 |
| `closed` | -108 | endpoint 已关闭或不再有 receiver |
| `timeout` | -109 | deadline 在请求交付或 reply 完成前到期 |
| `buffer_too_small` | -110 | 容量不足；报告完整所需长度且不消费对象 |
| `stale_token` | -111 | token 已消费、撤销、超时或代际失效 |
| `state` | -112 | 当前状态不允许该操作 |
| `address` | -113 | 用户地址范围无效或算术溢出 |
| `busy` | -114 | grant 映射被 pin，或 VM 修改与活动 grant 映射重叠 |

错误到 libc errno 的映射由 SDK 单独定义。`call.phase_out` 为
`not_delivered=0`、`delivered=1`、`replied=2`；timeout 发生于 delivered 后时，phase 保持
delivered，业务结果未知，调用者不得自动重试。`reply_receive.reply_consumed_out` 仅在
reply 成功消费 token 后置 bit0；后续 receive 失败仍报告该位，不能重放已完成 reply。

## IP3 通知、wait set 与慢路径

IP3 的 action 数值与请求布局已在共享头登记（8–18），SDK 提供对应薄封装。通知与 wait set
均已有 x86-64 慢路径；PR #111 的补验已通过（`tests/ipc_v1_guest.py` runs=3，资源基线守恒），feature query 的 supported mask
与两个 manifest 仍为空，保持验收结果与 feature 宣告分离。ABI/内核代码存在不表示已支持。通知与 wait set 的固定限制为系统各
32 个对象、每个 wait set 最多 8 个 source；对象 handle 仍计入每进程 8 个 handle 总额度。

| action | 值 | 请求结构 | 字节数 |
|---|---:|---|---:|
| `notification_create` | 8 | `ipc_v1_object_create` | 48 |
| `notification_delegate` | 9 | `ipc_v1_object_delegate` | 72 |
| `notification_signal` | 10 | `ipc_v1_notification_signal` | 40 |
| `notification_wait` | 11 | `ipc_v1_notification_wait` | 56 |
| `wait_set_create` | 12 | `ipc_v1_object_create` | 48 |
| `wait_set_delegate` | 13 | `ipc_v1_object_delegate` | 72 |
| `wait_set_add` | 14 | `ipc_v1_wait_set_add` | 64 |
| `wait_set_remove` | 15 | `ipc_v1_wait_set_remove` | 48 |
| `wait_set_wait` | 16 | `ipc_v1_wait_set_wait` | 64 |
| `notification_close` | 17 | `ipc_v1_object_close` | 40 |
| `wait_set_close` | 18 | `ipc_v1_object_close` | 40 |
| `grant_create` | 19 | `ipc_v1_grant_create` | 72 |
| `grant_delegate` | 20 | `ipc_v1_object_delegate` | 72 |
| `grant_map` | 21 | `ipc_v1_grant_map` | 72 |
| `grant_unmap` | 22 | `ipc_v1_grant_unmap` | 48 |
| `grant_close` | 23 | `ipc_v1_object_close` | 40 |

通知权利为 `signal=1`、`wait=2`、`manage=4`、`delegate=8`；wait set 权利为
`wait=1`、`manage=2`、`delegate=4`。创建和 delegate 共用 `ipc_v1_object_create` /
`ipc_v1_object_delegate` 布局。通知 signal 使用授权 handle 的 badge 作为 bit mask，pending
状态按 OR 合并；badge 为零是成功 no-op。notification wait 原子读取并清零累计位，0 deadline
只轮询，最大 u64 表示无限等待。单 CPU syscall gate 串行化 pending 检查和阻塞登记；多个
直接 notification waiter 按等待登记顺序消费。signal 唤醒直接 waiter 的优先级高于 wait-set
notification source；多个 wait-set waiter 按登记顺序分配可消费 bits。manage 权利持有者
close 会撤销全部 handle、清除 pending bits
并以 `closed` 唤醒 waiter。最后一个持有者 exit 或成功 exec 时对象也会销毁。

wait set 首版 source 类型仅支持 endpoint 与 notification：endpoint source 必须在添加时持有
receive 权利，报告 queued call readiness；notification source 必须持有 wait 权利，返回并消费
累计 bits。事件 kind 为 endpoint_ready=1、notification=2、closed=3。source close/revoke 产生
可重复观察的 closed 事件，直到显式 remove。wait 返回容量不足时应写入所需事件数且不消费
通知；最大容量为 8。首版不支持把 sys83 IRQ、process exit 或旧 channel `wait_many` 加入
wait set；这些既有接口语义不变，也不得宣称为统一等待。source 的 badge/value 解释固定在
事件 value 中：endpoint readiness 为 0，notification 为被消费的 bit mask，closed 为 0。

ABI 结构大小由共享头 static_assert 固定。通知和 wait set 都仅完成源码实现及本地静态检查，
没有 guest qualification，因此不能宣告任何 IP3 feature supported。

## 对象、权利与消息

逻辑对象为 endpoint、受权引用（handle）、一次性 reply token 和可选 notification。
引用绑定内核认证的主体及对象代际；`send/call`、`receive`、`reply`、`manage`、
`delegate`、`signal/wait` 分权。创建者显式授予，转授只能削减权利；不能用用户自报
PID、程序名、消息里的身份字段或未认证数字 handle 取得权限。badge 是**由授权者
设置、内核随消息交付的标签**，可标识授权路径，但不等于不可伪造的全球用户身份；
badge=0 合法，身份审计要同时考虑 endpoint/委派链。受控原始 endpoint 可以有多个
发送者；谁能 receive、是否允许多个 receiver 由授权与协议明确，不以持有 PID 推断。

IP1 将 handle 绑定到进程主体，不绑定可用户自报的 PID。创建 endpoint 的 holder 获得
endpoint_create 的 rights 必须是已知权利位的非零子集；调用者只能持有所请求的权利。
delegate 只可删减现有 rights，指定存活 target PID 与
u64 badge，并为目标生成新 handle。target PID 仅标识被授予者，不构成授权证明；只有拥有
派生 handle 的主体才能使用它。handle 在本次启动期单调唯一、不重用；目标进程 exit、
fault 或成功 exec 后其 handles 与持有的 reply tokens 撤销，fork 不继承，failed exec 不变。
endpoint 最后一个 receive 权利撤销时立即关闭：未交付 calls 返回 closed，已交付 calls
置结果未知并撤销 token。manage holder 关闭 endpoint 时所有 handle 失效，未交付请求不再
可接收，已交付请求的后续回复返回 stale_token。关闭不表示已交付的业务操作被撤回。

reply token 由 receive 原子地产生，只能由接收该调用时的 receiver 进程使用；不能通过
delegate、fork、exec 或消息负载转移。token 单调、不复用；reply 成功恰好消费一次，endpoint
close、调用取消/timeout、holder exit/fault/exec 使之失效。receiver 的 8-token quota 满时
receive 返回 resources，保持 queued call 不动。global call quota 统计 queued 与 delivered
状态，终态释放配额；handle、token、endpoint 达到单调编号极限后不回绕。

小消息是 `(label, payload)`：label 为无权限语义的用户协议标识，payload 为有限长度
字节序列，允许零长度；大小必须在查询的 profile 限额内。接收结果包含实际长度、
认证 badge 和消息；缓冲不足时返回 `buffer_too_small`、报告所需长度、**不消费消息**，
不截断也不交付 reply token。发送端快照长度与内容；缓冲区必须完整可读，接收区必须
完整可写；无效指针、溢出和资源不足在提交前失败，不部分传输或唤醒为成功。长消息、
IPC 寄存器数量及 byte/word 的转换由每架构 ABI 明定，不能把寄存器数写入协议版本。
首版不支持消息携带普通能力、物理地址、文件描述符或 grant；无相应已验 feature
时明确 unsupported。普通 payload 为字节，协议自行定义编码和 endian。

## 同步调用及状态机

以下函数名是与后端无关的逻辑操作名，不是当前 SDK 符号；固定 action 和请求布局见 IP1 表：

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
对已退出/取消对象回复均失败。reply 大于调用者声明的完整回复容量时，`reply` 返回
`buffer_too_small` 给 server，不消费 token、不写调用者缓冲；调用者仍等待同一 call 的
合法回复或期限到达。接收完成但未 reply 的 token 可由同一 server 进程保存在其有界槽中；
不能转授给第三方或通过普通消息伪造。

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

所有阻塞期限使用[统一单调时间域](time_domains.md)的绝对纳秒；0 表示只做立即配对检查，
`UINT64_MAX` 表示无限等待；有限非零值是绝对 deadline。先检查已就绪配对，再判定期限，
使 poll 在已等待接收者或已排队消息存在时可成功。唤醒、超时、关闭、取消必须原子登记并恰好完成
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

IP0 不为追求零拷贝开放任意跨进程映射。IP4 grant 使用内核单独分配并持有引用的
user pages，创建时可同步快照来源缓冲区（source=0 表示清零）；这不承诺零拷贝。
每 grant 最多 64 页，系统最多 16 个 grant/64 个活动映射，映射页计入 holder 的
user-page quota。初始 rights 为 read_mapping=1、write_mapping=2、manage=4、delegate=8；
delegate 只能缩权，grant badge 必须为零。grant delegate 在目标进程安装与源句柄相同的值，
`handle_out` 返回该值；目标已持有该值时返回 `resources`，不产生新句柄。映射只能 read 或 read_write，永不 executable；
grant 不授予任意物理地址、DMA 或 MMIO。使用者指定页对齐的高位 VM arena 地址；
映射预约同一匿名 VM reservation 集合，防止地址碰撞。活动 grant 映射期间，VM
commit/protect/decommit/unmap 对重叠区间返回 IPC busy。每个映射有单调 map_id，只有
同一进程持有对应 grant handle 才能 unmap。manage close 先整体检查所有进程的阻塞 pin，
若任何映射被 pin 则无副作用地返回 busy；否则同步撤销所有映射、handle 与 backing
references。exit/fault/成功 exec 撤销该 holder 的 map 与 handle；最后一个 handle 撤销时
销毁对象。单核 syscall gate 串行化 map/revoke 和页表变更，活动映射引用使 backing 页
在映射销毁前保持存活。仍须由 owner 在真实 guest 验证委派、跨进程共享、映射/关闭竞态、
资源回收和失败路径；feature query 与 SDK manifests 目前保持 unsupported。小消息与大块
数据走不同契约，不承诺大消息自动零拷贝；按实测选择阈值，阈值不是接口语义。

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

## qualification 与待项

IP1 已冻结并合入本页的 syscall 88 ABI、布局、错误、额度、生命周期与 feature 分组。
IP2/IP3 的真实客体资格已在 PR #111 的补验记录中完成：`tests/ipc_v1_guest.py`
同一构建运行 3 轮，覆盖并发 RPC、deadline/reply race、close wakeup、handle quota recovery、
notification merge/blocking、wait-set readiness/capacity，资源基线 `[129826,3,1]`
前后相同。四个 feature 因此由 query 与两个 SDK manifest 一并开放。快路径本次仍须由维护者
运行 IP5 性能/语义探针；资格记录与基准需区分已实测和待运行。

`bulk_grant_v1` 仍关闭，待 IP4 的共享映射授权、生命周期、竞争与资源 guest qualification
（grant 后端、SDK wrappers 与 `tests/ipc_v1_grant_guest.py` 见 PR #112，owner acceptance
记录以该 PR 为准）。实际 endpoint fairness 只要求 endpoint 内 FIFO，不宣称跨 endpoint
公平。fork 不继承、成功 exec 撤销 IPC v1 handles；failed exec 保持不变。安全性质与性能
指标矩阵见[实施路线](../plans/ipc_sel4.md)。
