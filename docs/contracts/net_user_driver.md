# 用户态 VirtIO-net 纵切 v1

2026-11-12。**implemented_unverified，guest qualification=not_run**。
2026-11-13 复核：在加固后的 main 上重跑 `tests/virtio_net_guest.py`，原始帧纵切
**guest qualification=passed_with_limits**（ARP TX/RX、IRQ、reset 释放、三轮资源稳定）；
TCP/DNS/TLS/不可信 DMA 隔离仍 not_run。证据见
[network_raw_20261113](../reports/network_raw_20261113/README.md)。
本轮用户授权先实现并交付可评审代码，客体证据后补；不沿用已撤回 N1 内核驱动的历史资格。

## 运行与权限路径

`scripts/run_qemu.py --network` 在现有 `pc-i440fx-10.0`、TCG、512 MiB、单 CPU profile
上显式增加 modern VirtIO-net，BDF `00:05.0`，device instance=41。默认启动仍无网卡。
新增参数为 `-netdev user,id=xosnet -device virtio-net-pci,disable-legacy=on,romfile=,netdev=xosnet,addr=05.0,mac=52:54:00:12:34:56`；
关闭网卡 option ROM，避免固件网络驱动接管设备。没有新增 host 转发端口。

supervisor 命令为 `net-start 41`、`net-stop`、`net-probe 41`。supervisor 从已嵌入的
不可变镜像目录加载 `net_service`，在现有 `spawn_options.prepare_child` 阶段对真实
building child 调 sys112 GRANT，再通过 sys81 受控通道交付 16 字节 bootstrap 消息。
服务枚举自己的 receive channel，校验 controller 与 peer 来自同一个内核授权者，随后
使用绑定自身生命周期的 grant token。普通 `exec net_service` 不因此获得设备权限。
内核授权依据是 supervisor 身份和 owned child，程序名只用于 supervisor 选择可信镜像。

内核提供的 [设备机制](device_authorization_v1.md)只授予所选 PCI function 的资源。
新增有限配置快照的原因是用户驱动需要 BAR 索引和 capability 内的偏移，已有通道和
sys112 原先占位入口不能提供这些硬件发现数据；给予 CF8/CFC 端口会扩大到整个 PCI。
因此 QUERY 只返回 grant 内设备的已清除物理 base 的只读快照，不允许扫描/写任意配置。
VirtIO 特性协商、队列、报文、ISR 读取及 reset 写入均在用户态驱动。

## 实现范围

驱动为 `src/user/drivers/virtio_net.cpp`，只实现现代 PCI capability transport，支持
`1af4:1041`，以及暴露现代 capability 的 transitional `1af4:1000`。以
[VirtIO 1.2](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html) 的
§2.6 split ring、§4.1 PCI transport、§5.1 network 为依据；不复制旧内核 VirtIO-net。

- 协商 `VIRTIO_F_VERSION_1` 和 `VIRTIO_NET_F_MAC`，不启用 offload、mergeable RX、
  indirect descriptors、event index、packed ring 或多队列。
- 两个 64-entry split queue，RX=0、TX=1；每槽 2048 字节、现代网络头 12 字节，
  最大 Ethernet frame 1514 字节（不含 FCS）。描述符、avail、used 和 buffer 使用
  sys112 分配的单个连续双向 DMA 对象，合计 66 页。
- 内存屏障发布 avail index，消费真实 used index；有界校验 used 距离、descriptor ID、
  长度和网络头。TX 满返回 BUSY，不覆盖仍由设备持有的槽。
- IRQ_WAIT 使用系统单调 deadline；驱动读取 ISR 清设备原因，再精确 ACK 内核事件序号。
  服务没有用内核 polling 代理整个帧。
- shutdown 在用户态写 reset，按单调时钟有界等待 status=0，然后 CLOSE grant。
  内核只读观察 reset 完成后回收 DMA。kill/fault 未完成 reset 时可能隔离页和设备。

## 原始帧服务协议

命名服务 `net`，定义在 `src/shared/include/xos/net_abi.hpp`，SDK 为
`src/user/include/xos/net_client.hpp`。共用既有认证 IPC channel，不新增 syscall。
报头固定 32 字节：u32 version、u32 operation、u64 sequence、i64 result、u32 length、
u32 reserved；之后 length 个字节，最大 1514。version=1、sequence 非零、request.result
与 reserved 为零，必须精确匹配线长度。响应回显 action/sequence，不携带设备 grant 或 DMA 地址。

| operation | 值 | 请求 / 响应 |
|---|---:|---|
| information | 1 | 空请求，返回 6 字节 MAC |
| transmit | 2 | 14..1514 字节 Ethernet frame；返回入 TX ring 结果 |
| receive | 3 | 空请求，返回一个 frame；当前无包返回 BUSY |
| stop | 4 | 仅 bootstrap controller 的认证 peer PID 可请求；完成回复消费后终止服务 |

服务目前同时处理一个会话，有界保存 8 个接收帧，满时丢弃最旧帧；队列容量和丢包
不是可靠传输承诺。TX 成功表示交给设备队列，不等于远端已接收。客户端超时关闭会话，
不自动重发有副作用的 TX。`net-stop` 客户端核对 peer 与 supervisor 实际启动的 PID 一致。
普通应用只能通过该帧协议访问网卡，不能映射 MMIO 或得到设备地址。

本阶段没有实现 TCP/IP socket、DNS、TLS、HTTP、DHCP、路由、多个客户端公平调度、
恶意设备隔离、共享 IRQ或SMP。它提供用户态设备收发基础，不声称浏览器联网资格。
未实现 IOMMU，获得 MMIO 的网卡驱动与设备必须受信；DMA token 和页配额不限制
驱动写入恶意总线地址，quarantine 只保护无法确认停止时的页回收。

## 可重放验证

宿主运行：

```sh
python3 tests/ipc_device_host.py
python3 tests/virtio_net_host.py
python3 tests/ipc_v1_query_compat_test.py
```

分别执行真实设备授权 store/物理 allocator（硬件边界由 shared mmap 和受控回调代替）、
真实 capability parser/split-ring 实现、旧/新 SDK 对真实 query 分支的兼容检查。
它们没有启动 guest，也不证明 PCI/PIC/页表指令或调度的正确性。

具备仓库固定工具链、QEMU 和同版本 SDK 后：

```sh
python3 scripts/build.py --output-dir build/ipc_device_system
python3 tests/virtio_net_guest.py --system build/ipc_device_system
```

网络客体探针通过 `net-probe 41` 实际发出 ARP，要求接收到 QEMU user networking
网关 `10.0.2.2` 的对应回复、至少一个 IRQ、reset 后 close=0，并比较后两轮资源基线。
首轮保留一个有界内核 observer 映射，故用首轮完成后的基线判断后续泄漏。
网络 guest runner 核对 system manifest 的全部源码/产物散列，记录镜像、命令、原始串口和结果。
IP4 bulk 沿用上游 `tests/ipc_v1_grant_guest.py` 及其公开 ABI，不另建第二套。
**本轮网络及 bulk 客体均为 NOT_RUN；没有写入或改写任何旧冻结报告。**
