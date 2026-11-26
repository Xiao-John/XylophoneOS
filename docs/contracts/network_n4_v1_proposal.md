# N4 配置与名称：原生服务契约提案 v1

2026-11-25。状态：**proposal / activation_blocked**。基线为
`2baed871f9d233a08258047b09863c991116dd7e`，已包含 N2/N3 的会话隔离、TCP close、
IPC exec 撤销和 [多应用客体验收](../work_log/ca46b580_network_multi_application_qualification.md)。
本提案不更改 shared 枚举、已分配 ABI 或生产 DNS/DHCP 开关。候选操作号须经主审、
登记、共享头与 SDK/服务实现同步后才能调用。

C0 完成接口和生命周期设计、锁定 lwIP 源码审阅与包级 audit，记录八个启用门槛失败，
见 [81c7b902](../work_log/81c7b902_n4_configuration_name_contract.md)。D1 已完成
端点/直接答案校验与有界熵后端：43 项真实帧宿主用例及 ASan/UBSan、原 N2 的
25+2 项普通与 sanitizer、preview 工具链的28对象编译通过，见
[4e29c6b1](../work_log/4e29c6b1_network_dns_hardening.md)。D2 的私有取消、正缓存期限与
重传期限已经在专用客体走通。服务 IPC 票据、配置、错误分类和 DHCP 继续各自验收。生产
DNS/DHCP 保持关闭。[私有客体记录](../work_log/c4201d53_network_dns_lifecycle_guest.md)

## 1. 权限与兼容

`net_service` 继续是唯一持有设备与 lwIP 的用户态进程。使用已有 net2 认证会话和
sys4/5、84–86；没有新的内核名称解析、DHCP 或 socket syscall。普通进程只能请求
解析与查询当前配置，不能选择上游 DNS、发送 DHCP、改地址/路由或取得 raw frame。
所有配置写入由 bootstrap controller 身份授权，不能相信消息里自报的 PID。

默认仍为确定性静态 `10.0.2.15/24`、网关 `10.0.2.2`。DHCP 必须显式选择；失败
保持 acquiring/failed，不自动退回静态地址。DNS 答案不会授予连接权限：现有
TCP/UDP 对 `10.0.2.2` 的目的地址限制仍在 PCB 分配前执行。放宽出站策略属于
独立审阅，不能由 DNS、DHCP route 或服务名绕过。

DNS/DHCP 控制流量使用服务私有 PCB 与单独定额；普通应用不能通过端口号伪装成
控制请求。DNS 的网络数据未经 DNSSEC 认证，DHCP 的本地网络配置也未经密码学
认证；可信 controller 的 resolver/网段白名单与最终 TLS 主机名/证书检查分别保留。
首次 profile 不接收 DHCP 提供的搜索域来隐式扩展用户查询。

原 op1–9 的报头、information 32 字节回复、错误语义和额度保持兼容。
新 SDK 先发送无负载的 configuration 探测；旧服务返回 unsupported 后停止，
不降级 raw。新操作的失败回复继续无有效负载；细分 DNS 错误只用于新操作。
现有普通 TCP/UDP 客户端不必理解新 DNS 错误。

## 2. 原生接口与候选线操作

保留 v2、64 字节报头、1024 字节负载。10–14 在 2.1 节登记为显式静态解析预览。
表中 DHCP 参数、多个 resolver 等后续资格继续按本计划推进。所有无关 header 字段为零，
SDK 逐操作校验返回形状。

| 候选操作 | 请求与权限 | 成功结果/生命周期 |
|---|---|---|
| 10 configuration | 所有已认证会话；object/负载为零 | 固定版本的配置快照：capabilities、mode/state、epoch、有效地址/掩码/网关、最多两个 resolver、租约绝对期限和实际用量 |
| 11 configure | 仅 controller；显式 static/dhcp/disabled 配置、resolver 白名单 | 完整校验后接受新配置，返回新 epoch；DHCP 的接受与获得租约分别显示 |
| 12 resolve_start | 普通会话；IN/A、显式长度名称、绝对 deadline | 分配不复用的 ticket；cache 命中仍走相同所有权模型 |
| 13 resolve_result | 仅 ticket 所有者；自身请求 deadline 不延长原查询 | pending 返回 would_block；完成时返回一个 IPv4 地址及保守 expiry，或具体解析错误，然后消费 ticket |
| 14 resolve_cancel | 仅 ticket 所有者 | 移除订阅并释放所有权，返回0；已释放 ticket 返回 closed |

