# Trusted installation egress policy

应用的连接授权由 Net2 服务持有的安装策略决定。DNS 解析结果、DHCP 的地址/路由/
resolver、普通应用传入的目的地址均不是修改授权的接口。策略在启动时复制到
`service_core`，在分配 connection/PCB 和发送任何应用网络包之前检查完整目的
地址、协议与端口。

## 封存的 profile

现有 `--net-static-profile` revision 1 保留原三个字段和最多 512 字节限制。
它仍使用默认 `10.0.2.2/32` TCP/UDP 规则。revision 2 最多 4096 字节，增加
必需的 `egress` 数组，最多 8 条规则；空数组明确拒绝全部应用出站。

```json
{
  "revision": 2,
  "pci_instance": 41,
  "resolver": "10.0.2.2",
  "egress": [
    {"cidr": "192.0.2.0/24", "protocol": "udp", "ports": [41001, 41001]}
  ]
}
```

示例是私有验证链路的明确授权，不是默认部署配置。每条规则的 `cidr` 必须是
规范 IPv4 network/prefix 字符串，prefix 为 0–32，host bits 为零；`protocol`
只接受 `tcp` 或 `udp`；`ports` 是含端点的 1–65535 整数区间。拒绝重复 JSON
字段、未知或缺失字段、重复规则、非法类型（包括把 bool 当整数）、逆序端口及
超额条目。无有效 profile 时不会静默选择一个更宽的策略。

CIDR 授予其中的全部有效目的地址，而不只授予某次 DNS 答案。`0.0.0.0/0` 因而
是安装方显式选择的广泛授权；它不会由 DNS 或 DHCP 自动产生。所有规则均额外
拒绝 unspecified、0/8、loopback、multicast/reserved IPv4 和全一广播地址。
UDP 67/68 无论规则怎样都属于服务私有 DHCP 控制流量，不能被普通应用打开。

构建器把通过校验的规则生成专用 C++ 常量，并记录原 profile 字节 SHA-256 和
规范内容到系统/lwIP 输入收据。生成的规则也经过 C++ 静态校验。应用没有在运行
时传入、替换或扩张此常量的操作；无效的内部策略同样拒绝全部出站。

## 与解析和配置 epoch 的关系

服务私有 DNS PCB 按已有 resolver 配置工作；得到一个合法 A 记录并不授予对
该地址的 TCP/UDP 权限。应用随后 open 时仍经过同一出站规则。相同地址的另一
端口、另一协议分别检查。配置 epoch 变更取消原 resolver 状态与缓存，旧票据
不能恢复使用，但出站授权副本不会改变。未来 DHCP 仅可在此相同规则下改变
接口地址和路由，不能把租约、网关或解析器字段当成新增的应用授权。

安装 profile 的 Xsh controller 可使用 `net-dns-configure off|on` 停用或重新
启用已经封存的 resolver。该入口复用服务原有 controller PID、expected epoch
及无活动连接/票据校验，不接收新的 resolver 或出站规则。普通应用仍被拒绝；
私有 raw DNS probe 仍只存在于 diagnostic 构建。

这套规则限定服务当前统一的安装授权范围；尚未提供逐应用授予、交互批准、
动态域名授权或跨进程策略管理。DNS 未提供 DNSSEC 认证。本模块不增加 TLS
证书信任，也不以私有链路测试声称公共互联网应用兼容性。
