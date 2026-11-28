# P1-K4：已安装 DHCP/TLS 与动态 GNU 组合

## 范围与交付边界

本组实现并验收 `p1_k4_installed_dhcp_tls_v1` 具名组合。它使用普通 Xsh
启动 ISO 和经 XPK 事务安装的持久 FAT 盘，将编译时封闭的 DHCP/bootstrap
策略、动态 GNU 调用者、控制器、运行库、租约身份及两代显式 TLS 信任根绑定在
同一 profile。首轮启动及崩溃后的冷启动均由普通 Xsh 自动启动网络服务，调用者
启动前不执行 `net-probe`、`net-start`、静态回退或运行时改配。

范围来源是 [P1-K4 验收项](../plans/p0_completion.md)，详细语义在
[安装组合契约](../contracts/installed_dhcp_tls_composition.md)。基础提交为
`f9139df5`，另保留主协调者的 GCC PIC CRT 解压优化，cherry-pick 后为
`f97ddece8146fb7a4bd2eadfdd4845757557611b`。该优化完整验证签名与 archive
hash 后仅跳过路径组件为 `testsuite` 的成员；本组真正编译了 PIC CRT，未执行
上游测试套件。本组不更新共享 ABI 登记或 `state.md`，由主协调者交付时汇总。

这是现有支持的 **ISO 引导 + 已安装数据/应用盘**。不新增 BIOS 硬盘启动，不
改称通用默认发行版已经开启网络，不使用 live ISO 临时导入应用冒充已安装盘。
运行器只复制完整安装盘，三次冷启动连续使用这一份盘，并在每次关机后核验完整
包归属数据库、索引与全部受管理文件。

## 实现

- `scripts/installed_dynamic_tls_support.py` 生成隔离的测试 CA/leaf 与 trust
  snapshot，并从现有锁定的 Mbed TLS 4.1.1 archive 构建 PIC 静态加密代码。
  私钥留在测试构建目录，不进入 XPK 或公开证据。
- `scripts/build_installed_dynamic_tls.py` 以完整 C SDK、native SDK 双锚及
  现有 public-startup GNU runtime 为输入，构建真实 GNU PIE、bootstrap、
  interpreter/libc 与 generation record，并运行生产装载器 preflight。
- `scripts/package_installed_dhcp_tls.py` 严格验证 system、完整父 SDK profile、
  程序、控制器、运行库、封闭网络策略和信任根，创建专属 profile，以现有离线
  XPK 事务安装完整闭包、控制器、策略/部署记录和许可证材料。
- `scripts/verify_installed_runtime.py` 将 runtime 原冻结 Git 源、完整 native
  snapshot、实际 `.d` 编译依赖和最终 archive members 与新 consumer 的实际输入
  逐项比较；证明作为安装 profile 的一部分保存，旧 runtime 锚点不改写。
- `tests/fixtures/network/installed_dynamic_tls.cpp` 真正进入 GNU constructor/main，
  检查主线程 TLS/errno 与当前线程拒绝语义，通过认证 Net2 peer 获取 DHCP lease，
  使用实际 Mbed TLS 与独立 OpenSSL peer 完成 TLS 1.3、全新 nonce 与关闭通知。
- `tests/installed_dhcp_tls_peer.py` 独立解析 DHCP/ARP/DNS/TCP wire 数据并使用
  OpenSSL MemoryBIO。它不复用 guest 的 lwIP、DHCP 状态机或 Mbed TLS 实现。
- `tests/installed_dhcp_tls_guest.py` 冷启已选安装盘，驱动续租、到期、停启、
  身份拒绝、信任根选择和真实服务死亡，并比较资源、归属数据库与持久文件。
- 普通 Xsh 增加 `spawn-command <command> [args]`，仅复用已有
  `launch_file(... inherit_create=true, background=true)`。无需文件名授予权限，
  不改变 `spawn-file`/`exec-file` 不继承创建权的既有语义。后台控制器让 Xsh
  能在动态调用者阻塞时管理自己拥有的服务。参见 [shell launch 契约](../contracts/shell_launch.md)。

