# DHCP reply policy and absolute lease authority

本契约描述 `src/user/network/dhcp_policy.hpp/.cpp` 的有界回复校验与租约授权。
它不发送 DHCP、实现 ACD 或管理 socket。接入使用已锁定的 lwIP 2.2.1
`dhcp.c` / `acd.c`；主服务仍须证明真实收发、地址冲突检测、epoch 撤销及资源恢复。
本模块的 host 与目标对象编译资格不等于 DHCP 客体资格。

## 1. 可信配置与回复范围

`dhcp::policy` 是服务的可信安装/controller 配置，不能由网络回复或普通应用填写。
IPv4 数值统一用网络记法：`10.0.2.2 == 0x0a000202`；lwIP 存储字段需显式转换。
它限定一个连续子网掩码、主机租约范围、最多两个 server、两个可选 gateway、
两个 resolver，以及有限租期上限。列表不得重复，未用尾部必须为零，租约范围
不能包含这些基础设施地址。server/gateway 必须是该直连子网的主机。

首个 profile 仅支持 Ethernet/IPv4 的直连 DHCP。回复 UDP payload 最多 576
字节；`op=BOOTREPLY`、`htype=1`、`hlen=6`、`hops=0`、cookie、flags 保留位、
`giaddr=0`、XID、六字节 chaddr 和零填充均验证。源端口必须为 67，源 IP
必须在 allowlist 且等于 server identifier。client identifier 若出现，只接受
`type=1 + 本机 MAC`；不要求旧服务器回显该可选字段。ciaddr 只能为零，或在
续租/重绑定中等于当前地址。

校验上下文来自服务持有的事务和本机 MAC，不能从收到的报文反推：

| 当前 phase | 可接受消息 | server/address 关系 |
|---|---|---|
| selecting | OFFER | allowlist 内服务器，地址在租约范围 |
| requesting | ACK / NAK | 选定服务器；ACK 必须等于请求地址 |
| renewing | ACK / NAK | 原服务器；ACK 必须等于当前地址 |
| rebinding | ACK / NAK | allowlist 内服务器；ACK 必须等于当前地址 |

OFFER/ACK 必须完整给出有限 lease 和精确匹配的 subnet mask。启用网关策略时
必须包含一个已获准的 router；未启用时不得携带 router option。resolver 同理，
启用时接受一至两个 allowlist 成员，并保留顺序。NAK 的 yiaddr/ciaddr 必须为零，
且不能同时携带地址配置或租约定时器。换地址必须通过失效后重新获取并执行 ACD，
不能借 renewing ACK 直接换成未探测的新地址。

每个 TLV 都检查长度，所有非 PAD/END option 均禁止重复；必须有 END，后续
只能为 PAD。mask 必须在 router 前。未知 option 只按边界跳过，不获得配置权。
option overload、拼接、relay、静态/classless route、多个 router 的报文在此
profile 不受支持。其余 BOOTP boot-server/name/file 字段不会成为网络配置。
这些是有意收窄的可测试 profile，不是所有 RFC2131/2132 服务器的兼容性承诺。

回复校验的失败不改变输出；有效配置在完整校验后一次复制。allowlist 是服务
的地址授权边界，DHCP 本身没有为这些报文提供密码学认证。应用出站 ACL 由
服务另行执行，租约地址、router 或 resolver 改变不能扩大应用授权。

## 2. 实际 REQUEST、绝对时间与 ACD

`lease_clock::start(now, deadline)` 只接受未来的有限获取期限，最长 60 秒。
调用方负责有限退避与停止；重试不能把该次获取的总期限不断向后移动。
只有 disabled/failed/expired 状态能开始，不能静默替换已发布地址。

`note_request_sent(phase, xid, now)` **仅在实际 DHCPREQUEST frame 成功提交给
驱动后**调用。调用驱动前采样时间，只有提交成功才记录该采样值；不能把本地
发送调用的耗时加到租约后面。每个未完成 XID 的第一次成功发送决定时间锚点。重传及同一
事务由 renewing 转为 rebinding 保留最早时间，避免迟到回复被当成较晚请求的
回复而延长租约。成功绑定后开始新续租必须生成新的 checked-random XID；
继续使用上一有效租约的 XID 被拒绝。随机失败不能回退到固定值或旧 XID。

`accept_ack` 要求与已实际发送的 REQUEST 匹配，计算 candidate，尚不发布地址。
全部租约记录保留 request_sent、T1、T2、expires 的绝对单调纳秒。默认 T1 为
租期 1/2、T2 为 7/8；先扩大到 64 位并拆分比例运算，保留短租约的分数秒。
显式 timer 是秒；必须满足 `0 < T1 < T2 < lease`。租期零与 `0xffffffff`
无限值都拒绝，最大有限值为 `0xfffffffe`，还受可信 profile 上限限制。
加到发送时刻之前检查溢出，恰好等于 `UINT64_MAX` 的有限 expiry 可以表示。

