# glibc G1：XOS 目标识别与配置阻塞调查

2026-11-13；基线 `ffc4ea69`，独立工作树；**G1 partial，XOS glibc 未构建、未运行**。补充动态链接目标见 [移植勘查](../plans/glibc_port_scout.md#动态链接明确目标与独立验收)。本次不修改公共 ABI、内核、SDK 或默认 libc。

## 输入与边界

沿用 [G0](../plans/glibc_g0.md) 的 glibc 2.44 候选归档，SHA-256 `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`；签名与可信发布者仍 **NOT_RUN**，仅用于研究，不可发行。`0001-config-sub-xos.patch` SHA-256 `5814d4d9f34271abc0aadccb29e9fe05589f16a257452df2ac3472659c95b2a4` 仅使上游 config.sub 识别 `x86_64-unknown-xos`；不是 sysdeps、ABI 或功能实现，不将其加入声称已验证的发行锁。

宿主 macOS arm64；目标编译器 `x86_64-elf-gcc 16.2.0` 的真实 `-dumpmachine` 为 `x86_64-elf`，不是 XOS 目标工具链。隔离下载并解包 GNU Make 4.4.1、Gawk 5.4.1、Bison 3.8.2，不升级共享依赖；Gawk 的私有副本重定位到本机依赖后重新签名。GNU readelf 使用对应 x86_64-elf 工具。`makeinfo` 与 GNU sed 未满足，配置警告部分特性/测试禁用。以上只消除调查中的工具障碍，不构成可发行、可复现供应链资格。

## 实测

1. 候选补丁后 `config.sub x86_64-unknown-xos` 输出该规范三元组。以脚本 `python3 scripts/glibc_g1_probe.py --archive "$GLIBC_ARCHIVE" --output "$NEW_SCRATCH"` 重放，归档哈希核对、私有解包和补丁应用成功；正常 configure 退出 1，报 `The GNU C library is currently unavailable for this platform`。
2. 相同脚本加 `--hacker-mode` 仅用于调查，绕过上游平台门；满足关键工具检查并明确选择目标 C/C++ 编译器后，在 sysdeps 搜索报 `Operating system xos is not supported`，退出 1。日志 SHA-256 `298810b17d56dbc411569853a446ac8b695115af6407079a395c3c8882433436`。该日志的路径和工具环境为本机临时数据，不是可移植复现命令或发布材料。
3. 为确认搜索行为，仅在丢弃型诊断源码副本创建**空** `sysdeps/xos`，并使用 hacker-mode；configure 退出 0，实际选择 `sysdeps/xos`、x86_64 通用目录和 `sysdeps/generic`。空目录没有提供任何 XOS 操作系统功能，**不能解释为 XOS 平台配置成功**。随后运行 GNU make，退出 2：`This configuration not matched in ../abi-tags`。不得随意给 XOS 伪造 GNU ABI tag 来宣称成功。生成配置还显示 C++ 编译器未通过链接检查；裸 `x86_64-elf` 和 XOS sysroot 的差异仍需解决。
4. 首次使用新工具时 configure 优先拾取系统旧 `gnumake`；通过私有 PATH 别名改正。补充 target readelf 和显式 CXX，避免宿主工具误选；辅助 makeinfo/sed 仍有警告。所有失败保留为失败，未执行静态 libc 交叉构建、目标头/符号资格、客体运行、动态链接、许可或源签名验证。

## 下一步

明确 XOS target 三元组及 GCC/binutils/sysroot 的真实匹配；依据上游端口方式设计 XOS sysdeps 的必要实现、启动及 ABI tag 策略和最早可执行纵切片。先盘点 generic ENOSYS/伪成功、构建需要的目标内核头、TLS/线程与 loader 合同，再以独立测试证明行为；不能把 hacker-mode、空目录或通用桩冒充后端。源码签名需通过可信独立来源确认公钥后验证；取得完整宿主工具并记录来源、版本和散列。G1 继续，不将该调查视为 G2 或动态链接完成。

## 继续：NPTL 依赖探针（2026-11-13）

在独立解包副本中进行更深入的**负向诊断**：`--hacker-mode --diagnose-nptl` 创建临时 `sysdeps/xos/Implies` 指向 `nptl`，并添加仅供测试的 ABI tag 255；该数字不是 XOS ABI 分配，不写入候选源码或发行材料。configure 返回 0 仅说明诊断目录组合可生成 Makefile，不能说明 XOS 后端有效。随后 GNU make 退出 2，首先暴露 `bits/semaphore.h` 和 `bits/pthread_stack_min-dynamic.h` 缺失；日志 SHA-256 `2469e67b16fa6c9da9e1e8ce6865dd9189a4062f91966540966aed111c91be43`。诊断入口拒绝无 hacker-mode 的该选项、错误归档与已存在的输出目录；`python3 tests/glibc_g1_probe_test.py` 通过。这些边界测试不是 glibc 功能测试。

| 实际接口 | glibc 2.44 源码依赖 | 当前 XOS 接口 | 尚需证明/实现 |
|---|---|---|---|
| 初始 TLS | x86-64 NPTL `tls.h` 的 `TLS_INIT_TCB_SIZE` 是 `sizeof(struct pthread)`，包含 DTV、自指针及线程描述符 | `src/user/arch/x86_64/tls.cpp` 按 variant II 映射静态模板，在 TP 写自指针并给 TCB 预留 16 字节；`sys_process_tls` 仅允许创建者对 building 子进程设置 | glibc TCB 大小、DTV、对齐、FS 基址变更权和主线程早期初始化必须有独立契约及真实客体证据；不可把现有 16 字节当完整 TCB |
| 创建/退出 | `nptl/pthread_create.c` 使用 `__clone_internal`、退出时的 clear-tid、rseq 与 robust-list 路径 | prepare/start/abort、begin_exit/exit、join/detach，且有每进程四线程、固定 stack/TLS 配额 | 定义成功/失败、发布原子性、线程 TLS、退出通知、清理、join 竞态和限制；不能只映射 syscall 号码，robust/rseq 是否可裁剪须由实际构建配置和语义证明 |
| 等待 | NPTL 的 futex、绝对时限、取消与 robust mutex 语义 | `sys_wait_word` / `sys_wake_word`、绝对单调 deadline，受 XOS 地址与资源约束 | 比较共享/私有等待键、竞态、取消、超时、内存生命周期；共享 futex、requeue、优先级继承和 owner death 不能凭接口同名宣称支持 |
| 启动/动态链接 | glibc startup、辅助向量、解释器与动态 TLS | XOS `_start` 收到 `startup_info`，既有 ELF 解析在用户态；当前 G1 未实现 glibc CRT | 版本化启动与 auxv 约定、真正 XOS 工具链、独立 sysroot、`PT_INTERP` 和隔离资源权限需另行冻结 |
| syscall 与文件 | glibc 内部系统相关头及 errno | x86-64 XOS SDK 使用 `int 0x80` 和 XOS 号；文件经认证文件服务/SDK | 独立 XOS sysdep 调用与错误映射，审查 fd/session/fork/exec/路径；禁止将 Linux syscall 号或 newlib 内部结构当成 XOS ABI |

以上是当前源码比对和诊断，尚无可运行 glibc；已运行探针的 ABI tag 及占位目录不能发布或用于真正目标。下一步应先确定 XOS glibc 线程后端的构造与初始 TLS 所有权，再按真实头、启动和等待语义实现最小静态纵切；签名、工具链、动态装载和授权仍是独立验收。

## 继续：源码签名与密钥有效期（2026-11-13）

从 GNU FTP 取得公开 GNU keyring，SHA-256 `8013de59880f7a59f53b6bd207f4d2a408d67b84a82fa9cba1dbbf443428e2db`。隔离准备 GnuPG gpgv 2.5.24 后，实际验证得到 `VALIDSIG`，签名子钥 `FD19E6D31B192EE4DC63EAD3DC2B16215ED5412A`，主钥 `35B17DF5752577CA0C541CEB94BFDF4484AD142F`；但该公钥环还报告 `EXPKEYSIG`，即使 gpgv 退出 0 也必须拒绝作为有效来源依据。

另外取得更新的 keyserver 公钥（装甲文件 SHA-256 `7305140fd8333ceefcb1a3aa88e78a865672caff82b9f274083b1321f90d178c`，解码后 keyring SHA-256 `4d7c10f67569448dca4901245e896988dadfa1318c208b3f3bbfb92c0fe440cc`）；gpgv 输出 `GOODSIG`、相同 `VALIDSIG` 和主钥指纹，签名密钥未报告 `EXPKEYSIG`。个别无关旧密钥有 `KEYEXPIRED`，不能仅凭这一通用状态判定签名密钥已过期。`scripts/glibc_g1_signature_diagnostic.py` 固定输入哈希和指纹、检查 gpgv 状态并拒绝过期/撤销签名；旧 GNU 公钥环应被拒绝，更新公钥可通过密码学检查。额外对篡改的 RSA 签名进行负向验证，即使相应更新了输入哈希也被拒绝。

**信任仍未完成**：keyserver 公钥的更新、有效期及撤销信息尚未经独立可信渠道确认，gpgv 将指定 keyring 当作信任输入，不能据 `GOODSIG` 推导身份信任。来源锁仍为 `candidate_unverified_signature`，仅供研究。签名核对不改变上述 G1 构建和客体验收状态。

## 继续：XOS 目标对象与隔离头文件探针（2026-11-13）

新增研究用 `src/ports/glibc/sysdeps/xos/`：x86-64 `_exit` 通过 XOS syscall 2 终止进程，意外返回时执行非法指令；`kernel-features.h` 不宣称 Linux 可选内核特性；`bits/stdio_lim.h` 的 `FILENAME_MAX` 为 256 字节（含 NUL），对应现有 XOS 文件路径缓冲界限。该定义是当前能力的候选值，文件描述符及 POSIX 路径语义仍须另行验证。它们不使整个 sysdeps 或运行时成为完成品。

重新从候选归档解包，隔离工具链，指定原本为空的私有 sysroot，以现有 `--hacker-mode --diagnose-nptl` 研究配置运行。构建时 `config-sysdirs` 实际包含 `sysdeps/xos`，编译器实际目标依然是裸 `x86_64-elf`，且配置仍临时使用 NPTL Implies 与合成 ABI tag 255；这些不是正式平台配置。所用编译器 SHA-256 `078530461bdb61bcd19fcb0da101c24d34ab19a924b31c4fc7b54bd5d7607b6f`，候选源码、补丁及 overlay 的散列和完整命令写入私有 report。

- glibc 的 `stdlib/abs.c` 和本端口的 `sysdeps/xos/_exit.c` 经 glibc 对应子目录规则实际编为 ELF64 x86-64 可重定位对象；对象 SHA-256 分别为 `82a2631427ea94843428e95d4029a68ae046780349352293046cbfb1501f3628`、`1a746248f719c2fe779275457d76db78d8bef75e1f46a5711b7c0a656686c4bb`。readelf 检查了符号，反汇编核对 `_exit` 的 syscall 号、`int 0x80`、返回后 `ud2` 与无外部重定位；未运行该对象。
- 尝试在私有 sysroot 安装 glibc 头文件，安装到 116 个文件后退出 2，首个头安装阻塞为 `bits/semaphore.h` 缺失；并行构建退出 2，暴露 `bits/semaphore.h` 和 `bits/pthread_stack_min-dynamic.h` 缺失。已安装文件是**不完整且未经资格认可的诊断产物**，不得作为 SDK。manifest SHA-256 `3d4de5b29b4a89511e25850b2b9b184d63466fdde3d88f147cdd73171af488ee`；抽查 `stdlib.h` 与上游源一致，`bits/stdio_lim.h` 与 XOS overlay 一致。
- `tests/glibc_g1_artifact_test.py` 对实际对象、符号、目标指令、编译依赖路径与散列、头文件清单和抽样来源做检查：依赖只来自解包 glibc、私有构建树或交叉 GCC 自身头目录，未混入 newlib/宿主 libc；该检查通过。`tests/glibc_g1_probe_test.py` 也通过。报告 SHA-256 `3d3a9c6d2474989e54f89d9a57fa2fdbb25731d57cea784f087488e0e12a78ef`；私有路径、日志和对象不作为发行物提交。

G1 仍 **partial**：还没有真实、无合成 ABI tag 的完整 XOS 后端配置，没有完整 glibc 或可用 SDK。下一步须为 NPTL 的线程、等待和信号量定义与实现可维护的 XOS 后端及 ABI，然后从干净输入重跑配置、对象、头文件与来源核验；不能把上述诊断对象当作完整 libc 或客体验收。

## 继续：无合成 ABI 标记的 XOS 配置探针（2026-11-13）

`sysdeps/xos/preconfigure` 使用 glibc 提供的端口预配置入口，仅对 `x86_64/64-xos` 设置 `libc_config_ok=yes` 并明确打印未完成警告。这个变量按上游定义会跳过其不支持平台的检查；它是实验端口的定向登记，**不是上游已支持或 XOS 后端已完成的证明**。`sysdeps/xos/Implies` 明确将 NPTL 选为依赖调查方向，选择源码不代表 XOS 已提供其线程、TLS、futex 或信号量语义。预配置入口对 x32、非 XOS 和其他架构不放行。

`--xos-backend` 从锁定候选归档解出新源码、应用 XOS 三元组补丁并复制仓库中的真实 XOS overlay，不使用 `--enable-hacker-mode`、不修改 `abi-tags`、不生成假的 ABI tag。私有空 sysroot 明确传给交叉编译器，正常 configure 退出 0 且 `config-sysdirs` 选择 XOS 和 NPTL；整体 make 退出 2，最早明确阻塞是上游 `abi-tags` 无 XOS 记录，另有 semaphore、pthread stack minimum 头缺失。`install-headers` 退出 2，在 116 个文件处因 `bits/semaphore.h` 停止。这些失败属于预期记录，不改变后端未完成状态，也不分配未经约定的 GNU OS ABI 标记。

同一干净输入使用 glibc 的实际子目录规则编出 `abs` 与 XOS `_exit` 的 ELF64 对象，SHA-256 为 `7cef76c76fe1cb694a21dbb3b58bf5618961057173d33be5a65f8c8b7beb9644`、`374ceb2cd5e6f647f88482e6ae4cb4ce35ea5758b40aace7cfcecf5b5689c3b3`。对其符号、汇编、依赖边界、头文件内容及散列执行 `tests/glibc_g1_artifact_test.py` 通过；测试还核对归档与锁、上游 `abs.c`、仓库补丁和 overlay、探针与各工具散列、所选 sysdeps、无虚构 ABI tag。目标选择与探针保护测试通过。私有报告 SHA-256 `393d36e4bacba1da1a96ea76905386cc3891a6260abbe40c23c2e098f5756df2`；对象散列绑定当次构建路径，不能当作可重现二进制声明。

```sh
# 在满足工具要求、已设置隔离工具 PATH 的环境中：
python3 scripts/glibc_g1_probe.py --archive "$GLIBC_ARCHIVE" --output "$NEW_SCRATCH" --xos-backend
# 完整构建尚未通过，探针预期非零；继续检查产生的报告和实际对象：
python3 tests/glibc_g1_artifact_test.py "$NEW_SCRATCH" --archive "$GLIBC_ARCHIVE"
python3 tests/glibc_g1_probe_test.py
```

G1 仍未验收：真实 XOS 工具链、正式 ABI note 策略、完整目标头与 libc 尚缺，候选签名的信任状态未变；本次不声称 guest、动态链接或 POSIX 支持。下一步先厘清 XOS 可执行格式与 glibc ABI note 的衔接，再实现有真实语义的目标线程/等待基础，不能为了通过构建复制 Linux 假设。

## 继续：XOS 的 GNU ABI note 构建路径（2026-11-14）

现有 `src/user/loader/elf.cpp` 对 ELF64 ET_EXEC 检查机器、OSABI、边界和 LOAD 等，但对 `PT_NOTE` 跳过内容；不读取 GNU ABI note。glibc 2.44 的通用 `csu/abi-note.c` 需要 `abi-tags` 分配的 GNU OS 编号，而 XOS 目前没有已知分配。研究配置据此选择不发出该 GNU OS ABI note，绝不借用 Linux 编号或保留的虚构数值。此举不提供版本检查或原生/外来二进制区分，也不决定未来 ABI：动态链接的身份、版本与拒绝策略仍须由 D0 冻结并在 D1/D3 验证。

新增候选补丁 `0002-xos-abi-note.patch`（SHA-256 `ad2c03e0613c8765fd4f3033efbf69d6357b39a70547da2fc1186df91aceac52`），仅在 XOS 配置下提供无 GNU OS 标签定义的 `abi-tag.h`，其他配置保留上游路径。实验 XOS 后端提供 `sysdeps/x86_64/xos/abi-note.c`，保留上游 x86 ISA property note 而省去 GNU OS ABI note。实际检测发现放到通用 `sysdeps/xos` 会被更高优先级的上游 x86 文件覆盖，已改为架构与系统组合目录；最终 configure 的 sysdeps 列表与实际编译命令均确认选择后者。

在新的隔离研究输出中，不使用 hacker 模式或合成 ABI tag，正常全构建越过 `abi-tags` 阻塞，仍因 `bits/semaphore.h` 与 `bits/pthread_stack_min-dynamic.h` 缺失退出 2。正常 `csu/abi-note.o` 构建仍被这些前置项阻塞；为了单独验证所选源和 note，额外调用 glibc 子目录 make 并明确清空 `before-compile` 前置项：该**受限单对象诊断**成功，readelf 显示 x86-64 baseline 的 `NT_GNU_PROPERTY_TYPE_0`，没有 `NT_GNU_ABI_TAG`。它不是正常 csu 构建通过，更不是客体测试。其对象 SHA-256 `4289a089ad3e7ace1f795c8ea2e55c1ce9e898b53d13e70eb1a2b4645a35a3f5`；报告 SHA-256 `f18bf43be6bcbd93fb35d6787d158ba2391fbb41829f197c23a71cd5fee1d98f`。

目标对象、编译依赖、sysroot 部分头文件、注册目标限制与报告输入散列的检查均通过，探针与证据路径检查重新执行。G1 仍 partial；下一处实际工作是为 NPTL 与 XOS 线程后端建立真实语义和目标头，而非将跳过前置项的结果当成完整 glibc 构建。