不分配 syscall、IPC operation、wire 布局或动态启动 ABI。GNU runtime 采用当前
公共 v2 启动闭包，未使用另一条进行中的 v3 runtime，也未借用其他会话的未验收
shared library。C SDK、native SDK 与实际产物均保留完整独立身份。

## 关键选择

本组合是共享 GNU libc 的主线程闭包，没有 `libgcc_s`。按既有 GNU 契约，
`pthread_create` 返回 `ENOTSUP`；fixture 检查这一结果，并检查 constructor 的
初始 TLS=17、main TLS=19、errno 保持独立正确。专属 profile 去掉 `threads`
及 `cxx_runtime` 能力声明，完整父 SDK 绑定仅作为来源。真实工作线程、跨线程
TLS 和 C++ 标准库由别的配置负责，本组不将它们计为通过。

普通 native SDK 同时携带历史 C 头。GNU TLS 编译仅导出其 `xos/` namespace，
所有 C 头来自明确的 GNU sysroot，避免 `-I` 优先级使另一 libc 的 `sys/cdefs.h`
遮蔽 GNU 头。Mbed TLS 的 128 位算术引用由同一个已认证 C SDK 的 `libgcc.a`
解决；链接 map 明确记录它，不链接第二个 libc，也不伪称存在 shared unwinder。

Net2 每进程仅接纳一个 session。续租先在原 TLS 连接上接收独立 peer 在 DHCP ACK
之后发出的 nonce 响应，再通过同一已认证 session 查验 epoch 和到期时间。
同一配置的续租必须保留 epoch 和原连接，并延长 absolute expiry。
新增 `net2::client::lease_status` 与 `native_tls::stream::lease_status` 只复用现有
operation 18；后者使用原始 stream deadline，不开第二 session、不重连。握手前
和 finish 后返回 `closed` 并清空输出，live query 失败则退役 stream。

原 runtime 的完整 native 头目录快照包含新增转发前的 `net_transport.hpp`，
但它没有参与任何实际 GNU native object 编译。核验器将 14 recipe、303 port、
150 native 输入的合并 388 个 Git blob 与原 `f97ddece` 逐一核对；150 个原
native snapshot 文件、9 个真实产物保持原锚点。18 个实际 `.d` 与 18 个被链接
archive member 对应，52 个实际使用的 native 输入和 GNU public startup ABI
与新 consumer 相同。唯一差异是没有参与 runtime 编译的 additive client 头；
报告分别保留 runtime 冻结源和 consumer 冻结源，不声称新 runtime 构建。

服务恢复分两类。`net-stop` 有序退出会确认设备 reset，允许同 boot 新 PID 重启，
旧 PID 必须在网络使用前被拒绝。真正 `kill` 未确认 DMA 停止时则遵守
[设备授权契约](../contracts/device_authorization_v1.md)：66 页 DMA 被隔离，连续三次
regrant 返回 `UNKNOWN(-11)`，资源保持一致；只有冷启动恢复该安装组合。
本组不解除隔离，不把这 66 页计作普通 caller 泄漏，也不宣称同 boot crash restart。

## 最终证据

最终 guest 与产物后置复核均 **passed**：3 次 cold boot、9 组验收、12 个动态
GNU caller；独立 peer 记录 10 条真实 TLS 1.3 flow，其中 7 条成功路径验证双方
close_notify。公开报告为 [p1_k4_installed_dhcp_tls_20261128](../reports/p1_k4_installed_dhcp_tls_20261128/README.md)，
采用新的平铺根清单。原始 producer 的 `built_not_run` / `installed_candidate_not_run`
状态保持不变，组合资格由独立 guest 报告给出。

