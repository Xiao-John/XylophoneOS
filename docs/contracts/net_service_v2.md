# N2 原生网络服务 v2

2026-11-25。登记基线 `08f3e13e`；实现分支先冻结本协议再实现。后续组合
`2baed87` 已完成[限定N2/N3客体验收](../work_log/ca46b580_network_multi_application_qualification.md)：
11项传输、13项生命周期和12轮撤销/槽复用。资格只适用于该记录的实际组合。
DNS/DHCP仍关闭；[N4提案](network_n4_v1_proposal.md)另列原生接口与启用门槛。

## 边界和兼容

用户态 `net_service` 独占原有 sys112 grant、VirtIO NIC 与 lwIP 2.2.1 NO_SYS 栈。
普通应用通过 `net2` 命名 IPC 服务操作连接，不接收帧、设备地址或 grant。使用现有
sys4/5、84–86，不新增 syscall，不依赖 bulk_grant_v1，不引入 libc 私有类型。
客户端须从可信启动者取得 service PID，并核验两个 IPC endpoint 的认证 peer PID。
同一服务进程发布的名称共享 accept 队列；按消息版本分派，名称不充当权限。

`net-start 41` 启动 v2 模式；`net` v1 名称仅保留 controller 的 stop 兼容路径。
`net-start 41 raw` 是显式可信诊断 profile，沿用 v1 原始帧服务供旧 net_ping/TCP
探针复验；该模式全部运行进程须受信，不与普通应用隔离资格混用。独立
`net-probe 41` 保留 ARP/IRQ/reset 诊断。旧 v1 普通客户端在 v2 模式被拒绝。
移除构建中的 `XOS_LWIP_SOURCE_ARCHIVE` 后，v2 启动明确失败；raw/probe 仍可重放。
回退分支恢复 v1 模式，v2 客户端遇到缺失服务/版本错误退出，不隐式降级 raw。

## 固定线格式

`src/shared/include/xos/net_service_abi.hpp` 是布局来源；x86-64 little-endian，
64 字节报头后跟 0–1024 字节负载，线长度必须精确匹配。

| 字段 | 类型 | 语义 |
|---|---|---|
| version/action | u32/u32 | version=2；操作见下表 |
| sequence | u64 | 每会话从1严格递增，不回绕、不重放 |
| object | u64 | 连接 handle；revoke_peer 时为认证目标 PID |
| deadline | u64 | 绝对单调纳秒；请求必须在当前时间之后且最多30秒 |
| result | i64 | 请求=0；响应负数错误，send 成功为已接受字节数 |
| address/port/transport | u32/u16/u16 | IPv4 数值按网络阅读顺序，如10.0.2.2=0x0a000202；端口为整数 |
| length/flags | u32/u32 | payload长度；receive请求flags=容量(1–1024)，响应状态位 |
| reserved | u64 | 必须为0 |

| action | 值 | 行为 |
|---|---:|---|
| information | 1 | 服务额度与会话/连接数量；不暴露其它应用数据 |
| open | 2 | transport=1 TCP/2 UDP，address/port非零；返回新handle，TCP可能connecting |
| status | 3 | 返回connecting/connected/EOF/failed状态，失败返回终止错误 |
| send | 4 | TCP短写；UDP保留报文边界、允许空报文；成功只表示本地接受 |
| receive | 5 | TCP短读/EOF；UDP一条完整报文，容量不足保留报文并返回所需长度 |
| close | 6 | 有序TCP关闭；未读接收数据或关闭排队不足时返回would_block并保留连接；UDP释放 |
| cancel | 7 | 立即终止连接、释放用户态资源；已发送字节结果仍未知 |
| revoke_peer | 8 | 仅bootstrap controller；撤销该PID全部会话并拒绝其后续连接，直到服务重启 |
| stop | 9 | 仅bootstrap controller；停止接入、有限等待回复消费，然后关闭全部连接和NIC |

错误域为 -201 invalid、-202 denied、-203 resources、-204 would_block、-205 timeout、
-206 closed、-207 io、-208 unsupported、-209 buffer_too_small、-210 reset。
未知操作返回unsupported；版本、线长度、保留字段、重放等损坏关闭会话。
失败响应不携带有效负载；buffer_too_small的flags单独报告所需容量。
open/status的终止错误可带failed位。information成功负载固定32字节且flags=0；
open/status成功无负载，状态为connecting、connected或connected|EOF；send及控制
成功无负载且flags=0；receive成功仅允许EOF位。SDK逐操作核验这些形状，损坏时关闭会话。

## 权限、生命周期和预算

默认确定性 profile 为静态10.0.2.15/24、网关10.0.2.2，只允许向10.0.2.2非零端口
发起TCP/UDP；不允许应用绑定监听、广播、多播或修改配置。地址授权在分配PCB前执行。
四个普通会话、另保留一个controller会话，每PID最多一个会话；每会话最多两个连接、
全局八个连接。handle在一次服务生命周期单调分配且不复用；服务重启使全部旧IPC失效。
最多16个撤销PID；表满返回resources且不部分撤销。

服务内部每次接纳分配不回绕的会话代际号，将IPC端点、待回复及其期限绑定到该次接纳。
撤销后同一轮复用槽位前关闭旧双端点并清空整份回复状态；代际不匹配时清理旧绑定。
代际号只在服务内部使用，线格式、连接handle和客户端sequence保持原协议。

