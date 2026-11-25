# N4-D1：DNS 端点、直接答案与有界熵

2026-11-25。基于本地`8f4dd18c4fa78811d9eee8322b6bcad04f662bb7`，对应
PR165的等价树`591303372d66db41ca51ae72d3dfee05a66b388a`；远端C0提交为
`d8e36e4dbec101c7646c58b4c1a74bfa32367f54`。独立分支
`codex/net-n4-dns-hardening-20261125`。本次只完成DNS后端D1；生产DNS/DHCP均为0，
候选op10–14、共享线协议、普通应用目的地址授权和全局state保持原有状态。

## 修改与决定

来源固定为lwIP2.2.1原归档，SHA256为
`83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1`。
新增两份真实git format-patch，依序列入`src/ports/lwip/source_lock.json`和
`port.json`。每份记录patch摘要以及每个修改文件的前/后像；原始BSD声明继续保留，
本地新增贡献按Apache-2.0说明。没有升级上游或改写C0审计证据。

| 修改 | 作用 |
|---|---|
| `0001_dns_reply_validation.patch` | 匹配查询实际PCB、server源地址/53端口和本地单播目的地址；校验QR/opcode/TC、完整question、直接A owner、压缩与长度；整个answer section有效后才发布结果 |
| `0002_dns_bounded_entropy.patch` | 可返回错误的随机钩子；源端口和ID各最多32次抽取；熵/资源失败即时返回；不共享其它查询的PCB；失败的新准入释放私有PCB且不触发callback |
| `lwip_stack.cpp/hpp`、network私有头 | `random_checked`区分成功值0和错误；fatal锁存后停止link_output，已有UDP连接也不能继续出帧 |
| `lwip_service_build.py`、raw端口配方 | 原归档校验后在私有副本应用补丁；禁fuzz，核对整个解包树的实际变化只等于登记后像；manifest/receipt记录patch输入 |
| `lwip_dns_hardening.py`、真实帧fixture | 43项正反例，使用生产栈与真实lwIP parser/UDP/内存池，不替换DNS callback为模拟结论 |
| `net_service_host.py`与fixture | 原N2回归使用同一patched来源；新增运行期熵错误下已有UDP禁止发送与PCB全部回收检查 |
| `lwip_target_compile.py` | 使用显式release SDK/toolchain编译当前原生网络，以及仅测试配置启用的DNS C单元；记录实际依赖文件、工具和对象摘要 |

`extract_source`保留为原始解包入口，供历史C0审计在其对应revision重放。
正常服务和raw端口配方使用`prepare_source`。raw包在source/receipt及
`usr/share/lwip/patches/`保留补丁；2026-11-13旧XPK资格在原报告中继续保留。
当前端口配方尚未重打XPK，`port.json`回到`source_locked`并移除对旧包哈希的当前绑定。

## 接收与失败语义

当前只验证单接口静态IPv4、IN/A直接地址profile。压缩允许指向报文内先前位置，
每个名字最多16次指针跳转、展开后最多255线字节；明确校验label边界和整个query，
不会把短前缀或带点的单label等同于原名称。同名多条直接A返回首条，但先验证整个
answer section，后续截断或伪owner不能被首条正确A掩盖。

错误ID、question、源地址/端口、别的查询端口、广播/多播目的地址、非QUERY opcode、
TC、未知RR/class、CNAME和畸形内容均丢弃并保留原查询。每个反例之后发送正确回复，
实际验证原查询仍能完成且callback恰好一次。authority/additional不作为A答案来源。

每个新准入先取得独占PCB/随机源端口，再选未冲突ID。端口或ID的32次预算耗尽
返回lwIP `ERR_USE`；PCB不足返回`ERR_MEM`；真实适配器熵失败返回`ERR_IF`并锁存
stack io。成功的ID可以是0。返回`ERR_INPROGRESS`前的失败没有callback、没有查询包，
已经取得的PCB立即归还。碰撞/池耗尽不会干扰已有查询，释放后能重新填满。

## 实际运行结果

| 检查 | 结果与边界 |
|---|---|
| DNS普通构建 | 43/43通过，实际Ethernet/IP/UDP/DNS帧及生产适配器 |
| DNS ASan/UBSan | 同43/43通过；`detect_leaks=0`，LeakSanitizer未运行 |
| 原N2普通回归 | 25个生产栈场景+2个生产service_loop场景通过 |
| 原N2 ASan/UBSan | 同25+2通过；含TCP未读RX close、排队TX、FIN段压力、旧槽回调及实体PCB压力 |
| release preview编译 | GCC/G++16.2.0；28对象通过：22个生产lwIP C单元、5个网络C++编译目标、1个test-only DNS单元 |
| 端口结构检查 | `scripts/ports.py check src/ports/lwip --json`通过；patch顺序/format-patch/登记一致 |
| 源码许可材料 | 解包COPYING与`licenses/lwip.txt`逐字节相同；components修改说明已同步 |

43项DNS覆盖五个正常回复形态（普通压缩、混合大小写无压缩、部分压缩、同名多A、
16级压缩），ID/question/源及目的端点错误、QR/opcode/TC、owner/class/type、
RDATA/answer计数、压缩越界/自指/前向/17级跳转、CNAME，以及端口/ID熵失败、
0值ID、32次非法端口/端口碰撞/ID碰撞、4查询满额与真实UDP池耗尽。
每个完成或失败准入场景都用真实UDP池验证剩余/全部槽归属。

