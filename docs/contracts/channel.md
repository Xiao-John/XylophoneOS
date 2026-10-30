# 有界受控通道：实施契约

2026-10-29。sys81 已实现，尚未客体验收。现有 files/display 会话是专用启动端点，
不能由普通终端服务安全创建或发现；轮询 IPC 又无法与串口等待组成可靠的服务。
本机制只提供受控、单槽、单向消息端点和等待，不解析服务协议或授予设备权限。
终端服务可用分别等待设备和通道的线程组成服务；多源原子等待仍未承诺。

拟用 sys81 `sys_channel(action,second,third)`，version 1 固定宽度请求：

- create：second 指向 `channel_create`（version/size、sender PID、receiver PID、
  容量、reserved），third=0；每端必须是调用者自己或有完成记录的直接子进程，
  且 sender/receiver 不同，不能是 dead、closing 或 exec 暂存体。caller 成为控制
  者；容量为 1–4096 字节，每控制者最多 4 条，系统总上限受端点池约束。成功返回
  内核单调且不复用的 opaque handle；失败不产生部分端点。building 子进程可连接，
  但在 receiver 可运行前 send 返回真实错误。不得以请求中的 PID 自证身份。
- enumerate：second 为有界序号，third 指向固定 `channel_info` 输出；仅列出调用者
  作为 sender 或 receiver 的通道，包含 handle、角色、对端和控制者 PID。输出的
  内核认证身份可供服务授权，必须在会话变化时重新枚举；不存在返回 not-found。
- close：second 为 handle、third=0；控制者或任一参与者可关闭，唤醒等待者并返回
  失效错误。handle 不复用。控制者、任一参与者退出/故障时立即关闭相关通道，
  未确认消息的业务结果可能未知，不能伪造已处理或未处理。
- wait：second 为 handle，third 为绝对单调纳秒截止时间；0 表示立即检查，
  `UINT64_MAX` 表示无限。仅参与者可等待；sender 等待空槽、receiver 等待已入队
  消息，先检查就绪再判超时；原子检查/登记，send/recv/close/进程退出唤醒。
  可伪唤醒，调用方必须重新验证并重试 I/O。单核、10ms 时钟量化。

SDK `channel_io.hpp` 提供等待后实际 send/recv 的辅助循环：仅在分别返回 full/empty
时重新等待；其他错误原样返回，消息内容不作业务解释。终端控制端及服务使用该循环，
避免把伪唤醒误判为会话失效；该辅助接口尚未经过客体验收。

现有 sys_send/sys_recv 对此类端点沿用单槽、有界复制和调用者 PID 检查；不改变旧
files/display 端点权限。构造/枚举/close/wait 须处理无效指针、容量、重复/资源耗尽、
退出和并发，旧身份和 token 不能指向新对象。成功 exec 不应隐式继承待确认通道：
执行前关闭相关通道；失败 exec 不改变。fork 默认不继承：新 PID 不能操作旧端点。
保留原 IPC 错误含义，新增操作的 EAGAIN/超时/失效以共享头明示。

实施时先在当前分支登记 ABI、再同步共享头、内核、SDK、两个 manifest 和定向客体
探针；本地 claim 不是其他分支已同步。用户要求全部相关修改提交后才做客体验收。
不得将通道实现或客户端 stub 冒称终端服务、模式恢复、W1 或 W2 完成。
