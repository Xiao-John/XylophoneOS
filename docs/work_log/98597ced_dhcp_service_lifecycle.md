# P0-N3：生产 DHCP/ACD、租约退役与原生 DNS

2026-11-28。基线 `f7240faae1fe1ef6f3dfae44fa21aef864849f23`，
最终本地受测源码提交 `da889821`；源码树 `e62e17a2b0be8de9623b7d4da24e8b3eb3e989bd`；系统 build `c3dfc464c631ce9e`。
公开对应源码为 `e1ee290792a0265aeb60edaaa2499a5cdfe654ac`，公开树
`a05787273d1a495c72ef58095a9effd1ed8ac753`。完整树比较只有
`docs/plans/p0_completion.md` 的 #397 reviewer 文档修复不同（5 增、3 删）；
所有生产源码、脚本与测试字节相同。两棵完整树并不相等。
本轮恢复的是此前没有留存在远端的生产 DHCP 接入，不挪用旧环境中的客体结果。
当前模块在显式安装的直连 IPv4 profile 内完成；最终组合树 P0-I 与发行 R1
各自仍须绑定其真正构建输入运行，不能由这个模块报告代替。

## 实现与可见行为

之前的 DHCP parser/lease_clock helper 已有独立资格，但生产服务仍使用固定
地址。现在 `--net-dhcp-profile` 把经过严格 JSON 校验的 server、租约范围、
gateway、resolver、有限 lease/acquisition 预算及独立 application egress
编译为安装常量。网卡初始配置全零，只有严格 ACK 和真实 lwIP ACD 均通过后
才开放地址。获取失败、冲突和租约到期没有静态或 AutoIP fallback。

锁定 lwIP 2.2.1 的第五个 patch 在 DHCP profile 宏下接入 parser、XID、ACD
和 bind hooks。其余静态构建不启用 DHCP。原始归档、patch、源文件前后像
仍逐项校验；patch 保留上游声明，修改标识和范围见端口 README。

关键授权顺序如下：

- REQUEST 只有成功交给 Ethernet driver 后才取得时间锚点；ARP 排队、重传、
  ACK 接收及同 XID rebind 不向后延长它。T1/T2/expiry 来自绝对单调纳秒，
  不再由 lwIP coarse lease tick 决定。最大有限租约的比例和分钟换算不溢出。
- 新续租生成 checked-random 新 XID，重传和 renewing→rebinding 保留该 XID。
  rebinding 可接受另一个安装 allowlist issuer，后续续租采用新 issuer。
- 严格 BOOTP/TLV、源 IP/port、MAC/XID、server/address 关系检查先于上游 parser。
  冲突后的 SELECTING 不继承 lwIP 残留的旧 OFFER issuer。
- 初次地址经真正的 lwIP ACD；冲突发送 DECLINE 并经过约十秒 backoff，整个
  获取过程共用原来的最多 60 秒绝对预算。未发布候选失效不自动刷新预算。
- 已发布配置退役时先关发送门，清 ARP 待发帧并终止旧 socket，撤销 DNS
  cache/ticket 和普通应用的两端 IPC endpoint/pending reply，再提升 epoch。
  controller 专用槽保留。单纯续租或 issuer 改变保持相同配置 epoch。
- client/UDP PCB 分配失败采用外层非阻塞重试，最多每 500ms 一次，原获取
  deadline 不变；OFF client 遗留的 ACD node 在重用/清理之前安全解绑。
  DISCOVER 的 driver backpressure 沿用上游 fine-timer 重试，同样受总预算约束。

Net2 version/header 不变，新增只读 operation 18 和固定 96-byte lease snapshot。
它公开 state、最近失效 reason、epoch、绝对租约时刻、已发布 tuple、饱和
parser/conflict/start/failure 计数。原生 SDK 验证快照结构、状态/配置、timer
严格顺序和计数关系；旧 IPC endpoint/broken peer 返回 `closed`，不自动重放
已提交请求。较高层 `client::resolve_ipv4` 同时接受有效 static/DHCP 配置；
未获地址或没有 active resolver 时不创建解析 ticket。

完整边界见 [生产服务契约](../contracts/dhcp_service_profile.md) 和
[独立 helper 契约](../contracts/dhcp_lease_authority.md)。

## 新取得的资格

