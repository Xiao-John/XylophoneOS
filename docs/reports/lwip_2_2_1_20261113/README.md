# lwIP 2.2.1 客体证据（2026-11-13）

| 项 | 值 |
|---|---|
| 端口 | `src/ports/lwip` |
| 上游归档 | `lwip_2.2.1+dfsg1.orig.tar.xz`，sha256 `83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1`（Debian/aliyun） |
| 构建方式 | NO_SYS 核心 + IPv4 + ethernet 编成 `liblwip.a`；手工链接 `net_ping` |
| 包 | `thirdparty.lwip-2.2.1.xpk`，sha256 `15bbd8dc4fa55e69f598e2d916360dee22994f8b98b936933179c84427c9f043`，168 个文件 |
| 客体镜像 | `build/xos-install.iso`，build `dbac77b20e54558e`（kernel 805016 字节） |

## 安装事务

```text
python3 scripts/xypm.py install --image base.img --output-image work.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json thirdparty.lwip-2.2.1.xpk
-> mutations 190, backend_sha256 0d8023a31e1aefee2e484e0e14b1db939aaac9ae4757ab40a41690a19756e7e7
```

## 客体原始输出（QEMU `--network`，VirtIO-net instance 41）

```text
xsh> net-start 41
[net-start] pid=10
xsh> [net] ready user_driver=1 raw_ethernet=1
xsh> net_ping
[net_ping] mac=52:54:00:12:34:56 ip=10.0.2.15 gateway=10.0.2.2
[net_ping] reply seq=1 rtt_ms=100
xsh> net-stop
```

- 链路：lwIP `netif` 的 `linkoutput` 直接调用 `net` 服务的 `transmit`；接收侧轮询
  `receive` 并送入 `ethernet_input`。
- 首先完成 ARP（网关 MAC `52:55:0a:00:02:02`），随后 ICMP echo request 收到
  `type=0`、`id=0x584f`、`seq=1` 的 echo reply。
- 同一轮启动/停止服务后，再跑一轮结果一致（重复运行验证）。

dash 路径（同一份包，`dash` 以 bare command 启动）：

```text
xsh> dash /tests/ping.sh
[net_ping] mac=52:54:00:12:34:56 ip=10.0.2.15 gateway=10.0.2.2
[net_ping] reply seq=1 rtt_ms=100
dash_rc=0
```

## 未覆盖

- 仅 ICMP；TCP/UDP 没有客体用例。DHCP/DNS/socket API 未启用。
- 未做丢包/乱序/MTU 边界与高吞吐测试；轮询间隔 25 ms，RTT 含轮询延迟。
- 未验证多会话/并发（`net` 服务单会话）。
- `tests/virtio_net_host.py` 在 macOS 上因 `-Wl,--gc-sections` 不能编译（宿主测试可移植性问题，
  与 lwIP/驱动无关）。