ACK 到达时租期已耗尽、原有效租约已过期，或获取期限已到，均不得复活旧地址。
`accept_nak` 同样核对已实际发出的事务；成功后同步失效全部 request/candidate，
并返回是否要撤销此前已发布 epoch。无实际发送的事务不能凭 NAK 撤销已有租约。

首次地址必须经过 lwIP ACD。`approve_address(candidate.generation, now, changed)`
只在 ACD clear 回调后调用；续租保持原地址时可以复用已有 ACD 结果，但仍须
经过此发布入口。generation 跨停止/获取保留，旧 ACD 回调不能批准另一份候选
租约。ACD 完成时再次检查期限。重复 approve 失败，没有第二次发布。

同一地址、mask、gateway 和有序 resolver 列表的续租只更新租期，不要求提升
有效配置 epoch。server 改变也不单独改变配置 epoch，但后续续租必须使用新的
issuer。路由、mask 或 resolver 改变通过 `configuration_changed` 显示，调用方
必须在新配置可用于流量前撤销旧连接、解析事务与缓存。

## 3. 每轮的授权顺序

`advance(now)` 必须在每轮 RX、应用 TX、接收 ACK/NAK 和 lwIP timer 之前执行。
expiry 优先于 T2，T2 优先于 T1；长暂停后的第一轮直接执行已到期动作。T1
输出单播 renew，T2 输出广播 rebind，事件各发一次。丢包和重发都不改变有效
租约的 expires。`usable(now)` 即便尚未调用 advance，也在精确 expiry 拒绝使用。
时钟倒退会撤销授权并进入可见失败状态。

| 已锁 lwIP / XOS 位置 | 接入必须执行的操作 |
|---|---|
| `dhcp_recv`，`dhcp_parse_reply` 之前 | 将完整有界 pbuf 复制进固定缓冲，先检查时间，再 validate_reply；ACK/NAK 再进 lease_clock，失败包不能进入原解析器 |
| `lwip_stack::link_output` 的成功 DHCPREQUEST 发送 | 验证 IP/UDP framing 与实际 message type 后 note_request_sent；ARP 排队、分配成功或调用 udp_send 不是实际发送证据 |
| 新的 `dhcp_renew` 事务 | checked entropy 生成新 XID；重传和 renewing→rebinding 保留该事务 XID |
| `dhcp_check` / `dhcp_conflict_callback` / `dhcp_bind` | 初次或新获取先 ACD；把 candidate generation 保存到回调；approve 成功后才运行 netif_set_addr 并发布配置 |
| `dhcp_handle_ack` 的 rebinding 成功路径 | 将已验证 server ID 写回 `dhcp->server_ip_addr`，后续 T1 单播到新 issuer |
| `lwip_stack::poll`、应用 send 与输入回调前 | advance；expiry/clock failure 时先禁止旧地址应用流量并同步撤销 core epoch，再清地址并停止旧 DHCP/ACD |
| `dhcp_handle_nak` / ACD 冲突 / link loss / stop | 取消候选与未完成 REQUEST；已发布地址先撤 epoch；重新获取仍受本轮总期限约束 |
| `dhcp_coarse_tmr` / 原 lease-used 计数 | 不再用向上取整的 coarse 时间授权地址；不能在绝对 expiry 后先跑一次旧地址 TX/RX |

本表是接入要求，**不是声称这些 hook 已在本模块接入**。lwIP 的 fine timer、
有界重发与 ACD 仍负责协议包；绝对 lease_clock 是地址授权的唯一期限来源。
失效事件必须同步传给 service_core，先取消 DNS ticket/cache 与旧连接，再公开
新地址或新 resolver；旧 epoch 的结果不能交付。自动重新获取可以继续，但单次
获取失败需要可查询状态，不能持续无限重试或启用 AutoIP 兜底。

## 4. 验收与依据

`tests/net_dhcp_policy_host.py` 用原实现执行 14 组语义测试和 20,000 次有界报文
突变，并编译 x86_64-elf freestanding 对象。相同测试通过 ASan/UBSan；此处的
可控时钟用于精确边界，未冒充真实客体租期或 ACD。该模块没有声称 lwIP 接入、
真实 DHCP server fixture、socket/DNS epoch 回收、硬件或多接口资格。

协议依据为 [RFC2131 §4.4.1、§4.4.5](https://www.rfc-editor.org/rfc/rfc2131.html)、
[RFC2132 §3、§9](https://www.rfc-editor.org/rfc/rfc2132.html) 与
[RFC5227 §2](https://www.rfc-editor.org/rfc/rfc5227.html)。XOS 完整收窄范围与
组合验收仍见 [N4 提案](network_n4_v1_proposal.md#6-dhcp-租约)。
