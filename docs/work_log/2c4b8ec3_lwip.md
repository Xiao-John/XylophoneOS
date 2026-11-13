# 网络纵切复核与 lwIP 端口

2026-11-13。来源：network_handoff N2 与网络契约 `net_user_driver` 的 not_run 状态。

## 1. 原始帧纵切复核

在加固后的 main（build `8dec156945c3a664`）重跑 `tests/virtio_net_guest.py`：
`status=passed, guest_qualification=passed_with_limits`，三轮 ARP TX/RX + IRQ +
reset 释放 + 资源稳定。报告与原始 JSON：`docs/reports/network_raw_20261113/`。
契约状态已注明复核结果；TCP/DNS/TLS/untrusted DMA 仍 not_run。

## 2. lwIP 端口

`src/ports/lwip`：lwIP 2.2.1，`NO_SYS=1`，零上游补丁。

- 构建 `liblwip.a`（core + IPv4 + ethernet；关闭 DHCP/AUTOIP/IGMP/DNS/socket API）。
- `net_ping` 探针：连接 `net` 服务，静态 10.0.2.15/24、网关 10.0.2.2；
  `linkoutput` → `transmit`，接收轮询 `receive` → `ethernet_input`。
- 关键点：lwIP 2.2 raw 回调收到的是**含 IPv4 头**的 pbuf，按 `IPH_HL_BYTES` 跳过；
  `net` 服务单会话、无包返回 BUSY，探针用 25 ms 截止重试。

## 3. 客体验证（build `dbac77b20e54558e`）

```text
xsh> net-start 41
[net-start] pid=10
[net] ready user_driver=1 raw_ethernet=1
xsh> net_ping
[net_ping] mac=52:54:00:12:34:56 ip=10.0.2.15 gateway=10.0.2.2
[net_ping] reply seq=1 rtt_ms=100
```

包 `thirdparty.lwip-2.2.1.xpk` sha256 `053b5430…`，168 文件；安装事务
`backend_sha256 0d8023a3…`。证据：`docs/reports/lwip_2_2_1_20261113/`。

## 4. 边界

仅 ICMP 验证；TCP/UDP/DHCP/DNS/TLS 未做；未压测吞吐/丢包；`net_ping` 需 bare
command 启动。宿主 `virtio_net_host.py` 在 macOS 上因 `-Wl,--gc-sections` 不能编译
（测试可移植性问题，另记）。
