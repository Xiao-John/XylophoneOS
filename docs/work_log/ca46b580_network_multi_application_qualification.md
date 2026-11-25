# N2/N3 multi-application isolation and lifecycle guest qualification

2026-11-25。基于 PR #155 的会话代际/TCP close 修复和 PR #158 的通用 IPC
exec 撤销，使用 release `xos-glibc-sdk-preview` 完成真实客体验收。本模块只
增加受 supervisor 身份保护的控制命令、夹具和验收工具；网络实现沿用上述
独立修复，HTTP/UDP/TCP probe 通过 native SDK 链接，无 libc 运行库耦合。

## 改动及专项契约

- supervisor `net-info` / `net-revoke` 复用 N2 控制操作和真实服务认证。
  控制客户端只操作 supervisor 自己启动的服务；普通应用的同类请求由服务拒绝。
- N3 probe 验证 unread-data close 返回 would_block，读取后正常 close；关闭前
  发送8192字节，宿主逐字节验证全部数据先于 FIN 到达。
- N2 原生进程夹具实际创建多应用、exec、fault、kill、撤销、超时与服务死亡，
  逐次核对 free/tasks/completions 和服务的 session/connection 数量。
- QEMU runner 可选择 serial-only，并保存 PCAP。每次真实交互使用独立随机
  challenge，避免把缓存响应或上一个应用的内容当作成功。

遵循 [device authorization](../contracts/device_authorization_v1.md)、
[network device proposal](../contracts/network_device_v1_proposal.md) 和
[IPC endpoint lifecycle](../contracts/ipc_endpoint_lifecycle.md)。本模块不更改
设备隔离策略：未经确认 reset 的驱动死亡必须保留 DMA 页并拒绝新 owner。

## 最终实际结果

系统 build ID **2f5890c5859e2625**。preview GCC/G++16.2.0、
Binutils2.47.20260726、NASM3.02、QEMU11.1.3，单 CPU、512MiB、TCG，
私有512MiB FAT32工作盘。网络 fixture 使用宿主本地 TCP/UDP sockets，
QEMU user-mode network；未访问外部网络服务。QMP在本环境不可用，使用串口。

| 验收 | 实际结果 |
|---|---|
| N3传输组合 | 11项 PASS |
| xsh及dash HTTP/UDP/TCP close | 各使用新challenge，精确字节/退出码/资源核对 |
| 四个同时活跃应用 | 两个HTTP、两个UDP独立challenge，全返回各自内容 |
| 未读数据和已排队发送的TCP关闭 | would_block后读取、8192字节完整发送、FIN后EOF |
| 错误service PID、关闭的远端端口 | 明确失败且资源恢复 |
| N2生命周期 | 13项 PASS |
| 跨PID连接handle及控制请求 | 拒绝；连接对象保持原owner |
| 配额 | 四应用八连接，控制会话保留，第五应用拒绝 |
| kill/cancel/exit/exec/fault | 每项连接、会话、进程资源恢复 |
| 回复和空闲超时 | 实际520ms与59.99s左右；按原60s空闲契约检测 |
| 待收数据撤销/槽复用/重连 | 12轮 PASS，每轮双向新challenge；新PID仅收自己的回复，旧PID重连拒绝 |
| 正常服务reset/重启 | 精确恢复资源，新PID重新服务 |
| 强杀服务 | 客户端收到失效；保留66页DMA，三次重新grant均拒绝 |
| 平台重启恢复 | NIC重新初始化与服务正常，停止后精确恢复原基线 |

服务运行基线为 **129630/3/1**，停止后 **129799/2/0**；强杀后的
**129733/2/0** 正好保留66页DMA。66页来自当前驱动两条队列：
`2 * (4096 + 64 * 2048) / 4096`。重新grant失败的三个building进程全部回收，
不会额外消耗页/任务槽/completion。warmup已建立固定的设备observer映射。

TCP close、并发HTTP/UDP及重启后的新响应在独立传输套件中运行；生命周期
套件确认正常reset与崩溃隔离的不同结果。当前设备契约没有原地恢复 quarantined
instance 的接口，崩溃后恢复路径为平台重启；该限制单列为后续机制设计项。

## 来源及证据

| 原始产物 | SHA-256 |
|---|---|
| 系统manifest | `95fd561f53eac7e8cc72b544332eda572521367946affc0b5dcb7d6c69d4bade` |
| ISO | `3e722682d8156e4acbd0f417d306e261fdc65d00630a56e7511671845587b125` |
| 传输报告 | `5c4bd7ab3a960e8c81595603afacb18c2bf7e3ab73db972f5e0743a6a1c81366` |
| 生命周期报告 | `4917472693a8410c47f6a32a2db705f74df44c5d1ddd080ccf39383db85d6fbd` |
| lwIP2.2.1归档 | `83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1` |
| 测试dash映像 | `0716c385f9948e29b68d1e4a3ee314b1293811bcb29c6d17a92441e5121f87c3` |

[公开证据索引](../reports/network_guest_20261125/manifest.json) 绑定15份证据；
完整系统source map、夹具SDK/ELF/tool摘要、所有challenge及串口均保留。
`derivation.json` 记录原始摘要和路径变量替换；三份 PCAP 使用原字节 base64，
解码后的摘要应与原报告一致。源码或产物前后绑定不一致时runner失败。

## 重放

工具使用preview环境；宿主需允许本地AF_INET TCP/UDP。设
`XOS_LWIP_SOURCE_ARCHIVE` 为上述锁定归档，`DASH_ELF` 为所记录的dash产物。
输出使用新目录，系统构建完成后再构建与该系统SDK匹配的两个probe。

```sh
python3 scripts/build.py --output-dir build/network_qualified_system
python3 scripts/build_net_lifecycle_probe.py --sdk build/network_qualified_system/sdk --output build/network_lifecycle_fixture
python3 scripts/build_net_transport_probe.py --sdk build/network_qualified_system/sdk --output build/network_transport_fixture
python3 tests/net_service_guest.py --system build/network_qualified_system --fixtures build/network_lifecycle_fixture --output build/network_lifecycle_guest --serial-only --revoke-rounds 12
python3 tests/net_transport_guest.py --system build/network_qualified_system --payload build/network_transport_fixture/net_transport_probe.elf --output build/network_transport_guest --serial-only --dash "$DASH_ELF" --dash-sha256 0716c385f9948e29b68d1e4a3ee314b1293811bcb29c6d17a92441e5121f87c3
python3 scripts/verify_evidence_index.py docs/reports/network_guest_20261125/manifest.json
base64 -d docs/reports/network_guest_20261125/transport.pcap.b64 > build/network_transport.pcap
```

## 已修正的验收问题与未验项

首轮串口匹配只等待PID前缀就解析余下字段，会在UART分片时误报。修正为等待
完整行，再用新源码重建全部系统/夹具。第二轮的12次撤销已通过，但runner曾
期望强杀驱动后直接重新grant成功；实际返回-11。核对设备契约后，新增正常
reset重启、强杀保留66页、三次拒绝与平台重启恢复的分别断言。两个原失败
报告保留；最终第三组合的两套全部重新运行并通过。

本环境没有执行实机、仓库锁定QEMU11.1.2、丢包/重排、设备reset无响应注入、
DNS/DHCP/TLS。强杀的隔离路径已实际运行，其他reset超时分支由后续注入补验。
确定性同一poll轮次的撤销/accept交错由PR#155生产宿主测试覆盖，客体12次
复用覆盖真实调度，二者分别记录。应用仍使用native网络接口；glibc socket和
应用DNS能力按后续专项契约推进。