| 绑定项 | 实际身份 |
| --- | --- |
| system build / source inputs | `13648be5fde3bd78` / 2309，另补齐 13 个 runtime metadata 文件 |
| system manifest SHA-256 | `29df33894bc6ce249f5cf7391a76927e86b7af9dacb175a2a8a93ba683ad8d27` |
| ordinary ISO SHA-256 | `9370740186c5802b81b3117c697b304f92945426de14d5b87451e60f38f54635` |
| native SDK manifest | `10e1c1dec9b84a26eb9773d82db7372cf2066d429f054d2b49542a551c6ae2e1` |
| native SDK full tree | `a7abc7fc74c01d1124b1e92427361ec5b32a25ec4fa645c5ad541e442ef60a0e` |
| C SDK manifest | `d5a5d40d1ad60d11d8dbae2b517d5aaeae0244fdcadb09145b2a45095ca884fa` |
| C SDK sysroot full tree | `3b7f05a77d720c6de494a470f495d4688c103e83a84ae997c13a21663ca9624c` |
| frozen GNU runtime manifest | `b0982dfe12f319d9a580f4716b66a4838a6d6dfc02576b0c82fee05d4a27d32b` |
| GNU native ABI | `c080a98581ac683150ce49f79fccc85cef737bb26a7d62afa6ca0181505696e3` |
| selected profile | `xos-x86_64-glibc-k4-dhcp-tls-c3581f3c3f99` |
| profile SHA-256 | `f46c32882f29fc651a29a403aefc63e433dabae9605c9f49b5ac28baa88a9e3c` |
| XPK SHA-256 | `6f1ecb1d7456bc8baff47d9bbb462feadcf4befc7b049e076bc36e0afec499ef` |
| installed disk SHA-256 | `6ccf0fbea5d8aa46ad90a6857da4489c6cd9e1d6f82abba3796456a4b99446ce` |

实际运行保持 epoch 2 的 lease 从 49.19s 延至 55.19s，且使用原 live TLS/session。
到期故障在 peer 收到全新 TLS 请求后 armed，记录 expiry=73.19s，pending read 在
73.20s 返回负值，延迟 10ms，早于原 stream deadline=87.58s。有序停止唤醒耗时
0.145758s，服务 PID 9 变为 21；旧 PID 在 DNS/TCP 前拒绝，新 caller 成功。
stale trust pin 同样在 DNS/TCP 前拒绝，显式选择安装的 generation 2 后成功。

真实 kill 的 pending TLS 在 0.100511s 内失败。三次 regrant 返回 `UNKNOWN(-11)`。
资源数组为 `[free_pages, tasks, completions]`：正常基线 `[129589, 3, 1]`；有序
无服务基线 `[129765, 2, 0]`；最终隔离基线 `[129699, 2, 0]`，恰好保留 66 页。
第三 cold boot 自动 DHCP/ACD 后再次成功 GNU/TLS，恢复 `[129589, 3, 1]`。
每次 boot 后全部 20 个 owned files、完整 package DB 和 index 的字节均不变，
原始安装候选也未被运行器改写。

四对象生产 preflight 均 error=0，closure=0；最终 system/source snapshot、runtime、
consumer inputs、完整 C/native SDK 与真实产物的后置核验通过。许可证审计为
10 个材料、0 个 open item。公开日志是明确标识的脱敏派生版本；raw 原件摘要不
冒充公开文件哈希，测试私钥不安装、不发布。文档与公开证据门禁的实际结果另见
[validation.json](../reports/p1_k4_installed_dhcp_tls_20261128/validation.json)。

提交前文档检查通过：2353 个 local links、79 个已分配 syscall、73 个 history
source。暂存差异相对明确基线 `f97ddece` 的 44 个文件全部扫描，PUBLIC_READY，
无 finding。新报告 28 个叶子全部平铺校验匹配。全仓报告检查仍有 17 个既有失败
（6 个 glibc_v2_* 旧 schema 与 Mobius Qt/widgets 的旧不合法项），本报告 compliant；
本组不修改这些历史报告，也不把全仓门禁写成通过。

## 构建与重放

