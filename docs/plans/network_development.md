# XOS 用户态网络开发计划

2026-11-13。基线 `ffc4ea69`（#136）；这是开发计划，不改变 ABI，也不把待验内容写成已完成。保留 [网络交接](network_handoff.md) 的设备授权、DMA 隔离与时间契约，以及 [WebKit 计划](webengine_port.md) 的多进程、用户态网络和真实 HTTPS 目标。

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:cfe2129f407a5958a14bebbde583f63cdc0ef8cc0f7ae9e4e0aa6f3922bdcfc7 -->

基线状态（`ffc4ea69`）：用户态 VirtIO 原始帧 ARP/IRQ/reset 限定通过；lwIP 2.2.1 NO_SYS 静态地址下 ARP/ICMP 有客体证据。TCP/UDP 虽编译但未验；现有 net 为单会话 raw frame，DNS、DHCP、socket、TLS 未启用。`xos_lwip_rand` 基于时钟，不是安全熵。现有 package 验证不代表多进程网络服务可用。

当前验收：N1 受限 TCP 客体验收已通过（QEMU user networking、静态 IPv4、单连接），见 [验收报告](../reports/lwip_tcp_20261113/README.md)；UDP 仍未验。

<!-- /coderabbit-ai-generated:v1 -->

## 阶段

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:3bd51f0965bffac939bc3d84fce5381a7c2af3f06d5b6a146214815277f73d94 -->

1. **N1 受控 TCP 探针**：沿现有 net 服务与 lwIP raw API，连接 QEMU user networking 下的 `10.0.2.2`，由测试在宿主临时端口监听，完成实时挑战、双向字节、分次发送、关闭及失败路径（不将分次 send 等同验证 TCP 分段或重排）；在客体实测并绑定系统/SDK/源码/ELF/fixture 与日志。单连接、静态地址、QEMU 为明确范围；不称 socket 服务、DNS、TLS 或生产就绪。不可省略 sys_check_timeouts，deadline 使用单调时间，错误退出和资源回收可观察。

<!-- /coderabbit-ai-generated:v1 -->
2. **N2 网络服务契约与多会话**：盘点 net 单会话与 IPC 生命周期；设计认证、连接/地址授权、独占设备、队列与预算、进程退出/取消/重启、背压和观察错误；先按登记流程冻结 ABI，再由用户态服务持有 lwIP，普通应用不接触设备。包括恶意/失效请求、并发、撤销和资源回收。
3. **N3 TCP/UDP 客户端接口与 HTTP**：分次实现可用的连接与数据报接口及 SDK，覆盖短读写、EOF、错误、超时、并发与多应用；以宿主新鲜挑战验证真实 HTTP 状态和字节，再将它接入浏览器，不将旧 HTTP 解析器当作完整后端。
4. **N4 配置与名称**：DHCP 租约和续期、DNS 解析与错误/缓存/超时单独验收；保留静态配置的确定性对照。
5. **N5 安全传输**：有真实熵、可信墙钟和独立证书信任配置后集成成熟 TLS；验证证书链、主机名、过期、时间不可用、熵不足、对端错误和真实 HTTPS，不绕过检查。
6. **N6 glibc 与 WebKit**：按上游实际依赖做 socket/POSIX 兼容、NetworkProcess 和进程隔离，真实网站和资源/故障测试单独验收；不以探针通过宣称 WebKit 完成。

每阶段冻结源码、系统镜像、SDK、程序、工具、配置及产物哈希；保留失败/未运行并报告能力边界。设备故障、reset 失败的 quarantine、IRQ 竞态和不可信 DMA 隔离独立推进；没有 IOMMU 证明前不声称 DMA 完全隔离。网络业务和协议不进入内核。