SDK 只使用固定宽度整数与原生错误域，接口形如
`resolve_start(name, length, deadline, ticket)`、`resolve_result(ticket, deadline, result)`、
`resolve_cancel(ticket, deadline)`。一个 client 仍由调用者串行使用；等待采用
现有绝对单调期限，不能在 service_loop 内同步阻塞某应用直到 DNS 完成。
`resolve_result` 的一个地址只是显式的 single-address 子集，不能伪造完整 RRset。
后续多个地址必须有计数/边界契约，不把无关记录拼入返回值。

需区分的错误为：NXDOMAIN、NOERROR/NODATA、临时解析失败、REFUSED、截断且无
TCP 回退、网络配置失效，以及既有 invalid/resources/timeout/closed/io/unsupported。
等待超时、服务故障或缺少响应均不能转换成名称不存在。底层 NULL callback 没有
这些信息，必须先扩展真实 resolver 结果，再映射原生错误；不能在 SDK 猜测。

成功消费结果和收到结果是两件事。回复丢失时客户端关闭会话，服务沿既有500ms
回复期限回收；调用方可显式开始新的查询，但不能重放旧 sequence。DNS 查询本身
没有业务写入副作用，重新查询仍受新的 deadline、定额和缓存规则约束。

### 2.1 N4 静态解析预览线格式

同一 `net2` 名称和 `version = 2`。旧 SDK 可继续使用 1–9。预览能力由 10 的零对象、
空请求探测，旧服务正常返回 `unsupported`。生产镜像保持该行为。开发镜像显式构建，
其 controller 在认证通道启动时看到禁用状态，并可用 11 启用固定 `10.0.2.2:53`。
预览启停只控制 resolver，接口和现有 TCP/UDP 目的地址授权保持现状。

| 操作 | payload 布局和校验 |
|---|---|
| 10 configuration | 成功 48 字节。偏移 0/4 为 `u32` revision=1、mode，8 为 `u64` epoch，16/20/24/28/32/36 为 `u32` capabilities、地址、掩码、网关、resolver、总票据数，40 为 `u64` 保留零。capabilities 的 bit0 表示直接 IN/A。禁用时 resolver 为零。 |
| 11 configure | controller 请求 16 字节。偏移 0/4 为 `u32` revision=1、mode，8 为 `u64` expected_epoch。模式 0 禁用，1 启用静态 resolver。成功返回同 op10 的快照。epoch 由 1 开始，写入成功递增。与当前 epoch 不符返回 `config_changed`，票据或连接未退休返回 `resources`。 |
| 12 resolve_start | 零对象，1–254 个未加结尾 NUL 的 ASCII 主机名字节。折叠 ASCII 大小写及一个末尾点，规范名上限 253 字节，拒绝歧义纯数字名。请求的绝对 deadline 也是票据截止点。成功空负载、对象为非零票据。 |
| 13 resolve_result | 对象为票据，请求空。成功 24 字节。偏移 0 和 8 为 `u64` epoch、绝对到期纳秒，16/20 为 `u32` IPv4 及保留零。到期等于零只表示本轮 TTL0 可使用，不可缓存。 |
| 14 resolve_cancel | 对象为票据，请求和成功回复均为空。 |

约定 `-211` 名称不存在、`-212` 无直接 A 数据、`-213` 服务器失败、`-214` 拒绝、
`-215` 截断、`-216` 配置代际不匹配、`-217` 正结果在交付前到期。新错误只用于上述
扩展请求，全部为零负载。请求自身超时由原错误 `timeout` 表示，pending 为
`would_block`。票据标识、配置代际和认证会话代际非回绕。不允许使用特殊对象或保留
字段申请控制权限。

### 2.2 静态安装 profile

`--net-static-profile` 接受安装维护者提供的 revision 1 JSON，字段为 `revision`、
`pci_instance`（1 + PCI BDF）、`resolver`（规范 IPv4）。安装镜像绑定配置文件的
SHA-256，并将解析出的网卡和固定 resolver 编入受信用户态启动者和服务的启动映像。
resolver 限于 `10.0.2.0/24` 的单播邻居，并排除 guest 自身地址。TCP/UDP 的应用目的
地址授权独立执行。profile 与 `--net-dns-probe` 分离，选用时须指明独立输出目录。