使用用户指定的 XOS SDK Preview 2 常规 launcher 开发。其 bundled sysroot
来自 `498a40ce` / `152cd96f4d4e95ab`；本次重新构建了系统及 native SDK，
没有用 bundled boot ISO 代替当前源代码资格。工具为 GCC 16.2.0、
NASM 3.02、GNU ld 2.47.20260726、QEMU 11.1.3，TCG 单 vCPU。
构建为独立输出，compiler/host/QEMU 工作最多两路，未覆盖共享默认输出。

| 验收 | 实际结果 |
|---|---|
| 生产 lwIP DHCP/ACD，ASan + UBSan | 18 个独立进程场景通过 |
| 原静态 production lwIP + core，ASan + UBSan | 32 场景通过 |
| 原生产 service_loop 回归 | revoked-slot pending reply 与 recv 后超期，2 场景通过 |
| 原生 Net2 SDK | 14 组非法 lease snapshot、两种旧 endpoint 接收错误及既有严格 reply/不重放回归通过 |
| 原生高层 transport + HTTP，ASan + UBSan | native client groups=8；production HTTP framing、短写、EOF、redirect 等通过；freestanding link 无 libc 通过 |
| 可信安装 JSON | 24 个边界/拒绝用例通过 |
| ABI 文档一致性 | 通过；内核 syscall ABI 未改 |
| 真实 QEMU + 独立 wire peer | 下列 8 场景全部通过，含明确 service restart |

18 个 DHCP host 场景使用真正的 pinned lwIP DHCP、ACD、ARP、UDP、DNS 及生产
adapter/core，只有 Ethernet device、monotonic clock 和 entropy 边界由 fixture
提供。它们覆盖 renew/expire/NAK/rebind/malformed/conflict/backoff、ACK 延迟与
重传不延期、ARP deferred REQUEST 的实际发送起点、未发送 REQUEST 的 ACK
拒绝、退休 ARP 队列、最大 finite lease、退时钟、获取总期限、driver 首包
pressure、真正 UDP PCB pool 的暂时/持续耗尽。其源输入 hash 在运行前后核对。

LeakSanitizer 因 launcher 的 ptrace 环境为 **not_run**；ASan/UBSan 使用
launcher 内显式 `ASAN_OPTIONS=detect_leaks=0`。没有把 LSan 或物理 NIC 写成通过。

## 真实客体矩阵

独立 Python peer 自行构造并校验 Ethernet、IPv4、UDP、DHCP、ARP 与 DNS，
不复用生产 DHCP parser 或 lease state machine。应用从当前重新构建的 native
SDK 链接；随机 nonce 的 UDP 请求必须收到 peer 新生成的 32-byte challenge。
DNS 查询包含同一个场景的新 nonce。包捕获与串口结果相互核对。

| 场景 | 真实观察与断言 |
|---|---|
| renew | T1 单播、fresh XID、租期更新；配置 epoch 保持 2 |
| expire | peer 丢弃续租/rebind；精确 expiry 后全零 tuple、epoch 3；旧 IPC/socket/DNS ticket 关闭，较高层 DNS 返回 closed |
| NAK/config change | 旧地址 10.0.2.15 被撤销，ACD 后发布 10.0.2.16；epoch 2→3→4；旧 handle/ticket 关闭；同 hostname 在新 epoch 重新发出 DNS query，旧 cache 未复活 |
| rebind/new issuer | T2 广播沿用续租 XID；批准的 10.0.2.3 接管 issuer，address/epoch 保持不变 |
| malformed/old XID | duplicate option、截断 TLV、未获准 issuer 和旧 XID 注入；仍仅在随后合法 ACK + ACD 后发布，adapter 至少记录三个拒绝 |
| ACD conflict | 真 ARP 冲突导致 DECLINE，无地址/UDP 应用授权；DNS 返回 closed |
| conflict/backoff/recover | DECLINE 后经过规定 backoff，重新 DISCOVER/ACK/ACD，重新获得地址并完成 UDP/DNS |
| service restart | 明确 net-stop/net-start；旧 endpoint 关闭、新 PID/new discovery XID；新实例重新 ACD、取得租约并完成独立 UDP/DNS |

最终捕获 197 个 frame：73 DHCP、76 ARP、28 DNS、20 application UDP。
其中十轮 nonce/challenge 均被客体真实接收；冲突拒绝场景没有应用 UDP。
每个场景停止/等待后都恢复同一资源基线：`free=129769, tasks=2, completions=0`。
该计数来自这次私有镜像，不能据此推广为其他镜像的固定空闲页数量。

