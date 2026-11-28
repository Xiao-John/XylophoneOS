# Net2 TCP readiness 与 SHUT_WR

基线：`daf2bd24`。独立网络 P0 模块，未改共享 `docs/state.md`。

## 交付

在 v2 新增可探测 operations 15–17：16 字节 capabilities、32 字节 TCP level
readiness 和写半关闭。操作 1–14、默认目的地址限制和认证会话均保留。
接收字节、EOF、错误与发送缓冲/段队列共同决定快照，connected 不再被误当成
可写。快照仅观察、不消费、不订阅、不预留容量。

写半关闭使用真实 lwIP `tcp_shutdown(..., 0, 1)`；保留 handle 和接收路径，
允许先发送 FIN 再读取远端响应，重复操作幂等。处理 FIN 分配压力、LAST_ACK
正常结束与 TIME_WAIT 的 PCB 回收，避免保留由定时器释放的指针。
SDK 核验新增响应布局、保留字段和状态一致性；旧服务 unsupported 不破坏原操作。

## 实测

使用 `xos-sdk-preview-2-linux-x86_64` pre-release 开发环境。通过常规 launcher
执行，未声称 `--offline` 网络命名空间隔离。锁定 lwIP SHA-256
`83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1`。

- SDK 内真实 lwIP 包级测试 30 项、生产 service loop 2 项：普通和 ASan/UBSan 均通过。
  覆盖半关闭保留接收、FIN 内存压力、TIME_WAIT 后 EOF、readiness 背压/消费/错误、
  跨会话和旧 handle 拒绝，以及既有 TCP/UDP/配额/撤销回归。
- SDK 客户端测试通过，覆盖 capability 旧服务拒绝、8 类损坏 readiness 和损坏 capability。
  native client/HTTP 的 ASan/UBSan 与 freestanding 链接通过。
- 重建系统 `180c17e82b74f8f1`，真实 QEMU TCG 两次服务启动完成半关闭挑战。
  每次独立宿主只在收到完整随机 nonce 和客户端 FIN 后才发送 32 字节随机 challenge；
  客体逐字节记录匹配内容、读取 EOF，最终资源回到原基线。
- 同一镜像 HTTP/UDP、四并发应用、错误 service PID、关闭端口、stop/restart、
  两种受控 TCP 窗口 close 回归全部通过。

证据：[目录和校验表](../reports/net_socket_extensions_20261127/manifest.json)，
[guest](../reports/net_socket_extensions_20261127/guest.json)，
[ASan/UBSan](../reports/net_socket_extensions_20261127/asan.json)。
公开命令路径使用 `XOS_REPO`、`XOS_TOOLCHAIN`、`XOS_RUN_TMP` 占位；原始收据哈希
与公开导出哈希分别记录，不把路径归一化后的文件冒充原始字节。

## 范围

本模块完成原生 Net2 TCP readiness 与半关闭；glibc 桥是下一独立模块。
未提供事件订阅、wait-set、非阻塞 connect、监听、DHCP 或公共 CA。
本次 guest 入口为 xsh；Dash 未重测，报告保留 `dash_shell` not_run。
DNS/DHCP/TLS 和设备 reset 故障隔离未由本次用例取得新增资格。
