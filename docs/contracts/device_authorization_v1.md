# 设备授权原语 v1（已实现，客体资格未运行）

2026-11-12。状态：**IMPLEMENTED_UNVERIFIED / GUEST_NOT_RUN**。本契约完成
[network_device_v1_proposal.md](network_device_v1_proposal.md) 的 C20 论证与 ABI 登记，
冻结接口、编号、权利与错误数值；本轮实现授权表、MMIO、DMA、IRQ 与终止后端，
以及受限的用户态 VirtIO-net 纵切。用户明确授权将完成实现与客体验收分开交付；
不修改旧段 1a 记录，不把宿主验证称为 guest 通过。对照 [abi_registry](abi_registry.md)，遵循宪法 C20/C21/C22/C25/C28/C29 与
[时间域契约](time_domains.md)。

## 1. C20 论证：为什么必须新增此内核机制

- **现有机制为何不足**：`sys_display`/`sys_display_present`（65/66）是显示单设备的
  定向接口，不提供通用 MMIO 窗口、IRQ 路由或 DMA 对象；`sys_process_grant`（28）仅为
  spawn 语义，不能授予活体进程设备权利；PCI 发现（`platform/pc/pci.cpp`）只做内核侧
  枚举与校验，没有面向用户态驱动的授予出口。缺少授权原语时，virtio_gpu+display、
  ata、ps2 三个 C28 存量驱动（[0088](../work_log/0088_kernel_driver_c28_debt_register.md)
  共 495 行）无法迁出内核，网络驱动线亦无落点。
- **调用主体与授权依据**：调用者是经内核认证的驱动服务进程或真实 bootstrap
  supervisor；授权只由设备授权者经受保护子进程对象或另行登记的运行期授权操作作出
  （C22：名称、路径、自报 PID 不授权）。grant 绑定设备实例、进程生命周期身份与
  不可回绕代际；token 跨进程无效。
- **资源与生命周期**：内核只提供通用机制——授权表、映射、IRQ 路由、DMA 页池与
  撤销（C28 边界）；设备协议、队列、恢复策略全部留在用户态驱动服务。对象随
  grant 关闭、进程退出、exec、撤销、故障进入统一终止序列（见 §5）。
- **失败行为**：所有拒绝返回冻结错误值；副作用前失败；完成态 UNKNOWN 不伪称
  未发生（C25）。
- **架构假设（v1 非目标）**：单核 x86-64；设备独占单驱动 owner；单 IRQ route；
  有限对象数。不宣称支持：共享 IRQ、热插拔、SMP、无受信硬件隔离下的不可信驱动。
  PIO 不在本契约范围——端口 I/O 授权属 `sys82` 线（pio_grant 契约，另线登记）；
  本契约的 IRQ 操作是该线 IRQ4 绑定的依赖项。

## 2. 接口冻结

### 2.1 入口

新增单一多路入口（认领号见 §6）：

```
i64 sys_device(u64 request_address);   // request_address: 调用者64字节请求结构的虚拟地址
```

内核先整体快照请求结构再逐项校验；输入结构的任何修改在快照后无效。输出经请求内
`output_address/output_length` 指定的调用者缓冲返回，先完整验证再一次性 copyout，
副作用之前短缓冲即失败；pin 失败返回 FAULT，完成后释放。

### 2.2 请求结构（64 字节，小端，8 字节对齐，冻结）

| 偏移 | 字段 | 约束 |
|---:|---|---|
| 0 | u32 version | 1；未知拒绝 |
| 4 | u32 size | 64；其他拒绝 |
| 8 | u32 operation | 见 §2.3；未知拒绝 |
| 12 | u32 flags | v1 必须 0；另定义前拒绝非零 |
| 16 | u64 object_token | 操作对象；未用为 0 |
| 24 | u64 input_address | 输入子结构 VA；未用为 0 |
| 32 | u32 input_length | 精确子结构大小；未用为 0 |
| 36 | u32 output_length | 精确容量；未用为 0 |
| 40 | u64 output_address | 输出子结构 VA；未用为 0 |
| 48 | u64 deadline_ns | 仅 IRQ_WAIT：系统单调绝对期限；0 为非阻塞（C29） |
| 56 | u64 reserved | 必须 0 |

### 2.3 操作编码（冻结）

