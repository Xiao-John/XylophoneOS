# ClarkE 的 XOS 域名解析队列

在已锁定的 WebCore 软件目标上，`native_dns_queue.patch` 将 WebCore 的域名查询
接到现有 Net2 用户态服务。网络进程在 WTF 主循环初始化后使用
`configureXOSDNSService` 传入其启动方提供的服务 PID。同一进程可重复设置同一个
PID，服务重启时由启动方重新创建持有网络访问权的进程。连接校验两个 IPC 端点的
对端身份，再提交原生 A 查询。

队列使用单个 WTF 工作线程和最多 24 个待完成请求。3 秒截止时间从入队开始，
完成回调在主线程执行。预取沿用 WebCore 的合并逻辑和同一原生查询。取消移除活动
请求并回调一次，工作线程观察取消后释放 Net2 票据。结果通过请求身份检查后再交付，
允许调用方复用已取消的编号。

[原生 Net2 DNS 契约](../../../../docs/contracts/net_service_v2.md)
