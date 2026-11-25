# sys84–86 IPC endpoint lifecycle

2026-11-25。本契约明确既有 endpoint pair、readiness wait 和 service name 的
进程映像生命周期；不分配 syscall，不更改结构、操作号或错误码。

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

## 与其它 IPC 的关系

- sys81 通用 channel 的显式、静止继承沿用 [channel 契约](channel.md)；这里
  的 sys84–86 端点没有继承开关，不能借 sys81 的保留列表延长其生命周期。
- sys88 IPC v1 继续使用 [ipc_v1 契约](ipc_v1.md) 的 exec 撤销规则。
- 文件服务专用会话继续按现有 exec 规则重新生成不透明端点 token；已打开文件
  描述和 FD 继承由文件/装载契约定义。

旧实现只在进程销毁时清理 sys84–86，成功 exec 漏掉了这组对象。本次修复落实
新映像不能继承未声明通信权利和旧消息的边界，也使 N2 同 PID 重连及连接回收
成立。回退此修复会重新引入该生命周期缺陷；不建议以客户端重试代替内核撤销。

## 验收

`tests/ipc_exec_guest.py` 构建独立 native fixture，真实执行失败 commit、成功
exec、新同 PID 认证连接、旧端点失效、旧名称移除、待 accept 消息丢弃以及精确
资源回收。fixture 只允许空 startup-v3 FD snapshot，并验证镜像、SDK、源码和
程序哈希。网络客户端的 exit/exec/fault 回收由 `tests/net_service_guest.py`
后续网络验收覆盖；完整终端/显示/Interactium 重跑和 sys81 继承压力单独记录。