每连接TCP接收环8KiB，读取前不扩大TCP接收窗口；UDP队列四条、每条1024字节，满时
丢新包并可查询计数。lwIP自身有界内存池，VirtIO队列满传递背压。每会话只保留一条
待回复，回复阻塞超过500ms、会话空闲60秒、对端关闭或格式错误均回收会话全部连接。
TCP连接建立受open请求原期限约束；没有自动重连/重发。服务轮转处理各会话，一轮
每会话至多一个请求、至多64个NIC帧，持续调用sys_check_timeouts并在统一单调域等待。
服务收到完整请求后重新采样单调时钟再授权，NIC轮询、其它会话或IPC接收期间跨过
deadline的请求返回timeout，尚未执行的open/send不进入网络后端。

TCP有序close在接收环或lwIP拒收缓冲仍有未读数据时返回would_block，保留handle、
原接收数据、已接受发送数据及回调。调用方继续receive，排空后用新sequence重试；
需要立即丢弃的调用方使用cancel。成功close表示lwIP已接管FIN和既有发送队列，
应用handle随即失效。锁定的lwIP 2.2.1在FIN段分配不足时通过TF_CLOSEPEND自行重试；
服务继续驱动计时器，并解除所有指向原应用槽位的回调，避免迟到FIN/RST影响复用槽位。
FIN成功接管后的远端确认和TCP状态回收继续遵循lwIP计时器；该返回值不保证远端收到。

客户端deadline超时关闭IPC会话；send可能已经交付，调用方不得自动重试副作用请求。
进程exit/exec/fault由现有IPC生命周期暴露断开，服务回收PCB；服务退出时reset/close
沿用设备契约。停止失败由内核quarantine处理，不冒称IOMMU隔离。

`sys_now` 是sys46纳秒向下取整到毫秒后取低32位，lwIP原生处理32位回绕；不校准新时基。
适配器随机源调用sys63，初始化熵失败则拒绝启动。lwIP当前TCP初始序列仍走上游
`tcp_next_iss`的计数默认实现；此前“TCP序列随机源调用sys63”的说明有误，ISN
加固须独立实现/验收。运行期熵错误锁存io后不再出帧；D1内部DNS准入使用可返回
错误的熵接口和有限抽取预算，见[N4提案](network_n4_v1_proposal.md#54-d1-当前实现边界)。
NO_SYS单线程服务不依赖pthread/TLS，DNS/DHCP/TLS与POSIX socket分别按N4/N5/N6推进。

## 验收与交接

宿主测试必须执行生产service_core和真实锁定lwIP后端：认证/地址拒绝、跨会话handle、
重放、配额、超时/关闭、TCP/UDP、短读写/EOF、背压和资源回收；host模拟不取得guest资格。
客体需重建镜像和匹配SDK，在xsh/dash运行多应用、取消/撤销/kill/restart、队列压力及
新鲜挑战HTTP，记录源码/SDK/ELF/镜像/夹具哈希、响应字节、资源基线及抓包。旧报告保持原样。

## N3 原生客户端与HTTP

`<xos/net_transport.hpp>`提供C++17便利API，继续使用上述v2线协议；没有新增字段、
操作号、syscall、POSIX errno或FD。单个client由调用方串行使用，每PID仍至多一个会话。

- `connect(expected_service_pid)`建立并认证会话；`close()`关闭会话和服务侧全部连接。
- `open(protocol, address, port, deadline, handle)`等待TCP建立或直接建立UDP关联，
  内部status轮询沿用原绝对期限；输出handle只在成功时可用。
- TCP的`write/read(handle, bytes, count, deadline)`可短写/短读；正容量read的0返回
  表示EOF。零容量调用立即返回0；发送空TCP内容不产生网络写入。
- UDP的`send_datagram`保留完整消息并允许0长度；`receive_datagram(..., required)`
  容量1–1024，返回0可为真实空报文。buffer_too_small给出required且保留队头供重试。
- `close_connection/cancel_connection(handle, deadline)`分别有序关闭/中止。已确认
  would_block可以带新sequence重试；交付后结果未知时关闭会话，禁止自动重放。

每个请求发送前和收到回复后都采样同一单调时钟，调度停顿跨过deadline时返回timeout。
返回错误域保留本契约负数值；客户端因损坏响应返回io，不接受带多余数据的成功回复。

`browser_http::fetch`连接真实原生TCP，支持数字IPv4的HTTP GET，遵守同一个总期限、
部分写入、精确Content-Length和EOF；返回status、完整body范围及最终URL。最多5次
重定向且地址/端口保持同源；0次配置返回第一条完整响应。头部增量线性扫描后解析，
头上限16KiB、body上限1MiB；调用方可以进一步限制总缓冲区。DNS、TLS、压缩和chunked
等待后续阶段。浏览器在独立模块实施资源同源规则与导航总预算。

新增真实客体入口`tests/net_transport_guest.py`使用运行时生成的nonce与随机32字节
挑战，校验HTTP状态/字节、UDP字节、双向关闭、错误PID、关闭端口、服务重启和资源
回收。测试记录按实际执行分别标为passed/failed/not_run；固定工具链与QEMU缺失时
保留具体原因，不复用旧raw/纯parser报告取得N3资格。
