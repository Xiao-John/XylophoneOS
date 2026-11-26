# c4201d53 · N4 私有解析生命周期客体验收

实现 `7ca3fdc3` 在锁定的 lwIP 2.2.1 上补充私有取消、清空、绝对正 TTL 和
事务重传期限。`c4201d53` 让验收区分 VirtIO 首次授权的 reset observer 与
解析进程的实际资源。受信 Xsh 用既有设备授权启动 `net_service` 诊断，固定本地
resolver，保持内核和共享 net2 ABI。
[N4 契约](../contracts/network_n4_v1_proposal.md#55-d2-私有生命周期诊断)

## 实际构建和客体

以本机 x86_64-elf GCC/G++ 16.2.0 重建 `56fd999ae921972a`，使用 QEMU
11.1.2 和私有 loopback socket Ethernet peer。peer 自行选取三个文档保留网段
地址，首次返回两个直接 A，TTL 分别 30 秒与 1 秒。客体命中第一地址，取消同名另一
订阅后的有效订阅仍收到结果。常规缓存命中使用变大小写和带末尾点的名称。暂停维护
循环 1.25 秒后，直接查找已看见短 TTL 到期并实际重发，读到另一个地址。peer
还观察独立取消与清空前的两笔正常查询。四笔报文均以实际 VirtIO 发送。

进程退出码为 0，设备关闭成功。首次独立 ARP 暖机确认设备并初始化原有 reset
observer，消耗一页。DNS 前后均为 129693 空闲页、3 个任务、1 个完成记录。
[原始客体回执、串口和抓包](../reports/n4_dns_lifecycle_20261126/manifest.json)

首轮原回执 `1c6600dc33a134e173fd0a5bbeeaa1915c42ad7002f13cb95b8838db523eb048`
由严格 peer 判定失败。实际抓包确认新查询发出后立即遇到上轮过期维护 tick 而重传。
改用每个事务的绝对最早重传时间。次轮原回执
`012a134c61065cac7b148076866cfef2fbeda425b488ea950cca4e1e997d26e9`
四笔 DNS 请求符合预期，但首次设备授权建立 reset observer，使未暖机基线多计一页。
独立 ARP 暖机后按最终冻结源码重建，所有客体检查通过。

## 普通网络与许可回归

普通镜像 `f88d6e70eedba0ff` 没有诊断解析符号，保留同一 net2 配置。完整 N2
QEMU 复验通过 13 项及 12 轮撤销，覆盖多会话、授权、关闭、重启和资源恢复。
较早的普通复验在行为检查后因诊断测试源码同时修改而未通过最终摘要绑定，最终结果
来自同源重建。两种镜像各通过 10 项许可材料检查，开放项为零。既有 D1 43 项及
N2 25+2 项宿主 ASan/UBSan 控制复验通过。宿主 D1 使用旧 DNS 选项，私有 D2
生命周期的直接证据来自上面的真实客体。
[普通 N2 回执](../reports/n4_dns_lifecycle_20261126/n2_guest.json) ·
[宿主回执摘要](../reports/n4_dns_lifecycle_20261126/host_checks.json)

明确保留直接 A 的单 resolver 诊断范围。生产 DNS/DHCP 关闭。下一组在原有 net2
认证会话上接入经登记的 ticket/config epoch 和准确的 NODATA、NXDOMAIN、REFUSED
等错误，验证跨应用、停止与期限。DHCP 继续按独立租约门推进。

## 入口

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP" python3 scripts/build.py --net-dns-probe \
  --output-dir build/n4-dns-system
python3 tests/net_dns_probe_guest.py --system build/n4-dns-system \
  --output build/n4-dns-guest
```