普通 xsh 在恢复门开放后启动 profile 的网卡，创建服务已用的 NIC 授予和私有启动通道。
服务从 epoch 1 发布静态配置。普通进程可读取快照和使用解析票据。安装系统重启后采用
同一 profile。旧应用仍可使用 op1–9。安装 profile 使用 `.2` 以外的 resolver 时，需使用
能校验静态子网快照的新 SDK，旧预览 SDK 仅接纳 `.2`。

受信 xsh 对每次普通启动按当时选定的服务生成 `XOS_NET_SERVICE_PID` 环境快照。dash
沿普通环境传递它。ClarkE 用户用 `--network` 选择该绑定，连接时核对两个端点的内核
对端。环境值属于调用者的启动选择，无额外 IPC 或设备权利。普通镜像的启动环境无该
变量。服务通过现有 stop/start 更新后，重新从 xsh 或新启动的 dash 打开客户端以获取
新快照。旧客户端和旧 shell 继续持有旧绑定，连接拒绝后需重新启动。原显式 PID 模式
供现有开发调用使用。

内核本次启动内的 PID 高水位单调增长，耗尽即拒绝分配。服务退出时撤销旧端点，替换
服务取得新的 PID。不同冷启动中的数字可以相同，快照仅适用于它出生的启动实例。
PID 核对证明当前端点的进程身份，无法证明同一进程的应用映像从未 exec。正式服务由
受信 xsh 启动、持有设备授予并按退出/新建方式更新。现场可改配置、跨独立登录会话的
绑定交付、DHCP 租约和证书分发有独立验收门。

## 3. 定额与公平调度

初始额度为可评审的有限 profile；若实测需调整，必须更新 manifest 与资源证据。

| 资源 | 设计上限与处理 |
|---|---|
| 普通会话/控制会话 | 复用4+1；controller 不占普通 resolver ticket |
| 查询 ticket | 每普通会话1个，全局4个；完成未消费也占用，不能挤占 TCP/UDP 的八个 handle |
| 上游 DNS 事务 | 全局4个；同 epoch/name/type/class 合并网络事务，保留独立订阅与 deadline |
| 解析状态/缓存 | 首个后端采用4个统一槽，pending 不被淘汰；完成项可淘汰，禁止上游和适配层各自保留一份不一致 cache |
| DNS 端口 | 最多4个，每个独立未决事务使用独立随机端口；额度耗尽返回resources，不静默复用另一查询端口 |
| UDP PCB | 保留原8个应用额度，DNS最多4个、DHCP1个另计；同时启用需要至少13个实体 PCB 并实测池耗尽 |
| 名称 | 规范化后最多253字节、单label最多63；可接受一个末尾点，拒绝嵌入NUL/空label/非法编码 |
| 消息 | 首个DNS profile：单question、UDP最多512字节、IN/A；解析有界，超长/压缩循环不会扩大工作量 |
| 重试 | 每 resolver 每次逻辑查询最多初发+2次重传，最多2个配置resolver；总期限仍最多30s |
| 请求速率 | 每会话每秒最多4次 start，全局每秒最多16次；按单调域令牌额度，拒绝时无PCB/报文副作用 |
| 主循环 | 保留每轮每会话1条IPC、至多64个NIC帧；每轮最多4个DNS状态推进，不能追赶无界定时器工作 |

rate/资源拒绝必须保持其他应用及 controller 可用，实际计数可查询。不得用增加
全局 PCB 池掩盖取消后仍持有对象的泄漏；释放后再次填满配额属于验收项。

## 4. 配置代际与撤销

采用两个不同身份：现有 session generation 保护应用槽位，新的 config epoch
保护有效网络配置。查询上下文同时保存 session generation、ticket 和 config epoch。
三个计数均不回绕复用；耗尽时拒绝新的分配。

同一 NO_SYS 调度线程拥有 resolver 状态。回调不能只存可复用槽的裸指针；交付前
比较三重身份。cancel、会话关闭、reply/idle timeout、revoke、exit/exec/fault 都必须
注销该订阅。最后一个订阅消失时取消网络事务，清除 callback 并关闭私有 PCB；
不把无人等待的事务保留到任意未来。共享查询中取消一个应用不能取消另一个应用的
有效订阅，也不能将两者的回复缓存混用。

ticket 状态为 pending、ready 或 failed，最后由 result 消费、cancel 或 session
回收转为 retired。原查询 deadline 到达时立即注销网络订阅、释放无主 PCB，并将
ticket 设为 failed/timeout；其少量结果元数据仍占该会话唯一 ticket，直到消费、
cancel 或既有60秒idle回收。后到的有效包也不能把它改回ready。`resolve_result`
请求自身的过期只返回该次RPC的timeout，不消费仍有效的查询；有效RPC读取到已
超时查询则消费该terminal结果。这样调用方能观察真实timeout，资源寿命仍有界。

