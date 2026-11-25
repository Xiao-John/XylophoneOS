# N4-C0：配置/名称契约与锁定 lwIP DNS 实测审计

2026-11-25。基于 `2baed871f9d233a08258047b09863c991116dd7e`（PR162 对应本地
组合），该基线已完成N2/N3的11项传输、13项生命周期与12轮撤销/槽复用验收。
本轮独立 worktree/分支：`codex/net-n4-contract-20261125`。范围为N4设计和
disabled DNS的真实包级宿主审计；不修改已冻结的glibc终端/文件模块或全局state。

## 交付与关键决定

新增 [network_n4_v1_proposal](../contracts/network_n4_v1_proposal.md)，明确：

- 保留用户态独占设备、原生IPC身份和静态地址对照；DNS结果、DHCP配置均不能
  扩大普通应用出站权限。配置写入只允许bootstrap controller。
- 候选op10 configuration、11 configure、12 resolve_start、13 resolve_result、
  14 resolve_cancel只作proposal；没有修改shared枚举或implemented ABI登记。
- 4个普通会话各1个ticket、全局4个上游DNS事务和4个统一缓存槽，DNS/DHCP的
  PCB与原8个应用PCB分开计数。公平轮转、速率、随机抽取、重试和解析工作均有界。
- ticket/session generation/config epoch三重身份；确定性取消订阅，最后订阅
  结束即关闭私有PCB，原deadline不因status轮询延长。配置变化清缓存、撤销旧事务。
- TTL与DHCP T1/T2/expiry使用统一绝对单调时间，长暂停后的第一轮先处理失效。
  明确NXDOMAIN、NODATA、临时失败、截断等类别，以及缓存/短期失败抑制边界。
- DNS原始报文与DHCP租约各自分阶段验收；glibc的getaddrinfo/socket属于后续适配，
  wire不包含libc私有类型、FD或errno。新接口不依赖glibc线程/TLS。

主审确认先交契约与audit，再推进端点/答案校验及有界熵的独立实现。生产DNS与
DHCP均保持0，正常系统构建的lwIP源清单保持原样。更新网络计划/接续入口和net2
契约的过期验收摘要，直接链接已有PR162证据，不改写该报告或其源绑定。

## 已执行的真实包级审计

`tests/lwip_dns_audit.py` 验证既有source_lock，解包未修改的lwIP2.2.1，只在独立
build/include目录将LWIP_DNS改为1。编译实际XOS `lwip_stack.cpp` 与真实
Ethernet/IP/UDP/DNS代码；fixture模拟本地Ethernet对端、时钟和熵状态，生成完整
ARP及校验正确的IPv4/UDP包。没有替换DNS parser或UDP callback，也未访问外部网络。
每个case为新宿主进程，使用实际初始化的lwIP内存池及动态源端口。

| 输入 | 实际观察 | 启用门槛 |
|---|---|---|
| 正常IN/A应答 | 接受期望地址，callback恰好1次 | 对照通过 |
| 错transaction ID | 未调用结果callback | 对照通过 |
| 错question名称 | 未调用结果callback | 对照通过 |
| 错server源地址 | 未调用结果callback | 对照通过 |
| 同server但UDP源端口5353 | 接受A答案 | **失败：需核对源端口** |
| 查询1应答发送到查询2的本地端口 | 查询1仍接收结果 | **失败：需绑定本次PCB/端口** |
| question正确，A记录owner为其他名称 | 接受无关A | **失败：需验证owner/CNAME关系** |
| TC置位但带A记录 | 接受不完整应答中的A | **失败：需明确截断行为** |
| opcode不是QUERY | 接受A答案 | **失败：需检查opcode** |
| TTL=2秒，poll暂停3秒后再查询 | 仍直接命中cache | **失败：需绝对expiry** |
| 改变DNSserver后再查询 | 仍命中原server的cache | **失败：需配置epoch失效** |
| 初始化后模拟sys63失败 | 4096次取随机数后调用仍未返回 | **失败：需有界、可返回错误的熵路径** |

最后一项使用生产 `random_word` 的真实错误锁存路径；fixture在4096次失败取样处
以exit42终止自己的测试进程，限定工作预算。该状态与普通成功exit0分开记录。
源码显示端口选择在返回值0时持续重试，服务无法返回poll来处理锁存错误。

