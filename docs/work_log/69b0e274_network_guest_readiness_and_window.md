# N2/N3 客体验收：待收回复与 TCP 零窗口关闭

2026-11-25，基于 `2baed871f9d233a08258047b09863c991116dd7e`（PR #162）。
修复 review `4694707744` / `4694707755` 指出的两项验收缺口：IPC 可读只能
证明有回复，须进一步证明本轮载荷仍在队列；已接纳发送后立即 close，也须
建立可断言的未发送状态。网络服务、内核、公共 ABI、连接授权和 glibc 均未修改。

## 1. 待收载荷的撤销前置条件

`tests/fixtures/network/net_lifecycle_probe.cpp` 和 `tests/net_service_guest.py`
改用以下事件顺序，替换固定等待 50ms 和第二次 echo：

1. 客体发送本轮唯一 32 字节 nonce；宿主暂存数据，暂缓 echo。
2. 客体真实 receive 得到 `would_block` 后打印 `NET_PENDING_EMPTY`。
   宿主确认此前 echo 次数为零，再释放唯一 echo。这是可复现的空队列负对照。
3. 客体以容量 31 调用既有 UDP receive，直至得到 `buffer_too_small`、
   `flags=32`、空响应 payload。UDP 保留整个 32 字节 datagram。
4. 客体请求 receive32，等待回复可读，再用容量 95 执行既有 sys5 接收。
   实际完整回复为 `64+32=96` 字节，短缓冲返回 `-2`，不复制、不消费；
   夹具检查整个输出缓冲仍为毒化值，并再次确认回复可读。
5. 仅此后输出 `NET_PENDING_READY`。宿主撤销该 PID；客体要求从目标请求发出
   到端点失效小于 500ms，从而排除回复超时自然回收。新 PID 验证自己的
   information 回复，旧 PID 重连遭拒，最终核对资源和会话计数。

该顺序利用现有 UDP 短缓冲保留语义和 IPC 短缓冲拒收语义；没有新增 peek 或
生产调试接口。每轮只有一个宿主 echo，主机发送的 nonce、客体 receive 操作和
保留的 96 字节回复通过同一已认证会话、同一连接与连续请求序号关联。

## 2. 可证明仍有未发送字节的关闭

新增私有 `tests/net_tcp_window_peer.py`。`scripts/run_qemu.py` 和
`tests/boot_smoke.py` 增加显式 `network_peer_port` 参数，选择 QEMU socket
后端连接本地 AF_INET 端口；默认 user-network 后端保持现有行为。真实流量仍
经过同一 VirtIO NIC、用户驱动、生产服务循环、core 和 lwIP。

`tcp_queued` 场景由对端在 challenge 数据帧中广告零窗口。客体先读取其中
1 字节，确定 TCP 已处理同帧窗口更新；保留 31 字节入站数据，然后接纳
4096 字节发送。第一次 close 必须返回 `would_block`，客体排空剩余入站数据，
第二次 close 必须成功。随后通过普通 UDP 发送本轮 nonce，形成同一 NIC
报文序列上的“close 已完成”屏障。

对端收到该 UDP 屏障前始终保持 TCP 窗口为零，并要求：仅收到最初的 nonce，
没有 FIN；额外数据最多为同一序号的单字节 persist probe。对端据此计算仍未
发出的下界，验证后才开放窗口，并检查全部已接纳数据的内容、序号和最终 FIN。
此同步不依赖宿主何时读取 socket、串口打印耗时或固定 sleep。

生产 `TCP_SND_BUF=4*1460=5840`，因此零窗口测试接纳 4096 字节，留在真实
预算内。原有 8192 字节 host-socket 测试继续运行。新增 `tcp_drained` 正对照
发送 8192 字节，对端完整接收后发送一帧确认全部字节的 ACK 和应用确认字节；
客体消费该字节后再 close，保证“已排空后关闭”路径同时通过。两场景均从 xsh
和相同冻结 dash 映像执行。

## 3. 最终实际结果

最终系统 build ID **`e3f598bdd209b82a`**。使用 release
`xos-glibc-sdk-preview` 工具环境中的 GCC/G++16.2.0、Binutils2.47.20260726、
NASM3.02、QEMU11.1.3、Python3.14.10；单 CPU、512MiB、TCG、串口模式。
应用 probe 通过 native SDK 链接，未链接 libc；dash 字节沿用 PR #162。

| 检查 | 实际结果 |
|---|---|
| 原有 HTTP/UDP/TCP、多应用与重启传输组合 | 11 项 PASS |
| xsh/dash 零窗口关闭 | 各 PASS；屏障时 4096 字节均未发出，persist probe 为零；随后完整接收并 FIN |
| xsh/dash 已排空关闭 | 各 PASS；8192 字节先获 ACK 与应用确认，随后 FIN |
| 传输套件合计 | 15 项 PASS |
| 生命周期套件 | 13 项 PASS，含 12 轮待收载荷撤销 |
| 12 轮撤销前置条件 | 全部先观察 would_block；唯一 echo；保留 datagram32；IPC 回复长度下界96且未消费 |
| 12 轮撤销时间 | 全部 100–110ms，小于 500ms 回复超时 |
| 独立抓包复核 | 91 个实际 Ethernet 帧、4 个连接 PASS |
| 最终来源复核 | 1296 项系统输入、289 项系统产物、SDK tree 和全部3个 probe ELF 摘要一致 |
| 交付检查 | 证据21/21匹配；公开路径30/30通过；报告目录格式检查无失败；git diff检查通过 |