configure 先验证完整参数、权限和可用状态，任何拒绝保留原配置/租约/cache。
初期仅在没有应用连接和 resolver ticket 时接受显式重配置；成功后递增 epoch、
清空旧 cache，并原子公布新快照。不能先调用 dns_setserver 再让旧回调继续命中。

DHCP 自动续租维持同一有效地址/路由/resolver 时可以更新期限；地址、路由或
resolver 集合变化必须提升 epoch。地址/路由失效时先停止应用 TX/RX、关闭普通
IPC 会话和连接、取消查询，再应用新配置；controller 查询通道保留。DNS-only
变化至少取消旧解析事务、清空 cache，旧epoch结果不可交付。失败中的已发送数据
仍可能到达远端，客户端不会获得透明重连或事务回滚承诺。

正常 stop 注销名称、取消 resolver、停止 DHCP、关闭 PCB，再执行现有设备 reset。
服务崩溃后旧 PID/IPC 全部失效，新进程重新申请配置和租约，cache 不跨进程持久化。
DMA quarantine 沿现设备契约；当前强杀后依赖平台重启恢复，N4 不新增隐式救援口。

## 5. DNS 校验、缓存与随机化

### 5.1 名称和应答

首个profile是ASCII DNS主机名；大小写归一，末尾点归一，显式拒绝尚未提供的
IDNA转换、搜索后缀、mDNS、AAAA和任意RR查询。严格四段十进制IPv4字面量由SDK
现有数值地址路径处理，不当作网络查询来消耗额度；不接受歧义八进制/缩写地址。

