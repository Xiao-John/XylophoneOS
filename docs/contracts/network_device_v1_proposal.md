# 网络设备 v1 认领提案（未实现）

2026-10-29。状态：**PROPOSED / BLOCKED_IMPLEMENTATION**。本PR仅认领一个编号，
不提供源码常量、假成功桩或SDK supported声明。需本登记合入后才能实施公开接口。
N1内部设备测试不依赖本提案合入；TCP/HTTP业务不进入内核。

## 实际缺口与分层

基线 upstream `39083f9968d84b5679c86a74a6c8394033c0d915`：

- `pci::map_bar_range`只提供内核有界UC映射。用户堆与IPC不能取得PCI配置、BAR、
  DMA所有权或网卡完成事件；不应放开它们来方便移植。
- `tasks.cpp::ipc_send/ipc_recv`只接受内核已建立且绑定双方PID的endpoint。
  客户端不能自建“网卡handle”；现有`sys_ipc_handles`返回文件会话而非设备。
- `sys_process_grant`28仅在supervisor拥有的未启动子进程上设置spawn_depth，第二参数
  仅允许0/1。它没有设备right，不借用该参数悄悄改变旧语义。
- PIC当前只开放PIT/PS2，IDT未提供一般PCI INTx入口。N1需先实际验证中断与回收。
  已有GPU测试中用户MMIO/PCI IO会fault，不能把破坏隔离当用户态驱动方案。

本轮已独立重跑[真实失败探针](../reports/network_device_gap_20261029/README.md)：在N1
实际BAR映射及32帧收发后，普通应用的MMIO写/PCI OUT分别fault14/13，且资源精确回收。
这是现有隔离机制按预期拒绝，不能冒称已实现用户态网卡API。

设备机制由PC平台驱动和通用受保护调用边界提供。用户态网络服务运行lwIP等固定来源
协议栈，负责ARP/IP/UDP/TCP/DNS和客户端连接策略。普通浏览器只持用户态服务会话，
不得取得原始帧、reset、DMA、PCI或进程管理权利。POSIX socket适配仍为NOT_RUN。

## 编号、协作和文件所有权

仅提议把112从unallocated扩为reserved，并claimed `sys_net_device`。113以后保持
unallocated；不预占整个未来网络号段。ABI表的allocated 1–66不变。
本PR负责人只改本提案、登记、state和独立work_log；后续实现负责人统一改
`process_record`权限/退出、dispatch、共享头、SDK普通/线程生成器及manifest。
浏览器PR不修改这些公共文件。PR #17的FB1/FB2与C27提案不在本PR范围内。

## 拟定调用、身份和生命周期

单个x86-64 profile入口，参数为用户request地址与精确64字节长度，第三参数必须0。
结构固定宽度，不含内核指针；地址为调用进程虚拟地址。version=1、size=64，未知op、
flag、reserved及版本均拒绝，不部分解释。字段顺序：

| 字段 | 类型/偏移 | 语义 |
|---|---|---|
| version, size, operation, flags | u32 ×4 / 0 | flags首版必须0 |
| object_token | u64 /16 | OPEN输出会话token；其余设备操作输入token；GRANT输入目标PID |
| data_address, data_length | u64 ×2 /24 | 受检用户缓冲区，零地址只用于不需数据的op |
| deadline_ns | u64 /40 | WAIT的绝对单调deadline，0为不阻塞 |
| result_length, status | u32 ×2 /48 | 输入0；输出实际字节数/事件位，其他op不得擅用 |
| reserved | u64 /56 | 必须0 |

拟定op为INFO0、TX1、RX2、WAIT3、RESET4、CLOSE5、OPEN6、GRANT7。具体共享头
尚未生成。INFO的输出结构、事件位和right位必须在实施前冻结并逐项验收。

- GRANT只允许已认证supervisor对其拥有且未启动的child授予显式TX/RX/WAIT/RESET
  right子集；无名称/路径授权。首版不允许进一步委派。rights=0撤销，需唤醒现有等待。
  具体rights位经独立小型grant输入结构传递，不能混入flags的保留位。