| 值 | 操作 | 所需权利/主体 | 最小输入 → 输出 |
|---:|---|---|---|
| 1 | GRANT | 设备授权者 | 受保护进程对象、设备实例、rights 子集 → `token,generation,rights` |
| 2 | QUERY | grant + QUERY | grant token → 有限资源描述符（索引、长度、权限、属性）；不开放任意 PCI 扫描 |
| 3 | MAP | grant + MMIO_MAP | token、资源索引、页对齐 offset/length、请求权限 → `映射地址,映射token`；页粒度会暴露其他设备/敏感寄存器时拒绝 |
| 4 | UNMAP | 映射 owner | 映射 token；同步 TLB，token 失效 |
| 5 | DMA_ALLOC | grant + DMA | token、长度、对齐、设备方向 → `DMA token,用户VA,设备可见地址,实际长度`；仅内核分配并固定、计入配额的页可作 DMA 对象 |
| 6 | DMA_RELEASE | DMA owner | DMA token；须先满足 §5 终止序 |
| 7 | IRQ_BIND | grant + IRQ | token、IRQ 资源索引 → `事件token,序号` |
| 8 | IRQ_WAIT | 事件 owner | 上次确认序号；deadline_ns 来自请求头 → 结果码+序号；检查与睡眠原子化，序号防丢唤醒 |
| 9 | IRQ_ACK | 事件 owner | 对应序号；校验 owner/代际/序号，重复与过期拒绝 |
| 10 | REVOKE | 设备授权者 | grant token；停止新操作、唤醒 WAIT、进入 §5 终止序 |
| 11 | CLOSE | owner | 关闭自身 grant；语义同 REVOKE |

### 2.4 权利位（冻结）

`QUERY = 1<<0`，`MMIO_MAP = 1<<1`，`DMA = 1<<2`，`IRQ = 1<<3`。互不隐含；每一处
操作与 DMA 方向均独立验证。`QUERY` 的资源索引仅在该 grant 的 generation 内有效。

### 2.5 错误值（冻结，负 i64，按本 ABI 命名空间）

`ok=0, invalid=-1, fault=-2, denied=-3, stale=-4, busy=-5, resources=-6,
no_device=-7, timeout=-8, closed=-9, io=-10, unknown=-11`。优先级：校验类
(invalid/fault) 先于授权类(denied/stale) 先于资源类(busy/resources) 先于设备类。
SDK 映射在实施 PR 的头文件中一一对应，不得新增未登记错误值。

### 2.6 输出字段（固定宽度 u64，未用字段必须 0）

`token, generation, rights, length, offset, attributes, address`；不输出内核指针或
任意物理地址（设备可见地址仅限 DMA_ALLOC 契约内）。

## 3. 对象模型

grant 绑定（设备实例、owner 进程生命周期身份、generation）；设备独占一个 owner，
竞争返回 BUSY；generation 耗尽拒绝新分配而非回绕。MAP/DMA/IRQ 对象均派生自 grant，
父 grant 关闭则级联终止。

## 4. IRQ 与时间

IRQ 到达：内核按路由屏蔽并记录待处理事件、唤醒 WAIT；ACK 后按平台路由语义恢复
递送，设备原因由用户驱动读取清除。事件积压有界计数、溢出状态与可恢复/失败规则，
不无限排队、不丢唤醒。EOI/屏蔽不执行设备队列逻辑、不隐式推进系统时间（C29）；
诊断有界且不改功能。WAIT 期限只接受系统单调绝对值（时间域契约），设备计数须显式转换。

## 5. 撤销与终止序（冻结）

REVOKE/CLOSE/exec/exit/故障：① 标记 closing，阻止新提交；② 取消 WAIT，使全部
token 失效；③ 屏蔽并解绑 IRQ；④ 撤销 CPU 映射并同步 TLB；⑤ **撤销映射不等于 DMA
停止**——授权者/受控驱动须在相关权利撤去前完成设备协议停止，或经独立审查的总线
机制禁用 bus mastering 并确认终止；⑥ 仅在有可验证停止与事务排空证据时解除 pin、
归还页。设备无响应/超时/无法证实停机：设备标记不可用，DMA 页与必要对象
**quarantine**（禁止重分配与新 owner 复用），在途操作结果 UNKNOWN。

## 6. ABI 登记

- 新设 reserved 段 **112–127「设备授权线」**（自原 112–65535 unallocated 中划出；
  扩大范围须再登记）。
