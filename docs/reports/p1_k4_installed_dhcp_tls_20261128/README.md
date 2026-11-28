# P1-K4 已安装 DHCP/TLS 与动态 GNU 组合

## 选定构建

| 项目 | 身份 |
| --- | --- |
| 系统 build | `13648be5fde3bd78` |
| profile | `xos-x86_64-glibc-k4-dhcp-tls-c3581f3c3f99` |
| 安装盘 SHA-256 | `6ccf0fbea5d8aa46ad90a6857da4489c6cd9e1d6f82abba3796456a4b99446ce` |
| XPK SHA-256 | `6f1ecb1d7456bc8baff47d9bbb462feadcf4befc7b049e076bc36e0afec499ef` |
| profile SHA-256 | `f46c32882f29fc651a29a403aefc63e433dabae9605c9f49b5ac28baa88a9e3c` |
| GNU native ABI | `c080a98581ac683150ce49f79fccc85cef737bb26a7d62afa6ca0181505696e3` |

## 实际结果

最终组合 **passed**：9 组检查、3 次 cold boot、12 个动态 GNU caller，
独立 peer 记录 10 条真实 TLS 1.3 连接，其中 7 条成功路径验证双方 close_notify。
四对象生产 preflight 全部 error=0、closure=0；guest 后 source、runtime、双 SDK、
application、controller 及系统产物的完整复核通过。

| 验收项 | 实际结果 |
| --- | --- |
| 冷启动 | 3 次均由普通 Xsh 自动 DHCP/ACD；首轮没有手动网络启动 |
| GNU 运行 | 12 个 caller 的 constructor TLS=17、main TLS=19、errno 正确；pthread_create=ENOTSUP |
| 续租 | epoch=2 不变，expiry 49.19s → 55.19s，原 live stream / same session |
| 租约到期 | armed expiry=73.19s，失败于 73.20s（+10ms），早于 87.58s 原 deadline |
| 有序停止 | pending TLS 在 0.145758s 内失败；PID 9 → 21，旧 PID 在 DNS/TCP 前拒绝，新 caller 成功 |
| 信任选择 | stale pin 在 DNS/TCP 前拒绝；安装的 generation 2 明确选择后真实 TLS 成功 |
| netd kill | pending TLS 在 0.100511s 内失败；3 次 regrant 返回 UNKNOWN(-11) |
| 资源 | running=[129589, 3, 1]；无 service=[129765, 2, 0]；隔离后=[129699, 2, 0] |
| DMA 与冷恢复 | 准确保留 66 页；第三 boot 自动 DHCP + GNU/TLS，恢复原 running 基线 |
| 安装归属 | 三个 boot 后 20 owned files、完整 package DB/index 逐字节不变 |

资源数组依次为 `[free_pages, tasks, completions]`。caller 正常回收的结果与必须
保留的 crash DMA 分开报告；最终 isolation 基线不是把那 66 页算成已释放。

## 资格边界与实现

本报告绑定一个具名组合：普通 Xsh ISO 引导，加一份经 XPK 事务安装的持久 FAT 盘。
三个 cold boot 连续使用同一测试安装盘；每次首轮调用前均无手动网络启动命令。
启动 ISO 内封闭的 DHCP 策略与磁盘中的部署记录、GNU 程序、控制器、运行库和
信任根由专属 profile 精确绑定。本报告不宣称新增硬盘引导或默认发行版联网能力。

动态闭包有 bootstrap、GNU interpreter、GNU PIE 与 GNU libc 四个对象。真实
GNU constructor 的初始线程局部值为 17，main 为 19，errno 正确；没有
`libgcc_s` 的 C-only 闭包按已有契约拒绝 `pthread_create`，fixture 实际检查
`ENOTSUP`。profile 不声明 threads/cxx_runtime。本报告中的 TLS 1.3 加密连接
运行在这个真实 GNU 主线程中，不把它误称为 GNU 工作线程资格。

