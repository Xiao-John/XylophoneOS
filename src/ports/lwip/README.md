# lwIP 2.2.1（XOS 端口）

用户态 TCP/IP 协议栈（NO_SYS=1），以 `net` 服务的原始以太网帧为链路层。

## 状态

`guest_verified`（2026-11-13）。上游零补丁。

- 包 id：`thirdparty.lwip`
- 目标 profile：`xos-x86_64-static-single-b2-v1`
- 已验证包哈希：`15bbd8dc4fa55e69f598e2d916360dee22994f8b98b936933179c84427c9f043`
  （由本目录配方构建；换 SDK/上游/配方后必须重算并更新 `port.json`）。

## 交付

| 路径 | 内容 |
|---|---|
| `/usr/bin/net_ping` | 探针：连接 `net` 服务，静态 IP 10.0.2.15/24，ICMP echo 网关 10.0.2.2 |
| `/usr/lib/liblwip.a` | lwIP core + IPv4 + ethernet（TCP/UDP/ICMP/RAW，无 DHCP/DNS/IGMP/socket API） |
| `/usr/share/lwip/include/` | lwIP 头文件、`lwipopts.h`、`arch/cc.h`、`xos_lwip.h` |

## 构建

```sh
export XOS_SDK=/path/to/xos_sdk
export XOS_SOURCE_ARCHIVE=/path/to/lwip-2.2.1.tar.xz
export XOS_OUT=/path/to/out
python3 build.py
```

配方会核对 `XOS_SDK` 树哈希是否登记在目标 profile 的 `sdk_tree_sha256`；用开发树
`build/sdk`（未登记）构建时需设置 `XOS_SDK_UNREGISTERED_OK=1`。

配方编译 `NO_SYS=1` 的 lwIP：核心 + IPv4（不含 DHCP/AUTOIP/IGMP/DNS）+ `ethernet.c`，
链接 `net_ping.cpp`（`sys_now`/`LWIP_RAND`/diag 由端口的 `xos_lwip.h` 提供）。

## 安装与验证

```sh
python3 scripts/xypm.py install --image base.img --output-image work.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json thirdparty.lwip-2.2.1.xpk
```

客体（QEMU 需 `--network`，即现代 VirtIO-net instance 41）：

```text
xsh> net-start 41
[net-start] pid=10
[net] ready user_driver=1 raw_ethernet=1
xsh> net_ping
[net_ping] mac=52:54:00:12:34:56 ip=10.0.2.15 gateway=10.0.2.2
[net_ping] reply seq=1 rtt_ms=100
```

`net_ping` 不启动设备：先由 supervisor `net-start <instance>` 授予设备并启动 `net` 服务，
再由探针通过命名 IPC 连接。`net-stop` 停止服务。

## 已知限制

- 只验证了 ARP + ICMP echo；**TCP/UDP 未做客体用例**，DHCP/DNS/socket API 未启用。
- 静态地址 10.0.2.15/24、网关 10.0.2.2 固定为 QEMU user networking 配置；没有 DHCP。
- lwIP raw API 的接收回调收到的是**含 IPv4 头**的 pbuf（lwIP 2.2 行为），探针按 `IPH_HL_BYTES` 跳过。
- 轮询 `net` 服务：`receive` 无包时返回 BUSY；探针以 25 ms 截止重试，吞吐/延迟未优化。
- `net_ping` 需以 bare command 启动（有 spawn/IPC 权限）；通过 `exec-file` 启动的程序仍需
  满足 SL3 授权契约。
