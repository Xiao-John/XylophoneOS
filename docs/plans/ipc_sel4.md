# 以 seL4 为参考的 XOS IPC 路线

2026-11-10。用户要求先明确应用与内核可并行工作的边界，暂不启动 VM3。规范见
[IPC v1 契约](../contracts/ipc_v1.md)。计划原始基线为 `d708790`；VM2 #102 已在其后合入，
本路线仍不要求 VM3 才能开展接口设计、参考模型和小消息实现。
2026-11-12：IP1–IP3 已合入，IP2/IP3 客体验收在 PR #111 记录并通过。四个 IPC feature
(`endpoint_call_v1`、`deadline_v1`、`notification_v1`、`wait_set_v1`) 已具备开放依据；
IP4 `bulk_grant_v1` 仍待客体验收。IP5 正加入受限短消息直接切换、handle 索引和批量复制，
附延迟分布探针；这次代码和性能探针仍待维护者 guest run。

## 当前事实与问题

- `sys_send/recv` 使用端点的一个内核消息槽，最大 4096 字节；发送 user→kernel，
  接收 kernel→user。满槽/空槽返回错误。37 个系统端点、8 个名称槽、16 个待接入
  连接槽；资源数是当前实现值，不是新接口承诺。[实现](../../src/kernel/arch/x86_64/tasks.cpp)。
- sys81 是受控单向通道，支持单通道截止等待和最多 4 个通道的 wait_many；sys84–86
  是成对端点、就绪等待和名称注册/连接。前者有部分客体通过证据，后者被
  [Interactium](../contracts/interactium.md)和音频使用；两者的创建、等待、身份和
  生命周期并不相同，旧契约中的“未验”状态可能早于相关专项证据，须逐项核实。
- 文件服务遍历会话并 yield，文件客户端轮询响应；音频命名通道用非阻塞检查和 10 ms
  分段睡眠来维持期限。pipe 为 4 KiB 环，当前读写逐字节复制。它们分别是可疑开销，
  不是已量化的性能结论。
- 端点查找和等待唤醒是固定数组线性扫描；单槽限制突发并发；连接/等待在部分路径
  要多次 syscall。现有设备/显示/文件的专用权限和错误路径不能被新机制绕开。
  仓库已有关联功能客体测试，尚未发现可直接比较本基线的 IPC 延迟/吞吐基准。

## seL4 借鉴与 XOS 选择

| 机制 | seL4 公开设计 | XOS 候选与区别 |
|---|---|---|
| endpoint | 同步发送/接收，等待线程排队 | 新能力定义 rendezvous；保留现有异步单槽，不混称 |
| 身份与授权 | 对象 capability、权限及内核交付 badge | 先定义最小受控引用、badge、代际及转授；不宣称现有 PID handle 已是完整 capability 系统 |
| RPC | Call；一次性 reply capability；ReplyRecv | 定义单次 reply token 和明确部分成功语义；不预设 seL4 CSpace 或调度 |
| 小消息 | 条件满足时寄存器与 fastpath | 语义先固定；数量/寄存器及是否直接切换由架构与测量确定 |
| 通知 | signal、badge 位 OR 合并及 wait | 独立能力，明确合并而非计数；wait set 与 IRQ 组合独立验收 |
| 长数据 | capability 与受控共享内存可组合 | 后续独立 grant，依赖授权/VM，不能将普通匿名 VM 当共享内存 |

