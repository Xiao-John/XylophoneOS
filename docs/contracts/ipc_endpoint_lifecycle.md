# sys84–86 IPC endpoint lifecycle

本契约明确既有 endpoint pair、readiness wait 和 service name 的进程映像
生命周期。文件回复的专用等待使用 sys85 的新增模式。

## 权属和替换边界

`sys_ipc_endpoint` (84) 创建的双向端点，以及 `sys_ipc_name` (86) 建立的同类
端点，绑定内核认证的两个进程身份。发布名称只用于发现；取得通信对象以后，
调用方仍须检查双方的认证 PID，服务须自行检查具体操作权限。

成功 `sys_process_exec_commit` 是旧映像的撤销边界。PID 可以保留，但旧映像
创建、持有或参与的 sys84–86 端点均失效；同一 pair 的两个方向一起撤销，清除
尚未消费的消息、尚未 accept 的连接和旧映像发布的所有名称。已阻塞的对端等待
被唤醒并收到 broken 错误；随后对旧句柄的调用按既有 invalid/denied 错误路径
失败。句柄使用单调 token，旧 token 不会指向后来建立的通信对象。

替换后的程序如需通信，显式重新发布名称或连接服务。服务观察到旧端点失效后
回收自己的会话/连接，再接受同 PID 的新请求；网络业务和恢复策略仍留用户态。

失败的 exec 保留原映像、名称、端点及未消费消息。撤销操作只在 entry、文件
会话、显式继承请求和 authority 的所有可失败检查通过以后执行。退出、kill 和
fault 的进程销毁使用同一个撤销实现，避免不同结束路径遗漏对象。

## 每主体资源额度

sys84 `create` 与 sys86 `connect` 按内核认证的 owner PID 共用最多 **4 个双向
pair**，每 pair 的两个端点只计一次。未 accept、已 accept、空/满队列、登记了
waiter 的 pair 同样计入；不能通过 drain accept、交给 peer 或换一个发现名称
重新取得额度。peer 接收已有 pair 不转移 owner，也不计为 peer 新建的 pair。
sys86 `publish` 每 PID 最多 **2 个名称**；重复发布自己的现有名称保持幂等成功。

限制在分配或写入输出之前检查，超额返回既有 `process_error_resources`；旧
pair、名称、消息及调用者输出保持原值。owner revoke 或任一参与者 close、
exit/fault/cancel、成功 exec 撤销 pair 后归还额度；失败 release、失败 exec
不归还。名称 unpublish/owner 终止后归还；失败 unpublish 不变。额度从现存
对象计算，避免独立计数与撤销路径不一致。名称上限与全局冲突分别判断：已有
他人名称仍返回 busy，不把命名冲突解释成授权。

共享头 `ipc_max_owned_channels` / `ipc_max_owned_names` 和 SDK manifest 的
`ipc_endpoint` 项公开限制。syscall 数字、请求布局、单调 token 和错误码保持；
旧二进制仍可使用原请求，超过新 profile 的额度收到原有资源失败。网络服务
可同时发布两个协议名，现有 Pumpkin/broker 流程保留其最多三个自建 pair。
全局池上限不扩大，仍可能因其他主体或系统资源压力提前失败。此机制保证单一
PID 不能占满 pair/name 池，不承诺整个进程树的预算、任意客户端数或防 DoS。

## 与其它 IPC 的关系

- sys81 通用 channel 的显式、静止继承沿用 [channel 契约](channel.md)；这里
  的 sys84–86 端点没有继承开关，不能借 sys81 的保留列表延长其生命周期。
- sys88 IPC v1 继续使用 [ipc_v1 契约](ipc_v1.md) 的 exec 撤销规则。
- 文件服务专用会话继续按现有 exec 规则重新生成不透明端点 token；已打开文件
  描述和 FD 继承由文件/装载契约定义。

## 文件回复等待

sys85 的 `file_reply_until`（mode 4）接收端点 token 和非零绝对单调纳秒期限。
仅允许调用者经 sys22 取得且本进程持有的文件回复端点。源端必须为当前内核
认证的 Files 服务。其他端点和其他进程名下的 token 返回 denied。原模式
0–3 的 generic IPC 端点范围和参数保留。

队列检查和登记等待是一次内核操作。就绪返回 0，接收者另行读取队列。到期
返回 `thread_error_timeout`，Files 服务终止后尚阻塞的等待者收到
`pipe_error_broken`。内核使用既有等待队列及统一单调时钟，终止客户端时按
现有进程生命周期撤销等待。现行 Files 由引导绑定，退出时撤销会话 token。
glibc 经期限、请求序号、协议内容校验后才向应用交付响应。
[文件会话](glibc_files_v1.md)

旧实现只在进程销毁时清理 sys84–86，成功 exec 漏掉了这组对象。本次修复落实
新映像不能继承未声明通信权利和旧消息的边界，也使 N2 同 PID 重连及连接回收
成立。回退此修复会重新引入该生命周期缺陷；不建议以客户端重试代替内核撤销。

## 验收

`scripts/build_ipc_exec_probe.py` 用所选 SDK 构建独立 native fixture；
`tests/ipc_exec_guest.py` 将它装入同源系统，真实执行失败 commit、成功 exec、
新同 PID 认证连接、旧端点失效、旧名称移除、待 accept 消息丢弃以及精确资源回收。
fixture 只允许空 startup-v3 FD snapshot，并验证镜像、SDK、源码和程序哈希。

阻塞唤醒必须与调用前已失效分开验收。fixture 通过 native worker 发起等待，
同进程的主线程使用既有 sys50 观察真实 `waiting` 计数，确认只有目标 worker
已经阻塞后才触发撤销。结果严格要求 `ipc_error_broken`，不接受
`process_error_denied` 代替阻塞唤醒。线程机制单独编译，不启用 single-thread libc。

组合检查还包括 owner revoke、peer close、正常退出、fault 与 parent cancel。
每条路径同时登记满队列 send 和空队列 receive 两个等待，要求分别唤醒；再由
用户态显式启动同名服务，重新验证真实 PID、新端点、旧 token 不复活及业务往返。
创建权默认不继承、sys88 句柄按主体绑定、委派只能缩权、reply token 单次消费、
配额失败与回收通过同一客体探针交叉检查，不能将名称或消息中的数字视为授权。

网络业务的恢复由 `tests/net_service_guest.py` 的专项验收覆盖；完整终端/显示/
Interactium 重跑、sys81 继承压力、SMP 与物理硬件资格单独记录。