使用记录的 GCC 16.2.0、binutils 2.47.20260726、QEMU 11.1.3 与 CMake 3.31.6。
宿主 SDK 不含 CMake，本次使用独立 wheel，SHA-256 为
`1c8b05df0602365da91ee6a3336fe57525b137706c4ab5675498f662ae1dbcec`，没有修改 SDK。
`K4_INPUTS` 指向按仓库锁验证的 source archives，`GLIBC_SDK` 指向明确选中的
GNU C SDK；以下命令在相应已验证的 host SDK 环境内执行。

```sh
export XOS_QMP_TRANSPORT=pipe
export XOS_LWIP_SOURCE_ARCHIVE="${K4_INPUTS}/lwip-2.2.1.tar.xz"
python3 scripts/build.py --output-dir build/k4_system \
  --quiet-demos-on-launch \
  --net-dhcp-profile tests/fixtures/network/installed_dhcp_tls_profile.json
python3 scripts/installed_dynamic_tls_support.py --certificates build/k4_certificates
python3 scripts/build_glibc_shared_runtime.py \
  --sdk-build "${GLIBC_SDK}" --public-startup --jobs 2 \
  --sdk-manifest-sha256 "${C_SDK_MANIFEST_SHA256}" \
  --sdk-tree-sha256 "${C_SDK_TREE_SHA256}" \
  --glibc-archive "${K4_INPUTS}/glibc-2.44.tar.xz" \
  --gcc-archive "${K4_INPUTS}/gcc-16.2.0.tar.xz" \
  --gcc-signature "${K4_INPUTS}/gcc-16.2.0.tar.xz.sig" \
  --gcc-keyring "${K4_INPUTS}/gnu-keyring.gpg" --output build/k4_runtime
python3 scripts/build_installed_dynamic_tls.py \
  --sdk-build "${GLIBC_SDK}" --native-sdk build/k4_system/sdk \
  --runtime-build build/k4_runtime \
  --source tests/fixtures/network/installed_dynamic_tls.cpp \
  --tls-archive "${K4_INPUTS}/mbedtls-4.1.1.tar.bz2" \
  --certificates build/k4_certificates --output build/k4_program \
  --name installed_dhcp_tls --generation-id 2026112804 \
  --sdk-manifest-sha256 "${C_SDK_MANIFEST_SHA256}" \
  --sdk-tree-sha256 "${C_SDK_TREE_SHA256}" \
  --native-sdk-manifest-sha256 "${NATIVE_SDK_MANIFEST_SHA256}" \
  --native-sdk-tree-sha256 "${NATIVE_SDK_TREE_SHA256}"
python3 scripts/build_dynamic_launcher.py --system build/k4_system \
  --sdk-build "${GLIBC_SDK}" \
  --sdk-manifest-sha256 "${C_SDK_MANIFEST_SHA256}" \
  --sdk-tree-sha256 "${C_SDK_TREE_SHA256}" \
  --generation build/k4_program/payload/generation.bin \
    /usr/lib/xos/generations/installed_dhcp_tls.bin --output build/k4_controller
python3 scripts/package_installed_dhcp_tls.py --system build/k4_system \
  --program build/k4_program --launcher build/k4_controller --runtime build/k4_runtime \
  --runtime-source-revision "${RUNTIME_SOURCE_REVISION}" \
  --certificates build/k4_certificates --profile "${C_SDK_PROFILE}" --output build/k4_installation
python3 tests/installed_dhcp_tls_guest.py --system build/k4_system \
  --installation build/k4_installation --certificates build/k4_certificates --output build/k4_guest
```

所有输出必须是新目录。独立选择和记录完整 SDK manifest/tree anchors，不能用
部分头或静态库哈希替代；换源、换 SDK 或换 policy 后生成新的组合与资格。
普通 system builder 绑定所选 src、scripts 与 tests 输入，因此最终系统构建开始后
冻结这些输入；若变化则重建对应 system/SDK/consumer，不把旧报告改绑。
`RUNTIME_SOURCE_REVISION` 必须是 runtime 实际使用的冻结 Git 提交；本次为
`f97ddece8146fb7a4bd2eadfdd4845757557611b`。从新的冻结提交重新构建 runtime
时传入该新提交，核验器不接受猜测或忽略输入差异。