续租与到期检查通过原已认证 Net2 session 使用现有 operation 18；TLS stream
保持原来的 29 秒 absolute deadline，不开第二 session、不重连、不重放应用 I/O。
独立 peer 只有在真实 TLS 握手及全新应用请求后才停止 DHCP ACK，调用者随后读取
当前 lease 的精确 expiry。成功场景使用真实 OpenSSL TLS 1.3 peer、全新 nonce
及双方 close_notify，DNS/DHCP/ARP/TCP 数据均来自客体实际 VirtIO/lwIP 路径。

同 boot 恢复仅用于有序 net-stop：确认 reset 后启动新服务 PID，拒绝旧 PID，再
运行新 caller。真正 kill 的未确认 DMA 继续隔离，三次 regrant 必须返回
UNKNOWN(-11)；第三次 cold boot 才恢复。它不解除既有隔离或宣称同 boot crash restart。

## 源码与运行库身份

本次 consumer 的 2309 个 system inputs 全部冻结；为完整 runtime metadata 验证，
快照另补 13 个由原 runtime hash 逐项核对的文件，包括 README、start.S 和源认证
材料，已有 system 字节和产物不变。GNU runtime 继续使用原
`f97ddece8146fb7a4bd2eadfdd4845757557611b` 身份。

冻结源核验覆盖 14 recipe、303 port、150 native 条目，合并为 388 个 Git blob；
原 native snapshot 和 9 个 runtime 产物完整复核。18 个实际 .d 文件对应 18 个
链接 archive member，52 个真正使用的 native 输入、公共 startup ABI 以及完整
C SDK 均与新 consumer 相同。唯一未编译输入差异是新增 convenience method 的
net_transport.hpp。它没有进入任何 runtime object，报告没有把旧 runtime 改称
新源码构建。完整证明随已安装 profile 保存。

## 证据使用

- [guest.json](guest.json)：独立 guest 资格、每个 caller 输出、peer wire/TLS 记录、
  三个 boot 的资源和安装归属校验。serial logs 与 pcap 各有三个 gzip 文件。
- [builds.json](builds.json)：系统、完整双 SDK、四对象闭包、XPK、安装盘、profile、
  GNU runtime、工具和虚拟机身份。
- [profile_selection.json](profile_selection.json)：已安装 profile 的派生展示；该文件
  自身不是安装盘中的原始 profile 字节。
- [source_bindings.json.gz](source_bindings.json.gz)：完整所选源码 hash 映射。
- [source_authentication.json](source_authentication.json)：GNU source 认证与 PIC CRT
  提取范围。全部 archive 已验证签名/hash；没有执行 GNU 上游 testsuites。
- [attempts.json](attempts.json)：保留失败与诊断尝试，均不因最终通过晋升为资格。
- [publication.json](publication.json)：原件来源与派生变换。raw origin digest 只标识
  未公开的本地原件；公开兄弟文件仅由 [manifest.json](manifest.json) 平铺校验。

公开日志对非 UTF-8 字节作转义、替换宿主路径并确定性 gzip；pcap 仅确定性压缩。测试私钥未安装或发布。
Producer receipts 保持 built_not_run / installed_candidate_not_run；组合通过的事实
仅由独立 guest report 给出，不修改 producer 的历史状态。

## 交付检查

文档检查通过（2353 local links、79 syscalls、73 history sources）；所选暂存差异
44 个文件全部 PUBLIC_READY、无 finding。当前报告 28 个叶子全部平铺校验通过。
全仓报告检查保留 17 个未改动的历史 schema/hash 错误；本目录独立 compliant，
不把全仓结果记成通过。实际结果保存在 `validation.json`。

## 未运行范围

物理 NIC、SMP、一般 Internet CA bundle、可信硬件时间/熵、断电、硬盘直接引导、
任意 online dlopen、新的 pending dynamic capsule ABI，以及本 C-only 闭包的 GNU
工作线程均未资格化。既有 static、DHCP、TLS 或单组件成功不能替代本组合结果。
重放命令和开发选择见 [工作记录](../../work_log/8ddc932a_p1_k4_installed_dhcp_tls.md)，
接口语义见 [组合契约](../../contracts/installed_dhcp_tls_composition.md)。
