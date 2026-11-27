# 可信安装出站规则与 DNS 权限边界

基线 `a2a33b8`。独立网络 P0 模块，不修改共享 `docs/state.md`。

## 交付

静态安装 profile revision 2 可封存最多 8 条规范 IPv4 CIDR、协议和端口区间。
构建器严格校验 JSON 字段、类型、数量、CIDR host bits、端口顺序和重复规则，
生成 C++ 常量并以原始 profile SHA-256 绑定构建。服务启动时复制规则，普通
应用没有修改接口；完整目的 tuple 在任何 connection/PCB 分配之前检查。

revision 1 和未提供新 profile 的默认地址范围仍是 `10.0.2.2/32`。UDP 67/68
明确保留给服务私有 DHCP PCB。CIDR 是安装方明确授予的整个地址范围，包括
`/0` 的广泛范围；DNS 的 A 结果与将来的 DHCP 路由配置都不能追加规则。
无效内部策略拒绝全部出站，不回退为更宽授权。

安装 profile 的 Xsh 增加已有 controller `net-dns-configure off|on` 的入口，
复用认证 PID、expected epoch、无活动连接/票据约束，只切换封存 resolver。
这不授予普通应用配置权，也不把诊断 raw DNS probe 编入生产 profile。

契约：[network_egress_policy.md](../contracts/network_egress_policy.md)。

## 验证

全部构建和执行使用已核验的 pre-release `xos-sdk-preview-2-linux-x86_64`
常规 launcher，没有声称 `--offline` 隔离通过。使用锁定的 lwIP 2.2.1 源码。

- 27 组安装 profile 入口校验与生成 C++ 编译通过，覆盖非规范 CIDR、非法
  prefix/协议/类型/端口、重复键、重复规则、超额、空规则及显式 `/0`。
- 真实 lwIP 包级 32 组和生产 service loop 2 组通过 ASan/UBSan。
  新用例证明同一地址的错误端口/协议和 DHCP 端口在 PCB/发包前拒绝；合法
  tuple 经真实 lwIP 完成 UDP echo。无效策略不会留下原宽授权。既有 TCP、
  half-close、readiness、配额、撤销与资源恢复回归通过。
- 系统 `d190e3847fa425fd` 的真实 QEMU TCG 安装 profile guest 通过。私有
  Ethernet peer 收到随机 nonce 域名后，分别返回授权 CIDR 内与范围外的随机 A。
  范围外的 A 解析成功，但 TCP/UDP open 均被拒绝；范围内 A 的另一端口和
  协议同样被拒绝，没有对应应用包到达 peer。
- 授权 tuple 收到 peer 独立生成的 32 字节 challenge。controller 将配置
  epoch 从 1 切到 2、3 后，旧 ticket 仍无效；相同 nonce 域名真正重新发出
  DNS 请求并获得另一个随机 A，再完成第二个独立 challenge。规则未改变。
  捕获的 DNS 请求计数与 peer 的 3 个事务一致，应用 wire 恰好 2 个合法 UDP
  请求；应用退出和服务 stop 后资源分别恢复到原基线。

证据：[摘要](../reports/net_egress_policy_20261127/summary.json)、
[guest](../reports/net_egress_policy_20261127/guest.json)、
[来源与产物绑定](../reports/net_egress_policy_20261127/binding.json)、
[校验表](../reports/net_egress_policy_20261127/manifest.json)。完整原始构建清单和
PCAP 保留在本地构建目录；公开 binding 保留原字节 SHA-256、完整来源映射摘要
和相关产品源码/产物哈希，runner 在执行前后校验完整 source/artifact map。
公开收据与明文 serial 使用路径占位，原始与导出后的哈希分别保留。

开发中修正了三个验证入口问题：环境不允许未使用的 QMP Unix socket，因此
明确关闭 QMP；安装 Xsh 缺少 controller DNS 开关，按原权限接入；host 的
错误策略测试改为复用单个 lwIP 实例，避免重复初始化其全局定时器池。最终
系统从修正后的完整来源重新构建并完成真实客体验证。

## 下一轮边界

本次资格为静态 IPv4 安装授权和受控私有链路，未声称公共互联网服务兼容性。
逐应用授权、动态域名权限、策略更新/签发、IPv6 和 DNSSEC 仍未完成；DHCP
使用独立 helper 与后续 lwIP/guest 接入门。TLS CA 信任不属于本模块。此次
入口为 xsh，Dash 未重跑。