宿主peer、单调时间和熵提供者由fixture控制；生产parser、UDP、PCB池、适配器与
service_loop执行真实代码。此处证明确定性的故障处理与解析行为；真实sys63品质、
网络设备时序和新组合客体仍按相应门槛验证。

### 中间失败与修正

第一轮39项普通/sanitizer及N2普通通过。继续审查发现ANY绑定的DNS PCB还能接收
广播目的地址，于是新增完整有效UDP校验和的`255.255.255.255`反例。
`build/n4_d1_destination_probe`实际运行到第32项时失败：旧的D1中间实现已经发布
callback，fixture因“invalid frame cannot complete either query”以SIGABRT退出。
原报告与输入摘要保留；没有把该次运行计为通过。

修复后加上有限广播、子网广播、组播和其它单播四项，再重建完整43项普通/ASan、
N2双构建与preview目标。最终结果绑定修正后的源码；早期39项结果只保留执行历史。

## 复现与来源

```sh
python3 tests/lwip_dns_hardening.py --archive "${XOS_LWIP_SOURCE_ARCHIVE}" \
  --output build/n4_d1_normal
python3 tests/lwip_dns_hardening.py --archive "${XOS_LWIP_SOURCE_ARCHIVE}" \
  --output build/n4_d1_sanitizer --sanitize
python3 tests/net_service_host.py --archive "${XOS_LWIP_SOURCE_ARCHIVE}" \
  --output build/n4_d1_n2_normal
ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
python3 tests/net_service_host.py --archive "${XOS_LWIP_SOURCE_ARCHIVE}" \
  --output build/n4_d1_n2_sanitizer --sanitize
"${XOS_PREVIEW_RUNNER}" python3 tests/lwip_target_compile.py \
  --archive "${XOS_LWIP_SOURCE_ARCHIVE}" --output build/n4_d1_target
python3 scripts/ports.py check src/ports/lwip --json
python3 scripts/verify_evidence_index.py docs/reports/n4_dns_hardening_20261125/manifest.json
python3 tests/check_public_evidence_paths.py --index --base 8f4dd18
```

复用输出时选择新目录。宿主实际使用Debian GCC/G++14.2.0-19；runner清理影响
头/链接查找的环境，记录编译器、patch工具摘要，执行后重新核对输入。目标编译
使用release `xos-glibc-sdk-preview`容器内GCC/G++16.2.0与SDK
build_id `152cd96f4d4e95ab`；当前共享XOS头来自本分支，C标准头来自该SDK。
只进行freestanding编译，没有把该release的现成libc/对象混入新glibc SDK。

| 最终产物 | SHA256 |
|---|---|
| 普通DNS宿主ELF | `2b3432d9c73986985fc545b114baf6f80920ed5a68cbed27719cbcf9a4651b7d` |
| sanitizer DNS宿主ELF | `9199561decbbb5ca3b267e3601df8c5a762214c8a6dfbb2542ed088c69f657dc` |
| 普通原始report | `3e41a2857b72dcee751effee763eade1c596dd90fc9bfe2a5adab2e25869cfab` |
| sanitizer原始report | `2f97d2a505ead274f7b9d18e494d903397ec2f2faa5efa09ddbad4bf4b7064b3` |
| preview编译原始report | `15012188831e3fd2399e9ee0dda5ec3885998ae4e65ad33c8fc7b8042c8929a4` |

完整公开证据位于[n4_dns_hardening_20261125](../reports/n4_dns_hardening_20261125/manifest.json)。
路径规范化派生文件由平铺manifest覆盖；`derivation.json`保留各原始文件摘要、
转换规则与中间失败。源码输入摘要、上游patched文件、工具/SDK清单和对象都分别
绑定，Git提交作为完整性的信任根。

## 尚待完成与下一步

- D2：绝对TTL/最小相关TTL、config epoch与旧cache清理、细分错误、名称/报文准入、
  同名独立订阅、cancel/revoke/退出/全局fatal/stop注销全部既存pending和资源回收。
  当前TC只丢弃；NXDOMAIN/NODATA等仍不能从NULL callback准确映射。
- D3：真实QEMU DNS、私有fixture新nonce/随机A/PCAP、缓存命中/过期、跨应用撤销、
  故障重启及source/SDK/ELF/ISO绑定。当前没有新SDK/ISO或该源码组合的N2客体重验。
- DHCP状态机/ACD/T1/T2/expiry、配置改变DNS/应用连接、glibc resolver/socket均未运行。
- raw探针新XPK和SDK复制声明的完整license-audit未运行；当前仅目标编译和源码声明
  核对，完整产物审计留到实际重建。未对上游新增签名或另行授予发行资格。
- 此次审查还纠正了net2契约中TCP ISN的过期说明：实际`tcp_next_iss`仍用上游
  static iss+ticks。后续独立模块采用受审阅的lwIP hook与sys63，验证任何熵失败在
  SYN前拒绝并回收，避免把初始化随机调用误写成每连接ISN已不可预测。

保持生产DNS/DHCP关闭，按D2、D3及DHCP独立门槛继续。TCP ISN安全修复可以独立推进，
无需等待名称解析对外接口；现有目的地址授权不随DNS答案扩展。