- OPEN仅已被明确授予设备right的进程可调用，一次仅一个网络服务所有者。占用时BUSY。
  owner是进程生命周期身份，token是不可重指新会话的generation标识，不能只用PID索引。
- 所有操作先认证主体和right，再访问payload；request自身仍须按用户地址规则校验。
  无权调用返回DENIED，泄漏给另一进程的token无效。OPEN成功不扩大right。
- CLOSE使token失效、取消等待并停止会话新提交；不自动撤销原grant。退出/故障/exec
  必须先撤销设备权利和token、停止新提交并按reset/quarantine契约处理outstanding DMA。
  是否重新OPEN由有权用户态策略决定，不自动重连。fork不继承设备权利。
- RESET必须持RESET right，先冻结提交，再实际reset并确认DMA停止；成功使旧token
  全部失效，需重新OPEN。reset失败使设备不可用且DMA隔离保留；不释放仍可能被设备
  写入的页。返回IO并标记在途发送结果UNKNOWN，不能宣称未发送/已远端收到。

INFO含MAC、MTU、link/ready/failed状态和有界资源计数，不返回BAR/物理地址。事件检查
与挂起在同一内核临界区完成；IRQ只记录完成并唤醒，协议栈不在中断上下文执行。
WAIT按绝对单调时钟，最长单次30秒；不得丢唤醒或无限等待，无网络活动不持续轮询。

## 资源和错误语义（实现前需冻结数值）

首版拟定Ethernet MTU1500，无VLAN/TSO/校验和卸载/多队列；完整帧14–1514字节。
RX/TX各16个descriptor，设备自有有界缓冲；实际DMA页数由N1收据冻结，不能用提案预算
冒称测量。每次只复制一帧，用户指针永不交设备。无权提交任意目的DMA。

| 情况 | 拟定符号语义 |
|---|---|
| TX队列满 | AGAIN，0字节入队；重试须等待TX事件 |
| TX成功 | 整帧已复制并入队；不承诺已发到线缆或对端接收，TCP由用户态ACK证明 |
| RX为空 | AGAIN，0字节，无假EOF |
| RX缓冲过小 | SMALL，报告所需长度，帧留在队列供重试；不悄悄截断 |
| WAIT已到期限 | TIMEOUT，不保证下一瞬间无事件；调用者可再次检查 |
| 设备缺失/初始化失败 | NO_DEVICE / IO；旧文件/Qt/串口继续可用 |
| 关闭、撤销或失效token | CLOSED / INVALID；旧token不能命中新对象 |
| 非法长度、地址、版本或保留位 | INVALID / FAULT；不提交设备 |
| 配额或内存不足 | RESOURCES；失败路径回滚，仍活跃DMA只可隔离 |
| 提交后设备故障/reset不确定 | IO + UNKNOWN在途语义；禁止伪造零执行 |

上述为XOS接口，不是errno数字承诺或POSIX socket。错误数值、INFO/grant布局和同步
复制失败的原子性需由后续实现PR给出共享头、SDK与客体探针，不在本登记PR放占位实现。
TCP连接对象另外需要session身份、配额、close/服务退出、部分send/超时/断线语义，
由用户态network service v1专项登记；设备入口不是网络客户端API。

## 实施验收与退出门槛

登记合入后，公开实现必须同时提供普通/线程SDK、两个manifest、grant/撤销/退出测试、
跨进程token拒绝、无卡/初始化失败、IRQ deadline/race、真实TX/RX、队列满/分配失败、
reset回收/隔离、文件/Qt/线程定向回归。未通过不得升级allocated或supported。
本提案不声称已经满足这些门槛，不把N1内核boot-monitor诊断作为N2客体TCP回执。
HTTPS、CA/时间/随机数、证书链/域名校验以及JavaScript均独立NOT_RUN。
