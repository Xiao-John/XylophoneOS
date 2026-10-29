# PR #18待审决策与精确边界

输入为 `97947c07853e785530d3c907738a8b45f530986e` 的
[原网络设备提案](https://github.com/www080327-glitch/XylophoneOS/blob/97947c07853e785530d3c907738a8b45f530986e/docs/contracts/network_device_v1_proposal.md)。
下表是本轮静态审查；建议均未变成公共ABI或已通过实现。

| ID | 现有具体文字/代码与风险 | 建议交给维护者决定 | 最小关闭证据 |
|---|---|---|---|
| R1 活体撤销 | 原提案要求GRANT只能对supervisor拥有且未启动child；又要求rights=0撤销并唤醒现有等待。若未启动限制覆盖撤销，则运行中WAIT无法被该入口撤销 | 将授予与撤销的准入分别写清：授予仍仅未启动child；撤销是否允许持原授权关系的supervisor对活体owner执行，并明确父退出/关系终止处理；或登记另一受控撤销路径。不能默认PID/路径授权 | 真owner阻塞WAIT时由有权主体撤销；等待醒来、后续调用拒绝、旧token不重指；无权主体不能撤销 |
| R2 布局未闭合 | 64字节request已描述，INFO/grant具体布局、right/event位和错误数值明确留待实施前冻结 | 冻结版本/尺寸、输入/输出字段、允许位、对齐和未知字段错误；INFO是否需right、外泄信息范围也写清；同步普通/线程SDK，禁止预留位偷塞grant | 逐偏移静态断言；非法version/size/flags/op/right/reserved、错误长度、溢出和边界指针逐项guest拒绝；两SDK一致 |
| R3 副作用与copyout | TX成功是整帧copy并入队，request又有输出字段。若入队后输出地址失效，普通FAULT不能证明“没有发送”；RX取走后copyout失败也可能丢帧 | 现单核profile下先验证完整request读写区与payload、明确并发mapping/退出的同步关系；提交后失败必须保留可查询状态或明确UNKNOWN。RX只在全部copy完成后消费，失败保帧；不要重复发送掩盖不确定性 | request跨页只读/不存在、payload跨页/重叠request、线程并发更改、RX短buf/copy失败的可观察队列与发帧计数；按冻结语义断言 |
| R4 token与主体 | 提案要求generation标识、不只PID，但位宽、耗尽、错误优先级、CLOSE后grant可否重新OPEN尚无具体编码 | 冻结进程生命周期身份与会话generation；wrap必须fail closed，不能回绕重指；操作先认证主体/right再读payload。CLOSE/RESET/exec/exit/parent死亡各列转移表 | 跨进程泄漏token、PID复用、关闭再开、reset再开、fork/exec、owner故障及代际耗尽故障注入 |
| R5 N1→运行期IRQ | N1 init要求选中的PIC线原先masked，结束恢复全PIC/ELCR状态并reset后才run。wait_until使用privileged pre-run中断睡眠；没有普通用户态期间调度等待资格 | 不把诊断入口当服务接口。设备负责人定义运行期IRQ route所有权和共享线边界；按内核等待队列集成原子事件检查/挂起，与撤销、期限、退出同步；IRQ仍无lwIP策略 | 普通用户程序/Qt/文件/线程同boot期间真实RX/TX中断；deadline前后完成竞态、撤销与服务故障；无丢唤醒、无空闲忙循环 |
| R6 reset失败 | N1代码reset最多1,000,000次status读取，失败保留DMA；冻结qualification明确reset-timeout/quarantine fault injection NOT_RUN | 规定失败设备状态、哪些route/映射/授权失效、quarantine资源计数与停止再提交；没有DMA停止证据绝不回收到通用页池。不能要求失败时“精确全页归零”逼实现释放活跃DMA | 注入实际reset确认超时，证明quarantine页保持且不能重分配；成功路径34页回收，新服务生命周期资源另测；文件/Qt/串口可继续 |
| R7 客户端协议 | 设备入口不等于socket；普通应用不能已有固定IPC endpoint以外自行mint endpoint。提案尚无真实network-service连接协议 | 先审计现有受保护IPC/进程关系是否满足浏览器客户端身份与服务发现；定义session/连接代际、配额、partial send/read、超时、close、服务退出/UNKNOWN。若必须新增公共机制另行先登记，不借112夹带业务op | 两客户端隔离、连接引用不可串用、服务退出后在途/后续状态、旧引用与新服务代际分离、配额/失败回滚 |

`R3`列出的并发地址失效是需要契约处理的风险，并非声称当前已有PX4-A实现。
本轮公共mmap/mprotect尚未登记实施；设计应避免设备ABI日后与VMA生命期冲突。
`R5`不要求本阶段实现通用共享IRQ或SMP；可以明确只支持一条独占已验证route并真实拒绝其他拓扑。
`R6`故障注入属于后续真实机制测试，不代表物理硬件/IOMMU资格。

N1依据为固定提交
[设备契约](https://github.com/www080327-glitch/XylophoneOS/blob/9b832fa06061b6905d00529a2e0a8445ea389a2a/docs/contracts/virtio_net.md)、
[驱动](https://github.com/www080327-glitch/XylophoneOS/blob/9b832fa06061b6905d00529a2e0a8445ea389a2a/src/kernel/platform/pc/virtio_net.cpp)、
[未验清单](https://github.com/www080327-glitch/XylophoneOS/blob/9b832fa06061b6905d00529a2e0a8445ea389a2a/docs/reports/virtio_net_n1_20261029/qualification.json)。
原public syscall1–66、spawn-only28、BAR/DMA隔离保持；本docs PR不修改提案的claimed登记，
也不抢占112或内存67–79。维护者仍须在原登记PR处理决议并合入后才能授权实施公共入口。
