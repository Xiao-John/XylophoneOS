# 有界 DHCP 服务安装 profile

本契约把 [严格回复与租约时钟](dhcp_lease_authority.md) 接到生产
`lwip_stack`、lwIP 2.2.1 DHCP/ACD、Net2 与普通 Xsh supervisor。
是否取得真实客体资格以本轮工作记录中的结果及 source-bound receipt 为准；
单独编译 helper 或仅通过 host 用例不构成该资格。

## 安装授权

构建参数 `--net-dhcp-profile <json>` 只允许独立输出目录与普通 Xsh supervisor。
必须提供 hash 锁定的 `XOS_LWIP_SOURCE_ARCHIVE`。它与 static resolver、DNS
probe 和其他替代 supervisor profile 互斥。没有该参数时，现有默认构建及静态
网络行为保持原定义；启用它后，网卡先以全零 IPv4 配置启动，没有静态地址、
AutoIP 或失败后恢复静态配置的路径。

JSON revision 1 必须精确包含如下字段；未知字段、重复键、超长输入、布尔值
冒充整数及非规范 IPv4/CIDR 均拒绝：

| 字段 | 边界 |
|---|---|
| `pci_instance` | `1 + PCI BDF`，1–65536 |
| `subnet` | 一个连续 IPv4 子网，最多 /30，保留 network/broadcast |
| `addresses` | 子网内两端闭合的租约主机区间，不包含基础设施地址 |
| `servers` | 1–2 个子网内获准 DHCP issuer |
| `gateways` | 0–2 个子网内获准 gateway |
| `resolvers` | 0–2 个获准 unicast resolver；每次 ACK 最多发布一个 active resolver |
| `max_lease_seconds` | 1–4294967294；不接受无限租约 |
| `acquisition_seconds` | 1–60；包括所有获取重试和 ACD/backoff |
| `egress` | 独立的最多 8 条地址/协议/端口授权，见 [出站契约](network_egress_policy.md) |

编译器生成只读 `installed_dhcp_policy`、获取预算和 `installed_egress_policy`。
DHCP 报文、DNS 答案、普通应用和 Net2 `configure` 均不能改写这些安装授权。
DHCP 模式下 controller 的静态 resolver 开关返回 `unsupported`；普通应用仍返回
`denied`。配置与租约查询只读，不赋予设备、raw Ethernet 或策略变更能力。

## lwIP 接入与时间授权

第五个受 hash/前后像约束的 lwIP patch 在原生服务 profile 下启用：

- 原 `dhcp_recv` 在调用宽松的上游 option parser 之前，先复制完整、有界 pbuf，
  使用当前事务、真实 MAC、已选择 issuer 和安装 allowlist 做严格验证。
- SELECTING 的上下文始终清零 selected server/requested address，不能继承
  上次冲突后仍留在 lwIP 结构中的 OFFER issuer。
- 上游 DNS 自动配置关闭。只有通过 lease 发布入口的 resolver 能进入 DNS
  adapter。一次 ACK 携带多个 DNS server 超过该首版服务的 active resolver
  表达范围时拒绝，不静默截断。
- 上游 coarse lease timer 不再决定有效期。服务以绝对单调纳秒授权 T1、T2、
  expires；细粒度 lwIP timer 只做有限重传、ACD 和 RFC backoff。
- 新续租使用 checked entropy 的新 XID；同一事务的重传和 T2 broadcast rebind
  保留 XID。rebinding ACK 可来自另一个已批准 issuer，后续续租转向该 issuer。
- `link_output` 在 driver 接受 DHCPREQUEST 后记录调用前的单调时刻。只入 ARP
  待发队列不算发送；ACK 接收、ARP 解析、重传和 rebind 均不能向后延长既有
  事务的时间锚点。driver backpressure 不消耗一个“已发送请求”身份。
- 最大有限租约的比例和 coarse 换算使用不会溢出的拆分算术。授权层保留
  完整 64 位绝对纳秒，不依赖上游缩窄后的分钟计数。

首次地址在 lwIP RFC5227 ACD clear 之前只作为 candidate。冲突发送 DECLINE，
至少等待上游约十秒 backoff 后重新 DISCOVER，继续使用同一获取总期限。
未发布候选到期或获取预算耗尽后停止，不以循环 start 续期该预算。
已发布租约被 NAK、冲突或绝对到期撤销后，允许一次新的独立、有界获取。
client/共享 UDP PCB 分配失败时，上游无法启动；adapter 安全解除残留 ACD
节点，每 500ms 最多重新启动一次，仍使用原获取绝对期限，并记录 start/failure
计数。DISCOVER frame 的分配或 driver backpressure 由上游 fine timer 重试，
同样受原绝对获取期限约束；不通过阻塞 sleep 或重新设置预算重试。时钟错误/倒退关闭授权并结束服务；
随机失败不能回退到旧 XID 或固定种子。