核验环境必须能读取该提交的 Git 对象。若隔离 SDK 仅挂载 worktree 而未挂载其
common Git directory，可把该精确提交完整 shallow-clone 为独立 bare repository，
核对 commit 并执行 `git fsck --full`，在 SDK 内显式设置 `GIT_DIR` 后运行 package。
它只提供冻结源码对象，不取代当前 consumer 的完整 source/artifact 逐项核验。

## 已发现并修正的开发尝试

最初宿主缺 CMake；补上独立 pinned 工具后，GNU 编译发现 native C 头遮蔽，
随后链接又发现需要 `__udivti3`。均由明确的 include 隔离和同 SDK 算术 helper
解决，失败日志保留。第一次 package 比对错误地将父 profile 的完整 C++ SDK view
与 C-only view 字典作全等比较；现改用既有严格 `verify_profile` 核验完整父绑定，
再对独立 manifest/tree 双锚。

初次 guest 用 `spawn-file` 启动动态控制器，因无创建权正确失败；新增普通后台
入口后，这一拒绝作为回归继续验证。另一次诊断证明 GNU main 已进入，但错误
期待无 unwinder 的闭包创建工作线程；现明确主线程范围并实际检查 `ENOTSUP`。

后续候选验证了两个冷启动，但续租 fixture 又开第二个同 PID session，触发
正确拒绝。中间候选修正关闭/查询顺序后续租通过；最终版本进一步复用原 live
session 查询 lease，保留原始 absolute deadline。expiry peer 继承了上一轮已完成的
renewal XID，错误拒绝下一轮正常 XID；现仅重置本次故障周期的 renewal 观察状态，
仍禁止到期时静默重新获取 lease。真正 kill 后尝试同 boot restart 失败，则是
既有 DMA quarantine 的正确边界；现拆分有序恢复与 crash 后冷启动恢复。
另一个完整候选在系统负载下让 GNU 装载跨过 18 秒 lease，暴露了在启动 caller
前停止 ACK 的时序错误。最终改为成功握手且 peer 解密全新请求后才停止 ACK，
调用者通过原 session 读取当时有效的 lease；不从 host 启动耗时推断到期点。

最终源码冻结后的两个 package 前置检查也保留失败：首先隔离 SDK 中 worktree 的
common Git 对象不可见，补上显式 `GIT_DIR`；随后 system builder 的编译输入快照
缺少 runtime 所记录的 `README.md` 等 recipe 元数据，按原 runtime hash 补齐。
这两次均未放宽校验，未改写 runtime 身份，也未改变已冻结的 2309 个 system
输入或 program/controller 产物；成功安装另用新输出目录。

这些旧候选保持 failed / diagnostic / unqualified，不因最终通过而被晋升。
已完成构建的可重建上游 source/object 在保留清理 receipt、认证 archive 身份、
SDK snapshot、全部真实 runtime/consumer artifacts 与日志后清理，前后哈希复核。
未触碰其他会话工作区、构建或旧冻结报告。

## 限制与交接

本组不覆盖物理 NIC、SMP、一般 Internet CA bundle、可信硬件时间/熵、断电、
硬盘直接引导、任意 online dlopen、pending dynamic v3 或 GNU 工作线程。测试根
只用于具名隔离配置。TLS 使用原始 29 秒 absolute deadline，到期失败须早于该
deadline 且在记录的 lease expiry 后 3 秒内；stop/kill 的 host wakeup 界限为 8 秒。

共享 state/registry 由主协调者汇总。发布审查应核对最终源树与 flat manifest，
保持 shell launch 小 hunk 的兼容语义；若整合改变生产实现或本组绑定输入，按受影响
范围重新构建并运行，既有证据不自动转移到新的组合。