在解析和写入cache前，必须匹配响应源地址/端口、目的本地地址/本次PCB端口、
transaction ID、QNAME、QCLASS、QTYPE和当前epoch。匹配错误的报文丢弃，保留
原事务等待正确响应。见 [RFC5452 §§9.1–9.2](https://www.rfc-editor.org/rfc/rfc5452)。
QR必须为响应、opcode必须为QUERY、question数必须为1；TC置位时不使用现存A答案。
未实现DNS TCP回退时返回明确truncated错误。

A记录的owner必须匹配请求名，或属于从请求名出发且完整验证的CNAME链；链最多8跳，
检测循环，链中所有TTL共同限制结果寿命。只支持直接A的首个子里程碑可明确拒绝
CNAME，不能跳过owner后接受任意A。压缩指针、label长度、section计数、RDLENGTH、
越界与总工作量全部校验；authority/additional中的无关A不能提升为答案。

### 5.2 缓存

缓存键含 config epoch、规范化名称、class/type与结果类别。正缓存上限300秒，
实际期限为相关有效RR最小TTL与本地上限的较小值；TTL0只用于当前订阅，立即清除。
对外 expiry 不超过实际有效期。按实际收到有效应答时的单调时间建立绝对期限，
在每次lookup和交付前重新检查；一次poll停顿不能把2秒TTL延长为更多秒。

NXDOMAIN/NODATA分开处理，只有验证过的SOA可给出负缓存期限，上限60秒，取
SOA TTL与MINIMUM的较小值；没有可用SOA时不制造名称不存在的缓存寿命。
参考 [RFC2308 §5](https://www.rfc-editor.org/rfc/rfc2308)。临时解析失败另作有界
短期抑制，首个profile为1秒，仍返回真实失败类别；用户主动cancel或过短的单个
订阅deadline不污染其他订阅/共享cache。后续退避至多300秒，保持
[RFC9520 §3.2](https://www.rfc-editor.org/rfc/rfc9520)的失败缓存边界。

配置变更清空全部旧epoch cache。cache命中和剩余TTL只说明解析状态，不授予
网络访问权；信息接口不枚举其他应用查询名。首次profile允许共享公开DNS结果和
有界时序可观察性，不能用于秘密应用数据的共享；如需私有resolver视图，应按
视图ID加入cache键并单独分配额度。

### 5.3 熵与资源失败

transaction ID覆盖16位取值，源端口从当前可用的1024–65535范围不可预测选择。
每个新逻辑网络事务重新选择，不能用时钟、固定值、进程PID或计数器替代sys63。
同时未决事务使用不同端口；ID与端口冲突检查各最多32次抽取，超限返回resources。
任何熵失败返回真实io并停止本次分配/发送，不能先发固定ID数据包再在poll末尾报错。
失败前已分配的PCB/pbuf必须释放，服务既有fatal状态按统一shutdown路径处理。

原始锁定上游的随机端口与ID循环没有次数上限，C0 已复现与旧XOS错误返回0组合后
无法返回。D1 通过来源补丁与可返回错误的内部熵接口完成该处加固；原归档和 C0
证据保留。每项准入的失败会回收该项PCB，耗尽时保持其他查询的独立端点。

### 5.4 D1 当前实现边界

D1 仅在测试配置编入 DNS。IPv4 接收同时核对当前接口单播目的地址、该查询实际
PCB、server源地址与53端口、ID和完整question；广播/多播不能经ANY绑定绕过。
完整answer section验证后才发布首个IN/A地址，所有owner须严格匹配query。
压缩仅允许指向报文内先前位置，最多16次指针跳转、展开名最多255线字节；保留
大小写不敏感匹配，并严格区分label边界。直接A子集接受多条同名A并返回首条；
CNAME、未知类型/class、畸形或截断答案丢弃，查询继续等待。

TC当前也是丢弃并保留pending；把截断、NODATA/NXDOMAIN等转换为准确对外错误，
属于D2。该阶段还须完成末尾点规范化、512字节准入、绝对TTL/epoch及结果寿命、
独立订阅取消、全局fatal/stop时注销所有既存DNS回调和PCB。D1只验证失败的新准入
与已完成事务的回收；既存pending的全部退出/取消生命周期由D2/D3验收。

内部`DNS_RANDOM_TRY`区分成功值0与熵错误；端口/ID分别最多32次抽取，遇熵错误
立即返回`ERR_IF`并锁存stack io，碰撞预算耗尽为`ERR_USE`、无PCB为`ERR_MEM`。
在返回`ERR_INPROGRESS`前失败时不调用callback、不发查询，回收本次独占PCB。
普通网络适配器在fatal锁存后拒绝link_output，防止已存在UDP连接继续出帧。
这是内部lwIP错误域；候选op10–14与新原生错误数值仍未分配。

### 5.5 D2 私有生命周期诊断

`--net-dns-probe` 构建隔离的 Xsh 诊断镜像。`net-dns-probe 41` 使用受信 Xsh
原有设备授权启动 `net_service`，在同一个 VirtIO、lwIP 与 sys63 链路上向固定的
`10.0.2.2:53` 查询。该模式无应用 IPC 注册，解析和配置入口随诊断 profile 编入，
普通构建及其共享协议沿用原有配置。

私有 resolver loop 可以取消指定 callback/context。如果其他订阅仍在等待同名结果，
它们继续使用原 PCB。取消最后一个订阅与清空会释放对应 PCB，并丢弃待用回调。
清空同时去掉已完成缓存和 resolver 地址。具名缓存用实际应答时的 64 位单调时间，
多个直接 A 记录共同取最短 TTL，正缓存上限 300 秒。每次查询检查绝对期限。重传保留
现有有限次数，并从当前事务发送时点计算下次重传，已过期的维护 tick 不提前重传。
该诊断只验证直接 A 的功能闭环，票据身份和配置 epoch 仍按共享服务设计验收。

## 6. DHCP 租约

复用 lwIP 2.2.1 DHCP + ACD，配置属于服务，不授予普通应用UDP67/68访问权。
初次启用需检查并编入 `dhcp.c` 与 `acd.c`；只编译UDP不足以提供租约能力。
状态至少区分 disabled/static、selecting/requesting/checking、bound、renewing、
rebinding、expired/failed。ACD完成前不把OFFER/ACK地址作为可用地址发布。

每个有效租约记录 server ID、地址/掩码/网关、resolver集合，以及 request开始、
T1、T2、expiry 的64位绝对单调时间。使用原DHCPREQUEST发送时间加服务端期限，
避免ACK延迟把租约往后延长；成功续租按该次请求时间更新。缺省T1=租期1/2、
T2=租期7/8，并验证 `0 < T1 < T2 < expiry`。秒转纳秒、加法、默认比例计算均
检查溢出。首个profile只接受有限租约；无限租约需独立表示，不能将0xffffffff
误算成零或有符号负数。依据 [RFC2131 §4.4.5](https://www.rfc-editor.org/rfc/rfc2131)。

先在每轮接收和应用发送前检查绝对expiry。过期时立即禁止使用旧地址、取消解析、
关闭普通会话/连接并回到获取状态；调度长暂停后的第一轮也执行。不能只依赖默认
60秒coarse计数或其向上取整来决定短租约有效性。T1单播原server，T2进入广播
rebinding；丢失续期回复保留地址仅到原expiry，不能把重发当作续租成功。

先核验BOOTP/DHCP固定头、cookie、硬件类型/长度、chaddr/client ID、XID、状态、
server identity、选项长度及重复/冲突选项，再应用配置；异常包没有半更新。
上游共享DHCP PCB通过UDP connect限制源端口67，不能只因dhcp_recv未使用port
参数就宣称该路径缺少端口过滤。server/DNS/router信息必须经过controller预先给出的
允许范围，网络响应不能更改应用权限。NAK、DECLINE、冲突和地址变化分别记录。

DHCP重试采用有界退避和真实随机XID，仍受获取期限/停止命令约束。获取失败后
进入可查询失败状态，后续controller可显式重试；不无限忙轮询、补造成功租约或
启用AutoIP兜底。无跨重启租约恢复，启动总是重新获取，持久化另行设计。

## 7. glibc 解耦与文件占用

网络服务保持 NO_SYS、原生frame/clock/random接口；协议里没有glibc/newlib结构、
errno、FD或pthread/TLS。N4 SDK先提供原生异步解析接口，N6再把真实结果映射到
`getaddrinfo/freeaddrinfo`、EAI错误与socket。NSS、`resolv.conf`/hosts策略、IDNA、
IPv6、DNSSEC、TLS和WebKit迁移分别验收。换libc或提供头文件不能替代服务能力。

实现预计位于 `src/user/network/` 的resolver/configuration模块、共享net2头、
原生SDK及lwIP端口patch；修改上游必须保留锁定原件和许可证、记录patch输入及
编译后源码哈希。不能在应用侧另写DNS客户端绕过认证服务，也不复制newlib私有
解析/进程接口。当前glibc终端kind5出站snapshot限制与N4无共享线接口。

## 8. 独立交付与实际验收门槛

| 里程碑 | 必须取得的实际证据 |
|---|---|
| N4-C0 本提案/audit | 来源锁、能力与缺陷定位；真实IPv4/UDP对照和失败用例；生产关闭，guest not_run |
| N4-D1 DNS后端校验/有界熵 | 错端点、ID、question、opcode、TC、owner、压缩/长度拒绝；故障熵/碰撞有界退出且无发送；普通+ASan/UBSan；原N2回归 |
| N4-D2 DNS生命周期/cache | begin/result/cancel与三重身份；同名合并/独立取消、revoke后槽复用、deadline、cache绝对TTL/epoch、满额度与释放重填；错误类别准确 |
| N4-D3 DNS真实客体 | 私有fixture的新nonce域名与随机A结果；host收包及PCAP；正确/错误响应、缓存命中不发包、TTL后重新查询、并发、撤销、服务故障/重启；source/SDK/ELF/ISO绑定 |
| N4-H1 DHCP状态/时间 | OFFER/ACK/NAK、T1单播/T2广播、续租/丢失/租约过期、ACD冲突、短租约/长暂停/溢出、错误XID/server/options、随机失败和池耗尽；实际生产状态机 |
| N4-H2 DHCP真实客体 | 私有DHCP fixture，短但真实单调租期；获取、续期成功/失败、NAK、换地址/resolver、过期禁止旧应用流量与资源恢复；静态对照保持 |
| N4组合 | DHCP配置影响DNS与活跃连接；多应用压力、控制会话公平性、stop/restart；xsh/dash入口分别记录 |

宿主测试不替代客体，QEMU user网络的一次长租约不能代替T1/T2/过期验收；外部
公共DNS不适合新鲜挑战的确定性验收。初期fixture只绑定宿主loopback/私有链路，
不得改宿主网络配置。AF_UNIX限制可继续serial-only；需要UDP/私有链路权限时先
做环境probe，限制导致未运行则保留准确错误、命令和下一位可执行入口。

主审后的下一最小实现先处理DNS端点/答案校验与有界熵。D1通过后仍保持production
DNS关闭，直到D2的取消/cache基础和D3真实客体闭环可交付；DHCP按独立门槛推进。
单个gate失败不阻塞其他模块的代码审阅或独立host工作，但必须阻止依赖它的能力宣告。
