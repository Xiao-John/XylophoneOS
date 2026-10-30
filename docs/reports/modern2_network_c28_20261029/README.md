# C28/C29生效后的N2替代交接

2026-10-29 20:14北京时间补充。**N2继续BLOCKED，原frame-proxy接续路径被本补充替代。**
上游[PR #24](https://github.com/Xiao-John/XylophoneOS/pull/24)已由维护者合入main
`169f51e6b410863b8d8c9707b7ea84a6f649d59c`。本分支merge该提交后按新宪法工作；
[公开PR快照](pr_snapshot.json)显示PR #18/#20/#22仍Draft/open/unmerged，#24已合入。
[输入校验](input_verification.json)固定新宪法、修订记录及新旧时基/驱动/提案的8份准确提交文件。

[原审查包](../modern2_network_20261029/README.md)及其snapshot/checksums所有字节保持不变，
仅作为修订发生前的静态审查与历史时点。它关于“PR #18合入后实现整帧内核复制入口、
内核独占设备队列、沿用N1内核驱动进入普通用户态期间”的接续建议不再适用。
原权限/代际/撤销/失败/回收问题和ETH→ARP→IP→TCP→HTTP→实际画面的因果验收仍有价值，
但D1–D3必须重写为新通用授权机制与用户态驱动验收，不能机械复用旧表中的实现位置。

## 新的裁定边界

最高来源是已合入的[宪法C28/C29](../../xos_plan.md)与
[修订裁定记录](../../work_log/0086_principle_amendment_driver_timebase.md)。

- **C28**：设备初始化、队列/数据通路、传输收发属于用户态驱动服务。内核保留中断递送/应答、
  授权MMIO、DMA授予、IPC/权利撤销等通用机制。缺少机制按C20论证后先登记，不能把驱动继续放内核。
  逐设备、窄窗口、显式且可撤销的MMIO只授予认证驱动服务；普通应用仍默认无MMIO/PCI IO/DMA。
  旧C21末句让步由C28替代。C26引导/调试过渡范围不能充当交付驱动主线。
- **C29**：唯一单调时基归属独立公共模块，由时间中断唯一写入；sys_ticks、单调/实时时钟、
  线程deadline、驱动等待与所有超时同源。EOI/屏蔽只是机制，不带计时/统计副作用。
  驱动或lwIP不能另起计数器，也不能把设备完成中断数当时间。
- **旧PR #20**：原真实Ethernet/IRQ/DMA与34页回收证据不追改；其内核态驱动按新原则为架构违规，
  不得作为交付驱动主线。能复用固定来源知识、失败输入和测试结构，不意味着实现位置获豁免。
- **旧PR #18**：当前内核队列+整帧复制的`sys_net_device`提案与C28不符；即使以后原样合入，
  也不能据此实施违规frame-proxy。须维护者重设计成设备授权原语并重新登记，rights/生命周期/token
  语义可借鉴。此补充不抢占112，不改原claimed，不自行新增MMIO/DMA/IRQ syscall或常量。

## 待重新登记的最小机制与权限问题

下表是维护者设计输入，不分配编号/布局，不宣称现有实现支持。

| 面 | 内核通用机制应明确什么 | 用户态职责与必须限制 |
|---|---|---|
| 设备主体/授权 | 认证supervisor、设备对象与驱动生命周期身份；授予/运行期撤销/退出失效；不以路径名、自报PID授予 | 只有获特定设备权利的驱动能初始化该设备；网络客户和浏览器只持受保护服务session |
| 窄MMIO | 逐设备验证资源边界、页粒度可能暴露的额外寄存器、属性/权限、映射撤销/TLB与并发；设备发现/PCI配置所需的最小受控机制另论证 | 用户态VirtIO能力解析、feature协商、队列配置、doorbell、ISR设备状态处理；禁止任意BAR或全PCI IO授权 |
| DMA授予 | 物理/设备可见地址的限定、pin/归属、配额、缓存一致性、撤销和隔离保留；普通应用无任意DMA地址权利 | 用户态驱动维护descriptor/avail/used、TX/RX队列和pbuf复制/引用；DMA只能指向被授予的缓冲对象 |
| IRQ递送/应答 | route权限、屏蔽、递送序号/未确认事件、原子等待、驱动退出撤权；EOI无业务/计时副作用 | 用户态驱动读设备状态并推进队列；中断不自动等于有帧，不能由内核代管VirtIO ring或lwIP |
| 失败/停止 | 权利撤销不自动等于DMA停止：机制必须给出可验证停止或quarantine策略，避免撤MMIO后无人能停设备；不隐含IOMMU | 驱动/监督者执行已授权的设备协议和重启策略；reset未确认时不得把可能仍被设备写的页归还通用池 |
| 服务IPC | 基于认证主体与对象代际的服务发现/session/限额/故障可观察性；不足时另行登记通用机制 | 用户态驱动与lwIP可按冻结的受信边界组合；普通client只能取得连接操作，不能获裸帧、reset或设备权 |

没有IOMMU资格时不能把任意不可信驱动当作已被DMA完全隔离；实际信任假设、bus-master停止机制、
故障驱动可做什么必须写入设计和真实测试。这里不以此推定必须在内核保留VirtIO驱动，
也不预先批准某个停止实现；由C20论证最小通用机制并让维护者登记。

## 修改后的验收顺序

1. **登记/审查门**：维护者处理PR #18旧claim、提交C28授权原语设计，冻结编号/布局/主体/权限、
   MMIO范围、DMA pin/quarantine、IRQ协议、代际/错误/撤销。正式合入前仅隔离探针，不调用未登记接口。
2. **M1权利与撤销**：真实guest证明普通应用拒绝、跨设备窗口拒绝、越界/旧token/跨进程拒绝；
   grant仅扩大到已允许对象，活体撤销、exec/fork/exit/驱动故障后映射和IRQ权利失效；真实访问异常有记录。
3. **M2用户态驱动**：实际VirtIO初始化、队列与RX/TX代码在用户态ELF；客体源码/反汇编/manifest及
   运行日志证明位置。真实Ethernet、边界帧、队列满/溢出、非法completion、分配失败、停止/重启均验。
   内核不能留下代做队列/整帧收发的隐蔽后门；不把pre-run诊断当交付驱动。
4. **M3等待/故障/资源**：IRQ到达与等待/撤销/deadline竞态，driver fault与停止失败时的UNKNOWN、
   quarantine及客户端状态；MMIO映射、DMA页、IRQ等待/事件引用逐项计数。成功回收和失败隔离分别报告。
   单核/独占route可作为明确受限profile，未验共享IRQ/SMP不能称支持。
5. **T1统一时基**：独立公共时基整改/登记后，真实证明sys_ticks、monotonic、wall-clock推进、线程deadline、
   设备等待和lwIP timeout同源；EOI/屏蔽调用不改变时钟或附带统计。阻塞/超时、回绕饱和策略和受影响线程/Qt
   回归绑定新组合。时基未整改不能从旧双计数器推定C29通过。
6. **N2真实协议与渲染**：用户态驱动→用户态lwIP2.2.1→TCP→受控宿主HTTP→真实guest响应。
   延续原验收包的独立guest request_nonce、host处理请求后fresh response_nonce、双向ARP/IP/TCP/HTTP PCAP、
   HTTP wire/body分别摘要、guest实际接收字节和同run真实截图。然后接原browser_http+liteHTML，不先开放假的socket。
   DNS/DHCP和HTTPS各自独立；TLS链/主机名/时间/熵检查不可关闭。

N2仍锁定lwIP2.2.1 `77dcd25a72509eb83f72b033d219b1d40cd8eb95`，NO_SYS原始archive仅编译准备；
`sys_now`和随机数绑定、所有状态/pbuf/PCB生命期仍在用户态。先numeric host与显式IPv4可缩小首个HTTP目标，
不等于DNS/DHCP资格。完整DOM、事件、模块、Worker、WASM和来源隔离仍独立Web平台阻塞。

## 可证实的C29差异与本轮结果

新main `169f51e` 的 `src/kernel/arch/x86_64/pic.cpp::pic_eoi` 只有EOI端口操作，
当前 `tasks.cpp` 的 `tick_count`/`monotonic_ns`仍在task模块；独立公共模块和全调用路径资格未由此文档实现。
旧N1候选 `9b832fa` 则新增 `pic.cpp::ticks`、`pic_ticks()`，在`pic_eoi(0)`递增，
同时保留 `tasks.cpp::tick_count`；`virtio_net::wait_until`读的是前一套。
这是源码中两个计数来源的静态证据，不是本轮时钟运行测量。具体哈希见input_verification。

本轮仅合入已批准的文档原则到独立分支、补静态审查与验收设计，没有运行时代码/公共ABI变更。
没有新guest、SDK、ELF、镜像、抓包、截图、内存/资源计数或产品资格。
原冻结报告校验保持8/8相同；补充文档/ABI/差异检查原始输出见 `checks/`。
此补充本身不满足本阶段至少一项真实公共兼容能力的成功标准。