seL4 的官方 [IPC](https://docs.sel4.systems/Tutorials/ipc.html) 和
[notifications](https://docs.sel4.systems/Tutorials/notifications.html) 是设计参考；
其 IPC fastpath 条件包括 Call/ReplyRecv、消息适配寄存器、有效地址空间、无 cap
转移和调度前提。XOS 不继承其形式化证明、操作名称或这些具体实现条件。

## 双轨交付与阶段

| 阶段 | 应用/服务侧 | 内核/SDK 侧 | 完成出口 |
|---|---|---|---|
| IP0 契约与基线 | 按提案设计服务协议和错误处理；标明不可运行 | 冻结语义、盘点旧用法，建立可重复测量方案 | 双方确认输入输出、状态机和差异；不宣称能力可用 |
| IP1 ABI 与参考模型 | 构建与后端无关的契约测试，编写不冒充产品的模型客户端/服务 | 登记 syscall 88、固定布局/错误/发现；普通与线程 SDK manifest 明确 unsupported | 当前 PR 合入后完成登记；参考模型覆盖边界；仍不标记 supported |
| IP2 同步端点与 RPC | 先以测试服务调用，显式检测 capability；旧客户端照常 | 对象/权限/队列、call/receive/reply、期限、取消、close/exit；正常慢路径 | 真实 guest 功能、异常、竞争与资源精确回收；新能力才可按 profile 宣告 |
| IP3 等待与迁移 | 在文件、终端、显示、Interactium、音频中选择纵向切片，旧/新差分 | notification、可授权的 wait set 和现有事件互操作；按实际缺口分开登记 | 各迁移服务双路径比较、崩溃及重启语义明确，适用工具 xsh/dash 双验 |
| IP4 大块数据 | 框架只依赖显式 buffer/grant feature，保持小消息通路 | 独立共享页/grant 授权、生命周期、撤销和 VM/COW 安全设计 | 在 VM/共享映射相关资格具备后作真实授权、故障和性能验收 |
| IP5 快路径与扩展 | 相同 API/协议，不因 fastpath 改调用 | 受限短消息直接切换、端点 handle 索引与 IPC payload 批量复制 | 新 guest probe 对比 direct-waiter 与 polling fallback 的延迟分布、语义和资源；SMP 另立阶段 |

两个工作流可以从 IP0 并行：服务侧以提案的逻辑类型、版本化协议和模型测试推进，
实际二进制、数字 wire 及 capability 宣告在 IP1 登记后才可依赖；内核侧先实现参考
慢路径。模型不是产品后端，也不证明内核安全或性能。IP3 某类 wait 的完成不自动
证明其它类型/IRQ 混合等待。共享 grant 不阻挡 IP0–IP3，但不得用不安全替代声明通过。

## 评审与验收矩阵

- 权限：无权调用/接收/转授、伪造 badge/handle、过期代际、拒绝扩权、目标退出和
  句柄回收后重用；reply token 恰好一次及不可跨请求串线。C22 身份来自内核授权。
- 状态：发送/接收先后、多个请求者/接收者、公平性、满额、空消息、最大消息、超长、
  跨页及无效地址、输出容量不足不消费、数据提交点；慢/快两条路径逐项对照。
- 竞争：排队与送达、deadline/wake、reply/取消、关闭/撤销、服务/client/thread
  kill、迟到回复及重启的所有胜出顺序；已送达后的结果未知不能重试伪装成功。
- 资源：第 N 个端点、等待记录、reply 槽、页/pin/临时对象申请失败及分批清理；
  多轮基线核对对象、页、引用、等待、token、线程、任务和完成记录，失败不泄漏。
- 跨线：VM 权限降低/decommit/unmap 与阻塞缓冲 pin；未来 COW copyout；exec、fork
  与句柄继承按各自阶段资格检查。受影响旧 ELF、文件、终端、显示、Interactium、
  音频回归；xsh/dash 各跑适用工具。
- 性能：固定新镜像/源码/SDK/QEMU或实机、CPU拓扑与计时源；分别记录空载及竞争下
  0/小/中/最大消息的单向与往返延迟 p50/p95/p99、消息/秒、字节/秒、CPU占用、
  syscall/上下文切换/复制字节、队列深度与失败率。比较当前 mailbox、参考慢路径、
  新快路径、pipe 批量复制；不把 QEMU 数值直接当硬件承诺。门槛在有可靠基线后冻结，
  低延迟不能以丢权限检查、饥饿或增加空转为代价。
- 发布证据：源码 commit、工具/镜像/ELF 和 SDK hash、参数、时间域、原始串口、
  通过/失败/未运行及范围；使用历史工作记录作线索，不将旧结果改绑新镜像。

## 当前下一步

1. IP2/IP3 已按 PR #111 的三轮真实客体验收开放四个 feature；bulk_grant 保持关闭，等待 IP4
   PR 的客体 race/resource 验收。
2. IP5 提供可重复的 QEMU 延迟分布脚本。运行前以同一源版本重建系统镜像和线程 SDK，记录
   build/image/SDK/ELF hash；QEMU 数值只作相对测量，不能代替硬件声明。
3. 快路径探针通过后复核慢/快路径错误、权限、deadline、handle/token 和资源回收；任何
   SMP 或跨核唤醒优化另立阶段。