- 认领：**112 `sys_device`**（设备授权/内核机制负责人；范围=本契约 v1；状态
  implemented_unverified；本轮已实现可调用后端，客体验收尚未运行）。
- 与 65/66 的关系：显示客户端 ABI 迁移期间保持不变；显示驱动迁出后 65/66 由
  用户态显示驱动服务承接，内核侧实现替换另行验收登记。

## 7. 迁移路线与客体验收

原路线的每步独立客体验收仍是资格记录要求；本轮用户授权实现与资格分开交付，
缺少客体环境不再阻止提交已完成的实现。当前已实现第 1 步后端和第 5 步网络纵切，
均为 implemented_unverified；第 2–4 步仍是后续迁移，不计为本轮完成。

1. 内核原语：授权表/代际、请求快照与校验框架、映射与 TLB、IRQ 路由与 WAIT/ACK、
   DMA 页池与 quarantine。验收：负向探针套件（越权、越界、代际、撤销竞态、
   DMA 终止证据缺失）+ 现有套件零回归。
2. 纵向切片一 = 显示迁移：virtio_gpu+display 迁为用户态显示驱动服务（0088 退出
   条件），显示定向回归验收；65/66 客户端零变更。
3. 输入：ps2 迁移（依赖 sys82 线的 PIO 泛化 + 本契约 IRQ；两线先对齐再动）。
4. 存储：ata 迁移（同上依赖），容量/写入/断电语义独立验收。
5. 网络：virtio-net 用户态驱动服务（webengine M3 的前置）。

## 8. 边界与非目标

- 本轮实现按用户授权推进；内核隔离默认不变，普通进程不能授予 MMIO/PCI IO/DMA。
- 未实现 IOMMU：获得 MMIO 的驱动属于受信驱动，能够填写设备 DMA 地址。
  handle/映射鉴权、pin、方向与配额不限制恶意驱动或设备发出的任意 DMA；v1 只授予
  受信驱动与设备组合。quarantine 仅处理无法确认停止时的内存回收，**不是硬件 DMA
  隔离**，不能把普通进程不能取得 grant 等同于已隔离受权驱动。
- pio_grant（sys82）线的资源模型、交接与隔离语义不在本契约内；两契约互不替代，
  IRQ 语义以本契约为通用出口。

## 9. 当前后端的精确 profile

接口和 SDK 分别为 `src/shared/include/xos/device_abi.hpp` 与
`src/user/include/xos/device.hpp`。请求头仍为 64 字节，输出精确 56 字节，均 8 字节对齐；
无输出的操作必须传 output_address/output_length=0，只有 IRQ_WAIT 可给 deadline。
所有输入先快照，输出在副作用前完整验证并 pin；无输出的撤销操作不回写请求结构。
DMA_ALLOC 失败引起自身 grant 终止且撤掉输出窗口时，清 pin、返回 FAULT，不再 copyout。

| 操作 | input_length / 子结构 | 输出解释（其余字段为 0） |
|---|---|---|
| GRANT | 32：process_object、device_instance、rights、reserved | token、generation、rights |
| QUERY | 16：index、reserved | token、generation、length、offset、rights、attributes；见下文 |
| MAP | 32：index、offset、length、permissions | token、generation、rights、length、attributes、address=用户 VA |
| UNMAP | 0 | 无；request.object_token 为映射 token |
| DMA_ALLOC | 32：length、alignment、direction、reserved | token、generation、length、address=用户 VA、offset=设备地址、attributes=direction、rights=CPU 权限 |
| DMA_RELEASE | 0 | 无；request.object_token 为 DMA token |
| IRQ_BIND | 16：index=6、reserved | token=事件、generation、offset=当前序号、attributes=IRQ |
| IRQ_WAIT / IRQ_ACK | 16：sequence、reserved | WAIT 同 IRQ_BIND；ACK 无输出 |
| REVOKE / CLOSE | 0 | 无；request.object_token 为 grant |

所有 reserved 必须为零。device_instance 编码为 `1 + (bus<<8 | slot<<3 | function)`，
范围 1..65536。授权仅限真实 bootstrap supervisor 对其 owned building child；不支持
任意活进程转授，PID、名称、路径均不能替代主体认证。issuer/owner 任一退出或成功 exec
均触发统一撤销。当前只接收未启用 bus mastering 的 network-class PCI type-0 function，
避免夺取内核仍使用的显示、存储等设备。PIO、全局 PCI 扫描、任意 config 写接口均未开放。