公开证据包括 [guest 报告](../reports/p0_dhcp_service_20261128/guest_report.json)、
[逐帧解码](../reports/p0_dhcp_service_20261128/network_decoded.json)、
[真实 pcap](../reports/p0_dhcp_service_20261128/network.pcap)、
[原始串口](../reports/p0_dhcp_service_20261128/guest_serial.log)、
[lease 观察](../reports/p0_dhcp_service_20261128/lease_observations.json) 和
[验收摘要](../reports/p0_dhcp_service_20261128/summary.json)。

## 可复现入口

以下命令在 SDK 常规 launcher 选定的工作树内执行；固定归档通过
`XOS_LWIP_SOURCE_ARCHIVE` 提供。不能省掉最终 fixture SDK 绑定检查。

```sh
ASAN_OPTIONS=detect_leaks=0 python3 tests/net_dhcp_stack_host.py --sanitize --output build/dhcp_host_final_v2
python3 tests/net_client_host.py
python3 tests/net_dhcp_profile.py
ASAN_OPTIONS=detect_leaks=0 python3 tests/net_service_host.py --sanitize --output build/dhcp_static_final
ASAN_OPTIONS=detect_leaks=0 python3 tests/net_transport_host.py --sanitize --output build/dhcp_transport_final
python3 scripts/build.py --output-dir build/dhcp_system_dns --net-dhcp-profile tests/fixtures/network/dhcp_profile.json --quiet-demos-on-launch
python3 scripts/build_net_dhcp_probe.py --sdk build/dhcp_system_dns/sdk --output build/dhcp_probe_dns
python3 tests/net_dhcp_guest.py --system build/dhcp_system_dns --fixtures build/dhcp_probe_dns --output build/dhcp_guest_dns
```

## 失败、修正与证据边界

首次 guest 在任何 DHCP 场景之前失败：未 arm 的 fixture 忽略了 raw NIC warmup
ARP，导致 `net-probe` gateway timeout。随后仅修正 peer 的 idle ARP 响应，
重新构建 source-bound 镜像。第一次失败的 report/串口/pcap 与原 build manifest
另存，未覆盖掉。补充启动恢复测试时也曾错误期待 DISCOVER TX pressure 使
`dhcp_start` 返回 ERR_MEM；实际 pinned 源码在该处使用 fine timer 重试。
最终测试分别注入真实 UDP PCB allocation failure 与 driver backpressure，
对应失败诊断保留在 `startup_test_development_failure.log`。

更早的 fixture 编译 -Werror/type 修正和初次 LSan --list 失败在摘要中如实
记录；其 stderr 只有工具输出，没有伪造为仍然存在的原始文件。最终资格全部
来自新 source-bound 运行，未引用丢失环境的结果。上一个八场景 pass 之后发现
高层原生 resolver 的 static-only guard，修正后又重新构建并跑完整八场景，
加入真实 DNS/cache epoch 断言；最终报告只引用最后这套输入。

报告目录的单一 `manifest.json` 覆盖全部叶子；guest report 对导出的 sibling
证据引用路径，不内嵌其 hash。机械路径模板化及原始/公开字节的转换单独列在
[转换记录](../evidence_exports/p0_dhcp_service_20261128.json)。没有改动冻结的旧
报告；也没有声称 SDK `--offline` 网络隔离得到验证。

公开路径 gate 实际结果为 `PUBLIC_READY`，包括二进制 pcap，没有 OPEN 或
UNVERIFIED。本目录 flat manifest 实际为 compliant。全仓 manifest checker
仍返回 failed：十个既有 glibc_v2/Mobius 报告目录产生 17 条旧格式/路径项问题；
本轮没有修写这些冻结报告，也没有把全仓 gate 描述为通过。具体范围见
[核对记录](../reports/p0_dhcp_service_20261128/verification.json)。

## 后续任务

P0-N3 在上述显式安装/直连 Ethernet/IPv4/单 active resolver 范围内完成。
P1-I 可从共享截止期限的多个 resolver failover、link-loss/device-reappearance
恢复和独立 physical NIC qualification 继续；IPv6、relay、持久化 INIT-REBOOT
和 profile 之外的 DHCP options 仍未实现。本轮不扩大这些兼容性承诺。
