# N2 原生网络服务 v2

2026-11-25。登记基线 `08f3e13e`；实现分支先冻结本协议再实现。状态为
implemented_unqualified，完整 guest qualification 待固定工具链与 QEMU 补验。

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
| close | 6 | 有序TCP关闭，队列不足可返回would_block；UDP释放 |
| cancel | 7 | 立即终止连接、释放用户态资源；已发送字节结果仍未知 |
| revoke_peer | 8 | 仅bootstrap controller；撤销该PID全部会话并拒绝其后续连接，直到服务重启 |
| stop | 9 | 仅bootstrap controller；停止接入、有限等待回复消费，然后关闭全部连接和NIC |

错误域为 -201 invalid、-202 denied、-203 resources、-204 would_block、-205 timeout、
-206 closed、-207 io、-208 unsupported、-209 buffer_too_small、-210 reset。
未知操作返回unsupported；版本、线长度、保留字段、重放等损坏关闭会话。
失败响应不携带有效负载；buffer_too_small的flags单独报告所需容量。

## 权限、生命周期和预算

默认确定性 profile 为静态10.0.2.15/24、网关10.0.2.2，只允许向10.0.2.2非零端口
发起TCP/UDP；不允许应用绑定监听、广播、多播或修改配置。地址授权在分配PCB前执行。
四个普通会话、另保留一个controller会话，每PID最多一个会话；每会话最多两个连接、
全局八个连接。handle在一次服务生命周期单调分配且不复用；服务重启使全部旧IPC失效。
最多16个撤销PID；表满返回resources且不部分撤销。

每连接TCP接收环8KiB，读取前不扩大TCP接收窗口；UDP队列四条、每条1024字节，满时
丢新包并可查询计数。lwIP自身有界内存池，VirtIO队列满传递背压。每会话只保留一条
待回复，回复阻塞超过500ms、会话空闲60秒、对端关闭或格式错误均回收会话全部连接。
TCP连接建立受open请求原期限约束；没有自动重连/重发。服务轮转处理各会话，一轮
每会话至多一个请求、至多64个NIC帧，持续调用sys_check_timeouts并在统一单调域等待。

客户端deadline超时关闭IPC会话；send可能已经交付，调用方不得自动重试副作用请求。
进程exit/exec/fault由现有IPC生命周期暴露断开，服务回收PCB；服务退出时reset/close
沿用设备契约。停止失败由内核quarantine处理，不冒称IOMMU隔离。

`sys_now` 是sys46纳秒向下取整到毫秒后取低32位，lwIP原生处理32位回绕；不校准新时基。
TCP序列随机源调用sys63，初始化熵失败则拒绝启动，不以时钟伪造随机数。NO_SYS单线程
服务不依赖pthread/TLS。DNS/DHCP/TLS与POSIX socket适配分别属于N4/N5/N6。

## 验收与交接

宿主测试必须执行生产service_core和真实锁定lwIP后端：认证/地址拒绝、跨会话handle、
重放、配额、超时/关闭、TCP/UDP、短读写/EOF、背压和资源回收；host模拟不取得guest资格。
客体需重建镜像和匹配SDK，在xsh/dash运行多应用、取消/撤销/kill/restart、队列压力及
新鲜挑战HTTP，记录源码/SDK/ELF/镜像/夹具哈希、响应字节、资源基线及抓包。旧报告保持原样。
