<!-- SPDX-License-Identifier: Apache-2.0 -->
# 63c043b9 — P1-A 只读观测、类型化提案与确定性回放

日期：2026-11-28，Asia/Shanghai。

## 交付状态与范围

**P1-A 已在下述限定配置完成实现和验收。** 普通只读客户端、真实 static Net2、
真实已加载 CA snapshot 与受影响 IPC 生命周期分别取得客体结果；102 份实际
observation/proposal 记录均两次求值一致。接口和离线验证器均不授予执行权限。
[资格摘要](../reports/p1_a_observation_20261128/qualification.json)、
[平铺证据清单](../reports/p1_a_observation_20261128/manifest.json)与
[导出来源](../reports/p1_a_observation_20261128/provenance.json)保留具体范围和身份。

用户把 P0 闭环交给另一条进行中的工作线，并要求本线执行阶段 1 的 P1-A。
范围依据 [P0/P1 计划](../plans/p0_completion.md) 的 AI-ready observation 行：
读状态、记录提案、重放验证，不引入模型执行依赖或自主写入。

ABI 占号已通过 [PR #421](https://github.com/Xiao-John/XylophoneOS/pull/421)
合入，merge 为 `beedb39ad04ab4519bb21bf31770ea4dcb7afc29`，登记 sys90。
最终测试基线为
`819ea63ae84b1e89862648af002c2a09d1936c02`，即 PR #430 的 merge，叠加本次
独立 `codex/p1-a-observation` 分支的修改。精确增量源字节见
[source bindings](../reports/p1_a_observation_20261128/source_bindings.json)，
完整构建 source digest、ISO 和 SDK 身份见资格摘要。实现按独立 PR 交付；
占号 PR 不替代实现 PR 或本次验收。

本线不改写 P0 的旧日志、验收结论或冻结报告，也不凭 P1-A 结果宣布 P0 已闭环。

## 实现与接口选择

| 层次 | 本次实现 | 权限与保留边界 |
| --- | --- | --- |
| Native sys90 | 48-byte v1 request、120-byte snapshot；process、resources、held service endpoint | 只读自身／直接子进程，或调用者已持有的 endpoint；非授权目标不泄露状态。身份比较发生在授权之后，期限贯穿 scan 和 copyout。 |
| 进程代次 | 每个新 PID 从 generation 1 开始；成功同 PID exec 才递增 | 失败 exec 保留旧身份和权限；溢出先拒绝提交。PID、endpoint token 与 image generation 都不是跨启动的全局身份。 |
| 用户态 endpoint | 64-byte request、208-byte response；唯一 wire operation 为 read | 双向认证 peer，owner 显式 attach 后再 authorize。grant 绑定 PID＋image generation、kind mask、次数、期限和 revision。 |
| 生命周期 | revoke、forget、close；pending reply 发送前复核 | 撤销／修改 grant 后尚未交付的数据不得借旧 capture 发布；forget 释放该消费方的连接和 grant 槽。已交付副本仍是历史授权读取。 |
| 普通 SDK client | 同一绝对期限覆盖 send/wait/receive；校验 source、caller、sequence、kind、data | source PID／epoch 来自可信配置，名称发现不授予权限。断链、超时或未知结果不会触发自动重连和重复 capture。 |
| 来源 adapter | process/service/resource 来自真实 sys90；runtime 来自 catalog.capture；network 来自认证 Net2 session；trust 来自实际 ready store bridge | provider scope 明确，不从请求中接受任意目标 PID，不把无法读取的源伪装成成功空状态。 |
| JSON 与 proposal | 六类 typed record、独立 proposal schema、显式 policy／logical time | proposal 只引用已记录的精确身份／代次；不包含执行 token 或 command payload。 |
| 离线 replay | 纯 Python 标准库；固定 schema/validator/policy v1；记录输入及实现／schema 摘要 | 同输入和同验证器字节得到同结果；模型输出作为记录输入，不假设模型生成确定性。所有结果均禁止执行授权和自动重试。 |

具体契约见 [native observation](../contracts/native_observation.md)、
[observation service](../contracts/observation_service.md)，操作说明见
[普通用户态使用教程](../usage/userland/observation.md)。实现入口包括
`src/shared/include/xos/observation_abi.hpp`、
`src/shared/include/xos/observation_service_abi.hpp`、
`src/user/observation/`、`src/user/include/xos/observation*.hpp`、
`src/ports/native_tls/observation.hpp` 和 `scripts/observation_replay.py`。
SDK 的 public headers、libxos archive 及 capability manifest 一并更新。

### Scope、预算与调度

`source.pid` 是 provider，`caller_pid` 是独立获授权的消费方。`self`／
`direct_child` 相对 provider，runtime 是其局部 controller，trust 是其应用
选择的实际 store。一次 wire read 只采样一类状态，跨来源、跨请求之间不保证
原子一致。资源记录目前只包含 generic IPC pair／name 的 per-process 数量，
不能作为 process-tree budget 或全系统资源清单。

endpoint transport 仅支持 sys84 generic endpoints，包括 sys86 具名连接
创建的同类端点，使用 sys84 peer/close 与 sys85 deadline wait。sys81
`generic_channel` 只在 native sys90 held-service **source** 中兼容；它不能
通过这里的 query_peer 认证，因此没有宣称 sys81 observation transport
已经实现或取得客体资格。发送前再次核对 live image generation 是防御性硬化。

每个 server 最多四个连接、四个 grant；每 grant 最多 64 次 capture、30 秒
有效期；每请求最多五秒。capture 按单 owner 串行运行，慢 Net2 请求可以占用
剩余请求期限，不能把 poll 视作立即返回或公平并发调度器。自定义 callback
必须遵守传入期限；服务能丢弃迟到结果，不能强制中断不返回的 callback。

### 活动 trust 的纠正

初版 adapter 只回报 owner 配置的 generation／digest，标签为
`configured_pin`。这一标签只能说明配置选择，不能满足 P1-A 对**活动已加载
trust generation**的要求，因此该做法在最终交付前被替换，而不是通过放宽
验收定义保留。

现在由可选 native TLS bridge 对真实 `native_tls::trust_store` 执行
`capture_pin`。只有完整 bounds/header/generation/SHA-256/DER/CA/duplicate
校验成功、store 已 ready 时，才复制实际 loaded generation 与完整快照摘要。
null、unready 或首次 load 失败返回 `unavailable`。独立 callback 保持基础
observation SDK 不链接 Mbed TLS；实际 native TLS 用户显式提供 bridge。

成功 JSON 唯一允许 `selection="loaded_snapshot"`。`configured_pin` 和未知
选择标签均有拒绝用例；本次尚未发布的 v1 schema、fixture 与教程同步更新。
owner 必须保持 borrowed store 存活并串行切换／销毁。loaded store 本身不可
重新 load；更新需验证一个新对象后显式选择。既有 TLS stream 拥有自己的 CA
副本，不会因这次观察自动切换或撤销，也不能据此推出握手或网络连通性通过。

## 开发环境与命令口径

开发使用 Linux x86-64 Preview 2 SDK 的工具环境。既有锁定归档 SHA-256 为
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`。
已读取系统 manifest 中的工具版本：GCC/G++ 16.2.0、Binutils 2.47.20260726、
NASM 3.02、QEMU 11.1.3。P1-A 普通 probe 是从匹配源码导出的原生 SDK 构建，
其 receipt 明确 `libc_linked=false`，不把它写成 glibc 动态应用资格。

以下均是**在所选 SDK 开发 shell 中、仓库根目录执行**的标准化命令，只使用
仓库相对路径。输出目录对应独立运行，不与 P0 共用或并发清理 build 目录；
重新验收使用新的输出目录，不能覆盖旧失败记录后把它当作原运行通过。

已取得 host 结果的入口：

```sh
python3 tests/observation_native_host.py \
  --sanitize --output build/p1_a_final_native
python3 tests/observation_transport_host.py \
  --sanitize --output build/p1_a_capture_recheck_transport
python3 tests/kernel_process_wait_race_test.py \
  --sanitize --output build/p1_a_final_process_wait
python3 tests/observation_replay_test.py \
  --output build/p1_a_loaded_trust_replay
python3 tests/docs_consistency.py \
  --output-dir build/p1_a_loaded_trust_docs
```

最终普通候选及 guest 的实际入口：

```sh
python3 scripts/build.py --output-dir build/p1_a_system_v3
python3 scripts/build_observation_probe.py \
  --sdk build/p1_a_system_v3/sdk --output build/p1_a_probe_v3
python3 tests/observation_guest.py \
  --system build/p1_a_system_v3 --fixture build/p1_a_probe_v3 \
  --output build/p1_a_guest_v3 --repeat 3
```

live static Net2 使用独立、匹配的 system／SDK／probe。构建时显式锁定
lwIP 2.2.1 归档（SHA-256 为
`83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1`）：

```sh
XOS_LWIP_SOURCE_ARCHIVE="$PWD/build/p1_a_inputs/lwip-2.2.1.tar.xz" \
  python3 scripts/build.py --output-dir build/p1_a_network_system_v3 \
  --net-static-profile tests/fixtures/observation_static_network.json
python3 scripts/build_observation_probe.py \
  --sdk build/p1_a_network_system_v3/sdk --output build/p1_a_network_probe_v3
python3 tests/observation_guest.py \
  --system build/p1_a_network_system_v3 --fixture build/p1_a_network_probe_v3 \
  --output build/p1_a_network_guest_v3 --repeat 3 --network
```

IPC 继承回归使用其已有 suite，已从最后一版系统重新构建 fixture 并执行：

```sh
python3 scripts/build_ipc_exec_probe.py \
  --sdk build/p1_a_system_v3/sdk --output build/p1_a_ipc_probe_v3
python3 tests/ipc_exec_guest.py \
  --system build/p1_a_system_v3 --fixture build/p1_a_ipc_probe_v3 \
  --output build/p1_a_ipc_guest_v3 --repeat 1 --suite lifecycle --serial-only
```

实际 ready trust store 使用新生成的本地 CA fixture。上游 Mbed TLS 归档、
只读复用的 mbedX509/PSA archive 及 signed-source glibc SDK 均先核对源锁、
工具和材料身份，再重编当前 trust/observation 代码，没有复用旧 P0 运行结果。
输入定位通过显式变量提供，以下为路径标准化后的实际调用：

```sh
python3 scripts/build_observation_trust_probe.py \
  --archive "${XOS_MBEDTLS_ARCHIVE}" --tls-build "${XOS_TLS_BUILD}" \
  --output build/p1_a_trust_host
python3 scripts/build_observation_trust_probe.py \
  --archive "${XOS_MBEDTLS_ARCHIVE}" --tls-build "${XOS_TLS_BUILD}" \
  --sdk "${XOS_GLIBC_SDK}" --output build/p1_a_trust_probe
python3 tests/observation_trust_guest.py \
  --system build/p1_a_system_v3 --fixture build/p1_a_trust_probe \
  --output build/p1_a_trust_guest_v3 --repeat 3
```

普通／network guest 的缺失 trust source 明确记录为 `unavailable`。独立
trust guest 执行真实 load → bridge → 生产 sources → 生产 JSON → replay；
其本地 provider envelope 不冒充第二次 remote grant/transport 验收。

## 已核对的 host 结果

下列报告存在，且已读取其实际 status 和结果项。host 替代边界仍然成立，
数量表示对应测试报告的分组／断言，不是额外的客体运行次数。

| 检查 | 已记录结果 | 原始报告及边界 |
| --- | --- | --- |
| Native sys90 | ASan/UBSan，6 组 PASS | `build/p1_a_final_native/report.json`；提取生产 records、实现和 syscall case，替代 clock／特权 copyout。 |
| Endpoint transport | ASan/UBSan，11 组 PASS | `build/p1_a_capture_recheck_transport/report.json`；运行生产 server/client，以确定性 host transport 替代内核边界，包括 capture 期间 peer 变化的防御性拒绝。 |
| Process wait／IPC deadline 回归 | ASan/UBSan，13 组 PASS | `build/p1_a_final_process_wait/report.json`；生产 wait/finish/deferred delivery 与 sys85 deadline/revoke 提取，guest=`not_run`。 |
| Replay | 201 项断言 PASS | `build/p1_a_loaded_trust_replay/report.json`；synthetic recorded pairs、严格 JSON／权限／期限／代次、configured-pin 拒绝、跨进程确定性。 |
| 独立 JSON Schema | 3 个 schema、8 个 fixture 通过，configured-pin 负例拒绝 | `build/p1_a_loaded_trust_schema/report.json`；独立 Draft 2020-12 validator 检查；生产 replay 仍只依赖标准库。 |
| 文档一致性 | PASS | `build/p1_a_loaded_trust_docs/docs_report.json`；该次为 2234 本地链接、79 syscall 分配、73 历史来源。最后文档门禁见下文。 |

native 与 wait 两份上述报告绑定的 `tasks.cpp` SHA-256 为
`1cdd25b308a2b5892e7d850f8a281f879a6c14fe3b115ce0d5231844f32c7005`。
各报告中的 source hashes 是对应运行的身份，不自动覆盖之后更改的源码。
loaded-snapshot 版 observation schema SHA-256 为
`b57103ea0f2f802c8f60147c678983af2c7a6d660e7c9f2ad3eaefeac4370741`。

## 初轮客体失败与旧 IPC 结果

初轮普通 observation guest 的原始报告
`build/p1_a_guest/report.json` 状态为 **failed**。已记录完成的六组为 native、
authorized、denials、quota、lifecycle、deadline，共 23 份 observation/proposal
回放；这些局部结果不构成整套完成。

随后 exec 场景确实输出了 `OBS_FAILED_EXEC_RETAINED` 和
`OBS_SUCCESSFUL_EXEC_GENERATION`，但 runner 使用过宽的 `b'OBS_FAIL'` 子串
匹配，把预期的“failed exec 保留状态”成功 marker 当作失败。现已改为精确
失败 token `b'OBS_FAIL '`／`b'OBS_NATIVE_FAIL '`，并继续要求退出码和
对应成功 markers。这个修正只纠正 runner 判定，不回写旧报告为 passed；
随后已从最后一版源重建 SDK、fixture 和镜像，并完成下述 v3 重跑。

同一旧候选的 `build/p1_a_ipc_guest/report.json` 为 **passed**，四组分别是
parent、lifecycle、authority、quota；它们确实完成了该次真实客体检查。
这份结果也不自动迁移到随后增加 loaded-trust bridge 等变化后的最终候选。

| 旧候选身份 | 值 |
| --- | --- |
| Build ID（不是 Git commit） | `c0640ebd7f7a7c2a` |
| 系统 source SHA-256 | `c0640ebd7f7a7c2a297131c7252a3dc9db69c54797db0e1027126edd2d05bdfd` |
| ISO SHA-256 | `0228670817a6385ff115873df87f0a66c9d79aa9cfd996553565f3badef87d4f` |
| 系统 manifest SHA-256 | `68c65460724745ed4294cdd565fec881930bd4b46bc72f3e82aec8c73a0ff5c5` |
| SDK tree SHA-256 | `d4040708f1895e9f32a2c7f6be1a25b2042858c5ec96ab96051225ff25e5bf25` |

## 最终 v3 验收与持久证据

| 最终项目 | 结果 | 证据及边界 |
| --- | --- | --- |
| 普通 observation guest | 7 组 × 3 轮，21 case PASS；69 组 replay 一致 | [ordinary](../reports/p1_a_observation_20261128/ordinary_guest.json)；native、authorized、denials、quota、lifecycle、deadline、exec，实际 catalog 101→102、代次与撤销等。 |
| live static Net2 | 3 轮 PASS；18 组 replay 一致 | [network](../reports/p1_a_observation_20261128/network_guest.json)；真实认证 session、非零配置 epoch、static/ready；无应用网络流量或抓包。 |
| loaded trust guest | 3 轮 × 15 项，45 检查 PASS；15 组 replay 一致 | [trust](../reports/p1_a_observation_20261128/trust_guest.json)；真实解析/失败初载/完整 pin/immutable reload/7→8→7 选择/清空，9 accepted proposal、6 unavailable。 |
| IPC lifecycle | parent/lifecycle/authority/quota 4 case PASS | [IPC](../reports/p1_a_observation_20261128/ipc_guest.json)；与普通观测、trust 使用同一最终 ISO；新 fixture 来自同一 SDK。 |
| loaded trust host | 14 项 PASS | [host](../reports/p1_a_observation_20261128/trust_host.json)；真实 Mbed X509/PSA 解析，不替代客体记录。 |
| 线程 SDK 新组件依赖 | whole-archive relocatable link PASS | [组件检查](../reports/p1_a_observation_20261128/thread_component_link.json)；8 单元按线程 flags 重编，0 强 undefined；仅保留有 syscall fallback 的原弱 console hook。不是完整线程 SDK 或 guest 资格。 |
| ABI 与许可材料 | sys90/当前 ABI PASS；两镜像各 10 项、0 open | [ABI](../reports/p1_a_observation_20261128/abi.json)及[资格摘要](../reports/p1_a_observation_20261128/qualification.json)；许可为登记材料和 SDK copy 检查。 |

普通、trust 和 IPC 的资源计数均逐场景回到 `[129793,2,0]`。网络配置有自己的
存活服务基线 `[129601,3,1]`，每轮同样精确恢复；不把相对回收写成系统全局零对象。

| 最终配置 | Build ID | ISO SHA-256 | SDK tree SHA-256 |
| --- | --- | --- | --- |
| ordinary／trust／IPC | `0036a7ffb163749b` | `3861432309eb49b4780c1f44d7e8c1af10a593a3b699b0709da4104567984312` | `cac8b07387dae073d9cde8f1c58352e1c41187ff0ee7b1866ab3d7e972b6bb94` |
| live static Net2 | `c59a2f5ac6e57ebe` | `c2762595f25503d8708cc9f84f5dcd3328c119d4d8bcc648cac5c38d00c45a8a` | `af5fda2a32bac4a1865bb10508b75c3a7c2018e187706e7b0fba9fd586881154` |

新增线程 SDK source adapter 引出了 `generation.cpp` 的 identity 依赖，评审发现
并补齐 `identity.cpp`。组件检查按实际线程宏、无 function/data-sections、无
GC 的条件纳入全部 archive 成员，确认强依赖闭合；完整线程/glibc 分发不在本次
重建范围。独立 trust ELF 是现编 source 的 signed glibc 专项组合。

v2 网络 runner 的首轮失败也被保留：静态镜像已自动发布 Net2 PID/ready，重复
执行 net-start 返回 owned-service-already-running，脚本等待第二个启动 marker
超时。修正为核对唯一的可信 boot announcement，只有没有已发布服务时才显式
启动；随后重新构建 v3 两个镜像并重跑全部四路。见
[开发失败记录](../reports/p1_a_observation_20261128/development_failures.json)。

102 份实际记录保存在 ordinary/network/trust 的 `*_replays.json` 中，分别有
69、18、15 组；输入、策略、逻辑时间和结果全部保留。独立 8 份 synthetic pair
与 201 项 host 断言单独报告。源记录／结果集中到单一叶子文件，只有平铺根清单
对导出文件计算 SHA-256。导出保留原始新运行的摘要，省略宿主命令路径和叶间文件
摘要；串口日志经无损 gzip 压缩，解压后的字节与原记录完全一致；没有导入 P0 验收正文。

最终执行并通过的定向提交检查：

```sh
python3 tests/docs_consistency.py --output-dir build/p1_a_delivery_docs
python3 scripts/verify_evidence_index.py \
  docs/reports/p1_a_observation_20261128/manifest.json
python3 tests/check_public_evidence_paths.py --index --base origin/main
```

最终 docs gate 通过：2264 个本地链接、79 个 syscall 分配、73 个历史来源。
本次证据清单 25/25 匹配，完整覆盖本目录；79 个实际暂存文件的公开路径扫描
为 PUBLIC_READY，零 findings。首轮派生组件报告残留的工具 resolved_path 已移除，
原始报告摘要、工具字节摘要和该字段变换均保留，未改变任何验证结果。

另行运行全库 `report_manifest_check.py` 时，本 P1-A 目录为 compliant，但全库
仍返回 failed：10 个既有 glibc/Mobius 报告目录有 17 条 manifest 格式或 hash
字段问题。已核对这些目录相对 `origin/main` 没有任何变更。这是保留的基线
问题，不写成全库通过，也不在本 PR 改写冻结历史报告；详情保留于本地
`build/p1_a_manifest_audit/report.json`。

## 最终必须保留的能力边界

- P0 闭环由另一条工作线推进；本线没有挪用或重分类其剩余门槛。
- runtime 记录来自实际 `activation_catalog::capture`，其 catalog 仍是单
  controller 局部、易失状态；不是持久 provisioning 或全局活动根。
- trust 成功来自 ready、已验证的 loaded snapshot；配置标签不够。观察选定
  store 不切换既有 stream 的 CA 副本，不证明 TLS 握手、连通性或全局根策略。
- 不同记录是独立采样，没有全局原子快照。资源观察不是资源预留，缺失／
  unavailable 不是“对象不存在”的证明。
- endpoint 只读；replay 只验证提案。没有模型生成依赖、执行权限、自主写入
  或未知结果自动重试。写操作仍须经过后续显式授权、预算、恢复和结果未知契约。
- 普通／静态网络测试不能推出 DHCP 租约转换、runtime ELF load、fork
  generation 客体覆盖、默认安装组合或物理 NIC 已验收；以最终报告明确列出的
  配置为准。

后续可在这条只读边界上接入实际消费者。持久写入仍以前置的 P1-B、相关
P1-C/E 授权、预算、恢复和结果未知契约为条件；本次没有增加自动执行入口。
本次合并者同步阶段路线和全局状态，P0 闭环继续由其原工作线记录。