独立抓包复核不调用 live peer 的实现，逐帧验证 IP/TCP/UDP 校验和、完整 payload、
序号、窗口、UDP 屏障和 FIN。xsh 零窗口路径为 challenge 第10帧、close 屏障
第12帧、开窗第14帧、发送数据第15帧起、FIN 第17帧；dash 对应第53/55/57/58/60帧。
已排空路径的完整 ACK/应用确认分别在第43/86帧，早于第44/87帧的 FIN。

生命周期仍验证到 520ms 回复超时、59.99s 空闲回收、正常 reset/重启、强杀
保留66页 DMA、三次拒绝重新授权、平台重启恢复。资源基线仍为运行时
`129630/3/1`、停止后 `129799/2/0`、强杀隔离后 `129733/2/0`。

| 原始输入或产物 | SHA-256 |
|---|---|
| 系统 manifest | `aa9b36d8bf888fddd3c094b1ca4f6b2bbeb9727f9d542873b6cda6b0970141fd` |
| 系统 ISO | `5f5be2aaeb588d88424c56b7ed3f7042486bb324a8e2f59def1ffe225399e523` |
| SDK tree | `62e913f94c648d45d3f82ace8d27fb7bc7276c6379e8b5d6d5d3f97714e2cf63` |
| 传输报告 | `268602a46ff410a898d10f95454b522c5889fb555b25425d7136d3948deae56c` |
| 生命周期报告 | `5ede44245b544f318d28bb81542d9a1603defb01740d604ea595ed10e5c8f48d` |
| 实际窗口 PCAP | `8997580a3737a43e188c0ff4d70c684fc4916dad037333ffb609918f1fc6a1e6` |
| lwIP2.2.1 源码归档 | `83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1` |
| 冻结 dash 映像 | `0716c385f9948e29b68d1e4a3ee314b1293811bcb29c6d17a92441e5121f87c3` |

[公开证据目录](../reports/network_guest_review_20261125/manifest.json) 包含最终
两个 runner 的报告、系统/SDK/fixture 来源、串口、原字节 PCAP 的 base64、
独立解析器及结果。路径脱敏版本均记录原始来源摘要；平铺 manifest 单独绑定
公开文件。既有 `network_guest_20261125` 历史证据保持原样。

## 4. 实际失败与修正

首轮诊断 build `9af431468a02743f` 的原11项传输全部通过；新增窗口场景在
15s 截止时间失败。抓包显示 SYN-ACK 广告窗口32，使锁定上游 `tcp_out.c`
的 `mss_local=min(mss,snd_wnd_max/2)` 取16，测试先触发分段池预算。夹具修正
为握手窗口65535、challenge 同帧收缩到零；客体仍须收到 challenge 首字节后
才写入4096字节。该调整消除了额外分段压力，保留确定的关闭前零窗口条件。
首轮失败报告和 PCAP 已单独保留。最终 source 重新构建完整系统和全部 probe，
两套客体均重新运行；最后增加的抓包解析器只读取冻结结果。

## 5. 可复现命令与后续验收

在 preview 工具环境执行，允许宿主本地 AF_INET TCP/UDP，并将
`XOS_LWIP_SOURCE_ARCHIVE` 指向上述锁定归档。`DASH_ELF` 必须匹配记录的摘要。
输出使用新的目录；下列为本轮最终实际目录名：

```sh
python3 scripts/build.py --output-dir build/network_review_system_v3
python3 scripts/build_net_transport_probe.py --sdk build/network_review_system_v3/sdk --output build/network_review_transport_fixture_v3
python3 scripts/build_net_lifecycle_probe.py --sdk build/network_review_system_v3/sdk --output build/network_review_lifecycle_fixture_v3
python3 tests/net_transport_guest.py --system build/network_review_system_v3 --payload build/network_review_transport_fixture_v3/net_transport_probe.elf --output build/network_review_transport_guest_v3 --serial-only --dash "$DASH_ELF" --dash-sha256 0716c385f9948e29b68d1e4a3ee314b1293811bcb29c6d17a92441e5121f87c3
python3 tests/net_service_guest.py --system build/network_review_system_v3 --fixtures build/network_review_lifecycle_fixture_v3 --output build/network_review_lifecycle_guest_v3 --serial-only --revoke-rounds 12
python3 docs/reports/network_guest_review_20261125/verify_window_capture.py
python3 scripts/verify_evidence_index.py docs/reports/network_guest_review_20261125/manifest.json
python3 tests/check_public_evidence_paths.py --index --base 2baed871f9d233a08258047b09863c991116dd7e
```

本轮未运行实机、仓库指定 QEMU11.1.2、C++ 宿主 sanitizer、reset 无响应注入、
丢包/重排、DNS/DHCP/TLS。确定性同一 poll 轮次的 revoke/accept 交错仍由
PR #155 的生产服务循环宿主测试覆盖，客体本轮覆盖12次真实调度下的载荷撤销。
设备崩溃后的原地 DMA 恢复仍需后续设备契约；已实现的恢复路径是平台重启。
TCP ISN 加固保留在独立工作分支，本修订完成后继续推进。