QUERY 索引 0..5 是完整页隔离的 memory BAR，6 是独占 legacy IRQ；不存在的资源返回
NO_DEVICE。MAP permissions 仅 1（读）或 3（读写），user/NX/UC；BAR 边界、页对齐与
页粒度隔离在入口校验。只允许 512 MiB..4 GiB 的平台设备窗口，不能映射 RAM。
QUERY 的 0x100..0x13f 为**已授予设备的只读 256 字节配置快照**：length=4、offset 为
配置字节偏移、attributes 低 32 位为 8，高 32 位为配置 dword；物理 BAR base、ROM base
和 MSI message address 已清除。这个有限机制使用户驱动能发现 vendor capabilities，
不必授予 PCI I/O 端口；不解释 VirtIO 队列、不开放任意设备配置。

系统最多 16 grants，派生映射总计 128；每进程 16 个 16 MiB slot，窗口
`0x210000000000..0x210010000000`。MMIO/DMA 映射同时受 process_max_pages 约束。
每个 grant 最多 1024 个 DMA 页、每 owner 最多 2048 页、全系统最多 4096 页，均含 quarantine 页；单 DMA 对象
最多 4 MiB、alignment 为 4096..16 MiB 的 2 次幂。真实连续物理分配、清零和 user-page
refcount 用同一 allocator，失败回滚，不把任意既存用户页“声明成 DMA”。方向为 1=to_device、
2=from_device、3=bidirectional；from_device 的 CPU 映射只读，其他两种读写。无 IOMMU
时方向和页配额不约束恶意设备的总线访问，仍要求受信设备与驱动组合。

当前可安全回收 DMA 的设备限于 VirtIO-net `1af4:1041`、以及具有 modern common
capability 的 `1af4:1000`。用户驱动写 reset 并等 device_status=0；内核仅以有界 UC
只读观察器核对该完成状态，同时禁用并读回 Bus Master Enable，然后才归还页。
依据 [VirtIO 1.2 §2.4.1 / §2.4.2](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html)：
设备报告 reset 完成后不得继续访问队列。该观察器只服务回收证明，不在内核驱动协议、
填写 ring、收发帧或执行 reset。PCIe Transactions Pending 清零本身**不是** posted-write
普适排空证明，当前没有采用该判据。其他设备请求 DMA 返回 NO_DEVICE。
每个受支持设备保留一个有界 observer 映射，最多 16 个，不计作用户 DMA 页泄漏。

DMA_RELEASE 先遮罩 IRQ、撤销该对象的 CPU 映射，再核对停止证据。成功时归还该对象页，
设备保持 bus mastering 暂停；以后 DMA_ALLOC 才重新启用。无法确认时级联终止 grant，
保留全部 DMA 页，返回 UNKNOWN。正常 CLOSE、issuer REVOKE、exit、exec、fault 都遵守
相同页保留规则。未按设备协议 reset 的 kill/fault **可能 quarantine**，不承诺无条件回收。
撤销不会把仍能 DMA 的页归还给下一进程，quarantined instance 不允许新 owner 重用。

IRQ 只接受平台实际独占、未被其他 PCI function 使用的 3/5/7/9/10/11 路由；保留
timer、PS/2、COM1、RTC、ATA 路由。一次到达屏蔽路由并发布单调序号；屏蔽期间同一
未确认 level 合并，最多一个 pending event。序号耗尽停止发布并返回 IO，绝不回绕。
WAIT 仅接受上次已确认序号；0 deadline 或已过期且无 pending 返回 TIMEOUT；有 pending
先返回事件。ACK 精确匹配当前 pending 序号，重复或过期返回 STALE；清设备原因留给
用户驱动。ACK 成功才重新开启路由。WAIT 的检查、pin、阻塞登记与 IRQ 路由同一 CPU
中断 gate 串行化；退出/撤销唤醒为 CLOSED，输出窗口被其他 grant 撤掉时返回 FAULT。

宿主入口 `tests/ipc_device_host.py` 测真实 store/allocator；它替代硬件边界，不能证明
PCI、PIC、TLB 或 guest 调度正确。客体入口 `tests/device_abi_guest.py` 与
`tests/virtio_net_guest.py` 均未在本轮运行；完整负向权限、并发与同镜像回归仍待客体执行。