## 配置 epoch 与退役顺序

普通应用连接、DNS cache/ticket、尚未发出的 IPC reply 与 ARP deferred IP
packet 都属于一个有效配置 epoch。首次发布、配置改变或撤销时：

1. 先关闭应用/DNS IPv4 发送门；物理网卡尚未接收的旧 IP 帧均不能再发送。
2. 清掉 lwIP ARP 待发队列并终止旧 socket；清 DNS 订阅及缓存。
3. 关闭四个普通应用槽的两端 IPC endpoint，并清除 pending/delivered reply 状态；
   core detach 同时撤销 handle、ticket 和 session generation。
4. 提升 config epoch，发布完整新 tuple 或完整零 tuple，重新设置 DNS adapter。
5. 新地址只有在 lease approve 成功后才能写入 netif 并开放流量。

保留 controller 专用第五槽，controller 能观察获取状态并停止服务。
相同 address/mask/gateway/resolver 的续租不改变 epoch；只更换获准 DHCP issuer
同样不改变应用配置 epoch。NAK 后重新获取不同地址产生一次零配置 epoch，
再产生一次新地址 epoch。旧连接与旧 DNS ticket 在新会话中保持 `closed`。

退役动作在安全的外层 poll/API 边界执行，不从活动中的 DHCP UDP、ARP 或 TCP
发送回调释放其 PCB。回调和实际 TX 边界先关闭授权并标记退役；下一安全边界
先退役再处理输入/回复。服务循环在取到请求后、发送 pending reply 前、dispatch
后均刷新时间并核对 generation，避免长暂停或收包跨过期限后输出旧 reply。
已经成功提交给物理设备的历史帧无法撤回；它们的授权发生在实际提交时刻。

## Net2 只读 lease snapshot

wire version 2 与原 64-byte message header 不变。新增操作 18 `lease_status`，
无 object、地址、端口、payload 或 flags 参数。支持 DHCP 的服务返回固定
96-byte revision 1 snapshot；没有该模式的服务返回 `unsupported`。
已有 socket capability flags 不变，旧 capability 客户端可以继续使用。

| 字段 | 意义 |
|---|---|
| `state` | 0 disabled、1 selecting、2 requesting、3 checking、4 bound、5 renewing、6 rebinding、7 expired、8 failed |
| `reason` | 最近失效原因：0 none、1 NAK、2 conflict、3 link lost、4 stopped、5 expiry、6 acquisition timeout、7 clock failure |
| `epoch` | 与配置快照相同的配置代际 |
| `request_sent / t1 / t2 / expires` | 当前已发布租约的绝对单调纳秒；不可用时全零 |
| `server / address / mask / gateway / resolver` | 当前已发布 tuple；不可用时全零 |
| `accepted / rejected / conflicts` | 饱和 32 位诊断计数；不是认证或重放防护凭据 |
| `start_attempts / start_failures` | 饱和的启动尝试/失败计数；初次 DISCOVER 压力不会隐藏为已运行的 client |
| `reserved` | 必须为零 |

原 Net2 `configuration` snapshot 增加 `mode=dhcp (2)`，未获得地址时 tuple
全零。原生 SDK 检查 revision、长度、保留字段、状态范围、时间严格顺序、
unicast 地址、掩码、gateway 关系及状态/tuple 一致性。内核报告旧 IPC endpoint
已消失或 peer broken 时，SDK 返回 `closed`、清 reply 和连接状态，不重发已经
提交的业务请求。只读监测器可显式以同一已认证 service PID 重新建立会话。
较高层 `net2::client::resolve_ipv4` 同时接受有效 static 与 DHCP 配置，且要求
已发布地址和 active resolver；获取中或失效后的 DHCP 不创建解析 ticket。
其返回值仍绑定原配置 epoch/TTL，DNS 答案不扩大 application egress。

## 当前范围

这是显式安装的直连 Ethernet/IPv4 DHCP profile。它没有 IPv6、relay、持久化
INIT-REBOOT、option overload、classless routes、多个 active resolver、自动
热插拔/link-loss 通知或通用多网卡策略。allowlist 限定地址授权，DHCP 未提供
密码学服务器认证。支持的边界必须通过该轮真实 peer、packet capture、native
SDK、host sanitizer 与资源恢复证据核对；不从 helper 的历史结果推导客体通过。
