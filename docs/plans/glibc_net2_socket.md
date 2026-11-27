# glibc 出站 TCP 与 Net2

基线为 v2 静态 SDK、现有 [32 项描述符表](../contracts/glibc_files_v1.md#fd并发与服务会话)
和 [认证 Net2 v2](../contracts/net_service_v2.md)。首段采用现有的用户态网络策略、请求期限
和双 endpoint PID 校验。内核 syscall、Net2 v2 的 1–14 操作和启动描述符布局沿用原格式。

## 首段 · 阻塞 IPv4 TCP

- `socket` 分配普通 libc fd 和私有 open description，接收 `AF_INET/SOCK_STREAM`、协议
  `0` 或 `IPPROTO_TCP`，支持 `SOCK_CLOEXEC`。`connect` 消费 `sockaddr_in` 的地址和端口，
  通过 `ntohl/ntohs` 转到 Net2 数值域。真实网络准入由 Net2 的现有 ACL 执行。
- 一个进程使用一个认证会话。应用 fd 的私有路由存放独立的 64 位 Net2 handle，不截断成
  fd 号码，也不写入启动或 fork 的继承记录。会话中途失效会使同一代的已连接描述符失效。
  只有显式的新连接可以建立下一代会话，失败的副作用请求不自动重发。
- `send/recv` 和 `read/write` 持有描述符租约后释放全局 fd 锁。每个 Net2 IPC 往返在会话
  锁下串行。收到确定的 `would_block` 后释放会话锁再等待，进度共用同一绝对单调期限。
  TCP 短写和短读如实返回，只有服务已经确认的 EOF 才返回 0。首段限定阻塞模式及已列明的
  flags。普通 `dup` 共享同一个 open description；fd 号的关闭和复用可以先于在途 I/O 完成。
- 最后一个引用在 fd 锁内登记待退休路由，释放 fd 锁后实际关闭 Net2 handle。先按原操作
  有序关闭。如果服务明确报告未读数据或暂不能关，使用取消释放；后续的旧引用不触及已复用
  的 fd。进程退出仍由已有 IPC 生命周期清除会话。首段的进程继承保持现有拒绝边界，socket
  带 `CLOEXEC` 可沿原 spawn 策略丢弃，携带 socket 的 fork 返回 `ENOTSUP`。
- 由采用受信静态安装配置的 Xsh 交付已启动的 `net2` 服务 PID。缺失绑定、错误 PID、目标地址拒绝、未连接
  I/O、额度、超时和服务重启分开观察。首段不开放 DNS、监听、IPv6 联网或 POSIX `poll`。

静态配置客体通过受控宿主 TCP 监听和随轮次变化的挑战验双向内容、部分 I/O、EOF、别名 close、
fd 复用和资源回收。错误 PID、无服务、非法族、目的地址拒绝和无效 fd 单独执行。
`<netinet/tcp.h>` 使用锁定的上游 GNU 头，公开的报头/选项数值与具体选项运行时资格分别登记。

## 后续 · 半关闭和就绪

Net2 当前的有序 close 会退休整个 handle。`SHUT_WR` 需要在 lwIP 成功发 FIN 后继续持有
读侧和原 handle，不能调用现有 close 模拟。现有 status 只给连接阶段与 EOF。可读需要真实
接收队列或 EOF，可写需要发送窗口，不能用 `connected` 代替。

拟作为独立的用户态 v2 协议扩展。在只读 capability 中明确半关闭和 readiness 位，旧服务的
`unsupported` 或旧 capability 形状保持原阻塞子集。新增操作用服务端串行的状态快照与代际
编号关联当次连接，保留旧消息布局。把读取后的再次确认纳入等待协议，处理查询和订阅之间
发生的就绪变化。分开验证 EOF/失败唤醒、消息丢失重查、在途操作取消、最后引用回收、老服务
拒绝，以及半关闭后继续接收的真实客体行为。该段须使用实际 Net2 和 lwIP 路径验收。