最终报告为 **audit_complete_activation_blocked**：4个对照观察通过、8个启用
门槛失败。测试进程能完整重现这些结论，不能登记为DNS功能验收通过。

## lwIP 适配缺口

`dns_recv`忽略传入pcb/port并按全局ID查表；答案owner仅被跳过。上游已有随机ID、
随机源端口与同名合并选项，但端口分配失败可复用已有PCB，随机选择没有次数上限。
公开callback只给一个地址或NULL，不提供错误类别/TTL，也没有取消、flush接口。
`dns_setserver`不清旧cache；`dns_init`依赖初始零状态，不提供重新初始化语义。
DNS TTL随`dns_tmr`调用递减，而cyclic timer在过载时跳过积压周期，已通过3秒
停顿用例验证缓存寿命问题。源码路径与原始摘要见`source_audit.json`。

DHCP本轮只做源码审阅：提供获取、续期、停止/清理和ACD接点，需编入dhcp.c/acd.c；
默认500ms fine和60s coarse计数不能直接作为短租约的准确失效依据。共享UDP PCB
已connect远端67端口，不能将dhcp_recv的未用port参数单独认作缺少端口过滤。
DHCP会写netif与全局DNS配置，必须接入controller约束、完整参数校验及配置epoch。
DHCP实际报文、ACK/NAK、ACD和租约状态机仍未执行。

原生DNS需要的取消、错误、绝对TTL、配置清理与随机错误路径不能通过套一层
`gethostbyname`掩盖。下一最小修复优先收紧匹配与有界熵；完成后继续按D2/D3
推进生命周期及客体。暂不为了获得一次成功lookup而打开生产开关。

## 来源、命令与证据

| 项目 | 实际值 |
|---|---|
| lwIP archive | `83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1` |
| 宿主编译器 | Debian GCC/G++14.2.0-19；实际路径/可执行文件摘要在报告中 |
| 最终宿主ELF | `984de16f47ad818de9c38b7fce38b453ed8c3e3bb2c80a10565284704e01d130` |
| 原始最终report | `a91df096a75de4a1dd5404e346504277ac597814032a4652244253bc71035702` |
| production开关 | DNS=0、DHCP=0，原源码未改 |
| 新SDK/ISO | 未构建；本里程碑为宿主audit和契约，没有客体资格 |

```sh
python3 tests/lwip_dns_audit.py --archive "${XOS_LWIP_SOURCE_ARCHIVE}" \
  --output build/n4_dns_upstream_audit_final
python3 scripts/verify_evidence_index.py docs/reports/n4_dns_audit_20261125/manifest.json
python3 tests/report_manifest_check.py
python3 tests/check_public_evidence_paths.py --index --base 2baed87
```

输出目录必须不存在，重放使用新目录。runner先验证archive、记录生产/fixture/
构建脚本输入与编译器身份，编译及运行后再次核对，捕获每条命令及实际返回码。
屏蔽可能改变头/链接查找的宿主环境变量。早期相同fixture得到相同4+8观察；
补齐编译器和abi_types来源后重新执行最终组合，两个原始报告均保留在build。

公开证据在 [n4_dns_audit_20261125](../reports/n4_dns_audit_20261125/manifest.json)，
4份叶子由平铺清单覆盖。路径规范化派生记录保留原始report摘要及转换规则，
不把导出字节的摘要当作原件。协议设计参考RFC5452、RFC2308及其失败缓存更新
RFC9520、RFC2131；链接与章节在契约和`source_audit.json`。

## 未运行与下一位接手

本轮未运行ASan/UBSan、QEMU DNS/DHCP、DHCP状态机、glibc resolver/socket或外部
DNS。DNS生产启用前须先修复八项门槛，再补取消/撤销/同名独立订阅、错误分类、
满额度释放与绝对TTL回归；正常和sanitizer都通过后，使用release preview构建独立
系统/原生SDK，并通过私有fixture新nonce与随机A结果进行真实客体验收。

提案的操作值、payload固定布局和新增错误数值仍需独立登记；本分支不能作为已
支持这些操作的ABI。DHCP的T1/T2/expiry及地址/resolver变更交付独立PR；原有静态
N2/N3对照与源绑定报告保留，组合修改后按影响范围重新运行。
