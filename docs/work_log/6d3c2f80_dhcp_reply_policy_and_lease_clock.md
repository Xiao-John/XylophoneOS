# P0 DHCP 有界回复策略与绝对租约授权

2026-11-27；基线 `daf2bd24ce92525ce61054ebe585ab0e88ed06e4`。
本模块独立增加 `src/user/network/dhcp_policy.hpp/.cpp`，供网络模块接入已锁定
lwIP 2.2.1 DHCP/ACD。**本 PR 的资格是 helper host + 目标对象编译；生产服务
接入与 DHCP 真实客体仍为 not_run**，不能据此把 P0 DHCP 标为完成。

## 原因与机制

既有 N4 契约要求有限租约从实际 REQUEST 发出时刻起算，并在每次应用收发前
检查绝对 expiry。上游 DHCP 使用 coarse lease 计数，短租约会向分钟取整，
而 dhcp_bind 重置 lease-used；仅打开 `LWIP_DHCP` 不能满足这些授权要求。
上游 dhcp_create_msg 对普通 DHCPREQUEST 还会沿用旧 XID，必须在新续租事务
生成新随机 XID，并让重传保留同一个事务标识。

新增 helper 不重新实现 DHCP wire 或 ACD。固定数组 parser 全量验证 BOOTP、
MAC/XID、server/source、option framing 与可信安装策略后才输出配置。状态机
记录实际请求时间，保留同 XID 的最早成功发送，计算 T1/T2/expiry，再以一次性
candidate generation 绑定 ACD 结果。NAK 也要求实际发出的匹配 REQUEST。
路由/resolver 变化单独通知调用者提升 epoch；helper 不扩大应用出站 ACL。

换地址必须经过失效、新获取和 ACD；renewing/rebinding ACK 必须保留当前地址。
接入时会继续复用 lwIP 的 pbuf、UDP、重试与冲突检测。详细 profile、接口和
按实际源码函数列出的 hook 顺序见 [契约](../contracts/dhcp_lease_authority.md)。

## 实际验收

使用 XOS SDK Preview 2 常规 Bubblewrap launcher。SDK 源来源仍为
`498a40ce85667a72b0c79f0ce1f5c11e7690122f`、发行 build `152cd96f4d4e95ab`；
此处编译的是当前工作树 helper，不把发行镜像当作本次源码的客体证据。
宿主 GCC 16.2.0、目标 x86_64-elf GCC 16.2.0、Python 3.14.10。

以下命令在 launcher 指定的工作目录内执行：

```sh
python3 tests/net_dhcp_policy_host.py --output build/p0_dhcp_policy_host_final
env ASAN_OPTIONS=detect_leaks=0 python3 tests/net_dhcp_policy_host.py --output build/p0_dhcp_policy_sanitized_final --sanitize
```

| 测试组 | 通过内容 |
|---|---|
| 可信 policy | mask/range、列表长度、重复/尾部、基础设施地址、有限上限 |
| BOOTP 与事务 | 截断、576 字节界限、cookie、MAC、XID、硬件类型、flags、relay/ciaddr、错误源端口 |
| server 与消息 phase | OFFER/ACK/NAK 状态、选中服务器、允许的重绑定服务器、server ID/source 不一致 |
| option 与配置 | 各 TLV 长度、重复/缺失/END/填充、router 顺序、拒绝 overload/classless routes、allowlist 与地址不符 |
| timer | 缺省分数秒、显式非法 T1/T2、零/无限/超 policy 租期、`0xfffffffe` 秒 |
| 实际发送与 ACD | 无 REQUEST 的 ACK/NAK 拒绝、重传保留起点、ACK 不直接发布、generation 防旧回调、approve 一次 |
| 续租/丢失 | 精确 T1/T2/expiry、重绑定保留最早请求时间、丢失回复不延期、不同 issuer、resolver/router 变化 |
| 撤销 | NAK、conflict、link loss、stop、超期 ACK、ACD 完成时过期、长暂停、退时钟、无无限获取 |
| 64 位边界 | REQUEST 时刻 0、恰好 UINT64_MAX 的有限 expiry、加法溢出拒绝、大租期 7/8 计算不溢出 |
| 有界突变 | 20,000 次确定性 payload/length 修改；失败输出不变，成功仍满足授权范围 |

普通及 ASan/UBSan 各 14 组全部通过；目标 freestanding 对象编译通过。target
编译启用 no-exceptions/no-rtti/nostdinc++；代码不分配内存、不依赖 libc、glibc
或 newlib 布局。runner 绑定五个直接源码输入的 SHA-256，在执行结束检查输入
未变化，记录编译器、实际命令、测试名和二进制摘要。

首次 sanitizer 将 `ASAN_OPTIONS` 放在 launcher 外，launcher 没有转交该变量，
导致 LeakSanitizer 在 ptrace 环境的 `--list` 阶段报错；未执行语义用例。随后
使用 launcher 内显式 `env ASAN_OPTIONS=detect_leaks=0`，ASan/UBSan 全通过。
LeakSanitizer 为 not_run。失败的真实 stderr、旧二进制摘要与初次源码绑定另存
报告；最终 runner 也保存 --list 失败日志。没有隐藏失败或把重试当初次成功。

公开 [摘要](../reports/p0_dhcp_policy_20261127/summary.json) 记录原件和公开副本
摘要。报告只替换构建路径变量，不更改结果。平铺 manifest 绑定全部报告叶子。
SDK ordinary launcher 可工作；未声称 `--offline` 的网络隔离已通过。

## 交接与尚未完成

网络接入必须在 DHCP 解析前调用 parser，在驱动真实 TX 成功后记录 REQUEST，
在 ACD clear 后 approve；绝对 expiry 优先于 lwIP timer 和应用 RX/TX。
rebinding 的新 issuer 需同步到 dhcp->server_ip_addr。NAK/expiry/conflict/link
loss 先阻止旧流量并撤销 service_core 的连接、解析及 epoch，再清接口地址。
单次获取共享原有总期限，不能每次重试重新延长 60 秒。

还需要网络模块的真实短租约 fixture：初次获取与 ACD、T1 单播续租、失联转
T2 广播、NAK、换地址/解析器、冲突、expiry 禁止旧流量、资源回收，以及静态
配置对照。helper 的受控时钟和包突变不会替代这些组合客体证据。
